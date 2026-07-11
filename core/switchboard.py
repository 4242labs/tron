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

## Wave 19 (GAP-C, fleet-outage self-release) — the #2 risk for the first
real-LLM run: a real fleet WILL hit a systemic outage (quota/auth/credit
exhausted, host CLI down) where EVERY spawn dies, synchronously, the instant
it is attempted (`eng._spawn_worker` raises — the realistic shape of a CLI
that refuses to even launch, distinct from a worker that launches fine and
then goes SILENT, which stays `core/liveness.py`'s own time-based ladder,
untouched by this brick). `fill` (below) catches that exception right at the
mint-then-spawn call site, frees the just-minted worker slot (a genuine
retry candidate next `fill` call — never a permanently "dead" record no
other module here has vocabulary for) and bumps `manifest["fleet"]
["consecutive_deaths"]` (`_record_fleet_death`, reset to 0 by
`_record_fleet_progress` the instant an ordinary block-engineer spawn
genuinely succeeds: "outage clearing" IS a subsequent spawn succeeding, the
design's own words). Scoped to the ORDINARY block-dispatch spawn only — the
same fleet the design calls out (`worker_count`'s own pool); the rarer
cadence-reviewer spawn (`core/reviewers.py::dispatch`, unedited — out of
this brick's minimal-edit scope) shares the identical `eng._spawn_worker`
seam but is left unwrapped here, so no rig in this stack ever configures a
`cadence:` that could dispatch a reviewer during a simulated outage.

Past `fleet_outage_deaths` (`core/knobs.py`, the ONE knobs.yaml seam)
consecutive deaths, the engine SELF-RELEASES: `manifest["paused"]` flips
true and `fill` (this module) refuses to spawn ANYTHING further — no
runaway re-spawn loop, no burn to session-end, no silent death — while a
fleet-outage escalation is raised ARCHITECT-FIRST (`core/casestate.py::
open_case`, wave 18's own routing, reused verbatim, unedited — a block-less
case, `kind="fleet_outage"`, exactly the shape `core/casestate_rig.py`'s own
BL0 block-less slice already proves works) rather than an immediate operator
page; the architect's own `operator` verdict is what floors it onto the
operator (wave 17's `reping`, also reused verbatim, unedited — a
quota/auth outage is the operator's to fix, never the architect's or a
worker's). `_fleet_paused` (below) derives "is dispatch currently paused"
LIVE off `manifest["cases"]` every `fill` call — never a second, driftable
boolean of its own — so the operator's `resume` (`core/casestate.py::
settle`, unedited) or the architect resolving the case itself
(`architect_resolve`, unedited) lifts the pause the SAME tick either clears
the case: no `core/casestate.py` edit needed at all, and a SECOND, LATER
outage (after the first genuinely resolved) can still raise its own fresh
case — "one outage case at a time", never a permanent one-shot latch.

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
import reviewers  # noqa: E402 — core/reviewers.py, wave 10's cadence-PULL reviewer dispatch
import casestate  # noqa: E402 — core/casestate.py, wave 18's architect-first raise-and-defer (unedited)
import knobs as knobs_mod   # noqa: E402 — core/knobs.py, the ONE knobs.yaml seam (fleet_outage_deaths)


def _agent_id(block):
    """Deterministic agent-id, minted BEFORE any process (adversary §11.3):
    reproducible from the block id alone, so a re-tick that (for whatever
    reason) reconsiders the same block always mints the SAME identity —
    never a second/duplicate identity for one dispatch."""
    return f"engineer-{block}"


def _fleet_paused(manifest):
    """Wave 19 (GAP-C): True while a still-open fleet-outage case sits on
    file — derived LIVE off `manifest["cases"]`, never a second, driftable
    boolean of its own (see module docstring). `core/architect.py` carries
    an IDENTICAL, deliberately duplicated helper (never imported — keeps
    that module's own dependency direction unchanged) so its own
    clear-ahead forward-job scan honors the SAME pause."""
    return any(c.get("kind") == "fleet_outage" and c.get("decision") is None
              for c in (manifest.get("cases") or {}).values())


def _record_fleet_death(eng, manifest, agent_id, block_id, exc):
    """Wave 19 (GAP-C): one fleet-wide spawn-then-immediate-death event —
    bumps `manifest["fleet"]["consecutive_deaths"]` and, past
    `fleet_outage_deaths` (`core/knobs.py`), self-releases: pauses dispatch
    + raises the ONE fleet-outage escalation, architect-first (never a
    second one while this one is still open — guarded by `_fleet_paused`,
    never a separate latch that could go stale)."""
    fleet = manifest.setdefault("fleet", {"consecutive_deaths": 0, "total_deaths": 0,
                                          "outage_case_id": None, "deaths": []})
    fleet["consecutive_deaths"] = fleet.get("consecutive_deaths", 0) + 1
    fleet["total_deaths"] = fleet.get("total_deaths", 0) + 1
    fleet.setdefault("deaths", []).append(
        {"agent_id": agent_id, "block": block_id, "error": repr(exc)})
    eng.log("flow", f"switchboard: SPAWN FAILED for {agent_id} (block={block_id!r}): "
                    f"{exc!r} — worker slot freed (a genuine retry next fill, never a "
                    f"permanently-dead record); fleet consecutive_deaths="
                    f"{fleet['consecutive_deaths']}")

    threshold = knobs_mod.load(eng.ctx).fleet_outage_deaths
    if fleet["consecutive_deaths"] < threshold or _fleet_paused(manifest):
        return

    detail = (f"fleet outage: {fleet['consecutive_deaths']} consecutive worker "
             f"spawn-then-immediate-death events (>= fleet_outage_deaths="
             f"{threshold}) — self-releasing: dispatch PAUSED (spawning "
             f"NOTHING further, never re-spawning into the outage), escalated "
             f"ARCHITECT-FIRST (never an immediate operator page, never a "
             f"silent death, never burned to session-end)")
    case_id = casestate.open_case(eng, manifest, None, "fleet.outage", detail,
                                  worker_id=None, kind="fleet_outage")
    fleet["outage_case_id"] = case_id
    manifest["paused"] = True
    eng.log("operator", f"switchboard: FLEET OUTAGE — {detail} (case={case_id!r})")


def _record_fleet_progress(manifest):
    """Wave 19 (GAP-C): a spawn that genuinely SUCCEEDED — "outage clearing"
    IS a subsequent spawn succeeding (the design's own words) — resets the
    consecutive-death counter. Deliberately NOT gated on `_fleet_paused`:
    while paused, `fill` (below) never even attempts a spawn, so this is
    only ever reached post-resume, exactly where the reset belongs."""
    fleet = manifest.setdefault("fleet", {"consecutive_deaths": 0, "total_deaths": 0,
                                          "outage_case_id": None, "deaths": []})
    if fleet.get("consecutive_deaths"):
        fleet["consecutive_deaths"] = 0


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


def fill(eng, snapshot, view=None):
    """Fill every free worker slot with a fresh SPAWN. Returns the list of
    agent-ids freshly spawned this call (empty if no free slot or nothing
    dispatchable) — a NON-durable convenience for the caller/rig, exactly
    like `core.tick.tick`'s own return value; the manifest write is the only
    durable record.

    `view` (wave 6) is an optional pre-fetched `core.pipeline.read_view(eng)`
    result — pass it to reuse the SAME trunk-pinned pipeline read
    `core/tick.py` also threads through `core/session.py::check` this tick,
    instead of this call minting its OWN second trunk read/snapshot.
    Omitted, `pipeline.dispatchable` fetches its own (unchanged behavior).

    Wave 10 (`core/reviewers.py`): priority is a DUE cadence reviewer
    BEFORE the next block by pipeline order (blueprint §1 SWITCHBOARD's own
    priority — adhoc is a later-wave addition, unchanged note from wave 5).
    A reviewer SHARES this same free-slot pool (`reviewers.dispatch`
    records a `manifest["workers"]` entry exactly like an engineer spawn
    below, so `_active_worker_count` already accounts for it with no
    change to that helper) — never a second slot-accounting mechanism. A
    project with no `cadence` configured at all (every rig before this
    wave) sees `reviewers.due_type` return `None` every call — a no-op,
    this whole arm falls through unchanged to the block-dispatch loop."""
    manifest = snapshot.manifest
    workers = manifest.setdefault("workers", {})

    # ── Wave 19 (GAP-C): the fleet-outage self-release — spawn NOTHING new
    #     while a fleet-outage case sits open (never re-spawning into the
    #     outage; see module docstring). Checked FIRST, before any free-slot
    #     accounting — a pause means zero dispatch, not a partial one. ──
    if _fleet_paused(manifest):
        manifest["paused"] = True
        return []
    manifest["paused"] = False

    worker_count = max(1, int(eng.paths.get("worker_count", 1) or 1))

    free = worker_count - _active_worker_count(manifest)
    if free <= 0:
        return []

    spawned = []
    while free > 0:
        typ = reviewers.due_type(eng, manifest)
        if not typ:
            break
        spawned.append(reviewers.dispatch(eng, manifest, typ))
        free -= 1
    if free <= 0:
        return spawned

    candidates = pipeline.dispatchable(eng, manifest, view=view)

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
        try:
            eng._spawn_worker(agent_id, block["id"])   # STUBBED — no real process
        except Exception as exc:
            # Wave 19 (GAP-C): a SYNCHRONOUS spawn-time failure (quota/auth/
            # credit exhausted, host CLI down) — distinct from a worker that
            # spawns fine and later goes silent (`core/liveness.py`'s own
            # ladder, untouched). Free the slot (a genuine retry candidate,
            # never a permanently-"dead" record) and count it toward the
            # fleet-outage signal; NEVER re-raise — the tick continues.
            workers.pop(agent_id, None)
            _record_fleet_death(eng, manifest, agent_id, block["id"], exc)
            free -= 1
            if _fleet_paused(manifest):
                manifest["paused"] = True
                break
            continue
        _record_fleet_progress(manifest)
        # PMT-SPAWN needs role + persona slots to render (the worker's first
        # contact — it carries the report-channel + contract + persona the
        # agent reads). Resolve the REAL role/persona off roles.yaml when the
        # engine exposes it (a real `Engine`); a rig `MiniEng` has no roles
        # config, falls back to role="engineer"/persona="" and, shipping no
        # canon, renders the fallback text anyway (unchanged).
        _role, _persona = "engineer", ""
        if callable(getattr(eng, "_roles_config", None)):
            try:
                _role = eng._resolve_role_for_block(block["id"]) or "engineer"
                _persona = eng._roles_config().persona_for(_role) or ""
            except Exception:   # noqa: BLE001 — never let role resolution block a spawn
                _role, _persona = "engineer", ""
        eng.emit(
            "spawn.worker",
            f"[TRON]  {agent_id} — you're spawned for block {block['id']}. "
            f"Report online with your OWN feature branch name (a structured "
            f"`worker.online` report carrying `worker.branch`) — I assign "
            f"the work the moment you do.",
            slots={"role": _role, "persona": _persona},
            worker_id=agent_id,
            kind="PMT-SPAWN")
        eng.log("flow", f"switchboard: spawned {agent_id} for block "
                        f"{block['id']!r} (identity-only; ASSIGN awaits "
                        f"worker.online)")
        spawned.append(agent_id)
        free -= 1

    return spawned
