"""lint — blueprint-lint for the event-table model (contracts §9).

A malformed flow must fail at seed/validate time, not at runtime. Two layers:

  CANON (routing.yaml + the engine TABLE) — the fixed vocabulary + behaviour:
    grammar well-formed · tag enum closed + total · every trigger satisfies the
    grammar · every tag trigger resolves to a TABLE row · every TABLE handler
    resolves to an Engine method · the only judgment tools are the canon two.

  COMPOSITION (knobs.yaml) — the per-project knobs the engine reads:
    worker_count present · cadence types map to positive ints · session shape ·
    WAKE timing knobs (cooldown/ceiling) positive.

  PROMPTS (prompts/registry.yaml) — the PMT layer the engine imports at tick:
    every registry id resolves to a self-contained file · every worker-channel
    message references a PMT id that the registry knows (closed + total).

Wired into `engine.py doctor` / `validate`. Grammar-driven: the legal token set
is read FROM routing.yaml, so the rules check internal consistency rather than a
hardcoded duplicate.
"""
import os

import util
# Engine table + class — module-level, no Engine instance needed (fsm exposes TABLE).
from fsm import TABLE, Engine

# The closed tag enum the engine knows how to route (mirrors routing.yaml tags).
CANON_TAGS = {
    "worker.done", "worker.wall", "worker.review_done", "worker.await_confirm",
    "worker.progress", "worker.question_peer", "worker.question_tron",
    "architect.reconciled", "architect.logged",
    "operator.decision", "operator.status_query", "operator.knob_change",
    "operator.directive",
    "sweep.tick", "worker.stalled", "worker.dead",
    "unclassified",
}
CANON_TOOLS = {"classify_message"}
# TRON ships and requires NO agents — they are the project's (realign decision #11).
# L13 therefore hardcodes no roster; it only checks that the roles TRON's OWN config
# (cadence lenses, peer-consults) references resolve to a persona the project provides.

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


# ── COMPOSITION rules (knobs.yaml) ──
def _composition(comp, project):
    r = []
    knobs = comp.get("knobs", {}) or {}
    cadence = comp.get("cadence", {}) or {}
    session = comp.get("session", {}) or {}

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

    # L13 — TRON's config resolves against the project's agents (skipped if no project.yaml).
    # TRON hardcodes no roster (it ships zero agents — realign #11). It only checks the roles
    # its OWN config references against what the project supplies: each cadence lens must have a
    # reviewer persona the engine can resolve (`reviewer-<lens>` OR a generic `reviewer`, mirroring
    # fsm._handover), and every peer-consult role must exist. It does NOT require architect/engineer/
    # reviewer by name — those are the project's personas, validated by the seeder at seed time.
    agents = project.get("agents")
    if not agents:
        r.append(Result("L13 config resolves to project agents", True, "(no project.yaml agents — skipped)"))
    else:
        roles = {a.get("role") for a in agents}
        pc = comp.get("peer_consults") or []
        pc_roles = {p.get(k) for p in pc for k in ("worker", "may_consult") if p.get(k)}
        cadence_unresolved = sorted(t for t in cadence
                                    if f"reviewer-{t}" not in roles and "reviewer" not in roles)
        unknown = sorted(pc_roles - roles)
        bad = []
        if cadence_unresolved:
            bad.append(f"cadence lens(es) with no reviewer persona (reviewer-<lens> or reviewer): {cadence_unresolved}")
        if unknown:
            bad.append(f"peer_consults names undeclared role(s): {unknown}")
        r.append(Result("L13 config resolves to project agents", not bad, "; ".join(bad)))

    # L14 — WAKE timing knobs are positive ints (fixed knobs; the daemon reads them, 01-04).
    badw = [f"{k}={knobs.get(k)!r}" for k in ("wake_cooldown_sec", "wake_ceiling_sec")
            if not (isinstance(knobs.get(k), int) and knobs.get(k) > 0)]
    r.append(Result("L14 WAKE timing knobs positive", not badw, f"bad: {badw}"))

    # L15 — WAKE cooldown floor must not exceed the ceiling (only checkable once L14 holds).
    if badw:
        r.append(Result("L15 WAKE cooldown <= ceiling", False, "(knobs invalid — see L14)"))
    else:
        ok15 = knobs["wake_cooldown_sec"] <= knobs["wake_ceiling_sec"]
        r.append(Result("L15 WAKE cooldown <= ceiling", ok15,
                        "" if ok15 else f"cooldown {knobs['wake_cooldown_sec']}s > ceiling {knobs['wake_ceiling_sec']}s"))
    return r


# ── PROMPT rules (prompts/registry.yaml + messages.yaml) ──
def _prompts(ctx):
    """The PMT layer: a closed registry of self-contained prompt files, referenced by
    id from the worker-channel messages. Total = every worker `pmt:` ref resolves;
    Closed = every registry id maps to a file that exists."""
    r = []
    reg = (util.load_yaml(ctx.prompts_registry) or {}).get("prompts", {}) \
        if os.path.exists(ctx.prompts_registry) else None
    if reg is None:
        r.append(Result("L16 PMT registry present", False, f"no registry at {ctx.prompts_registry}"))
        return r

    # L16 — every registry id resolves to a self-contained file that exists.
    missing = []
    for pid, spec in reg.items():
        f = (spec or {}).get("file")
        if not f or not os.path.exists(os.path.join(ctx.prompts_dir, f)):
            missing.append(pid)
    r.append(Result("L16 PMT registry resolves to files", not missing, f"unresolved: {missing}"))

    # L17 — every worker-channel message references a PMT id the registry knows (total).
    msgs = (util.load_yaml(ctx.messages) or {}).get("templates", {})
    unknown, inlined = [], []
    for mid, tpl in msgs.items():
        if (tpl or {}).get("channel") != "worker":
            continue
        pid = (tpl or {}).get("pmt")
        if not pid:
            inlined.append(mid)                  # a worker line must carry a PMT, never inline copy
        elif pid not in reg:
            unknown.append(f"{mid}->{pid}")
    d = []
    if inlined:
        d.append(f"worker line(s) without a pmt ref: {inlined}")
    if unknown:
        d.append(f"pmt ref(s) not in registry: {unknown}")
    r.append(Result("L17 worker messages reference known PMTs", not d, "; ".join(d)))
    return r


def run(ctx, project=None):
    """Full lint. Returns (ok, results). project optional (L13 skipped if absent)."""
    routing = ctx.load_routing()
    comp = ctx.load_knobs()
    if project is None:
        project = ctx.load_project()
    results = _canon(routing) + _composition(comp, project) + _prompts(ctx)
    return all(x.ok for x in results), results
