"""core.classify — the ONE LLM judgment (`classify_message`), pinned to the
OBSERVE phase (`contracts/rebuild-spec.md` T2/T5; `contracts/blueprint-
contracts.md` §2-§4). Every prior wave's own docstring says it plainly: "NO
LLM/classify in this brick — a later wave". This is that wave. `decide`/
`act`/`route` (`core/gate.py`, `core/router.py`, `core/switchboard.py`,
`core/sentry.py`, `core/liveness.py`, `core/casestate.py`, `core/
architect.py`) stay exactly as pure as they already are: NONE of them import
this module or `engine/judge.py`; `core/snapshot.py::build` is the ONE call
site (see its own docstring for the wiring), so the model is touched exactly
once per free-text inbox line, ONLY while the OBSERVE pass is being built,
NEVER while `decide`/`act` drive a gate forward.

Shape learned by READING `engine/fsm.py::_classify`/`_structured` (never
copied — re-expressed fresh for this stack's own plain-manifest shape, none
of that module's role/PR/architect-queue/violation-repair machinery, which
stay out of scope here):

  **Structured bypass first** (`_structured`, T2/rebuild-spec) — a report
  that already carries its own `tag` (every `worker.online`/`worker.done`/
  `worker.wall`/`operator.decision`/... line every prior `core/*_rig.py`
  fixture already sends) resolves deterministically, in this SAME function,
  with the model NEVER consulted — `core/classify_rig.py`'s AC-1 asserts the
  stub queue is untouched for exactly this path. This is what makes wave 13
  purely additive: every one of the 12 prior rigs still sends only
  structured lines, so `classify()` is a same-tag echo for every one of
  them, zero behavior change.

  **Operator CASE-<n> <verb> settles via a deterministic regex too**
  (`_settle_from_text`) — re-expressed for THIS stack's own case-id
  vocabulary (`core/casestate.py::next_case_id`'s `case-<token>-<n>` shape,
  never the legacy engine's bare `CASE-<n>` numeric form): a genuinely open
  case id (`manifest["cases"]`, `decision is None`) appearing verbatim in an
  operator's free text, plus a settle verb (`core/casestate.py::VERBS`,
  `approve` accepted as a synonym for `resume`), settles deterministically —
  zero model calls. A message naming no currently-open case (an operator's
  prose that happens to contain the word "case") never misfires; it falls
  through to the one real judgment below, unchanged.

  **Free-text → the one judgment** — otherwise, `judge.call("classify_
  message", {text, sender}, eng.ctx, ...)` (`engine/judge.py`, reused
  VERBATIM — this module never re-implements validation, retry, or the
  stub short-circuit; `TRON_JUDGE_STUB` makes the whole path deterministic
  for `core/classify_rig.py`, exactly like `engine/e2e_test.py::report`).
  `judge.call`'s own validator (`judge._v_classify`) already schema-checks
  the return against `routing.yaml`'s closed tag enum AND rejects every
  `judge.ENGINE_ONLY` tag (`worker.stalled`/`worker.dead` — engine-produced
  only, never a classifier output) — this module adds NO second enum check
  of its own, single source of truth. `max_retries` is read off `routing.
  yaml`'s own `invalid_output.max_retries` (mirrors `engine/fsm.py`'s
  `self._max_retries`, re-derived here rather than duplicated as a second
  hardcoded constant).

  **Invalid-output exhaustion / a self-declared `unclassified` tag** →
  `_triage_unclassified`: logged (forensic — `eng.log` + a durable
  `eng.events.event("unclassified", ...)` record, RAW body included, never
  truncated-away in the log line alone) and handed to the architect FIRST
  — wave 18 (GAP-E): `core/architect.py::enqueue_triage` REUSED VERBATIM
  (never forked), a case-less PMT-TRIAGE job (`case_id=None`, `block=None`
  — no gate/block to park, this is raw free text) carrying the raw body as
  its `detail`. The architect's own scripted (L1)/real (L3) triage verdict
  (`scope_forward`/`answer`/`operator`) then steers it: `scope_forward`
  authors it forward as upcoming work (the SAME adhoc-block mechanism wave
  10's own `enqueue_log_review` already established, reused by `core/
  architect.py::_advance_triage`'s own `scope_forward` arm); `operator`
  mints a genuine operator-owned case (`core/casestate.py::
  open_operator_case`) — R3's own "say it's the operator's, which becomes a
  wall" — never a second LLM judgment call of this module's own (the
  retired second judgment stays retired). `unclassified` itself is STILL
  returned to the caller (the `*` SENTRY catch-all, T5) — triage is a SIDE
  EFFECT of classifying `unclassified`, never a replacement for the tag
  itself.

Duck-typed `eng` contract: `eng.ctx` (routing.yaml + judge's own context
reads), `eng.log`, `eng.events` (an `EventLog`/`_Events`-shaped `.event(...)`
sink — the SAME object every other `core/*.py` module already uses for its
own `eng.events.event(...)` call, `core/landing.py`'s `grant_minted` the
precedent). No git/subprocess of any kind in this module — `judge.call`'s
OWN internal seam (`engine/jobs.RUNTIME` subprocess, or a pure-Python stub
read under `TRON_JUDGE_STUB`) is the only non-deterministic touch, and it is
NEVER reached at all under the stub (`core/classify_rig.py`'s whole
contract, exactly `engine/e2e_test.py`'s own).
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import judge       # noqa: E402 — engine/judge.py, the ONE LLM seam, reused as-is (never forked)
import architect    # noqa: E402 — core/architect.py, wave 9/10's log-review job, reused for triage
import casestate     # noqa: E402 — core/casestate.py, VERBS (the settle-regex verb vocabulary)

# "approve" is accepted as a settle synonym for "resume" (mirrors engine/
# fsm.py's own SETTLE_VERB_RE, which the operator-facing copy still teaches:
# "'resume CASE-007' / 'approve CASE-007' / 'abandon CASE-007'") — never a
# second/duplicate verb this stack's own casestate.settle would reject.
_VERB_SYNONYMS = {"approve": "resume"}
_VERB_RE = re.compile(
    r"\b(" + "|".join(list(casestate.VERBS) + list(_VERB_SYNONYMS)) + r")\b",
    re.IGNORECASE)


# report.sh's own verb vocabulary (worker-contract.md §2 "Verbs") -> this
# stack's canonical `worker.*` tags. `scripts/report.sh` writes the RAW verb
# a real worker types (`--tag done`/`recorded`/`wall`/`review-done`/`clean`);
# the engine reads the namespaced tag (`worker.done`, ...). The legacy engine
# resolved this in `fsm._structured` (`block:next:done` -> `_h_worker_done`);
# ported here so a REAL report.sh line resolves deterministically, no model.
# `clean` is the close clean-confirmation (legacy `_h_worker_done`, T7: a
# `done`/`clean` report on an already-✅ block is the close confirmation, the
# gate's own git-observed `replica_clean` is what actually advances).
_REPORT_VERB_TAG = {
    "done": "worker.done",
    "recorded": "worker.recorded",
    "wall": "worker.wall",
    "review-done": "worker.review_done",
    "review_done": "worker.review_done",
    "branch": "worker.branch",
    "online": "worker.online",
    "clean": "worker.done",
    # the ARCHITECT's own completion verb (`report.sh architect --tag
    # reconciled --block <id>`) — the reconcile-gate (M-05) clears only on a
    # canonical `architect.reconciled`, and without this a real architect
    # could never emit it, gating the next block forever (forward-wall #4).
    "reconciled": "architect.reconciled",
}


def _canonical_tag(tag):
    """A tag that is ALREADY namespaced (`worker.done`, `architect.reconciled`,
    `operator.decision` — everything `core/*_rig.py` and `core/sim/worker.py`
    write directly, and every structured line the engine mints internally)
    contains a `.` and passes through UNCHANGED — so no rig is re-pointed. A
    BARE verb (a real `scripts/report.sh --tag <verb>` line) is mapped to its
    canonical `worker.*` tag; an unknown bare token is left as-is (it will
    fail routing.yaml's closed-enum check downstream -> architect triage,
    never silently mis-advance a gate)."""
    if not tag or "." in tag:
        return tag
    return _REPORT_VERB_TAG.get(tag.strip().lower(), tag)


def _structured(msg):
    """A report that already carries its own `tag` resolves without the
    model — the SAME discipline `core/snapshot.py`'s own `local_reports`
    drain already keeps for `worker.done`. Returns `(tag, slots)` or
    `(None, None)` when `msg` carries neither a `tag` NOR a branch
    declaration (the free-text path, this module's own real job, below). A
    raw `report.sh` verb (`done`, ...) is mapped to its canonical `worker.*`
    tag here (`_canonical_tag`); an already-namespaced tag passes through
    untouched.

    A tag-LESS report that declares a branch is the canonical branch
    declaration and resolves DETERMINISTICALLY to `worker.branch` — NEVER
    the free-text judge. `scripts/report.sh` documents this shape verbatim
    ("The canonical branch declaration needs no `--tag` at all:
    `report.sh <id> --branch <name> <message>`") and it is the ONLY tag-less
    report that carries a branch slot. A branch slot is itself a
    deterministic structured signal; handing such a report to the LLM judge
    let a contentless declaration message (the bare word "placeholder") be
    mis-graded `worker.wall`, minting a phantom architect-first case the
    architect could not triage and escalated LOUD to the operator — a
    spurious page that fails an otherwise-clean run (the T2-16 REJECT). The
    gate still opens from the same rep's branch via
    `router._open_gate_if_branch`; this only stops the mis-classification.
    An EXPLICIT `--tag wall` (or any other tag) still wins above — a
    worker's stated intent is never overridden."""
    tag = msg.get("tag")
    if tag:
        return _canonical_tag(tag), dict(msg.get("slots") or {})
    slots = dict(msg.get("slots") or {})
    if slots.get("branch") or msg.get("branch"):
        return "worker.branch", slots
    return None, None


def _settle_from_text(manifest, text):
    """Operator CASE-<n> <verb> settles via a deterministic regex — zero
    model calls (shape learned from `engine/fsm.py::_settle_regex`,
    re-expressed for THIS stack's own case-id vocabulary). Only matches a
    case id that is GENUINELY open right now (`manifest["cases"]`, `decision
    is None`) — an operator's prose that happens to contain the substring
    "case" never misfires into a settle for a case that doesn't exist; a
    hit with no recognizable verb, or naming no open case at all, returns
    `None` (falls through to the free-text judge call, unchanged)."""
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


def _triage_unclassified(eng, manifest, text, sender, attempts):
    """unclassified -> the architect FIRST (`PMT-TRIAGE`, rebuild-spec.md T5
    + wave 18/GAP-E) — NEVER a second LLM judgment, NEVER a direct operator
    page. Reuses `core/architect.py::enqueue_triage` VERBATIM, case-less
    (`case_id=None`, `block=None` — raw free text, no gate/block to park):
    the architect's own scripted (L1)/real (L3) triage verdict steers it —
    author it forward as an upcoming adhoc block (`scope_forward`), or —
    its OWN project-context judgment, `core/architect.py`'s own concern,
    never this module's — say it's the operator's, which mints a genuine
    operator-owned case per R3 (`operator`, via `core/casestate.py::
    open_operator_case`). `manifest` may be `None` (a direct unit-level
    `classify()` call with no tick/manifest context) — triage bookkeeping
    is then skipped, but the FORENSIC log/event record below still fires
    unconditionally: raw body is NEVER lost, whether or not there's a
    manifest to queue a job into."""
    raw = str(text)[:2000]
    last_attempt = str(attempts[-1])[:500] if attempts else ""
    eng.log("flow", f"classify: unclassified from sender={sender!r} -> "
                    f"architect triage (PMT-TRIAGE, architect-first); "
                    f"raw={raw!r} last_attempt={last_attempt!r}")
    eng.events.event("unclassified", sender=sender, raw=raw, last_attempt=last_attempt)
    if manifest is None:
        return
    # R1a (ADR-0005) — the architect can never be the SOURCE of a triage/case.
    # An UNCLASSIFIED message from the architect itself is narration (its reasoning
    # while working a triage), never a new phantom. Short-circuit CREATION here and
    # create nothing. Deliberately NO benign 'answer' write for its in-flight triage
    # (the old self-triage guard): that write was source-AGNOSTIC and, the instant
    # the architect narrated a turn while triaging a GENUINE worker.wall, resolved
    # that real escalation to 'answer' before its structured `operator` verdict
    # arrived — swallowing the page (M1, the false-green disease). Resolution of the
    # architect's in-flight triage is now the single idle-gated, source-directional
    # backstop in `architect._advance_triage` (R1b): a low-confidence phantom
    # resolves benign, a genuine wall resolves LOUD to the operator, once the
    # architect settles idle without a structured verdict.
    if (sender or {}).get("id") == architect.ARCHITECT_WID:
        eng.log("flow", "classify: unclassified architect narration -> created "
                        "nothing (R1a self-source guard); any in-flight triage "
                        "resolves via the architect-idle backstop, not narration")
        return
    architect.enqueue_triage(eng, manifest, None, "classify.unclassified",
                             None, raw, worker_id=(sender or {}).get("id"))


def classify(eng, msg, manifest=None):
    """Resolve ONE drained inbox line to `(tag, slots)` — called from `core/
    snapshot.py::build`'s observe pass, once per drained report (structured
    AND free-text alike; the structured-bypass check below is what keeps
    every structured line's cost at zero). `manifest` (optional — `core/
    snapshot.py` always supplies its own in-progress manifest) backs the
    deterministic operator-settle regex above; a caller with no manifest in
    scope simply skips that ONE bypass and falls through to the real
    judgment (never a crash, never a guess).

    Returns `(tag, slots)` — `tag` is always a string (never `None`):
    `unclassified` on invalid-output exhaustion OR a self-declared
    `unclassified` return from the model itself (T5's own "the model found
    no matching tag" case)."""
    stag, sslots = _structured(msg)
    if stag:
        return stag, sslots

    sender = msg.get("sender") or {}
    text = msg.get("text", "") or ""

    if sender.get("kind") == "operator":
        settled = _settle_from_text(manifest, text)
        if settled:
            return "operator.decision", settled

    routing = eng.ctx.load_routing()
    max_retries = int((routing.get("invalid_output") or {}).get("max_retries", 2))

    payload = {"text": text, "sender": sender}
    ok, out, attempts = judge.call("classify_message", payload, eng.ctx,
                                   max_retries=max_retries, elog=eng.events)
    if not ok:
        # Invalid-output budget exhausted (or, under TRON_JUDGE_STUB, a
        # single bad canned response — the stub's own short-circuit
        # contract, see engine/judge.py::call: it pops exactly ONE queued
        # response per call and skips the internal retry loop entirely,
        # deterministically STANDING IN for "the whole budget came back
        # bad" without spending a real retry cycle) -> unclassified.
        _triage_unclassified(eng, manifest, text, sender, attempts)
        return "unclassified", {"detail": text[:200]}

    tag = out["tag"]
    if tag == "unclassified":   # the model itself found no matching tag (T5)
        _triage_unclassified(eng, manifest, text, sender, attempts)
    return tag, out.get("slots") or {}
