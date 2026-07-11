"""core.sim.acceptance_verdict_rig — unit lock for the LIVE acceptance gate
`live._acceptance_verdict`, covering the ADR-0005 conjuncts (regression) AND the
ADR-0006 R2d/R2e additions. The gate turns a run's `result` dict into (ok,
reasons); a false-GREEN here is the whole false-green disease, so the most
important proof is the symmetric one: a genuinely clean result still ACCEPTs
(no new conjunct reddens a clean trivial run).

Pure unit rig — no scaffold, no processes: `_acceptance_verdict` is a pure
function of the `result` dict.

Proofs:
  V1  fully clean trivial result                       -> ACCEPT (no false-positive)
  V2  orphan processes present                         -> REJECT
  V3  a dangling OPEN case (decision None)             -> REJECT
  V4  a spurious page (count != expect_pages=0)        -> REJECT
  V5  R2d: escalations recorded, trivial (expect 0)    -> REJECT
  V6  R2d: escalations recorded, MODERATE (expect 1,
      one matching page) -> ACCEPT (log allowed for N>0; no false-positive)
  V7  R2e: session_end + a hard-kill -> ACCEPT (WARNING not REJECT — no clean-run
      false-positive; the kill is surfaced by run_live's ⚠, never the verdict)
  V8  R2e demotion scoped: a real defect (open case) + a kill -> still REJECT on
      the defect, never a kill-reason

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on fail.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.dirname(_HERE)
_APP_ROOT = os.path.dirname(_CORE_DIR)
sys.path.insert(0, os.path.join(_APP_ROOT, "engine"))
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import live                            # noqa: E402 — core/sim/live.py, unit under test

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _clean(**over):
    """A fully-clean trivial result; `over` overrides one field to break it."""
    r = {
        "outcome": "session_end",
        "orphans": [],
        "cases": {},
        "operator_pages": {},
        "escalations": [],
        "escalated_kills": [],
    }
    r.update(over)
    return r


def main():
    # V1 — the symmetric no-false-positive proof
    okv, reasons = live._acceptance_verdict(_clean(), expect_pages=0)
    ok("V1: a fully clean trivial result ACCEPTs (no new conjunct reddens a clean run)",
       okv and not reasons, f"reasons={reasons}")

    # V2 — orphans
    okv, reasons = live._acceptance_verdict(_clean(orphans=["claude 424243 ..."]), expect_pages=0)
    ok("V2: an orphan process REJECTs", not okv and any("orphan" in r for r in reasons),
       f"reasons={reasons}")

    # V3 — dangling open case
    okv, reasons = live._acceptance_verdict(
        _clean(cases={"case-1": {"decision": None}}), expect_pages=0)
    ok("V3: a dangling OPEN case REJECTs", not okv and any("OPEN" in r for r in reasons),
       f"reasons={reasons}")

    # V4 — spurious page (count mismatch)
    okv, reasons = live._acceptance_verdict(
        _clean(operator_pages={"p1": {"case_id": "c1"}}), expect_pages=0)
    ok("V4: a spurious operator page (count != 0) REJECTs",
       not okv and any("escalations" in r for r in reasons), f"reasons={reasons}")

    # V5 — R2d escalations on a trivial SIM
    okv, reasons = live._acceptance_verdict(
        _clean(escalations=[{"block": "01-02", "stage": "merge", "kind": "cap"}]),
        expect_pages=0)
    ok("V5 (R2d): a recorded sentry/channel escalation REJECTs a trivial SIM",
       not okv and any("escalation(s) recorded" in r for r in reasons), f"reasons={reasons}")

    # V6 — R2d must NOT fire for a moderate SIM (expect_pages=1, one matching page)
    okv, reasons = live._acceptance_verdict(
        _clean(operator_pages={"p1": {"case_id": "c1", "detail": "PLANTED-XYZ"}},
               cases={"c1": {"decision": "operator"}},
               escalations=[{"block": "01-02", "stage": "merge", "kind": "cap"}]),
        expect_pages=1, expect_signature="PLANTED-XYZ")
    ok("V6 (R2d no-FP): escalations are ALLOWED for a moderate SIM (expect_pages>0) — "
       "the planted-wall path legitimately populates the log; ACCEPTs",
       okv and not reasons, f"reasons={reasons}")

    # V7 — R2e is a WARNING, NOT a REJECT (ADR §7): a hard-kill at an otherwise-clean
    # session_end must NOT fail the verdict (a >10s claude SIGTERM latency on a
    # mid-turn actor is architecture, not an ignored release — a hard conjunct would
    # false-REJECT a clean run). It is surfaced by run_live's ⚠ output, not here.
    okv, reasons = live._acceptance_verdict(
        _clean(escalated_kills=["engineer-01-02"]), expect_pages=0)
    ok("V7 (R2e WARNING not REJECT): a hard-kill at an otherwise-clean session_end does "
       "NOT fail the verdict (no clean-run false-positive; surfaced as a run_live warning)",
       okv and not reasons, f"reasons={reasons}")

    # V8 — a genuine defect (open case) STILL REJECTs even alongside a kill: R2e's
    # demotion didn't weaken the real conjuncts.
    okv, reasons = live._acceptance_verdict(
        _clean(escalated_kills=["engineer-01-02"],
               cases={"c1": {"decision": None}}), expect_pages=0)
    ok("V8 (R2e demotion is scoped): a real defect (dangling case) still REJECTs even "
       "with a kill present — only the kill-alone conjunct was demoted",
       not okv and any("OPEN" in r for r in reasons)
       and not any("hard-kill" in r for r in reasons), f"reasons={reasons}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.sim.acceptance_verdict_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
