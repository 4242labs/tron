"""core.worker_working_rig — the regression lock for ADR-0006 R1a: the
deadline-bounded `Engine._worker_working`. The runner declares its OWN turn
deadline (`worker_runner._write_state`: `rec["deadline"]=time.time()+TURN_TIMEOUT_S`,
epoch seconds, whenever it goes `working`), `jobs.index` projects it, and
`_worker_working` must refuse to count an actor "working" once `time.time()`
passes that deadline — otherwise a hung-but-alive runner (`state=="working"`
forever) re-anchors every silence ladder (`core/liveness.py`, `core/sentry.py`)
and the real per-turn ceiling becomes TURN_TIMEOUT_S (30 min), silently
overriding `silence_escalate_min` (8 min). R1a is the PREREQUISITE for
R1b/R1c/R1e — with it inert, none of them can tell working from wedged.

Unit-level on purpose: drives the REAL `core.engine.Engine._worker_working`
(via `Engine.__new__` to skip the heavy boot) with `engine.jobs` monkeypatched
to return a chosen record — the branch under test is entirely inside the method.

Proofs:
  W1  working + deadline in the FUTURE            -> True  (a live turn)
  W2  working + deadline in the PAST              -> False (the bound — the FIX)
  W3  working + deadline None (stale/pre-A4 rec)  -> True  (old behavior preserved)
  W4  state != working                            -> False (idle/online/error)
  W5  not alive                                   -> False (dead runner)
  W6  CLOCK-UNIT KILLER: working + past deadline, with `eng._now` injected as
      epoch MINUTES (as the live driver does, live.py:96) -> STILL False. Proves
      the comparison uses raw `time.time()` (epoch seconds), NOT `self._now()`
      (minutes) — the exact mismatch that would make the whole fix inert.
  W7  self.dry                                    -> False (no real runner)

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)`, exits non-zero
on any fail.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # ctx/grants/trunk substrate
sys.path.insert(0, HERE)                                 # core/*.py

import jobs                                   # noqa: E402 — engine/jobs.py, the ONE seam this rig stubs
from engine import Engine                     # noqa: E402 — core/engine.py, THE MODULE UNDER TEST

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _mk_eng(dry=False, now=None):
    """A real Engine WITHOUT the heavy boot — `_worker_working` reads only
    `self.dry` (+ the module-level `jobs`), so `__new__` + the two attrs suffice."""
    eng = Engine.__new__(Engine)
    eng.dry = dry
    if now is not None:
        eng._now = now
    return eng


def _install_jobs(rec, alive=True):
    """Point `engine.jobs.find`/`is_alive` at a single chosen record."""
    jobs.find = lambda wid, idx=None: rec
    jobs.is_alive = lambda wid, idx=None: alive


def main():
    real_find, real_is_alive = jobs.find, jobs.is_alive
    try:
        now = time.time()

        # W1 — working, deadline in the future -> True
        _install_jobs({"state": "working", "deadline": now + 100})
        ok("W1: working + future deadline -> working",
           _mk_eng()._worker_working("w") is True)

        # W2 — working, deadline in the past -> False (the bound)
        _install_jobs({"state": "working", "deadline": now - 1})
        ok("W2: working + PAST deadline -> not-working (the R1a bound)",
           _mk_eng()._worker_working("w") is False)

        # W3 — working, deadline None -> True (old behavior preserved)
        _install_jobs({"state": "working", "deadline": None})
        ok("W3: working + no deadline -> working (prior behavior preserved)",
           _mk_eng()._worker_working("w") is True)

        # W4 — non-working state -> False
        _install_jobs({"state": "idle", "deadline": None})
        ok("W4: idle -> not-working",
           _mk_eng()._worker_working("w") is False)

        # W5 — not alive -> False (deadline irrelevant)
        _install_jobs({"state": "working", "deadline": now + 100}, alive=False)
        ok("W5: dead runner -> not-working",
           _mk_eng()._worker_working("w") is False)

        # W6 — CLOCK-UNIT KILLER: past deadline, eng._now injected as epoch MINUTES.
        # A wrong `self._now() < deadline` would read minutes(~2.9e7) < seconds(~1.7e9)
        # == True (working forever). Correct raw-time.time() reads past -> False.
        _install_jobs({"state": "working", "deadline": now - 1})
        eng_min = _mk_eng(now=lambda: time.time() / 60.0)
        ok("W6: past deadline w/ minutes _now injected -> STILL not-working "
           "(raw time.time, not self._now)",
           eng_min._worker_working("w") is False)

        # W7 — dry -> False (no real runner)
        _install_jobs({"state": "working", "deadline": now + 100})
        ok("W7: dry -> not-working (report-only ladder governs)",
           _mk_eng(dry=True)._worker_working("w") is False)
    finally:
        jobs.find, jobs.is_alive = real_find, real_is_alive

    passed = sum(1 for _, c, _ in _results if c)
    total = len(_results)
    for name, cond, detail in _results:
        mark = "ok  " if cond else "FAIL"
        line = f"  [{mark}] {name}"
        if detail and not cond:
            line += f"  -- {detail}"
        print(line)
    print(f"\nworker_working_rig: PASS ({passed}/{total})" if passed == total
          else f"\nworker_working_rig: FAIL ({passed}/{total})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
