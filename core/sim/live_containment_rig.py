"""core.sim.live_containment_rig — block 01-38 T19 (Completion Gate): lock
for `core/sim/live.py::main`'s CONTAINMENT SELF-PROOF (`_git_state`).

`core/sim/live.py::main` is THE entrypoint the two Completion-Gate live runs
actually invoke, and it spawns REAL claude agents (`adapter="host-cli"`) —
the highest-risk surface in this block (the T15 incident was exactly a
live-agent-spawning path with no isolation). Reusing `core/prompt_
conformance.py`'s own pattern verbatim: capture the REAL tron-app worktree's
git HEAD + working-tree status BEFORE the run, assert byte-identical AFTER,
in a `finally` so it fires even on an exception/refused-boot path — and,
UNLIKE `prompt_conformance.py`, a breach here must override whatever exit
code the run's own acceptance verdict would have produced (a containment
breach can never be masked by an otherwise-clean-looking result).

Pure control-flow rig: `live.run_live`/`live._git_state` are monkeypatched
(restored in `finally`) so this never spawns a real process or touches the
real worktree's actual git state — it proves `main`'s WIRING, not the real
spawn path (already proven honest by every other rig in this block that
exercises `core.engine.Engine` for real).

Proofs:
  C1  no breach, a clean ACCEPT result -> exit 0, no CRITICAL line
  C2  a breach (HEAD changed) -> exit 3, OVERRIDING the accept result's own
      exit 0 — a breach is never masked by an otherwise-clean verdict
  C3  a breach (status changed, HEAD same) -> exit 3 (either signal alone trips it)
  C3b block 01-38 T19 gate fix H2a: a breach via the THIRD arm alone —
      the sensitive-ignored path set changed, head+status unchanged —
      still trips exit 3 (proves the OR is genuinely three-armed, not two)
  C4  a breach on the LiveRunError (refused-boot) exception path -> STILL exit 3,
      never the try block's own exit 2 — the `finally` fires even there
  C5  no breach on the refused-boot path -> the ORIGINAL exit 2 is preserved
      (the self-proof does not override a clean refusal)
  C6  (H2a, REAL GIT — not the canned-tuple monkeypatch C1-C5/C3b use) a write
      to a SENSITIVE gitignored path (`.claude/x`) between baseline and after,
      against a REAL temp git repo -> breach -> exit 3. The C1-C5 monkeypatch
      of `live._git_state` is exactly why the ignored-path blind spot shipped
      blind in the first place (it never drove the real `git status
      --ignored` command at all) — C6/C7 close that gap by pointing
      `live._APP_ROOT` at a disposable real repo and letting the REAL
      (unpatched) `_git_state` run against it.
  C7  (H2a, REAL GIT, non-vacuity) a write to BENIGN gitignored paths
      (`core/__pycache__/x.pyc`, `logs/x.log`) — the harness's own churn —
      does NOT trip a breach, against a REAL temp repo. Without this, a
      too-broad denylist would false-REJECT every real run on its own
      footprint; C7 proves the denylist is not a disguised allowlist.

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on
fail.
"""
import os
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app worktree root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import live                            # noqa: E402 — core/sim/live.py, unit under test

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


_CLEAN_RESULT = {
    "outcome": "session_end", "orphans": [], "cases": {}, "operator_pages": {},
    "escalations": [], "escalated_kills": [], "abandoned_blocks": [],
    "leftover_branches": [], "events": [],
}


def _drive(git_states, run_live_stub):
    """Monkeypatch `live._git_state` to return each of `git_states` in order
    (one call per invocation — `main` calls it exactly twice: before, then
    in `finally`) and `live.run_live` to `run_live_stub`. Restores both in
    `finally`. Returns `main`'s exit code."""
    orig_git_state = live._git_state
    orig_run_live = live.run_live
    calls = iter(git_states)
    live._git_state = lambda: next(calls)
    live.run_live = run_live_stub
    try:
        return live.main(["--expect-pages", "0"])
    finally:
        live._git_state = orig_git_state
        live.run_live = orig_run_live


def _drive_real_git(app_root, run_live_stub):
    """C6/C7 (H2a): point `live._APP_ROOT` at a REAL disposable temp repo and
    let the REAL (unpatched) `live._git_state` run against it — never a
    canned tuple. `run_live_stub` is where the simulated breach/churn WRITE
    actually happens (between the baseline and after `_git_state()` calls
    `main` makes), so this genuinely drives `git status --porcelain
    --ignored` over real on-disk changes. Restores `live._APP_ROOT`/
    `live.run_live` in `finally`."""
    orig_app_root = live._APP_ROOT
    orig_run_live = live.run_live
    live._APP_ROOT = app_root
    live.run_live = run_live_stub
    try:
        return live.main(["--expect-pages", "0"])
    finally:
        live._APP_ROOT = orig_app_root
        live.run_live = orig_run_live


def _make_temp_repo():
    """A real, disposable, git-initialized repo mirroring the production
    `.gitignore`'s SENSITIVE entries (`.claude/`, `.env`, `config.yaml`,
    `.sandbox/`) plus the full H2a benign-churn denylist set, committed once
    so HEAD/status start clean. Caller removes the directory when done."""
    d = tempfile.mkdtemp(prefix="live-containment-rig-")
    subprocess.run(["git", "-C", d, "init", "-q"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "rig@test.invalid"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.name", "rig"], check=True)
    with open(os.path.join(d, ".gitignore"), "w") as f:
        f.write(
            ".claude/\n.env\nconfig.yaml\n.sandbox/\n"
            "__pycache__/\n*.py[cod]\n*.pyo\n.pytest_cache/\n"
            ".venv/\nvenv/\ndist/\nbuild/\n*.egg-info/\n"
            ".coverage\nhtmlcov/\nlogs/*.log\n")
    with open(os.path.join(d, "README.md"), "w") as f:
        f.write("live_containment_rig fixture repo\n")
    subprocess.run(["git", "-C", d, "add", "-A"], check=True)
    subprocess.run(["git", "-C", d, "commit", "-q", "-m", "init"], check=True)
    return d


def main():
    same = ("deadbeef" * 5, "", frozenset())   # (head, status, sensitive_ignored)
    changed_head = [("deadbeef" * 5, "", frozenset()), ("cafebabe" * 5, "", frozenset())]
    changed_status = [("deadbeef" * 5, "", frozenset()),
                      ("deadbeef" * 5, " M some/file.py\n", frozenset())]
    changed_sensitive = [("deadbeef" * 5, "", frozenset()),
                         ("deadbeef" * 5, "", frozenset({".claude/x"}))]

    # C1 — no breach, clean ACCEPT -> exit 0
    code = _drive([same, same], lambda **kw: dict(_CLEAN_RESULT))
    ok("C1: no breach + clean ACCEPT -> exit 0", code == 0, f"code={code}")

    # C2 — HEAD changed -> exit 3, overriding the accept result's own exit 0
    code = _drive(changed_head, lambda **kw: dict(_CLEAN_RESULT))
    ok("C2: HEAD changed (breach) -> exit 3, OVERRIDING the clean accept's "
       "own exit 0 — a breach is never masked", code == 3, f"code={code}")

    # C3 — status changed (HEAD same) -> exit 3
    code = _drive(changed_status, lambda **kw: dict(_CLEAN_RESULT))
    ok("C3: working-tree status changed (HEAD same) -> exit 3 — either "
       "signal alone trips the breach", code == 3, f"code={code}")

    # C3b (H2a) — the sensitive-ignored path SET changed, head+status
    # unchanged -> exit 3: the third arm of the breach OR genuinely trips on
    # its own, not just riding along with head/status.
    code = _drive(changed_sensitive, lambda **kw: dict(_CLEAN_RESULT))
    ok("C3b (H2a): sensitive-ignored path set changed (head+status "
       "unchanged) -> exit 3 — the breach check's THIRD arm alone trips it",
       code == 3, f"code={code}")

    # C4 — a breach on the refused-boot (LiveRunError) exception path ->
    # STILL exit 3, never the try block's own exit 2.
    def _refuse(**kw):
        raise live.LiveRunError("boot refused (synthetic)")
    code = _drive(changed_head, _refuse)
    ok("C4: a breach on the refused-boot exception path -> STILL exit 3 "
       "(never the try block's exit 2) — the `finally` self-proof fires "
       "even on an exception path", code == 3, f"code={code}")

    # C5 — no breach on the refused-boot path -> the ORIGINAL exit 2 is
    # preserved (the self-proof does not override a clean refusal).
    code = _drive([same, same], _refuse)
    ok("C5: no breach on the refused-boot path -> the original exit 2 is "
       "preserved (self-proof never overrides a CLEAN run, even a refused one)",
       code == 2, f"code={code}")

    # C6 (H2a, REAL GIT — not the canned-tuple monkeypatch above): a write to
    # a SENSITIVE gitignored path between baseline and after, against a real
    # temp repo -> breach -> exit 3.
    repo6 = _make_temp_repo()
    try:
        def _breach_sensitive(**kw):
            os.makedirs(os.path.join(repo6, ".claude"), exist_ok=True)
            with open(os.path.join(repo6, ".claude", "__breach_probe.json"), "w") as f:
                f.write('{"breach": true}\n')
            return dict(_CLEAN_RESULT)
        code6 = _drive_real_git(repo6, _breach_sensitive)
        ok("C6 (H2a, REAL GIT, non-vacuity): a write to a sensitive gitignored "
           "path (.claude/__breach_probe.json) between baseline and after, "
           "against a REAL temp git repo (not a canned tuple) -> breach -> "
           "exit 3", code6 == 3, f"code={code6}")
    finally:
        shutil.rmtree(repo6, ignore_errors=True)

    # C7 (H2a, REAL GIT, non-vacuity) — a write to BENIGN gitignored paths
    # (the harness's own churn) does NOT trip a breach, against a real temp
    # repo -> exit 0.
    repo7 = _make_temp_repo()
    try:
        def _benign_churn(**kw):
            os.makedirs(os.path.join(repo7, "core", "__pycache__"), exist_ok=True)
            with open(os.path.join(repo7, "core", "__pycache__", "x.pyc"), "wb") as f:
                f.write(b"\x00\x01")
            os.makedirs(os.path.join(repo7, "logs"), exist_ok=True)
            with open(os.path.join(repo7, "logs", "x.log"), "w") as f:
                f.write("benign harness log line\n")
            return dict(_CLEAN_RESULT)
        code7 = _drive_real_git(repo7, _benign_churn)
        ok("C7 (H2a, REAL GIT, non-vacuity): a write to BENIGN gitignored "
           "paths (core/__pycache__/x.pyc, logs/x.log) between baseline and "
           "after, against a REAL temp git repo, does NOT trip a breach -> "
           "exit 0 (else every real run would false-REJECT on the harness's "
           "own footprint — the denylist is not a disguised allowlist)",
           code7 == 0, f"code={code7}")
    finally:
        shutil.rmtree(repo7, ignore_errors=True)

    n_pass = sum(1 for _, c, _ in _results if c)
    n_total = len(_results)
    for name, cond, detail in _results:
        mark = "PASS" if cond else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))
    print(f"live_containment_rig: PASS ({n_pass}/{n_total})")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
