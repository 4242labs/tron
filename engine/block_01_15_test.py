"""block_01_15_test — regressions for the 01-15 close-integrity set (tron-16 defects
D-16-1/D-16-2 + residues).

  T1  held-sender verbs (D-16-1 seam 1): a message from a WALLED sender never has its
      verb dropped or acted on — it is queued whole on the worker's own record (manifest
      state) and replayed in arrival order the instant the operator `resume`s. Modifiers
      (--branch) still register immediately, unaffected by hold state (unit-level, in
      _classify — not re-tested here; unchanged).
  T2  wall path never orphans the gate (D-16-1 seam 2): raising OR settling a wall never
      pops a block's gate directly — gate lifecycle stays exclusively _confirm_close's
      (release) and _gate_giveup's (escalation) to own.
  T3  idle-bound orphan (D-16-1 seam 3): an engineer idle, bound to a block, whose gate is
      orphaned (block already done, or no gate at all) escalates NAMED (`gate-orphaned`)
      after one silence window — never silent, even though the runner's own idle-poll
      keeps it looking "alive" to the ordinary stall check.
  T4  hold/un-hold symmetry (D-16-2): the engine-raised gate-stuck path (_gate_giveup)
      holds and un-holds through the SAME primitive pair as a worker-declared wall.
  T5  merge_ff_only fails closed on a missing trunk branch (residue a) — never a silent
      merge onto whatever HEAD happens to be.
  T6  a close-time `violation` wall (residue b): operator `approve` lands the named range
      (ordered merge, same content pin as a merge ASK, same lander cleanup after); `resume`
      lets the worker resolve its own branch; `abandon` is unchanged.

FSM-level cases are dry (TRON_DRY, sentry_test's fixture builders — same convention as
block_01_13/14_test.py). T5/T6's git primitives are proven against REAL throwaway repos
(block_01_14_test's _mkrepo/_git convention) — git reads by design.

Run: python3 engine/block_01_15_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import util             # noqa: E402
import jobs             # noqa: E402
import trunk            # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started, events  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _events(eng):
    return util.read_jsonl(eng.ctx.event_log)


def _eng_with_gate(block="A-01", stage="close", status="🔄"):
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx); started(eng)
    if stage == "close":
        eng.st.row(block)["status"] = "done"        # CLOSE only exists once ✅ landed
    eng.st.workers.append({"id": f"ENG-{block}", "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    g = eng.st.gate.setdefault(block, {"stage": stage, "pr": None})
    return eng, g


def _wall_case(eng, block, wid):
    """Raise a worker-declared wall (T2/T4's unchanged worker-side raiser) and return the
    pending case id it parked."""
    eng._h_escalate({"block": block, "worker_id": wid, "detail": "flaky ci"})
    return next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")


# ── T1 (AC-1): a held sender's verb is queued whole, replayed in order on resume ──
def t_held_verb_queued_and_replayed_on_resume():
    eng, g = _eng_with_gate()
    orig_land, orig_clean = trunk.land_docs, trunk.replica_clean
    trunk.land_docs = lambda *a, **k: ("landed", "0 file(s)")
    trunk.replica_clean = lambda *a, **k: (True, "")
    try:
        cid = _wall_case(eng, "A-01", "ENG-A-01")
        w = next(x for x in eng.st.workers if x["id"] == "ENG-A-01")
        ok("T1 setup: the wall holds the sender (walled)", w.get("status") == "walled")

        # The engineer's close clean-confirmation arrives WHILE held.
        eng._ingest("worker.done", {"block": "A-01", "clean_confirm": True, "_raw": "clean"},
                    {"kind": "worker", "id": "ENG-A-01"})
        ok("T1 the held verb is queued, never processed",
           w.get("held_verbs") == [{"tag": "worker.done",
                                    "slots": {"block": "A-01", "clean_confirm": True,
                                              "_raw": "clean"}}],
           f"held_verbs={w.get('held_verbs')}")
        ok("T1 the gate is untouched while the verb sits queued",
           "A-01" in eng.st.gate and eng.st.gate["A-01"].get("stage") == "close")

        # Resume un-holds AND replays the queue in arrival order.
        eng._h_apply_decision({"case": cid, "decision": "resume"})
        eng._drain_triggers()          # the replayed trigger lands in _tq; drain it (as
                                        # _drain_triggers's own loop would in production)
        ok("T1 resume replays the queued verb: the close confirms and releases",
           "A-01" not in eng.st.gate
           and not any(x["id"] == "ENG-A-01" for x in eng.st.workers),
           f"gate={eng.st.gate} workers={eng.st.workers}")
        ok("T1 the queue is drained (nothing left pending)", not w.get("held_verbs"))
    finally:
        trunk.land_docs, trunk.replica_clean = orig_land, orig_clean


def t_abandon_discards_the_held_queue():
    eng, g = _eng_with_gate()
    cid = _wall_case(eng, "A-01", "ENG-A-01")
    w = next(x for x in eng.st.workers if x["id"] == "ENG-A-01")
    eng._ingest("worker.done", {"block": "A-01", "clean_confirm": True, "_raw": "clean"},
                {"kind": "worker", "id": "ENG-A-01"})
    ok("T1 setup: a verb is queued behind the wall", w.get("held_verbs"))
    eng._h_apply_decision({"case": cid, "decision": "abandon"})
    ok("T1 abandon discards the queue whole (the held worker record itself is released)",
       not any(x["id"] == "ENG-A-01" for x in eng.st.workers))


# ── T2 (AC-2): the wall path never pops a block's gate, raise or settle ──
def t_wall_raise_leaves_gate_intact():
    eng, g = _eng_with_gate(stage="close")
    eng._h_escalate({"block": "A-01", "worker_id": "ENG-A-01", "detail": "stuck"})
    ok("T2 raising a wall leaves the gate intact",
       "A-01" in eng.st.gate and eng.st.gate["A-01"].get("stage") == "close",
       f"gate={eng.st.gate}")


def t_wall_resume_settle_leaves_gate_intact():
    eng, g = _eng_with_gate(stage="close")
    cid = _wall_case(eng, "A-01", "ENG-A-01")
    eng._h_apply_decision({"case": cid, "decision": "resume"})
    ok("T2 settling (resume) a wall leaves the gate intact",
       "A-01" in eng.st.gate and eng.st.gate["A-01"].get("stage") == "close",
       f"gate={eng.st.gate}")


def t_wall_abandon_settle_does_not_pop_the_gate_directly():
    eng, g = _eng_with_gate(block="A-02", stage="close")
    cid = _wall_case(eng, "A-02", "ENG-A-02")
    eng._h_apply_decision({"case": cid, "decision": "abandon"})
    ok("T2 abandon does not pop the gate directly (never the settle code's own doing)",
       "A-02" in eng.st.gate, f"gate={eng.st.gate}")
    eng._drive_gates()             # the DONE ladder's own dropped-block check, next pass
    ok("T2 the gate clears on the ladder's next pass instead (still not the settle path)",
       "A-02" not in eng.st.gate)


# ── T3 (AC-3): idle-bound-with-an-orphaned-gate escalates NAMED, never silently ──
def t_idle_bound_orphan_escalates_gate_orphaned_no_gate():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "s1", "status": "idle"})
    rec = {"state": "idle", "turns": 1}
    orig = (jobs.index, jobs.is_alive, jobs.find,
            jobs.activity_signals, jobs.has_positive_activity)
    jobs.index = lambda: {}
    jobs.is_alive = lambda wid, idx=None: True
    jobs.find = lambda wid, idx=None: rec
    jobs.activity_signals = lambda wid, since_iso=None, idx=None: {
        "last_activity_delta_s": 900}
    # The runner's own idle-poll keeps this true — the exact class the ordinary
    # silent-stall check (delta > esc*60) never reaches (tron-16's escaped net).
    jobs.has_positive_activity = lambda sig: True
    try:
        eng._tq = []
        eng._sweep()
        raised = [t for t, s in eng._tq if t.startswith("wall:raised:")]
        ok("T3 no gate at all -> idle-bound orphan escalates a wall",
           raised == ["wall:raised:A-01"], f"tq={eng._tq}")
        eng._drain_triggers()
        fails = [e for e in _events(eng) if e.get("kind") == "failure"]
        hit = next((e for e in fails if e.get("code") == "gate-orphaned"), None)
        ok("T3 escalation is NAMED gate-orphaned (never a silent/generic stall)",
           hit is not None, f"fails={fails}")
        ok("T3 escalation names the worker id and the block",
           hit and "ENG-A-01" in hit.get("cause", "") and hit.get("block") == "A-01",
           f"hit={hit}")
        ok("T3 the worker is held, never left running unnoticed",
           next(w for w in eng.st.workers if w["id"] == "ENG-A-01").get("status") == "walled")
    finally:
        (jobs.index, jobs.is_alive, jobs.find,
         jobs.activity_signals, jobs.has_positive_activity) = orig
        eng.dry = True


def t_idle_bound_orphan_escalates_gate_orphaned_block_done():
    eng, g = _eng_with_gate(stage="close")
    eng.dry = False
    del eng.st.gate["A-01"]                # simulate the gate having vanished (D-16-1)
    w = eng.st.workers[0]
    w["status"] = "idle"
    w["session_id"] = "s1"                 # a live (non-"dry") session for the sweep
    rec = {"state": "idle", "turns": 1}
    orig = (jobs.index, jobs.is_alive, jobs.find,
            jobs.activity_signals, jobs.has_positive_activity)
    jobs.index = lambda: {}
    jobs.is_alive = lambda wid, idx=None: True
    jobs.find = lambda wid, idx=None: rec
    jobs.activity_signals = lambda wid, since_iso=None, idx=None: {
        "last_activity_delta_s": 900}
    jobs.has_positive_activity = lambda sig: True
    try:
        eng._tq = []
        eng._sweep()
        ok("T3 block already done + no gate -> orphan escalates too",
           any(t == "wall:raised:A-01" for t, _ in eng._tq), f"tq={eng._tq}")
    finally:
        (jobs.index, jobs.is_alive, jobs.find,
         jobs.activity_signals, jobs.has_positive_activity) = orig
        eng.dry = True


def t_idle_bound_normal_wait_never_misfires():
    # Regression guard: an ordinary idle-between-turns engineer, still building (not
    # done, gate not yet opened) must NEVER misread as an orphan — only a normal wait.
    eng, g = _eng_with_gate(stage="local", status="🔄")
    del eng.st.gate["A-01"]                # no report yet -> genuinely no gate (normal)
    eng.dry = False
    w = eng.st.workers[0]
    w["status"] = "idle"
    w["session_id"] = "s1"                 # a live (non-"dry") session for the sweep
    rec = {"state": "idle", "turns": 1}
    orig = (jobs.index, jobs.is_alive, jobs.find,
            jobs.activity_signals, jobs.has_positive_activity)
    jobs.index = lambda: {}
    jobs.is_alive = lambda wid, idx=None: True
    jobs.find = lambda wid, idx=None: rec
    # Only just idle (under the silence window) — never orphaned this fast.
    jobs.activity_signals = lambda wid, since_iso=None, idx=None: {
        "last_activity_delta_s": 5}
    jobs.has_positive_activity = lambda sig: True
    try:
        eng._tq = []
        eng._sweep()
        ok("T3 a fresh idle engineer with no gate yet is never misread as orphaned",
           not eng._tq, f"tq={eng._tq}")
    finally:
        (jobs.index, jobs.is_alive, jobs.find,
         jobs.activity_signals, jobs.has_positive_activity) = orig
        eng.dry = True


# ── T4 (AC-4): engine-raised gate-stuck holds/un-holds through the SAME primitive ──
def t_engine_raised_hold_restores_on_resume():
    eng, g = _eng_with_gate(stage="trunk")
    w = eng.st.workers[0]
    eng._gate_giveup("A-01", g, "ENG-A-01", "worker idle 90s at trunk", "gate-idle-cap",
                     "check worker liveness; resume or reassign")
    eng._drain_triggers()          # the queued wall:raised trigger -> _h_escalate holds it
    ok("T4 engine-raised gate-stuck holds the worker (walled), same as a worker wall",
       w.get("status") == "walled" and w.get("held_status") == "working", f"w={w}")
    ok("T4 the escalation (the OTHER legitimate gate-pop owner) does clear the gate",
       "A-01" not in eng.st.gate)
    cid = next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")
    eng._h_apply_decision({"case": cid, "decision": "resume"})
    ok("T4 resume restores the pre-hold status via the shared _unhold_worker primitive",
       w.get("status") == "working" and "held_status" not in w, f"w={w}")
    ok("T4 resume returns the worker to work-selection (_pool)",
       any(x.get("id") == "ENG-A-01" for x in eng._pool()))


# ── T5 (AC-5): merge_ff_only fails closed on a missing trunk branch ──
def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _mkrepo(prefix):
    d = tempfile.mkdtemp(prefix=prefix)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    os.makedirs(os.path.join(d, "meta"))
    with open(os.path.join(d, "meta", "x.md"), "w") as fh:
        fh.write("base\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


def t_ff_merge_refuses_missing_trunk_branch():
    d = _mkrepo("tron-0115-notrunk-")
    _git(d, "checkout", "-qb", "feat/x")
    with open(os.path.join(d, "meta", "x.md"), "a") as fh:
        fh.write("more\n")
    _git(d, "commit", "-aqm", "work")
    _git(d, "branch", "-D", "main")            # the trunk branch itself is gone (boot-1)
    okm, err = trunk.merge_ff_only(d, "feat/x", "main")
    ok("T5 ff-merge refuses a missing trunk branch, never a silent merge onto HEAD",
       not okm and "does not exist" in err, f"okm={okm} err={err}")
    branch = _git(d, "rev-parse", "--abbrev-ref", "HEAD")[1]
    ok("T5 HEAD never silently moved (still on feat/x, nothing merged)", branch == "feat/x")
    code, detail = trunk.land_docs(d, "feat/x", ["meta/"], "main")
    ok("T5 land_docs surfaces the same fault as an error, never a fabricated non-ff",
       code == "error", f"{code}: {detail}")
    shutil.rmtree(d, ignore_errors=True)


def t_ff_merge_still_works_when_trunk_exists():
    # Regression guard: the new existence check must never block an ordinary landing.
    d = _mkrepo("tron-0115-normal-")
    _git(d, "branch", "feat/y")
    okm, err = trunk.merge_ff_only(d, "feat/y", "main")
    ok("T5 an ordinary ff-merge (trunk exists) still lands", okm, err)
    shutil.rmtree(d, ignore_errors=True)


# ── T6 (AC-6): a close-time violation wall — approve lands the named range ──
def t_violation_wall_approve_lands_the_range():
    d = _mkrepo("tron-0115-violation-")
    _git(d, "checkout", "-qb", "feat/A-01")
    with open(os.path.join(d, "src.py"), "w") as fh:      # non-paperwork content
        fh.write("code\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "oops, real code on the close branch")
    _git(d, "checkout", "-q", "main")

    eng, g = _eng_with_gate(stage="close")
    eng.dry = False                                    # real land_docs/merge_ff_only run
    eng.paths["root"] = d
    eng.paths["main_branch"] = "main"
    eng.st.branches["A-01"] = "feat/A-01"
    orig_replica = trunk.replica_clean
    trunk.replica_clean = lambda *a, **k: (True, "")
    try:
        eng._confirm_close("A-01", g)          # land_docs sees src.py -> "violation"
        eng._drain_triggers()                  # process the queued wall:raised trigger
        ok("T6 a close-time violation parks (never gate-gives-up outright)",
           "A-01" in eng.st.gate and g.get("violation_pending") is True, f"g={g}")
        cid = next(cid for cid, c in eng.st.pending_cases.items()
                   if c.get("kind") == "wall")
        ok("T6 the wall names the offending file", "src.py" in eng.st.pending_cases[cid]["detail"])

        eng._h_apply_decision({"case": cid, "decision": "approve"})
        ok("T6 approve lands the named range (ordered merge)",
           "A-01" not in eng.st.gate, f"gate={eng.st.gate}")
        ok("T6 the lander cleanup ran: the branch is gone",
           not trunk.branch_exists(d, "feat/A-01"))
        rc, out, _ = _git(d, "show", "main:src.py")
        ok("T6 the code actually landed on trunk", rc == 0 and out.strip() == "code")
        ok("T6 the engineer is released, same as an ordinary close", not eng.st.workers)
        ok("T6 landing recorded as a docs_landed event",
           any(e.get("type") == "docs_landed" for e in _events(eng)))
    finally:
        trunk.replica_clean = orig_replica
        eng.dry = True
        shutil.rmtree(d, ignore_errors=True)


def t_violation_wall_resume_lets_worker_resolve_its_own_branch():
    d = _mkrepo("tron-0115-violation-resume-")
    _git(d, "checkout", "-qb", "feat/A-01")
    with open(os.path.join(d, "src.py"), "w") as fh:
        fh.write("code\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "oops")
    _git(d, "checkout", "-q", "main")

    eng, g = _eng_with_gate(stage="close")
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["main_branch"] = "main"
    eng.st.branches["A-01"] = "feat/A-01"
    orig_replica = trunk.replica_clean
    trunk.replica_clean = lambda *a, **k: (True, "")
    try:
        eng._confirm_close("A-01", g)
        eng._drain_triggers()
        cid = next(cid for cid, c in eng.st.pending_cases.items()
                   if c.get("kind") == "wall")
        eng._h_apply_decision({"case": cid, "decision": "resume"})
        ok("T6 resume un-parks (worker resolves its own branch) and un-holds it",
           not g.get("violation_pending")
           and next(w for w in eng.st.workers if w["id"] == "ENG-A-01").get("status")
               == "working",
           f"g={g}")
        ok("T6 resume never lands anything itself — the branch is still there",
           trunk.branch_exists(d, "feat/A-01"))
    finally:
        trunk.replica_clean = orig_replica
        eng.dry = True
        shutil.rmtree(d, ignore_errors=True)


def t_violation_wall_abandon_unchanged():
    eng, g = _eng_with_gate(stage="close")
    orig_land = trunk.land_docs
    trunk.land_docs = lambda *a, **k: ("violation", "src/sneak.py")
    try:
        eng._confirm_close("A-01", g)
        eng._drain_triggers()
        cid = next(cid for cid, c in eng.st.pending_cases.items()
                   if c.get("kind") == "wall")
        eng._h_apply_decision({"case": cid, "decision": "abandon"})
        ok("T6 abandon on a violation wall drops the block as always",
           "A-01" in eng._dropped()
           and not any(w["id"] == "ENG-A-01" for w in eng.st.workers))
    finally:
        trunk.land_docs = orig_land


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
