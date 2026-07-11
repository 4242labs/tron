"""core.router — structured routing (NO LLM/classify IN THIS MODULE): the
ASSIGN half of the two-step spawn->online->assign handshake
(`contracts/rebuild-spec.md` C1/D1; `blueprint-contracts.md` §5's "Branch
ownership" rule). `core/switchboard.py` owns SPAWN (identity-only); this
module drains this tick's ALREADY-TAGGED worker reports (`core/snapshot.py`
's own drain — every line, structured or originally free-text, has its
`tag`+`slots` resolved by `core/classify.py` during the observe pass, BEFORE
this module ever runs; a `worker.online` line IS the online report, read
structurally, exactly like `worker.done` already is for the DONE-gate's
local-pass report) and, for each well-formed `worker.online` report,
ASSIGNS: opens the block's gate at `gate.local`, bound to the worker's OWN
REPORTED branch (`worker.branch`, carried in the report's `slots` — NEVER a
guessed `feat/<block>`; the worker names its own branch, the engine only
ever records the name it reports).

Real classify (`classify_message`, the sole LLM entrypoint per T2 of
`rebuild-spec.md`) is wave 13, `core/classify.py` — pinned to the OBSERVE
phase (`core/snapshot.py::build`), never here: this router imports neither
`classify` nor `engine/judge.py` and only ever acts on an ALREADY-RESOLVED
`tag`+`slots` shape, same discipline `core/snapshot.py`'s `local_reports`
drain already keeps for `worker.done` — `decide`/`route`/`act` stay pure,
by construction, not by convention.

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

Wave 18 (GAP-E) adds ONE more structured tag: `architect.triage_verdict`
(`{"tag": "architect.triage_verdict", "triage_id": <id>, "verdict":
scope_forward|answer|operator, "note": <optional>}`) — the architect's own
completion report for a `triage` job (PMT-TRIAGE, `core/architect.py`),
routed exactly like `architect.reconciled` above. Keyed by the job's OWN
`triage_id` (`core/architect.py::_next_triage_id`) — deliberately NEVER the
casestate `case_id`, which is legitimately `None` for a case-less triage
(an unclassified classify result with no block/gate behind it) and would
otherwise collide across two independent case-less jobs raised over one
run. Malformed (no `triage_id`, or an unrecognized verdict) is logged and
dropped, an internal engine-scripted signal, never adversarial input. A
well-formed one records into `manifest["triage_verdicts"]` (idempotent: a
triage_id already recorded is a no-op) — `core/architect.py::
_advance_triage` is what actually applies the verdict and clears the
architect's own `current_job` off that record.

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
import architect    # noqa: E402 — core/architect.py, block-less wall -> architect-first triage


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
        elif tag == "architect.triage_verdict":
            _route_architect_triage_verdict(eng, manifest, rep)
        # else: worker.done and anything else — not this module's concern.
        # AFTER the per-tag dispatch: open the gate as soon as a branch is
        # known — for ANY report carrying one (the online report in the rig's
        # one-phase path; a later branch/done declaration in a real worker's
        # two-phase path). See `_open_gate_if_branch`.
        _open_gate_if_branch(eng, workers, gates, rep)


def _route_online(eng, manifest, workers, gates, rep):
    """`worker.online` — the worker's first check-in. Its job is ONE thing:
    ASSIGN (tell the worker WHAT to build), exactly once. It does NOT require a
    branch: `PMT-SPAWN` correctly orders the worker to come online FIRST and
    NOT branch yet ("your assignment comes next"), so the online report has no
    branch to give — requiring one here was the T2-01 deadlock. The gate opens
    later, the moment a branch is declared, via `_open_gate_if_branch` (which
    also fires THIS same tick when the rig's one-phase online already carries
    `slots.branch`)."""
    agent_id = rep.get("agent_id") or rep.get("worker_id")
    if not agent_id:
        eng.log("flow", f"router: dropped a worker.online report with no "
                        f"identity (agent_id/sender.id): {rep!r}")
        return

    worker = workers.get(agent_id)
    if not worker:
        eng.log("flow", f"router: worker.online from unrecorded agent "
                        f"{agent_id!r} — no matching spawn, dropped")
        return
    if worker.get("status") == "released" or worker.get("assigned"):
        # Released, or already assigned — never a second ASSIGN.
        return

    block = worker.get("block")
    block_file = worker.get("block_file")
    if not eng.dry:
        assignment = (f"[TRON]  {agent_id} — you own block {block}. Read its "
                      f"spec at {block_file} and build it end to end. Declare "
                      f"your OWN feature branch (a `--branch <name>` report) "
                      f"and report a structured `done` when the local "
                      f"acceptance suite passes.")
        eng.emit(
            "assign.worker",
            assignment,
            slots={"assignment": assignment, "merge_path": ""},
            worker_id=agent_id,
            kind="PMT-ASSIGN")
    worker["assigned"] = True
    eng.log("flow", f"router: ASSIGN {agent_id!r} -> block {block!r} "
                    f"(gate.local opens when it declares its branch)")


def _open_gate_if_branch(eng, workers, gates, rep):
    """Open `gate.local` for an ASSIGNED worker the moment a branch is known.
    Fires for ANY report carrying `slots.branch` (a worker.online that already
    named it — the rig's one-phase path — OR a later branch/done declaration —
    a real worker's two-phase path). Guarded so it never opens a gate before
    the worker was ASSIGNED, never overwrites an in-flight gate, and is inert
    for a report with no branch."""
    agent_id = rep.get("agent_id") or rep.get("worker_id")
    slots = rep.get("slots") or {}
    branch = slots.get("branch") or rep.get("branch")
    if not agent_id or not branch:
        return
    worker = workers.get(agent_id)
    if not worker or not worker.get("assigned") or worker.get("status") == "released":
        return
    block = worker.get("block")
    if not block or block in gates:
        return
    gates[block] = gate.new_state_full(eng, block, worker.get("block_file"),
                                       branch, agent_id)
    worker["status"] = "busy"
    worker["branch"] = branch
    eng.log("flow", f"router: gate.local opened for block {block!r} on "
                    f"{agent_id!r}'s declared branch {branch!r}")


def _route_wall(eng, manifest, rep):
    """`worker.wall` — B7's raise-and-defer trigger. A wall must NEVER silently
    vanish, but it must ALSO never crash the whole tick: a REAL worker raises a
    wall in PROSE (couriered turn-output, or `report.sh --tag wall "<text>"`),
    so `slots.detail` is usually absent and the block id may be too. The old
    fail-loud `raise` propagated through `core/tick.py` and aborted the entire
    run (outcome=error) on a single prose wall — never acceptable. Instead:
      - detail falls back to the report's own free `text` (the prose IS the
        detail), then to a non-empty placeholder — a wall is never dropped for
        want of a detail string;
      - a wall naming a block opens a parked case (architect-first, GAP-E);
      - a BLOCK-LESS wall routes to architect triage (`enqueue_triage`, the
        SAME block-less path `core/classify.py::_triage_unclassified` uses) —
        never a crash, never a silent drop."""
    block = rep.get("block")
    worker_id = rep.get("agent_id") or rep.get("worker_id")
    slots = rep.get("slots") or {}
    detail = slots.get("detail") or (rep.get("text") or "").strip() \
        or f"worker {worker_id!r} raised a wall (no detail text)"
    # A "wall" whose sender is the architect is the architect NARRATING (its
    # status/reasoning while working a triage — "sorted it", "operator's call,
    # re-mint"), never a real worker wall: the architect cannot wall or triage
    # ITSELF. Routing it as a wall spawned phantom worker.wall-sourced triages
    # that neither the classify self-triage-guard nor the phantom-grace (both
    # classify.unclassified-only) cover — they could loop/wedge session-end
    # (s6 first-honest-SIM). Resolve the architect's in-flight triage benignly
    # instead (its clean escalation path is a structured architect.triage_verdict,
    # unaffected); never a new case/triage from the architect's own prose.
    if worker_id == architect.ARCHITECT_WID:
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job") or {}
        if cur.get("kind") == "triage" and cur.get("triage_id"):
            verdicts = manifest.setdefault("triage_verdicts", {})
            verdicts.setdefault(cur["triage_id"], {"verdict": "answer",
                "note": "architect narration (mis-tagged worker.wall) while triaging"})
            eng.log("flow", f"router: worker.wall FROM the architect (narration) -> "
                            f"benign 'answer' verdict for its in-flight triage "
                            f"{cur['triage_id']!r}, no new triage (self-wall guard)")
        else:
            eng.log("flow", "router: worker.wall FROM the architect (narration), no "
                            "in-flight triage -> logged, no case/triage (self-wall guard)")
        return
    if not block:
        eng.log("flow", f"router: block-less worker.wall from {worker_id!r} "
                        f"-> architect triage (never a crash): {detail}")
        architect.enqueue_triage(eng, manifest, None, "worker.wall", None,
                                 detail, worker_id=worker_id)
        return
    casestate.open_case(eng, manifest, block, "worker.wall", detail,
                        worker_id=worker_id, kind="wall")


def _route_architect_reconciled(eng, manifest, rep):
    """`architect.reconciled` — the architect's completion report for a
    `reconcile` job (M-05, `core/architect.py`). Malformed (no `block`) is
    logged and dropped — an internal, engine-scripted signal, never
    adversarial input, same forgiving discipline `worker.online` already
    gets for an unrecordable sender. Idempotent: a block already in
    `manifest["reconciled"]` is a no-op, never appended twice."""
    # The block a reconcile clears is the architect's OWN in-flight reconcile
    # job's block — NEVER a block id parsed from the architect's free-text
    # report. The architect works exactly one reconcile job at a time, and
    # classify routinely resolves `block` to the just-LANDED block named in the
    # prose ("Forward review of 01-02 done — no impact on 01-03") rather than
    # the GATED block ('01-03') the job actually holds; trusting the report's
    # block recorded reconciled['01-02'] while `advance` waited on reconciled
    # ['01-03'], so `current_job` never cleared and the dependent block stayed
    # permanently gated (the s2 first-honest-SIM 01-03 stall). The report's own
    # block is only a fallback when no reconcile job is in flight.
    arch = manifest.get("architect") or {}
    cur = arch.get("current_job") or {}
    job_block = cur.get("block") if cur.get("kind") == "reconcile" else None
    block = job_block or rep.get("block")
    if not block:
        eng.log("flow", f"router: dropped a malformed architect.reconciled "
                        f"report (no in-flight reconcile job, no block): {rep!r}")
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


def _route_architect_triage_verdict(eng, manifest, rep):
    """`architect.triage_verdict` — the architect's completion report for a
    `triage` job (PMT-TRIAGE, wave 18/GAP-E, `core/architect.py`). Malformed
    (no `triage_id`, or an unrecognized `verdict`) is logged and dropped,
    same forgiving discipline `architect.reconciled` already gets for an
    internal, engine-scripted signal. Idempotent: a triage_id already
    recorded is a no-op, never overwritten twice."""
    triage_id = rep.get("triage_id")
    verdict = rep.get("verdict")
    note = rep.get("note")
    if not triage_id or verdict not in ("scope_forward", "answer", "operator"):
        eng.log("flow", f"router: dropped a malformed architect.triage_verdict "
                        f"report (triage_id={triage_id!r} verdict={verdict!r}): {rep!r}")
        return
    verdicts = manifest.setdefault("triage_verdicts", {})
    if triage_id in verdicts:
        eng.log("flow", f"router: architect.triage_verdict for triage_id="
                        f"{triage_id!r} — already recorded, no-op")
        return
    verdicts[triage_id] = {"verdict": verdict, "note": note}
    eng.log("flow", f"router: architect.triage_verdict for triage_id="
                    f"{triage_id!r} -> {verdict!r} recorded (core/"
                    f"architect.py::advance drains it, applies it, clears "
                    f"the architect's own current_job off this)")


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
