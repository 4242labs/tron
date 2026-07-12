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
  V9  ADR-0007 §7: an abandoned block -> REJECT (the app was not built to the fullest)
  V10 ADR-0007 §7 THE HOLE: a moderate abandon-close with FULL escalation fidelity
      (paged, settled, signature carried) -> STILL REJECT — a valid abandon never greens

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
        "abandoned_blocks": [],
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

    # V9 — ADR-0007 §7: an abandoned block REJECTs a trivial SIM (app not built to the fullest)
    okv, reasons = live._acceptance_verdict(_clean(abandoned_blocks=["01-03"]), expect_pages=0)
    ok("V9 (ADR-0007 §7): an abandoned block REJECTs even at a clean session_end "
       "(the app was NOT built to the fullest)",
       not okv and any("abandoned" in r for r in reasons), f"reasons={reasons}")

    # V10 — THE HOLE, closed: a MODERATE abandon-close that satisfies escalation fidelity
    # (planted wall paged, case settled, signature carried) STILL REJECTs because the block
    # was abandoned rather than built. This is the exact false-green ADR-0007 §7 names.
    okv, reasons = live._acceptance_verdict(
        _clean(operator_pages={"p1": {"case_id": "c1", "detail": "PLANTED-XYZ"}},
               cases={"c1": {"decision": "abandon"}},
               abandoned_blocks=["01-05"],
               escalations=[{"block": "01-05", "stage": "local", "kind": "wall"}]),
        expect_pages=1, expect_signature="PLANTED-XYZ")
    ok("V10 (ADR-0007 §7, THE HOLE): a moderate abandon-close with FULL escalation fidelity "
       "(paged, settled, signature) STILL REJECTs — a valid abandon never greens an unbuilt block",
       not okv and any("abandoned" in r for r in reasons), f"reasons={reasons}")

    # ── ADR-0008 guard C — a provably-stale-resolved transient is discounted ──
    # V11 — a landing worker.wall the engine self-resolved on trunk (decision=
    # 'stale-resolved-on-trunk') that ALREADY paged once AND channel-escalated:
    # both the page count and the R2d escalation-log arm discount it -> ACCEPT.
    okv, reasons = live._acceptance_verdict(
        _clean(operator_pages={"p1": {"case_id": "case-stale-1"}},
               cases={"case-stale-1": {"decision": "stale-resolved-on-trunk"}},
               escalations=[{"case": "case-stale-1", "target_block": "01-03",
                             "kind": "operator-page-failed", "level": "warning"}]),
        expect_pages=0)
    ok("V11 (ADR-0008): a paged + channel-escalated case the engine PROVED resolved on "
       "trunk (decision='stale-resolved-on-trunk') is discounted from BOTH the page count "
       "and the R2d escalation log -> ACCEPTs a trivial SIM",
       okv and not reasons, f"reasons={reasons}")

    # V12 (NON-VACUITY) — the SAME page but the case is genuinely OPEN (decision=None):
    # nothing is discounted -> REJECT (guard C only discounts the trunk-truth decision).
    okv, reasons = live._acceptance_verdict(
        _clean(operator_pages={"p1": {"case_id": "case-open-1"}},
               cases={"case-open-1": {"decision": None}}),
        expect_pages=0)
    ok("V12 (ADR-0008 non-vacuity): an OPEN (undecided) case with a page is NOT discounted "
       "-> still REJECTs (dangling case + count) — guard C keys ONLY on the trunk-truth decision",
       not okv and (any("OPEN" in r for r in reasons) or any("escalations" in r for r in reasons)),
       f"reasons={reasons}")

    # V13 (NON-VACUITY) — a case settled by a DIFFERENT decision ('operator', a real
    # human answer) with a page on a trivial SIM: NOT discounted -> REJECT on the count.
    # Proves the discount is scoped to the 'stale-resolved-on-trunk' literal, no other.
    okv, reasons = live._acceptance_verdict(
        _clean(operator_pages={"p1": {"case_id": "case-op-1"}},
               cases={"case-op-1": {"decision": "operator"}}),
        expect_pages=0)
    ok("V13 (ADR-0008 non-vacuity): a case settled by a NON-stale decision ('operator') "
       "with a page still REJECTs a trivial SIM on the count — only 'stale-resolved-on-trunk' "
       "is discounted, never another decision value",
       not okv and any("escalations" in r for r in reasons), f"reasons={reasons}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.sim.acceptance_verdict_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
