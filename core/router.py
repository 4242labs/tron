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

Wave 9 (`core/architect.py`) adds ONE more structured tag: `architect.
reconciled` (`{"tag": "architect.reconciled", "block": <block>}`) — the
architect's own completion report for a `reconcile` job (M-05), drained and
routed exactly like every other structured report here. Malformed (no
`block`) is LOGGED and dropped, same forgiving discipline as an unknown
`worker.online` sender — this is an internal, engine-scripted signal, never
adversarial input. A well-formed one records the block into `manifest
["reconciled"]` (idempotent: already-reconciled is a no-op) — `core/
architect.py::advance` is what actually clears the architect's own
`current_job` off that record (see its own docstring for why that's a
SEPARATE step, positioned after `core/switchboard.py::fill`).

Wave 8 (`core/casestate.py`) adds TWO more structured tags this SAME pass
drains, each acted on exactly like `worker.online` above — no LLM/classify,
same discipline:

  `worker.wall` — a worker's structured wall report (`block`, `agent_id`,
  `slots.detail`). FAIL-LOUD on malformed (a `worker.wall` naming no block or
  carrying no detail RAISES — never a silent drop; a wall is exactly the
  kind of signal this whole brick exists to make sure never vanishes). A
  well-formed one opens a parked case via `core.casestate.open_case` — the
  raise-and-defer half of the design.

  `operator.decision` — the operator's reply to a parked case (`slots.
  case_id`, `slots.verb` ∈ resume|amend|abandon, optional `slots.note`).
  Malformed (no case_id, or an unrecognized verb) is LOGGED, never raised,
  never guessed at — `core.casestate.settle` itself handles an unknown/
  duplicate case_id the same forgiving way (a settle attempt is a REPLY, not
  a structural claim the router can validate up front the way a wall's own
  content can).

Wave 10 (`core/reviewers.py`) adds ONE more structured tag this SAME pass
drains: `worker.review_done` (`{"tag": "worker.review_done", "agent_id":
<id>, "type": <type>, "slots": {"findings": [...]}}`) — the DONE-REVIEW
gate's hand-back (first HOLDS/attest-coverage, second RELEASES + queues an
architect log-review), routed to `reviewers.on_review_done` exactly like
every other structured report here; that module owns its own malformed/
stale handling (logged, dropped, never a crash on an internal signal).

No git/subprocess of any kind here; the ONE mutation is a manifest write
(`core/gate.py::new_state_full`, the SAME full-ladder constructor
`core/gate_full_rig.py`/`core/tick_rig.py` already use, for ASSIGN — PLUS,
wave 8, whatever `core.casestate.open_case`/`.settle` themselves mutate, both
equally git-free plain-manifest writes) — no raw git, no `core.gitobs` call
of its own (the gate's own OWN stage machinery does all git observation from
here on, via `core.gate.advance`).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gate        # noqa: E402 — core/gate.py, the DONE-ladder constructor this ASSIGN opens
import casestate    # noqa: E402 — core/casestate.py, wave 8's parked-case FSM
import reviewers    # noqa: E402 — core/reviewers.py, wave 10's DONE-REVIEW gate
import liveness     # noqa: E402 — core/liveness.py, wave 11's worker-silence side-system


def route(eng, manifest, worker_reports):
    """One observe-phase pass over this tick's drained worker reports: act on
    every well-formed `worker.online` (ASSIGN), `worker.wall` (open a
    parked case), and `operator.decision` (settle a parked case) line;
    anything else (local-pass `worker.done` reports included) is `core/
    snapshot.py`'s own concern, fed to `core.gate.advance` separately by
    `core/tick.py` — never double-handled here.

    Wave 11 (`core/liveness.py`): BEFORE any of the per-tag dispatch below,
    every drained report touches its own reporting worker's record
    (`liveness.touch` — a transient `_reported` flag `core/liveness.py::
    sweep` turns into a fresh `last_seen` reading later THIS SAME tick,
    after `core/tick.py` has run `router.route` — see that module's own
    docstring for why the ACTUAL clock read happens there, not here). This
    is the ONLY place `last_seen` gets marked live — a worker's own report
    is what proves it isn't silent, independent of which specific tag it
    sent."""
    workers = manifest.setdefault("workers", {})
    gates = manifest.setdefault("gates", {})

    for rep in worker_reports:
        liveness.touch(workers, gates, rep)

    for rep in worker_reports:
        tag = rep.get("tag")
        if tag == "worker.online":
            _route_online(eng, manifest, workers, gates, rep)
        elif tag == "worker.wall":
            _route_wall(eng, manifest, rep)
        elif tag == "operator.decision":
            _route_decision(eng, manifest, rep)
        elif tag == "architect.reconciled":
            _route_architect_reconciled(eng, manifest, rep)
        elif tag == "worker.review_done":
            reviewers.on_review_done(eng, manifest, rep)
        # else: worker.done and anything else — not this module's concern.


def _route_online(eng, manifest, workers, gates, rep):
    agent_id = rep.get("agent_id")
    slots = rep.get("slots") or {}
    branch = slots.get("branch")
    if not agent_id or not branch:
        eng.log("flow", f"router: dropped a malformed worker.online report "
                        f"(agent_id={agent_id!r} branch={branch!r})")
        return

    worker = workers.get(agent_id)
    if not worker:
        eng.log("flow", f"router: worker.online from unrecorded agent "
                        f"{agent_id!r} — no matching spawn, dropped")
        return
    if worker.get("status") != "spawning":
        # Already assigned (or released) — a duplicate/late report;
        # never a second ASSIGN for the same worker.
        return

    block = worker.get("block")
    block_file = worker.get("block_file")
    if block in gates:
        # Defensive: a gate already open for this block under a
        # different path — never overwrite an in-flight gate.
        eng.log("flow", f"router: block {block!r} already has an open "
                        f"gate — worker.online from {agent_id!r} ignored")
        return

    gates[block] = gate.new_state_full(eng, block, block_file, branch, agent_id)
    worker["status"] = "busy"
    worker["branch"] = branch
    eng.log("flow", f"router: ASSIGN {agent_id!r} -> block {block!r} on "
                    f"its own reported branch {branch!r} (gate.local opened)")


def _route_wall(eng, manifest, rep):
    """`worker.wall` — B7's raise-and-defer trigger. FAIL-LOUD on malformed
    (no block, or no detail): a wall must NEVER silently vanish into a log
    line the way an unknown `worker.online` sender safely can — there is no
    safe "drop" for a genuine in-flight problem report."""
    block = rep.get("block")
    worker_id = rep.get("agent_id") or rep.get("worker_id")
    slots = rep.get("slots") or {}
    detail = slots.get("detail")
    if not block:
        raise ValueError(f"router: worker.wall report carries no block — "
                         f"fail-loud, a wall is never silently dropped: {rep!r}")
    if not detail:
        raise ValueError(f"router: worker.wall for block {block!r} carries "
                         f"no detail — fail-loud, a wall is never silently "
                         f"dropped: {rep!r}")
    casestate.open_case(eng, manifest, block, "worker.wall", detail,
                        worker_id=worker_id, kind="wall")


def _route_architect_reconciled(eng, manifest, rep):
    """`architect.reconciled` — the architect's completion report for a
    `reconcile` job (M-05, `core/architect.py`). Malformed (no `block`) is
    logged and dropped — an internal, engine-scripted signal, never
    adversarial input, same forgiving discipline `worker.online` already
    gets for an unrecordable sender. Idempotent: a block already in
    `manifest["reconciled"]` is a no-op, never appended twice."""
    block = rep.get("block")
    if not block:
        eng.log("flow", f"router: dropped a malformed architect.reconciled "
                        f"report (no block): {rep!r}")
        return
    reconciled = manifest.setdefault("reconciled", [])
    if block in reconciled:
        eng.log("flow", f"router: architect.reconciled for block {block!r} "
                        f"— already reconciled, no-op")
        return
    reconciled.append(block)
    eng.log("flow", f"router: architect.reconciled for block {block!r} -> "
                    f"reconcile-gate record set (core/architect.py::advance "
                    f"clears the architect's own current_job off this)")


def _route_decision(eng, manifest, rep):
    """`operator.decision` — F6/B7's Settle trigger. Malformed (no case_id,
    or an unrecognized verb) is logged and dropped, never raised — an
    operator reply is not a structural contract the way a worker's own wall
    report is; `core.casestate.settle` itself handles an unknown/duplicate
    case_id the same forgiving way."""
    slots = rep.get("slots") or {}
    case_id = rep.get("case_id") or slots.get("case_id")
    verb = rep.get("verb") or slots.get("verb")
    note = rep.get("note") or slots.get("note")
    if not case_id or verb not in casestate.VERBS:
        eng.log("flow", f"router: dropped a malformed operator.decision report "
                        f"(case_id={case_id!r} verb={verb!r}) — logged, no-op, "
                        f"never crashes, never guesses a case")
        return
    casestate.settle(eng, manifest, case_id, verb, note=note)
