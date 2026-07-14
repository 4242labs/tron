"""core.sim.operator_proxy_rig — unit + honest-path lock for the MODERATE-tier
LLM operator-proxy (`core.sim.operator_proxy`, ADR-0007).

The proxy stands an LLM in for the operator on a moderate SIM: it finds every
case the engine escalated to the operator and injects a decision. The single
most important property — the one that keeps it from reintroducing the false-
green disease — is that it can ONLY settle a genuinely-escalated operator case,
by the SAME classify->router->settle path a real operator reply travels, and it
fabricates NOTHING else. So this rig's flagship proofs are the HONEST-PATH ones
(E1/E2): a decision the proxy injects is routed by the REAL `core.classify` +
`core.router` + `core.casestate.settle` and actually settles the case — no
faked trunk, no direct case-dict mutation.

Token-free throughout via the `decide_fn` seam: every proof injects a stub
decision, so the rig asserts the WIRING (predicate -> inject -> settle; gating;
idempotency; architect-refusal; malformed-drop), never a model's judgment.

Proofs:
  P1  _needs_operator: operator-owned + OPEN                 -> True
  P2  _needs_operator: architect-owned + open               -> False (never bypass architect-first)
  P3  _needs_operator: operator-owned + already-settled      -> False
  P4  _parse_decision: clean / fenced / prose / bad-verb / empty (tolerance lock)
  P5  _inject_decision runs the REAL scripts/operator-reply.sh subprocess and
      lands a well-formed tagged operator.decision line on ctx.operator_inbox
  T1  tick on an operator-owned open case (stub resume)     -> injects 1, marks decided
  T2  tick again, case already decided this run             -> no-op (idempotent)
  T3  tick on an ARCHITECT-owned case                       -> no inject, decide_fn NEVER called
  T4  tick, decide_fn returns None (malformed)              -> no inject, attempt counted, no crash
  T5  tick, decide_fn keeps failing                          -> capped at _MAX_ATTEMPTS calls
  T6  tick over a mixed manifest (op-open / arch-open / settled) -> only the op-open injects
  E1  HONEST PATH: injected {resume} -> real classify+router+settle -> case SETTLED (no dangling)
  E2  HONEST PATH: injected {abandon} -> case settled AND block in abandoned_blocks
  E3  HONEST negative: a bad-verb decision never settles -> case stays OPEN (honest REJECT surface)
  E4  DEFENSE LAYER 2: a bad-verb report routed through the REAL router is refused by
      `casestate.settle` ITSELF (independent of the proxy's own layer-1 filter) -> case stays OPEN

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on fail.
"""
import json
import os
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.dirname(_HERE)
_APP_ROOT = os.path.dirname(_CORE_DIR)
sys.path.insert(0, os.path.join(_APP_ROOT, "engine"))
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import casestate                       # noqa: E402 — core/casestate.py, the real settle
import classify                        # noqa: E402 — core/classify.py, the real structured bypass
import router                          # noqa: E402 — core/router.py, the real operator.decision route
import operator_proxy as op            # noqa: E402 — core/sim/operator_proxy.py, unit under test

_results = []

_REAL_OPERATOR_REPLY_SH = os.path.join(_APP_ROOT, "scripts", "operator-reply.sh")


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


class _DuckCtx:
    """A REAL (throwaway, temp-dir) instance root — `scripts/operator-
    reply.sh` is a genuine file-system door script (block 01-38 T3/T4): it
    self-locates `../operator-inbox.jsonl` off its OWN install path, so
    driving it for real needs a real `scripts/` dir on disk, not a bare
    inbox path. `.p()` mirrors `engine/ctx.py::Ctx.p` (the exact surface
    `_inject_decision` calls)."""
    def __init__(self, inst_dir):
        self.dir = inst_dir

    def p(self, *parts):
        return os.path.join(self.dir, *parts)

    @property
    def operator_inbox(self):
        return self.p("operator-inbox.jsonl")


def _fresh_instance():
    """A throwaway instance dir carrying a REAL copy of `scripts/operator-
    reply.sh` (byte-identical, never reimplemented) — genuinely drives the
    real door as a subprocess, never a Python file write standing in for
    it."""
    d = tempfile.mkdtemp(prefix="opproxy_inst_")
    scripts_dir = os.path.join(d, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    dst = os.path.join(scripts_dir, "operator-reply.sh")
    shutil.copyfile(_REAL_OPERATOR_REPLY_SH, dst)
    os.chmod(dst, os.stat(_REAL_OPERATOR_REPLY_SH).st_mode)
    return _DuckCtx(d)


class _DuckEng:
    """The minimum `eng` surface `_inject_decision` + `settle` (resume/abandon)
    touch: a real ctx (`.p`, `.operator_inbox`), `.dry`, and a `.log` sink."""
    def __init__(self, ctx):
        self.dry = True
        self.ctx = ctx
        self.logs = []

    def log(self, channel, msg):
        self.logs.append((channel, msg))


def _op_case(cid, block="01-02", owner="operator", decision=None):
    """A case dict in `open_operator_case`'s shape — only the keys the proxy /
    settle actually read need be present."""
    return {
        "case_id": cid, "block": block, "kind": "wall", "source": "worker.wall",
        "worker_id": f"engineer-{block}", "detail": f"planted wall on {block}",
        "decision": decision, "owner": owner,
    }


def _last_line(ctx):
    path = ctx.operator_inbox
    if not os.path.exists(path):
        return None
    with open(path) as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else None


def _count_lines(ctx):
    path = ctx.operator_inbox
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return len([ln for ln in f.read().splitlines() if ln.strip()])


def main():
    # ── P1-P3: the predicate is exactly casestate.reping's (never architect) ──
    ok("P1: _needs_operator TRUE for an operator-owned OPEN case",
       op._needs_operator(_op_case("c1")) is True)
    ok("P2: _needs_operator FALSE for an ARCHITECT-owned case (never bypass architect-first)",
       op._needs_operator(_op_case("c2", owner="architect")) is False)
    ok("P3: _needs_operator FALSE for an already-SETTLED operator case",
       op._needs_operator(_op_case("c3", decision="resume")) is False)

    # ── P4: parse tolerance ──
    ok("P4a: clean JSON parses",
       op._parse_decision('{"verb": "resume", "note": "ok"}') == {"verb": "resume", "note": "ok"})
    ok("P4b: a ```json-fenced object inside prose parses",
       (op._parse_decision('Sure.\n```json\n{"verb": "amend", "note": "fix"}\n```') or {}).get("verb") == "amend")
    ok("P4c: prose with no JSON object -> None (never a guessed verb)",
       op._parse_decision("I think we should resume actually") is None)
    ok("P4d: a JSON object with a non-VERB verb -> None",
       op._parse_decision('{"verb": "nuke"}') is None)
    ok("P4e: empty text -> None",
       op._parse_decision("") is None)

    # ── P5: injection shape, via the REAL scripts/operator-reply.sh subprocess ──
    ctx = _fresh_instance()
    eng = _DuckEng(ctx)
    injected_ok = op._inject_decision(eng, "CASE-9", {"verb": "resume", "note": "unblock it"})
    line = _last_line(ctx)
    ok("P5a: _inject_decision's real operator-reply.sh subprocess reports success",
       injected_ok is True, f"injected_ok={injected_ok}")
    ok("P5b: the real door wrote a tagged operator.decision with operator sender + slots "
       "to ctx.operator_inbox (never worker_inbox)",
       line and line.get("tag") == "operator.decision"
       and line.get("sender", {}).get("kind") == "operator"
       and line["slots"] == {"case_id": "CASE-9", "verb": "resume", "note": "unblock it"},
       f"line={line}")

    # ── T1/T2: inject once, then idempotent ──
    ctx = _fresh_instance()
    eng = _DuckEng(ctx)
    manifest = {"cases": {"CASE-1": _op_case("CASE-1")}}
    decided, attempts = set(), {}
    calls = {"n": 0}

    def stub_resume(case):
        calls["n"] += 1
        return {"verb": "resume", "note": "proxy: unblock"}

    n1 = op.tick(eng, manifest, decided, attempts, decide_fn=stub_resume)
    ok("T1: tick injects exactly one decision for one operator-owned open case, marks it decided",
       n1 == 1 and "CASE-1" in decided and _count_lines(ctx) == 1, f"n1={n1} decided={decided}")
    n2 = op.tick(eng, manifest, decided, attempts, decide_fn=stub_resume)
    ok("T2: tick is idempotent — a case already decided this run is a no-op (no second line)",
       n2 == 0 and _count_lines(ctx) == 1 and calls["n"] == 1, f"n2={n2} calls={calls['n']}")

    # ── T3: an ARCHITECT-owned case is never touched, decide_fn never called ──
    ctx = _fresh_instance()
    eng = _DuckEng(ctx)
    manifest = {"cases": {"CASE-A": _op_case("CASE-A", owner="architect")}}
    ac = {"n": 0}

    def stub_counted(case):
        ac["n"] += 1
        return {"verb": "resume"}

    n3 = op.tick(eng, manifest, set(), {}, decide_fn=stub_counted)
    ok("T3: tick never acts on an ARCHITECT-owned case (no inject, decide_fn NEVER called)",
       n3 == 0 and _count_lines(ctx) == 0 and ac["n"] == 0, f"n3={n3} decide_calls={ac['n']}")

    # ── T4: a malformed decision (None) never injects, counts an attempt, no crash ──
    ctx = _fresh_instance()
    eng = _DuckEng(ctx)
    manifest = {"cases": {"CASE-M": _op_case("CASE-M")}}
    decided, attempts = set(), {}
    n4 = op.tick(eng, manifest, decided, attempts, decide_fn=lambda c: None)
    ok("T4: a malformed (None) decision -> no inject, case NOT marked decided, attempt counted",
       n4 == 0 and _count_lines(ctx) == 0 and "CASE-M" not in decided
       and attempts.get("CASE-M") == 1, f"n4={n4} attempts={attempts}")

    # ── T5: repeated failure is capped at _MAX_ATTEMPTS decide_fn calls ──
    ctx = _fresh_instance()
    eng = _DuckEng(ctx)
    manifest = {"cases": {"CASE-C": _op_case("CASE-C")}}
    decided, attempts = set(), {}
    fc = {"n": 0}

    def stub_fail(case):
        fc["n"] += 1
        return None

    for _ in range(op._MAX_ATTEMPTS + 3):
        op.tick(eng, manifest, decided, attempts, decide_fn=stub_fail)
    ok("T5: a persistently-failing decide_fn is capped at _MAX_ATTEMPTS calls (no infinite retry, no inject)",
       fc["n"] == op._MAX_ATTEMPTS and _count_lines(ctx) == 0,
       f"decide_calls={fc['n']} cap={op._MAX_ATTEMPTS}")

    # ── T6: mixed manifest — only the operator-owned OPEN case is injected ──
    ctx = _fresh_instance()
    eng = _DuckEng(ctx)
    manifest = {"cases": {
        "OP-OPEN": _op_case("OP-OPEN", block="01-02"),
        "ARCH": _op_case("ARCH", block="01-03", owner="architect"),
        "SETTLED": _op_case("SETTLED", block="01-04", decision="resume"),
    }}
    n6 = op.tick(eng, manifest, set(), {}, decide_fn=stub_resume)
    injected = _last_line(ctx)
    ok("T6: over a mixed manifest, ONLY the operator-owned open case is injected",
       n6 == 1 and _count_lines(ctx) == 1 and injected["slots"]["case_id"] == "OP-OPEN",
       f"n6={n6} injected={injected and injected['slots']['case_id']}")

    # ══ E1: THE HONEST PATH — injected {resume} routed by REAL classify+router+settle ══
    ctx = _fresh_instance()
    eng = _DuckEng(ctx)
    manifest = {"cases": {"CASE-E1": _op_case("CASE-E1")}}
    op.tick(eng, manifest, set(), {}, decide_fn=lambda c: {"verb": "resume", "note": "unblock"})
    msg = _last_line(ctx)
    tag, slots = classify.classify(eng, msg, manifest)
    ok("E1a: the injected line classifies as operator.decision via the real structured bypass",
       tag == "operator.decision" and slots.get("case_id") == "CASE-E1" and slots.get("verb") == "resume",
       f"tag={tag} slots={slots}")
    # R8 (block 01-38, defense-in-depth): `_route_decision` resolves the
    # requester's channel-derived ORIGIN off the full report (`vocab.
    # resolve_origin`) and hands it to `casestate.settle` as a second,
    # independent check — pass through `msg`'s own `sender` (operator-
    # reply.sh's real payload) rather than a stripped `{tag, slots}`-only
    # dict, which `core/snapshot.py::_classify_reports` never produces in
    # real production (it only ever PROMOTES fields, never drops them).
    router._route_decision(eng, manifest, {**msg, "tag": tag, "slots": slots})
    ok("E1b: the REAL settle path removed the case (no dangling open case — the gate's conjunct)",
       "CASE-E1" not in manifest.get("cases", {}), f"cases={list(manifest.get('cases', {}))}")

    # ══ E2: injected {abandon} — settled AND block abandoned, via the real path ══
    ctx = _fresh_instance()
    eng = _DuckEng(ctx)
    manifest = {"cases": {"CASE-E2": _op_case("CASE-E2", block="01-07")}}
    op.tick(eng, manifest, set(), {}, decide_fn=lambda c: {"verb": "abandon", "note": "out of scope"})
    msg = _last_line(ctx)
    tag, slots = classify.classify(eng, msg, manifest)
    router._route_decision(eng, manifest, {**msg, "tag": tag, "slots": slots})
    ok("E2: injected abandon settles via the real path — case cleared AND block in abandoned_blocks",
       "CASE-E2" not in manifest.get("cases", {})
       and "01-07" in (manifest.get("abandoned_blocks") or []),
       f"cases={list(manifest.get('cases', {}))} abandoned={manifest.get('abandoned_blocks')}")

    # ══ E3: HONEST negative — a bad-verb decision never settles; the case stays OPEN ══
    ctx = _fresh_instance()
    eng = _DuckEng(ctx)
    manifest = {"cases": {"CASE-E3": _op_case("CASE-E3")}}
    n = op.tick(eng, manifest, set(), {}, decide_fn=lambda c: {"verb": "nuke"})
    ok("E3: a bad-verb decision injects nothing and leaves the case OPEN (a malformed op reply never greens)",
       n == 0 and manifest["cases"]["CASE-E3"].get("decision") is None,
       f"n={n} decision={manifest['cases']['CASE-E3'].get('decision')}")

    # ══ E4: DEFENSE LAYER 2 — settle's OWN verb-guard. Bypass the proxy's layer-1
    # filter and hand the REAL router a bad-verb operator.decision directly: the
    # case must stay OPEN because `casestate.settle` itself refuses a non-VERB verb
    # (proves the two layers are independent — a mutation deleting settle's own
    # check would be caught here, not masked by the proxy's filter always firing first).
    eng = _DuckEng(_fresh_instance())
    manifest = {"cases": {"CASE-E4": _op_case("CASE-E4")}}
    router._route_decision(eng, manifest, {"tag": "operator.decision",
                                           "slots": {"case_id": "CASE-E4", "verb": "nuke"}})
    ok("E4: settle's OWN verb-guard refuses a bad verb via the real router (defense layer 2) — case stays OPEN",
       "CASE-E4" in manifest.get("cases", {})
       and manifest["cases"]["CASE-E4"].get("decision") is None,
       f"case={manifest.get('cases', {}).get('CASE-E4')}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.sim.operator_proxy_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
