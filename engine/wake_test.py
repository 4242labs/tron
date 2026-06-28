"""wake_test — the 01-04 WAKE-daemon acceptance suite (AC-2, AC-3).

Deterministic, token-free: no real session, no agents, no LLM. Tests the daemon's
two load-bearing mechanisms directly —
  • the WAKE schedule (bounds + the cooldown/ceiling debounce decision)   → AC-2
  • single-flight + process lifecycle (one supervised daemon, no overlap)  → AC-3

Run: python3 engine/wake_test.py   (exit 0 = pass).
"""
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import util            # noqa: E402
import wake            # noqa: E402
from ctx import Ctx    # noqa: E402

_fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        _fails.append(name)


def _ctx():
    return Ctx(tempfile.mkdtemp(prefix="wake-test-"))


# ── AC-2: WAKE schedule (bounds + debounce) ──
def test_bounds():
    print("AC-2 — WAKE bounds (knobs → cooldown/ceiling)")
    check("defaults 5/30 when unset", wake.bounds({}) == (5, 30))
    check("reads knob values", wake.bounds({"wake_cooldown_sec": 3, "wake_ceiling_sec": 20}) == (3, 20))
    check("cooldown floored at 1s", wake.bounds({"wake_cooldown_sec": 0})[0] == 1)
    # ceiling can never sit below the floor (cooldown ≤ ceiling invariant)
    check("ceiling clamped up to cooldown", wake.bounds({"wake_cooldown_sec": 10, "wake_ceiling_sec": 4}) == (10, 10))


def test_due():
    print("AC-2 — debounce decision (cooldown ≤ gap ≤ ceiling)")
    cd, ceil = 5, 30
    # a fresh message wakes early — but never inside the COOLDOWN floor
    check("msg inside cooldown → wait", wake.due(True, 2, cd, ceil) is False)
    check("msg past cooldown → wake early", wake.due(True, 6, cd, ceil) is True)
    check("msg exactly at cooldown → wake", wake.due(True, 5, cd, ceil) is True)
    # idle: nothing fires until the CEILING cadence
    check("idle below ceiling → wait", wake.due(False, 10, cd, ceil) is False)
    check("idle at ceiling → wake", wake.due(False, 30, cd, ceil) is True)
    check("idle past ceiling → wake", wake.due(False, 99, cd, ceil) is True)


# ── AC-3: single-flight + lifecycle ──
def test_single_flight():
    print("AC-3 — single-flight (two ticks never overlap)")
    ctx = _ctx()
    with wake.single_flight(ctx) as first:
        check("first caller wins the lock", first is True)
        with wake.single_flight(ctx) as second:
            check("second caller is refused while held", second is False)
        # locked_tick refuses without ever entering the engine while the lock is held
        check("locked_tick skips under a held lock", wake.locked_tick(ctx) == (False, False))
    # released → reacquirable
    with wake.single_flight(ctx) as again:
        check("lock reacquirable once released", again is True)


def test_session_live():
    print("AC-3 — session_live gates the daemon")
    ctx = _ctx()
    check("no manifest → not live", wake.session_live(ctx) is False)
    util.atomic_write(ctx.state, "session:\n  started_at: '2026-06-28T00:00:00Z'\n")
    check("started_at set → live", wake.session_live(ctx) is True)
    util.atomic_write(ctx.state, "session:\n  started_at: null\n")
    check("started_at cleared → not live (daemon self-exits)", wake.session_live(ctx) is False)


def test_lifecycle():
    print("AC-3 — pid lifecycle + supervised stop")
    ctx = _ctx()
    check("no pid file → not running", wake.is_running(ctx) is False)
    check("stop() on nothing → False", wake.stop(ctx) is False)
    # stand in a real long-lived child for the daemon process and prove stop() reaps it
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    util.atomic_write(ctx.wake_pid, str(child.pid))
    check("is_running True for a live pid", wake.is_running(ctx) is True)
    check("spawn() is idempotent (returns the live pid)", wake.spawn(ctx) == child.pid)
    check("stop() reports it stopped one", wake.stop(ctx) is True)
    time.sleep(0.2)
    check("child process actually terminated", child.poll() is not None)
    check("pid file removed after stop", not os.path.exists(ctx.wake_pid))
    if child.poll() is None:
        child.kill()
    # a stale pid (dead process) reads as not-running
    util.atomic_write(ctx.wake_pid, "999999")
    check("stale/dead pid → not running", wake.is_running(ctx) is False)


def test_concurrent_spawn():
    print("AC-3 — concurrent spawn launches exactly one daemon (no TOCTOU)")
    ctx = _ctx()
    launched = []                                    # one entry per real _launch call
    procs = []
    guard = threading.Lock()

    def fake_launch(c):
        # a real, alive stand-in for the daemon so the pidfile ends up holding a live pid
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        with guard:
            launched.append(p.pid)
            procs.append(p)
        return p

    orig = wake._launch
    wake._launch = fake_launch
    barrier = threading.Barrier(12)                  # fire all callers at once to force the race
    results = []

    def caller():
        barrier.wait()
        results.append(wake.spawn(ctx))

    try:
        threads = [threading.Thread(target=caller) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        check("exactly one daemon was launched", len(launched) == 1)
        check("pidfile holds the launched daemon's pid", wake._read_pid(ctx) == launched[0])
        check("the daemon reads as running", wake.is_running(ctx) is True)
        # every caller either got the live daemon pid or saw the in-flight claim (None) —
        # none launched a second daemon
        check("no caller returned a rival pid", set(results) <= {launched[0], os.getpid(), None})
    finally:
        wake._launch = orig
        for p in procs:
            p.kill()


def main():
    for t in (test_bounds, test_due, test_single_flight, test_session_live,
              test_lifecycle, test_concurrent_spawn):
        t()
    print()
    if _fails:
        print(f"wake_test: FAILED ({len(_fails)}): {_fails}")
        return 1
    print("wake_test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
