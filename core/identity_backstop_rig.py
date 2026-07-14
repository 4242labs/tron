"""core.identity_backstop_rig — block 01-38 T2/T3's two AC-0 proofs: the
PRIMARY typed-record guarantee, and its structural backstop.

  test:<report_no_identity_slot> (PRIMARY — the root invariant's own words:
  "the typed record has no identity field — a read does not type-check /
  raises by construction, this is the primary guarantee, not a test"):
  proven twice — a unit-level `core.report.Report` construction/read/write,
  AND a REAL drained report off the real `report.sh` -> `core.snapshot.
  build` path (never a rig-internal injection), for every one of the five
  forbidden keys (`sender`, `worker`, `actor`, `agent_id`, `worker_id`).

  test:<identity_only_via_typed_origin> — the STRUCTURAL BACKSTOP: an AST
  scan over the live `core/*.py` production surface (never `core/*_rig.py`/
  `core/sim/*`, and never `engine/fsm.py` — frozen, out of scope) asserts
  NO module reads a message-borne identity key as a literal dict key/
  subscript — EXCEPT the durable-id modules block 01-38 T3's own "Not in
  this task" list names (`architect.py`, `casestate.py`, `engine.py`,
  `gate.py`, `pipeline.py`, `sentry.py`, `switchboard.py`, `tick.py` — these
  read a CASE/JOB/MANIFEST record's own durable `worker_id`/`agent_id`
  field, the record's *owner*, never a message's claimed identity) and
  `core/r3_lint.py`/`core/r3_guard.py` (the honesty backstop's own taint
  analysis legitimately contains these tokens as AST-matched strings, not as
  a read off a report) and `core/report.py` itself (defines the forbidden
  set). This is the TRIPWIRE for accidental reintroduction (a new
  dict-shaped path smuggling identity back in) — the type itself (`core.
  report.Report`, proven above) is the actual guarantee.

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on
fail.
"""
import ast
import glob
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_APP_ROOT, "engine"))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "sim"))

from ctx import Ctx                 # noqa: E402 — engine/ctx.py
from engine import Engine           # noqa: E402 — core/engine.py
import snapshot                     # noqa: E402 — core/snapshot.py, the observe pass under test
import vocab                        # noqa: E402 — core/vocab.py
import intake                       # noqa: E402 — core/intake.py, block 01-38 T1's per-agent intake
import architect                    # noqa: E402 — core/architect.py, ARCHITECT_WID
import report as report_mod         # noqa: E402 — core/report.py, block 01-38 T2's typed record under test
from boot_real_scaffold_rig import copy_real_scaffold, seed_live_instance   # noqa: E402
from seed_canon import install_canon   # noqa: E402
import subprocess

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ═══════════════════════════════════════════════════════════════════════
# test:<report_no_identity_slot> — PRIMARY guarantee, part 1: unit-level
# ═══════════════════════════════════════════════════════════════════════
def run_unit_level():
    for key in sorted(report_mod.FORBIDDEN_IDENTITY_KEYS):
        rep = report_mod.Report({"tag": "worker.done", "block": "01-01"})

        def _read():
            return rep.get(key)

        def _getitem():
            return rep[key]

        def _contains():
            return key in rep

        def _write():
            rep[key] = "forged"

        def _setdefault():
            rep.setdefault(key, "forged")

        for label, fn in (("get", _read), ("getitem", _getitem),
                          ("contains", _contains), ("setitem", _write),
                          ("setdefault", _setdefault)):
            raised = False
            try:
                fn()
            except report_mod.IdentityNotOnMessage:
                raised = True
            except Exception as e:   # noqa: BLE001 — anything else is the WRONG failure mode
                ok(f"UNIT[{key}].{label}: raises IdentityNotOnMessage specifically "
                   f"(not some other error)", False, f"raised {type(e).__name__}: {e}")
                continue
            ok(f"UNIT[{key}].{label} (PRIMARY GUARANTEE — must be GREEN): a "
               f"{label} of the forbidden identity key {key!r} on a Report "
               f"raises IdentityNotOnMessage BY CONSTRUCTION — never returns "
               f"None, never silently stores a forged value",
               raised, f"raised={raised}")

    # A Report constructed from a raw dict that ALREADY carries a forbidden
    # key must refuse to smuggle it through — snapshot.py strips these keys
    # before construction (its own job), but the TYPE itself is also the
    # backstop: passing one straight to the constructor raises too, never
    # silently drops or silently accepts it.
    for key in sorted(report_mod.FORBIDDEN_IDENTITY_KEYS):
        raised = False
        try:
            report_mod.Report({"tag": "worker.done", key: "forged"})
        except report_mod.IdentityNotOnMessage:
            raised = True
        ok(f"UNIT[{key}].construct (a raw dict carrying the forbidden key "
           f"cannot be smuggled through the Report constructor either)",
           raised, f"raised={raised}")

    # Every OTHER key still behaves exactly like a plain dict — this is a
    # scoped refusal of five specific keys, not a redesign of the whole
    # report shape (T2's own hard rule: no per-caller guards, no widened
    # scope).
    rep = report_mod.Report({"tag": "worker.done", "block": "01-01"})
    rep["slots"] = {"branch": "feat/x"}
    ok("UNIT-NONFORBIDDEN: every non-identity key (tag/block/slots/origin/"
       "...) reads and writes exactly like a plain dict — the refusal is "
       "scoped to the five identity keys only",
       rep.get("tag") == "worker.done" and rep["block"] == "01-01"
       and "block" in rep and rep.get("slots") == {"branch": "feat/x"}
       and dict(rep) == {"tag": "worker.done", "block": "01-01", "slots": {"branch": "feat/x"}},
       f"rep={dict(rep)}")


# ═══════════════════════════════════════════════════════════════════════
# test:<report_no_identity_slot> — PRIMARY guarantee, part 2: through the
# REAL report.sh -> core.snapshot.build door (never a rig-internal inject)
# ═══════════════════════════════════════════════════════════════════════
def run_real_door_level():
    root = copy_real_scaffold()
    inst, _project, _knobs = seed_live_instance(root)
    install_canon(inst)
    ctx = Ctx(inst)
    eng = Engine(ctx)
    eng.dry = False

    agent_id = "engineer-01-02"
    agent_intake = intake.intake_path(ctx, agent_id)
    script = os.path.join(inst, "scripts", "report.sh")
    r = subprocess.run(
        ["bash", script, "--intake", agent_intake, agent_id,
         "--tag", "flag", "--block", "01-02", "a real structured report"],
        capture_output=True, text=True)
    ok("REAL-DOOR R0: the real report.sh call succeeded", r.returncode == 0,
       f"rc={r.returncode} stderr={r.stderr!r}")

    snap = snapshot.build(eng)
    flags = [rep for rep in snap.worker_reports if rep.get("tag") == "worker.flag"]
    ok("REAL-DOOR R1: a real drained/admitted report resolved (worker.flag present)",
       bool(flags), f"tags={[rep.get('tag') for rep in snap.worker_reports]}")

    if flags:
        rep = flags[-1]
        ok("REAL-DOOR R2: the real report's identity IS available — via the "
           "typed Origin, not a forbidden key",
           rep.get("origin") == intake.Origin(vocab.WORKER, agent_id),
           f"origin={rep.get('origin')}")
        for key in sorted(report_mod.FORBIDDEN_IDENTITY_KEYS):
            raised = False
            try:
                rep.get(key)
            except report_mod.IdentityNotOnMessage:
                raised = True
            ok(f"REAL-DOOR[{key}] (PRIMARY GUARANTEE, THROUGH THE REAL DOOR — "
               f"must be GREEN): reading {key!r} off a REAL report.sh-produced, "
               f"snapshot.build-resolved report raises IdentityNotOnMessage — "
               f"a type error by construction, not a value that happens to be "
               f"empty",
               raised, f"raised={raised}")
    snapshot.release(snap)


# ═══════════════════════════════════════════════════════════════════════
# test:<identity_only_via_typed_origin> — the structural backstop
# ═══════════════════════════════════════════════════════════════════════
# Block 01-38 T3's own "Not in this task" list: these read a CASE/JOB/
# MANIFEST record's own DURABLE worker_id/agent_id field (the record's
# *owner* — a reference to some OTHER worker, not the sender of the message
# in hand) — never a forgeable sender read off an inbound report. Not
# rewired (T3's own hard rule); therefore not asserted clean here either.
_DURABLE_ID_EXEMPT = {
    "architect.py", "casestate.py", "engine.py", "gate.py", "pipeline.py",
    "sentry.py", "switchboard.py", "tick.py",
}
# `r3_lint.py`/`r3_guard.py` — the R3 honesty backstop's own static taint
# analysis legitimately matches these tokens as AST-compared string
# literals (its OWN detection substrate), never as a subscript/`.get` read
# off a report. `report.py` defines `FORBIDDEN_IDENTITY_KEYS` itself.
_STRUCTURAL_EXEMPT = {"r3_lint.py", "r3_guard.py", "report.py"}

FORBIDDEN = report_mod.FORBIDDEN_IDENTITY_KEYS


def _const_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _forbidden_key_hits(path):
    """Every place `path` reads/writes a message-borne identity key as a
    LITERAL dict key — `x["sender"]`, `x.get("agent_id")`, `x.setdefault(
    "worker_id", ...)`, `x.pop("actor")`, `"worker" in x` — via AST (never a
    text grep: a docstring/comment mentioning the word "sender" is not a
    read, and a VARIABLE named `worker_id` used as a lookup KEY — e.g.
    `manifest["workers"][worker_id]`, the durable-id shape — is not a
    literal-string subscript on the forbidden set either)."""
    with open(path) as fh:
        src = fh.read()
    tree = ast.parse(src, filename=path)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            key = _const_str(node.slice)
            if key in FORBIDDEN:
                hits.append((node.lineno, f'[{key!r}]'))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("get", "setdefault", "pop") and node.args:
                key = _const_str(node.args[0])
                if key in FORBIDDEN:
                    hits.append((node.lineno, f'.{node.func.attr}({key!r})'))
        elif isinstance(node, ast.Compare):
            for op, comparator in zip(node.ops, node.comparators):
                if isinstance(op, (ast.In, ast.NotIn)):
                    key = _const_str(node.left)
                    if key in FORBIDDEN:
                        hits.append((node.lineno, f'{key!r} in ...'))
    return hits


def run_structural_backstop():
    core_files = sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(_HERE, "*.py"))
        if not os.path.basename(p).endswith("_rig.py") and os.path.basename(p) != "__init__.py")
    must_be_clean = [f for f in core_files
                     if f not in _DURABLE_ID_EXEMPT and f not in _STRUCTURAL_EXEMPT]
    ok("BACKSTOP-SCOPE: the must-be-clean file set is non-empty and includes "
       "the fixed T3 reader set",
       {"classify.py", "liveness.py", "router.py", "snapshot.py", "reviewers.py",
        "door.py", "vocab.py", "intake.py"} <= set(must_be_clean),
       f"must_be_clean={must_be_clean}")

    for fname in must_be_clean:
        path = os.path.join(_HERE, fname)
        hits = _forbidden_key_hits(path)
        ok(f"test:<identity_only_via_typed_origin>[{fname}] — no message-borne "
           f"identity key read/written as a literal dict key",
           not hits, f"hits={hits}")

    # Non-vacuity: confirm the checker actually FIRES on a known offender —
    # the excluded durable-id set legitimately trips it (proves this isn't
    # a checker that vacuously finds nothing anywhere).
    durable_hits = {f: _forbidden_key_hits(os.path.join(_HERE, f))
                    for f in sorted(_DURABLE_ID_EXEMPT)}
    ok("BACKSTOP-NONVACUITY: the AST checker DOES fire on the (legitimately "
       "exempt) durable-id modules — proves it is a real, discriminating "
       "check, not a vacuous pass",
       any(hits for hits in durable_hits.values()),
       f"durable_hits={{f: len(h) for f, h in durable_hits.items()}}")

    # Mutation-style: a hostile edit reintroducing `rep.get("agent_id")`
    # into a scratch copy of a must-be-clean file IS caught.
    victim = os.path.join(_HERE, "router.py")
    with open(victim) as fh:
        clean_src = fh.read()
    hostile_src = clean_src + '\n\ndef _hostile_probe(rep):\n    return rep.get("agent_id")\n'
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix="_router_hostile.py", delete=False) as fh:
        fh.write(hostile_src)
        hostile_path = fh.name
    try:
        hostile_hits = _forbidden_key_hits(hostile_path)
    finally:
        os.remove(hostile_path)
    ok("BACKSTOP-MUTATION: a hostile re-introduction of `rep.get(\"agent_id\")` "
       "into a scratch copy of an otherwise-clean must-be-clean module IS "
       "caught by the checker (mutation-proven, not just vacuously green "
       "on the current tree)",
       bool(hostile_hits), f"hostile_hits={hostile_hits}")


def main():
    run_unit_level()
    run_real_door_level()
    run_structural_backstop()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.identity_backstop_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        if not c:
            print(f"  [FAIL] {name} — {detail}")
    print(f"  ({passed}/{len(_results)} passed; failures printed above, if any)")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
