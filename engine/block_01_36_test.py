r"""block_01_36_test — total escalation, worker-death handover, session-limit
resilience (block 01-36, ADR-0003 D-E + D-F + D-H + engine-side D-G + the ND-02-10/
ND-09 slice of D-J).

Context: SIM tron-40 proved (against events.jsonl + worker timelines, ADR-0003
Context section) that TRON's escalation/outage handling dropped problems on the
floor — a block-less architect wall was logged `unclassified` (silent discard); a
73-min session-limit outage saw the architect (cardinality-1) respawned
UNCONDITIONALLY, taking ~146 of ~218 leaked spawns, because the fleet-refusal hold
never covered it; two cases `case_safe_parked` mid-outage and died at drain,
undelivered. This corrective is surgical, not a redesign — most of the escalation
machinery (wall/case handling, architect-first triage, architect liveness, the
fleet-refusal hold's canary mechanism itself) already worked; this suite proves the
SPECIFIC gaps are closed, and that everything already-correct (_admit's sender-first
block resolution, the case-reping ladder, the canary's healthy-turn-not-dispatch
release rule) is untouched.

Standalone runner convention (exit 0 = pass, no tokens, no network — TRON_DRY stubs
every side effect; AC-8b's own "real LLM call" assertions monkeypatch
`judge._call_llm` directly, exactly like block_01_35_test.py's AC-5, which bypasses
that dry guard entirely).

Covers this block's own acceptance criteria
(blocks/01-36-total-escalation-handover-outage.md):
  AC-1 test:<blockless_wall_routes> — a `worker.wall` naming no block never logs
       `unclassified`: it attaches the sender's in-context block, else opens a
       block-less case (block=None) and reaches a resolver. Covers both entry
       points D-E names: a worker-raised wall at `_admit`, and an architect's own
       block-less raise (`_escalate_from_architect`).
  AC-2 test:<architect_cant_solve_or_down_to_operator> — architect can't-solve
       (explicit raise) AND architect-unreachable (no architect at all) both route
       to the operator; a settled case stops re-sending; an ordinary (non-refusal)
       architect death restores immediately with NO operator page (a routine
       respawn gap must not page).
  AC-3 test:<operator_page_dedup_per_case> — two different conditions racing to
       open/page an architect-stall case for the SAME underlying job (the ordinary
       idle-cap arm and the bounce-cap arm, `_open_architect_stall_case`'s own
       shared idempotency) mint/page exactly once, deduped on case id.
  AC-4 test:<safe_park_guaranteed_delivery> — a case that reaches `case_safe_parked`
       gets a real page attempt (never a bare emit skipping the paging chokepoint);
       a case still undecided at session end also gets one, guaranteed, never dies
       unattempted at drain.
  AC-5 test:<worker_death_full_handover_outage_aware> — a recovery dispatch's
       assignment carries full context + a timeline tail + a re-verify instruction
       (never a fresh dispatch's plain assignment); orders re-target by block state,
       not the dead worker's id; a block whose worker is absorbed into the fleet
       hold (outage) is preserved and redriven, once, on the hold's release — never
       dropped.
  AC-6 test:<injected_outage_hold_persists_bounded_notified> — INJECTION-
       AUTHORITATIVE (ADR-0003 D-I): an injected RunnerRefusal outage engages the
       hold; it persists across a probe-dispatch tick (never releases on dispatch,
       only a healthy TURN); the cardinality-1 architect is covered by the SAME
       single-canary mechanism (never a parallel unconditional respawn — the exact
       tron-40 root cause); the operator is notified exactly once for the hold's
       own engage condition; a spawn-dependent gate's stall counter is FROZEN while
       held (never bumped, never capped) while an observation-only advance still
       proceeds; the hold self-releases on the first healthy canary turn.
  AC-7 test:<escalation_debounce_and_page_receipt_contract> — no duplicate
       escalation for a case resolved/resolving in the same tick it's raised (the
       ~20s stale-escalation race, `_drive_cases` now running after
       `_drain_triggers`); the engine's minimal receipt contract
       (`_consume_page_receipt`) escalates further (forces an immediate re-ping) on
       a permanent-fail receipt, never silently drops it, and never itself
       retries/sends (that stays the transport's job, 02-12 T3).
  AC-8 test:<every_case_terminates_sweep> — an automated sweep over a short
       synthetic multi-path scenario (wall settle, architect relay, abandon,
       safe-park) proves every case that was ever raised/paged either settled or
       remains visibly (never silently) still parked — none vanish unaccounted.
  AC-8b test:<aide_runtime_real_llm_bounded_failsafe> — ND-02-10 (`_page_operator`)
       and ND-09 (`_aide_answer_or_escalate`) are a REAL `judge.call("aide")`
       (mocked at `judge._call_llm`, never a deterministic stand-in), carrying
       Project-Docs context, capped at <=1 AIDE call per tick shared across both
       nodes, with the AIDE-down fail-safe (`ask` degrades to the architect;
       ND-02-10 delivers the RAW/un-briefed detail, never held/blocked).
AC-9 is `manual_by:operator` (the live campaign, verified in 02-07) — not covered
here by design.

Run: python3 engine/block_01_36_test.py   (exit 0 = pass).
"""
import os
import sys
import json
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"
os.environ.setdefault("TRON_WORKER_MODEL", "test-model")

import util                      # noqa: E402
import jobs                      # noqa: E402
import judge                     # noqa: E402
import eventlog                  # noqa: E402
from fsm import Engine           # noqa: E402
from sentry_test import build, started, TRIVIAL_ROLES  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _eng(blocks=None):
    ctx, repo = build(blocks=blocks if blocks is not None else
                       [("A-01", "📋", "none"), ("A-02", "📋", "none")])
    eng = Engine(ctx); started(eng)
    return eng, repo


def _events(eng):
    return [e for e in util.read_jsonl(eng.ctx.event_log)]


def _console_lines(eng):
    return [e.get("text", "") for e in util.read_jsonl(eng.ctx.home_log)]


def _arch(eng, current_job=None):
    w = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
         "status": "busy" if current_job else "idle",
         "current_job": current_job, "block": None, "mbox_seq": 0}
    eng.st.workers.append(w)
    return w


# ══════════════════════════════════════════════════════════════════════════
# AC-1 test:<blockless_wall_routes>
# ══════════════════════════════════════════════════════════════════════════

def test_blockless_wall_routes():
    # (a) sender HAS an assigned block — untouched A-1 sender-first resolution: the
    # block-less path never even triggers, the wall attaches the sender's own block.
    eng, _ = _eng()
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    eng._ingest("worker.wall", {"detail": "stuck on the real thing"},
                {"kind": "worker", "id": "ENG-A-01"})
    eng._drain_triggers()
    case = next(iter(eng.st.pending_cases.values()))
    ok("AC-1 a sender's own in-context block is attached (A-1, untouched)",
       case.get("block") == "A-01", f"case={case}")

    # (b) sender has NO assigned block (a reviewer — _admit nulls its `block`) and no
    # resolvable text ref: the wall must open a BLOCK-LESS case (block=None) — never
    # bounce, never `events.unclassified`, never dropped.
    eng2, _ = _eng()
    eng2.st.workers.append({"id": "REV-code", "role": "reviewer-code",
                            "block": "review:code", "session_id": "dry", "status": "working"})
    before = len(eng2.st.pending_cases)
    eng2._ingest("worker.wall", {"detail": "found a real defect while reviewing"},
                {"kind": "worker", "id": "REV-code"})
    ok("AC-1 a block-less wall (no assigned block, no ref) still opens a case",
       len(eng2.st.pending_cases) == before + 1,
       f"cases={eng2.st.pending_cases}")
    case2 = next(iter(eng2.st.pending_cases.values()))
    ok("AC-1 ...and the case's block is explicitly None (D-E's new case shape)",
       case2.get("block") is None, f"case={case2}")
    ok("AC-1 ...never logged unclassified (SIM tron-40's verified silent discard)",
       not any(e.get("kind") == "unclassified" for e in _events(eng2)),
       f"events={_events(eng2)}")
    ok("AC-1 ...never bounced at the door either (a real reason was given)",
       not any("bounce" in (e.get("text") or "").lower() for e in
               util.read_jsonl(eng2.ctx.home_log)))
    ok("AC-1 ...and it reaches a resolver (parked, undecided — not silently dropped)",
       case2.get("decision") is None)

    # (c) an unresolvable text ref (given, but no canon block) is ALSO block-less —
    # not just an absent one.
    eng3, _ = _eng()
    eng3.st.workers.append({"id": "REV-code", "role": "reviewer-code",
                            "block": "review:code", "session_id": "dry", "status": "working"})
    eng3._ingest("worker.wall", {"block": "ZZZ-NOPE", "detail": "a real reason"},
                {"kind": "worker", "id": "REV-code"})
    case3 = next(iter(eng3.st.pending_cases.values()))
    ok("AC-1 an unresolvable --block ref is ALSO routed block-less, never bounced",
       case3.get("block") is None
       and not any(e.get("kind") == "unclassified" for e in _events(eng3)),
       f"case={case3} events={_events(eng3)}")

    # (d) the architect's OWN block-less raise (_escalate_from_architect, no block
    # in the triaged job) is the SECOND D-E entry point — also a case, never a bare
    # caseless escalate.unclassified.
    eng4, _ = _eng()
    _arch(eng4, current_job={"kind": "triage", "detail": "x", "sender": "ENG-A-01",
                             "block": None})
    before4 = len(eng4.st.pending_cases)
    eng4._escalate_from_architect({"detail": "the architect judged this the operator's call"})
    ok("AC-1 the architect's own block-less raise ALSO opens a case (not a bare page)",
       len(eng4.st.pending_cases) == before4 + 1, f"cases={eng4.st.pending_cases}")
    case4 = next(iter(eng4.st.pending_cases.values()))
    ok("AC-1 ...block-less (None), reaching the operator directly (architect_raise)",
       case4.get("block") is None and case4.get("decision") is None)


# ══════════════════════════════════════════════════════════════════════════
# AC-2 test:<architect_cant_solve_or_down_to_operator>
# ══════════════════════════════════════════════════════════════════════════

def test_architect_cant_solve_or_down_to_operator():
    # (a) architect explicitly can't-solve (judges "operator's call") -> operator,
    # directly (never re-triaged back to itself — the `origin` exemption).
    eng, _ = _eng()
    _arch(eng, current_job={"kind": "triage", "detail": "x", "sender": "ENG-A-01",
                            "block": "A-01"})
    eng._escalate_from_architect({"detail": "not mine to solve"})
    eng._drain_triggers()     # a block-carrying raise queues wall:raised:<block>
    ok("AC-2 architect can't-solve routes straight to the operator",
       any(c.get("block") == "A-01" for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")

    # (b) architect UNREACHABLE (none online at all) -> a wall still reaches the
    # operator (through _triage_to_architect's no-architect fallback, now via
    # _page_operator — a real, case-correlated page, not a caseless one).
    eng2, _ = _eng()
    eng2.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                            "session_id": "dry", "status": "working"})
    eng2._h_escalate({"block": "A-01", "worker_id": "ENG-A-01", "detail": "stuck"})
    cases2 = list(eng2.st.pending_cases)
    ok("AC-2 architect-unreachable ALSO routes the wall to the operator",
       len(cases2) == 1, f"cases={eng2.st.pending_cases}")
    ok("AC-2 ...the page names the case id (a real, settleable page)",
       any(f"[{cases2[0]}]" in t for t in _console_lines(eng2)),
       f"lines={_console_lines(eng2)}")

    # (c) a settled case stops re-sending — closing it makes _drive_cases silent
    # about it forever after.
    eng2._h_apply_decision({"case": cases2[0], "decision": "resume"})
    ok("AC-2 the settled case is gone", cases2[0] not in eng2.st.pending_cases)
    before_lines = len(_console_lines(eng2))
    eng2._now_s = lambda: 100000.0     # far past any reping window
    eng2._drive_cases()
    ok("AC-2 a settled case never re-sends (the re-ping ladder has nothing to find)",
       len(_console_lines(eng2)) == before_lines)

    # (d) a ROUTINE respawn gap (an ordinary, non-refusal architect death) restores
    # the architect on the SAME sweep with NO operator page — "operator is the last
    # resort," a plain crash must not page.
    eng3, _ = _eng()
    eng3.dry = False
    _arch(eng3)
    orig = (jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind)
    jobs.index = lambda: {}                      # architect record simply absent -> dead
    jobs.find = lambda wid, idx=None: None
    jobs.is_alive = lambda wid, idx=None: False
    jobs.last_turn_error_kind = lambda wdir: ""   # NOT a refusal — an ordinary crash
    spawned = []
    eng3._spawn_architect = lambda: spawned.append(True)
    try:
        before3 = len(_console_lines(eng3))
        eng3._sweep()
    finally:
        jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind = orig
    ok("AC-2 a routine (non-refusal) architect death restores immediately",
       spawned == [True])
    ok("AC-2 ...with NO operator page for the death itself (a routine gap never pages)",
       len(_console_lines(eng3)) == before3, f"lines={_console_lines(eng3)}")


# ══════════════════════════════════════════════════════════════════════════
# AC-3 test:<operator_page_dedup_per_case>
# ══════════════════════════════════════════════════════════════════════════

def test_operator_page_dedup_per_case():
    # Two different conditions can both try to raise "the architect is stuck on
    # this job" — the ordinary idle-cap arm (_drive_architect_liveness) and the
    # bounce-cap arm (_bounce_gate) both funnel through the SAME
    # _open_architect_stall_case chokepoint. Firing it twice for the SAME still-
    # busy job (simulating both conditions racing) must mint/page exactly once.
    eng, _ = _eng()
    arch = _arch(eng, current_job={"kind": "triage", "detail": "x", "sender": "ENG-A-01",
                                   "block": "A-01"})
    eng._open_architect_stall_case(arch, "idle 200s with no completion report")
    before_pages = sum(1 for t in _console_lines(eng) if "Above my pay grade" in t)
    cases_after_first = dict(eng.st.pending_cases)
    eng._open_architect_stall_case(arch, "3 bounced reports with no usable completion")
    ok("AC-3 exactly one case is minted for the job, regardless of which condition "
       "asked (dedup on case id)",
       eng.st.pending_cases == cases_after_first, f"cases={eng.st.pending_cases}")
    after_pages = sum(1 for t in _console_lines(eng) if "Above my pay grade" in t)
    ok("AC-3 the operator was paged exactly once, not once per condition",
       after_pages == before_pages == 1, f"before={before_pages} after={after_pages}")


# ══════════════════════════════════════════════════════════════════════════
# AC-4 test:<safe_park_guaranteed_delivery>
# ══════════════════════════════════════════════════════════════════════════

def test_safe_park_guaranteed_delivery():
    # (a) a case ridden through the full re-ping ladder to safe-park gets a REAL
    # page attempt (never a bare emit bypassing the chokepoint) — the safe-park
    # notice itself is the delivery guarantee.
    eng, _ = _eng()
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    cid = eng._open_case("A-01", "wall", "ENG-A-01", "a real blocker")
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng.st.pending_cases[cid]["ping_anchor_s"] = clock["t"]   # prime the ladder's own clock
    span = eng._pace("case_reping_after", 20)
    reping_max = int(eng.knobs.get("case_reping_max", 3))
    for _ in range(reping_max + 1):
        clock["t"] += span + 1
        eng._drive_cases()
    case = eng.st.pending_cases[cid]
    ok("AC-4 the case reaches case_safe_parked", case.get("parked") == "safe",
       f"case={case}")
    ok("AC-4 safe-park emits a REAL page (never dies silently at the cap)",
       any("safe-parked" in t for t in _console_lines(eng)),
       f"lines={_console_lines(eng)}")
    ok("AC-4 a case_safe_parked forensic record exists",
       any(e.get("type") == "case_safe_parked" for e in _events(eng)))

    # (b) a case that is STILL undecided (never even safe-parked yet) at session end
    # gets a guaranteed page too — never dies unattempted at drain.
    eng2, _ = _eng()
    cid2 = eng2._open_case("A-02", "wall", None, "a case never even reponged yet")
    eng2._end_session()
    ok("AC-4 a still-parked case at session end is paged (drain never drops it)",
       any(f"[{cid2}]" in t for t in _console_lines(eng2)),
       f"lines={_console_lines(eng2)}")
    ok("AC-4 ...and the page carries the 'goes to the archive unresolved' notice",
       any("archive unresolved" in t for t in _console_lines(eng2)))


# ══════════════════════════════════════════════════════════════════════════
# AC-5 test:<worker_death_full_handover_outage_aware>
# ══════════════════════════════════════════════════════════════════════════

def test_worker_death_full_handover_outage_aware():
    # (a) the recovery assignment is a FULL handover — context, gate-stage note,
    # timeline (best-effort), and an explicit re-verify instruction — never a fresh
    # dispatch's plain assignment string.
    eng, repo = _eng()
    eng.st.gate["A-01"] = {"stage": "trunk", "pr": None}
    eng.st.branches["A-01"] = "feat/A-01"
    d = tempfile.mkdtemp(prefix="tron-timeline-")
    with open(os.path.join(d, jobs.TIMELINE), "w") as fh:
        fh.write(json.dumps({"text": "ran the acceptance suite locally, all green"}) + "\n")
    orig_find = jobs.find
    jobs.find = lambda wid, idx=None: {"dir": d} if wid == "DEAD-ENG" else orig_find(wid, idx)
    try:
        assignment = eng._recovery_assignment("A-01", dead_wid="DEAD-ENG")
    finally:
        jobs.find = orig_find
    ok("AC-5 the handover names this as a REPLACEMENT, not a fresh assignment",
       "REPLACING" in assignment, f"assignment={assignment!r}")
    ok("AC-5 ...carries an explicit RE-VERIFY-current-state instruction",
       "RE-VERIFY" in assignment, f"assignment={assignment!r}")
    ok("AC-5 ...names the block's current gate stage (context)",
       "trunk" in assignment, f"assignment={assignment!r}")
    ok("AC-5 ...names the branch a prior worker registered",
       "feat/A-01" in assignment, f"assignment={assignment!r}")
    ok("AC-5 ...and a fresh assignment (_engineer_assignment) is NOT this rich",
       "REPLACING" not in eng._engineer_assignment("A-01"))
    fresh_assignment = eng._recovery_assignment("A-02")   # no dead_wid known at all
    ok("AC-5 no known dead worker -> degrades gracefully (still a real handover, "
       "never a crash)",
       "REPLACING" in fresh_assignment, f"assignment={fresh_assignment!r}")

    # (b) _redispatch actually USES the recovery assignment (not the plain one).
    eng2, _ = _eng()
    row = eng2.st.row("A-01")
    row["status"] = "to-do"
    eng2._redispatch("A-01", dead_wid="DEAD-ENG")
    w = next(x for x in eng2.st.workers if x.get("block") == "A-01")
    ok("AC-5 _redispatch's pending_assign carries the RICH recovery assignment",
       "REPLACING" in (w.get("pending_assign") or {}).get("assignment", ""),
       f"pending_assign={w.get('pending_assign')}")

    # (c) outage interaction (D-F): a BUILD worker absorbed into the fleet-refusal
    # hold (its block already gated) is TRACKED, never dropped — and redriven,
    # exactly once, the instant the hold releases.
    eng3, _ = _eng()
    eng3.dry = False
    eng3.st.gate["A-01"] = {"stage": "local", "pr": None}
    dead = {"id": "ENG-A-01", "role": "engineer", "block": "A-01", "session_id": "real"}
    eng3.st.workers.append(dead)
    eng3._release_worker = lambda w, notify=True, reason=None: (
        eng3.st.workers.remove(w) if w in eng3.st.workers else None)
    eng3._drive_fleet_refusal_hold(dead)
    ok("AC-5 the dead worker's block is tracked for redrive across the hold "
       "(D-F: never dropped to an outage)",
       eng3.st.data.get("hold_pending_redispatch", {}).get("A-01") == "ENG-A-01",
       f"pending={eng3.st.data.get('hold_pending_redispatch')}")
    resolved = []
    eng3._resolve_workerless_gate = lambda block, g: resolved.append(block)
    eng3._release_hold_pending()
    ok("AC-5 on hold-release, the gated block hands off to the SAME workerless-gate "
       "resolution any other dead worker's gate already gets (never a blind "
       "fresh BUILD redispatch onto work past the build stage)",
       resolved == ["A-01"], f"resolved={resolved}")
    ok("AC-5 the pending-redispatch map is consumed, never replayed twice",
       not eng3.st.data.get("hold_pending_redispatch"))

    # An UNGATED absorbed block redrives via the ordinary recovery _redispatch,
    # carrying the dead worker's id (full handover), not the block/branch's dead
    # worker's literal identity as the re-target KEY (D-F: "dedupe on block/branch
    # state, not the dead worker's id" — the id rides only as CONTEXT).
    eng4, _ = _eng()
    eng4.dry = False
    dead2 = {"id": "ENG-A-02", "role": "engineer", "block": "A-02", "session_id": "real"}
    eng4.st.workers.append(dead2)
    eng4._release_worker = lambda w, notify=True, reason=None: (
        eng4.st.workers.remove(w) if w in eng4.st.workers else None)
    eng4._drive_fleet_refusal_hold(dead2)
    redispatched = []
    eng4._redispatch = lambda block, bypass_gate=False, dead_wid=None: (
        redispatched.append((block, dead_wid)))
    eng4._release_hold_pending()
    ok("AC-5 an ungated absorbed block redrives via _redispatch, carrying the dead "
       "worker's id as HANDOVER CONTEXT (re-targeted by block state, not identity)",
       redispatched == [("A-02", "ENG-A-02")], f"redispatched={redispatched}")


# ══════════════════════════════════════════════════════════════════════════
# AC-6 test:<injected_outage_hold_persists_bounded_notified> — INJECTION-AUTHORITATIVE
# ══════════════════════════════════════════════════════════════════════════

def test_injected_outage_hold_persists_bounded_notified():
    """ADR-0003 D-I: D-H's acceptance is THIS injection unit test — a simulated
    RunnerRefusal, never a real provider outage. Mirrors block_01_20_test.py's own
    t3b fixture shape (the pre-existing, working half of this mechanism) and
    extends it to the ONE confirmed gap: the cardinality-1 architect."""
    eng, _ = _eng(blocks=[("A-01", "🔄", "none"), ("A-02", "🔄", "none")])
    eng.dry = False
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]

    world = {"dead": {}, "canary_wid": None, "canary_healthy": False}

    def _index():
        out = {}
        for wid in world["dead"]:
            out[wid] = {"state": "error", "dir": f"/fake/{wid}", "pid": None, "turns": 0}
        if world["canary_wid"] and world["canary_healthy"]:
            out[world["canary_wid"]] = {"state": "idle", "dir": "/fake/canary",
                                        "pid": 999, "turns": 1}
        return out

    def _find(wid, idx=None):
        return (idx if idx is not None else _index()).get(wid)

    def _alive(wid, idx=None):
        rec = (idx if idx is not None else _index()).get(wid)
        return bool(rec) and rec.get("state") != "error"

    def _kind(wdir):
        for wid in world["dead"]:
            if wdir == f"/fake/{wid}":
                return "RunnerRefusal"
        return ""

    orig = (jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind)
    jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind = _index, _find, _alive, _kind
    spawned_arch = []
    eng._spawn_architect = lambda: (spawned_arch.append(True),
                                    eng.st.workers.append(
                                        {"id": "ARCH-PERSIST", "role": "architect",
                                         "session_id": "dry", "status": "idle",
                                         "current_job": None, "block": None}))
    try:
        # Tick 1: ENG-A-01 dies of refusal alone — hold not yet active.
        eng.st.workers[:] = [{"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                             "session_id": "real-1", "status": "working"}]
        world["dead"] = {"ENG-A-01": True}
        eng._tq = []
        eng._sweep()
        ok("AC-6 setup: a lone refusal death does not yet engage the hold",
           not eng.st.data.get("refusal_hold", {}).get("active"))
        eng.st.workers[:] = []   # simulate the ordinary per-worker recover having released it

        # Tick 2: the ARCHITECT dies of refusal too, inside the window -> the SECOND
        # absorbed death, engaging the hold. This is the tron-40 root cause: the
        # architect must be covered by the SAME hold, never respawned unconditionally.
        eng.st.workers.append({"id": "ARCH-PERSIST", "role": "architect",
                               "session_id": "real-arch", "status": "idle",
                               "current_job": {"kind": "log", "detail": "x"}, "block": None})
        world["dead"] = {"ARCH-PERSIST": True}
        eng._tq = []
        eng._sweep()
        hold = eng.st.data.get("refusal_hold", {})
        ok("AC-6 the architect's refusal death engages the SAME fleet-wide hold",
           hold.get("active") is True, f"hold={hold}")
        ok("AC-6 the architect was elected as the SINGLE canary (D-H: 'including "
           "the architect')", hold.get("canary") == eng.ARCHITECT_CANARY_REF,
           f"hold={hold}")
        # The canary's FIRST-ever probe fires immediately, unpaced — exactly like
        # an engineer/reviewer canary's first probe (block_01_20_test.py's own
        # "present-dead canary fires its first-ever probe immediately" parity) —
        # this is the ONE bounded probe D-H allows, never a second unconditional
        # spawn on top of it (proven below).
        ok("AC-6 the architect's first canary probe fires bounded (exactly once), "
           "never TWICE for the same election — never the tron-40 unconditional "
           "every-tick respawn",
           spawned_arch == [True], f"spawned={spawned_arch}")
        ok("AC-6 its in-flight job survived the hold (D-F: never dropped)",
           any(j.get("kind") == "log" for j in eng.st.architect_queue),
           f"queue={eng.st.architect_queue}")

        # Tick 3: a FURTHER sweep, still well inside the canary's paced re-probe
        # window and with the probe still not healthy — must NOT spawn a second
        # architect (the exact tron-40 defect: unconditional respawn every tick).
        # The hold PERSISTS across the probe's own dispatch too (never releases
        # merely because a probe was spawned; only a healthy TURN lifts it).
        clock["t"] += 1
        eng._sweep()
        ok("AC-6 a further sweep inside the paced window spawns NO second architect "
           "(bounded to the ONE in-flight canary, fleet-wide — the tron-40 bug, "
           "closed)", spawned_arch == [True], f"spawned={spawned_arch}")
        ok("AC-6 the hold PERSISTS across the probe's own dispatch (not released on "
           "dispatch — the exact tron-40 self-release-in-30s defect)",
           eng.st.data.get("refusal_hold", {}).get("active") is True)

        # STALL-CAP FREEZE (MJ-A): while held, a spawn-dependent gate neither
        # accrues stall_attempts nor caps, even on a repeat report reading 'false'.
        eng.st.gate["A-01"] = {"stage": "local", "pr": None}
        cap = int(eng.knobs.get("gate_step_cap", 2))
        for _ in range(cap + 3):
            eng._h_worker_done({"block": "A-01"})
        ok("AC-6 a spawn-dependent gate's stall counter is FROZEN while held — "
           "never bumped past/through the cap, however many repeat reports arrive",
           eng.st.gate.get("A-01", {}).get("stall_attempts", 0) == 0
           and "A-01" in eng.st.gate and "A-01" not in eng.st.blocked,
           f"gate={eng.st.gate.get('A-01')} blocked={eng.st.blocked}")

        # OBSERVATION-ONLY ADVANCE STILL PROCEEDS while the SAME hold is active — a
        # block already ✅ on trunk still closes by ancestry, no spawn needed
        # (_drive_gate's OWN row.status=='done' branch, unconditional — never
        # gated on _dispatch_held() at all). Proven by driving the REAL
        # _drive_gates() (which iterates every gate every tick, held or not) and
        # confirming it reaches _drive_close for this block — never frozen behind
        # the hold that IS freezing A-01's spawn-dependent stall counter above, in
        # the very same sweep.
        drove_close = []
        eng._drive_close = lambda block, g, wid: drove_close.append(block)
        eng.st.row("A-02")["status"] = "done"
        eng.st.gate["A-02"] = {"stage": "record", "pr": None}
        eng._drive_gates()
        ok("AC-6 an observation-only advance (already-done trunk ancestry) still "
           "proceeds while held — the hold suppresses only SPAWN-dependent gates",
           drove_close == ["A-02"], f"drove_close={drove_close}")

        # OPERATOR NOTIFIED EXACTLY ONCE for the hold's own engage condition.
        engage_pages = sum(1 for t in _console_lines(eng) if "fleet dispatch held" in t)
        ok("AC-6 the operator is notified EXACTLY ONCE for the hold engaging "
           "(never once per absorbed death)", engage_pages == 1, f"n={engage_pages}")

        # SELF-RELEASE on the first healthy canary turn.
        world["canary_wid"] = "ARCH-PERSIST"
        world["canary_healthy"] = True
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._sweep_fleet_refusal_canary(_index())
        hold_after = eng.st.data.get("refusal_hold", {})
        ok("AC-6 the hold SELF-RELEASES the instant the canary's first turn is "
           "healthy — no other gate/blocked mutation required",
           hold_after.get("active") is False, f"hold={hold_after}")

        # The stall-cap counter resumes counting on release (unfrozen).
        for _ in range(cap + 3):
            eng._h_worker_done({"block": "A-01"})
        ok("AC-6 stall-cap accrual RESUMES the instant the hold releases",
           "A-01" in eng.st.blocked or eng.st.gate.get("A-01", {}).get("stall_attempts", 0) > 0,
           f"gate={eng.st.gate.get('A-01')} blocked={eng.st.blocked}")
    finally:
        jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind = orig


# ══════════════════════════════════════════════════════════════════════════
# AC-7 test:<escalation_debounce_and_page_receipt_contract>
# ══════════════════════════════════════════════════════════════════════════

def test_escalation_debounce_and_page_receipt_contract():
    # (a) debounce: a case settled THIS tick (via the operator's own reply, drained
    # by _drain_triggers) must never ALSO draw a stale re-ping/safe-park page from
    # _drive_cases this same tick — _drive_cases now runs AFTER _drain_triggers.
    eng, _ = _eng()
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    cid = eng._open_case("A-01", "wall", "ENG-A-01", "a real blocker")
    case = eng.st.pending_cases[cid]
    # Anchor the case's ping clock so THIS tick's _drive_cases would otherwise fire
    # a re-ping (simulating the ~20s race: the case is due for a re-ping the exact
    # tick its settle also arrives).
    case["ping_anchor_s"] = 0.0
    eng._now_s = lambda: 10 ** 9
    util.append_jsonl(eng.ctx.operator_inbox,
                      {"text": f"resume {cid}", "sender": {"kind": "operator"}})
    eng.tick()
    ok("AC-7 the same-tick settle actually closed the case",
       cid not in eng.st.pending_cases, f"cases={eng.st.pending_cases}")
    ok("AC-7 no stale re-ping/safe-park fired for a case resolving THIS tick "
       "(the ~20s stale-escalation race)",
       not any(e.get("type") in ("case_reping", "case_safe_parked") for e in _events(eng)),
       f"events={_events(eng)}")

    # (b) the minimal receipt contract: a 'failed-permanent' receipt never silently
    # drops — it escalates (forces the case's next re-ping immediate) and leaves a
    # forensic record, all WITHOUT the engine itself ever sending/retrying.
    eng2, _ = _eng()
    cid2 = eng2._open_case("A-01", "wall", None, "a real blocker")
    eng2.st.data["operator_page_receipts"] = {cid2: "failed-permanent"}
    eng2._page_operator(cid2, "A-01", "a real blocker")
    ok("AC-7 a permanent-fail receipt is recorded forensically, never silently "
       "dropped", any(e.get("fclass") == "operator-page-failed" for e in _events(eng2)),
       f"events={_events(eng2)}")
    ok("AC-7 ...and forces this case's NEXT re-ping to fire immediately (escalates "
       "further, via the engine's OWN existing ladder — never a new retry loop)",
       eng2.st.pending_cases[cid2].get("ping_anchor_s") == 0)
    ok("AC-7 the receipt slot is consumed (never re-read/re-acted on twice)",
       cid2 not in (eng2.st.data.get("operator_page_receipts") or {}))
    # Behavioral: the engine's own receipt reader only ever POPS an existing
    # receipt (a transport's own write) — it never manufactures/confirms a
    # 'delivered' receipt for a case that never had one, and never touches a
    # DIFFERENT case's still-pending receipt.
    eng2.st.data["operator_page_receipts"] = {"CASE-999": "delivered"}
    eng2._consume_page_receipt("CASE-NEVER-PAGED")
    ok("AC-7 consuming a receipt for a case with NO stub entry writes nothing "
       "(never fabricates/confirms a delivery it cannot make)",
       eng2.st.data["operator_page_receipts"] == {"CASE-999": "delivered"},
       f"receipts={eng2.st.data['operator_page_receipts']}")


# ══════════════════════════════════════════════════════════════════════════
# AC-8 test:<every_case_terminates_sweep> (automated invariant sweep)
# ══════════════════════════════════════════════════════════════════════════

def test_every_case_terminates_sweep():
    """A short synthetic multi-path scenario (wall settle, architect relay, abandon,
    safe-park) — then an automated sweep of events.jsonl proves every case that was
    ever raised/paged is accounted for: either it settled (a `settle` record names
    its cid) or it is STILL visibly parked (never silently vanished, never merely
    `unclassified`)."""
    eng, _ = _eng(blocks=[("A-01", "📋", "none"), ("A-02", "📋", "none"),
                          ("A-03", "📋", "none")])
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    eng.st.workers.append({"id": "ENG-A-02", "role": "engineer", "block": "A-02",
                           "session_id": "dry", "status": "working"})
    eng.st.workers.append({"id": "ENG-A-03", "role": "engineer", "block": "A-03",
                           "session_id": "dry", "status": "working"})
    # Path 1: raise + operator settle (resume).
    eng._h_escalate({"block": "A-01", "worker_id": "ENG-A-01", "detail": "wall one"})
    c1 = next(cid for cid, c in eng.st.pending_cases.items() if c.get("block") == "A-01")
    eng._h_apply_decision({"case": c1, "decision": "resume"})
    # Path 2: raise + abandon.
    eng._h_escalate({"block": "A-02", "worker_id": "ENG-A-02", "detail": "wall two"})
    c2 = next(cid for cid, c in eng.st.pending_cases.items() if c.get("block") == "A-02")
    eng._h_apply_decision({"case": c2, "decision": "abandon"})
    # Path 3: raise, left genuinely still parked (never settled) — must remain
    # VISIBLE, never silently dropped.
    eng._h_escalate({"block": "A-03", "worker_id": "ENG-A-03", "detail": "wall three"})
    c3 = next(cid for cid, c in eng.st.pending_cases.items() if c.get("block") == "A-03")

    settled_cids = {e.get("cid") for e in _events(eng) if e.get("type") == "settle"}
    raised_cids = {e.get("cid") for e in _events(eng)
                   if e.get("type") == "escalate" and e.get("cid")}
    still_parked = set(eng.st.pending_cases)
    ok("AC-8 setup: three distinct cases were raised", len(raised_cids) == 3,
       f"raised={raised_cids}")
    unaccounted = raised_cids - settled_cids - still_parked
    ok("AC-8 every raised case terminates in resolved|operator-delivered — none "
       "vanish unaccounted (settled, or still visibly parked)",
       unaccounted == set(), f"unaccounted={unaccounted}")
    ok("AC-8 the still-open case is genuinely visible in pending_cases (never "
       "silently dropped)", c3 in still_parked)
    ok("AC-8 no wall/escalation anywhere in this run logged unclassified",
       not any(e.get("kind") == "unclassified" for e in _events(eng)))


# ══════════════════════════════════════════════════════════════════════════
# AC-8b test:<aide_runtime_real_llm_bounded_failsafe>
# ══════════════════════════════════════════════════════════════════════════

def test_aide_runtime_real_llm_bounded_failsafe():
    # (a) ND-02-10: a real judge.call('aide') fires (mocked LLM) carrying
    # Project-Docs context; the delivered page is the AIDE brief, not the raw text.
    eng, repo = _eng()
    with open(os.path.join(repo, "meta", "context.md"), "w") as fh:
        fh.write("PROJECT CONTEXT MARKER — this project builds widgets.\n")
    calls = []
    orig_call_llm = judge._call_llm

    def fake_resolve(tool, payload, ctx_, correction=None, context=None, model=None):
        calls.append({"tool": tool, "payload": payload, "context": context})
        return '{"advice": "AIDE BRIEF: this looks like a real, novel blocker"}'

    judge._call_llm = fake_resolve
    try:
        cid = eng._open_case("A-01", "wall", None, "raw detail nobody briefed yet")
        eng._page_operator(cid, "A-01", "raw detail nobody briefed yet")
    finally:
        judge._call_llm = orig_call_llm
    ok("AC-8b a REAL judge.call('aide') fires at ND-02-10 (mocked LLM, never a "
       "deterministic stand-in)", len(calls) == 1 and calls[0]["tool"] == "aide",
       f"calls={calls}")
    ok("AC-8b ...mode='resolve' (the same brief+offer-choices shape bootup RESOLVE "
       "uses)", calls[0]["payload"].get("mode") == "resolve", f"payload={calls[0]}")
    ok("AC-8b ...carrying Project-Docs context (context.md content present)",
       "PROJECT CONTEXT MARKER" in (calls[0]["context"] or ""),
       f"context={calls[0]['context']!r}")
    ok("AC-8b the delivered page is AIDE's OWN brief, not the raw detail",
       any("AIDE BRIEF" in t for t in _console_lines(eng)), f"lines={_console_lines(eng)}")

    # (b) the <=1 AIDE call per TICK cap is SHARED across cases — a second case
    # paging the SAME tick gets the raw detail, never a second real LLM call.
    eng2, _ = _eng()
    calls2 = []
    judge._call_llm = lambda *a, **k: (calls2.append(1),
                                       '{"advice": "briefed"}')[1]
    try:
        cid_a = eng2._open_case("A-01", "wall", None, "case A raw detail")
        cid_b = eng2._open_case("A-02", "wall", None, "case B raw detail")
        eng2._page_operator(cid_a, "A-01", "case A raw detail")
        eng2._page_operator(cid_b, "A-02", "case B raw detail")
    finally:
        judge._call_llm = orig_call_llm
    ok("AC-8b exactly ONE real AIDE call fires across the whole tick, never one "
       "per parked case (D-J reconciliation (b))", len(calls2) == 1, f"n={len(calls2)}")
    ok("AC-8b the SECOND case (budget already spent) delivers its RAW detail — "
       "never blocked/held waiting on a brief that can't compose",
       any("case B raw detail" in t for t in _console_lines(eng2)),
       f"lines={_console_lines(eng2)}")

    # (c) ND-09: AIDE answers an open `ask` from Project Docs — a real LLM call,
    # relayed to the asker; never dead-ends to a heuristic.
    eng3, repo3 = _eng()
    eng3.dry = False   # the relay send is dry-gated; this sub-test drives it for real
    eng3.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                            "session_id": "dry", "status": "working"})
    calls3 = []

    def fake_ask(tool, payload, ctx_, correction=None, context=None, model=None):
        calls3.append({"tool": tool, "payload": payload})
        return '{"advice": "the answer is in pipeline.md", "answered": true}'

    judge._call_llm = fake_ask
    sent = []
    eng3._to_worker = lambda wid, text, kind: sent.append((wid, text, kind))
    try:
        eng3._aide_answer_or_escalate({"detail": "what's the deploy target?",
                                       "worker_id": "ENG-A-01", "block": "A-01"})
    finally:
        judge._call_llm = orig_call_llm
    ok("AC-8b ND-09: a real judge.call('aide') fires, mode='ask'",
       len(calls3) == 1 and calls3[0]["payload"].get("mode") == "ask", f"calls={calls3}")
    ok("AC-8b ...the question rides as INPUT.question",
       calls3[0]["payload"].get("question") == "what's the deploy target?")
    ok("AC-8b ...AIDE's real answer relays straight back to the asker",
       any("the answer is in pipeline.md" in t for _, t, _ in sent), f"sent={sent}")

    # (d) fail-safe: AIDE unavailable (no monkeypatch — TRON_DRY's own aide-down
    # contract) -> `ask` degrades to the architect, never a heuristic substitute.
    eng4, _ = _eng()
    _arch(eng4)
    triaged = []
    orig_triage = eng4._triage_to_architect
    eng4._triage_to_architect = lambda detail, sender=None, block=None, case=None: (
        triaged.append(detail), orig_triage(detail, sender=sender, block=block, case=case))[-1]
    eng4._aide_answer_or_escalate({"detail": "an unanswerable-by-docs question",
                                   "worker_id": "ENG-A-01", "block": "A-01"})
    ok("AC-8b fail-safe: AIDE down -> the ask degrades to the architect (never a "
       "heuristic answer, never dead-ends)",
       triaged == ["an unanswerable-by-docs question"], f"triaged={triaged}")

    # (e) fail-safe: an escalation brief that can't compose (AIDE down, no mock)
    # still delivers the RAW payload immediately — never held.
    eng5, _ = _eng()
    cid5 = eng5._open_case("A-01", "wall", None, "raw payload, AIDE is down")
    eng5._page_operator(cid5, "A-01", "raw payload, AIDE is down")
    ok("AC-8b fail-safe: ND-02-10 with AIDE down delivers the RAW/un-briefed "
       "payload immediately (never held for a brief that can't compose)",
       any("raw payload, AIDE is down" in t for t in _console_lines(eng5)),
       f"lines={_console_lines(eng5)}")


def main():
    for fn in sorted(k for k in globals() if k.startswith("test_")):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
