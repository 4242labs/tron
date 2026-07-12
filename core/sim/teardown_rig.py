#!/usr/bin/env python3
"""core/sim/teardown_rig.py — T2-19 REJECT root lock: `real_spawn.teardown`
hard-kills a runner that self-reported `state:"released"` but whose OS process
is STILL alive (a slow `claude` SIGTERM), so the OS-truth orphan scan that runs
next (`live._owned_orphans`) never flags it.

REAL process (honest, no mock of the thing under test): spawns an actual
`sleep` in its own session (leads its own pgid, exactly like a runner), stamps a
fake runner record `state:"released"` naming its real pid, and drives the real
`teardown`. The divergence the fix closes is asserted directly:
`jobs.is_alive` (state-based) reads the released runner DEAD while
`jobs.proc_alive` (OS-truth) reads it ALIVE — teardown keys on the latter.

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on fail.
"""
import os
import signal
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.dirname(_HERE)
_APP_ROOT = os.path.dirname(_CORE_DIR)
sys.path.insert(0, os.path.join(_APP_ROOT, "engine"))
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import jobs           # noqa: E402 — engine/jobs.py (is_alive/proc_alive/kill_hard under test)
import real_tier      # noqa: E402 — core/sim/real_tier.py (real_spawn.teardown under test)

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def main():
    # A real process in its OWN session (start_new_session -> pgid == pid, exactly
    # how spawn_runner starts a runner), so killpg(pid) reaches it.
    proc = subprocess.Popen(["sleep", "300"], start_new_session=True)
    wid = "architect"
    _orig_index, _orig_find, _orig_release = jobs.index, jobs.find, jobs.release
    try:
        rec = {wid: {"pid": proc.pid, "state": "released", "dir": _HERE, "turns": 0}}
        jobs.index = lambda: rec
        jobs.find = lambda w, idx=None: (idx or rec).get(w)
        jobs.release = lambda w, idx=None: True     # no-op: a real `sleep` ignores a .stop file

        # ── the exact divergence the fix closes ──
        ok("D1 (DIVERGENCE — must be GREEN): a released-but-alive runner reads DEAD via "
           "state-based is_alive yet ALIVE via OS-truth proc_alive — the gap that let "
           "teardown skip the hard-kill (T2-19)",
           jobs.is_alive(wid) is False and jobs.proc_alive(wid) is True,
           f"is_alive={jobs.is_alive(wid)} proc_alive={jobs.proc_alive(wid)} pid={proc.pid}")

        rs = real_tier.real_spawn.__new__(real_tier.real_spawn)
        rs.spawn_calls = [{"worker_id": wid}]
        escalated = rs.teardown(timeout_s=0.5)

        ok("T1 (HARD-KILL — must be GREEN): teardown ESCALATED the released-but-alive "
           "runner (keyed on proc_alive, not is_alive) — it is in the returned kill list",
           wid in escalated, f"escalated={escalated}")
        ok("T2 (NO ORPHAN — must be GREEN): the real process is genuinely GONE after "
           "teardown returns — the OS-truth orphan scan that runs next sees nothing",
           not _pid_alive(proc.pid) and not jobs.proc_alive(wid),
           f"pid_alive={_pid_alive(proc.pid)} proc_alive={jobs.proc_alive(wid)}")
    finally:
        jobs.index, jobs.find, jobs.release = _orig_index, _orig_find, _orig_release
        if _pid_alive(proc.pid):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            proc.wait(timeout=2)
        except Exception:   # noqa: BLE001
            pass

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.sim.teardown_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
