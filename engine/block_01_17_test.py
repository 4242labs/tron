"""block_01_17_test — regressions for the 01-17 paperwork-landing robustness + wall
invariants set (tron-22/23/24 defect set).

  T1  the dominant wall class (tron-22/23/24, 5+ runs): every ordered/ff landing path
      shares ONE primitive, `trunk.merge_ff_only`.
      SUPERSEDED (block 01-32, ADR-0002 D1/D2): the auto-rebase-and-retry this T1 used to
      describe (on a first ff-refusal, rebase the branch onto trunk ONCE and retry) is
      RETIRED outright — TRON never rebases, conflict-free or not (a write-boundary
      violation). Every non-ff refusal now returns the plain detail, unconditionally; the
      two behavioral tests below are updated in place to the new contract, and the
      structural replacement (the worker's own rebase-before-close ritual resolves it, or
      an unfinishable rebase walls with content) lives in block_01_32_test.py's
      `clobber_dead` (AC-2).
  T2  D-22-1: a failed (or re-pinned) violation-land settle must never spend the case that
      is a `violation_pending` gate's ONLY reachable handle — `_land_violation_range`
      reports back whether it actually landed, and `_h_apply_decision` reopens the SAME
      case (decision back to None) on anything short of a full land, so the gate stays
      parked AND reachable by a fresh settle.
  T3  wall/hold invariants (tron-23), sweep-enforced after one silence window: (a) a
      `walled` worker whose case already carries a decision un-holds via the ordinary
      _unhold_worker + the 01-16 post-unhold nudge; (b) a `walled` worker with NO pending
      case gets one re-raised (the recorded detail, else the inconsistency named). Also
      covers the root-cause fix: `_hold_worker` no longer clobbers `held_status` on a
      SECOND hold of an already-walled worker (the tron-23 mechanism — a corrupted
      held_status of 'walled' made every later un-hold a no-op).
      SUPERSEDED (block 01-31, ADR-0002 D5): `_sweep_wall_invariant` (both arms above)
      is retired outright — `_close_case`/`_release_case_hold` now owns every worker-hold
      release by construction, so the drift these arms repaired can no longer occur. The
      three arm-specific behavioral tests below are replaced with one structural
      retirement proof; full new-mechanism depth lives in block_01_31_test.py. The
      root-cause `_hold_worker` fix is untouched by this and still tested as-is.

T1's real-git cases reuse the block_01_14_test/tron13_test `_mkrepo`/`_git` convention
(git reads by design). T2/T3 are FSM-level, dry (TRON_DRY, sentry_test's fixture
builders — same convention as block_01_14_test.py/block_01_16_test.py).

Run: python3 engine/block_01_17_test.py   (exit 0 = pass). No tokens, no network.
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
import trunk             # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _events(eng):
    return util.read_jsonl(eng.ctx.event_log)


def _failures(eng):
    return [e for e in _events(eng) if e.get("kind") == "failure"]


PING_WINDOW_S = 6 * 60 + 1   # past silence_ping_min (default 6) — the T3 escalation window


# ── real-git fixture (T1) — block_01_14_test/tron13_test convention ──
def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _mkrepo(prefix="tron-0117-"):
    d = tempfile.mkdtemp(prefix=prefix)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    with open(os.path.join(d, "README.md"), "w") as fh:
        fh.write("readme\n")
    os.makedirs(os.path.join(d, "meta"))
    with open(os.path.join(d, "meta", "x.md"), "w") as fh:
        fh.write("base\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


# ── T1 (AC-1 bullet 1): ff-refusal -> rebase-retry -> land ──
# SUPERSEDED (block 01-32, ADR-0002 D1/D2 T1): the auto-rebase-and-retry arm these two
# tests locked in is RETIRED — a git rebase, conflict-free or not, is a write TRON
# performs on the worker's own branch content, exactly the class the strict/folder-
# absolute write boundary forbids. Behavioral replacement (engine never rebases, even
# on a disjoint-file, conflict-free timing race) lives in block_01_32_test.py's
# `clobber_dead` (AC-2); the two tests below are updated in place to the NEW contract
# (a first ff-refusal returns non-ff, unconditionally, no retry of any kind) rather than
# kept as dead behavioral history.
def t_merge_ff_only_rebases_once_and_lands():
    d = _mkrepo()
    _git(d, "checkout", "-qb", "feat/x")
    with open(os.path.join(d, "meta", "x.md"), "a") as fh:
        fh.write("branch change\n")
    _git(d, "commit", "-aqm", "branch work")
    _git(d, "checkout", "-q", "main")
    # Trunk moves under the branch, on a DIFFERENT file -> a real timing race, no conflict —
    # exactly the shape the retired arm used to auto-rebase-and-land silently.
    with open(os.path.join(d, "README.md"), "w") as fh:
        fh.write("readme v2\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "trunk moved")
    trunk_tip_before = _git(d, "rev-parse", "main")[1]
    ok("setup: trunk really did move under the branch",
       _git(d, "merge-base", "--is-ancestor", trunk_tip_before, "feat/x")[0] != 0)
    okm, err = trunk.merge_ff_only(d, "feat/x", "main")
    ok("01-32 T1: a first ff-refusal is NEVER auto-rebased any more — the engine "
       "never rebases, conflict-free or not", okm is False, f"err={err}")
    ok("01-32 T1: trunk is untouched — the branch's content never lands without the "
       "worker's own rebase", "branch change" not in open(os.path.join(d, "meta", "x.md")).read())
    ok("01-32 T1: no rebase was ever attempted — no mid-rebase residue, ever",
       not os.path.exists(os.path.join(d, ".git", "rebase-merge"))
       and not os.path.exists(os.path.join(d, ".git", "rebase-apply")))
    shutil.rmtree(d, ignore_errors=True)


def t_land_docs_rebases_and_lands_the_dominant_wall_class():
    # Same race, through the actual paperwork lander (land_docs), the FSM's own call site —
    # land_docs shares merge_ff_only, so it inherits the same 01-32 T1 retirement: it no
    # longer auto-rebases paperwork branches either (Decision 1 is engine-wide, not scoped
    # to engineer blocks). A disjoint-file timing race now surfaces as "non-ff", not a
    # silent land — the paperwork lane's own rebase-before-close ritual (or a repair-scoped
    # re-land) is the worker's/architect's to drive, same as the block gate.
    d = _mkrepo()
    _git(d, "checkout", "-qb", "docs/late")
    with open(os.path.join(d, "meta", "x.md"), "a") as fh:
        fh.write("paperwork line\n")
    _git(d, "commit", "-aqm", "paperwork")
    _git(d, "checkout", "-q", "main")
    with open(os.path.join(d, "README.md"), "w") as fh:
        fh.write("readme v2\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "another lander moved trunk first")
    code, detail = trunk.verify_docs(d, "docs/late", ["meta/"], "main")
    ok("01-32 T1: land_docs no longer auto-rebases either — a timing race is 'non-ff', "
       "never a silent land", code == "non-ff", f"{code}: {detail}")
    ok("01-32 T1: the branch survives, untouched, for its owner to rebase",
       trunk.branch_exists(d, "docs/late"))
    shutil.rmtree(d, ignore_errors=True)


# ── T1 (AC-1 bullet 2): conflicted rebase -> wall with today's detail ──
def t_merge_ff_only_conflict_still_fails_cleanly():
    d = _mkrepo()
    _git(d, "checkout", "-qb", "feat/y")
    with open(os.path.join(d, "meta", "x.md"), "w") as fh:
        fh.write("branch overwrite\n")
    _git(d, "commit", "-aqm", "branch conflicting change")
    _git(d, "checkout", "-q", "main")
    with open(os.path.join(d, "meta", "x.md"), "w") as fh:
        fh.write("trunk overwrite\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "trunk conflicting change")
    okm, err = trunk.merge_ff_only(d, "feat/y", "main")
    ok("T1 a genuinely conflicting rebase still fails (never fabricates a resolution)",
       okm is False, f"err={err}")
    ok("T1 the failure detail is the ORIGINAL non-ff text — today's detail, unchanged",
       bool(err.strip()), f"err={err!r}")
    ok("T1 the repo is left clean — no mid-rebase residue after the abort",
       not os.path.exists(os.path.join(d, ".git", "rebase-merge"))
       and not os.path.exists(os.path.join(d, ".git", "rebase-apply")))
    ok("T1 the branch survives, untouched, for its owner to resolve",
       trunk.branch_exists(d, "feat/y"))
    rc, out, _ = _git(d, "status", "--porcelain")
    ok("T1 the working tree is clean (checked back out onto main)", out == "", f"status={out!r}")
    ok("T1 HEAD is back on main after the aborted rebase",
       _git(d, "rev-parse", "--abbrev-ref", "HEAD")[1] == "main")
    shutil.rmtree(d, ignore_errors=True)


def t_merge_ff_only_missing_trunk_untouched_by_the_retry():
    # T5 (01-15) regression guard: the retry must never fire ahead of the pre-existing
    # missing-trunk-branch fail-closed check.
    d = _mkrepo()
    okm, err = trunk.merge_ff_only(d, "feat/nope", "no-such-trunk")
    ok("T1 a missing trunk branch still fails closed before any retry is attempted",
       okm is False and "does not exist" in err, f"err={err}")
    shutil.rmtree(d, ignore_errors=True)


# ── T2 (AC-1 bullet 3): violation-land failure -> case re-opened, gate reachable ──
def _eng_with_violation_wall(block="A-01"):
    ctx, _ = build(blocks=[(block, "✅", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    g = eng.st.gate.setdefault(block, {"stage": "close"})
    restore = _mock_land("violation", "src/sneak.txt")
    try:
        eng._confirm_close(block, g)
        eng._drain_triggers()          # process the queued wall:raised trigger
    finally:
        restore()
    cid = next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")
    return eng, g, cid


def _mock_land(code, detail=""):
    orig = trunk.verify_docs
    trunk.verify_docs = lambda *a, **k: (code, detail)
    return lambda: setattr(sys.modules["trunk"], "verify_docs", orig)


def t_violation_land_failure_reopens_the_same_case():
    eng, g, cid = _eng_with_violation_wall()
    ok("setup: violation wall parked", g.get("violation_pending") is True
       and cid in eng.st.pending_cases)
    orig_lom = trunk.land_ordered_merge
    trunk.land_ordered_merge = lambda *a, **k: (False, "merge error: dubious ownership")
    try:
        eng._h_apply_decision({"case": cid, "decision": "approve", "block": "A-01"})
    finally:
        trunk.land_ordered_merge = orig_lom
    ok("T2 the gate stays parked (violation_pending) on a failed land",
       eng.st.gate.get("A-01", {}).get("violation_pending") is True)
    ok("T2 the SAME case is reopened, never spent — decision reverted to None",
       cid in eng.st.pending_cases and eng.st.pending_cases[cid].get("decision") is None,
       f"cases={eng.st.pending_cases}")
    ok("T2 the block is back on the wall (blocked), consistent with a live case",
       "A-01" in eng.st.blocked)
    ok("T2 the engineer stays walled (never released on a failed land)",
       any(w.get("id") == "ENG-A-01" and w.get("status") == "walled"
           for w in eng.st.workers))
    # T2's "gate reachable" half: the SAME case_id must still resolve a FRESH settle.
    orig_lom2 = trunk.land_ordered_merge
    trunk.land_ordered_merge = lambda *a, **k: (True, "landed @ abc1234")
    try:
        eng._h_apply_decision({"case": cid, "decision": "approve", "block": "A-01"})
    finally:
        trunk.land_ordered_merge = orig_lom2
    ok("T2 gate reachable: the reopened case settles cleanly once the land actually works",
       "A-01" not in eng.st.gate and cid not in eng.st.pending_cases,
       f"gate={eng.st.gate.get('A-01')} cases={eng.st.pending_cases}")
    ok("T2 the engineer is released on the eventual successful land",
       not any(w.get("id") == "ENG-A-01" for w in eng.st.workers))


def t_violation_land_repin_also_reopens_the_case():
    # The A-3 re-pin rider (tip moved, divergent diff) is the SAME "didn't land" shape —
    # it must never spend the case either.
    eng, g, cid = _eng_with_violation_wall()
    g["violation_tip"] = "sha1"     # TRON_DRY parked with no real tip — pin one explicitly
    orig_tip, orig_pid = trunk.tip_sha, trunk.patch_id_matches
    trunk.tip_sha = lambda *a, **k: "deadbeef"          # tip moved since park
    trunk.patch_id_matches = lambda *a, **k: False       # ...with a genuinely new diff
    try:
        eng._h_apply_decision({"case": cid, "decision": "approve", "block": "A-01"})
    finally:
        trunk.tip_sha, trunk.patch_id_matches = orig_tip, orig_pid
    ok("T2 a re-pinned violation tip also reopens the same case (never a dead end)",
       cid in eng.st.pending_cases and eng.st.pending_cases[cid].get("decision") is None,
       f"cases={eng.st.pending_cases}")
    ok("T2 the gate re-pins the new tip rather than landing blind",
       eng.st.gate.get("A-01", {}).get("violation_tip") == "deadbeef")


def t_violation_land_success_still_closes_the_case_as_before():
    # Regression guard: T2 must not change the HAPPY path — a successful land closes the
    # case and clears the gate exactly as it always has (01-15 T6).
    eng, g, cid = _eng_with_violation_wall()
    orig_lom = trunk.land_ordered_merge
    trunk.land_ordered_merge = lambda *a, **k: (True, "landed @ abc1234")
    try:
        eng._h_apply_decision({"case": cid, "decision": "approve", "block": "A-01"})
    finally:
        trunk.land_ordered_merge = orig_lom
    ok("T2 regression: a successful land clears the gate", "A-01" not in eng.st.gate)
    ok("T2 regression: a successful land closes the case", cid not in eng.st.pending_cases)


# ── T3 (AC-1 bullets 4/5): sweep-enforced wall/hold invariants ──
def _walled(eng, block, wid, status="idle", detail="flaky ci"):
    """An idle worker held by a wall (mirrors block_01_16_test's _walled helper). Returns
    the parked case id."""
    eng.st.workers.append({"id": wid, "role": "engineer", "block": block,
                           "session_id": "dry", "status": status})
    eng._tq = []
    eng._h_escalate({"block": block, "worker_id": wid, "detail": detail})
    return next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")


def _eng17(block="A-01"):
    ctx, _ = build(blocks=[(block, "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False        # _sweep no-ops entirely under dry
    return eng


def t_sweep_wall_invariant_retired_01_31():
    """SUPERSEDED (block 01-31, ADR-0002 D5): both T3(a) and T3(b) above are gone —
    `_sweep_wall_invariant` no longer exists at all, and `_sweep()` simply skips a
    walled worker (no repair, no un-hold, no re-raise) since the case that opened the
    hold is now the only thing that can close it. Structural proof here; full
    behavioral coverage of the replacement (F-1 via `_on_block_done`) lives in
    block_01_31_test.py."""
    ok("T3 _sweep_wall_invariant retired (01-31) — no longer an Engine attribute",
       not any(n == "_sweep_wall_invariant" for n in dir(Engine)))
    eng = _eng17()
    cid = _walled(eng, "A-01", "ENG-A-01", detail="close-time violation on feat/a-01")
    eng.st.pending_cases[cid]["decision"] = "resume"   # bypasses _close_case, on purpose
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    eng._sweep()
    clock["t"] += PING_WINDOW_S
    eng._sweep()                    # no arm (a)/(b) left to fire, either shape
    w = next(w for w in eng.st.workers if w["id"] == "ENG-A-01")
    ok("T3 a walled worker with a decided-but-unclosed case stays walled — "
       "sweep alone never un-holds it anymore", w.get("status") == "walled", f"w={w}")
    ok("T3 the case stays open — sweep alone never closes it anymore",
       cid in eng.st.pending_cases, f"cases={eng.st.pending_cases}")


def t_sweep_never_touches_a_walled_worker_with_a_live_case():
    # Regression guard: the ordinary wall state (a live, undecided case) must never be
    # touched by either invariant arm, however long it sits.
    eng = _eng17()
    _walled(eng, "A-01", "ENG-A-01")
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    clock["t"] += PING_WINDOW_S * 5
    eng._sweep()
    w = next(w for w in eng.st.workers if w["id"] == "ENG-A-01")
    ok("T3 regression: an ordinary live wall is never touched by the invariant sweep",
       w.get("status") == "walled" and len(eng.st.pending_cases) == 1, f"w={w}")


# ── T3 root cause: _hold_worker never clobbers held_status on a second hold ──
def t_hold_worker_second_hold_never_clobbers_held_status():
    eng = _eng17()
    w = {"id": "ENG-A-01", "role": "engineer", "block": "A-01",
        "session_id": "dry", "status": "idle"}
    eng.st.workers.append(w)
    eng._hold_worker(w)
    ok("setup: first hold stamps the true pre-hold status",
       w.get("held_status") == "idle" and w.get("status") == "walled")
    # A second hold call (the tron-23 mechanism: a repeated-stall wall / a racing
    # gate-giveup on an already-walled worker) must never overwrite held_status with
    # 'walled' itself.
    eng._hold_worker(w)
    ok("T3 root cause: a second hold on an already-walled worker leaves held_status alone",
       w.get("held_status") == "idle", f"w={w}")
    eng._unhold_worker(w)
    ok("T3 root cause: the worker un-holds to its TRUE original status, never stuck 'walled'",
       w.get("status") == "idle", f"w={w}")


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
