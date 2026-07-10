"""core.pipeline — the deterministic pipeline reader (no LLM): the front end
`core/switchboard.py`'s SPAWN arm reads to pick the next block.

`dispatchable(eng, manifest) -> [block, ...]` parses `pipeline.md` +
`blocks/<id>.md` OFF TRUNK (via `core.gitobs.read_pipeline_view` — the ONE
seam; NO raw git and no `import trunk`/`import reader` of this module's own)
and returns the blocks a caller may dispatch THIS tick, in living-doc
(pipeline-file) ORDER: canon §7's rule — status `📋` (a block file present and
`to-do`), every `Depends on` already `✅` on trunk, and NOT already in-flight.

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


def dispatchable(eng, manifest):
    """Deterministic pipeline read -> the blocks eligible for SWITCHBOARD to
    dispatch this tick, in pipeline (living-doc) ORDER. Each entry:
    `{"id", "block_file" (repo-relative, e.g. "meta/blocks/01-02.md"),
    "title", "depends_on", "order"}`. `block_file` is resolved here (never
    guessed downstream): the pipeline row's own `Block \\`blocks/<file>\\``
    Notes reference when present, else `<id>.md` under the project's
    `blocks_rel` — the SAME fallback `engine/reader.py::load` itself applies
    when a row is matched by id rather than an explicit file ref."""
    root = eng.paths["root"]
    main_branch = eng.paths.get("main_branch", "main")
    pipeline_rel = eng.paths.get("pipeline_rel") or "meta/pipeline.md"
    blocks_rel = (eng.paths.get("blocks_rel") or "meta/blocks/").rstrip("/")
    snapshot_dir = eng.ctx.trunk_snapshot_dir

    view, _trunk_sha = gitobs.read_pipeline_view(
        root, main_branch, pipeline_rel, blocks_rel, snapshot_dir, eng.dry)

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
