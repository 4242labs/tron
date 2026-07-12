"""core.pipeline — the deterministic pipeline reader (no LLM): the front end
`core/switchboard.py`'s SPAWN arm reads to pick the next block, and (wave 6)
`core/session.py`'s clean-terminal check reads to know the FULL in-scope
picture.

`read_view(eng) -> (view, trunk_sha)` is the ONE trunk-pinned git read this
module performs (via `core.gitobs.read_pipeline_view` — the ONE seam; NO raw
git and no `import trunk`/`import reader` of this module's own). A caller
that needs BOTH `dispatchable` (below) and a scope/session read in the SAME
tick fetches `view` once here and threads it through both — never two
separate trunk reads (and two separate `git archive` snapshots) for what is,
within one bounded tick, the same pinned trunk tip.

`dispatchable(eng, manifest, view=None) -> [block, ...]` returns the blocks a
caller may dispatch THIS tick, in living-doc (pipeline-file) ORDER: canon
§7's rule — status `📋` (a block file present and `to-do`), every
`Depends on` already `✅` on trunk, and NOT already in-flight. `view` is
optional (defaults to a fresh `read_view(eng)` call, unchanged pre-wave-6
behavior) — pass a pre-fetched view to avoid a second trunk read.

"In-flight" is a MANIFEST read only (never re-derived from git): a block
counts as in-flight when it has an open (non-terminal) gate in
`manifest["gates"]`, OR a worker record in `manifest["workers"]` naming it
whose block has no gate yet (the SPAWNED-but-not-yet-ASSIGNED window —
`core/switchboard.py`'s own two-step handshake, T3/D1 of
`contracts/rebuild-spec.md`). This is exactly blueprint-contracts.md §1's "a
live worker OR an open landing OR a gate" — an open gate already covers the
"live worker" and "open landing" cases once ASSIGN has fired (a gate's own
stage IS the ladder, `gate.merge` included); the pre-ASSIGN worker record
covers the window before a gate exists at all. Once a gate closes (✅ landed,
replica clean, slot released), the SAME block's status flips to `done` on
trunk via the record commit, so it drops out of `to-do` on its own — no
separate "was once in-flight" bookkeeping needed.

Fail-loud, never a guess: `core.gitobs.read_pipeline_view` raises on an
unresolvable trunk tip or a failed snapshot; this module does not catch that
— a caller (`core/switchboard.py`, ultimately `core/tick.py`) that wants a
softer fallback makes that choice explicitly, never buried here.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gitobs   # noqa: E402 — core/gitobs.py, the ONE git-observation seam

DISPATCHABLE_STATUS = "to-do"
_TERMINAL_GATE_STAGES = ("closed", "escalated")


def block_landed_closed(manifest, block):
    """True iff `block`'s gate reached the terminal CLOSED stage — landed +
    closed out on trunk. Durable: `core/gate.py` sets `stage="closed"` at close
    and does NOT pop the gate (only case-resolution `_drop_gate_and_worker`
    pops), so this survives branch teardown — unlike branch-ancestry, which
    reads a deleted ref. NOT `"escalated"` (also terminal, but NOT landed).
    ADR-0008 stale-wall revalidation primitive."""
    if not block:
        return False
    return ((manifest.get("gates") or {}).get(block) or {}).get("stage") == "closed"


def _is_landing_wall(detail):
    """A land.sh-refusal signature in a wall's free-text detail. Additive and
    fail-safe: a landing wall whose text misses the signature simply pages
    (ADR-0008 §3.2), so this only ever NARROWS suppression to genuine landing
    walls — a dep-cycle / untestable-AC wall never matches."""
    d = (detail or "").lower()
    return "land.sh" in d or ("land" in d and ("grant" in d or "refus" in d
                                               or "content mismatch" in d))


def stale_landing_wall(manifest, source, worker_id, detail):
    """ADR-0008: True iff a `worker.wall` is a LANDING wall now moot — the
    raising `engineer-<block>` worker's block has closed out on trunk. Every
    unresolvable input fails TOWARD paging (returns False): a non-worker.wall
    source, a non-`engineer-` worker (an architect self-escalation carries
    ARCHITECT_WID → never suppressed), a detail without a landing signature, or
    a block whose gate is not `"closed"`. The one signal it trusts — the gate
    stage — is durable across branch teardown and correct in live and dry."""
    if source != "worker.wall":
        return False
    wid = worker_id or ""
    if not wid.startswith("engineer-"):
        return False
    if not _is_landing_wall(detail):
        return False
    return block_landed_closed(manifest, wid[len("engineer-"):])


def in_flight_blocks(manifest):
    """Block ids in-flight per the manifest alone (see module docstring):
    every non-terminal gate's block, plus every worker's block that has no
    gate yet (spawned, awaiting its own `worker.online`+`worker.branch`
    ASSIGN). Exported (not `_`-private) because `core/switchboard.py`'s own
    free-slot count needs the IDENTICAL definition of "in-flight" — one
    block occupies exactly one slot, whether or not that block's gate
    happens to have a matching `manifest["workers"]` entry (a gate seeded
    directly, bypassing SPAWN entirely — `core/tick_rig.py`'s own wave-4
    fixture is exactly this shape — must still count as occupying a slot;
    never assume every gate has a switchboard-recorded worker behind it)."""
    gates = manifest.get("gates") or {}
    inflight = {block for block, gstate in gates.items()
               if gstate.get("stage") not in _TERMINAL_GATE_STAGES}
    for w in (manifest.get("workers") or {}).values():
        block = w.get("block")
        if block and block not in gates:
            inflight.add(block)
    return inflight


def read_view(eng):
    """The ONE trunk-pinned pipeline+blocks read (`core.gitobs.
    read_pipeline_view`) — resolves `pipeline_rel`/`blocks_rel`/
    `trunk_snapshot_dir` off `eng.paths`/`eng.ctx` exactly as `dispatchable`
    always has, factored out so a caller (`core/tick.py`) can fetch it once
    and thread it through both `dispatchable` and `core/session.py::check`
    within the same bounded tick. Fail-loud, never a guess (unchanged from
    before this refactor): raises on an unresolvable trunk tip or a failed
    snapshot — this module does not catch that."""
    root = eng.paths["root"]
    main_branch = eng.paths.get("main_branch", "main")
    pipeline_rel = eng.paths.get("pipeline_rel") or "meta/pipeline.md"
    blocks_rel = (eng.paths.get("blocks_rel") or "meta/blocks/").rstrip("/")
    snapshot_dir = eng.ctx.trunk_snapshot_dir
    return gitobs.read_pipeline_view(
        root, main_branch, pipeline_rel, blocks_rel, snapshot_dir, eng.dry)


def dispatchable(eng, manifest, view=None):
    """Deterministic pipeline read -> the blocks eligible for SWITCHBOARD to
    dispatch this tick, in pipeline (living-doc) ORDER. Each entry:
    `{"id", "block_file" (repo-relative, e.g. "meta/blocks/01-02.md"),
    "title", "depends_on", "order"}`. `block_file` is resolved here (never
    guessed downstream): the pipeline row's own `Block \\`blocks/<file>\\``
    Notes reference when present, else `<id>.md` under the project's
    `blocks_rel` — the SAME fallback `engine/reader.py::load` itself applies
    when a row is matched by id rather than an explicit file ref.

    `view` is optional — pass a pre-fetched `read_view(eng)` result to reuse
    the SAME trunk-pinned read a caller already made this tick; omitted, this
    fetches its own (unchanged pre-wave-6 behavior, one read per call)."""
    if view is None:
        view, _trunk_sha = read_view(eng)

    blocks_rel = (eng.paths.get("blocks_rel") or "meta/blocks/").rstrip("/")
    status_idx = {row["id"]: row.get("status") for row in view}
    inflight = in_flight_blocks(manifest)

    out = []
    for row in view:
        if not row.get("has_block_file"):
            continue
        if row.get("status") != DISPATCHABLE_STATUS:
            continue
        if row["id"] in inflight:
            continue
        deps = row.get("depends_on") or []
        if not all(status_idx.get(dep) == "done" for dep in deps):
            continue
        fname = row.get("block_file") or f"{row['id']}.md"
        out.append({
            "id": row["id"],
            "block_file": f"{blocks_rel}/{fname}",
            "title": row.get("task"),
            "depends_on": deps,
            "order": row.get("order"),
        })
    return out
