#!/usr/bin/env python3
"""core/pipeline_rig.py — unit lock for the ADR-0008 stale-wall primitives
`pipeline.block_landed_closed` and `pipeline.stale_landing_wall`.

Pure unit rig — no scaffold, no processes. Every FALSE branch of the predicate
is a fail-toward-page guarantee (an unverifiable wall is NEVER suppressed), so
each is locked explicitly. `ok(name, cond, detail)`; `main()` prints
`PASS (n/m)`, exits non-zero on any fail.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_APP_ROOT, "engine"))
sys.path.insert(0, _HERE)

import pipeline   # noqa: E402 — unit under test

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


_LAND = ("land.sh refused: grant minted for commit 98a1347, but worker committed "
         "8f04a86 before landing, causing content mismatch")
_CLOSED = {"gates": {"01-03": {"stage": "closed"}}}
_MERGE = {"gates": {"01-03": {"stage": "merge"}}}
_ESC = {"gates": {"01-03": {"stage": "escalated"}}}


def main():
    # ── block_landed_closed ────────────────────────────────────────────────
    ok("B1: block_landed_closed True iff gate stage=='closed'",
       pipeline.block_landed_closed(_CLOSED, "01-03") is True)
    ok("B2: 'merge' (in-flight) -> False", pipeline.block_landed_closed(_MERGE, "01-03") is False)
    ok("B3: 'escalated' (terminal but NOT landed) -> False — distinct from closed",
       pipeline.block_landed_closed(_ESC, "01-03") is False)
    ok("B4: missing gate -> False", pipeline.block_landed_closed({"gates": {}}, "01-03") is False)
    ok("B5: no gates key -> False", pipeline.block_landed_closed({}, "01-03") is False)
    ok("B6: no block -> False", pipeline.block_landed_closed(_CLOSED, None) is False)

    # ── stale_landing_wall — the TRUE case ─────────────────────────────────
    ok("S1 (the T2-18 killer): worker.wall + engineer-<closed block> + land.sh detail -> True",
       pipeline.stale_landing_wall(_CLOSED, "worker.wall", "engineer-01-03", _LAND) is True)
    ok("S1b: a differently-worded land.sh refusal (grant/land) still matches the signature",
       pipeline.stale_landing_wall(_CLOSED, "worker.wall", "engineer-01-03",
                                   "the land grant was refused; branch tip moved") is True)

    # ── stale_landing_wall — every fail-toward-page FALSE branch ────────────
    ok("S2: non-worker.wall source (sentry.cap) -> False",
       pipeline.stale_landing_wall(_CLOSED, "sentry.cap", "engineer-01-03", _LAND) is False)
    ok("S3: non-engineer worker (architect self-escalation) -> False, never suppressed",
       pipeline.stale_landing_wall(_CLOSED, "worker.wall", "architect", _LAND) is False)
    ok("S4: None worker_id -> False",
       pipeline.stale_landing_wall(_CLOSED, "worker.wall", None, _LAND) is False)
    ok("S5: block NOT closed (merge) -> False — never suppress an in-flight block",
       pipeline.stale_landing_wall(_MERGE, "worker.wall", "engineer-01-03", _LAND) is False)
    ok("S6: block escalated (terminal-not-landed) -> False",
       pipeline.stale_landing_wall(_ESC, "worker.wall", "engineer-01-03", _LAND) is False)
    ok("S7: closed block but NON-landing detail (dep cycle) -> False — landing-scoped by content",
       pipeline.stale_landing_wall(_CLOSED, "worker.wall", "engineer-01-03",
                                   "dependency cycle 01-06<->01-07") is False)
    ok("S8: closed block but empty detail -> False (no signature)",
       pipeline.stale_landing_wall(_CLOSED, "worker.wall", "engineer-01-03", None) is False)
    ok("S9: missing gate for the worker's block -> False",
       pipeline.stale_landing_wall({"gates": {}}, "worker.wall", "engineer-01-03", _LAND) is False)

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.pipeline_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
