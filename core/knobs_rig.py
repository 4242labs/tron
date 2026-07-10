"""core.knobs_rig — real-file-IO rig proving `core/knobs.py` (wave 16, the
ONE knobs.yaml seam fixing the wave-15 silent-default nesting bug) does
EXACTLY what its own module docstring promises:

  1. A NESTED, schema-compliant `knobs.yaml` (`contracts/schema/knobs.
     schema.yaml` — fields under a top-level `knobs:` map; `cadence:`/
     `peer_consults:` their own top-level blocks) reads correctly: every
     typed accessor resolves to its DECLARED value.
  2. `silence_ping_min`/`silence_escalate_min` — the exact two knobs
     wave 15 caught silently resolving to `None` on the real scaffold —
     resolve to their DECLARED values on a schema-compliant file (never
     `None`), reproducing the real `trivial-tip-converter` scaffold's own
     6/8 declaration verbatim.
  3. A knobs.yaml missing the REQUIRED top-level `knobs:` map (the exact
     FLAT, unnested shape every rig before this wave wrote, and the exact
     wave-15 regression shape) raises `KnobsError` LOUDLY — never silently
     read as `{}` (the bug reborn one level up).
  4. A knobs.yaml with a `knobs:` map present but missing the REQUIRED
     `worker_count` key raises `KnobsError` LOUDLY.
  5. A knobs.yaml with a `knobs:` map present but missing an OPTIONAL key
     (`grant_ttl`) returns that key's documented schema default (60)
     EXPLICITLY, never `None`, never silently swallowed.
  6. No `knobs.yaml` file at all reads as "nothing configured" (the
     established, unrelated convention every knobs.yaml-less rig before
     this wave already relies on) — optional accessors still resolve
     their documented defaults, `cadence`/`peer_consults` read empty.
  7. `Knobs.declared(name)` — `core/liveness.py`'s own opt-in check —
     correctly distinguishes "declared" from "resolves via default".

Real file IO throughout (`engine.ctx.Ctx` pointed at a real tempdir, a real
`knobs.yaml` written to disk, read back via `core.knobs.load`) — never a
faked/monkeypatched read, matching every other `core/*_rig.py`'s own
discipline. No git/subprocess anywhere in this rig (this module needs
none — `core/knobs.py` itself never touches git).

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail."""
import os
import sys
import tempfile

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))            # core
_APP_ROOT = os.path.dirname(_HERE)                              # tron-app worktree root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _HERE)

from ctx import Ctx          # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import knobs                  # noqa: E402 — core/knobs.py, THE MODULE UNDER TEST

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _inst(tag):
    d = tempfile.mkdtemp(prefix=f"tron-knobs-rig-{tag}-")
    inst = os.path.join(d, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    return Ctx(inst)


def _write(ctx, doc):
    os.makedirs(os.path.dirname(ctx.knobs_file), exist_ok=True)
    with open(ctx.knobs_file, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)


REAL_NESTED_DOC = {
    "knobs": {
        "worker_count": 2,
        "architect_count": 1,
        "git": "on",
        "silence_ping_min": 6,
        "silence_escalate_min": 8,
        "wake_cooldown_sec": 5,
        "wake_ceiling_sec": 30,
        "abandon_flag_window": 60,
        "carve_liveness_timeout": 300,
        "grant_ttl": 45,          # deliberately NON-default, proves a real DECLARED read (not a default)
    },
    "cadence": {"code": 1},
    "peer_consults": [{"worker": "engineer", "may_consult": "architect", "for": "design"}],
}


def main():
    # ══ 1/2. a schema-compliant NESTED knobs.yaml reads correctly — every
    #     accessor resolves the DECLARED value, silence_ping_min/
    #     silence_escalate_min included (the exact wave-15 killer) ══
    ctx1 = _inst("nested")
    _write(ctx1, REAL_NESTED_DOC)
    k1 = knobs.load(ctx1)
    ok("1a: worker_count resolves the declared value (2)",
       k1.worker_count == 2, f"got={k1.worker_count!r}")
    ok("1b: architect_count resolves the declared value (1)",
       k1.architect_count == 1, f"got={k1.architect_count!r}")
    ok("1c: git resolves the declared value ('on')",
       k1.git == "on", f"got={k1.git!r}")
    ok("2a: silence_ping_min resolves the DECLARED value 6 — NOT None "
       "(the exact wave-15 killer: a flat top-level read silently missed "
       "this nested field on a real scaffold)",
       k1.silence_ping_min == 6, f"got={k1.silence_ping_min!r}")
    ok("2b: silence_escalate_min resolves the DECLARED value 8 — NOT None",
       k1.silence_escalate_min == 8, f"got={k1.silence_escalate_min!r}")
    ok("1d: wake_cooldown_sec/wake_ceiling_sec resolve declared (5, 30)",
       (k1.wake_cooldown_sec, k1.wake_ceiling_sec) == (5.0, 30.0),
       f"got={(k1.wake_cooldown_sec, k1.wake_ceiling_sec)!r}")
    ok("1e: abandon_flag_window/carve_liveness_timeout resolve declared (60, 300)",
       (k1.abandon_flag_window, k1.carve_liveness_timeout) == (60, 300.0),
       f"got={(k1.abandon_flag_window, k1.carve_liveness_timeout)!r}")
    ok("1f: grant_ttl resolves the declared, NON-default value 45 (proves a "
       "real declared read, not a coincidental default match)",
       k1.grant_ttl == 45.0, f"got={k1.grant_ttl!r}")
    ok("1g: cadence resolves the top-level (sibling of `knobs:`, never "
       "nested) declared map",
       k1.cadence == {"code": 1}, f"got={k1.cadence!r}")
    ok("1h: peer_consults resolves the top-level declared list",
       k1.peer_consults == REAL_NESTED_DOC["peer_consults"],
       f"got={k1.peer_consults!r}")
    ok("7a: declared('silence_ping_min') is True on this nested file",
       k1.declared("silence_ping_min") is True)

    # ══ 2c. reproduce the REAL trivial-tip-converter scaffold's own declared
    #     6/8 verbatim (the exact scenario boot_real_scaffold_rig exercises
    #     end to end) ══
    ctx2 = _inst("real-shape")
    _write(ctx2, {"knobs": {"worker_count": 2, "git": "on", "silence_ping_min": 6,
                            "silence_escalate_min": 8, "wake_cooldown_sec": 5,
                            "wake_ceiling_sec": 30, "carve_liveness_timeout": 300,
                            "grant_ttl": 60, "abandon_flag_window": 60},
                  "cadence": {"code": 1}, "peer_consults": []})
    k2 = knobs.load(ctx2)
    ok("2d: real-scaffold-shaped knobs.yaml -> silence_ping_min=6, "
       "silence_escalate_min=8 (liveness ACTIVE, not None)",
       (k2.silence_ping_min, k2.silence_escalate_min) == (6, 8),
       f"got={(k2.silence_ping_min, k2.silence_escalate_min)!r}")

    # ══ 3. FLAT (unnested) knobs.yaml — the pre-wave-16 regression shape —
    #     raises LOUDLY, never silently read as `{}` ══
    ctx3 = _inst("flat-regression")
    _write(ctx3, {"worker_count": 2, "silence_ping_min": 6, "silence_escalate_min": 8})
    flat_raised = None
    try:
        knobs.load(ctx3)
    except knobs.KnobsError as e:
        flat_raised = e
    ok("3: a FLAT (unnested) knobs.yaml — missing the top-level `knobs:` "
       "map — raises KnobsError loudly (never silently read as `{}`, "
       "which is the wave-15 bug reborn one level up)",
       flat_raised is not None, f"raised={flat_raised}")

    # ══ 4. `knobs:` present but missing the REQUIRED `worker_count` key —
    #     raises LOUDLY ══
    ctx4 = _inst("missing-required")
    _write(ctx4, {"knobs": {"architect_count": 1, "grant_ttl": 60}, "cadence": {}})
    missing_required_raised = None
    try:
        knobs.load(ctx4)
    except knobs.KnobsError as e:
        missing_required_raised = e
    ok("4: `knobs:` present but missing the REQUIRED `worker_count` key "
       "raises KnobsError loudly — fail-loud, never a silent None/default",
       missing_required_raised is not None, f"raised={missing_required_raised}")

    # ══ 5. `knobs:` present, `worker_count` present, an OPTIONAL key "
    #     (`grant_ttl`) absent -> the documented schema default (60), "
    #     explicit, never None ══
    ctx5 = _inst("optional-absent")
    _write(ctx5, {"knobs": {"worker_count": None}, "cadence": {}})
    k5 = knobs.load(ctx5)
    ok("5a: worker_count may be null per the schema (operator asked at "
       "session start) — the KEY is present, so this is NOT a fail-loud "
       "case; the accessor returns the declared null",
       k5.worker_count is None, f"got={k5.worker_count!r}")
    ok("5b: grant_ttl, absent, returns its documented schema default (60) "
       "EXPLICITLY — never a bare None",
       k5.grant_ttl == 60.0, f"got={k5.grant_ttl!r}")
    ok("5c: architect_count, absent, returns its documented default (1)",
       k5.architect_count == 1, f"got={k5.architect_count!r}")
    ok("5d: git, absent, returns its documented default ('on')",
       k5.git == "on", f"got={k5.git!r}")
    ok("5e: silence_ping_min/silence_escalate_min, absent, return their "
       "documented defaults (6, 8) — the accessor is honest regardless of "
       "whether `core/liveness.py` chooses to consult it (see 7b)",
       (k5.silence_ping_min, k5.silence_escalate_min) == (6, 8),
       f"got={(k5.silence_ping_min, k5.silence_escalate_min)!r}")
    ok("5f: wake_cooldown_sec/wake_ceiling_sec/abandon_flag_window/"
       "carve_liveness_timeout, absent, return their documented defaults "
       "(5, 30, 60, 300)",
       (k5.wake_cooldown_sec, k5.wake_ceiling_sec, k5.abandon_flag_window,
        k5.carve_liveness_timeout) == (5.0, 30.0, 60, 300.0),
       f"got={(k5.wake_cooldown_sec, k5.wake_ceiling_sec, k5.abandon_flag_window, k5.carve_liveness_timeout)!r}")
    ok("5g: cadence/peer_consults, absent, read empty (schema-equivalent "
       "to an explicit empty block — no information lost)",
       (k5.cadence, k5.peer_consults) == ({}, []),
       f"got={(k5.cadence, k5.peer_consults)!r}")
    ok("7b: declared('silence_ping_min') is False on this file (the key "
       "genuinely never appears) — `core/liveness.py`'s own opt-in check, "
       "distinct from the accessor's default-carrying VALUE above",
       k5.declared("silence_ping_min") is False)
    ok("7c: declared('worker_count') is True even though its VALUE is "
       "null — declared means key-present, never truthiness",
       k5.declared("worker_count") is True)

    # ══ 6. NO knobs.yaml file at all — "nothing configured", the "
    #     established convention every knobs.yaml-less rig before this "
    #     wave already relies on ══
    ctx6 = _inst("no-file")
    ok("pre6: no knobs.yaml written for this instance",
       not os.path.exists(ctx6.knobs_file))
    k6 = knobs.load(ctx6)
    ok("6a: grant_ttl still resolves its documented default (60) with no "
       "file at all — identical to a present-but-absent-key read",
       k6.grant_ttl == 60.0, f"got={k6.grant_ttl!r}")
    ok("6b: cadence/peer_consults read empty with no file at all",
       (k6.cadence, k6.peer_consults) == ({}, []),
       f"got={(k6.cadence, k6.peer_consults)!r}")
    ok("6c: declared('silence_ping_min') is False with no file at all",
       k6.declared("silence_ping_min") is False)

    # ══ malformed-shape guards — `knobs:` present but not a mapping ══
    ctx7 = _inst("malformed-knobs-shape")
    _write(ctx7, {"knobs": ["not", "a", "mapping"]})
    malformed_raised = None
    try:
        knobs.load(ctx7)
    except knobs.KnobsError as e:
        malformed_raised = e
    ok("8: a non-mapping `knobs:` value raises KnobsError loudly",
       malformed_raised is not None, f"raised={malformed_raised}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.knobs_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
         f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
