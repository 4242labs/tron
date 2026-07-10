"""core.router — structured routing (NO LLM/classify in this brick): the
ASSIGN half of the two-step spawn->online->assign handshake
(`contracts/rebuild-spec.md` C1/D1; `blueprint-contracts.md` §5's "Branch
ownership" rule). `core/switchboard.py` owns SPAWN (identity-only); this
module drains this tick's structured `tag`+`slots` worker reports
(`core/snapshot.py`'s own drain — a `worker.online` line IS the online
report, read structurally, exactly like `worker.done` already is for the
DONE-gate's local-pass report) and, for each well-formed `worker.online`
report, ASSIGNS: opens the block's gate at `gate.local`, bound to the
worker's OWN REPORTED branch (`worker.branch`, carried in the report's
`slots` — NEVER a guessed `feat/<block>`; the worker names its own branch,
the engine only ever records the name it reports).

Real classify (`classify_message`, the sole LLM entrypoint per T2 of
`rebuild-spec.md`) is a later wave, pinned to the observe phase — this
router only ever acts on an ALREADY-STRUCTURED `tag`+`slots` shape, same
discipline `core/snapshot.py`'s `local_reports` drain already keeps for
`worker.done`.

State-guarded, idempotent: a report for an agent-id with no matching
"spawning" worker record (unknown, already assigned, or already released) —
or naming a block that already has an open gate — is dropped (logged, never
raised); a duplicate/late-arriving `worker.online` after ASSIGN already fired
is therefore a correct no-op, never a second gate for the same block.

No git/subprocess of any kind here; the ONE mutation is a manifest write
(`core/gate.py::new_state_full`, the SAME full-ladder constructor
`core/gate_full_rig.py`/`core/tick_rig.py` already use) — no raw git, no
`core.gitobs` call of its own (the gate's own OWN stage machinery does all
git observation from here on, via `core.gate.advance`).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gate   # noqa: E402 — core/gate.py, the DONE-ladder constructor this ASSIGN opens


def route(eng, manifest, worker_reports):
    """One observe-phase pass over this tick's drained worker reports: act on
    every well-formed `worker.online` line; anything else (local-pass
    `worker.done` reports included) is `core/snapshot.py`'s own concern, fed
    to `core.gate.advance` separately by `core/tick.py` — never double-handled
    here."""
    workers = manifest.setdefault("workers", {})
    gates = manifest.setdefault("gates", {})

    for rep in worker_reports:
        if rep.get("tag") != "worker.online":
            continue
        agent_id = rep.get("agent_id")
        slots = rep.get("slots") or {}
        branch = slots.get("branch")
        if not agent_id or not branch:
            eng.log("flow", f"router: dropped a malformed worker.online report "
                            f"(agent_id={agent_id!r} branch={branch!r})")
            continue

        worker = workers.get(agent_id)
        if not worker:
            eng.log("flow", f"router: worker.online from unrecorded agent "
                            f"{agent_id!r} — no matching spawn, dropped")
            continue
        if worker.get("status") != "spawning":
            # Already assigned (or released) — a duplicate/late report;
            # never a second ASSIGN for the same worker.
            continue

        block = worker.get("block")
        block_file = worker.get("block_file")
        if block in gates:
            # Defensive: a gate already open for this block under a
            # different path — never overwrite an in-flight gate.
            eng.log("flow", f"router: block {block!r} already has an open "
                            f"gate — worker.online from {agent_id!r} ignored")
            continue

        gates[block] = gate.new_state_full(eng, block, block_file, branch, agent_id)
        worker["status"] = "busy"
        worker["branch"] = branch
        eng.log("flow", f"router: ASSIGN {agent_id!r} -> block {block!r} on "
                        f"its own reported branch {branch!r} (gate.local opened)")
