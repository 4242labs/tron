"""core.sim.orphan_scan_rig — TOKEN-FREE lock for the LIVE driver's teardown
orphan check (`live._owned_orphans` / `live._is_worker_exec`).

The bug this locks against: the old `_pgrep_scoped(root)` acceptance-orphan
sweep matched `pgrep -fa claude` / `worker_runner.py` and kept ANY line whose
command referenced the run's copy root. A monitoring shell — `/bin/bash -c
'sleep 270; ... /home/x/.claude/...  /tmp/<root>/.../home-events.jsonl ...'` —
matches BOTH the loose `claude` pattern (its path contains `.claude`) AND the
`root in line` test (it tails the run's eventlog), so an otherwise-CLEAN run
(session_end, 0 cases, 0 pages) was hard-REJECTed as if a worker leaked. That
false-REJECT actually happened on T2-08.

The fix scopes the check to the driver's OWN fleet: a spawned worker id
(`rs.spawn_calls`) whose recorded pid is still alive (`jobs.is_alive`, OS-truth),
or a real worker EXECUTABLE (`_is_worker_exec` — classify by argv[0], never a
substring anywhere in the line). A bystander is excluded on both arms.

Pure unit rig — no scaffold, no LLM, no real processes: `subprocess.run` (pgrep)
and `jobs.*` are stubbed so the classification logic is exercised deterministically.

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on fail.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import live                            # noqa: E402 — core/sim/live.py, unit under test

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


ROOT = "/tmp/tron-boot-real-scaffold-XYZ/trivial-tip-converter"

# The EXACT shape of the T2-08 false-positive: a monitor shell that tails the
# run's eventlog (references ROOT) and whose command contains `.claude`.
BYSTANDER = (f"1709737 /bin/bash -c source /home/anderson/.claude/shell-snapshots/"
             f"snapshot.sh && eval 'sleep 270; tail {ROOT}/meta/agents/tron/"
             f"home-events.jsonl; pgrep -f core.sim.live'")
# A real worker_runner.py process for THIS root (a genuine leaked runner) —
# spawned as `python3 <root>/…/worker_runner.py`, so ROOT IS in its argv.
RUNNER = (f"424242 python3 {ROOT}/meta/agents/tron/workers/engineer-01-99/"
          f"worker_runner.py engineer-01-99")
RUNNER_PID = 424242
# A real re-parented `claude` child whose runner already died. CRITICAL: the
# real HostCliAdapter invocation (engine/worker_runner.py) carries ROOT only via
# `Popen(cwd=…)`, NEVER in argv — so this fixture has NO root anywhere in its
# command line. The OLD `root in ln` filter MISSED exactly this shape (the
# false-NEGATIVE peer review found); ownership must come from its cwd instead.
CLAUDE = ("424243 /home/anderson/.nvm/versions/node/v24/bin/claude.exe -p "
          "--input-format stream-json --output-format stream-json --verbose "
          "--session-id abc --model claude-opus-4-8 --dangerously-skip-permissions")
CLAUDE_PID = 424243
CLAUDE_CWD = f"{ROOT}/meta/agents/tron/workers/engineer-01-99"   # Popen cwd=, under ROOT
# A `tail` bystander that also references ROOT (in argv).
TAIL = f"999001 tail -f {ROOT}/meta/agents/tron/home-events.jsonl"
# A claude worker belonging to a DIFFERENT run's root (not ours).
OTHER_ROOT = "/tmp/tron-boot-real-scaffold-OTHER/trivial-tip-converter"
CLAUDE_OTHER = ("770001 /home/anderson/.nvm/versions/node/v24/bin/claude.exe -p "
                "--session-id zzz --model claude-opus-4-8")
CLAUDE_OTHER_PID = 770001


class _FakeRun:
    def __init__(self, stdout):
        self.stdout = stdout


def _install_pgrep(mapping):
    """Stub live.subprocess.run so `pgrep -fa <pat>` yields `mapping[pat]`."""
    def fake_run(cmd, **kw):
        pat = cmd[2] if len(cmd) > 2 else ""
        return _FakeRun(mapping.get(pat, ""))
    live.subprocess.run = fake_run


def _install_jobs(alive_ids):
    """Stub live.jobs so only worker ids in `alive_ids` read as alive."""
    live.jobs.index = lambda: {wid: {"pid": 5000 + i, "state": "working"}
                               for i, wid in enumerate(alive_ids)}
    live.jobs.is_alive = lambda wid, idx=None: wid in alive_ids
    live.jobs.find = lambda wid, idx=None: (idx or live.jobs.index()).get(wid)


def _install_cwd(mapping):
    """Stub live._proc_cwd so a pid resolves to `mapping[pid]` (else ''), letting
    the rig exercise CWD-based ownership without real /proc processes."""
    live._proc_cwd = lambda pid: mapping.get(int(pid), "")


class _RS:
    def __init__(self, wids):
        self.spawn_calls = [{"worker_id": w} for w in wids]


def main():
    # ── _is_worker_exec classification (the discriminator) ──
    ok("O1: a `/bin/bash -c` monitor referencing .claude + root is NOT a worker exec",
       not live._is_worker_exec(BYSTANDER.split(None, 1)[1]), BYSTANDER)
    ok("O2: a real worker_runner.py line IS a worker exec",
       live._is_worker_exec(RUNNER.split(None, 1)[1]), RUNNER)
    ok("O3: a real claude.exe child IS a worker exec (argv[0] basename)",
       live._is_worker_exec(CLAUDE.split(None, 1)[1]), CLAUDE)
    ok("O4: a `tail -f <root>/events` bystander is NOT a worker exec",
       not live._is_worker_exec(TAIL.split(None, 1)[1]), TAIL)

    # ── _owned_orphans: the T2-08 CLEAN case — only a monitor shell survives ──
    _install_jobs(alive_ids=[])                        # no spawned worker alive
    _install_cwd({})
    _install_pgrep({"worker_runner.py": "", "claude": BYSTANDER + "\n"})
    orphans = live._owned_orphans(_RS(["engineer-01-02", "engineer-01-03"]), ROOT)
    ok("O5: a clean run whose only root-referencing process is the monitor shell "
       "reports ZERO orphans (the T2-08 false-REJECT is gone)",
       orphans == [], f"orphans={orphans}")

    # ── a genuinely leaked SPAWNED worker (its pid still alive) IS flagged ──
    _install_jobs(alive_ids=["engineer-01-02"])
    _install_cwd({})
    _install_pgrep({"worker_runner.py": "", "claude": BYSTANDER + "\n"})
    orphans = live._owned_orphans(_RS(["engineer-01-02", "engineer-01-03"]), ROOT)
    ok("O6: a spawned worker still alive after teardown IS flagged (owned-scope arm)",
       len(orphans) == 1 and "engineer-01-02" in orphans[0], f"orphans={orphans}")

    # ── a real re-parented worker_runner (argv-root) + claude (CWD-root, NO root
    #    in argv) for this root ARE flagged; the bash monitor and the tail are NOT ──
    _install_jobs(alive_ids=[])
    _install_cwd({CLAUDE_PID: CLAUDE_CWD})             # the claude child's real cwd, under ROOT
    _install_pgrep({"worker_runner.py": RUNNER + "\n",
                    "claude": BYSTANDER + "\n" + CLAUDE + "\n" + TAIL + "\n"})
    orphans = live._owned_orphans(_RS(["engineer-01-02"]), ROOT)
    flagged = " ".join(orphans)
    ok("O7: a real re-parented worker_runner.py (argv-root) + claude.exe (cwd-root, "
       "no root in argv) for this root ARE flagged, but the bash monitor and the tail are NOT",
       "worker_runner.py" in flagged and "claude.exe" in flagged
       and "/bin/bash" not in flagged and "tail -f" not in flagged,
       f"orphans={orphans}")

    # ── THE PEER-REVIEW FALSE-NEGATIVE (must be GREEN): a re-parented claude child
    #    whose worker_runner already DIED (gone from pgrep AND from jobs) and whose
    #    argv carries NO root — caught ONLY by its cwd. The OLD `root in ln` filter
    #    silently passed this live token-burning leak as a clean teardown. ──
    _install_jobs(alive_ids=[])                        # parent runner dead: is_alive False
    _install_cwd({CLAUDE_PID: CLAUDE_CWD})
    _install_pgrep({"worker_runner.py": "", "claude": CLAUDE + "\n"})
    orphans = live._owned_orphans(_RS(["engineer-01-99"]), ROOT)
    ok("O9 (FALSE-NEGATIVE KILLER — must be GREEN): a re-parented claude child "
       "with NO root in argv, cwd under root, whose runner already died, IS flagged "
       "(the old argv-substring filter missed it → silent leak passed as clean)",
       len(orphans) == 1 and "claude.exe" in orphans[0], f"orphans={orphans}")

    # ── a worker for a DIFFERENT run's root is NOT ours (no false-positive across runs) ──
    _install_jobs(alive_ids=[])
    _install_cwd({CLAUDE_OTHER_PID: f"{OTHER_ROOT}/meta/agents/tron/workers/x"})
    _install_pgrep({"worker_runner.py": "", "claude": CLAUDE_OTHER + "\n"})
    orphans = live._owned_orphans(_RS(["engineer-01-99"]), ROOT)
    ok("O10: a claude worker whose cwd is under a DIFFERENT run's root is NOT flagged "
       "(ownership is scoped to THIS root, no cross-run false-positive)",
       orphans == [], f"orphans={orphans}")

    # ── the driver's own pid is never flagged, even as a worker-shaped line ──
    _install_jobs(alive_ids=[])
    _install_cwd({})
    self_line = f"{os.getpid()} python3 {ROOT}/meta/agents/tron/workers/x/worker_runner.py x"
    _install_pgrep({"worker_runner.py": self_line + "\n", "claude": ""})
    orphans = live._owned_orphans(_RS([]), ROOT)
    ok("O8: the driver's OWN pid is excluded even if it matches a worker pattern",
       orphans == [], f"orphans={orphans}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.sim.orphan_scan_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
