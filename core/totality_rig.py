"""core.totality_rig — block 01-38 T14 (AC-9): `test:<totality>`.

GENERATED from `core/vocab.py` itself — never a hand-picked subset, never a
per-word list that could silently drift as the vocabulary grows. For every
word `vocab.TAGS` declares, both directions, asserts the full journey
exists (sender command -> route -> effect -> template, outbound):

  INBOUND — every word has an explicit, live DISPATCH DECISION reachable
  from a real report through the real engine, never falling to the T4
  catch-all (`core/router.py::_route_catch_all`) merely by omission:
    - the 11 report.sh-sendable / router-dispatched words (`worker.online`,
      `worker.wall`, `worker.wall_retract`, `operator.decision`,
      `architect.reconciled`, `worker.review_done`,
      `architect.triage_verdict`, `worker.flag`, `worker.done`,
      `worker.branch`, `worker.recorded`) plus `unclassified` (12 total) —
      an AST scan of `core/router.py::route`'s own dispatch chain (every
      `tag == "..."` / `tag in (...)` literal it actually compares against,
      read live off the source, never copied by hand) must contain the
      word's tag. This is the SAME chain a real report walks; a word this
      scan cannot find would silently fall through to the catch-all in
      production exactly the way D1's typo'd tag historically did.
    - the 2 ENGINE-minted-only words (`worker.stalled`,
      `worker.report_refused` — never inbound-routed AT ALL by design,
      minted directly by their own producer) — an AST scan of every
      `casestate.open_case(...)` call site across live `core/*.py`
      (production only, never `*_rig.py`) extracts the literal `source`
      argument (positional index 3 or the `source=` keyword) each call
      site actually mints; the word's tag must appear in that set — this
      IS its journey (the case IS the route+effect for an engine-produced
      word; there is no report to dispatch).

  OUTBOUND — every `vocab.TPL_*` constant (`vocab.EMIT_TEMPLATE_IDS`) is
  reachable from a real call site: an AST scan of every `core/*.py`
  production module (never `vocab.py` itself, never `*_rig.py`) for an
  `Attribute(value=Name("vocab"), attr="TPL_*")` reference; a template
  declared but never referenced anywhere is a genuine orphan (the D6/AC-6
  class this scan exists to catch, generatively, not by memorizing which
  templates "should" be live).

DISCLOSED FINDINGS (not hidden, not silently patched around — the whole
point of a GENERATED totality test is to surface exactly this kind of
gap; each is a NAMED, PINNED, CLOSED set — never a general "any orphan
auto-passes" escape hatch, so a genuinely NEW missing journey still FAILS
this proof, the entire point of generating it from the vocabulary):

  INBOUND — `vocab.TAGS["worker.dead"]` is declared `("engine-produced
  only")` but `core/liveness.py::sweep` — its own module docstring's named
  producer — mints ONLY `"worker.stalled"`; no `core/*.py` production
  module anywhere mints `"worker.dead"`. Pre-existing, grepped directly,
  confirmed absent, not assumed.

  OUTBOUND — of 32 declared `vocab.TPL_*` templates, this rig found only
  10 with a live `vocab.TPL_*`-referencing call site before this task; SIX
  more (`gate.local`/`gate.record`/`close.worker`/`assign.worker`/
  `gate.review`/`spawn.worker`) WERE real, reached, call sites but via a
  bare literal string instead of the constant — a genuine R2 violation
  ("every emitted identifier is an imported constant") that `engine/
  lint.py`'s own L27 lint is SUPPOSED to catch but structurally cannot
  (its regex is single-line-only; every one of those six call sites is
  multi-line `eng.emit(\n    "literal.id", ...)`) — FIXED in this same
  commit (mechanical, byte-identical runtime string values, core/-only:
  `core/gate.py` x3, `core/router.py`, `core/reviewers.py`, `core/
  switchboard.py` now reference the constant). The REMAINING 22 templates
  (session start/end/scope, every terminal.* state, most escalate.*, both
  tg.*, gate.merge, gate.trunk, heartbeat.ping, close.dirty,
  arch.remediation) have ZERO call site of any kind anywhere in `core/
  *.py` — confirmed directly: `core/engine.py`'s own session-lifecycle
  bookkeeping is a typed EVENT (`emit.put(..., "engine_session_started"
  ...)`), never a rendered message; `core/engine.py::_page_operator`
  sends the caller's raw `detail` text, never a template render;
  `core/liveness.py`'s heartbeat ping hand-builds its text inline. Best
  read (per `vocab.py`'s own docstring, "mirrors messages.yaml's own
  template keys exactly"): these 22 are the shared canon file's LEGACY
  `engine/fsm.py`-side ids, not yet (or not ever going to be) ported to
  this new `core/*.py` engine's own event-stream-first design — but
  WIRING them (new operator/session-lifecycle messaging design, high
  blast radius) or DELETING them (touches the shared canon + L28's
  messages.yaml sync lint + the legacy engine) is a product decision
  outside a totality-TEST-authoring task's own scope. This rig does NOT
  invent an answer for either finding above. It asserts the true,
  CONFIRMED fact (no live journey exists) as a NAMED, VISIBLE, non-hidden
  open item per word/template — exactly the ledger's own STILL-OPEN/
  NEEDS-A-VECTOR convention — rather than (a) a false "journey exists"
  claim or (b) silently excluding it from the generated sweep. A pin that
  goes STALE (the word/template later GAINS a real journey without the
  pin being removed) flips this same assertion to FAIL — the pin can
  never quietly keep excusing a fixed gap, mirroring `core/r3_lint.py`'s
  own KNOWN_RED staleness discipline. Flagged to the operator/CLU in this
  task's own work log for a ruling; carried forward, never dropped.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.
"""
import ast
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # core
APP_ROOT = os.path.dirname(HERE)                             # worktree root
sys.path.insert(0, HERE)

import vocab   # noqa: E402 — core/vocab.py, the ONE closed vocabulary (generated FROM, never copied)

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _production_files():
    """Every live `core/*.py` production module — never `*_rig.py`, never
    `core/sim/*` (the harness surface), never this rig itself. Mirrors
    `core/r3_lint.py`'s own `production_files()` scoping convention (T7's
    completeness lint), re-derived here rather than imported, so this rig
    stays a pure AST-reader with no dependency on r3_lint's internals."""
    files = sorted(glob.glob(os.path.join(HERE, "*.py")))
    return [f for f in files
            if not os.path.basename(f).endswith("_rig.py")
            and os.path.basename(f) != "__init__.py"]


def _parse(path):
    with open(path) as fh:
        src = fh.read()
    return ast.parse(src, filename=path)


# ══════════════════════════════════════════════════════════════════════════
# INBOUND, part 1 — router.route's OWN dispatch chain, read live off the
# source (never a hand-copied list of tags).
# ══════════════════════════════════════════════════════════════════════════
def _router_dispatch_set():
    """Every literal tag `core/router.py::route`'s own if/elif chain
    compares `tag` against — `tag == "x"` arms AND `tag in ("x", "y")`
    membership arms alike — extracted by walking the REAL function's AST,
    not re-typed from reading it."""
    tree = _parse(os.path.join(HERE, "router.py"))
    route_fn = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "route")
    found = set()

    class _Visitor(ast.NodeVisitor):
        def visit_Compare(self, node):
            left_is_tag = isinstance(node.left, ast.Name) and node.left.id == "tag"
            if left_is_tag:
                for op, comp in zip(node.ops, node.comparators):
                    if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant):
                        found.add(comp.value)
                    elif isinstance(op, ast.In):
                        elts = getattr(comp, "elts", None) or []
                        for e in elts:
                            if isinstance(e, ast.Constant):
                                found.add(e.value)
            self.generic_visit(node)

    _Visitor().visit(route_fn)
    return found


# ══════════════════════════════════════════════════════════════════════════
# INBOUND, part 2 — every `casestate.open_case(...)` call site's literal
# `source` argument, across ALL production core/*.py modules.
# ══════════════════════════════════════════════════════════════════════════
def _open_case_sources():
    """Every literal `source` string ANY production module's `casestate.
    open_case(...)` call site actually mints — positional index 3
    (`eng, manifest, block, source, ...`) or the `source=` keyword,
    extracted by AST, across every live `core/*.py` file (never a single
    hand-picked file — a NEW module minting an engine-only word later is
    picked up here for free)."""
    found = set()
    for path in _production_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            is_open_case = (
                (isinstance(fn, ast.Attribute) and fn.attr == "open_case")
                or (isinstance(fn, ast.Name) and fn.id == "open_case"))
            if not is_open_case:
                continue
            src_val = None
            if len(node.args) >= 4 and isinstance(node.args[3], ast.Constant):
                src_val = node.args[3].value
            for kw in node.keywords:
                if kw.arg == "source" and isinstance(kw.value, ast.Constant):
                    src_val = kw.value.value
            if src_val is not None:
                found.add(src_val)
    return found


# ══════════════════════════════════════════════════════════════════════════
# OUTBOUND — every `vocab.TPL_*` reference across production core/*.py.
# ══════════════════════════════════════════════════════════════════════════
def _referenced_template_names():
    """Every `vocab.TPL_*` ATTRIBUTE reference in any production module
    (never `vocab.py` itself, where they are DEFINED, not referenced) —
    AST-walked, not grepped, so a reference inside a string/comment never
    falsely counts as a real call site."""
    found = set()
    for path in _production_files():
        if os.path.basename(path) == "vocab.py":
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute)
                    and node.attr.startswith("TPL_")
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "vocab"):
                found.add(node.attr)
    return found


# ══════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════
# The 2 ENGINE-minted-only words the router NEVER dispatches (by design —
# see `core/door.py`'s own "no verb, never arrives through that door" note).
_ENGINE_ONLY_WORDS = {"worker.stalled", "worker.report_refused"}

# The genuinely orphaned word — declared, never wired, disclosed above.
_KNOWN_ORPHAN_WORDS = {"worker.dead"}

# The 22 templates with ZERO core/*.py call site of any kind (disclosed
# above) — a NAMED, PINNED, CLOSED set. A template NOT in this set that
# turns up orphaned is a genuine, un-excused totality FAILURE; a template
# IN this set that turns up REFERENCED (the pin going stale — someone
# wired it and forgot to shrink this set) also FAILS, by construction
# (see `run_outbound`'s own assertion), never a silent, permanently-open
# excuse.
_KNOWN_ORPHAN_TEMPLATES = {
    "TPL_ARCH_REMEDIATION", "TPL_CLOSE_DIRTY", "TPL_ESCALATE_AWAIT",
    "TPL_ESCALATE_GATE", "TPL_ESCALATE_UNCLASSIFIED", "TPL_ESCALATE_WALL",
    "TPL_GATE_MERGE", "TPL_GATE_TRUNK", "TPL_HEARTBEAT_PING",
    "TPL_SESSION_END", "TPL_SESSION_SCOPE", "TPL_SESSION_START",
    "TPL_TERMINAL_BLOCK_DONE", "TPL_TERMINAL_DISPATCHED",
    "TPL_TERMINAL_HALT_BOOTUP", "TPL_TERMINAL_HALT_TRUNK",
    "TPL_TERMINAL_PLAN_FIRST", "TPL_TERMINAL_REVIEW",
    "TPL_TERMINAL_RUN_CONTROL", "TPL_TERMINAL_SCOPE_UNKNOWN",
    "TPL_TG_ESCALATE", "TPL_TG_STATUS_DIGEST",
}


def run_inbound():
    dispatched = _router_dispatch_set()
    minted = _open_case_sources()

    for tag, word in sorted(vocab.TAGS.items()):
        if tag in _KNOWN_ORPHAN_WORDS:
            continue   # handled separately below — a disclosed finding, not a silent skip
        if tag in _ENGINE_ONLY_WORDS:
            ok(f"INBOUND {tag!r}: ENGINE-minted-only word has a live "
               f"casestate.open_case(source={tag!r}) producer somewhere "
               f"in production core/*.py (its journey IS the mint — no "
               f"report.sh dispatch exists for it by design)",
               tag in minted, f"minted={sorted(minted)}")
        else:
            ok(f"INBOUND {tag!r}: core/router.py::route's OWN dispatch "
               f"chain has an explicit decision for this tag (an elif arm "
               f"or the acknowledged 'handled elsewhere' tuple) — never "
               f"falls through to the T4 catch-all merely by omission",
               tag in dispatched, f"dispatched={sorted(dispatched)}")

    ok("INBOUND NON-VACUITY: the router-dispatch scan found a NON-EMPTY, "
       "MULTI-ENTRY set (a real AST read of a live if/elif chain, never a "
       "vacuously-empty parse)",
       len(dispatched) >= 10, f"n={len(dispatched)} dispatched={sorted(dispatched)}")
    ok("INBOUND NON-VACUITY: the open_case-source scan found a NON-EMPTY "
       "set (a real AST read across production modules, never vacuous)",
       len(minted) >= 2, f"n={len(minted)} minted={sorted(minted)}")

    # DISCLOSED FINDING — asserted TRUE (the gap genuinely exists), never
    # silently hidden and never falsely claimed covered. See module
    # docstring for the full disclosure + the forward-note to the operator.
    for tag in sorted(_KNOWN_ORPHAN_WORDS):
        ok(f"DISCLOSED GAP {tag!r}: declared in vocab.TAGS "
           f"({vocab.TAGS[tag].note!r}) but has NO live producer anywhere "
           f"in production core/*.py — neither router-dispatched nor "
           f"open_case-minted. A real, pre-existing, orphaned word (grepped "
           f"directly). NOT fixed here (wiring new dead-vs-stalled "
           f"semantics, or deleting the word per the D2/D7 precedent, is a "
           f"product decision beyond a totality-test task) — flagged to "
           f"the operator/CLU, carried forward, never dropped.",
           tag not in dispatched and tag not in minted,
           f"dispatched={tag in dispatched} minted={tag in minted}")


def run_outbound():
    referenced = _referenced_template_names()
    declared = sorted(k for k, v in vars(vocab).items() if k.startswith("TPL_"))

    ok("OUTBOUND NON-VACUITY: vocab.py declares a non-trivial set of TPL_* "
       "constants (a real registry, not an empty stub)",
       len(declared) >= 20, f"n={len(declared)}")
    ok("OUTBOUND NON-VACUITY: the reference scan found a NON-EMPTY set (a "
       "real AST read across production modules, never vacuous)",
       len(referenced) >= 10, f"n={len(referenced)} referenced={sorted(referenced)}")

    for name in declared:
        if name in _KNOWN_ORPHAN_TEMPLATES:
            # DISCLOSED FINDING (see module docstring): asserted TRUE (the
            # gap genuinely, currently exists) — NOT excused as covered.
            # If this template later GAINS a real call site, `name in
            # referenced` flips True and this assertion FAILS, forcing
            # the pin to shrink — never a silently-stale excuse.
            ok(f"DISCLOSED GAP vocab.{name}: ZERO production core/*.py "
               f"call site references this constant — a named, pinned, "
               f"open item (see module docstring), NOT wired here (a "
               f"product decision beyond this task's scope), NOT silently "
               f"claimed covered",
               name not in referenced, f"referenced={sorted(referenced)}")
        else:
            ok(f"OUTBOUND vocab.{name}: at least one production core/*.py "
               f"call site references this constant (never an orphan "
               f"template declared but never sent — the D6/AC-6 class)",
               name in referenced, f"referenced={sorted(referenced)}")


def main():
    run_inbound()
    run_outbound()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.totality_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + ("" if c else f" — {detail}"))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
