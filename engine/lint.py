"""lint — blueprint-lint for the event-table model (contracts §9).

A malformed flow must fail at seed/validate time, not at runtime. Two layers:

  CANON (routing.yaml + the engine TABLE) — the fixed vocabulary + behaviour:
    grammar well-formed · tag enum closed + total · every trigger satisfies the
    grammar · every tag trigger resolves to a TABLE row · every TABLE handler
    resolves to an Engine method · the only judgment tools are the canon two.

  COMPOSITION (knobs.yaml) — the per-project knobs the engine reads:
    worker_count present · worker_model present (01-21) · cadence types map to
    positive ints · session shape · WAKE timing knobs (cooldown/ceiling) positive.

  PROMPTS (prompts/registry.yaml) — the PMT layer the engine imports at tick:
    every registry id resolves to a self-contained file · every worker-channel
    message references a PMT id that the registry knows (closed + total).

  VERSION (M-06) — the instance's stamped `project.yaml.tron_version` against its
    own copied canon `VERSION`: any gap means a partial/manual patch, not a full seed.

Wired into `engine.py doctor` / `validate`. Grammar-driven: the legal token set
is read FROM routing.yaml, so the rules check internal consistency rather than a
hardcoded duplicate.
"""
import os
import re

import util
# Engine table + class — module-level, no Engine instance needed (fsm exposes TABLE).
from fsm import TABLE, Engine

# The closed tag enum the engine knows how to route (mirrors routing.yaml tags).
CANON_TAGS = {
    "worker.online", "worker.recorded",
    "worker.done", "worker.wall", "worker.review_done", "worker.await_confirm",
    "worker.branch", "worker.progress", "worker.question_peer", "worker.question_tron",
    "architect.reconciled", "architect.logged", "architect.relay", "architect.escalate",
    "operator.decision", "operator.status_query", "operator.knob_change",
    "operator.directive",
    "worker.stalled", "worker.dead",
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

    # L3 — total coverage: every tag action is exactly one of trigger | side.
    bad = []
    for t, a in tags.items():
        if not (isinstance(a, dict) and len(a) == 1
                and ("trigger" in a or "side" in a)):
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

    # L25 (01-21 T1) — worker_model knob declared. Presence-only here (a null value ships
    # in canon, mirroring L10) — the REAL fail-closed enforcement is jobs.spawn_runner's
    # own spawn-time guard (WorkerModelUnconfigured), which refuses regardless of what
    # this lint sees. This just makes an operator's config drift (the knob deleted
    # entirely) visible at seed/validate time too, never only at first spawn.
    r.append(Result("L25 worker_model knob present", "worker_model" in knobs,
                    "" if "worker_model" in knobs else "missing worker_model"))

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
    # fsm._spawn), and every peer-consult role must exist. It does NOT require architect/engineer/
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


def _reply_contract(ctx):
    # L19 — the reply contract (01-11 FX-1/FX-5/FX-8): a worker reply that never reaches the
    # channel does not exist to the engine, so EVERY PMT must carry the channel instruction —
    # either flagged `reply_expected: true` (the loader appends the shared reply_line) or its
    # body references {report} inline (PMT-SPAWN's bespoke check-in). The shared line itself
    # must exist and render both {report} and {worker_id}. Data, not convention: a new PMT
    # cannot silently skip the channel.
    doc = util.load_yaml(ctx.prompts_registry) if os.path.exists(ctx.prompts_registry) else {}
    doc = doc or {}
    reg = doc.get("prompts", {})
    line = (doc.get("reply_line") or "")
    d19 = []
    if "{report}" not in line or "{worker_id}" not in line:
        d19.append("reply_line missing or lacks {report}/{worker_id}")
    for pid, spec in reg.items():
        if (spec or {}).get("reply_expected"):
            continue
        f = (spec or {}).get("file")
        path = os.path.join(ctx.prompts_dir, f) if f else None
        body = ""
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
        if "{report}" not in body:
            d19.append(f"{pid}: not reply_expected and no {{report}} in body")
    return [Result("L19 every PMT carries the reply channel", not d19, "; ".join(d19))]


def _reply_prefixes(ctx):
    # L20 — prescribed-prefix sync (S-4, tron-07 review cycle): each PMT's `reply_prefix`
    # (the registry is the single source) must appear in the PMT body AND in tron.md's
    # classify context, so a copy edit can't silently break the reply contract. The body may
    # carry the {block} slot literally; tron.md documents it as `<block>` — both accepted.
    doc = util.load_yaml(ctx.prompts_registry) if os.path.exists(ctx.prompts_registry) else {}
    reg = (doc or {}).get("prompts", {})
    tron_md = ""
    if os.path.exists(ctx.tron_md):
        with open(ctx.tron_md, encoding="utf-8") as fh:
            tron_md = fh.read()
    bad = []
    for pid, spec in reg.items():
        pfx = (spec or {}).get("reply_prefix")
        if not pfx:
            continue
        f = (spec or {}).get("file")
        path = os.path.join(ctx.prompts_dir, f) if f else None
        body = ""
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
        # The PMT body must carry the prefix VERBATIM (slots literal: `done {block} — local:`).
        if pfx not in body:
            bad.append(f"{pid}: body lacks prescribed prefix '{pfx}'")
        # tron.md documents slots as <block> and may abbreviate the shared head — require the
        # distinctive tail after the slot (`— local:`), else the head itself.
        tail = pfx.split("}")[-1].strip() if "}" in pfx else pfx
        probe = tail or pfx.split("{")[0].strip()
        if probe and probe not in tron_md:
            bad.append(f"{pid}: tron.md classify context lacks '{probe}'")
    return [Result("L20 prescribed reply prefixes in sync (registry -> PMT + tron.md)",
                   not bad, "; ".join(bad))]


def _emit_only_renders(ctx):
    # L21 — every worker-facing render goes through emit()'s slot injection (W4/S-4): a bare
    # `renderer.render(` outside emit() is the crash class that broke `stop --force` and the
    # reviewer release. Source check over the engine's own fsm.py; the sole legal call site
    # is inside `def emit(`.
    src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fsm.py")
    bad = []
    if os.path.exists(src_path):
        with open(src_path, encoding="utf-8") as fh:
            lines = fh.readlines()
        in_emit = False
        for i, ln in enumerate(lines, 1):
            stripped = ln.strip()
            if stripped.startswith("def "):
                in_emit = stripped.startswith("def emit(")
            if "renderer.render(" in ln and not in_emit:
                bad.append(f"fsm.py:{i}")
    return [Result("L21 worker renders only through emit()", not bad,
                   "bare renderer.render at: " + ", ".join(bad))]


def _paperwork_sanity(project):
    # L23 (tron-13 D1 rider) — paperwork_paths sanity: an entry covering the WHOLE repo
    # makes everything landable paperwork (fails); entries outside the pipeline's meta
    # dir are legal but NAMED, so the operator chose them with eyes open.
    if not project:
        return [Result("L23 paperwork paths sane", True, "(no project.yaml — skipped)")]
    paths = project.get("paperwork_paths")
    if not paths:
        return [Result("L23 paperwork paths sane", True, "(default: the pipeline's meta dir)")]
    whole = [p for p in paths if str(p).strip() in ("", ".", "./", "/")]
    if whole:
        return [Result("L23 paperwork paths sane", False,
                       f"entry covers the whole repo: {whole} — code is never paperwork")]
    meta = (os.path.dirname(project.get("pipeline_path") or "meta/pipeline.md")
            or "meta") + "/"
    outside = [str(p) for p in paths
               if not (str(p) == meta or str(p).startswith(meta))]
    note = (f"operator-declared paperwork outside {meta}: {', '.join(outside)}"
            if outside else "")
    return [Result("L23 paperwork paths sane", True, note)]


def _worker_contract(ctx):
    # L24 (worker contract) — the contract doc exists in the instance/canon and carries the
    # SAME closed vocabulary the engine enforces: every registry reply_prefix and every
    # structured verb (fsm REPORT_VERBS + the branch modifier) appears verbatim. The doc
    # teaches; the registry/engine enforce; drift between them is a lie to every worker.
    path = ctx.p("worker-contract.md")
    if not os.path.exists(path):
        return [Result("L24 worker contract present + in sync", False,
                       f"missing {path} — re-seed")]
    with open(path, encoding="utf-8") as fh:
        doc = fh.read()
    reg = util.load_yaml(ctx.prompts_registry) or {}
    missing = []
    for pid, meta in (reg.get("prompts") or {}).items():
        pfx = (meta or {}).get("reply_prefix")
        if not pfx:
            continue
        # Verbatim or prose-normalized ({block}/{type} -> <...>) — NO first-word fallback:
        # "done" appearing anywhere must never vouch for a specific prescription.
        probe = pfx.replace("{block}", "<block>").replace("{type}", "<type>")
        if pfx not in doc and probe not in doc:
            missing.append(f"{pid} prefix '{pfx}'")
    src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fsm.py")
    with open(src_path, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"REPORT_VERBS\s*=\s*\{(.*?)\n\s*\}", src, re.S)
    verbs = set(re.findall(r'"([a-z-]+)":\s*\(', m.group(1)) if m else [])
    # Both directions, backticked-form only: the doc must teach every live verb, and must
    # not teach a dead one (its taught set == the engine's enum).
    taught = set(re.findall(r"`([a-z-]+)`", doc)) & (verbs | {"done", "recorded", "wall",
                                                              "review-done", "clean"})
    for v in sorted(verbs - taught):
        missing.append(f"verb '{v}' not taught")
    for v in sorted(taught - verbs):
        missing.append(f"doc teaches dead verb '{v}'")
    for mod in ("--branch", "--block"):
        if f"`{mod}" not in doc and mod not in doc:
            missing.append(f"modifier '{mod}'")
    return [Result("L24 worker contract present + in sync", not missing,
                   "; ".join(missing))]


def _admission_table(ctx, routing):
    # L22 (S-2-full, tron-13) — the declarative ADMISSION table is TOTAL over routing.yaml's
    # gate-facing tags (trigger opens/advances a block gate), and _admit stays the ONLY
    # admission checkpoint (rider 4): exactly one call site outside its own definition.
    src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fsm.py")
    if not os.path.exists(src_path):
        return [Result("L22 admission table total + single checkpoint", False,
                       "fsm.py not found")]
    with open(src_path, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"ADMISSION\s*=\s*\{(.*?)\n\s*\}", src, re.S)
    keys = set(re.findall(r'"([a-z_.]+)"\s*:\s*\{', m.group(1))) if m else set()
    gate_facing = set()
    for tag, action in (routing.get("tags") or {}).items():
        trig = (action or {}).get("trigger") or ""
        if trig.startswith("block:next:") or trig.startswith("wall:raised"):
            gate_facing.add(tag)
    missing = sorted(gate_facing - keys)
    stray = sorted(keys - set((routing.get("tags") or {})))
    calls = len(re.findall(r"self\._admit\(", src))
    problems = []
    if not m:
        problems.append("no ADMISSION table in fsm.py")
    if missing:
        problems.append(f"gate-facing tags missing a row: {missing}")
    if stray:
        problems.append(f"ADMISSION rows for unknown tags: {stray}")
    if calls != 1:
        problems.append(f"_admit called {calls}x (must be exactly 1 — the _ingest checkpoint)")
    return [Result("L22 admission table total + single checkpoint", not problems,
                   "; ".join(problems))]


# ── VERSION rule (M-06): the instance's stamped tron_version vs its own copied
# canon VERSION — the two are written from the same source at every seed, so any
# gap means the instance was patched or partially re-seeded, not fully. A canon
# self-lint (no project.yaml, e.g. a contributor's `./tron validate`) has no
# per-project stamp to check — skipped, mirroring L13. ──
def _version(ctx, project):
    if not project:
        return [Result("L18 version stamp matches canon", True, "(no project.yaml — skipped)")]
    canon_v = ctx.load_version()
    stamped = project.get("tron_version")
    if canon_v is None:
        return [Result("L18 version stamp matches canon", False,
                        f"no VERSION file at {ctx.version_file} — re-seed")]
    if not stamped:
        return [Result("L18 version stamp matches canon", False,
                        f"instance has no tron_version stamp (pre-M-06 seed); canon is {canon_v} — re-seed")]
    if stamped != canon_v:
        return [Result("L18 version stamp matches canon", False,
                        f"drift: instance stamped {stamped}, canon VERSION is {canon_v} — re-seed")]
    return [Result("L18 version stamp matches canon", True)]


def run(ctx, project=None):
    """Full lint. Returns (ok, results). project optional (L13 skipped if absent)."""
    routing = ctx.load_routing()
    comp = ctx.load_knobs()
    if project is None:
        project = ctx.load_project()
    results = (_canon(routing) + _composition(comp, project) + _prompts(ctx)
               + _version(ctx, project) + _reply_contract(ctx)
               + _reply_prefixes(ctx) + _emit_only_renders(ctx)
               + _admission_table(ctx, routing) + _paperwork_sanity(project)
               + _worker_contract(ctx))
    return all(x.ok for x in results), results


# ── T7 (01-18 addendum): `python3 engine/lint.py` must never be a silent no-op ──
# This module has no __main__ of its own — `run()` is a library function the CLI
# (engine.py validate) drives with a resolved ctx/project. Called bare, the interpreter
# just imported the module and exited 0 having checked NOTHING: a fail-open trap for any
# tooling told to "run lint.py" directly. Fail loud instead: build the SAME ctx/project
# `engine.py cmd_validate` builds (mirrored here — a few lines, cheap) and run the real
# rule set for real when that's reproducible standalone; if construction itself fails
# (no instance here to lint), name `./lint.sh` as the real entrypoint and exit non-zero.
# Never exit 0 without having checked something.
if __name__ == "__main__":
    import sys as _sys

    def _main():
        tron_dir = os.environ.get("TRON_DIR") or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        try:
            from ctx import Ctx
            ctx = Ctx(tron_dir)
            project = ctx.load_project() or None
            ok, results = run(ctx, project)
        except Exception as e:
            print(f"lint.py: can't run the rule set standalone here "
                  f"({type(e).__name__}: {e}) — use ./lint.sh, the real entrypoint.")
            return 1
        print("blueprint-lint:")
        for r in results:
            print(r)
        print("OK" if ok else "FAILED")
        return 0 if ok else 1

    _sys.exit(_main())
