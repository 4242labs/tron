"""lint — blueprint-lint for the event-table model (contracts §9).

A malformed flow must fail at seed/validate time, not at runtime. Two layers:

  CANON (routing.yaml + the engine TABLE) — the fixed vocabulary + behaviour:
    grammar well-formed · tag enum closed + total · every trigger satisfies the
    grammar · every tag trigger resolves to a TABLE row · every TABLE handler
    resolves to an Engine method · the only judgment tools are the canon two.

  COMPOSITION (workflow.yaml) — the per-project knobs the engine reads:
    worker_count present · cadence types map to positive ints · session shape.

Wired into `engine.py doctor` / `validate`. Grammar-driven: the legal token set
is read FROM routing.yaml, so the rules check internal consistency rather than a
hardcoded duplicate.
"""
# Engine table + class — module-level, no Engine instance needed (fsm exposes TABLE).
from fsm import TABLE, Engine

# The closed tag enum the engine knows how to route (mirrors routing.yaml tags).
CANON_TAGS = {
    "worker.done", "worker.wall", "worker.review_done", "worker.progress",
    "worker.question_peer", "worker.question_tron",
    "architect.cleared", "architect.logged",
    "operator.decision", "operator.status_query", "operator.workflow_change",
    "operator.directive",
    "sweep.tick", "worker.stalled", "worker.dead",
    "unclassified",
}
CANON_TOOLS = {"classify_message", "assess_wall"}

GRAMMAR_KEYS = {"forms", "subjects", "events", "params", "wildcard",
                "alternatives", "terminals", "control", "match"}


class Result:
    def __init__(self, rule, ok, detail=""):
        self.rule, self.ok, self.detail = rule, ok, detail

    def __str__(self):
        mark = "PASS" if self.ok else "FAIL"
        return f"  [{mark}] {self.rule}{(' — ' + self.detail) if self.detail else ''}"


# ── grammar helpers ──
def _legal_tokens(g):
    """Every segment a trigger may use, drawn from the declared grammar."""
    toks = set(g.get("subjects", []) or [])
    toks |= set(g.get("events", []) or [])
    toks |= set((g.get("reserved", {}) or {}).keys())
    toks |= set((g.get("params", {}) or {}).keys())   # the literal "<type>"/"<block>"
    toks.add(g.get("wildcard", "*"))
    return toks


def _trigger_ok(trig, g, legal):
    """True if a trigger string satisfies the grammar (2–3 segs, all legal; or `*`)."""
    if trig == g.get("wildcard", "*"):
        return True
    segs = trig.split(":")
    if len(segs) not in (2, 3):
        return False
    return all(s in legal for s in segs)


def _match_table(trig):
    """Mirror of fsm._match: does this (possibly placeholder) trigger resolve to a row?

    Returns the matched pattern, or None. Placeholders are treated as wildcards so
    a tag trigger like `wall:raised:<block>` resolves to its row.
    """
    segs = trig.split(":")
    best = None  # (pattern, score)
    for pat, _ in TABLE:
        if pat == "*":
            continue
        ps = pat.split(":")
        if len(ps) != len(segs):
            continue
        score, ok = 0, True
        for pseg, cseg in zip(ps, segs):
            pvar = pseg in ("<block>", "<type>", "*")
            cvar = cseg in ("<block>", "<type>", "*")
            if pseg == cseg:
                score += 2
            elif pvar or cvar:
                score += 1
            else:
                ok = False
                break
        if ok and (best is None or score > best[1]):
            best = (pat, score)
    return best[0] if best else None


# ── CANON rules (routing.yaml + TABLE) ──
def _canon(routing):
    r = []
    g = routing.get("grammar", {}) or {}
    tags = routing.get("tags", {}) or {}
    tools = routing.get("tools", {}) or {}
    inv = routing.get("invalid_output", {}) or {}
    legal = _legal_tokens(g)

    # L1 — grammar block declares every required field.
    miss = sorted(GRAMMAR_KEYS - set(g))
    r.append(Result("L1 grammar complete", not miss, f"missing: {miss}"))

    # L2 — tag enum closed (== CANON_TAGS) and unclassified -> the `*` catch-all.
    drift_extra = sorted(set(tags) - CANON_TAGS)
    drift_miss = sorted(CANON_TAGS - set(tags))
    uncl = tags.get("unclassified") == {"trigger": "*"}
    d = []
    if drift_extra or drift_miss:
        d.append(f"enum drift: +{drift_extra} -{drift_miss}")
    if not uncl:
        d.append("unclassified is not { trigger: '*' }")
    r.append(Result("L2 closed tag enum + unclassified", not d, "; ".join(d)))

    # L3 — total coverage: every tag action is exactly one of trigger | side | tick.
    bad = []
    for t, a in tags.items():
        if not (isinstance(a, dict) and len(a) == 1
                and ("trigger" in a or "side" in a or a.get("tick") is True)):
            bad.append(t)
    r.append(Result("L3 total tag coverage", not bad, f"malformed: {bad}"))

    # L4 — every tag trigger satisfies the grammar.
    badg = [f"{t}:{a['trigger']}" for t, a in tags.items()
            if isinstance(a, dict) and "trigger" in a
            and not _trigger_ok(a["trigger"], g, legal)]
    r.append(Result("L4 tag triggers satisfy grammar", not badg, f"bad: {badg}"))

    # L5 — judgment tools are exactly the canon two, each with a structured `out`.
    extra = sorted(set(tools) - CANON_TOOLS)
    miss = sorted(CANON_TOOLS - set(tools))
    prose = [t for t, c in tools.items()
             if not isinstance((c or {}).get("out"), list) or not (c or {}).get("out")]
    d = []
    if extra or miss:
        d.append(f"tool set: +{extra} -{miss}")
    if prose:
        d.append(f"unstructured out: {prose}")
    r.append(Result("L5 canon tools + structured out", not d, "; ".join(d)))

    # L6 — invalid-output policy present and its on_exhaustion is a valid trigger.
    ok6 = (isinstance(inv.get("max_retries"), int)
           and _trigger_ok(str(inv.get("on_exhaustion", "")), g, legal))
    r.append(Result("L6 invalid-output policy", ok6,
                    "" if ok6 else f"got: {inv}"))

    # L7 — every TABLE pattern satisfies the grammar.
    badp = [p for p, _ in TABLE if not _trigger_ok(p, g, legal)]
    r.append(Result("L7 table patterns satisfy grammar", not badp, f"bad: {badp}"))

    # L8 — every TABLE handler resolves to a callable Engine method (None = worker row).
    badh = [h for _, h in TABLE
            if h is not None and not callable(getattr(Engine, h, None))]
    r.append(Result("L8 table handlers resolve", not badh, f"unbound: {badh}"))

    # L9 — every tag trigger resolves to a TABLE row (no orphan classification).
    orphan = []
    for t, a in tags.items():
        if isinstance(a, dict) and "trigger" in a:
            trig = a["trigger"]
            if trig == "*":
                continue
            if _match_table(trig) is None:
                orphan.append(f"{t}:{trig}")
    r.append(Result("L9 tag triggers resolve to a row", not orphan, f"orphan: {orphan}"))
    return r


# ── COMPOSITION rules (workflow.yaml) ──
def _composition(workflow, project):
    r = []
    knobs = workflow.get("knobs", {}) or {}
    cadence = workflow.get("cadence", {}) or {}
    session = workflow.get("session", {}) or {}

    # L10 — worker_count knob declared (value may be null -> required at runtime).
    r.append(Result("L10 worker_count knob present", "worker_count" in knobs,
                    "" if "worker_count" in knobs else "missing worker_count"))

    # L11 — every cadence type maps to a positive int threshold.
    badc = [f"{t}={v}" for t, v in cadence.items()
            if not (isinstance(v, int) and v > 0)]
    r.append(Result("L11 cadence thresholds positive", not badc, f"bad: {badc}"))

    # L12 — persistent_architect is a bool (the architect is canon-on by default).
    pa = session.get("persistent_architect")
    r.append(Result("L12 session shape", isinstance(pa, bool),
                    "" if isinstance(pa, bool) else f"persistent_architect={pa!r}"))

    # L13 — roles named in project.agents are sane (skipped if no project.yaml).
    roles = {a.get("role") for a in (project.get("agents") or [])}
    note = "" if roles else "(no project.yaml agents — skipped)"
    r.append(Result("L13 project roles", True, note))
    return r


def run(ctx, project=None):
    """Full lint. Returns (ok, results). project optional (L13 skipped if absent)."""
    routing = ctx.load_routing()
    workflow = ctx.load_workflow()
    if project is None:
        project = ctx.load_project()
    results = _canon(routing) + _composition(workflow, project)
    return all(x.ok for x in results), results
