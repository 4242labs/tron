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


def admit(tag, slots, msg, architect_wid):
    """Pure predicate: `(ok, reason)`. `ok=False` iff `tag` is not a known
    vocab tag, `msg`'s resolved origin is not a legal minter of `tag`
    (ADR-0011 S-1), or the report combines a progress-advancing and a
    blocking class signal (R5/T6, `vocab.classes_conflict` — the
    enumerated partition over every (tag, slot) pair, not just one seen
    pair). `msg` is the FULL drained report dict (see `vocab.resolve_
    origin` — a scripted rig's bare top-level `agent_id` is equally valid
    ambient identity, never just `sender`). Never touches `manifest`/`eng`
    — the caller decides what a refusal DOES; this only decides whether
    one occurred."""
    if tag not in vocab.TAGS:
        return False, (f"unknown tag {tag!r} — not in the closed vocabulary. "
                       f"Legal --tag values:\n{vocab.legal_set_text()}")
    # Minters enforcement (ADR-0011 S-1, widened block 01-38 T3 per the
    # hostile review that found the hole below) closes an IMPERSONATION
    # surface on the report DOOR: a worker-shaped sender claiming a
    # restricted-origin tag through the SAME door a worker uses. Enforced
    # for EVERY tag, unconditionally — a prior version of this check SKIPPED
    # minters for any tag with no `report.sh` verb (`verb is None`:
    # `operator.decision`, `worker.stalled`/`dead`, `worker.report_refused`,
    # `unclassified`), reasoning that a verb-less tag "never arrives through
    # report.sh's door". That reasoning was WRONG for `operator.decision`
    # specifically: a STRUCTURED line carrying `{"tag": "operator.decision",
    # ...}` resolves via `core/vocab.py::verb_to_tag`'s dotted-tag passthrough
    # (`_structured` in `core/classify.py`) regardless of verb, so it DOES
    # reach this exact function — and with minters skipped, ANY sender
    # (including a worker writing into its own ambient channel) could mint a
    # legitimate-looking `operator.decision` and settle its own parked case,
    # defeating R8 ("resolved by a real inbound operator command") — the
    # EXPLOIT this widening closes. `worker.stalled`/`worker.dead`/`worker.
    # report_refused` are still, in practice, never sent by a real report.sh
    # (no verb) and `unclassified`'s minters already include every origin —
    # so enforcing minters uniformly changes nothing for those three, and
    # closes the operator.decision hole for the fourth. Identity for a
    # verb-less tag is resolved the SAME way as any other: `vocab.
    # resolve_origin` off the CHANNEL the message arrived on (R6/R8) — never
    # a payload field, never `report.sh`'s own (informational-only) verb
    # gate.
    if not vocab.minters_ok(tag, msg, architect_wid):
        origin = vocab.resolve_origin(msg, architect_wid)
        return False, (f"tag {tag!r} may not be minted by origin {origin!r} "
                       f"(sender={(msg or {}).get('sender')!r}, "
                       f"agent_id={(msg or {}).get('agent_id')!r}) — legal "
                       f"minters: {sorted(vocab.TAGS[tag].minters)}")
    if vocab.classes_conflict(tag, (slots or {}).keys()):
        return False, (f"report combines a progress-advancing and a blocking "
                       f"class signal (tag={tag!r}, slots={sorted((slots or {}).keys())}) "
                       f"— illegal by R5's partition; send one contradiction-free report")
    return True, None


def refuse(eng, manifest, sender, attempted_tag, raw_text, reason, worker_id=None):
    """Record a door refusal durably (R2: full text + sender, never just a
    count) and open a case via the SAME architect-first path a `worker.
    wall` already uses — reused wholesale, never forked, so a refusal
    inherits triage, the reping floor, and session-end open-case detection
    for free. `manifest` may carry no durable `workers[worker_id]["block"]`
    binding yet (a malformed report from a not-yet-ASSIGNED sender) — the
    case is minted block-less in that case (`casestate.open_case(block=
    None, ...)`, the identical fallback `core/router.py::_route_wall`
    already uses for an unmapped worker)."""
    text = (raw_text or "")[:2000]
    eng.log("flow", f"door: REFUSED a report from sender={sender!r} "
                    f"attempted_tag={attempted_tag!r} — {reason} — raw={text!r}")
    eng.events.event("door_refusal", sender=sender, attempted_tag=attempted_tag,
                     reason=reason, raw=text)
    if manifest is None:
        return None
    durable_block = (manifest.get("workers") or {}).get(worker_id or "", {}).get("block")
    detail = f"door refused a report ({reason}): {text}"
    return casestate.open_case(eng, manifest, durable_block, "worker.report_refused",
                               detail, worker_id=worker_id, kind="door_refusal")
