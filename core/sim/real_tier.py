"""core.sim.real_tier — the L3 real-worker WIRING (wave 15): routes `core.
engine.Engine`'s two process-spawn seams (`_spawn_worker`/`_spawn_architect`,
both of which call `engine.jobs.spawn_runner` for real already — see `core/
engine.py`'s own docstring, "The two REAL process-touching seams") to a REAL
`worker_runner.py` OS process, adapter-selectable (`host-cli` for an actual
L3 run, `echo` for a token-free transport smoke) — instead of the "rig plays
the worker, never spawns a real agent" no-op stub every `core/*_rig.py` /
`core.sim.run.run_sim`'s own scripted tier installs.

Free-text worker REPORTS need NO wiring here at all: `core/snapshot.py::
build`'s observe pass already calls `core.classify.classify` (real `engine.
judge.call`) unconditionally on every drained free-text line — nothing in
this whole `core/` stack stubs that short of `TRON_JUDGE_STUB`, which this
module never sets (`core/classify.py`'s own docstring). So "the real tier"
reduces to exactly one seam: make `jobs.spawn_runner` calls REAL, adapter-
selectable, instead of recorded no-ops.

Why this needs its OWN wrapper rather than `core.engine.Engine` reaching
`jobs.spawn_runner` unmodified: `Engine._real_spawn` (`core/engine.py`) never
threads an `adapter=` kwarg through its own `jobs.spawn_runner(...)` call —
it relies on `engine/jobs.py`'s frozen-at-import `ADAPTER` env default
(`TRON_WORKER_ADAPTER`, read ONCE at import time, never re-read per call).
Editing `core/engine.py` to add an adapter param is out of scope (hard rule:
`core/*.py` behavior is unchanged this wave) — so this module wraps `jobs.
spawn_runner` itself (the SAME "wrap the one process-spawn seam" pattern
`core.sim.run`'s scripted tier already uses for its own no-op stub) with a
thin forwarder that injects the chosen adapter and otherwise calls straight
through to the REAL `engine.jobs.spawn_runner` — a REAL OS process spawns on
every call under this wiring; NOTHING about `core/engine.py`'s own code
changes.

HARD RULE (this wave): built + validated, never RUN with `adapter="host-cli"`
here (that would spawn a real `claude` process — a real-LLM fleet) — only
`adapter="echo"` may actually be exercised by this wave's own token-free
smoke (`core/sim/boot_real_scaffold_rig.py`), and even that is optional/
skippable. This module itself never decides to spawn anything; it only wires
the seam for whichever caller (a later, carefully-monitored L3 step, or this
wave's own bounded smoke) chooses to.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app worktree root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

import jobs   # noqa: E402 — engine/jobs.py, the ONE seam this module wraps (never stubs)

ADAPTERS = ("host-cli", "echo")


class RealTierError(ValueError):
    """tier="real" misconfigured (unknown adapter) — fails loud, never a
    silent fall-through to the host CLI's own ambient default adapter."""


def install(adapter="host-cli"):
    """Wrap `jobs.spawn_runner` so every call — from `Engine._spawn_worker`
    OR `Engine._spawn_architect`, the SAME single seam both already share —
    forwards to the REAL implementation with `adapter` forced to `adapter`
    (Engine's own call site never supplies one). Returns `(spawn_calls,
    restore)`: `spawn_calls` is a live list this wrapper appends
    `{worker_id, model, cwd, session_id, adapter}` to on every call (the
    SAME shape every `core/*_rig.py`'s own stub-spawn recorder already
    uses, so a caller's orphan-accounting code needs no new shape to
    handle); `restore()` puts the ORIGINAL `jobs.spawn_runner` back —
    the caller MUST call it once done (this module performs no cleanup of
    real processes itself; whoever chose to spawn them owns killing them,
    exactly like a live deployment would own its own fleet)."""
    if adapter not in ADAPTERS:
        raise RealTierError(
            f"core.sim.real_tier.install: adapter={adapter!r} not in {ADAPTERS!r}")

    real_spawn_runner = jobs.spawn_runner
    spawn_calls = []

    def _real_forward(worker_id, worker_dir, session_id, cwd=None,
                      runtime=None, adapter=None, model=None, settle_s=2.0):
        use_adapter = adapter or install_adapter
        spawn_calls.append({"worker_id": worker_id, "model": model, "cwd": cwd,
                            "session_id": session_id, "adapter": use_adapter})
        return real_spawn_runner(worker_id, worker_dir, session_id, cwd=cwd,
                                 runtime=runtime, adapter=use_adapter, model=model,
                                 settle_s=settle_s)

    install_adapter = adapter   # bound into the closure above by name lookup
    jobs.spawn_runner = _real_forward

    def restore():
        jobs.spawn_runner = real_spawn_runner

    return spawn_calls, restore


class real_spawn:
    """Context-manager convenience over `install`/`restore` — `with real_spawn
    ("echo") as rs:` installs on entry, restores on exit (even on an
    exception, so a smoke that raises mid-run never leaves the wrapper
    installed for whatever runs next in the SAME process). `rs.spawn_calls`
    is the SAME live list `install()` returns; `rs.teardown()` additionally
    releases + hard-kills every worker id this instance's own `spawn_calls`
    named, and returns the list of ids that were still alive before that
    (the caller's own orphan-accounting hook — see module docstring: this
    class does not call `teardown()` for you, `__exit__` only restores the
    `jobs.spawn_runner` seam, never touches a real process)."""

    def __init__(self, adapter="host-cli"):
        self.adapter = adapter
        self.spawn_calls = None
        self._restore = None

    def __enter__(self):
        self.spawn_calls, self._restore = install(self.adapter)
        return self

    def __exit__(self, *exc):
        if self._restore:
            self._restore()
        return False

    def teardown(self, timeout_s=8.0):
        """Release + (if still alive past `timeout_s`) hard-kill every
        worker id this wrapper ever spawned. Returns the list of ids that
        were still alive right before the hard-kill escalation (empty ==
        every worker released cleanly on its own)."""
        import time
        ids = sorted({c["worker_id"] for c in (self.spawn_calls or [])})
        for wid in ids:
            jobs.release(wid)
        deadline = time.time() + timeout_s
        still_alive = set(ids)
        while time.time() < deadline and still_alive:
            still_alive = {wid for wid in still_alive if jobs.is_alive(wid)}
            if still_alive:
                time.sleep(0.25)
        escalated = sorted(still_alive)
        for wid in escalated:
            jobs.kill_hard(wid)
        return escalated
