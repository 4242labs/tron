"""lint — blueprint-lint (contracts §9, L1-L13).

A malformed flow must fail at seed/validate time, not at runtime. Canon rules
(L1-L5) check routing.yaml + the tag enum; composition rules (L6-L13) check
workflow.yaml against routing.yaml + project.yaml. Wired into doctor/validate.
"""
import os

# ── canon reference (contracts §1, §2) — the fixed shapes lint enforces ──
CANON_PRIMITIVES = {
    "dispatch":        {"edges": {"done", "wall", "stalled"},
                        "tools": {"classify_message", "assess_stall"}},
    "review":          {"edges": {"clean", "findings"}, "tools": {"classify_message"}},
    "gate":            {"edges": {"pass", "fail"}, "tools": set()},
    "escalate":        {"edges": {"resolved", "abort"}, "tools": {"classify_message"}},
    "findings-triage": {"edges": {"fixes", "none"}, "tools": {"triage", "scope_fix"}},
}

CANON_TAGS = {
    "worker.done", "worker.wall", "worker.findings", "worker.question_peer",
    "worker.question_tron", "worker.blocked_dep", "worker.progress",
    "operator.decision", "operator.abort", "operator.bug_report",
    "operator.status_query", "operator.workflow_change", "operator.directive",
    "sweep.tick", "worker.stalled", "worker.dead", "gate.pass", "gate.fail",
    "unclassified",
}

RESERVED_TARGETS = {"next", "end", "escalate"}
KNOWN_KNOBS = {"reviewer_threshold", "max_concurrent_engineers",
               "silence_ping_min", "silence_escalate_min", "git"}


class Result:
    def __init__(self, rule, ok, detail=""):
        self.rule, self.ok, self.detail = rule, ok, detail

    def __str__(self):
        mark = "PASS" if self.ok else "FAIL"
        return f"  [{mark}] {self.rule}{(' — ' + self.detail) if self.detail else ''}"


def _canon(routing):
    r = []
    prims = routing.get("primitives", {})
    tags = routing.get("tags", {})
    tools = routing.get("tools", {})

    # L1 — each primitive declares exactly its canon edge set.
    bad = []
    for name, spec in CANON_PRIMITIVES.items():
        got = set((prims.get(name) or {}).get("edges", []))
        if got != spec["edges"]:
            bad.append(f"{name}: {sorted(got)} != {sorted(spec['edges'])}")
    extra = set(prims) - set(CANON_PRIMITIVES)
    if extra:
        bad.append(f"unknown primitives: {sorted(extra)}")
    r.append(Result("L1 primitive edge sets", not bad, "; ".join(bad)))

    # L2 — tag enum closed; unclassified -> hardwired escalate.
    closed = set(tags) == CANON_TAGS
    uncl = tags.get("unclassified") == "hardwired:escalate"
    d = []
    if not closed:
        d.append(f"enum drift: +{sorted(set(tags) - CANON_TAGS)} -{sorted(CANON_TAGS - set(tags))}")
    if not uncl:
        d.append("unclassified is not hardwired:escalate")
    r.append(Result("L2 closed tag enum + unclassified", closed and uncl, "; ".join(d)))

    # L3 — total coverage: every tag maps to a well-formed action.
    unmapped = [t for t, a in tags.items()
                if not (isinstance(a, str) and (a.startswith("edge:") or a.startswith("side:")
                        or a == "tick" or a == "hardwired:escalate"))]
    r.append(Result("L3 total tag coverage", not unmapped, f"unmapped: {unmapped}"))

    # L4 — every tool a primitive references has a contract in routing.tools.
    missing = []
    for name, spec in CANON_PRIMITIVES.items():
        for t in (prims.get(name) or {}).get("tools", []):
            if t not in tools:
                missing.append(f"{name}->{t}")
    r.append(Result("L4 tool contracts present", not missing, f"missing: {missing}"))

    # L5 — no tool output is free prose: every tool declares a structured `out` list.
    prose = [t for t, c in tools.items() if not isinstance(c.get("out"), list) or not c.get("out")]
    r.append(Result("L5 structured tool outputs", not prose, f"unstructured: {prose}"))
    return r


def _composition(routing, workflow, project):
    r = []
    prims = routing.get("primitives", {})
    steps = workflow.get("steps", []) or []
    by_id = {s["id"]: s for s in steps}
    entry = workflow.get("entry")
    knobs = set((workflow.get("knobs") or {}).keys())
    roles = {a.get("role") for a in (project.get("agents") or [])}

    # L6 — every step.primitive exists.
    badp = [s["id"] for s in steps if s.get("primitive") not in prims]
    r.append(Result("L6 primitives exist", not badp, f"bad: {badp}"))

    # L7 — every exposed edge bound; no unbound, no extra.
    unbound = []
    for s in steps:
        spec = prims.get(s.get("primitive"))
        if not spec:
            continue
        exposed = set(spec.get("edges", []))
        bound = set((s.get("edges") or {}).keys())
        if exposed - bound:
            unbound.append(f"{s['id']}: missing {sorted(exposed - bound)}")
        if bound - exposed:
            unbound.append(f"{s['id']}: extra {sorted(bound - exposed)}")
    r.append(Result("L7 all edges bound", not unbound, "; ".join(unbound)))

    # L8 — every target resolves to a step id or reserved target.
    badt = []
    for s in steps:
        for edge, tgt in (s.get("edges") or {}).items():
            if tgt not in by_id and tgt not in RESERVED_TARGETS:
                badt.append(f"{s['id']}.{edge}->{tgt}")
    r.append(Result("L8 targets resolve", not badt, f"dangling: {badt}"))

    # L9 — no orphan steps (all reachable from entry).
    reach, frontier = set(), [entry] if entry in by_id else []
    while frontier:
        cur = frontier.pop()
        if cur in reach:
            continue
        reach.add(cur)
        for tgt in (by_id[cur].get("edges") or {}).values():
            if tgt in by_id and tgt not in reach:
                frontier.append(tgt)
    orphans = set(by_id) - reach
    r.append(Result("L9 no orphan steps", not orphans and entry in by_id,
                    f"orphans: {sorted(orphans)}" if orphans else
                    ("" if entry in by_id else f"entry '{entry}' not a step")))

    # L10 — a terminal (end) is reachable from every step.
    def reaches_end(start):
        seen, fr = set(), [start]
        while fr:
            c = fr.pop()
            if c in seen:
                continue
            seen.add(c)
            for tgt in (by_id.get(c, {}).get("edges") or {}).values():
                if tgt == "end":
                    return True
                if tgt in by_id:
                    fr.append(tgt)
        return False
    traps = [sid for sid in by_id if not reaches_end(sid)]
    r.append(Result("L10 end reachable from all", not traps, f"traps: {traps}"))

    # L11 — every role named in a step exists in project.agents.
    badr = []
    for s in steps:
        role = s.get("role")
        if role and roles and role not in roles:
            badr.append(f"{s['id']}:{role}")
    note = "" if roles else "(no project.yaml agents — skipped)"
    r.append(Result("L11 roles exist", not badr, "; ".join(badr) or note))

    # L12 — escalate step defined and unclassified hardwires to it.
    has_escalate = any(s.get("primitive") == "escalate" for s in steps)
    uncl_ok = routing.get("tags", {}).get("unclassified") == "hardwired:escalate"
    r.append(Result("L12 escalate wired", has_escalate and uncl_ok,
                    "" if has_escalate else "no escalate step"))

    # L13 — every knob reference resolves to a declared knob.
    badk = []
    for s in steps:
        c = s.get("concurrency")
        if isinstance(c, str) and c not in knobs:
            badk.append(f"{s['id']}.concurrency={c}")
        cad = (s.get("cadence") or {}).get("every_n_blocks")
        if isinstance(cad, str) and cad not in knobs:
            badk.append(f"{s['id']}.cadence={cad}")
    r.append(Result("L13 knob refs resolve", not badk, "; ".join(badk)))
    return r


def run(ctx, project=None):
    """Full lint. Returns (ok, results). project optional (L11 skipped if absent)."""
    routing = ctx.load_routing()
    workflow = ctx.load_workflow()
    if project is None:
        project = ctx.load_project()
    results = _canon(routing) + _composition(routing, workflow, project)
    return all(x.ok for x in results), results
