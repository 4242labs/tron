"""judge — the only place the engine calls an LLM (contracts §3, §4).

The canon set is TWO bounded, typed questions:
  classify_message (cheap)  put an inbound worker/operator message into exactly one
                            tag from routing.yaml's closed enum (+ structured slots).
  aide (strong, ADR-0003 D-J)  the operator's LLM advisor at the bootup nodes
                            (ND-01-08 SET SCOPE, ND-01-09 SET COUNTS, ND-01-14
                            RESOLVE — console.py; 01-36 reuses this same lane at
                            ND-02-10/ND-09) — reads the PROJECT DOCS
                            (`context.md`+`pipeline.md`+relevant block doc(s), see
                            `build_aide_context`/`call_aide` below) as its context
                            instead of tron.md. Advisory only — it never itself
                            decides flow, and it is NEVER replaced by a
                            deterministic/heuristic stand-in (operator hard rule):
                            fail-open to a built-in default model, and a
                            runtime-unavailable call degrades to "proceed unaided",
                            never a heuristic answer.

The prompt context (tron.md for classify_message; Project Docs for aide) leads the
prompt; the tool instruction names the decision; the model must return JSON in the
tool's exact shape. The runner schema-validates every return; invalid output is
retried (budget 2) then collapses to `unclassified` -> the `*` SENTRY catch-all
(classify_message) or "proceed unaided" (aide) — never free prose reaching the flow.

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
# ADR-0003 D-J reconciliation (a): AIDE's built-in default model — an engine-builtin
# LLM lane like classify_message, NOT a roles.yaml capability class. Overridable per
# session via the bootup model question / a TRON-owned knob (console._ask_aide_model
# -> eng.st.live_config["aide_model"], never roles.yaml) — this constant is only the
# fail-open floor when neither supplies one.
AIDE_DEFAULT_MODEL = os.environ.get("TRON_MODEL_AIDE", STRONG)
TIER = {"classify_message": CHEAP, "aide": AIDE_DEFAULT_MODEL}

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


def _v_aide(o, ctx):
    """ADR-0003 D-J: AIDE's output is a typed shape too (never free prose reaching the
    operator unchecked) — `advice` is always required; `recommended_block` (SET SCOPE)
    and `choices` (RESOLVE) are mode-specific and OPTIONAL here (the mode itself is
    caller-declared in the payload, not re-validated against the output).

    T5 (01-36, ADR-0003 D-J, ND-09 PARLEY `ask`): `answered` is a NEW optional bool
    — `ask` mode's own signal that AIDE could/couldn't answer INPUT.question from the
    Project Docs (absent for every other mode). Optional here for the same reason
    `recommended_block`/`choices` are: the mode itself is caller-declared, not
    re-validated against the output shape — a caller that ignores it (every non-ask
    mode) is unaffected."""
    if not isinstance(o, dict):
        return "aide output must be a JSON object"
    advice = o.get("advice")
    if not isinstance(advice, str) or not advice.strip():
        return "aide output missing a non-empty 'advice' string"
    rb = o.get("recommended_block")
    if rb is not None and not isinstance(rb, str):
        return "aide 'recommended_block' must be a string when present"
    choices = o.get("choices")
    if choices is not None and not (isinstance(choices, list) and choices
                                     and all(isinstance(c, str) and c.strip() for c in choices)):
        return "aide 'choices' must be a non-empty list of strings when present"
    answered = o.get("answered")
    if answered is not None and not isinstance(answered, bool):
        return "aide 'answered' must be a boolean when present"
    return None


VALIDATORS = {"classify_message": _v_classify, "aide": _v_aide}

INSTRUCTIONS = {
    "classify_message":
        "TOOL: classify_message. Put the inbound message in exactly one tag from the "
        "closed vocabulary (or `unclassified`). Pull any block id / reviewer type / "
        "operator decision into slots. Return JSON: "
        '{"tag": <tag>, "slots": {<pulled fields>}, "confidence": <0..1>}.',
    "aide":
        "TOOL: aide. You are AIDE (ADR-0003 D-J), the operator's LLM advisor — you "
        "READ the PROJECT DOCS supplied above (context.md + pipeline.md + any named "
        "block doc(s)) and reason over them; you are advisory only and NEVER a "
        "deterministic/heuristic stand-in. INPUT.mode names your task: 'scope' — "
        "advise the operator on run scope, including which open, dependency-clear "
        "block looks best to pick up next; 'counts' — advise on the worker_count "
        "knob (flag an unusual-but-valid or below-floor count, otherwise a brief "
        "affirmation); 'resolve' — brief the operator on INPUT.detail and offer "
        "exactly three named choices (block 01-36, ADR-0003 D-J: this mode now "
        "covers BOTH the bootup RESOLVE node, reached when a resumed run's MANIFEST "
        "can't be reconciled, AND an in-tick escalation brief for a parked operator "
        "case — INPUT.detail is the thing needing a brief either way, bootup "
        "conflict or live case); 'ask' (block 01-36, ADR-0003 D-J, ND-09 PARLEY) — "
        "attempt to answer INPUT.question STRICTLY from the Project Docs above; if "
        "you genuinely cannot answer it from them, say so in 'advice' (a short "
        "reason, never a guess) and set 'answered' to false. Return JSON: "
        "{\"advice\": <str — the answer in 'ask' mode, or a short reason you "
        "can't answer it>, \"recommended_block\": <block id string, scope mode "
        "only, else null>, \"choices\": [<exactly three short strings>, resolve "
        "mode only, else null], \"answered\": <bool, ask mode only, else null>}.",
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


def _call_llm(tool, payload, ctx, correction=None, context=None, model=None):
    """`context` defaults to tron.md (classify_message's own prompt context, unchanged);
    a caller may supply a different one (aide's Project Docs — `build_aide_context`)
    instead of a second hardcoded read path. `model` defaults to `TIER[tool]`; a
    caller may override it (aide's session/knob resolution — never a second TIER
    table).

    `tool == "aide"` under bare TRON_DRY (no explicit TRON_JUDGE_STUB) never reaches a
    real subprocess: this is AIDE's OWN fail-safe contract (ADR-0003 D-J reconciliation
    (e), "runtime-unavailable -> proceed unaided"), not a generic dry-mode rule — it
    is scoped to `aide` alone so `classify_message`'s behavior/tests are byte-
    identical to before this block (many existing dry suites transitively import
    sentry_test, which sets TRON_DRY=1 as a process-wide side effect, and some of
    them monkeypatch subprocess.run directly to exercise classify_message's real
    call shape — that path must stay untouched). This is what makes
    `console.bootup`'s new AIDE advisories safe to call unconditionally from every
    existing dry test suite: an aide call with no stub degrades instantly to
    ok=False ("proceed unaided"), never a hang/spawn. A caller that wants to
    exercise AIDE's own real call shape under TRON_DRY (a mocked-LLM unit test, e.g.
    this block's AC-5) monkeypatches this function directly, which bypasses this
    guard entirely (the guard lives in THIS body, never reached by a replacement)."""
    if tool == "aide" and os.environ.get("TRON_DRY") and not os.environ.get("TRON_JUDGE_STUB"):
        return ""
    if context is None:
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
    cmd = [RUNTIME, "-p", "--model", model or TIER[tool]]
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


def call(tool, payload, ctx, max_retries=2, elog=None, cid=None, context=None, model=None):
    """Run one judgment tool. Returns (ok, output_dict_or_None, raw_attempts).

    ok=False means the invalid-output budget was exhausted -> the caller maps
    this to `unclassified` / the `*` SENTRY catch-all (classify_message) or
    "proceed unaided" (aide — never a heuristic substitute, ADR-0003 D-J).

    `elog` (an EventLog) + `cid` are the forensic sink: one `model_call` record is emitted
    per call from this single chokepoint — never from the fsm call site (one place, every tool).

    `context`/`model` (ADR-0003 D-J): optional per-call overrides of the default prompt
    context (tron.md) and tier model — aide's own context (Project Docs) and model
    (session/knob-resolved, fail-open) ride these; classify_message never passes them
    and behaves exactly as before.
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
        raw = _call_llm(tool, payload, ctx, correction, context=context, model=model)
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


# ── AIDE Project-Docs context (ADR-0003 D-J reconciliation (d)) — SHARED infra: the
# ONE builder every aide call site reuses (bootup here; 01-36's ND-02-10/ND-09 later),
# never a per-caller copy. ──
def _read_if_exists(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    return None


def build_aide_context(paths, block_files=None):
    """The Project Docs every `aide` judge.call carries as its context — `context.md`
    + `pipeline.md` + the relevant block doc(s) — built from the SAME `paths` dict
    `ctx.repo_paths(ctx.load_project())` already resolves (never a second/duplicate
    path convention). `block_files` are blocks-dir-relative filenames (as
    `reader`'s parsed rows carry in `block_file`) or absolute paths — the caller
    (which already has the pipeline snapshot) resolves ids to filenames; this stays
    decoupled from `reader`. Missing files degrade silently to absence (never
    fabricated content) — a first-run/empty project still gets a best-effort
    context, never a crash."""
    paths = paths or {}
    root = paths.get("root") or ""
    pipeline_rel = paths.get("pipeline_rel") or "meta/pipeline.md"
    context_md_path = os.path.join(root, os.path.dirname(pipeline_rel), "context.md")
    sections = []
    for label, content in (
        ("context.md", _read_if_exists(context_md_path)),
        ("pipeline.md", _read_if_exists(paths.get("pipeline"))),
    ):
        if content is not None:
            sections.append(f"=== {label} ===\n{content}")
    blocks_dir = paths.get("blocks") or ""
    for name in (block_files or []):
        path = name if os.path.isabs(name) else os.path.join(blocks_dir, name)
        content = _read_if_exists(path)
        if content is not None:
            sections.append(f"=== block {name} ===\n{content}")
    return "\n\n".join(sections)


def call_aide(ctx, paths, mode, extra=None, block_files=None, model=None,
              max_retries=2, elog=None, cid=None):
    """The shared `aide` judge-tool entry point (ADR-0003 D-J): builds the
    Project-Docs context fresh for THIS call (`build_aide_context`), wraps `extra`
    into the mode-tagged payload (`mode` in {"scope", "counts", "resolve"} at this
    block's three bootup nodes; block 01-36 reuses "resolve" for ND-02-10's in-tick
    escalation brief and adds "ask" for ND-09's PARLEY open question), and calls
    the real `aide` LLM lane
    — the ONE call shape every aide site reuses, never a per-caller copy. Returns
    the same (ok, output_dict_or_None, raw_attempts) shape as `call()`; ok=False
    (runtime-unavailable) means the caller proceeds unaided — never a heuristic
    substitute (D-J reconciliation (e))."""
    context = build_aide_context(paths, block_files=block_files)
    payload = {"mode": mode, **(extra or {})}
    return call("aide", payload, ctx, max_retries=max_retries, elog=elog, cid=cid,
                context=context, model=model)
