"""judge — the only place the engine calls an LLM (contracts §3, §4).

The canon set is ONE bounded, typed question:
  classify_message (cheap)  put an inbound worker/operator message into exactly one
                            tag from routing.yaml's closed enum (+ structured slots).

tron.md is the prompt context; the tool instruction names the decision; the model
must return JSON in the tool's exact shape. The runner schema-validates every
return; invalid output is retried (budget 2) then collapses to `unclassified`
-> the `*` SENTRY catch-all, which hands the input to the architect to sort.
The LLM never sees the flow path and never returns free prose to the flow.

NOT judgment tools, by design: "is this the operator's problem?" (the old
second-judgment tool — RETIRED; an unclassifiable input routes to the architect,
who steers it — the LLM never makes a flow-steering call), review verdicts
(review is a milestone), findings
triage / fix scoping (the architect's log-review skill), stall detection (the
engine's deterministic liveness sweep).

Offline testability: set TRON_JUDGE_STUB to a JSON file mapping tool name -> list
of canned responses (popped in order). The FSM is then fully exercisable without
spending a token.
"""
import os
import re
import json
import subprocess

import util

CHEAP = os.environ.get("TRON_MODEL_CHEAP", "claude-haiku-4-5")
STRONG = os.environ.get("TRON_MODEL_STRONG", "claude-opus-4-8")
TIER = {"classify_message": CHEAP}

_stub_cache = None
_stub_idx = {}
_tags_cache = None

# Engine-produced tags — the classifier must NEVER emit these (the engine's liveness
# sweep produces them). Enforced at the validator, not just in the prompt.
ENGINE_ONLY = {"worker.stalled", "worker.dead"}


def _allowed_tags(ctx):
    """The closed tag enum, read from routing.yaml (single source — no duplication)."""
    global _tags_cache
    if _tags_cache is None:
        _tags_cache = set((util.load_yaml(ctx.routing).get("tags", {}) or {}).keys())
    return _tags_cache


def _stub_response(tool):
    global _stub_cache
    path = os.environ.get("TRON_JUDGE_STUB")
    if not path:
        return None
    if _stub_cache is None:
        with open(path) as fh:
            _stub_cache = json.load(fh)
    queue = _stub_cache.get(tool, [])
    i = _stub_idx.get(tool, 0)
    if i >= len(queue):
        return queue[-1] if queue else None
    _stub_idx[tool] = i + 1
    return queue[i]


# ── output validators: enforce tag+structured-slots, never prose ──
def _v_classify(o, ctx):
    tag = o.get("tag")
    if tag not in _allowed_tags(ctx) or tag in ENGINE_ONLY:
        return f"tag '{tag}' is not a valid classifier output"
    if not isinstance(o.get("slots", {}), dict):
        return "slots must be an object"
    return None


VALIDATORS = {"classify_message": _v_classify}

INSTRUCTIONS = {
    "classify_message":
        "TOOL: classify_message. Put the inbound message in exactly one tag from the "
        "closed vocabulary (or `unclassified`). Pull any block id / reviewer type / "
        "operator decision into slots. Return JSON: "
        '{"tag": <tag>, "slots": {<pulled fields>}, "confidence": <0..1>}.',
}


def _extract_json(text):
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _call_llm(tool, payload, ctx, correction=None):
    with open(ctx.tron_md) as fh:
        context = fh.read()
    parts = [context, "\n---\n", INSTRUCTIONS[tool],
             "\nINPUT:\n", json.dumps(payload, indent=2),
             "\n\nReturn ONLY the JSON object. No prose, no fences."]
    if correction:
        parts.append(f"\n\nYour previous output failed validation: {correction}")
    from jobs import RUNTIME
    # The prompt body goes on STDIN, never as a positional arg: tron.md leads with `---`
    # frontmatter, which the runtime would parse as an unknown CLI option (empty output ->
    # every classify fails). Only the model/tier flags stay as argv.
    cmd = [RUNTIME, "-p", "--model", TIER[tool]]
    try:
        r = subprocess.run(cmd, input="".join(parts),
                           capture_output=True, text=True, timeout=120)
        return r.stdout or ""
    except subprocess.SubprocessError:
        return ""


def _record_model_call(elog, tool, *, retries, ok, cid):
    """Forensic record of one model call (01-09): the engine's only LLM call is here, so this
    single chokepoint logs every current/future judgment tool's cost/operability accounting —
    plane · tool · tier · retries · ok. Emitted for the engine's own audit; the run-trace
    observer happens to read it. Stays unaware of measurement (no measurement-specific code)."""
    if elog is None:
        return
    elog.event("model_call", cid=cid, plane="control", tool=tool,
               tier=TIER.get(tool), retries=retries, ok=bool(ok))


def call(tool, payload, ctx, max_retries=2, elog=None, cid=None):
    """Run one judgment tool. Returns (ok, output_dict_or_None, raw_attempts).

    ok=False means the invalid-output budget was exhausted -> the caller maps
    this to `unclassified` / the `*` SENTRY catch-all (contracts §4).

    `elog` (an EventLog) + `cid` are the forensic sink: one `model_call` record is emitted
    per call from this single chokepoint — never from the fsm call site (one place, every tool).
    """
    validate = VALIDATORS[tool]
    stub = _stub_response(tool)
    if stub is not None:
        err = validate(stub, ctx)
        ok = err is None
        _record_model_call(elog, tool, retries=0, ok=ok, cid=cid)
        return ok, (stub if ok else None), [stub]

    raw_attempts = []
    correction = None
    for _ in range(max_retries + 1):
        raw = _call_llm(tool, payload, ctx, correction)
        raw_attempts.append(raw)
        obj = _extract_json(raw)
        if obj is None:
            correction = "output was not valid JSON"
            continue
        err = validate(obj, ctx)
        if err is None:
            _record_model_call(elog, tool, retries=len(raw_attempts) - 1, ok=True, cid=cid)
            return True, obj, raw_attempts
        correction = err
    _record_model_call(elog, tool, retries=len(raw_attempts) - 1, ok=False, cid=cid)
    return False, None, raw_attempts
