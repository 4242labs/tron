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
  C4  a breach on the LiveRunError (refused-boot) exception path -> STILL exit 3,
      never the try block's own exit 2 — the `finally` fires even there
  C5  no breach on the refused-boot path -> the ORIGINAL exit 2 is preserved
      (the self-proof does not override a clean refusal)

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on
fail.
"""
import os
import sys

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


def main():
    same = ("deadbeef" * 5, "")   # (head, status) — identical before/after == no breach
    changed_head = [("deadbeef" * 5, ""), ("cafebabe" * 5, "")]
    changed_status = [("deadbeef" * 5, ""), ("deadbeef" * 5, " M some/file.py\n")]

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

    n_pass = sum(1 for _, c, _ in _results if c)
    n_total = len(_results)
    for name, cond, detail in _results:
        mark = "PASS" if cond else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))
    print(f"live_containment_rig: PASS ({n_pass}/{n_total})")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
