"""core.sim.run — `run_sim(...)`, the reusable L2 driver (wave 14, ADR-0004
§11.5): seed the fresh real-git mockup (`core.sim.scaffold`) -> `core.engine.
Engine(ctx).start(...)` -> loop `Engine.tick()` while playing the scripted
workers/architect/reviewer (`core.sim.worker.ScriptedDriver`) -> stop at a
clean session-end or the tick cap -> a structured result. This is the WHOLE
point of this brick: a single reusable entrypoint any caller (this wave's
own `sim_l2_rig.py`, a future scenario module) hands a block list + knobs to,
never re-deriving the seed/drive/observe wiring itself.

REAL git surface throughout (via `core.engine.Engine`, which routes every
git observation through `core.gitobs`, and `core.sim.worker`'s own real
`git`/`land.sh` calls playing the worker's terminal); NO real worker
process — `engine.jobs.spawn_runner` is monkeypatched to a no-op recorder for
the ENTIRE call (restored in `finally`, exactly the established "rig plays
the worker, never spawns a real agent" pattern every `core/*_rig.py` already
uses) — and NO LLM anywhere in this module.

This module itself does ZERO raw git / subprocess calls of its own — every
git-observing read goes through `core.gitobs` (`tip_sha`, for the idempotent-
replay check) or `core.engine.Engine`/`core.state` (`Engine.start`/`.tick`,
`state.load`); the ONLY things that touch git directly are `core.sim.
scaffold` (fixture construction) and `core.sim.worker` (the scripted
worker's own terminal commands) — see each module's own docstring.

`tier="scripted"` is the only tier this wave implements (the ONE the hard
rules scope this brick to: NO real worker processes, NO LLM) — the seam is
named now so L3 can swap in a real-worker tier on this SAME driver without
another rewrite; any other value fails loud rather than silently falling
back to scripted."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))          # core/sim
_CORE_DIR = os.path.dirname(_HERE)                            # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                          # tron-app worktree root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
# Unconditional, in this exact order (mirrors core/engine_rig.py's own
# convention verbatim): engine dir first, then core dir — core dir must
# win on the bare name "engine" (shadowing engine/engine.py's CLI script)
# for `from engine import Engine` below to resolve to core/engine.py.
# A caller (core/sim/sim_l2_rig.py) that already inserted core dir BEFORE
# this module loads must not short-circuit this ordering on an "already
# present" guard — re-inserting at position 0 is what fixes the order,
# not a redundant no-op.
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import jobs                       # noqa: E402 — engine/jobs.py, the ONE seam this driver stubs
import state                       # noqa: E402 — core/state.py
import gitobs                       # noqa: E402 — core/gitobs.py, the ONE git-observation seam
from engine import Engine, BootupError   # noqa: E402 — core/engine.py, the module this drives

import scaffold as sim_scaffold    # noqa: E402 — core/sim/scaffold.py
import worker as sim_worker         # noqa: E402 — core/sim/worker.py

MAIN = "main"
DEFAULT_MAX_TICKS = 200


class SimTierError(ValueError):
    """`run_sim(tier=...)` named something other than `"scripted"` — fails
    loud rather than silently falling back (this wave implements exactly
    one tier)."""


def run_sim(blocks, knobs=None, worker_count=1, tier="scripted", max_ticks=DEFAULT_MAX_TICKS,
           test_command=None, transcript=None, scope="all", models=None,
           pipeline_rel=sim_worker.PIPELINE_REL, blocks_rel=sim_worker.BLOCKS_REL):
    """Seed a fresh real-git mockup for `blocks` (`core.sim.scaffold.build`),
    boot `core.engine.Engine` over it, and drive it to a clean session-end
    (or `max_ticks`) by playing scripted workers/architect/reviewer each
    tick (`core.sim.worker.ScriptedDriver`). Returns a structured result
    dict — see the fields set below; nothing durable this function itself
    owns (the manifest/real git ARE the durable record, exactly like every
    `core/*_rig.py` before it).

    `knobs` (optional dict): `cadence` ({<type>: <threshold>}), `worker_count`
    (informational — the `worker_count` PARAM above is what actually governs
    the pool), `silence_ping_min`/`silence_escalate_min`, `grant_ttl` — all
    optional, `core.sim.scaffold.write_knobs`'s own defaults apply when
    omitted.

    `transcript` (optional `core.sim.worker.Transcript`) — the ONE seam a
    caller overrides to author specific (or deliberately BROKEN) code per
    block; defaults to `core.sim.worker.default_transcript()` (every block
    gets a small, generic, CORRECT function)."""
    if tier != "scripted":
        raise SimTierError(f"core.sim.run.run_sim: tier={tier!r} not implemented — "
                           f"only 'scripted' exists at this wave (no real workers, no LLM)")

    knobs = knobs or {}
    ctx, root = sim_scaffold.build(
        blocks, test_command=test_command, cadence=knobs.get("cadence"),
        worker_count=worker_count,
        silence_ping_min=knobs.get("silence_ping_min", sim_scaffold.DEFAULT_SILENCE_PING_MIN),
        silence_escalate_min=knobs.get("silence_escalate_min", sim_scaffold.DEFAULT_SILENCE_ESCALATE_MIN),
        grant_ttl=knobs.get("grant_ttl", sim_scaffold.DEFAULT_GRANT_TTL))
    grants_dir = ctx.grants_dir
    transcript = transcript or sim_worker.default_transcript()
    driver = sim_worker.ScriptedDriver(root, grants_dir, ctx, transcript,
                                       pipeline_rel=pipeline_rel, blocks_rel=blocks_rel)

    # ── stub the ONE process-spawn seam — never a real `claude` process,
    #     matching every `core/*_rig.py`'s established "rig plays the
    #     worker, never spawns a real agent" convention. Both engineer/
    #     reviewer spawns AND the persistent architect's own spawn go
    #     through this SAME call. ──
    spawn_calls = []

    def _fake_spawn_runner(worker_id, worker_dir, session_id, cwd=None,
                           runtime=None, adapter=None, model=None, settle_s=2.0):
        spawn_calls.append({"worker_id": worker_id, "model": model, "cwd": cwd,
                            "session_id": session_id})
        return {}

    real_spawn_runner = jobs.spawn_runner
    jobs.spawn_runner = _fake_spawn_runner

    release_calls = []
    real_release = jobs.release

    def _wrapped_release(worker_id, idx=None):
        release_calls.append(worker_id)
        return real_release(worker_id, idx=idx)

    jobs.release = _wrapped_release

    try:
        eng = Engine(ctx)
        eng.dry = False   # HARD RULE: real trunk observation throughout

        try:
            spawned_at_boot = eng.start(scope=scope, worker_count=worker_count, models=models or {})
        except BootupError:
            raise

        history = []
        i = -1
        session_ended_tick = None
        for i in range(max_ticks):
            res = eng.tick()
            manifest = state.load(ctx)
            history.append({
                "i": i, "outcomes": dict(res.get("outcomes") or {}),
                "spawned": list(res.get("spawned") or []),
                "nudged": list(res.get("nudged") or []),
                "escalated": list(res.get("escalated") or []),
                "session_end": res.get("session_end"),
            })
            driver.record_done_ticks(i, res.get("outcomes") or {})
            driver.react(i, manifest)
            if res.get("session_end") is not None and session_ended_tick is None:
                session_ended_tick = i
                break
        ticks_used = i + 1

        final_manifest = state.load(ctx)

        idempotent = None
        if session_ended_tick is not None:
            pre_bytes = open(ctx.state, "rb").read()
            pre_main = gitobs.tip_sha(root, MAIN, False)
            pre_spawn_n = len(spawn_calls)
            replay = eng.tick()
            post_bytes = open(ctx.state, "rb").read()
            post_main = gitobs.tip_sha(root, MAIN, False)
            idempotent = {
                "ok": (replay.get("session_end") == final_manifest.get("session")
                      and replay.get("spawned") == [] and replay.get("outcomes") == {}
                      and len(spawn_calls) == pre_spawn_n
                      and post_bytes == pre_bytes and post_main == pre_main),
                "replay": replay,
            }

        # Orphan check (hard rule: NO real worker process ever exists in this
        # driver — `jobs.spawn_runner` is stubbed above for the whole call —
        # so this asserts that for real, off the SAME production registry
        # reader (`engine.jobs.is_alive`) a live deployment's own reaper
        # would use, rather than assuming it from the stub alone).
        orphan_ids = sorted({c["worker_id"] for c in spawn_calls})
        orphans = [wid for wid in orphan_ids if jobs.is_alive(wid)]

        return {
            "root": root, "ctx": ctx, "grants_dir": grants_dir, "eng": eng,
            "blocks": blocks, "worker_count": worker_count, "max_ticks": max_ticks,
            "ticks_used": ticks_used, "session_ended_tick": session_ended_tick,
            "session_end": final_manifest.get("session"),
            "final_manifest": final_manifest, "history": history, "driver": driver,
            "escalations": final_manifest.get("escalations") or [],
            "cases": final_manifest.get("cases") or {},
            "spawn_calls": spawn_calls, "release_calls": release_calls,
            "orphans": orphans, "orphan_count": len(orphans),
            "idempotent": idempotent, "spawned_at_boot": spawned_at_boot,
        }
    finally:
        jobs.spawn_runner = real_spawn_runner
        jobs.release = real_release
