"""judge — the only place the engine calls an LLM (contracts §3, §4).

Each of the five judgment tools is one bounded, typed question: tron.md is the
prompt context, the tool instruction names the decision, and the model must
return JSON in the tool's exact output shape. The runner schema-validates every
return; invalid output is retried (budget 2) and then collapses to `unclassified`
-> the hardwired escalate edge. The LLM never sees the flow path and never
returns free prose to the flow. Model tiering: cheap vs strong.

Offline testability: set TRON_JUDGE_STUB to a JSON file mapping tool name ->
list of canned responses (popped in order). The FSM is then fully exercisable
without spending a token.
"""
import os
import re
import json
import subprocess

from lint import CANON_TAGS

CHEAP = os.environ.get("TRON_MODEL_CHEAP", "claude-haiku-4-5")
STRONG = os.environ.get("TRON_MODEL_STRONG", "claude-opus-4-8")
TIER = {
    "classify_message": CHEAP, "scope_fix": CHEAP,
    "triage": STRONG, "assess_wall": STRONG, "assess_stall": STRONG,
}

_stub_cache = None
_stub_idx = {}


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


# ── output validators: enforce tag+structured-slots, never prose (L5) ──
def _v_classify(o):
    if o.get("tag") not in CANON_TAGS:
        return f"tag '{o.get('tag')}' not in closed enum"
    if not isinstance(o.get("slots", {}), dict):
        return "slots must be an object"
    return None


def _v_triage(o):
    if not isinstance(o.get("verdicts"), list):
        return "verdicts must be a list"
    if not isinstance(o.get("fix_needed"), bool):
        return "fix_needed must be a bool"
    return None


def _v_scope_fix(o):
    for k in ("goal", "acceptance_criteria", "scope_bounds", "owner_role", "deps"):
        if k not in o:
            return f"missing '{k}'"
    if not isinstance(o.get("acceptance_criteria"), list):
        return "acceptance_criteria must be a list"
    return None


def _v_assess_wall(o):
    if not isinstance(o.get("wall"), bool):
        return "wall must be a bool"
    if o.get("kind") not in ("backend", "ui", "operator-only", "external"):
        return f"kind '{o.get('kind')}' invalid"
    return None


def _v_assess_stall(o):
    if not isinstance(o.get("stalled"), bool):
        return "stalled must be a bool"
    return None


VALIDATORS = {
    "classify_message": _v_classify, "triage": _v_triage, "scope_fix": _v_scope_fix,
    "assess_wall": _v_assess_wall, "assess_stall": _v_assess_stall,
}

INSTRUCTIONS = {
    "classify_message":
        "TOOL: classify_message. Put the inbound message in exactly one tag from the "
        "closed vocabulary (or `unclassified`). Return JSON: "
        '{"tag": <tag>, "slots": {<pulled fields>}, "confidence": <0..1>}.',
    "triage":
        "TOOL: triage. Judge the findings. Return JSON: "
        '{"verdicts": [{"finding_id": <id>, "agree": <bool>, "severity": <str>}], '
        '"fix_needed": <bool>}.',
    "scope_fix":
        "TOOL: scope_fix. Size one fix into a block a fresh engineer can own. Return JSON: "
        '{"goal": <str>, "acceptance_criteria": [<str>], '
        '"scope_bounds": {"in": [<str>], "out": [<str>]}, "owner_role": <str>, "deps": [<str>]}.',
    "assess_wall":
        "TOOL: assess_wall. Is this actually the operator's problem? Default solvable. "
        'Return JSON: {"wall": <bool>, "kind": "backend|ui|operator-only|external", '
        '"rationale": <one line>}.',
    "assess_stall":
        "TOOL: assess_stall. Slow, or actually stuck? Return JSON: "
        '{"stalled": <bool>, "rationale": <one line>}.',
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
    prompt = "".join(parts)
    cmd = ["claude", "-p", "--model", TIER[tool], prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.stdout or ""
    except subprocess.SubprocessError:
        return ""


def call(tool, payload, ctx, max_retries=2):
    """Run one judgment tool. Returns (ok, output_dict_or_None, raw_attempts).

    ok=False means the invalid-output budget was exhausted -> the caller maps
    this to `unclassified` / hardwired escalate (contracts §4).
    """
    stub = _stub_response(tool)
    if stub is not None:
        err = VALIDATORS[tool](stub)
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
        err = VALIDATORS[tool](obj)
        if err is None:
            return True, obj, raw_attempts
        correction = err
    return False, None, raw_attempts
