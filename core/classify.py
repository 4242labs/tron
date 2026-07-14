"""core.classify — STRUCTURED-ONLY report resolution (ADR-0012 §6(b),
block 01-37 T3/T6/T8). Pinned to the OBSERVE phase exactly as before
(`contracts/rebuild-spec.md` T2/T5): `decide`/`act`/`route` (`core/gate.py`,
`core/router.py`, `core/switchboard.py`, `core/sentry.py`, `core/
liveness.py`, `core/casestate.py`, `core/architect.py`) stay pure — none of
them import this module; `core/snapshot.py::build` is the ONE call site.

**The free-text grader is RETIRED (§6(b), operator-approved).** The word on
a report IS the classification — every tag `core/vocab.py::TAGS` declares
resolves DETERMINISTICALLY here, off `report.sh --tag <verb>` (or a
tag-less branch declaration), through the SAME admission door (`core.door`)
T3's `scripts/report.sh` refuses at first: unknown tag, wrong minter, or a
progress+blocking class conflict (R5/T6) is REFUSED, never guessed at by a
model. The free-text grading tool (`engine/judge.py`'s classify tool) — the
documented deepest root of every phantom-escalation run — is no longer
called from this module at all (the grep proof: `core/classify_rig.py`'s
structural check). Architect/AIDE/
worker judgment is UNTOUCHED — they answer through their own structured
words (the verdict wire, T9); this module removes only the free-text
GRADER, never a second flow-steering LLM.

A message with NEITHER a `tag` NOR a `branch` slot (genuine free prose, or
an unrecognized operator settle) is refused at the door exactly like a bad
tag: `core.door.refuse` records the FULL text + sender durably and opens an
architect-first case (reused `casestate.open_case` — R2's "never quiet
paralysis": a worker stuck re-sending surfaces via the ordinary liveness
budget, never a second escalation mechanism of this module's own). Returns
`(None, None)` — `core/snapshot.py::_classify_reports` drops a `(None,
None)` resolution from `worker_reports` entirely: a refused line was
ALREADY fully handled (case opened) here, so it is never handed to `core/
router.py::route` as a "report" at all — the router's OWN T4 catch-all
(`core/router.py`'s `else` arm) is a SEPARATE, structurally-independent
backstop for a tag that bypasses THIS door (a rig writing straight into
`worker_reports`, or a future vocab tag `router.py` forgot to wire) —
never double-cased with a door refusal.

`_settle_from_text` (operator CASE-<n> <verb>, zero model calls) is kept —
T8 permits this: "keep it as a door-side parse" — it is the operator's own
deterministic settle path, unrelated to the retired free-text GRADER, and
runs BEFORE the free-text refusal so a genuine settle reply is never
refused.

Duck-typed `eng` contract: `eng.log`, `eng.events` (an `EventLog`/`_Events`
-shaped `.event(...)` sink). No git/subprocess/LLM of any kind in this
module anymore.
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import architect    # noqa: E402 — core/architect.py, ARCHITECT_WID (door origin resolution)
import casestate     # noqa: E402 — core/casestate.py, VERBS (the settle-regex verb vocabulary)
import door           # noqa: E402 — core/door.py, the T3/T6 admission door
import vocab           # noqa: E402 — core/vocab.py, the ONE closed vocabulary
# ADR-0010 (Invariant A) removed this module's only use of `pipeline._is_landing_wall`
# (the deleted prose-mint of `worker.wall`), so `import pipeline` is gone from here.
# `pipeline.stale_landing_wall` (ADR-0008 suppression) is a SEPARATE consumer living in
# core/casestate.py + core/architect.py — untouched by this change.

# "approve" is accepted as a settle synonym for "resume" (mirrors engine/
# fsm.py's own SETTLE_VERB_RE, which the operator-facing copy still teaches:
# "'resume CASE-007' / 'approve CASE-007' / 'abandon CASE-007'") — never a
# second/duplicate verb this stack's own casestate.settle would reject.
_VERB_SYNONYMS = {"approve": "resume"}
_VERB_RE = re.compile(
    r"\b(" + "|".join(list(casestate.VERBS) + list(_VERB_SYNONYMS)) + r")\b",
    re.IGNORECASE)


def _structured(msg):
    """A report carrying its own `--tag` (`msg["tag"]`) resolves via `core.
    vocab.verb_to_tag` — deletes the old hand-maintained verb-to-tag map
    this module used to carry (AC-1): single source, `core/vocab.py::
    VERB_TO_TAG`. Returns `(raw_tag, canonical_tag_or_None, slots)` — the
    RAW tag is preserved for a refusal message even when `canonical_tag` is
    `None` (unknown verb). A tag-LESS report that declares a branch is the
    canonical branch declaration and resolves DETERMINISTICALLY to `worker.
    branch` (`scripts/report.sh`'s own documented shape: "The canonical
    branch declaration needs no --tag at all") — never sent to the door as
    free text. Returns `(None, None, None)` for neither shape (genuine free
    text, the caller's own refusal to make)."""
    tag = msg.get("tag")
    if tag:
        return tag, vocab.verb_to_tag(tag), dict(msg.get("slots") or {})
    slots = dict(msg.get("slots") or {})
    if slots.get("branch") or msg.get("branch"):
        return "branch", "worker.branch", slots
    return None, None, None


def _settle_from_text(manifest, text):
    """Operator CASE-<n> <verb> settles via a deterministic regex — zero
    model calls (shape learned from `engine/fsm.py::_settle_regex`,
    re-expressed for THIS stack's own case-id vocabulary). Only matches a
    case id that is GENUINELY open right now (`manifest["cases"]`, `decision
    is None`) — an operator's prose that happens to contain the substring
    "case" never misfires into a settle for a case that doesn't exist; a
    hit with no recognizable verb, or naming no open case at all, returns
    `None` (falls through to the door refusal below, unchanged)."""
    if not manifest or not text:
        return None
    cases = manifest.get("cases") or {}
    open_ids = [cid for cid, c in cases.items() if c.get("decision") is None]
    if not open_ids:
        return None
    low = text.lower()
    hit_id = next((cid for cid in open_ids if cid.lower() in low), None)
    if not hit_id:
        return None
    vm = _VERB_RE.search(text)
    if not vm:
        return None
    verb = _VERB_SYNONYMS.get(vm.group(1).lower(), vm.group(1).lower())
    if verb not in casestate.VERBS:
        return None
    return {"case_id": hit_id, "verb": verb}


def classify(eng, msg, manifest=None):
    """Resolve ONE drained inbox line to `(tag, slots)` — called from `core/
    snapshot.py::build`'s observe pass, once per drained report. Returns
    `(None, None)` for a line the admission door REFUSED (already fully
    handled: recorded + an architect-first case opened, `core.door.refuse`)
    — `core/snapshot.py` drops such a resolution from `worker_reports`
    entirely, never handing a refused line to `core/router.py::route`.
    Otherwise returns `(tag, slots)` with `tag` a real `core/vocab.py::TAGS`
    member.

    `manifest` (optional — `core/snapshot.py` always supplies its own
    in-progress manifest) backs BOTH the deterministic operator-settle
    regex AND the door refusal's case-opening; a caller with no manifest in
    scope (a direct unit-level `classify()` call) still gets the door's
    admission CHECK and the forensic event, just no case bookkeeping (mirrors
    the pre-existing `_triage_unclassified` contract this replaces)."""
    sender = msg.get("sender") or {}
    text = msg.get("text", "") or ""

    if sender.get("kind") == "operator":
        settled = _settle_from_text(manifest, text)
        if settled:
            return "operator.decision", settled

    raw_tag, tag, slots = _structured(msg)
    if tag is None:
        # Either an unknown/mistyped verb (raw_tag is set) or genuine
        # free-text prose (raw_tag is None) — both refused at the door,
        # identically: structured-only reporting, no free-text judgment
        # behind either (§6(b)).
        reason = (f"unrecognized report verb {raw_tag!r} — not in the closed "
                 f"vocabulary. Legal --tag values:\n{vocab.legal_set_text()}"
                 if raw_tag else
                 "prose-only report with no --tag and no --branch — "
                 "structured-only reporting: use `report.sh --tag <verb> ...`. "
                 f"Legal --tag values:\n{vocab.legal_set_text()}")
        door.refuse(eng, manifest, sender, raw_tag, text, reason,
                    worker_id=sender.get("id"))
        return None, None

    ok, reason = door.admit(tag, slots, msg, architect.ARCHITECT_WID)
    if not ok:
        worker_id = sender.get("id") or msg.get("agent_id") or msg.get("worker_id")
        door.refuse(eng, manifest, sender, tag, text, reason,
                    worker_id=worker_id)
        return None, None

    return tag, slots
