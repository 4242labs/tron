"""block_01_18_test — regressions for the 01-18 gate-anchor-integrity + walled-worker
pacing-exemption set (holistic review round 2, post-01-17, canon 27d551c).

  T1  the F1 false-contradiction wall: `merged_sha` must anchor a sha that actually
      LANDED, never a pre-image. `merge_ff_only` may internally rebase-and-retry on a
      first ff-refusal (trunk.py T1, 01-17), rewriting the branch's tip out from under a
      PRE-merge tip read — anchoring to that pre-image dangled the A-5 ancestry predicate
      and gate-gave-up a clean landing one tick later as a false "force-push or reset?"
      contradiction. Fix: always re-read the tip AFTER `merge_ff_only` returns ok.
  T2  the un-hold seam owns held-verb replay (F2 + N7 + N9): `_unhold_worker` now pops
      `held_verbs` UNCONDITIONALLY and returns the queue; every caller (operator resume,
      the sweep's arm (a) settled-case repair) replays it in arrival order and sends the
      01-16 empty-queue nudge only when nothing was queued — mirroring resume exactly,
      where 01-17's sweep repair used to un-hold without ever popping (stale verbs from
      one hold episode used to replay again on a LATER re-wall). N9: an UNDECIDED case
      coexisting with a settled one for the same worker/block must win the match — arm
      (a) must never un-hold a worker out from under its own still-open wall.
  T3  walled workers are exempt from gate/close pacing (N3, both sites): a wall raised
      mid-gate or mid-close-out HOLDS its worker (D-15-2) and its runner idles by design
      (parked on the operator) — never a stall to accrue against. The close site is the
      worse defect (and the AC scenario): unfixed, a plain wall during close-out passed
      the idle guard, accrued, and at cap force-released a HELD worker out from under its
      own live wall case.
  T4  a settle that resolves a real case never reports "no match" (N6): the no-match
      notice was keyed on `not block`, which is also true for a correctly-RESOLVED
      block-less case (kind paperwork/residue, `block` is None by design) — key it on
      `case is None` instead.

Addendum (operator decision 2026-07-04, fix ALL known issues in this block):
  T5  `await` resume notifies the paused worker (N1): resume/approve settling a
      kind-`await` case matched no arm in `_h_apply_decision` (await never blocks the
      block or holds the worker) — the case closed and the worker stayed paused until
      the orphan-idle sweep raised a SECOND wall minutes later. Fix sends the paused
      worker the exact proceed line rung (c) already owns, worded for a settled
      checkpoint. `abandon` on an await case is untouched (today's drop-the-block path).
  T6  the blocked list gets its own invariant arm (N2): a block in `st.blocked` with NO
      undecided case, NO walled worker, and NO gate is unreachable by every other net —
      the wall-pairing law's third key (01-17 repaired the worker-keyed and gate-keyed
      halves; never the blocked-list half). Same one-silence-window law, same repair
      vocabulary (`_reraise_wall`) as the other two sweep arms.
  T7  `python3 engine/lint.py` no longer silently exits 0 having checked nothing — a
      `__main__` runs the real rule set standalone (mirroring `engine.py cmd_validate`)
      or names `./lint.sh` and exits non-zero.

Addendum 2 (operator, 2026-07-04):
  T8  a durable inbound-message archive (`messages.jsonl`, beside `events.jsonl`):
      `_claim_inboxes` archives every claimed inbox line VERBATIM — worker, operator,
      and tg all land, with `source` distinguishing the tg inbox from the console/API
      operator inbox even though both normalize to sender kind `operator`. A JSON-
      undecodable line archives too, flagged `unparsed`, raw, and today's skip-and-
      continue behavior is unchanged. A crash-replayed `.proc` sidecar re-archives —
      accepted, honest at-least-once duplicate forensics, same rule as every other
      at-least-once surface here.

T1/T3/T4/T5 are dry FSM-level cases (TRON_DRY, sentry_test's fixture builders — same
convention as mg_01_test.py/tron07_test.py). T2/T6's sweep arms need `eng.dry = False`
(_sweep no-ops entirely under dry) — same convention as block_01_17_test.py's T3 cases.
T8 cases call `_claim_inboxes()` directly (no classify/dispatch machinery needed) and
read `messages.jsonl` back via `util.read_jsonl`.

Run: python3 engine/block_01_18_test.py   (exit 0 = pass). No tokens, no network.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import util             # noqa: E402
import jobs              # noqa: E402
import trunk             # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []

PING_WINDOW_S = 6 * 60 + 1   # past silence_ping_min (default 6) — the sweep escalation window


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _events(eng):
    return util.read_jsonl(eng.ctx.event_log)


def _capture(eng):
    """Spy on eng.emit — returns the list it appends (template_id, slots) to, mirroring
    tron07_test._capture's convention."""
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
                sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


def _capture_to_worker(eng):
    """Spy on eng._to_worker (block_01_13_test's convention) — replaces it outright, since
    T5's proceed line is engine-composed via `_to_worker` directly, never through emit()."""
    sent = []
    eng._to_worker = lambda wid, text, kind: sent.append((wid, text, kind))
    return sent


# ── fixture builders ──
def _eng(block="A-01", status="🔄"):
    """A started engine with ONE working engineer already bound to `block` (mg_01_test/
    tron07_test convention)."""
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _wall(eng, block, wid, detail="flaky ci"):
    """Raise a worker-declared wall against an ALREADY-rostered worker (T3's convention:
    the worker exists via `_eng`; this just holds it). Returns the parked case id."""
    eng._tq = []
    eng._h_escalate({"block": block, "worker_id": wid, "detail": detail})
    return next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")


def _eng_bare(block="A-01", status="🔄"):
    """A started engine with NO worker yet — the sweep tests add their own via `_walled`
    (block_01_17_test's convention). `dry = False`: _sweep() no-ops entirely under dry."""
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    return eng


def _walled(eng, block, wid, status="idle", detail="flaky ci"):
    """A FRESH worker, held by a wall (block_01_17_test's convention). Returns the parked
    case id."""
    eng.st.workers.append({"id": wid, "role": "engineer", "block": block,
                           "session_id": "dry", "status": status})
    eng._tq = []
    eng._h_escalate({"block": block, "worker_id": wid, "detail": detail})
    return next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")


# ── T1 (AC-1 bullet 1): merged_sha anchors the POST-merge tip, survives a rebase-retry ──
def t_merged_sha_anchors_post_merge_tip_survives_rebase_retry():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    orig = (trunk.branch_merged, trunk.branch_exists, trunk.tip_sha,
           trunk.merge_ff_only, trunk.is_ancestor)
    calls = {"n": 0}

    def fake_tip_sha(root, branch, dry=False):
        # 1st read is the PRE-merge cur_tip (~1364); the internal rebase-retry (trunk.py
        # T1, 01-17) rewrites the branch's tip before the ff lands, so every read AFTER
        # `merge_ff_only` returns must see the NEW (post-rebase) tip.
        calls["n"] += 1
        return "PREIMAGE1234" if calls["n"] == 1 else "POSTMERGE5678"

    trunk.branch_merged = lambda *a, **k: False       # not on trunk yet
    trunk.branch_exists = lambda *a, **k: True         # the branch is really there
    trunk.tip_sha = fake_tip_sha
    trunk.merge_ff_only = lambda *a, **k: (True, "")   # simulates: ff-refused, rebased, retried, landed
    try:
        eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
        ok("T1 setup: the local ff-merge landed (stage advanced local -> trunk)",
           g.get("stage") == "trunk", f"g={g}")
        ok("T1 merged_sha anchors the POST-merge tip, never the pre-merge pre-image",
           g.get("merged_sha") == "POSTMERGE5678", f"g={g}")

        # Subsequent ticks at trunk/record must hold quietly: the pre-image sha would
        # falsely read as "no longer in trunk history" (rebased away); the correctly
        # anchored post-merge tip is the real trunk ancestor.
        trunk.is_ancestor = lambda root, sha, main, dry=False: sha == "POSTMERGE5678"
        eng._tq = []
        eng._drive_gate("A-01", g)          # plain tick at trunk (on_report=False)
        ok("T1 a tick at trunk holds quietly on the correctly-anchored sha "
           "(no false gate-contradiction)",
           "A-01" in eng.st.gate and g.get("stage") == "trunk"
           and not any(t.startswith("wall:raised:") for t, _ in eng._tq),
           f"gate={eng.st.gate} tq={eng._tq}")

        g["stage"] = "record"
        eng._tq = []
        eng._drive_gate("A-01", g)          # plain tick at record
        ok("T1 a tick at record also holds quietly on the same anchored sha",
           "A-01" in eng.st.gate
           and not any(t.startswith("wall:raised:") for t, _ in eng._tq),
           f"gate={eng.st.gate} tq={eng._tq}")
    finally:
        (trunk.branch_merged, trunk.branch_exists, trunk.tip_sha,
         trunk.merge_ff_only, trunk.is_ancestor) = orig


def t_merged_sha_regression_the_preimage_WOULD_have_false_contradicted():
    # Regression guard proving the fixture actually exercises the bug: anchoring to the
    # pre-merge pre-image (the old behavior) against the SAME is_ancestor stub as above
    # does read as a contradiction — the fix's `merged_sha` choice is load-bearing.
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None,
                                        "merged_sha": "PREIMAGE1234"})
    orig_anc = trunk.is_ancestor
    trunk.is_ancestor = lambda root, sha, main, dry=False: sha == "POSTMERGE5678"
    try:
        eng._tq = []
        eng._drive_gate("A-01", g)
        ok("setup: a pre-image anchor WOULD false gate-contradict (proves the fixture bites)",
           "A-01" not in eng.st.gate
           and any(t.startswith("wall:raised:") for t, _ in eng._tq),
           f"gate={eng.st.gate} tq={eng._tq}")
    finally:
        trunk.is_ancestor = orig_anc


# ── T2 (AC-1 bullet 2): the sweep's un-hold seam pops + replays exactly like resume ──
def t_sweep_arm_a_replays_the_queued_verb_and_releases():
    # Mirrors block_01_15_test's resume-replay case, but the un-hold is the SWEEP's
    # settled-case repair (arm (a)), never an operator resume.
    eng = _eng_bare()
    eng.st.row("A-01")["status"] = "done"
    wid = "ENG-A-01"
    cid = _walled(eng, "A-01", wid)
    orig_land, orig_clean = trunk.land_docs, trunk.replica_clean
    trunk.land_docs = lambda *a, **k: ("landed", "0 file(s)")
    trunk.replica_clean = lambda *a, **k: (True, "")
    try:
        eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
        # The clean confirmation arrives WHILE held -> queued, never processed live.
        eng._ingest("worker.done", {"block": "A-01", "clean_confirm": True, "_raw": "clean"},
                    {"kind": "worker", "id": wid})
        w = next(x for x in eng.st.workers if x["id"] == wid)
        ok("setup: the clean verb is queued behind the wall, not acted on",
           w.get("held_verbs") == [{"tag": "worker.done",
                                    "slots": {"block": "A-01", "clean_confirm": True,
                                              "_raw": "clean"}}],
           f"held_verbs={w.get('held_verbs')}")
        # Simulate the tron-23-class inconsistency: the case settles but nothing un-holds
        # (arm (a)'s own precondition).
        eng.st.pending_cases[cid]["decision"] = "resume"
        clock = {"t": 1000.0}
        eng._now_s = lambda: clock["t"]
        eng._sweep()                       # anchors wall_bad_since; too soon to fire
        ok("T2 the sweep does not act inside one silence window",
           next(x for x in eng.st.workers if x["id"] == wid).get("status") == "walled")
        clock["t"] += PING_WINDOW_S
        eng._sweep()
        eng._drain_triggers()              # the replayed trigger lands in _tq; drain it
        ok("T2 arm (a) replays the queued verb: the close confirms and releases "
           "(the D-16-1 swallow class, closed through the sweep's own door)",
           "A-01" not in eng.st.gate and not any(x["id"] == wid for x in eng.st.workers),
           f"gate={eng.st.gate} workers={eng.st.workers}")
    finally:
        trunk.land_docs, trunk.replica_clean = orig_land, orig_clean


def t_sweep_arm_a_pops_the_queue_even_when_the_replay_is_a_noop():
    # F2/N7: a STALE verb (queued behind a wall, then never relevant at replay time)
    # must be POPPED regardless — never left stranded to replay a second time on a
    # later hold episode.
    eng = _eng_bare()
    wid = "ENG-A-01"
    cid = _walled(eng, "A-01", wid)
    eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})
    # A stale record-receipt queues behind the wall; the gate sits at 'trunk', not
    # 'record', so replaying it later is a harmless no-op admission-wise — exactly the
    # stale shape F2/N7 must never replay twice.
    eng._ingest("worker.recorded", {"block": "A-01"}, {"kind": "worker", "id": wid})
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("setup: the stale verb is queued behind the wall",
       w.get("held_verbs") == [{"tag": "worker.recorded", "slots": {"block": "A-01"}}])
    eng.st.pending_cases[cid]["decision"] = "resume"
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng._sweep()
    clock["t"] += PING_WINDOW_S
    eng._sweep()
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("T2 arm (a) un-holds on the settled case", w.get("status") != "walled", f"w={w}")
    ok("T2 arm (a) pops held_verbs UNCONDITIONALLY (never stranded for a later re-wall)",
       not w.get("held_verbs"), f"w={w}")
    ok("T2 the replayed stale verb is a harmless no-op at this stage (gate untouched)",
       "A-01" in eng.st.gate and eng.st.gate["A-01"].get("stage") == "trunk",
       f"gate={eng.st.gate}")


def t_sweep_arm_a_empty_queue_nudge_parity_with_resume():
    # 01-16 addendum, mirrored: an EMPTY replay queue must never leave a mutual wait —
    # the un-hold sends the gate's own pending stage prompt, exactly like resume's own
    # empty-queue nudge (~1104-1112).
    eng = _eng_bare()
    wid = "ENG-A-01"
    cid = _walled(eng, "A-01", wid)
    eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})
    eng.st.pending_cases[cid]["decision"] = "resume"
    sent = _capture(eng)
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng._sweep()
    clock["t"] += PING_WINDOW_S
    eng._sweep()
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("T2 arm (a) un-holds with an empty replay queue", w.get("status") != "walled", f"w={w}")
    ok("T2 empty-queue nudge parity: the gate's own pending stage prompt re-sends "
       "(never a bare un-hold, same as an operator resume)",
       any(tid == "gate.trunk" for tid, _ in sent), f"sent={sent}")


def t_sweep_undecided_case_wins_over_a_settled_one_n9():
    # N9: a settled-but-unclosed case coexisting with a LIVE undecided one for the same
    # worker/block must never let arm (a) un-hold the worker out from under its own
    # still-open wall.
    eng = _eng_bare()
    wid = "ENG-A-01"
    cid_settled = _walled(eng, "A-01", wid, detail="first wall, already settled")
    eng.st.pending_cases[cid_settled]["decision"] = "resume"
    cid_live = eng._open_case("A-01", "wall", wid, "second wall, still live")
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng._sweep()
    clock["t"] += PING_WINDOW_S
    eng._sweep()
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("N9 an undecided case coexisting with a settled one wins the match "
       "-> the worker STAYS walled", w.get("status") == "walled", f"w={w}")
    ok("N9 the settled case is left untouched (arm (a) never fired on it)",
       eng.st.pending_cases.get(cid_settled, {}).get("decision") == "resume")
    ok("N9 the live case is still there, undecided",
       eng.st.pending_cases.get(cid_live, {}).get("decision") is None)


# ── T3 (AC-1 bullet 3): walled workers are exempt from gate/close pacing (N3) ──
def t_walled_worker_exempt_from_gate_idle_accrual():
    eng = _eng(status="🔄")
    wid = "ENG-A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    _wall(eng, "A-01", wid)
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda *a, **k: True     # idle by design — parked on the operator
    try:
        eng._drive_gate("A-01", g)
        clock["t"] += eng._pace("gate_idle_cap", 3) + 1    # well past the cap
        eng._tq = []
        eng._drive_gate("A-01", g)
        ok("T3 a walled worker never accrues gate idle time (no gate-idle-cap escalation, "
           "the slot 01-15 deliberately preserved stays preserved)",
           "A-01" in eng.st.gate and g.get("stage") == "local"
           and g.get("idle_since") is None
           and not any(t.startswith("wall:raised:") for t, _ in eng._tq),
           f"gate={eng.st.gate} tq={eng._tq}")
    finally:
        jobs.runner_idle = orig_idle


def t_walled_worker_exempt_from_close_pacing_the_ac_scenario():
    # The AC scenario: a plain wall raised DURING close-out must never force-release the
    # HELD worker out from under its own live wall case.
    eng = _eng(status="✅")
    eng.st.row("A-01")["status"] = "done"
    wid = "ENG-A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    cid = _wall(eng, "A-01", wid)
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda *a, **k: True     # the held worker's runner idles, by design
    try:
        eng._drive_close("A-01", g, wid)
        clock["t"] += eng._pace("gate_close_cap", 3) + 1    # well past the force-release cap
        eng._tq = []
        eng._drive_close("A-01", eng.st.gate["A-01"], wid)
        ok("T3 (AC) a walled worker at close never accrues close-idle time",
           g.get("close_idle_since") is None, f"g={g}")
        ok("T3 (AC) the gate holds instead of force-releasing the held worker out from "
           "under its own live wall",
           "A-01" in eng.st.gate and eng.st.gate["A-01"].get("stage") == "close",
           f"gate={eng.st.gate}")
        ok("T3 (AC) the worker stays walled (never force-released)",
           any(w["id"] == wid and w.get("status") == "walled" for w in eng.st.workers),
           f"workers={eng.st.workers}")
        ok("T3 (AC) the live wall case is untouched (no duplicate/blind release)",
           cid in eng.st.pending_cases and eng.st.pending_cases[cid].get("decision") is None)
    finally:
        jobs.runner_idle = orig_idle


# ── T4 (AC-1 bullet 4): a resolved case never reports "no match" ──
def t_paperwork_and_residue_case_settle_never_reports_no_match():
    eng = _eng()
    wid = "ENG-A-01"
    for kind in ("paperwork", "residue"):
        cid = eng._open_case(None, kind, wid, f"{kind} unlandable — needs an operator call")
        sent = _capture(eng)
        eng._h_apply_decision({"case": cid, "decision": "resume"})
        ok(f"T4 a resolved block-less '{kind}' case never emits the false 'no match' notice",
           not any(tid == "escalate.unclassified" for tid, _ in sent), f"sent={sent}")
        ok(f"T4 the resolved '{kind}' case is still closed exactly as before",
           cid not in eng.st.pending_cases)


def t_unresolved_settle_still_reports_no_match_regression():
    # Regression guard (D-15-3 unchanged): a settle that resolves NOTHING at all must
    # still name it — T4 narrows the trigger, it never silences the real case.
    eng = _eng()
    sent = _capture(eng)
    eng._h_apply_decision({"case": "CASE-999", "decision": "resume"})
    ok("T4 regression: a genuinely unresolved settle still reports 'no match'",
       any(tid == "escalate.unclassified" for tid, _ in sent), f"sent={sent}")


# ── T5 (AC-1 bullet 5): await-resume notifies the paused worker (N1) ──
def t_await_resume_delivers_the_proceed_line():
    eng = _eng()
    wid = "ENG-A-01"
    cid = eng._open_case("A-01", "await", wid, "ship it?")
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        eng._h_apply_decision({"case": cid, "decision": "resume"})
    finally:
        eng.dry = True
    ok("T5 await-resume sends the paused worker the proceed line",
       any(w == wid and k == "await.proceed" for w, _, k in tw), f"sent={tw}")
    ok("T5 await-resume closes the settled case", cid not in eng.st.pending_cases)


def t_await_approve_is_treated_the_same_as_resume():
    # T5: "treat approve the same — both mean proceed."
    eng = _eng()
    wid = "ENG-A-01"
    cid = eng._open_case("A-01", "await", wid, "ship it?")
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        eng._h_apply_decision({"case": cid, "decision": "approve"})
    finally:
        eng.dry = True
    ok("T5 approve on an await case also delivers the proceed line",
       any(w == wid and k == "await.proceed" for w, _, k in tw), f"sent={tw}")


def t_await_abandon_keeps_todays_drop_path_no_proceed_line():
    # abandon on an await case must NOT notify the worker — it keeps the existing
    # unconditional drop-the-block path (the abandon arm never checked `block in
    # st.blocked`, so it already fired for await cases before this fix; T5 must not
    # change that).
    eng = _eng()
    wid = "ENG-A-01"
    cid = eng._open_case("A-01", "await", wid, "ship it?")
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        eng._h_apply_decision({"case": cid, "decision": "abandon"})
    finally:
        eng.dry = True
    ok("T5 abandon on an await case never sends the proceed line",
       not any(k == "await.proceed" for _, _, k in tw), f"sent={tw}")
    ok("T5 abandon on an await case still drops the block (today's behavior, unchanged)",
       "A-01" in eng._dropped())
    ok("T5 abandon on an await case still releases the worker",
       not any(w["id"] == wid for w in eng.st.workers))


# ── T6 (AC-1 bullet 6): the blocked-list gets its own invariant arm (N2) ──
def t_blocked_list_arm_reraises_an_uncovered_block_after_one_window():
    eng = _eng_bare()
    eng.st.blocked.append("A-01")             # blocked, NO case, NO walled worker, NO gate
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng._sweep()
    ok("T6 the arm never fires inside one silence window",
       not any(c.get("kind") == "wall" and c.get("worker_id") is None
               for c in eng.st.pending_cases.values()))
    clock["t"] += PING_WINDOW_S
    eng._sweep()
    ok("T6 an uncovered blocked block re-raises a fresh wall case (wid None) after one window",
       any(c.get("kind") == "wall" and c.get("block") == "A-01" and c.get("worker_id") is None
           for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")
    ok("T6 the reraise emits the ordinary escalate event",
       any(e.get("type") == "escalate" and e.get("block") == "A-01"
           for e in _events(eng)),
       f"events={_events(eng)}")


def t_blocked_list_arm_never_touches_a_case_covered_block():
    eng = _eng_bare()
    eng.st.blocked.append("A-01")
    eng._open_case("A-01", "wall", None, "already parked")   # coverage: a live undecided case
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng._sweep()
    clock["t"] += PING_WINDOW_S
    before = len(eng.st.pending_cases)
    eng._sweep()
    ok("T6 a block covered by a live undecided case is never re-raised",
       len(eng.st.pending_cases) == before, f"cases={eng.st.pending_cases}")


def t_blocked_list_arm_never_touches_a_walled_worker_covered_block():
    eng = _eng_bare()
    eng.st.blocked.append("A-01")
    wid = "ENG-A-01"
    eng.st.workers.append({"id": wid, "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "walled"})
    eng._open_case("A-01", "wall", wid, "a genuine, still-live wall")   # keeps arm (a)/(b) quiet
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng._sweep()
    clock["t"] += PING_WINDOW_S
    eng._sweep()
    ok("T6 a block covered by a walled worker is never re-raised by this arm",
       not any(c.get("kind") == "wall" and c.get("block") == "A-01"
               and c.get("worker_id") is None
               for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")


def t_blocked_list_arm_never_touches_a_gated_block():
    eng = _eng_bare()
    eng.st.blocked.append("A-01")
    eng.st.gate["A-01"] = {"stage": "local", "pr": None}
    # A bound (non-walled) worker keeps the PRE-EXISTING workerless-gate sweep arm
    # (01-16, T2) from popping this gate at the same one-window mark this test advances
    # past — this test isolates T6's OWN "gate exists" coverage rule, not that other net.
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng._sweep()
    clock["t"] += PING_WINDOW_S
    before = len(eng.st.pending_cases)
    eng._sweep()
    ok("T6 a block covered by a live gate is never re-raised",
       len(eng.st.pending_cases) == before and "A-01" in eng.st.gate,
       f"cases={eng.st.pending_cases} gate={eng.st.gate}")


def t_blocked_list_arm_clock_clears_when_coverage_returns():
    eng = _eng_bare()
    eng.st.blocked.append("A-01")
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng._sweep()                       # anchors blocked_bad_since["A-01"]
    ok("setup: the clock anchored on the uncovered block",
       "A-01" in (eng.st.data.get("blocked_bad_since") or {}))
    eng._open_case("A-01", "wall", None, "operator parked it in the meantime")
    eng._sweep()                       # coverage returned -> clock clears immediately
    ok("T6 the clock clears the instant coverage returns",
       "A-01" not in (eng.st.data.get("blocked_bad_since") or {}))
    clock["t"] += PING_WINDOW_S
    before = len(eng.st.pending_cases)
    eng._sweep()
    ok("T6 no reraise fires later since coverage had already returned",
       len(eng.st.pending_cases) == before, f"cases={eng.st.pending_cases}")


# ── T7: `python3 engine/lint.py` is never a silent no-op ──
def t_lint_py_entrypoint_really_lints_or_exits_nonzero():
    proc = subprocess.run([sys.executable, os.path.join(HERE, "lint.py")],
                          capture_output=True, text=True, cwd=HERE)
    ran_real_rules = "blueprint-lint:" in proc.stdout and ("OK" in proc.stdout
                                                           or "FAILED" in proc.stdout)
    named_entrypoint_and_failed = ("lint.sh" in proc.stdout and proc.returncode != 0)
    ok("T7 lint.py either runs the real rule set standalone or names ./lint.sh and fails",
       ran_real_rules or named_entrypoint_and_failed,
       f"rc={proc.returncode} stdout={proc.stdout!r}")
    ok("T7 lint.py never exits 0 without having checked something",
       proc.returncode == 0 and ran_real_rules or proc.returncode != 0,
       f"rc={proc.returncode} stdout={proc.stdout!r}")
    # This repo IS the canon self-lint context (no project.yaml) — the real rule set is
    # cheaply reproducible here, so it should actually run and pass, exactly like ./lint.sh.
    ok("T7 in this repo, lint.py's __main__ reproduces ./lint.sh's own OK result",
       ran_real_rules and proc.returncode == 0 and "OK" in proc.stdout,
       f"rc={proc.returncode} stdout={proc.stdout!r}")


# ── T8 (Addendum 2, AC-T8): durable inbound-message archive ──
def _messages(eng):
    return util.read_jsonl(eng.ctx.message_log)


def t_claimed_messages_archived_verbatim_worker_operator_tg():
    eng = _eng_bare()
    eng.st.data.setdefault("last_sweep", {})["sweeps_this_session"] = 7
    util.append_jsonl(eng.ctx.worker_inbox,
                      {"text": "worker report", "sender": {"kind": "worker", "id": "ENG-A-01"}})
    util.append_jsonl(eng.ctx.operator_inbox,
                      {"text": "resume CASE-001", "sender": {"kind": "operator", "id": "op1"}})
    util.append_jsonl(eng.ctx.tg_inbox,
                      {"text": "approve CASE-002", "sender": {"kind": "operator", "id": "tg-1"}})
    claimed, msgs = eng._claim_inboxes()
    ok("setup: all three inboxes parsed", len(msgs) == 3, f"msgs={msgs}")
    recs = _messages(eng)
    ok("T8 every claimed message (worker + operator + tg) lands in messages.jsonl",
       len(recs) == 3, f"recs={recs}")
    ok("T8 archived BEFORE the sidecar is released (still .proc on disk when read back)",
       all(os.path.exists(p) for p in claimed), f"claimed={claimed}")
    by_source = {r["source"]: r for r in recs}
    ok("T8 source distinguishes worker/operator/tg even though tg normalizes to sender "
       "kind 'operator' like the console/API inbox",
       set(by_source) == {"worker", "operator", "tg"}, f"recs={recs}")
    ok("T8 the tg record's sender kind is normalized 'operator' (kind unchanged; source "
       "is the new, finer key)",
       by_source["tg"]["sender"].get("kind") == "operator", f"recs={recs}")
    ok("T8 every record carries the in-progress tick number (_log_env's own idiom)",
       all(r.get("tick") == 7 for r in recs), f"recs={recs}")
    ok("T8 text is preserved verbatim per source",
       by_source["worker"]["text"] == "worker report"
       and by_source["operator"]["text"] == "resume CASE-001"
       and by_source["tg"]["text"] == "approve CASE-002",
       f"recs={recs}")


def t_malformed_line_archived_flagged_unparsed_processing_unharmed():
    eng = _eng_bare()
    eng.st.data.setdefault("last_sweep", {})["sweeps_this_session"] = 3
    with open(eng.ctx.worker_inbox, "w") as fh:
        fh.write("not json at all\n")
        fh.write(json.dumps({"text": "a good one",
                             "sender": {"kind": "worker", "id": "ENG-A-01"}}) + "\n")
    claimed, msgs = eng._claim_inboxes()
    ok("T8 setup: the malformed line is still skipped from processing (unchanged behavior)",
       len(msgs) == 1 and msgs[0]["text"] == "a good one", f"msgs={msgs}")
    recs = _messages(eng)
    ok("T8 both lines are archived despite one being JSON-undecodable", len(recs) == 2,
       f"recs={recs}")
    ok("T8 the malformed line archives flagged unparsed, with the raw text preserved",
       any(r.get("unparsed") is True and r.get("raw") == "not json at all"
           and r.get("tick") == 3 for r in recs),
       f"recs={recs}")
    ok("T8 the well-formed line on the same inbox still archives normally",
       any(r.get("text") == "a good one" and not r.get("unparsed") for r in recs),
       f"recs={recs}")


def t_crash_replay_leftover_proc_sidecar_rearchives_without_breaking_tick():
    eng = _eng_bare()
    eng.st.data.setdefault("last_sweep", {})["sweeps_this_session"] = 5
    proc = eng.ctx.worker_inbox + ".proc"
    with open(proc, "w") as fh:
        fh.write(json.dumps({"text": "crash replay text",
                             "sender": {"kind": "worker", "id": "ENG-A-01"}}) + "\n")
    claimed, msgs = eng._claim_inboxes()
    ok("T8 a leftover .proc (crash residue) is claimed again, never a fresh live-inbox read",
       claimed == [proc], f"claimed={claimed}")
    ok("T8 the replayed message still reaches processing (at-least-once, unbroken tick)",
       len(msgs) == 1 and msgs[0]["text"] == "crash replay text", f"msgs={msgs}")
    recs = _messages(eng)
    ok("T8 the crash-replayed sidecar re-archives its line", len(recs) == 1
       and recs[0]["text"] == "crash replay text", f"recs={recs}")
    # A second crash before release replays the SAME sidecar again -> accepted duplicate
    # forensics (at-least-once law), never a raised error, never a broken tick.
    claimed2, msgs2 = eng._claim_inboxes()
    ok("T8 re-claiming the same leftover sidecar a second time still does not break the tick",
       len(msgs2) == 1, f"msgs2={msgs2}")
    ok("T8 the duplicate re-archive is accepted (2 honest duplicate records, not deduped)",
       len(_messages(eng)) == 2, f"recs={_messages(eng)}")


def t_full_text_never_truncated():
    eng = _eng_bare()
    eng.st.data.setdefault("last_sweep", {})["sweeps_this_session"] = 9
    long_text = ("the operator's full inbound reasoning, well past the 200-char "
                 "snippet the unclassified/failure records keep — this line exists "
                 "to prove the archive never truncates it, unlike those forensic "
                 "shortcuts elsewhere in the engine. end-marker-follows.")
    ok("setup: fixture text is actually over 200 chars", len(long_text) > 200,
       f"len={len(long_text)}")
    util.append_jsonl(eng.ctx.operator_inbox,
                      {"text": long_text, "sender": {"kind": "operator", "id": "op1"}})
    eng._claim_inboxes()
    recs = _messages(eng)
    ok("T8 the full text is archived verbatim, never truncated",
       any(r.get("text") == long_text for r in recs),
       f"lens={[len(r.get('text') or '') for r in recs]}")


def main():
    for fn in sorted(k for k in globals() if k.startswith("t_")):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
