"""block_01_16_test — regressions for the 01-16 gate-lifecycle-under-worker-purge set
(tron-17 defect D-17-1).

  T1  a purged worker is a released worker (seam 1): `recover`'s dead-runner purge emits
      the ordinary `release` event (reason `stall-recover`, same vocabulary `_h_recover`
      already uses for a live-detected stall) and hands any gate the worker held to T2 —
      never a silent pool removal.
  T2  a workerless gate is never a wait state (seams 2 + 4): every path that finds a
      block's gate outliving its bound worker (a purge, a `resume` that finds nobody left
      to un-hold, the sweep's silence backstop) resolves deterministically — confirm-close
      on trunk evidence if the block is ✅ + landed clean, else `gate-orphaned` (never a
      new code). The 01-15 sweep predicate (which required an idle WORKER to exist) is
      extended to cover a gate with NO bound worker at all.
  T3  an empty trunk read never mutates gate state (supporting defect): a blank trunk sha
      is a FAULT for that tick alone — skip the read/reconcile and gate re-evaluation,
      never regress a done block's gate or re-create gate state from the blank view.
  T4  wind-down cannot silently live-lock (seam 4 hardening): a stranded workerless gate
      resolves within one silence window, so `_all_settled` and the sweep's escalation
      agree — no reachable state ticks forever with no worker, no dispatch, no
      escalation, and no session end.
  ADD the tron-19/20 addendum — the SECOND live-lock arm, a LIVE idle runner in a mutual
      wait: (i) un-hold with an empty replay queue always ends with the worker's
      state-appropriate next message (stage prompt / heartbeat ping / release) — never
      two parties waiting on each other; (ii) the idle-bound orphan predicate fires on a
      clock the runner's idle-poll cannot refresh (one observed-inconsistency window on
      the engine's own wall clock, OR the original stale-record delta) — arm (a)
      done+gateless releases and frees the slot, arm (b) open+gateless escalates
      gate-orphaned; (iii) a missing runner record stays covered end-to-end
      (worker:stalled -> release + redispatch).

FSM-level cases are dry (TRON_DRY, sentry_test's fixture builders — same convention as
block_01_15_test.py). Run: python3 engine/block_01_16_test.py   (exit 0 = pass). No
tokens, no network.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import util             # noqa: E402
import trunk             # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _events(eng):
    return util.read_jsonl(eng.ctx.event_log)


def _releases(eng):
    return [e for e in _events(eng) if e.get("type") == "release"]


def _failures(eng):
    return [e for e in _events(eng) if e.get("kind") == "failure"]


def _gate_advances(eng, since=0):
    return [e for e in _events(eng)[since:] if e.get("type") == "gate_advance"]


PING_WINDOW_S = 6 * 60 + 1  # past silence_ping_min (default 6) — the T2/T4 escalation window


# ── T1 (AC-1): purge emits release + T2 handoff ──
def t_purge_done_gate_confirm_closes_on_evidence():
    ctx, _ = build(blocks=[("A-01", "✅", "none")])
    eng = Engine(ctx); started(eng)
    ok("setup: block already done on trunk", eng.st.row("A-01")["status"] == "done")
    eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "s1", "status": "working"})
    # No real runner-store record exists for ENG-A-01 -> jobs.is_alive reads dead by
    # default (the natural fixture, not a monkeypatch — a fresh test ctx never spawned it).
    orig_land, orig_clean = trunk.land_docs, trunk.replica_clean
    trunk.land_docs = lambda *a, **k: ("landed", "0 file(s)")
    trunk.replica_clean = lambda *a, **k: (True, "")
    try:
        alive, purged = eng.recover()
        ok("T1 the dead runner is purged, not recovered", (alive, purged) == (0, 1))
        rel = _releases(eng)
        hit = next((e for e in rel if e.get("actor") == "ENG-A-01"), None)
        ok("T1 the purge emits an ordinary release event (never silent)", hit is not None,
           f"releases={rel}")
        ok("T1 the release reason is the existing stall-recover vocabulary",
           hit and hit.get("payload", {}).get("reason") == "stall-recover", f"hit={hit}")
        ok("T1 the worker leaves the roster",
           not any(w["id"] == "ENG-A-01" for w in eng.st.workers))
        ok("T1 the handed-off gate confirm-closes on trunk evidence (never stranded)",
           "A-01" not in eng.st.gate, f"gate={eng.st.gate}")
        ok("T1 no gate-orphaned escalation needed — the evidence was there",
           not any(f.get("code") == "gate-orphaned" for f in _failures(eng)))
    finally:
        trunk.land_docs, trunk.replica_clean = orig_land, orig_clean


def t_purge_not_done_gate_escalates_gate_orphaned():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    ok("setup: block not done yet", eng.st.row("A-01")["status"] != "done")
    eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "s1", "status": "working"})
    alive, purged = eng.recover()
    ok("T1 the dead runner is purged", (alive, purged) == (0, 1))
    rel = _releases(eng)
    ok("T1 the purge still emits release when the block isn't done",
       any(e.get("actor") == "ENG-A-01" and e.get("payload", {}).get("reason") == "stall-recover"
           for e in rel), f"releases={rel}")
    ok("T1 _redispatch alone (the old behavior) would have no-op'd here — "
       "the handoff must escalate instead",
       "A-01" not in eng.st.gate)
    fails = _failures(eng)
    hit = next((f for f in fails if f.get("code") == "gate-orphaned"), None)
    ok("T2 anything short of done-on-trunk gives up NAMED gate-orphaned",
       hit is not None and hit.get("block") == "A-01", f"fails={fails}")


# ── T2 (AC-1): resume-on-missing-worker never silently no-ops ──
def t_resume_missing_worker_confirm_closes_done_gate():
    ctx, _ = build(blocks=[("A-01", "✅", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "s1", "status": "working"})
    eng._tq = []
    eng._h_escalate({"block": "A-01", "worker_id": "ENG-A-01", "detail": "flaky ci"})
    cid = next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")
    ok("setup: the wall holds the worker and parks the block",
       next(w for w in eng.st.workers if w["id"] == "ENG-A-01").get("status") == "walled"
       and "A-01" in eng.st.blocked)
    # The held worker's runner dies and is purged out from under its own wall (tron-17's
    # exact gap) — simulated directly: the roster entry is simply gone by the time the
    # operator's reply lands.
    eng.st.workers[:] = [w for w in eng.st.workers if w["id"] != "ENG-A-01"]
    orig_land, orig_clean = trunk.land_docs, trunk.replica_clean
    trunk.land_docs = lambda *a, **k: ("landed", "0 file(s)")
    trunk.replica_clean = lambda *a, **k: (True, "")
    try:
        eng._h_apply_decision({"case": cid, "decision": "resume"})
        ok("T2 resume with no worker to un-hold never silently no-ops — "
           "it confirm-closes on trunk evidence",
           "A-01" not in eng.st.gate, f"gate={eng.st.gate}")
        ok("T2 the block leaves the blocked/parked set", "A-01" not in eng.st.blocked)
    finally:
        trunk.land_docs, trunk.replica_clean = orig_land, orig_clean


def t_resume_missing_worker_not_done_escalates():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "s1", "status": "working"})
    eng._tq = []
    eng._h_escalate({"block": "A-01", "worker_id": "ENG-A-01", "detail": "flaky ci"})
    cid = next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")
    eng.st.workers[:] = [w for w in eng.st.workers if w["id"] != "ENG-A-01"]
    eng._h_apply_decision({"case": cid, "decision": "resume"})
    ok("T2 resume with no worker and no done-evidence gives up NAMED, never silent",
       "A-01" not in eng.st.gate)
    hit = next((f for f in _failures(eng) if f.get("code") == "gate-orphaned"), None)
    ok("T2 the escalation is the existing gate-orphaned code",
       hit is not None and hit.get("block") == "A-01", f"fails={_failures(eng)}")


# ── T2 (AC-1): the extended sweep predicate — a workerless gate escalates within one window ──
def t_sweep_workerless_not_done_gate_escalates_within_window():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False        # _sweep no-ops entirely under dry — this exercises the real path
    eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})  # no bound worker at all
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng._sweep()
    ok("T2 a fresh workerless gate is not yet escalated (never misfires instantly)",
       "A-01" in eng.st.gate, f"gate={eng.st.gate}")
    clock["t"] += 100          # well under the silence window
    eng._sweep()
    ok("T2 still parked under the silence window",
       "A-01" in eng.st.gate, f"gate={eng.st.gate}")
    clock["t"] += PING_WINDOW_S
    eng._sweep()
    ok("T2 the workerless gate escalates gate-orphaned after one silence window",
       "A-01" not in eng.st.gate, f"gate={eng.st.gate}")
    hit = next((f for f in _failures(eng) if f.get("code") == "gate-orphaned"), None)
    ok("T2 escalation is NAMED gate-orphaned", hit is not None and hit.get("block") == "A-01")


def t_sweep_never_misreads_a_bound_worker_as_orphaned():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    clock["t"] += PING_WINDOW_S * 3
    eng._sweep()
    ok("T2 regression guard: a gate with a LIVE bound worker never orphans via the "
       "workerless net, however long it sits",
       "A-01" in eng.st.gate, f"gate={eng.st.gate}")


def t_sweep_never_misreads_a_review_gate_as_orphaned():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.st.gate["review:code"] = {"stage": "review", "pr": None}
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    clock["t"] += PING_WINDOW_S * 3
    eng._sweep()
    ok("T2 regression guard: a review gate is never swept by the engineer-workerless net "
       "(it has no engineer to bind in the first place)",
       "review:code" in eng.st.gate, f"gate={eng.st.gate}")


def t_sweep_spares_a_violation_wall_already_parked():
    ctx, _ = build(blocks=[("A-01", "✅", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.st.gate["A-01"] = {"stage": "close", "pr": None, "violation_pending": True}
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    clock["t"] += PING_WINDOW_S * 3
    eng._sweep()
    ok("T2 a close-time violation already parked as an ordinary wall survives the purge "
       "(the case, not the gate, owns its resolution)",
       "A-01" in eng.st.gate and eng.st.gate["A-01"].get("violation_pending") is True)


# ── T3 (AC-1): an empty trunk read leaves all gate state untouched ──
def t_empty_trunk_read_never_regresses_gate_state():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    eng.st.row("A-01")["status"] = "done"      # the gate's own view — done + at close
    before = len(_events(eng))
    # T2 (01-32, ADR-0002 D1): _refresh_from_trunk reads trunk.truth_sha, never
    # trunk.head_sha — stub the seam the engine actually calls.
    orig_truth_sha = trunk.truth_sha
    trunk.truth_sha = lambda *a, **k: ""
    try:
        eng.tick()
    finally:
        trunk.truth_sha = orig_truth_sha
    ok("T3 a blank trunk sha is flagged a fault for this tick",
       eng._trunk_fault is True)
    ok("T3 the gate never regresses off a blank view",
       eng.st.gate.get("A-01", {}).get("stage") == "close", f"g={eng.st.gate.get('A-01')}")
    ok("T3 the row view is untouched too (no reconcile against a blank read)",
       eng.st.row("A-01")["status"] == "done")
    ok("T3 no gate_advance fired this tick (no phantom close -> local -> close)",
       not _gate_advances(eng, before), f"advances={_gate_advances(eng, before)}")


def t_empty_trunk_read_recovers_next_good_tick():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    eng.st.row("A-01")["status"] = "done"
    orig_truth_sha = trunk.truth_sha
    trunk.truth_sha = lambda *a, **k: ""
    try:
        eng.tick()
    finally:
        trunk.truth_sha = orig_truth_sha
    ok("setup: the fault tick left the fault flag set", eng._trunk_fault is True)
    eng.tick()          # a normal tick with a real trunk read
    ok("T3 the very next good-read tick clears the fault",
       eng._trunk_fault is False)


# ── ADDENDUM (tron-19/20): the second live-lock arm — LIVE idle runner, mutual wait ──
def _capture(eng):
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
                sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


def _walled(eng, block, wid, status="idle"):
    """An idle worker held by a wall with an EMPTY replay queue — tron-19/20's exact
    pre-resume state. Returns the parked case id."""
    eng.st.workers.append({"id": wid, "role": "engineer", "block": block,
                           "session_id": "dry", "status": status})
    eng._tq = []
    eng._h_escalate({"block": block, "worker_id": wid, "detail": "flaky ci"})
    return next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")


def t_resume_empty_queue_open_gateless_pings_worker():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    cid = _walled(eng, "A-01", "ENG-A-01")
    sent = _capture(eng)
    eng._h_apply_decision({"case": cid, "decision": "resume"})
    w = next(x for x in eng.st.workers if x["id"] == "ENG-A-01")
    ok("ADD resume restores the held status (not walled)", w.get("status") == "idle",
       f"w={w}")
    ok("ADD un-hold with an empty replay queue re-nudges — never a mutual wait",
       any(t == "heartbeat.ping" and s.get("worker_id") == "ENG-A-01" for t, s in sent),
       f"sent={sent}")


def t_resume_empty_queue_gate_open_resends_stage_prompt():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.gate["A-01"] = {"stage": "trunk", "pr": None, "merged_sha": None}
    cid = _walled(eng, "A-01", "ENG-A-01")
    sent = _capture(eng)
    eng._h_apply_decision({"case": cid, "decision": "resume"})
    ok("ADD un-hold mid-gate re-sends the gate's own pending stage prompt",
       any(t == "gate.trunk" and s.get("worker_id") == "ENG-A-01" for t, s in sent),
       f"sent={sent}")
    ok("ADD the gate itself is untouched by the re-nudge",
       eng.st.gate.get("A-01", {}).get("stage") == "trunk")


def t_resume_empty_queue_done_gateless_releases_and_frees_slot():
    ctx, _ = build(blocks=[("A-01", "✅", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.live_config["worker_count"] = 1
    cid = _walled(eng, "A-01", "ENG-A-01")
    eng._h_apply_decision({"case": cid, "decision": "resume"})
    ok("ADD resume on a done+gateless block releases the worker (nothing remains for it)",
       not any(x.get("id") == "ENG-A-01" for x in eng.st.workers),
       f"workers={eng.st.workers}")
    rel = [e for e in _releases(eng) if e.get("actor") == "ENG-A-01"]
    ok("ADD the release is event-logged", bool(rel), f"releases={_releases(eng)}")
    ok("ADD dispatch is no longer starved (the slot is free)", eng._free_slots() == 1)


def t_resume_no_worker_no_gate_rearms_the_block():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.blocked.append("A-01")     # parked, but its worker AND gate are both long gone
    eng._h_apply_decision({"block": "A-01", "decision": "resume"})
    ok("ADD resume with no worker and no gate re-arms the block (ordinary redispatch)",
       any(w.get("block") == "A-01" for w in eng.st.workers),
       f"workers={eng.st.workers}")


def _live_idle_runner():
    """Monkeypatch the runner store to a LIVE idle runner whose idle-poll keeps its
    record fresh (delta small, record advancing) — the tron-19/20 signature that made
    the 01-15 `delta > ping*60` clock structurally unable to fire."""
    import jobs
    # `dir` points nowhere: jobs.release's .stop write fails quietly (OSError swallowed),
    # exactly like releasing a worker whose store dir was already reaped.
    rec = {"state": "idle", "turns": 1, "dir": "/nonexistent/tron-test-worker"}
    orig = (jobs.index, jobs.is_alive, jobs.find, jobs.activity_signals)
    jobs.index = lambda: {}
    jobs.is_alive = lambda w, idx=None: True
    jobs.find = lambda w, idx=None: rec
    jobs.activity_signals = lambda w, since_iso=None, idx=None: {
        "last_activity_delta_s": 5, "record_advanced": True}

    def restore():
        (jobs.index, jobs.is_alive, jobs.find, jobs.activity_signals) = orig
    return restore


def t_sweep_live_idle_done_gateless_releases_within_window():
    ctx, _ = build(blocks=[("A-01", "✅", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.st.live_config["worker_count"] = 1
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "s1", "status": "idle"})
    ok("setup: the zombie starves dispatch (0 free slots)", eng._free_slots() == 0)
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    restore = _live_idle_runner()
    try:
        eng._tq = []
        eng._sweep()
        ok("ADD arm (a) never misfires instantly (clock armed, worker held over)",
           any(x.get("id") == "ENG-A-01" for x in eng.st.workers))
        clock["t"] += PING_WINDOW_S
        eng._sweep()
        ok("ADD arm (a): live idle runner + block done + no gate -> RELEASED within one "
           "window even though the idle-poll keeps its record fresh",
           not any(x.get("id") == "ENG-A-01" for x in eng.st.workers),
           f"workers={eng.st.workers}")
        rel = [e for e in _releases(eng) if e.get("actor") == "ENG-A-01"]
        ok("ADD arm (a) release is event-logged", bool(rel))
        ok("ADD arm (a) frees the slot (dispatch no longer starved)",
           eng._free_slots() == 1)
        ok("ADD arm (a) pulses the switchboard (dispatch/session-end re-evaluates)",
           any(t == "pulse" for t, _ in eng._tq), f"tq={eng._tq}")
    finally:
        restore()
        eng.dry = True


def t_sweep_live_idle_open_gateless_escalates_within_window():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.st.live_config["worker_count"] = 1
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "s1", "status": "idle"})
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    restore = _live_idle_runner()
    try:
        eng._tq = []
        eng._sweep()
        ok("ADD arm (b) never misfires instantly", "A-01" not in eng.st.blocked)
        clock["t"] += PING_WINDOW_S
        eng._sweep()
        raised = [t for t, _ in eng._tq if t.startswith("wall:raised:")]
        ok("ADD arm (b): live idle runner + open block + no gate (mutual wait) -> "
           "escalates within one window despite fresh idle-poll signals",
           raised == ["wall:raised:A-01"], f"tq={eng._tq}")
        eng._drain_triggers()
        hit = next((f for f in _failures(eng) if f.get("code") == "gate-orphaned"), None)
        ok("ADD arm (b) escalation is the existing gate-orphaned code",
           hit is not None and "ENG-A-01" in hit.get("cause", ""), f"fails={_failures(eng)}")
        w = next(x for x in eng.st.workers if x["id"] == "ENG-A-01")
        ok("ADD arm (b) holds the worker (walled) — the slot is freed for dispatch",
           w.get("status") == "walled" and eng._free_slots() == 1)
    finally:
        restore()
        eng.dry = True


def t_sweep_dead_runner_no_record_releases_and_redispatches():
    # The FIRST addendum's shape (and tron-17's): a pool entry whose runner record is
    # MISSING entirely. jobs.is_alive reads a missing record as dead -> worker:stalled ->
    # release (event) + redispatch. Pinned end-to-end so the "no runner record" arm can
    # never regress into a silent wait either.
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.st.live_config["worker_count"] = 1
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "s1", "status": "idle"})
    eng._spawn = lambda wid, tpl, role, block=None, rtype=None: ("s-new", "short")
    ok("setup: the zombie starves dispatch", eng._free_slots() == 0)
    eng._tq = []
    eng._sweep()          # the empty workers dir IS the missing record — no monkeypatch
    ok("ADD no-runner-record -> worker:stalled on the very next sweep",
       any(t == "worker:stalled" for t, _ in eng._tq), f"tq={eng._tq}")
    eng._drain_triggers()
    rel = [e for e in _releases(eng) if e.get("actor") == "ENG-A-01"
           and e.get("payload", {}).get("reason") == "stall-recover"]
    ok("ADD the dead entry is released (event-logged, stall-recover)", bool(rel))
    ok("ADD dispatch resumes — the block is re-armed on a fresh worker",
       any(w.get("block") == "A-01" and w.get("session_id") == "s-new"
           for w in eng.st.workers), f"workers={eng.st.workers}")
    eng.dry = True


# ── T4 (AC-1): wind-down never idles past the window — it ends or escalates ──
def t_winddown_stranded_gate_resolves_and_settles():
    ctx, _ = build(blocks=[("A-01", "✅", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    ok("setup: the only block is already done", eng.st.row("A-01")["status"] == "done")
    eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})   # workerless from the start
    orig_land = trunk.land_docs
    trunk.land_docs = lambda *a, **k: ("non-ff", "trunk moved under the parked paperwork")
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    try:
        ok("T4 a stranded workerless gate blocks session end (the live-lock's own trigger)",
           not eng._all_settled())
        eng._sweep()
        ok("T4 still parked before the silence window elapses",
           "A-01" in eng.st.gate and not eng._all_settled())
        clock["t"] += PING_WINDOW_S
        eng._sweep()
        ok("T4 the stranded gate resolves within one window (never idles past it)",
           "A-01" not in eng.st.gate)
        ok("T4 wind-down now agrees — nothing left in flight, session settles",
           eng._all_settled())
    finally:
        trunk.land_docs = orig_land


def main():
    for t in (
        t_purge_done_gate_confirm_closes_on_evidence,
        t_purge_not_done_gate_escalates_gate_orphaned,
        t_resume_missing_worker_confirm_closes_done_gate,
        t_resume_missing_worker_not_done_escalates,
        t_sweep_workerless_not_done_gate_escalates_within_window,
        t_sweep_never_misreads_a_bound_worker_as_orphaned,
        t_sweep_never_misreads_a_review_gate_as_orphaned,
        t_sweep_spares_a_violation_wall_already_parked,
        t_empty_trunk_read_never_regresses_gate_state,
        t_empty_trunk_read_recovers_next_good_tick,
        t_resume_empty_queue_open_gateless_pings_worker,
        t_resume_empty_queue_gate_open_resends_stage_prompt,
        t_resume_empty_queue_done_gateless_releases_and_frees_slot,
        t_resume_no_worker_no_gate_rearms_the_block,
        t_sweep_live_idle_done_gateless_releases_within_window,
        t_sweep_live_idle_open_gateless_escalates_within_window,
        t_sweep_dead_runner_no_record_releases_and_redispatches,
        t_winddown_stranded_gate_resolves_and_settles,
    ):
        t()

    fails = [(n, d) for n, c, d in _results if not c]
    print(f"block_01_16_test: {len(_results)} checks, {len(fails)} failed")
    for n, d in fails:
        print(f"  FAIL: {n}" + (f" ({d})" if d else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
