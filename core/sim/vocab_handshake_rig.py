"""core.sim.vocab_handshake_rig — block 01-37 T2/T5 mutation proofs:

  AC-3  a spawn under a STALE `vocab.version` fails loud (`vocab.
        HandshakeError`, uncaught out of `core/engine.py::Engine.start`)
        AND bumps the must-be-zero `vocab_version_handshake_failed` event —
        never a silent fallback to an embedded copy. Proven against a REAL
        `core.engine.Engine.start()` boot over the real trivial-tip-
        converter scaffold (`core.sim.boot_real_scaffold_rig`'s own
        `copy_real_scaffold`/`seed_live_instance` helpers, reused verbatim
        — never a synthetic stand-in): a correctly-seeded schema boots past
        the handshake cleanly (GREEN); the SAME schema with its `version`
        field corrupted afterward raises `HandshakeError` at the very first
        line of `start()` (RED, the mutation) — proving the check is real,
        not vacuous.

  AC-6  `core/engine.py::Engine.emit` raises `vocab.UnknownTemplateError`
        for a template id that is not a member of `vocab.EMIT_TEMPLATE_IDS`
        — checked BEFORE the renderer is ever touched, so it fires even
        under a canon-less `eng` (this rig's own real canon notwithstanding)
        — and NEVER falls back to `fallback_text` for it. Mutation proof:
        temporarily remove one legitimate id from `vocab.EMIT_TEMPLATE_IDS`
        (monkeypatch, restored in a `finally`) and prove `emit()` now
        raises for THAT id too — "delete one template entry, assert emit
        raises rather than fabricating a placeholder" (T5's own words).

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import jobs                        # noqa: E402 — engine/jobs.py, spawn_runner stub (never a real claude)
from ctx import Ctx                 # noqa: E402 — engine/ctx.py, the real runtime-context resolver
from engine import Engine            # noqa: E402 — core/engine.py, THE MODULE UNDER TEST
import vocab                          # noqa: E402 — core/vocab.py, THE MODULE UNDER TEST
from boot_real_scaffold_rig import copy_real_scaffold, seed_live_instance   # noqa: E402
from seed_canon import install_canon   # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


class _Events:
    def __init__(self):
        self.log = []

    def event(self, type_, **payload):
        self.log.append({"type": type_, "payload": payload})


def _seeded_instance():
    """A fully real, bootable instance dir — copy_real_scaffold + seed_
    live_instance (project.yaml/knobs.yaml, `core.sim.boot_real_scaffold_
    rig`'s own real-seed helpers) + install_canon (messages/routing/prompts/
    report.sh/vocab.schema.json, `core.sim.seed_canon`'s own real-seed
    helper). Returns `(root, inst_dir)`."""
    root = copy_real_scaffold()
    inst, _project, _knobs = seed_live_instance(root)
    install_canon(inst)
    return root, inst


# ═══════════════════════════════════════════════════════════════════════
# AC-3 — the vocab version handshake
# ═══════════════════════════════════════════════════════════════════════
def run_handshake_scenarios():
    orig_spawn = jobs.spawn_runner
    jobs.spawn_runner = lambda *a, **kw: None   # never a real claude process

    # ── GREEN: a correctly-seeded schema boots straight past the handshake ──
    try:
        root, inst = _seeded_instance()
        ctx = Ctx(inst)
        stamped_ok = None
        import json as _json
        with open(ctx.vocab_schema) as fh:
            stamped_ok = _json.load(fh).get("version")
        ok("H0: the freshly-seeded instance's schema is stamped with THIS "
           "engine's live VERSION (install_canon's own write_schema call)",
           stamped_ok == vocab.VERSION, f"stamped={stamped_ok} live={vocab.VERSION}")

        eng = Engine(ctx)
        eng.dry = False
        handshake_raised = False
        other_error = None
        try:
            eng.start(scope="all", worker_count=1, models={})
        except vocab.HandshakeError:
            handshake_raised = True
        except Exception as e:   # noqa: BLE001 — captured for diagnostics only
            other_error = f"{type(e).__name__}: {e}"
        ok("H1 (GREEN — must be GREEN): Engine.start() over a correctly-"
           "seeded instance does NOT raise HandshakeError (any OTHER "
           "exception is a different, unrelated concern this rig doesn't "
           "chase — the handshake specifically must not be what blocks it)",
           not handshake_raised, f"handshake_raised={handshake_raised} other={other_error}")
    finally:
        pass

    # ── RED (the mutation): the SAME schema, version corrupted afterward —
    #     HandshakeError, uncaught, AND the must-be-zero event recorded ──
    root2, inst2 = _seeded_instance()
    ctx2 = Ctx(inst2)
    import json as _json
    with open(ctx2.vocab_schema) as fh:
        doc = _json.load(fh)
    doc["version"] = "STALE-" + str(doc.get("version"))
    with open(ctx2.vocab_schema, "w") as fh:
        _json.dump(doc, fh)

    events = _Events()
    eng2 = Engine(ctx2, events=events)
    eng2.dry = False
    raised = None
    try:
        eng2.start(scope="all", worker_count=1, models={})
    except vocab.HandshakeError as e:
        raised = e
    ok("H2 (MUTATION -> RED, THE AC-3 KILLER — must be GREEN, i.e. this "
       "assertion is TRUE: HandshakeError WAS raised): a stale vocab_"
       "version on the seeded schema fails Engine.start() LOUD, uncaught, "
       "never a silent fallback to an embedded copy",
       raised is not None, f"raised={raised}")
    must_zero = [e for e in events.log if e["type"] == "must_be_zero"
                and e["payload"].get("counter") == "vocab_version_handshake_failed"]
    ok("H3 (MUST-BE-ZERO COUNTER — must be GREEN): the handshake failure "
       "was durably counted (events.event('must_be_zero', counter="
       "'vocab_version_handshake_failed', ...)) BEFORE the raise propagated",
       len(must_zero) == 1, f"events={events.log}")

    # ── missing schema entirely (a pre-block-01-37 instance / a canon-less
    #     rig) is a SOFT skip — never itself the reason start() fails
    #     (distinct from a genuinely stale/corrupted one, H2 above) ──
    root3, inst3 = _seeded_instance()
    ctx3 = Ctx(inst3)
    os.remove(ctx3.vocab_schema)
    eng3 = Engine(ctx3)
    eng3.dry = False
    handshake_raised3 = False
    try:
        eng3.start(scope="all", worker_count=1, models={})
    except vocab.HandshakeError:
        handshake_raised3 = True
    except Exception:   # noqa: BLE001 — any other real-boot exception is out of scope here
        pass
    ok("H4 (MISSING-SCHEMA SOFT-SKIP — must be GREEN): an instance with NO "
       "vocab.schema.json at all (pre-block-01-37 shape) is never itself "
       "blocked by the handshake — distinct from a genuinely STALE one (H2)",
       not handshake_raised3, f"handshake_raised={handshake_raised3}")

    jobs.spawn_runner = orig_spawn


# ═══════════════════════════════════════════════════════════════════════
# AC-6 — emit() raises loud on an unknown/removed template id
# ═══════════════════════════════════════════════════════════════════════
def run_emit_scenarios():
    root, inst = _seeded_instance()
    ctx = Ctx(inst)
    eng = Engine(ctx)
    eng.dry = True   # never touch a real worker mailbox — pure render-path proof

    # ── a REAL vocab template id renders fine (the real canon this rig
    #     installed — messages.yaml/prompts/ — is on disk) ──
    line = eng.emit(vocab.TPL_HEARTBEAT_PING, "fallback should never surface",
                    slots={}, worker_id="probe-01")
    ok("E1: a real vocab template id renders via the REAL canon (never the "
       "fallback text) — proves the renderer path is genuinely live",
       line != "fallback should never surface" and bool(line), f"line={line!r}")

    # ── an unknown/typo'd template id raises IMMEDIATELY — never silently
    #     substitutes fallback_text (the deleted swallow, R2/T5) ──
    raised_unknown = None
    try:
        eng.emit("totally.not.a.real.template", "should never be returned",
                 slots={}, worker_id="probe-01")
    except vocab.UnknownTemplateError as e:
        raised_unknown = e
    ok("E2 (THE AC-6 KILLER — must be GREEN): an unknown template id raises "
       "vocab.UnknownTemplateError, never silently substitutes fallback_text",
       raised_unknown is not None, f"raised={raised_unknown}")

    # ── MUTATION: delete one REAL, previously-legitimate template entry
    #     from the closed set — emit() for that SAME id must now raise too,
    #     never fabricate a placeholder ──
    victim = vocab.TPL_HEARTBEAT_PING
    mutated = frozenset(vocab.EMIT_TEMPLATE_IDS - {victim})
    orig_ids = vocab.EMIT_TEMPLATE_IDS
    vocab.EMIT_TEMPLATE_IDS = mutated
    try:
        raised_mutated = None
        try:
            eng.emit(victim, "should never be returned either",
                    slots={}, worker_id="probe-01")
        except vocab.UnknownTemplateError as e:
            raised_mutated = e
        ok("E3 (MUTATION -> RED for the DELETED entry, THE T5 KILLER — must "
           "be GREEN, i.e. this assertion is TRUE: emit() DID raise): "
           "deleting one template entry from the closed set makes emit() "
           "raise for it, never fabricate a placeholder — proves E1/E2 are "
           "genuinely discriminating, not vacuous",
           raised_mutated is not None, f"raised={raised_mutated} victim={victim!r}")
    finally:
        vocab.EMIT_TEMPLATE_IDS = orig_ids

    # ── belt-and-suspenders: restored, the SAME id renders again ──
    line2 = eng.emit(victim, "fallback should never surface again",
                     slots={}, worker_id="probe-01")
    ok("E4: restoring the entry makes emit() render normally again (E3's "
       "mutation was scoped, not a lingering side effect)",
       line2 != "fallback should never surface again" and bool(line2), f"line={line2!r}")


def main():
    run_handshake_scenarios()
    run_emit_scenarios()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.sim.vocab_handshake_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
