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
  truncated-away in the log line alone) and handed to the architect —
  `core/architect.py::enqueue_log_review` REUSED VERBATIM (never forked)
  with `typ="triage"` and the raw text as the ONE finding: the exact same
  "author an adhoc block per finding, or none" mechanism wave 10 already
  built for a review's findings, now doing double duty for T5's `PMT-
  TRIAGE` path — the architect steers an unclassifiable report forward
  (authors it as upcoming work) using its own project-context judgment,
  never a second LLM judgment call of this module's own (the retired
  second judgment stays retired). `unclassified` itself is STILL returned
  to the caller (the `*` SENTRY catch-all, T5) — triage is a SIDE EFFECT of
  classifying `unclassified`, never a replacement for the tag itself.

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


def _structured(msg):
    """A report that already carries its own `tag` resolves without the
    model — the SAME discipline `core/snapshot.py`'s own `local_reports`
    drain already keeps for `worker.done`. Returns `(tag, slots)` or
    `(None, None)` when `msg` carries no `tag` at all (the free-text path,
    this module's own real job, below)."""
    tag = msg.get("tag")
    if not tag:
        return None, None
    return tag, dict(msg.get("slots") or {})


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
    """unclassified -> the architect (`PMT-TRIAGE`, rebuild-spec.md T5) —
    NEVER a second LLM judgment. Reuses `core/architect.py::
    enqueue_log_review` VERBATIM with `typ="triage"`: the architect steers
    an unclassifiable report exactly the way it already steers a review
    finding (author it forward as an upcoming adhoc block, or — its OWN
    project-context judgment, `core/architect.py`'s own concern, never this
    module's — say it's the operator's, which becomes a wall per R3).
    `manifest` may be `None` (a direct unit-level `classify()` call with no
    tick/manifest context) — triage bookkeeping is then skipped, but the
    FORENSIC log/event record below still fires unconditionally: raw body
    is NEVER lost, whether or not there's a manifest to queue a job into."""
    raw = str(text)[:2000]
    last_attempt = str(attempts[-1])[:500] if attempts else ""
    eng.log("flow", f"classify: unclassified from sender={sender!r} -> "
                    f"architect triage (PMT-TRIAGE); raw={raw!r} "
                    f"last_attempt={last_attempt!r}")
    eng.events.event("unclassified", sender=sender, raw=raw, last_attempt=last_attempt)
    if manifest is not None:
        architect.enqueue_log_review(eng, manifest, "triage", [raw])


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
