"""block_01_31_test — escalation unification + content integrity (ADR-0002 D3+D5).

Per-AC coverage (block doc `blocks/01-31-escalation-content-integrity.md`):

  AC-1 test:contentless_wall_rejected — a contentless wall is NAK'd (x2) then converted
       to an engine-observed wall; the literal "wall" placeholder can never reach a case.
  AC-2 test:all_walls_architect_first — every wall kind (9 WALL_KINDS incl. close-
       violation, each gate-giveup code, repeated-stall) reaches the architect before any
       operator page; operator-direct only on raise/dead/fleet-hold/TRIAGE-self.
  AC-3 test:abandon_releases_no_livelock — abandon releases the worker; no "invariant
       repair" re-raise ever fires; `_sweep_wall_invariant` is deleted.
  AC-4 test:observed_done_autosettles_wall — a mis-tagged wall on a block that
       subsequently observes done auto-settles without architect/operator action.
  AC-5 test:silent_drop_high_fixed — question_tron reaches the architect with full
       content; sentry text arrives untruncated; a failed jobs.send is retried +
       forensically logged, never silently lost.
  AC-5b test:silent_drop_med_forensics — handler exceptions emit a forensic event;
       triage text-dedup drops emit one; the "(peer question)" placeholder is refused,
       real content required.
  AC-6 cmd:<lint run red on fixture, green on tree> — a light in-suite echo of the
       standalone RED/GREEN proof (see PR body / final report for the captured runs).

Run: python3 engine/block_01_31_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import jobs                                            # noqa: E402
import lint                                             # noqa: E402
from fsm import (                                       # noqa: E402
    Engine, WALL_KINDS, GATE_GIVEUP_SPLIT_CODES, WALL_NAK_MAX, MissingContent,
    require_content,
)
from sentry_test import build, started                  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── fixture builders (block_01_19/24/29_test convention) ──
def _eng(block="A-01", status="🔄"):
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _arch_idle(eng):
    w = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
         "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
    eng.st.workers.append(w)
    return w


def _capture(eng):
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
               sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


def _capture_to_worker(eng):
    sent = []
    eng._to_worker = lambda wid, text, kind: sent.append((wid, text, kind))
    return sent


PING_WINDOW_S = 6 * 60 + 1


# ══════════════════════════════════════════════════════════════════════════════════
# AC-1: contentless wall rejected — NAK x2, then engine-observed conversion
# ══════════════════════════════════════════════════════════════════════════════════

def test_contentless_wall_rejected():
    eng = _eng()
    wid = "ENG-A-01"
    sent = _capture(eng)
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        for n in range(1, WALL_NAK_MAX + 1):
            eng._ingest("worker.wall", {"block": "A-01", "detail": ""},
                       {"kind": "worker", "id": wid})
            ok(f"AC-1 NAK #{n}: no case opened yet",
               not eng.st.pending_cases, f"cases={eng.st.pending_cases}")
        ok("AC-1 at least one bounce line sent across the NAK budget, no case opened",
           len(tw) >= 1 and not eng.st.pending_cases, f"tw={tw}")
        # Past the budget: the engine gives up asking and opens a wall ABOUT the
        # worker itself — an engine-observed fact, never the old literal placeholder.
        eng._ingest("worker.wall", {"block": "A-01", "detail": ""},
                   {"kind": "worker", "id": wid})
    finally:
        eng.dry = True
    eng._drain_triggers()
    cases = list(eng.st.pending_cases.values())
    ok("AC-1 past the NAK budget, a case DOES open", len(cases) == 1, f"cases={cases}")
    detail = (cases[0].get("detail") or "") if cases else ""
    ok("AC-1 the literal 'wall' placeholder never reaches the case",
       detail != "wall", f"detail={detail!r}")
    ok("AC-1 the case names the engine-OBSERVED fact (worker couldn't articulate it)",
       "could not articulate" in detail and wid in detail, f"detail={detail!r}")


def test_contentless_wall_from_unrostered_sender_terminates():
    """An UNROSTERED sender (no worker record to persist a NAK count on) must never
    enter an unterminating NAK loop — the engine converts immediately to the
    engine-observed fact instead of bouncing forever."""
    eng = _eng()
    got = eng._admit("worker.wall", {"block": "A-01", "detail": ""},
                    {"kind": "worker", "id": "ADHOC-99"})
    ok("AC-1 an unrostered sender's contentless wall converts immediately "
       "(no unterminating NAK loop)",
       got is not None and "could not articulate" in (got.get("detail") or ""),
       f"got={got}")


def test_require_content_raises_on_missing_field():
    # The ONE ingest choke-point primitive itself: raises loud, never defaults.
    try:
        require_content({}, "detail")
        raised = False
    except MissingContent:
        raised = True
    ok("AC-1 require_content raises MissingContent on an absent field", raised)
    try:
        require_content({"detail": "   "}, "detail")
        raised = False
    except MissingContent:
        raised = True
    ok("AC-1 require_content raises on a whitespace-only field (never silently accepted)",
       raised)
    ok("AC-1 require_content returns the value when genuinely present",
       require_content({"detail": "real reason"}, "detail") == "real reason")


# ══════════════════════════════════════════════════════════════════════════════════
# AC-2: every wall kind reaches the architect first; operator-direct only on the four
# named structural exemptions.
# ══════════════════════════════════════════════════════════════════════════════════

def test_all_walls_architect_first():
    # Every one of the 9 WALL_KINDS (plain 'wall' + the 8 gate-giveup split codes).
    for kind in WALL_KINDS:
        eng = _eng()
        wid = "ENG-A-01"
        arch = _arch_idle(eng)
        sent = _capture(eng)
        m = {"block": "A-01", "worker_id": wid, "detail": f"blocked ({kind})"}
        if kind != "wall":
            m["code"] = kind
        eng._tq = []
        eng._h_escalate(m)
        case = next((c for c in eng.st.pending_cases.values()
                    if c.get("block") == "A-01"), None)
        ok(f"AC-2 wall kind '{kind}' opens a case of that exact kind",
           case is not None and case.get("kind") == kind, f"case={case}")
        ok(f"AC-2 wall kind '{kind}' never pages the operator directly",
           not any(tid in ("escalate.wall", "tg.escalate") for tid, _ in sent),
           f"sent={sent}")
        ok(f"AC-2 wall kind '{kind}' dispatches the architect (triage job, case-carrying)",
           (arch.get("current_job") or {}).get("kind") == "triage"
           and (arch.get("current_job") or {}).get("case") is not None, f"arch={arch}")


def test_close_time_violation_routes_architect_first():
    import trunk
    eng = _eng()
    arch = _arch_idle(eng)
    sent = _capture(eng)
    g = eng.st.gate.setdefault("A-01", {"stage": "close"})
    orig = trunk.land_docs
    trunk.land_docs = lambda *a, **k: ("violation", "src/sneak.txt")
    try:
        eng._confirm_close("A-01", g)
        eng._drain_triggers()
    finally:
        trunk.land_docs = orig
    ok("AC-2 close-time violation never pages the operator directly",
       not any(tid in ("escalate.wall", "tg.escalate") for tid, _ in sent), f"sent={sent}")
    ok("AC-2 close-time violation dispatches the architect",
       (arch.get("current_job") or {}).get("kind") == "triage", f"arch={arch}")


def test_repeated_stall_routes_architect_first():
    eng = _eng()
    wid = "ENG-A-01"
    arch = _arch_idle(eng)
    sent = _capture(eng)
    eng.st.counters.setdefault("stalls", {})["A-01"] = 3   # already over the cap (>2)
    eng._tq = []
    eng._h_recover({"worker_id": wid})
    eng._drain_triggers()
    case = next((c for c in eng.st.pending_cases.values()
                if c.get("detail") == "repeated stall"), None)
    ok("AC-2 repeated-stall opens a wall case",
       case is not None and case.get("kind") == "wall", f"case={case}")
    ok("AC-2 repeated-stall never pages the operator directly",
       not any(tid in ("escalate.wall", "tg.escalate") for tid, _ in sent), f"sent={sent}")
    ok("AC-2 repeated-stall dispatches the architect",
       (arch.get("current_job") or {}).get("kind") == "triage", f"arch={arch}")


def test_operator_direct_exemption_architect_raise():
    eng = _eng()
    arch = _arch_idle(eng)
    arch["current_job"] = {"kind": "triage", "detail": "x", "sender": "ENG-A-01",
                           "block": "A-01"}
    sent = _capture(eng)
    eng._tq = []
    eng._side("escalate_to_operator", {"detail": "operator's call"}, None)
    eng._drain_triggers()
    ok("AC-2 exemption: an explicit architect RAISE pages the operator directly "
       "(never re-triaged back to the architect)",
       any(tid in ("escalate.wall", "tg.escalate") for tid, _ in sent)
       and (arch.get("current_job") or {}).get("kind") != "triage", f"sent={sent} arch={arch}")


def test_operator_direct_exemption_architect_dead():
    eng = _eng()
    arch = _arch_idle(eng)
    arch["status"] = "busy"
    arch["current_job"] = {"kind": "log"}
    sent = _capture(eng)
    eng._open_architect_stall_case(arch, "idle 999s with no completion report")
    ok("AC-2 exemption: architect-idle-cap (effectively dead/stalled) pages the "
       "operator directly", any(tid == "escalate.wall" for tid, _ in sent), f"sent={sent}")


def test_operator_direct_exemption_fleet_hold():
    eng = _eng()
    sent = _capture(eng)
    now = eng._now_s()
    eng.st.data["refusal_hold"] = {"deaths": [now - 1, now - 0.5], "active": False}
    eng._fleet_hold_note(next(iter(eng.st.workers)))
    ok("AC-2 exemption: fleet-hold engagement pages the operator directly",
       any(tid == "escalate.unclassified" for tid, _ in sent), f"sent={sent}")


def test_operator_direct_exemption_triage_self_wall():
    eng = _eng()
    arch = _arch_idle(eng)
    sent = _capture(eng)
    eng._tq = []
    eng._h_escalate({"block": None, "worker_id": arch["id"], "detail": "architect stuck"})
    ok("AC-2 exemption: a TRIAGE (architect)-role self-wall pages the operator directly "
       "(cardinality-1 — routing it architect-first would self-loop)",
       any(tid == "escalate.wall" for tid, _ in sent), f"sent={sent}")


# ══════════════════════════════════════════════════════════════════════════════════
# AC-3: abandon releases, no invariant-repair livelock, sweep retired
# ══════════════════════════════════════════════════════════════════════════════════

def test_sweep_wall_invariant_is_deleted():
    ok("AC-3 _sweep_wall_invariant no longer exists on Engine",
       not any(n == "_sweep_wall_invariant" for n in dir(Engine)))


def test_abandon_releases_no_livelock():
    eng = _eng()
    wid = "ENG-A-01"
    eng._tq = []
    eng._h_escalate({"block": "A-01", "worker_id": wid, "detail": "genuinely stuck"})
    cid = next(iter(eng.st.pending_cases))
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("setup: the worker is walled", w.get("status") == "walled")
    eng._h_apply_decision({"case": cid, "decision": "abandon", "block": "A-01"})
    ok("AC-3 abandon releases the worker (removed from the roster)",
       not any(x.get("id") == wid for x in eng.st.workers), f"workers={eng.st.workers}")
    ok("AC-3 abandon closes the case", cid not in eng.st.pending_cases)
    ok("AC-3 abandon fires a loud 'abandon' event", any(
        r.get("type") == "abandon" for r in _events(eng)))
    ok("AC-3 abandon records a manifest flag for the block",
       any(f.get("block") == "A-01" for f in eng.st.data.get("abandon_flags", [])),
       f"flags={eng.st.data.get('abandon_flags')}")
    # Run the clock hard, well past any historical invariant-repair window — no worker
    # is on the roster to re-raise against, and nothing should ever try.
    eng.dry = False
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    try:
        for _ in range(5):
            clock["t"] += PING_WINDOW_S
            eng._sweep()
    finally:
        eng.dry = True
    ok("AC-3 no 'invariant repair' re-raise ever fires after abandon",
       not eng.st.pending_cases, f"cases={eng.st.pending_cases}")


def test_abandon_flag_rides_the_next_architect_touchpoint():
    # No architect online YET at abandon time — the wall settles operator-direct
    # (no architect to triage to), so the abandon itself creates no architect job at
    # all (a drop verb must not generate work). Only AFTER an architect comes online
    # and gets its own, independently-arriving job does the flag ride that touchpoint.
    eng = _eng()
    wid = "ENG-A-01"
    eng._tq = []
    eng._h_escalate({"block": "A-01", "worker_id": wid, "detail": "genuinely stuck"})
    cid = next(iter(eng.st.pending_cases))
    eng.dry = False
    tw = _capture_to_worker(eng)
    try:
        eng._h_apply_decision({"case": cid, "decision": "abandon", "block": "A-01"})
        arch = _arch_idle(eng)
        ok("setup: no automatic new architect case from a bare abandon",
           arch.get("current_job") is None, f"arch={arch}")
        # The architect's next dispatched touchpoint (any job) carries the flag.
        eng.st.architect_queue.append({"kind": "forward", "block": "A-02"})
        eng._pump_architect()
    finally:
        eng.dry = True
    ok("AC-3 the abandon flag rides the architect's next dispatched touchpoint",
       any(k == "abandon.flag" and "A-01" in t for _, t, k in tw), f"tw={tw}")
    ok("AC-3 the flag clears once delivered (never re-delivered)",
       not eng.st.data.get("abandon_flags"), f"flags={eng.st.data.get('abandon_flags')}")


def test_abandon_flag_escalates_after_bounded_window_if_untouched():
    # Drives the REAL production entry point (`_sweep()`, the per-tick liveness sweep) —
    # never `_sweep_abandon_flags()` directly — so this test would have caught the wiring
    # gap where the bounded-window escalation existed as a method but was never actually
    # called from `_sweep()`.
    eng = _eng()
    wid = "ENG-A-01"
    eng._tq = []
    eng._h_escalate({"block": "A-01", "worker_id": wid, "detail": "genuinely stuck"})
    cid = next(iter(eng.st.pending_cases))
    eng.dry = False
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    try:
        eng._h_apply_decision({"case": cid, "decision": "abandon", "block": "A-01"})
        eng._sweep()
        ok("setup: the flag does not escalate immediately",
           eng.st.data.get("abandon_flags"), f"flags={eng.st.data.get('abandon_flags')}")
        clock["t"] += int(eng.knobs.get("abandon_flag_window", 60)) * 60 + 1
        eng._sweep()
    finally:
        eng.dry = True
    ok("AC-3 an untouched flag escalates to exactly ONE ordinary case after the "
       "bounded window (abandon_flag_window, default 60min) — via the REAL sweep entry "
       "point, not the helper directly",
       any("A-01" in (c.get("detail") or "") for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")
    ok("AC-3 the flag clears once escalated (never a second case)",
       not eng.st.data.get("abandon_flags"), f"flags={eng.st.data.get('abandon_flags')}")


def test_force_release_block_is_gone():
    ok("AC-3 _force_release_block no longer exists on Engine (the ADHOC-worker gap "
       "it left open is retired with it)",
       not any(n == "_force_release_block" for n in dir(Engine)))


# ══════════════════════════════════════════════════════════════════════════════════
# AC-4: observed-done auto-settle (F-1 self-healing survives the sweep retirement)
# ══════════════════════════════════════════════════════════════════════════════════

def test_observed_done_autosettles_wall():
    eng = _eng()
    wid = "ENG-A-01"
    sent = _capture(eng)
    eng._tq = []
    eng._h_escalate({"block": "A-01", "worker_id": wid, "detail": "mis-tagged — actually done"})
    cid = next(iter(eng.st.pending_cases))
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("setup: the worker is walled on a live, undecided case",
       w.get("status") == "walled" and eng.st.pending_cases[cid].get("decision") is None)
    # The block's gate subsequently OBSERVES the milestone done — never architect/
    # operator action.
    eng._on_block_done("A-01")
    ok("AC-4 the wall case auto-settles the instant done is observed — no operator page",
       cid not in eng.st.pending_cases, f"cases={eng.st.pending_cases}")
    ok("AC-4 zero operator/architect page from the auto-settle itself",
       not any(tid in ("escalate.wall", "tg.escalate") for tid, _ in sent), f"sent={sent}")
    ok("AC-4 a forensic wall_auto_settled event records the auto-settle",
       any(r.get("type") == "wall_auto_settled" and r.get("block") == "A-01"
           for r in _events(eng)), f"events={_events(eng)}")


def test_undecided_wall_on_undone_block_never_falsely_autosettles():
    eng = _eng()
    wid = "ENG-A-01"
    eng._tq = []
    eng._h_escalate({"block": "A-02", "worker_id": wid, "detail": "a real, live wall"})
    cid = next(iter(eng.st.pending_cases))
    eng._on_block_done("A-01")             # a DIFFERENT block reaching done
    ok("AC-4 regression: a wall on a DIFFERENT block never auto-settles",
       cid in eng.st.pending_cases, f"cases={eng.st.pending_cases}")


# ══════════════════════════════════════════════════════════════════════════════════
# AC-5: HIGH inventory — question_tron, sentry truncation, jobs.send retry
# ══════════════════════════════════════════════════════════════════════════════════

def test_question_tron_reaches_architect_with_full_content():
    eng = _eng()
    wid = "ENG-A-01"
    arch = _arch_idle(eng)
    long_q = "why is the trunk read stale? " * 20   # long enough that truncation would show
    eng._ingest("worker.question_tron", {"detail": long_q}, {"kind": "worker", "id": wid})
    job = arch.get("current_job") or {}
    ok("AC-5 question_tron reaches the architect (never a dead-end log-only path)",
       job.get("kind") == "triage", f"arch={arch}")
    ok("AC-5 the FULL content reaches the architect, untruncated",
       job.get("detail") == long_q, f"job={job}")


def test_sentry_text_arrives_untruncated():
    eng = _eng()
    arch = _arch_idle(eng)
    long_text = "x" * 300   # over the old 160-char cap
    eng._h_sentry({"_trigger": "*", "detail": long_text, "worker_id": "ENG-A-01"})
    job = arch.get("current_job") or {}
    ok("AC-5 sentry text reaches the architect fully, never capped at 160 chars",
       job.get("detail") == long_text, f"len={len(job.get('detail') or '')}")


def test_failed_jobs_send_is_retried_and_forensic_never_lost():
    eng = _eng()
    wid = "ENG-A-01"
    eng.dry = False
    w = next(x for x in eng.st.workers if x["id"] == wid)
    w["mbox_seq"] = 0
    orig_send = jobs.send
    calls = {"n": 0}

    def always_fail(*a, **k):
        calls["n"] += 1
        return False
    jobs.send = always_fail
    try:
        eng._to_worker(wid, "hello", "test.kind")
    finally:
        jobs.send = orig_send
    ok("AC-5 a failed jobs.send is retried inline (not given up on the first OSError)",
       calls["n"] >= 2, f"calls={calls}")
    ok("AC-5 the message is queued durable, never lost",
       bool(w.get("pending_sends")), f"w={w}")
    ok("AC-5 a forensic event records the mailbox failure",
       any(r.get("fclass") == "mailbox-send-failed" for r in _failures(eng)),
       f"failures={_failures(eng)}")
    # The queue drains at-least-once on the next tick's flush, once delivery works again.
    jobs.send = lambda *a, **k: True
    try:
        eng._flush_pending_sends()
    finally:
        jobs.send = orig_send
    ok("AC-5 the durable queue drains once delivery works again (at-least-once, never lost)",
       not w.get("pending_sends"), f"w={w}")
    eng.dry = True


# ══════════════════════════════════════════════════════════════════════════════════
# AC-5b: MED inventory (non-lint-catchable class)
# ══════════════════════════════════════════════════════════════════════════════════

def test_mailbox_send_failure_never_collides_seq_with_the_next_send():
    # Regression: the seq counter must reserve BEFORE the send attempt, not only on
    # success — else a later, unrelated send for the same worker right after a total
    # failure could compute the SAME seq a still-pending retry is holding, and the
    # runner's high-water dedupe would silently swallow whichever line arrives second.
    eng = _eng()
    wid = "ENG-A-01"
    eng.dry = False
    w = next(x for x in eng.st.workers if x["id"] == wid)
    w["mbox_seq"] = 4
    orig_send = jobs.send
    jobs.send = lambda *a, **k: False
    try:
        eng._to_worker(wid, "msg1 (fails)", "kind1")
    finally:
        jobs.send = orig_send
    ok("setup: msg1 queued pending after total failure", bool(w.get("pending_sends")))
    seq1 = w["pending_sends"][0]["seq"] if w.get("pending_sends") else None
    sent2 = []
    jobs.send = lambda worker_dir, seq, kind, text: sent2.append(seq) or True
    try:
        eng._to_worker(wid, "msg2 (succeeds)", "kind2")
    finally:
        jobs.send = orig_send
        eng.dry = True
    ok("AC-5 regression: a later successful send never reuses a still-pending seq",
       bool(sent2) and sent2[0] != seq1, f"seq1={seq1} sent2={sent2}")


def test_handler_exception_emits_forensic_event():
    eng = _eng()
    eng._tq = [("wall:raised:A-01", {"block": "A-01", "detail": "x"})]
    eng._route = (lambda trig, slots:
                 (_ for _ in ()).throw(RuntimeError("simulated handler explosion")))
    eng._drain_triggers()
    ok("AC-5b a handler exception emits a forensic event (never a bare silent log line)",
       any(r.get("fclass") == "handler-raised"
           and "simulated handler explosion" in (r.get("cause") or "")
           for r in _failures(eng)), f"failures={_failures(eng)}")


def test_triage_dedup_drop_emits_forensic_event():
    eng = _eng()
    eng.st.architect_queue.append({"kind": "triage", "detail": "same text twice",
                                   "sender": None, "block": "A-01"})
    eng._triage_to_architect("same text twice", block="A-01")
    ok("AC-5b a triage text-dedup drop emits a forensic event",
       any(r.get("type") == "triage_dedup_dropped" for r in _events(eng)),
       f"events={_events(eng)}")


def test_peer_question_placeholder_refused_real_content_required():
    eng = _eng()
    arch = _arch_idle(eng)
    wid = "ENG-A-01"
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        eng._ingest("worker.question_peer", {"detail": ""}, {"kind": "worker", "id": wid})
    finally:
        eng.dry = True
    ok("AC-5b an empty peer question is refused at the door (bounced, never laundered "
       "into a placeholder)", bool(tw) and not eng.st.architect_queue, f"tw={tw}")
    ok("AC-5b no '(peer question)' placeholder anywhere in what would have reached "
       "the architect", (arch.get("current_job") or {}) == {} or
       "(peer question)" not in ((arch.get("current_job") or {}).get("detail") or ""))
    # A REAL question still reaches the architect with its actual content.
    eng._ingest("worker.question_peer", {"detail": "should I use approach B?"},
               {"kind": "worker", "id": wid})
    job = arch.get("current_job") or {}
    ok("AC-5b a real peer question reaches the architect with its actual content",
       job.get("detail") == "should I use approach B?", f"job={job}")


# ══════════════════════════════════════════════════════════════════════════════════
# Regression: _close_case's new release-by-construction (_release_case_hold) now
# un-holds+replays a settled WALL_KINDS case itself — a caller that ALSO calls
# _unhold_and_replay explicitly after _close_case risks a double-fire (dead code at
# best if the walled-status guard happens to save it, a genuine double-nudge at worst
# if it doesn't). _relay_architect_answer used to do exactly this; the redundant
# explicit call is removed — _close_case alone is the complete release now.
# ══════════════════════════════════════════════════════════════════════════════════

def test_architect_relayed_settle_unhold_and_replay_fires_exactly_once():
    eng = _eng()
    wid = "ENG-A-01"
    arch = _arch_idle(eng)
    eng._tq = []
    eng._ingest("worker.wall", {"block": "A-01", "detail": "which schema?", "kind": "scope"},
               {"kind": "worker", "id": wid})
    eng._drain_triggers()
    cid = next(iter(eng.st.pending_cases))
    calls = {"n": 0}
    orig = eng._unhold_and_replay

    def spy(w, block, case):
        calls["n"] += 1
        return orig(w, block, case)
    eng._unhold_and_replay = spy
    eng.dry = False
    try:
        eng._ingest("worker.done", {"detail": "use v2"}, {"kind": "worker", "id": arch["id"]})
    finally:
        eng.dry = True
    ok("regression: the architect-relayed settle un-holds+replays EXACTLY ONCE "
       "(_close_case's own release-by-construction, never a second explicit call)",
       calls["n"] == 1, f"calls={calls}")
    ok("regression: the case still closes and the worker still un-holds",
       cid not in eng.st.pending_cases
       and next(x for x in eng.st.workers if x["id"] == wid).get("status") != "walled")


# ══════════════════════════════════════════════════════════════════════════════════
# AC-6 (light in-suite echo; the authoritative RED/GREEN proof is captured standalone
# in the PR body / final report per the block's cmd: verification method)
# ══════════════════════════════════════════════════════════════════════════════════

def test_lint_red_on_fixture_green_on_tree():
    d = tempfile.mkdtemp(prefix="tron-0131-lint-")
    fx = os.path.join(d, "fixture.py")
    with open(fx, "w") as fh:
        fh.write('detail = m.get("detail", "wall")\n')
    ok_red, violations = lint.content_field_lint([fx])
    ok("AC-6 the lint is RED on a seeded .get(<content-field>, default) fixture",
       not ok_red and violations, f"violations={violations}")
    ok_green, violations2 = lint.content_field_lint(lint._engine_source_files())
    ok("AC-6 the lint is GREEN on the clean engine tree",
       ok_green, f"violations={violations2}")


# ── forensic helpers ──
def _events(eng):
    import util
    return util.read_jsonl(eng.ctx.event_log)


def _failures(eng):
    return [r for r in _events(eng) if r.get("kind") == "failure"]


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
