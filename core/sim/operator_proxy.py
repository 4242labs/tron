"""core.sim.operator_proxy — the MODERATE-tier LLM operator stand-in (ADR-0007).

Complex SIMs page a real human. A moderate SIM cannot: it plants a wall whose
whole purpose is to reach the operator, and the live driver has NO human in it —
so the operator-owned case it opens would sit undecided forever, `session_end`
would never fire, and the run could only die on budget. The moderate tier is, by
construction, unreachable-green without an operator (ADR-0006 §3 FLAG).

This module IS that operator — an LLM, never a canned verb (AIDE-must-be-LLM).
Each poll it finds every case the engine has GENUINELY escalated to the operator
(`decision is None and owner == "operator"` — the exact predicate
`casestate.reping` uses, so it can NEVER act on an architect-owned case, and
`casestate.settle` double-guards that anyway), hands the case's `detail` to a
one-shot `claude` call, and injects the returned verb (resume/amend/abandon) +
note as a real `operator.decision` report into the engine inbox. The decision
then travels the SAME classify->router->settle path a real operator reply would.

Honest-surface guarantees (why this cannot reintroduce the false-green disease):
  • acts ONLY on `owner=="operator" and decision is None` (engine-escalated);
  • injects through the real inbox->classify->router->settle path (path A: a
    TAGGED structured report, `sender.kind=="operator"`), never by mutating a
    case dict directly;
  • provides the DECISION and nothing else — orphans, escalation counts, the
    planted signature and `session_end` all stay the engine's to produce, so it
    can only green a run a real operator settling the same case would also green;
  • a bad/nonsense decision does NOT green a run: an unparseable reply -> no
    valid verb -> no settle -> case stays open -> budget REJECT; a valid-but-
    wrong verb settles the case into a state the SIM can't drive to all-done ->
    no session_end -> REJECT. Honesty is enforced by the gate, not by luck.

Gating: OFF by default. `run_live(operator_proxy=True)` (the `--operator-proxy`
flag) turns it on for a MODERATE SIM only; a complex SIM runs WITHOUT it and its
pages reach the real human. Enabling is an explicit, INDEPENDENT choice — never
inferred from `expect_pages` (a complex SIM may also have expect_pages>0).

The `decide_fn(case) -> {"verb","note"} | None` seam is injectable: the default
is the real one-shot `claude` call (`_claude_decide`); rigs pass a deterministic
stub so the unit lock spends no tokens and asserts the WIRING, not a model's
judgment.
"""
import json
import os
import re
import subprocess
import sys

# Self-establish core/ on sys.path (the stack's own module pattern) so `import
# casestate` resolves regardless of the import site — both current importers
# already insert it; this makes the module not depend on that.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import casestate                       # noqa: E402 — VERBS + the settle path's own module

_OPERATOR_PROXY_WID = "operator-proxy"
_DECIDE_TIMEOUT_S = 90.0               # one-shot claude call ceiling (RD)
_MAX_ATTEMPTS = 3                      # per case: guard a malformed-output retry storm (RC)
_DECIDE_MODEL = "claude-opus-4-8"      # the operator is an LLM; opus by design


def _needs_operator(case):
    """Exactly `casestate.reping`'s predicate: an OPEN case the engine has
    escalated PAST the architect to the operator. Never an architect-owned case
    (architect-first is inviolate; `casestate.settle` refuses those too)."""
    return case.get("decision") is None and case.get("owner") == "operator"


def _decide_prompt(case):
    """The operator-agent's brief: the case, and a strict-JSON reply contract.
    Biases toward resume/amend for a resolvable wall; reserves abandon for a
    genuinely unbuildable/out-of-scope block (ADR-0007 §7)."""
    return (
        "You are the OPERATOR of an autonomous software-build orchestrator. A worker hit a\n"
        "wall that the architect could not absorb, so it was escalated to YOU to decide.\n\n"
        "Case:\n"
        f"  block:   {case.get('block')!r}\n"
        f"  worker:  {case.get('worker_id')!r}\n"
        f"  kind:    {case.get('kind')!r}\n"
        f"  source:  {case.get('source')!r}\n"
        f"  detail:  {case.get('detail')!r}\n\n"
        "Choose ONE action:\n"
        '  "resume"  — the wall is spurious or already resolved; let the worker proceed as-is.\n'
        '  "amend"   — the work needs a correction; the worker is sent back with your note.\n'
        '  "abandon" — this block is genuinely unbuildable / out of scope; drop it (it will\n'
        "              NOT be completed). Reserve this; prefer resume/amend for a wall that\n"
        "              can be resolved so the build can still finish.\n\n"
        "Reply with ONLY a JSON object, no prose, no code fence:\n"
        '{"verb": "resume|amend|abandon", "note": "<one sentence: your reasoning / instruction>"}'
    )


def _parse_decision(text):
    """Extract `{"verb","note"}` from the agent's reply, tolerant of prose or a
    ```json fence around the object. Returns None on anything unparseable or a
    verb not in `casestate.VERBS` (a malformed reply -> no settle -> honest)."""
    if not text:
        return None
    candidates = []
    stripped = text.strip()
    candidates.append(stripped)
    # any {...} blocks in the prose (last-first: the reply's final object wins)
    candidates.extend(reversed(re.findall(r"\{[^{}]*\}", text, re.DOTALL)))
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except (ValueError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue
        verb = obj.get("verb")
        if verb in casestate.VERBS:
            note = obj.get("note")
            return {"verb": verb, "note": (note if isinstance(note, str) else None)}
    return None


def _claude_decide(case):
    """The default `decide_fn`: a one-shot `claude` operator decision. Mirrors
    `engine/judge.py`'s pattern — prompt on STDIN (never argv: a reply that
    starts with `---` would be parsed as CLI flags), model as argv, stdout
    captured. Returns `{"verb","note"}` or None on ANY failure (parse/timeout/
    nonzero/missing binary) — the caller treats None as 'no decision this poll',
    never crashes."""
    try:
        from jobs import RUNTIME
    except Exception:   # noqa: BLE001 — engine/ not importable is a driver fault, not the proxy's
        return None
    try:
        r = subprocess.run(
            [RUNTIME, "-p", "--model", _DECIDE_MODEL],
            input=_decide_prompt(case),
            capture_output=True, text=True, timeout=_DECIDE_TIMEOUT_S,
        )
    except Exception:   # noqa: BLE001 — timeout, OSError (no binary), etc.
        return None
    if r.returncode != 0:
        return None
    return _parse_decision(r.stdout or "")


def _inject_decision(eng, case_id, decision):
    """Path A honest injection: append a TAGGED `operator.decision` report to the
    engine inbox. `classify` short-circuits on the tag (no model spend) and
    `router._route_decision` -> `casestate.settle` applies it. `sender.kind ==
    "operator"` marks it a genuine operator reply, exactly as a human's would.
    Returns True on a written line, False if the inbox append failed (mirrors the
    courier's own tolerant append — an IO fault must not raise out of the poll
    loop, and the caller must NOT mark a case decided on a write that never
    landed; the case simply stays open and is retried)."""
    rep = {
        "tag": "operator.decision",
        "slots": {
            "case_id": case_id,
            "verb": decision["verb"],
            "note": decision.get("note") or "operator-proxy (moderate SIM)",
        },
        "sender": {"kind": "operator", "id": _OPERATOR_PROXY_WID},
    }
    try:
        with open(eng.ctx.worker_inbox, "a") as ib:
            ib.write(json.dumps(rep) + "\n")
    except OSError as e:
        eng.log("flow", f"operator-proxy: inbox write FAILED for case {case_id!r} "
                        f"({e}) — decision NOT injected, case stays open (retried)")
        return False
    return True


def tick(eng, manifest, decided, attempts, decide_fn=_claude_decide):
    """One proxy poll. Scans operator-owned OPEN cases; for each not yet decided
    this run (and under the per-case attempt cap), calls `decide_fn` and injects
    a real `operator.decision` report — the SAME `eng.tick()` then drains and
    settles it. `decided` (a set of case_ids) and `attempts` (a dict) are the
    driver's per-run in-memory guards (RC). Decides AT MOST ONE case per poll (a
    decide call may block up to _DECIDE_TIMEOUT_S — bounding it to one keeps a
    poll's latency bounded no matter how many cases are open), so returns 0 or 1.
    Never raises for a bad decision or an inbox IO fault — both are logged no-ops."""
    cases = manifest.get("cases") or {}
    injected = 0
    for cid, case in cases.items():
        if not _needs_operator(case):
            continue
        if cid in decided:
            continue
        if attempts.get(cid, 0) >= _MAX_ATTEMPTS:
            continue
        attempts[cid] = attempts.get(cid, 0) + 1
        decision = decide_fn(case)
        # AT MOST ONE decide_fn call per poll: it can block up to _DECIDE_TIMEOUT_S,
        # so returning after the first candidate bounds a single poll's latency to
        # one call regardless of how many operator cases are open — the rest are
        # handled on the following polls (`decided`/`attempts` guard the re-work).
        # A truthy NON-dict return is treated as malformed (never `.get` on a
        # non-dict) — the same isinstance discipline `_parse_decision` applies.
        if not isinstance(decision, dict) or decision.get("verb") not in casestate.VERBS:
            eng.log("flow", f"operator-proxy: no valid decision for case {cid!r} "
                            f"(attempt {attempts[cid]}/{_MAX_ATTEMPTS}) — case stays "
                            f"open (a malformed reply never settles)")
            return injected
        if not _inject_decision(eng, cid, decision):
            return injected     # inbox write failed — retried next poll (bounded by cap)
        decided.add(cid)
        injected += 1
        eng.log("flow", f"operator-proxy: settled case {cid!r} -> {decision['verb']!r} "
                        f"(LLM operator stand-in; injected via the real settle path)")
        return injected
    return injected
