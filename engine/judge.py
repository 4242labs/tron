"""judge — the only place the engine calls an LLM (contracts §3, §4).

The canon set is TWO bounded, typed questions:
  classify_message (cheap)  put an inbound worker/operator message into exactly one
                            tag from routing.yaml's closed enum (+ structured slots).
  assess_wall (strong)      is an unexpected/ambiguous input actually the operator's
                            problem? (the `*` SCRIPTS path).

tron.md is the prompt context; the tool instruction names the decision; the model
must return JSON in the tool's exact shape. The runner schema-validates every
return; invalid output is retried (budget 2) then collapses to `unclassified`
-> the `*` SCRIPTS catch-all (which may wall). The LLM never sees the flow path
and never returns free prose to the flow.

NOT judgment tools, by design: review verdicts (review is a milestone), findings
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
TIER = {"classify_message": CHEAP, "assess_wall": STRONG}

_stub_cache = None
_stub_idx = {}
_tags_cache = None

# Engine-produced tags — the classifier must NEVER emit these (the engine's liveness
# sweep / cron produce them). Enforced at the validator, not just in the prompt.
ENGINE_ONLY = {"worker.stalled", "worker.dead", "sweep.tick"}


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


def _v_assess_wall(o, ctx):
    if not isinstance(o.get("wall"), bool):
        return "wall must be a bool"
    if o.get("kind") not in ("backend", "ui", "operator-only", "external"):
        return f"kind '{o.get('kind')}' invalid"
    return None


VALIDATORS = {"classify_message": _v_classify, "assess_wall": _v_assess_wall}

INSTRUCTIONS = {
    "classify_message":
        "TOOL: classify_message. Put the inbound message in exactly one tag from the "
        "closed vocabulary (or `unclassified`). Pull any block id / reviewer type / "
        "operator decision into slots. Return JSON: "
        '{"tag": <tag>, "slots": {<pulled fields>}, "confidence": <0..1>}.',
    "assess_wall":
        "TOOL: assess_wall. Is this actually the operator's problem, or solvable? "
        "Default solvable. Return JSON: "
        '{"wall": <bool>, "kind": "backend|ui|operator-only|external", "rationale": <one line>}.',
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
    cmd = ["claude", "-p", "--model", TIER[tool], "".join(parts)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.stdout or ""
    except subprocess.SubprocessError:
        return ""


def call(tool, payload, ctx, max_retries=2):
    """Run one judgment tool. Returns (ok, output_dict_or_None, raw_attempts).

    ok=False means the invalid-output budget was exhausted -> the caller maps
    this to `unclassified` / the `*` SCRIPTS catch-all (contracts §4).
    """
    validate = VALIDATORS[tool]
    stub = _stub_response(tool)
    if stub is not None:
        err = validate(stub, ctx)
        return (err is None), (stub if err is None else None), [stub]

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
            return True, obj, raw_attempts
        correction = err
    return False, None, raw_attempts
