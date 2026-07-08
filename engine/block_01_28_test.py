"""block_01_28_test — trunk validation: trusted verdict, no false wall (block 01-28, AC-1…AC-6).

Wave-1 walled a DONE, GREEN, MERGED block. Root cause (ADR-tron-post-wave1-enhancements
§A): the post-merge test RE-RUN seam (`trunk.run_block_tests`, sole caller fsm.py:1542)
(a) computed an EMPTY validation range on a fast-forward landing (`base == merged_sha` on
a bare ff -> `X..X`, Defect A) and (b) only ever discovered `*_test.py` (Python), so a
TS/vitest project could never validate at all (Defect B). Audit: 8 of 9 recorded "stuck at
trunk" pages were this same false-wall — endemic, not incident-driven.

This block REPLACES the seam (retired outright — `trunk.run_block_tests` no longer
exists) with a trusted-verdict model (`trunk.validate_trunk`):
  T1  no base/range of ANY kind feeds the new model — the ff-collapse defect is closed
      structurally (there is nothing left to collapse), not by patching the old
      post-hoc `merge_base(main, branch)` recompute. That dead recompute (and the
      `g["merge_base"]` bookkeeping it fed, across fsm.py's branch_merged/self_merge/
      remote-PR/redrive arms) is removed at every call site.
  T2  `test.command` (+ optional `test.env`) declared in project.yaml (schema:
      contracts/schema/project.schema.yaml) is the engine's SOLE source of truth,
      run ONCE in a clean, detached `git worktree` at the merged commit the worker
      never controls — never a worker say-so, never a language/runner guess.
  T3  three outcomes, never two: "pass" advances, a genuinely OBSERVED "fail" holds
      quietly (unchanged from before), and "unconfirmed" (no merged sha / nothing
      declared / an unresolvable commit / a stale or mismatched CI read) ALSO holds
      but additionally routes to the architect first (`_triage_to_architect`, the same
      primitive `_h_escalate`/`_h_await` use for spec-ownable routing) — "can't
      confirm" never reads as "failed" and never raises a wall/failure page.
  T4  when `ci.check_name` is declared, the DONE-TRUNK gate reads CI's verdict for the
      merged commit instead of re-running — trusted only if commit-exact (head_sha ==
      merged_sha), non-stale (status == completed), and the exact declared check name.
  T5  `trunk.block_invariant_ok` (fsm.py:2099, `_drive_close`) is UNTOUCHED — this
      block proves it still fails closed with the retired seam gone, never coupled
      to whichever trunk-stage validation model is in use.

Deterministic, token-free: REAL throwaway git repos + real subprocess runs for the
trunk.py-level predicates (same convention as block_01_25_test's git-level cases), dry
FSM-level fixtures (sentry_test's builders, TRON_DRY) + monkeypatched `trunk.ci_check_runs`
/ `trunk._run_declared_command` for the CI-mode wiring proof (AC-6).

Fail-before: AC-1/AC-2/AC-3/AC-4 all fail if `engine/trunk.py` still routes through the
retired `run_block_tests(repo, merge_base(main, branch), merged_sha)` — a bare-ff base
collapses to `merged_sha` there (AC-1/Defect A) and its `f.endswith("_test.py")` discovery
finds nothing in a TS-only tree (AC-1/AC-3/Defect B); AC-4 fails if any collapsed/absent
read is treated as a hard failure instead of "unconfirmed, routed"; AC-5 fails if the
ancestry guard were ever accidentally coupled to (or weakened alongside) the retired seam.

Run: python3 engine/block_01_28_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import trunk             # noqa: E402
from fsm import Engine   # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def _scratch(d):
    """N3 (review round 2): `trunk._under_scratch_root` now REFUSES a worktree
    add/remove with no `scratch_root` at all (fail-closed — the pre-01-32 opt-in
    fallback to the system tempdir is gone). Every direct `trunk.validate_trunk` call
    in this file that reaches `_run_declared_command`'s clean checkout must now supply
    one explicitly, same as the one real production caller (fsm.py's `ctx.scratch_dir`)
    always did. Nested under the test repo's own tempdir so it's swept by the same
    `shutil.rmtree(d, ...)` each test already runs — no separate cleanup needed."""
    return os.path.join(d, ".trunkval-scratch")


def _mkrepo():
    d = tempfile.mkdtemp(prefix="tron-0128-")
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    with open(os.path.join(d, "src.txt"), "w") as fh:
        fh.write("base\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


def _ff_merge_scenario():
    """A bare fast-forward landing (main tip == branch tip after the merge) of a
    NON-Python feature — the exact wave-1 shape: Defect A (a post-hoc
    `merge_base(main, branch)` collapses to `merged_sha` itself here) and Defect B (zero
    `*_test.py` files exist anywhere in this tree to discover). Returns (repo_dir, sha)."""
    d = _mkrepo()
    _git(d, "checkout", "-q", "-b", "feat/A-01")
    with open(os.path.join(d, "feature.ts"), "w") as fh:
        fh.write("export function add(a, b) { return a + b; }\n")
    with open(os.path.join(d, "feature.test.ts"), "w") as fh:
        fh.write("// vitest-style test file — never a *_test.py\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "TS feature + its vitest-style test")
    _git(d, "checkout", "-q", "main")
    _git(d, "merge", "-q", "--ff-only", "feat/A-01")   # bare ff: main tip == branch tip
    _, sha = _git(d, "rev-parse", "HEAD")
    return d, sha


def _eng(block="A-01", status="🔄", with_architect=False):
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx)
    started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    if with_architect:
        eng.st.workers.append({"id": "ARCH-PERSIST", "role": "architect", "session_id": "",
                               "shortid": "", "status": "idle", "current_job": None, "block": None})
    return eng


def _capture_failures(eng):
    calls = []
    orig = eng.events.failure
    eng.events.failure = (lambda fclass, code, op, cause, **k:
                          calls.append((fclass, code, op, cause)) or orig(fclass, code, op, cause, **k))
    return calls


# ── AC-1: ff-landed, green, non-Python block reaches ✅/close with ZERO mechanism page ──
def t_ac1_ff_landed_green_block_closes_clean():
    d, sha = _ff_merge_scenario()
    cmd = "test -f feature.test.ts && exit 0 || exit 1"
    status, detail = trunk.validate_trunk(d, sha, cmd, None, None, False, scratch_root=_scratch(d))
    ok("AC-1 a bare-ff merged commit validates green via the declared command "
       "(no base/range, nothing to collapse)", status == "pass", detail)

    # FSM wiring: on_report at the trunk stage reaches record with ZERO TRON-mechanism
    # page — reproduces + fixes wave-1 end to end.
    eng = _eng("A-01")
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["test_command"] = cmd
    fails = _capture_failures(eng)
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None, "merged_sha": sha})
    eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
    ok("AC-1 wiring: trunk -> record on the observed green signal",
       g.get("stage") == "record", f"g={g}")
    ok("AC-1 wiring: zero TRON-mechanism page (no wall/failure raised)", fails == [], f"fails={fails}")
    ok("AC-1 wiring: the block never lands in the blocked/escalated set",
       "A-01" not in eng.st.blocked, f"blocked={eng.st.blocked}")
    ok("AC-1 wiring: no architect triage was queued (a clean pass routes nowhere)",
       not eng.st.architect_queue, f"queue={eng.st.architect_queue}")
    shutil.rmtree(d, ignore_errors=True)


# ── AC-2: a genuinely test-red block still HOLDS — no false pass ──
def t_ac2_red_block_holds():
    d, sha = _ff_merge_scenario()
    status, detail = trunk.validate_trunk(d, sha, "exit 1", None, None, False, scratch_root=_scratch(d))
    ok("AC-2 a genuinely failing declared command reads fail, not unconfirmed",
       status == "fail", detail)

    eng = _eng("A-01", with_architect=True)
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["test_command"] = "exit 1"
    fails = _capture_failures(eng)
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None, "merged_sha": sha})
    eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
    ok("AC-2 a genuine red HOLDS at trunk — no false pass", g.get("stage") == "trunk", f"g={g}")
    ok("AC-2 a genuine red never raises a wall/failure page (holds quietly)",
       fails == [], f"fails={fails}")
    ok("AC-2 a genuine red does NOT route to the architect — distinct from 'unconfirmed' (T3)",
       not eng.st.architect_queue and not (eng._architect() or {}).get("current_job"),
       f"queue={eng.st.architect_queue} arch={eng._architect()}")
    shutil.rmtree(d, ignore_errors=True)


# ── AC-3: the declared test.command validates a non-Python (TS/vitest) block green ──
def t_ac3_declared_command_validates_ts():
    ok("AC-3 the retired *_test.py/python3 discovery no longer exists on trunk.py",
       not hasattr(trunk, "run_block_tests"))
    d = _mkrepo()
    _git(d, "checkout", "-q", "-b", "feat/A-03")
    with open(os.path.join(d, "feature.ts"), "w") as fh:
        fh.write("export function add(a, b) { return a + b; }\n")
    with open(os.path.join(d, "feature.test.ts"), "w") as fh:
        fh.write("// vitest-style: expect(add(2,2)).toBe(4)\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "TS feature + vitest-style test, no python anywhere")
    _git(d, "checkout", "-q", "main")
    _git(d, "merge", "-q", "--ff-only", "feat/A-03")
    _, sha = _git(d, "rev-parse", "HEAD")

    py_tests = [f for f in os.listdir(d) if f.endswith("_test.py")]
    ok("AC-3 setup: no *_test.py anywhere in this TS project (the old discovery finds nothing)",
       py_tests == [], f"found {py_tests}")

    # a real, non-Python declared command that actually inspects the landed content —
    # a genuine command execution, never a language assumption.
    cmd = 'grep -q "add(2,2)" feature.test.ts && exit 0 || exit 1'
    status, detail = trunk.validate_trunk(d, sha, cmd, None, None, False, scratch_root=_scratch(d))
    ok("AC-3 a declared non-Python command validates green off the real landed content",
       status == "pass", detail)

    cmd_broken = 'grep -q "NEVER MATCHES ANYTHING" feature.test.ts && exit 0 || exit 1'
    status2, detail2 = trunk.validate_trunk(d, sha, cmd_broken, None, None, False,
                                             scratch_root=_scratch(d))
    ok("AC-3 the declared command genuinely runs — a non-matching check fails, not a free pass",
       status2 == "fail", detail2)

    # test.env is honored (layered onto the clean checkout's shell env).
    cmd_env = 'test "$TRON_TEST_MARK" = "01-28" && exit 0 || exit 1'
    status3, detail3 = trunk.validate_trunk(d, sha, cmd_env, {"TRON_TEST_MARK": "01-28"}, None, False,
                                             scratch_root=_scratch(d))
    ok("AC-3 test.env is layered onto the clean checkout before the command runs",
       status3 == "pass", detail3)
    shutil.rmtree(d, ignore_errors=True)


# ── AC-4: empty/collapsed/unresolvable validation HOLDS + routes architect-first ──
def t_ac4_unconfirmable_routes_not_walls():
    d = _mkrepo()
    _, base_sha = _git(d, "rev-parse", "HEAD")

    status, detail = trunk.validate_trunk(d, None, "exit 0", None, None, False)
    ok("AC-4a no merged sha -> unconfirmed, never failed", status == "unconfirmed", detail)

    status2, detail2 = trunk.validate_trunk(d, base_sha, None, None, None, False)
    ok("AC-4b no test.command declared -> unconfirmed, never failed", status2 == "unconfirmed", detail2)

    status3, detail3 = trunk.validate_trunk(d, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                                             "exit 0", None, None, False)
    ok("AC-4c an unresolvable merged sha -> unconfirmed, never failed",
       status3 == "unconfirmed", detail3)

    # FSM wiring: unconfirmed HOLDS at trunk and routes to the architect first — never a
    # wall/failure page — and only ONCE per unconfirmed episode (no per-tick spam).
    eng = _eng("A-01", with_architect=True)
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["test_command"] = None    # nothing declared -> can't confirm
    fails = _capture_failures(eng)
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None, "merged_sha": base_sha})
    eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
    ok("AC-4 wiring: unconfirmed HOLDS at trunk (no advance, never a false pass)",
       g.get("stage") == "trunk", f"g={g}")
    ok("AC-4 wiring: zero wall/failure page emitted", fails == [], f"fails={fails}")
    routed = bool(eng.st.architect_queue) or bool((eng._architect() or {}).get("current_job"))
    ok("AC-4 wiring: routed to the architect first (queued or dispatched), not straight to the operator",
       routed, f"queue={eng.st.architect_queue} arch={eng._architect()}")
    ok("AC-4 wiring: the episode is stamped so it isn't re-queued every tick",
       g.get("validation_unconfirmed") is True, f"g={g}")

    def _pending():
        return len(eng.st.architect_queue) + (1 if (eng._architect() or {}).get("current_job") else 0)
    before = _pending()
    eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
    ok("AC-4 wiring: a repeated unconfirmed tick doesn't spam a second architect job",
       _pending() == before, f"before={before} after={_pending()}")
    shutil.rmtree(d, ignore_errors=True)


# ── AC-5: the F-3 ancestry guard still fails closed, with the test seam removed ──
def t_ac5_ancestry_still_closes_f3():
    ok("AC-5 the retired run_block_tests seam no longer exists on trunk.py",
       not hasattr(trunk, "run_block_tests"))

    d = _mkrepo()
    _git(d, "checkout", "-q", "-b", "feat/A-05")
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("code, never merged to trunk\n")
    _git(d, "commit", "-aqm", "F-3 shape: stranded commit, never landed")
    _git(d, "checkout", "-q", "main")

    okc, detail = trunk.block_invariant_ok(d, "feat/A-05", None, "main", False)
    ok("AC-5 block_invariant_ok (T5, unchanged) still fails closed on a stranded commit",
       not okc and "feat/A-05" in detail, detail)

    # FSM wiring: _drive_close still runs the invariant BEFORE closing and gives up NAMED
    # — proving the F-3 close-time guard is wired independently of the retired seam.
    eng = _eng("A-05")
    eng.dry = False
    eng.paths["root"] = d
    eng.st.branches["A-05"] = "feat/A-05"
    g = eng.st.gate.setdefault("A-05", {"stage": "record", "pr": None, "record_checked": True})
    fails = _capture_failures(eng)
    eng._drive_close("A-05", g, "ENG-A-05")
    ok("AC-5 wiring: a stranded commit still blocks close (gate dropped, never closed)",
       "A-05" not in eng.st.gate, f"gate={eng.st.gate}")
    ok("AC-5 wiring: the escalation is the named record-bypass code, ancestry-caused",
       fails and fails[0][1] == "record-bypass" and "feat/A-05" in fails[0][3], f"fails={fails}")
    shutil.rmtree(d, ignore_errors=True)


# ── AC-6: CI-verdict path trusts only a commit-exact, non-stale, correctly-named verdict ──
def t_ac6_ci_verdict_commit_exact():
    sha = "a" * 40
    other_sha = "b" * 40
    orig = trunk.ci_check_runs

    def _fixture(runs):
        return lambda repo_root, s, dry=False: runs

    trunk.ci_check_runs = _fixture([{"name": "ci/tests", "head_sha": sha,
                                     "status": "completed", "conclusion": "success"}])
    try:
        status, detail = trunk.ci_verdict("/repo", sha, "ci/tests", False)
    finally:
        trunk.ci_check_runs = orig
    ok("AC-6a commit-exact + completed + success -> pass", status == "pass", detail)

    trunk.ci_check_runs = _fixture([{"name": "ci/tests", "head_sha": other_sha,
                                     "status": "completed", "conclusion": "success"}])
    try:
        status2, detail2 = trunk.ci_verdict("/repo", sha, "ci/tests", False)
    finally:
        trunk.ci_check_runs = orig
    ok("AC-6b a sha-mismatched (stale-ref) verdict never passes the block",
       status2 != "pass", detail2)

    trunk.ci_check_runs = _fixture([{"name": "ci/tests", "head_sha": sha,
                                     "status": "in_progress", "conclusion": None}])
    try:
        status3, detail3 = trunk.ci_verdict("/repo", sha, "ci/tests", False)
    finally:
        trunk.ci_check_runs = orig
    ok("AC-6c a still-running (non-completed/stale) verdict never passes the block",
       status3 == "unconfirmed", detail3)

    trunk.ci_check_runs = _fixture([{"name": "unrelated-lint", "head_sha": sha,
                                     "status": "completed", "conclusion": "success"}])
    try:
        status4, detail4 = trunk.ci_verdict("/repo", sha, "ci/tests", False)
    finally:
        trunk.ci_check_runs = orig
    ok("AC-6d an unrelated green check never substitutes for the declared suite",
       status4 == "unconfirmed", detail4)

    trunk.ci_check_runs = _fixture([{"name": "ci/tests", "head_sha": sha,
                                     "status": "completed", "conclusion": "failure"}])
    try:
        status5, detail5 = trunk.ci_verdict("/repo", sha, "ci/tests", False)
    finally:
        trunk.ci_check_runs = orig
    ok("AC-6e a genuine completed failure at the exact commit reads fail — not a silent pass",
       status5 == "fail", detail5)

    # No trusted CI configured at all (no ci.check_name) -> unconfirmed, never a free pass.
    status5b, detail5b = trunk.ci_verdict("/repo", sha, None, False)
    ok("AC-6f no ci.check_name declared -> unconfirmed, never a free pass",
       status5b == "unconfirmed", detail5b)

    # FSM/trunk wiring: CI mode never re-runs the engine's own command.
    called = {"n": 0}
    orig_run = trunk._run_declared_command

    def _spy(*a, **k):
        called["n"] += 1
        return "pass", "should never run"
    trunk._run_declared_command = _spy
    trunk.ci_check_runs = _fixture([{"name": "ci/tests", "head_sha": sha,
                                     "status": "completed", "conclusion": "success"}])
    try:
        status6, detail6 = trunk.validate_trunk("/repo", sha, "should be ignored", None,
                                                 "ci/tests", False)
    finally:
        trunk._run_declared_command = orig_run
        trunk.ci_check_runs = orig
    ok("AC-6 wiring: a trusted CI verdict path never re-runs the engine's own command",
       status6 == "pass" and called["n"] == 0, f"status={status6} called={called}")


def main():
    t_ac1_ff_landed_green_block_closes_clean()
    t_ac2_red_block_holds()
    t_ac3_declared_command_validates_ts()
    t_ac4_unconfirmable_routes_not_walls()
    t_ac5_ancestry_still_closes_f3()
    t_ac6_ci_verdict_commit_exact()

    failed = [n for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("ok  " if c else "FAIL") + " " + n + (f" — {d}" if d and not c else ""))
    print(f"\n{len(_results) - len(failed)}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
