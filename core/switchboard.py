"""core.switchboard — SWITCHBOARD (ND-03), the SPAWN half of the two-step
spawn->online->assign handshake (`contracts/rebuild-spec.md` C1/D1;
`blueprint-contracts.md` §1). The ASSIGN half — creating the gate at the
worker's OWN reported branch, once it reports `worker.online` — lives in
`core/router.py`, fired off a later tick's inbox drain; this module never
creates a gate itself.

`fill(eng, snapshot)`: for each FREE worker slot (`eng.paths["worker_count"]`,
floor 1), pick the next dispatchable block (`core/pipeline.py::dispatchable`
— priority is next-by-pipeline-order; adhoc/cadence priority is a later-wave
addition, C1's own note this brick is scoped to "next-by-order is enough")
and SPAWN it: mint a DETERMINISTIC agent-id (reproducible from the block id
alone — never random/uuid, adversary §11.3) and record the worker into
`snapshot.manifest["workers"]` with `status="spawning"` BEFORE calling
`eng._spawn_worker` (the process-spawn hook — STUBBED in this brick, no real
`claude` process; a duck-typed side-effect call exactly like `eng.
_to_worker`/`eng._release_worker` in `core/gate.py`, opaque to this module,
never touched directly), then sends the identity-only order via
`eng._to_worker` (a `PMT-SPAWN`-equivalent — structured, deterministic,
composed here, never an LLM call).

State-guarded, idempotent across ticks AND within one `fill` call:
`pipeline.dispatchable` itself excludes any block already in-flight (a live
worker awaiting ASSIGN, or an open gate — `core/pipeline.py`'s own contract),
so a block already dispatched — this tick or a prior one — is never re-picked
here; a defensive check against the deterministic agent-id itself (an
unexpected collision) additionally refuses to ever overwrite an existing
worker record.

No git/subprocess of any kind here — the ONE read (`pipeline.dispatchable`)
goes through `core.gitobs`; the ONE write is a plain manifest mutation, the
same "gates is a direct alias onto the manifest" idiom `core/snapshot.py`
already uses for gate state.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import pipeline   # noqa: E402 — core/pipeline.py, the dispatch-eligible read + in-flight count


def _agent_id(block):
    """Deterministic agent-id, minted BEFORE any process (adversary §11.3):
    reproducible from the block id alone, so a re-tick that (for whatever
    reason) reconsiders the same block always mints the SAME identity —
    never a second/duplicate identity for one dispatch."""
    return f"engineer-{block}"


def _active_worker_count(manifest):
    """How many worker slots are currently occupied — ONE in-flight block
    (`core/pipeline.py::in_flight_blocks`, the SAME definition dispatch
    eligibility itself uses) == one occupied slot. Deliberately NOT a count
    of `manifest["workers"]` entries alone: a gate can be in-flight with no
    matching worker record at all (seeded directly, bypassing SPAWN — e.g.
    `core/tick_rig.py`'s own wave-4 fixture) and must still occupy a slot; a
    CLOSED/ESCALATED gate's block, conversely, is freed the SAME tick it
    closes (PULSE's own ordering, blueprint-contracts.md §5)."""
    return len(pipeline.in_flight_blocks(manifest))


def fill(eng, snapshot):
    """Fill every free worker slot with a fresh SPAWN. Returns the list of
    agent-ids freshly spawned this call (empty if no free slot or nothing
    dispatchable) — a NON-durable convenience for the caller/rig, exactly
    like `core.tick.tick`'s own return value; the manifest write is the only
    durable record."""
    manifest = snapshot.manifest
    workers = manifest.setdefault("workers", {})
    worker_count = max(1, int(eng.paths.get("worker_count", 1) or 1))

    free = worker_count - _active_worker_count(manifest)
    if free <= 0:
        return []

    candidates = pipeline.dispatchable(eng, manifest)

    spawned = []
    for block in candidates:
        if free <= 0:
            break
        agent_id = _agent_id(block["id"])
        if agent_id in workers:
            # A deterministic id already on file for this block should be
            # structurally unreachable here (pipeline.dispatchable already
            # excludes any in-flight block) — defensive only: never
            # overwrite an existing worker record.
            eng.log("flow", f"switchboard: {agent_id} already recorded — "
                            f"refusing to re-spawn for block {block['id']!r}")
            continue

        # Mint + record BEFORE any process (adversary §11.3): the manifest
        # write happens first, so even a crash between here and the
        # `eng._spawn_worker` stub below leaves a real, re-derivable
        # "spawning" record a later tick's `pipeline.dispatchable` still
        # treats as in-flight — never a double-spawn on replay.
        workers[agent_id] = {
            "block": block["id"],
            "block_file": block["block_file"],
            "status": "spawning",
            "branch": None,
        }
        eng._spawn_worker(agent_id, block["id"])   # STUBBED — no real process
        eng._to_worker(
            agent_id,
            f"[TRON]  {agent_id} — you're spawned for block {block['id']}. "
            f"Report online with your OWN feature branch name (a structured "
            f"`worker.online` report carrying `worker.branch`) — I assign "
            f"the work the moment you do.",
            "PMT-SPAWN")
        eng.log("flow", f"switchboard: spawned {agent_id} for block "
                        f"{block['id']!r} (identity-only; ASSIGN awaits "
                        f"worker.online)")
        spawned.append(agent_id)
        free -= 1

    return spawned
