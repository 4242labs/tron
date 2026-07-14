"""core.door — the INBOUND admission door (ADR-0012 §2 R2/R5; block 01-37
T3/T6). The single place a drained inbox line is checked against `core.
vocab` before it is trusted as the tag it claims: unknown/unmintable tags
and contradictory progress+blocking reports are refused HERE, never routed.

Called from `core/classify.py::classify` (the observe-phase resolver,
wave 13's own single call site) for every line that already resolved a
`(tag, slots)` pair — structurally (`_structured`, a `--tag`/branch
report) — there is no free-text arm left to validate (T8: the free-text
grader is retired; a prose-only line never reaches here with a tag at
all, and is refused separately, see `classify.py`).

A refusal is never a silent drop: `refuse()` records the FULL attempted
text + sender durably (`eng.events.event("door_refusal", ...)`, R2 — "a
genuine cry for help ... preserved as content, not reduced to an
integer") AND opens a case via the SAME architect-first `casestate.
open_case`/`architect.enqueue_triage` machinery a `worker.wall` already
uses — this is deliberate reuse, not a parallel mechanism: it gives a
refusal, for free, everything a wall already has — architect-first
triage, the reping floor, and (session.py's own `_open_escalations`
read of `manifest["cases"]`) "unresolved at session end is an open
case" (AC-4) — never a bespoke, second escalation path to keep in sync.
A worker that keeps re-sending a bad report is caught by the ordinary
liveness budget exactly like any other silent/stuck worker (R2's own
"refusal never becomes quiet paralysis") — this module does not itself
rate-limit or dedupe repeat refusals from the same sender beyond the
normal case-open idempotency `casestate.open_case` already gives per
block.

No git/subprocess of any kind here; a plain manifest mutation (via
`casestate.open_case`) plus one forensic event — the same discipline
every other `core/*.py` module in this stack already keeps.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import vocab       # noqa: E402 — core/vocab.py, the ONE closed vocabulary
import casestate    # noqa: E402 — core/casestate.py, the parked-case FSM (reused, never forked)


def admit(tag, slots, origin):
    """Pure predicate: `(ok, reason)`. `ok=False` iff `tag` is not a known
    vocab tag, `origin` (the typed `core.intake.Origin` the door resolved
    for this report — block 01-38 T1/T2, never derived from the message
    body) is not a legal minter of `tag` (ADR-0011 S-1), or the report
    combines a progress-advancing and a blocking class signal (R5/T6,
    `vocab.classes_conflict` — the enumerated partition over every (tag,
    slot) pair, not just one seen pair). Never touches `manifest`/`eng` —
    the caller decides what a refusal DOES; this only decides whether one
    occurred."""
    if tag not in vocab.TAGS:
        return False, (f"unknown tag {tag!r} — not in the closed vocabulary. "
                       f"Legal --tag values:\n{vocab.legal_set_text()}")
    # Minters enforcement (ADR-0011 S-1) closes an IMPERSONATION surface on
    # the shared report.sh DOOR: a worker-shaped sender claiming an
    # architect-only verb (`reconciled`/`verdict`) through the SAME door a
    # worker uses. A tag with NO report.sh verb (`operator.decision`,
    # `worker.stalled`/`dead`, `unclassified`) never arrives through that
    # door at all — `operator.decision` is minted ONLY by `core/classify.py`
    # ::_settle_from_text`'s own trusted regex (which never calls this
    # function) or, today, a test rig's direct structured injection
    # simulating the not-yet-built real operator channel (R8/01-38's own
    # scope); `worker.stalled`/`dead` are engine-produced, never via inbox
    # classify at all. There is no impersonation surface to close for a
    # verb-less tag, so minters is not enforced here for one — enforcing it
    # anyway would refuse every existing operator-settle-adjacent rig
    # against an identity shape (`origin.kind == OPERATOR`) the operator
    # channel doesn't structurally provide yet.
    if vocab.TAGS[tag].verb is not None and not vocab.minters_ok(tag, origin):
        return False, (f"tag {tag!r} may not be minted by origin {origin!r} — legal "
                       f"minters: {sorted(vocab.TAGS[tag].minters)}")
    if vocab.classes_conflict(tag, (slots or {}).keys()):
        return False, (f"report combines a progress-advancing and a blocking "
                       f"class signal (tag={tag!r}, slots={sorted((slots or {}).keys())}) "
                       f"— illegal by R5's partition; send one contradiction-free report")
    return True, None


def refuse(eng, manifest, origin, attempted_tag, raw_text, reason):
    """Record a door refusal durably (R2: full text + origin, never just a
    count) and open a case via the SAME architect-first path a `worker.
    wall` already uses — reused wholesale, never forked, so a refusal
    inherits triage, the reping floor, and session-end open-case detection
    for free. `origin` is the typed `core.intake.Origin` the door resolved
    for this report (block 01-38 T2 — never a message-borne `sender`
    field). `manifest` may carry no durable `workers[origin.id]["block"]`
    binding yet (a malformed report from a not-yet-ASSIGNED channel) — the
    case is minted block-less in that case (`casestate.open_case(block=
    None, ...)`, the identical fallback `core/router.py::_route_wall`
    already uses for an unmapped worker)."""
    text = (raw_text or "")[:2000]
    worker_id = origin.id if origin else None
    eng.log("flow", f"door: REFUSED a report from origin={origin!r} "
                    f"attempted_tag={attempted_tag!r} — {reason} — raw={text!r}")
    eng.events.event("door_refusal",
                     origin={"kind": origin.kind, "id": origin.id} if origin else None,
                     attempted_tag=attempted_tag, reason=reason, raw=text)
    if manifest is None:
        return None
    durable_block = (manifest.get("workers") or {}).get(worker_id or "", {}).get("block")
    detail = f"door refused a report ({reason}): {text}"
    return casestate.open_case(eng, manifest, durable_block, "worker.report_refused",
                               detail, worker_id=worker_id, kind="door_refusal")
