"""tron07_test — regressions for the tron-07 campaign wall set (W1–W8) and the co-signed
review-cycle hardening (S-1..S-5, A-1/A-3/A-4, R-2..R-5).

Five live acceptance runs (tron-07..tron-11, block 02-02-02) each failed one layer deeper;
every wall and every co-signed consolidation is pinned here, deterministic and token-free
(dry-mode engine over sentry_test's builders; monkeypatched git predicates and a fake
wall-clock where the defect is about how the engine *reads* them):

  W1     monotonic DONE gate — a tick recompute at stage `trunk` HOLDS; only the accepted
         report advances to record.
  W2/A-3 single-use, SHA-PINNED merge grant — consumed by the merge it authorized; a moved
         tip voids it and re-parks naming the new tip; a non-ff retry keeps it.
  W3/A-1 block refs resolve sender-first (the assignment is authoritative), text
         canonicalizes exact-then-unique-prefix; unknown ids never gate.
  W4     every worker render goes through emit() (lint L21 pins the class).
  W6     close discipline — the record receipt is never a confirmation; close pacing is
         idle-keyed; every slot-freeing path pulses.
  S-1    ONE wall-clock pacing law (idle_since/close_idle_since vs knob x wake ceiling) —
         tick bursts can't cap a worker, starved timers can't blind detection (R-1).
  W8/A-4 the sweep honors the runner's own declared turn deadline; past it (presumed
         suspended) it escalates and hard-kills after a grace (R-2(ii), that path only).
  R-2(i) off-roster (zombie) reports are quarantined at the drain.
  rider4 _admit is the ONLY admission checkpoint (source-asserted).

Run: python3 engine/tron07_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import trunk            # noqa: E402
import jobs             # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _eng(blocks=None, block="A-01"):
    ctx, repo = build(blocks=blocks)
    eng = Engine(ctx)
    started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _capture(eng):
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
                sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


# ── W1: the DONE ladder is monotonic at trunk ──
def t_gate_holds_at_trunk():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})
    sent = _capture(eng)
    # The tron-07 condition: branch exists, tip NOT on trunk (post-merge doc commit).
    orig_bm, orig_be = trunk.branch_merged, trunk.branch_exists
    trunk.branch_merged = lambda *a, **k: False
    trunk.branch_exists = lambda *a, **k: True
    try:
        eng._drive_gate("A-01", g)                      # plain tick, no report
        ok("W1 tick at trunk holds (never regresses to local)", g.get("stage") == "trunk",
           f"stage={g.get('stage')}")
        ok("W1 no duplicate DONE-LOCAL order on the hold",
           not any(t == "gate.local" for t, _ in sent), f"sent={sent}")
        # The accepted trunk report still advances — the hold is not a dead-end.
        eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
        ok("W1 accepted trunk report still advances to record", g.get("stage") == "record")
    finally:
        trunk.branch_merged, trunk.branch_exists = orig_bm, orig_be


# ── W2: one approval = one executed merge ──
def t_merge_approval_single_use():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                        "approved_merge": True})
    orig_be, orig_ff = trunk.branch_exists, trunk.merge_ff_only
    trunk.branch_exists = lambda *a, **k: True
    trunk.merge_ff_only = lambda *a, **k: (True, "")
    try:
        eng._drive_gate("A-01", g)
        ok("W2 executed ff-merge advances to trunk", g.get("stage") == "trunk")
        ok("W2 executed ff-merge consumes the approval", "approved_merge" not in g,
           f"g={g}")
        # A regressed/duplicate pass can never ride the spent grant into a second merge:
        # the merge step now re-parks (ASK) instead of silently merging again.
        # Non-ff retry: the SAME unexecuted merge keeps its grant.
        eng2 = _eng()
        g2 = eng2.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                              "approved_merge": True})
        trunk.merge_ff_only = lambda *a, **k: (False, "non-ff")
        eng2._drive_gate("A-01", g2)
        ok("W2 non-ff retry keeps the grant (merge never executed)",
           g2.get("approved_merge") is True and g2.get("stage") == "local",
           f"g2={g2}")
    finally:
        trunk.branch_exists, trunk.merge_ff_only = orig_be, orig_ff


# ── W3: block-ref canonicalization + no phantom gates ──
def t_block_ref_resolution():
    eng = _eng(blocks=[("01-02-logic", "🔄", "none"), ("01-03-ui", "📋", "none")],
               block="01-02-logic")
    ok("W3 exact id resolves to itself",
       eng._resolve_block_ref("01-02-logic") == "01-02-logic")
    ok("W3 unique prefix resolves to the canon id",
       eng._resolve_block_ref("01-02") == "01-02-logic")
    ok("W3 ambiguous prefix resolves to nothing",
       eng._resolve_block_ref("01-0") is None)
    ok("W3 unknown ref resolves to nothing",
       eng._resolve_block_ref("99-99") is None)
    # _ingest -> _admit canonicalizes the slot before the trigger fires (S-2-lite: the ONE
    # admission checkpoint — handlers carry no residual re-checks, rider 4).
    eng._tq = []
    eng._ingest("worker.done", {"block": "01-02"}, {"id": "ENG-01-02-logic"})
    done = [(t, sl) for t, sl in eng._tq if t == "block:next:done"]
    ok("W3 _ingest fires the trigger with the canonical id",
       done and done[0][1].get("block") == "01-02-logic", f"tq={eng._tq}")
    # An id the canon has no row for never opens a gate (refused at admission).
    eng._tq = []
    eng._ingest("worker.done", {"block": "zz-99"}, {"id": "GHOST"})
    ok("W3 unknown block id refused at admission (no trigger)",
       not any(t == "block:next:done" for t, _ in eng._tq), f"tq={eng._tq}")
    eng._h_worker_done({"block": "01-02-logic"})
    ok("W3 known block id still gates", "01-02-logic" in eng.st.gate)
    # A-1: the sender's ASSIGNED block is authoritative over a divergent text ref.
    eng2 = _eng(blocks=[("01-02-logic", "🔄", "none"), ("01-03-ui", "📋", "none")],
                block="01-02-logic")
    eng2._tq = []
    eng2._ingest("worker.done", {"block": "01-03-ui"}, {"id": "ENG-01-02-logic"})
    done = [(t, sl) for t, sl in eng2._tq if t == "block:next:done"]
    ok("A-1 sender's assignment beats a divergent text ref",
       done and done[0][1].get("block") == "01-02-logic", f"tq={eng2._tq}")
    # A-1: an unresolvable ref from an assigned sender defaults to the assignment.
    eng2._tq = []
    eng2._ingest("worker.done", {"block": "01-0"}, {"id": "ENG-01-02-logic"})
    done = [(t, sl) for t, sl in eng2._tq if t == "block:next:done"]
    ok("A-1 ambiguous ref defaults to the sender's assignment",
       done and done[0][1].get("block") == "01-02-logic", f"tq={eng2._tq}")


# ── W6: the close stage — receipt vs confirmation, idle-keyed nudges, pulse on release ──
def t_close_stage_discipline():
    # W6a: the record receipt routes to its own handler and is never a close confirmation.
    eng = _eng()
    row = eng.st.row("A-01")
    row["status"] = "done"
    g = eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    confirmed = []
    orig_cc = eng._confirm_close
    eng._confirm_close = lambda b, gg: confirmed.append(b)
    try:
        eng._tq = []
        eng._ingest("worker.recorded", {"block": "A-01"}, {"id": "ENG-A-01"})
        ok("W6a record receipt at CLOSE refused at admission (never a confirmation)",
           not confirmed and not any(t == "block:next:recorded" for t, _ in eng._tq),
           f"confirmed={confirmed} tq={eng._tq}")
        # ...but the receipt at stage RECORD still drives record -> close.
        eng2 = _eng()
        eng2.st.row("A-01")["status"] = "done"
        g2 = eng2.st.gate.setdefault("A-01", {"stage": "record", "pr": None,
                                              "record_checked": True})
        eng2._h_worker_recorded({"block": "A-01"})
        ok("W6a record receipt at RECORD advances to close", g2.get("stage") == "close")
        # routing carries the split: worker.recorded at stage record fires its own row.
        eng2b = _eng()
        eng2b.st.row("A-01")["status"] = "done"
        eng2b.st.gate["A-01"] = {"stage": "record", "pr": None}
        eng2b._tq = []
        eng2b._ingest("worker.recorded", {"block": "A-01"}, {"id": "ENG-A-01"})
        ok("W6a worker.recorded routes to block:next:recorded",
           any(t == "block:next:recorded" for t, _ in eng2b._tq), f"tq={eng2b._tq}")
    finally:
        eng._confirm_close = orig_cc

    # W6b + S-1: a worker mid-close-out (runner working) never accrues; an idle close
    # escalates (F-4, 01-27: routed through _gate_giveup — a NAMED wall, never the old
    # silent force-release; see block_01_27_test.py for the full AC-6 escalation proof)
    # only after gate_close_cap x ceiling of continuous WALL-CLOCK idle.
    eng3 = _eng()
    eng3.st.row("A-01")["status"] = "done"
    g3 = eng3.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    clock = {"t": 1000.0}
    eng3._now_s = lambda: clock["t"]
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda wid, idx=None: False        # working
    try:
        for _ in range(5):
            clock["t"] += eng3._pace("gate_close_cap", 3)
            eng3._drive_close("A-01", g3, "ENG-A-01")
        ok("W6b working runner never accrues close idle (no escalation)",
           g3.get("close_idle_since") is None and "A-01" in eng3.st.gate, f"g={g3}")
        jobs.runner_idle = lambda wid, idx=None: True     # idle -> wall-clock to the cap
        eng3._tq = []
        eng3._drive_close("A-01", g3, "ENG-A-01")          # anchor close_idle_since
        clock["t"] += eng3._pace("gate_close_cap", 3) + 1
        eng3._drive_close("A-01", eng3.st.gate["A-01"], "ENG-A-01")
        ok("W6b idle close escalates past the wall-clock cap (gate dropped)",
           "A-01" not in eng3.st.gate)
        # F-4 (01-27): a stuck close-out now PAGES a named wall — never a silent
        # force-release. W6c's old direct pulse is gone (nothing is released here
        # anymore; _h_escalate — not this cap — owns the pulse, once the wall drains).
        ok("F-4 the stuck close raises a NAMED wall with its own distinct case-kind "
           "(never the generic 'wall')",
           any(t == "wall:raised:A-01" and s.get("code") == "gate-close-idle-cap"
               for t, s in eng3._tq),
           f"tq={eng3._tq}")
    finally:
        jobs.runner_idle = orig_idle


# ── W7b/S-1: pacing is WALL-CLOCK — tick bursts (any trigger source) can't cap a worker ──
def t_tick_bursts_never_cap():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda *a, **k: True                 # idle runner
    try:
        for _ in range(25):                                 # a 25-tick burst in one instant
            eng._drive_gate("A-01", g)
        ok("W7b/S-1 a tick burst at one instant never caps (idle is wall-clock)",
           "A-01" in eng.st.gate and g.get("stage") == "local", f"g={g}")
        clock["t"] += eng._pace("gate_idle_cap", 3) + 1     # real time passing DOES
        eng._drive_gate("A-01", g)
        ok("W7b/S-1 real elapsed idle still escalates", "A-01" not in eng.st.gate)
        # and the close stage obeys the same law
        eng2 = _eng()
        eng2.st.row("A-01")["status"] = "done"
        g2 = eng2.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
        clock2 = {"t": 1000.0}
        eng2._now_s = lambda: clock2["t"]
        for _ in range(25):
            eng2._drive_close("A-01", g2, "ENG-A-01")
        ok("W7b/S-1 close-stage burst at one instant never force-releases",
           "A-01" in eng2.st.gate, f"g2={g2}")
    finally:
        jobs.runner_idle = orig_idle


# ── W8 + A-4 + R-2(ii): the sweep honors the runner's OWN deadline; kill after grace ──
def t_sweep_spares_working_turns():
    import fsm as fsm_mod

    def sweep_with(rstate, delta, alive=True, deadline=None, now=10_000.0, kill_at=None):
        eng = _eng()
        eng.dry = False
        eng._now_s = lambda: now
        w = eng.st.workers[0]
        w["session_id"], w["status"], w["pinged_at"] = "s1", "working", "old"
        if kill_at is not None:
            w["kill_at"] = kill_at
        rec = {"state": rstate, "turns": 1}
        if deadline is not None:
            rec["deadline"] = deadline
        killed = []
        orig = (jobs.index, jobs.is_alive, jobs.find,
                jobs.activity_signals, jobs.has_positive_activity, jobs.kill_hard)
        jobs.index = lambda: {}
        jobs.is_alive = lambda wid, idx=None: alive
        jobs.find = lambda wid, idx=None: rec
        jobs.activity_signals = lambda wid, since_iso=None, idx=None: {
            "last_activity_delta_s": delta}
        jobs.has_positive_activity = lambda sig: False
        jobs.kill_hard = lambda wid, idx=None: killed.append(wid)
        eng._tq = []
        try:
            eng._sweep()
        finally:
            (jobs.index, jobs.is_alive, jobs.find,
             jobs.activity_signals, jobs.has_positive_activity, jobs.kill_hard) = orig
            eng.dry = True
        stalled = any(t == "worker:stalled" for t, _ in eng._tq)
        return stalled, w, killed

    # A-4: the runner's declared deadline governs — young turn exempt.
    stalled, w, killed = sweep_with("working", 600, deadline=10_500.0)
    ok("W8/A-4 working turn inside its own deadline is never stalled",
       not stalled and "pinged_at" not in w and not killed,
       f"stalled={stalled} killed={killed}")
    # Past the declared deadline (+grace): presumed suspended -> escalate, arm the kill.
    stalled, w, killed = sweep_with("working", 600, deadline=9_000.0)
    ok("W8/A-4 working past its own deadline escalates + arms the kill grace",
       stalled and w.get("kill_at") and not killed, f"w={w.get('kill_at')} killed={killed}")
    # Grace elapsed -> SIGKILL (R-2(ii): this path only).
    stalled, w, killed = sweep_with("working", 600, deadline=9_000.0, kill_at=9_500.0)
    ok("R-2(ii) kill grace elapsed -> hard kill", killed == [w.get("id")], f"killed={killed}")
    # No declared deadline (pre-A-4 record): env-ceiling fallback still protects.
    stalled, _, _ = sweep_with("working", 600)
    ok("W8 fallback: young turn (env ceiling) exempt without a declared deadline", not stalled)
    stalled, _, _ = sweep_with("working", fsm_mod.TURN_CEILING_S + 200)
    ok("W8 fallback: past the env ceiling escalates", stalled)
    # Crashed runner with a stale working file -> the dead path, untouched.
    stalled, _, _ = sweep_with("working", 600, alive=False)
    ok("W8 dead runner with a stale working state still hits the stalled path", stalled)
    stalled, _, _ = sweep_with("idle", 600)
    ok("W8 idle silence past the escalate threshold still stalls", stalled)


# ── R-2(i): off-roster (zombie) reports are quarantined at the drain ──
def t_zombie_reports_quarantined():
    eng = _eng(blocks=[("A-01", "✅", "none")])          # done ON DISK — tick refresh re-reads it
    eng.st.gate["A-01"] = {"stage": "close", "pr": None}
    import util as _u
    _u.append_jsonl(eng.ctx.worker_inbox,
                    {"text": "clean A-01: all torn down", "sender": {"kind": "worker", "id": "ENG-GHOST"}})
    classified = []
    eng._classify = lambda m: classified.append(m) or ("worker.done", {"block": "A-01"})
    eng.tick()
    ok("R-2(i) off-roster report never reaches classify (quarantined)",
       not classified, f"classified={classified}")
    ok("R-2(i) quarantine leaves the gate untouched",
       eng.st.gate.get("A-01", {}).get("stage") == "close")
    # the same report from the LIVE worker still lands
    _u.append_jsonl(eng.ctx.worker_inbox,
                    {"text": "clean A-01: all torn down", "sender": {"kind": "worker", "id": "ENG-A-01"}})
    eng.tick()
    ok("R-2(i) on-roster report still classifies", bool(classified), f"n={len(classified)}")


# ── A-3: the merge grant binds the sha the operator saw ──
def t_grant_binds_sha():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                        "approved_merge": True, "case_tip": "aaa1111"})
    orig = (trunk.branch_exists, trunk.merge_ff_only, trunk.tip_sha)
    trunk.branch_exists = lambda *a, **k: True
    trunk.merge_ff_only = lambda *a, **k: (True, "")
    trunk.tip_sha = lambda *a, **k: "bbb2222"            # tip moved since the park
    try:
        eng.st.approvals["merge"] = "ASK"
        eng._drive_gate("A-01", g)
        ok("A-3 moved tip voids the grant (no merge executed)",
           g.get("stage") == "local" and not g.get("approved_merge"), f"g={g}")
        ok("A-3 re-park names the new tip (rider 2)",
           any("bbb2222"[:7] in (c.get("detail") or "") for c in eng.st.pending_cases.values()),
           f"cases={eng.st.pending_cases}")
        # unchanged tip: the grant executes exactly once
        eng2 = _eng()
        g2 = eng2.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                              "approved_merge": True, "case_tip": "aaa1111"})
        trunk.tip_sha = lambda *a, **k: "aaa1111"
        eng2._drive_gate("A-01", g2)
        ok("A-3 unmoved tip executes the grant", g2.get("stage") == "trunk", f"g2={g2}")
    finally:
        trunk.branch_exists, trunk.merge_ff_only, trunk.tip_sha = orig


# ── S-2-lite rider 4: _admit is the ONLY admission checkpoint ──
def t_admit_is_sole_checkpoint():
    import inspect
    import fsm as fsm_mod
    done_src = inspect.getsource(fsm_mod.Engine._h_worker_done)
    rec_src = inspect.getsource(fsm_mod.Engine._h_worker_recorded)
    ok("rider-4 _h_worker_done carries no residual prefix guard",
       "startswith" not in done_src and "unclassified(" not in done_src)
    ok("rider-4 _h_worker_recorded carries no residual admission",
       "unclassified(" not in rec_src and "_resolve_block_ref" not in rec_src)
    # the close clean-prefix now enforces at admission, reading the registry (S-4)
    eng = _eng()
    eng.st.row("A-01")["status"] = "done"
    eng.st.gate["A-01"] = {"stage": "close", "pr": None}
    eng._tq = []
    eng._ingest("worker.done", {"block": "A-01", "_raw": "all torn down, we good"},
                {"id": "ENG-A-01"})
    ok("rider-4 non-clean-prefixed close reply refused at admission",
       not any(t == "block:next:done" for t, _ in eng._tq), f"tq={eng._tq}")
    eng._ingest("worker.done", {"block": "A-01", "_raw": "clean A-01: torn down"},
                {"id": "ENG-A-01"})
    ok("rider-4 clean-prefixed close reply admitted",
       any(t == "block:next:done" for t, _ in eng._tq), f"tq={eng._tq}")


# ── W4: release + end-session render through emit() (universal slots injected) ──
def t_release_renders_clean():
    eng = _eng()
    line = eng.emit("close.worker", {"worker_id": "ENG-A-01"}, worker_id="ENG-A-01")
    ok("W4 close.worker renders with the injected report slot",
       "report.sh" in (line or ""), f"line={line!r}")
    # The non-dry paths that crashed: _release_worker (reviewer hand-back) and
    # _end_session (tron stop --force). Run them for real minus process side-effects.
    eng.dry = False
    orig_send, orig_rel = eng._to_worker, jobs.release
    delivered = []
    eng._to_worker = lambda wid, text, kind: delivered.append((wid, kind, text))
    jobs.release = lambda wid: None
    try:
        w = eng.st.workers[0]
        eng._release_worker(w, notify=True, reason="review-complete")
        ok("W4 _release_worker(notify=True) renders + delivers without raising",
           any(k == "close.worker" and "report.sh" in t for _, k, t in delivered),
           f"delivered={[(w_, k) for w_, k, _ in delivered]}")
        eng.st.workers.append({"id": "ENG-B", "role": "engineer", "block": "A-02",
                               "session_id": "dry", "status": "working"})
        eng._end_session()
        ok("W4 _end_session renders + delivers without raising",
           any(w_ == "ENG-B" and k == "close.worker" for w_, k, _ in delivered),
           f"delivered={[(w_, k) for w_, k, _ in delivered]}")
    finally:
        eng._to_worker, jobs.release = orig_send, orig_rel
        eng.dry = True


def main():
    for t in (t_gate_holds_at_trunk, t_merge_approval_single_use,
              t_block_ref_resolution, t_close_stage_discipline,
              t_tick_bursts_never_cap, t_sweep_spares_working_turns,
              t_zombie_reports_quarantined, t_grant_binds_sha, t_admit_is_sole_checkpoint,
              t_release_renders_clean):
        t()
    fails = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n + (f"  [{d}]" if (d and not c) else ""))
    print(f"{len(_results) - len(fails)}/{len(_results)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
