"""record_landing_test — the RECORD-stage landing arms (ADR-0002 D2 completeness,
closed 2026-07-08 after the first live reset wave hard-failed on them).

Two defects, two fixes, both guarded here:

  D-A  Nothing ever minted a grant for the gate-ordered status-flip commit
       (PMT-DONE-RECORD says "this one commit is gate-authorized"; land.sh is
       grant-gated with no exceptions; `_drive_record_redrive` correctly declines
       paperwork-only deltas — so both reset-wave-1b/2b runs wedged at record,
       workers walling "no live grant exists"). Fix: the paperwork-only descendant
       at stage=='record' now takes `_drive_record_paperwork_landing` — the same
       mint-order-observe protocol as every other landing site.

  D-B  `trunk.record_commit_ok` walked `git log -- <file>` with NO rev — on the D1
       detached-root seat that reads the STALE detached HEAD's history (the base
       commit), never trunk truth, so even a correctly-landed flip gave up close
       with "record commit non-conforming". Fix: the log walk is keyed to the
       caller's truth ref (T2 rekeying parity with block_invariant_ok).

The end-to-end acceptance test for the whole ladder is tron-meta's `ghost_ladder`
micro-sim drill; these tests keep the two arms guarded in canon's own CI.
"""
import os
import sys
import shutil
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("TRON_DRY", "1")

import grants                                             # noqa: E402
import trunk                                              # noqa: E402
from fsm import Engine                                    # noqa: E402
from sentry_test import build, started                    # noqa: E402

LAND_SH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "templates", "project-scaffold", "templates", "meta",
                       "scripts", "land.sh")

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _run_land(repo, case_id, grants_dir, main="main"):
    return subprocess.run(["bash", LAND_SH, case_id, "--main", main],
                          cwd=repo, capture_output=True, text=True,
                          env={**os.environ, "LAND_GRANTS_DIR": grants_dir})


def _mkrepo_record(prefix="tron-record-"):
    """Real repo in the seeded-project shape (pipeline table + block doc with a
    `**Status:**` field), root DETACHED at the base commit (D1 seat), and a
    feat/a-01 branch whose CODE work has ALREADY landed on main (ff) — the exact
    state at the top of the record stage, one flip away from close."""
    d = tempfile.mkdtemp(prefix=prefix)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    os.makedirs(os.path.join(d, "meta", "blocks"))
    os.makedirs(os.path.join(d, "src"))
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("## Roadmap\n### Phase 1: Test\n| ID | Task | Status | Notes |\n"
                 "|:--|:--|:--|:--|\n| A-01 | t | 🔄 | Block `blocks/A-01.md` |\n")
    with open(os.path.join(d, "meta", "blocks", "A-01.md"), "w") as fh:
        fh.write("# Block A-01: test A-01\n**Phase:** Phase 1: Test\n"
                 "**Status:** 🔄\n**Depends on:** none\n**Reviewer class:** code\n"
                 "**Merge approval:** auto\n**Deploy:** none\n\n---\n\n## Body\n")
    with open(os.path.join(d, "src", "lib.py"), "w") as fh:
        fh.write("VALUE = 1\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    base = _git(d, "rev-parse", "HEAD")[1]
    _git(d, "checkout", "-qb", "feat/a-01")
    with open(os.path.join(d, "src", "lib.py"), "w") as fh:
        fh.write("VALUE = 2\n")
    _git(d, "commit", "-aqm", "A-01: work")
    work = _git(d, "rev-parse", "HEAD")[1]
    _git(d, "checkout", "-q", "main")
    _git(d, "merge", "-q", "--ff-only", "feat/a-01")      # code already landed
    _git(d, "checkout", "-q", "--detach", base)            # D1 seat: detached, STALE
    return d, work


def _flip_record(d, branch="feat/a-01"):
    """The worker's hands: flip exactly the Status line on its own branch via a
    scratch worktree (never the shared root)."""
    wt = tempfile.mkdtemp(prefix="tron-record-wt-")
    os.rmdir(wt)
    _git(d, "worktree", "add", wt, branch)
    try:
        doc = os.path.join(wt, "meta", "blocks", "A-01.md")
        with open(doc) as fh:
            lines = fh.read().splitlines(keepends=True)
        with open(doc, "w") as fh:
            for ln in lines:
                fh.write("**Status:** ✅ Done\n" if ln.startswith("**Status:**") else ln)
        _git(wt, "commit", "-aqm", "A-01: record ✅")
        return _git(wt, "rev-parse", "HEAD")[1]
    finally:
        rc, _, _ = _git(d, "worktree", "remove", "--force", wt)
        if rc != 0:
            shutil.rmtree(wt, ignore_errors=True)
            _git(d, "worktree", "prune")


def _eng_record(d, block="A-01"):
    ctx, _ = build(blocks=[(block, "🔄", "none")])
    eng = Engine(ctx)
    started(eng)
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["main_branch"] = "main"
    eng.paths["remote"] = None
    eng.paths["blocks"] = os.path.join(d, "meta", "blocks")
    eng.st.branches[block] = "feat/a-01"
    eng.st.block_roles[block] = eng.roles.select_build_role()   # live dispatch parity
    return eng


# ── D-A: the record-stage paperwork landing mints + orders + observes ──
def t_record_stage_mints_and_worker_lands():
    d, work = _mkrepo_record()
    try:
        eng = _eng_record(d)
        g = eng.st.gate.setdefault("A-01", {"stage": "record", "merged_sha": work,
                                            "pr": None})
        flip = _flip_record(d)
        # tick 1: the gate observes the paperwork-only descendant at record ->
        # mints record-<block>-<tip> and ORDERS the land; trunk must NOT move.
        eng._drive_gate("A-01", g)
        case_id = g.get("record_landing_case")
        ok("D-A: a record-stage grant mints for the flip (record_landing_case set)",
           bool(case_id) and case_id.startswith("record-A-01-"), f"g={g}")
        live = grants.read_live(eng.ctx.grants_dir, case_id) if case_id else None
        ok("D-A: the grant is LIVE, patch-id-bound, for the worker's branch",
           bool(live) and bool(live.get("patch_id")) and live.get("branch") == "feat/a-01",
           f"live={live}")
        ok("D-A: trunk did NOT move on the engine's own account",
           _git(d, "rev-parse", "main")[1] == work)
        # the worker's hands: land.sh with the minted grant.
        r = _run_land(d, case_id, eng.ctx.grants_dir)
        ok("D-A: land.sh (the worker's hands) lands the flip", r.returncode == 0,
           f"stdout={r.stdout} stderr={r.stderr}")
        ok("D-A: trunk now IS the flip", _git(d, "rev-parse", "main")[1] == flip)
        # tick 2: the engine observes, consumes administratively, clears the case.
        eng._drive_gate("A-01", g)
        ok("D-A: observed -> grant consumed (receipt), case cleared",
           g.get("record_landing_case") is None
           and grants.read_consumed(eng.ctx.grants_dir, case_id) is not None,
           f"g={g}")
        ok("D-A: stage never advanced here (trunk truth owns the ✅ advance)",
           g.get("stage") == "record", f"g={g}")
        # and the same tick must not re-mint for the already-landed content.
        ok("D-A: no second live grant lingers", grants.list_live(eng.ctx.grants_dir) == {})
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── D-A guard: a CODE-bearing descendant still takes the redrive, never this arm ──
def t_code_bearing_descendant_still_redrives():
    d, work = _mkrepo_record()
    try:
        eng = _eng_record(d)
        g = eng.st.gate.setdefault("A-01", {"stage": "record", "merged_sha": work,
                                            "pr": None})
        wt = tempfile.mkdtemp(prefix="tron-record-wt-")
        os.rmdir(wt)
        _git(d, "worktree", "add", wt, "feat/a-01")
        try:
            with open(os.path.join(wt, "src", "lib.py"), "w") as fh:
                fh.write("VALUE = 3\n")
            _git(wt, "commit", "-aqm", "A-01: required fix")
        finally:
            _git(d, "worktree", "remove", "--force", wt)
        eng._drive_gate("A-01", g)
        ok("D-A guard: a code-bearing descendant mints the REDRIVE case, not the "
           "record-paperwork one",
           bool(g.get("redrive_case")) and not g.get("record_landing_case"), f"g={g}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── D-B: record_commit_ok is truth-ref-keyed, never detached-HEAD-keyed ──
def t_record_commit_ok_truth_ref_keyed():
    d, work = _mkrepo_record()
    try:
        flip = _flip_record(d)
        _git(d, "update-ref", "refs/heads/main", flip, work)   # flip on trunk
        # root HEAD is still detached at the BASE commit (the D1 seat) — the old
        # rev-less walk read base as the doc's last toucher and gave up close.
        okc, detail = trunk.record_commit_ok(d, "meta/blocks/A-01.md",
                                            truth_ref="main")
        ok("D-B: keyed to the truth ref, a landed conforming flip PASSES",
           okc, f"detail={detail}")
        ok("D-B: and the accepted sha is the FLIP, not the stale HEAD's toucher",
           detail == flip[:8], f"detail={detail} flip={flip[:8]}")
        # a non-conforming record (extra file) still fails, keyed the same way.
        wt = tempfile.mkdtemp(prefix="tron-record-wt-")
        os.rmdir(wt)
        _git(d, "worktree", "add", wt, "feat/a-01")
        try:
            with open(os.path.join(wt, "meta", "blocks", "A-01.md"), "a") as fh:
                fh.write("extra\n")
            with open(os.path.join(wt, "src", "lib.py"), "w") as fh:
                fh.write("VALUE = 9\n")
            _git(wt, "commit", "-aqm", "smuggle")
            bad = _git(wt, "rev-parse", "HEAD")[1]
        finally:
            _git(d, "worktree", "remove", "--force", wt)
        _git(d, "update-ref", "refs/heads/main", bad, flip)
        okc2, detail2 = trunk.record_commit_ok(d, "meta/blocks/A-01.md",
                                              truth_ref="main")
        ok("D-B: a smuggling record still FAILS under the truth-ref walk",
           not okc2, f"detail={detail2}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    for fn in (t_record_stage_mints_and_worker_lands,
              t_code_bearing_descendant_still_redrives,
              t_record_commit_ok_truth_ref_keyed):
        fn()
    bad = [r for r in _results if not r[1]]
    for name, good, detail in _results:
        print(f"  [{'PASS' if good else 'FAIL'}] {name}"
              + (f" — {detail}" if detail and not good else ""))
    print(f"record_landing_test: {'PASS' if not bad else 'FAIL'} "
          f"({len(_results)-len(bad)}/{len(_results)})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
