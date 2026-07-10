"""core.sentry_working_rig — the regression lock for the WORKING-AWARE gate
pacing fix (GAP-H, sentry side): a gate whose worker is provably MID-TURN
(`eng._worker_working(wid) is True`) must NEVER nudge or escalate, however long
the turn runs — while a gate whose worker is IDLE-at-gate (not working) must
still nudge then escalate exactly as before. Without this, `core.sentry.pace`
would escalate `gate.local` after `GATE_IDLE_CAP` holding-ticks on a worker
that is legitimately still executing its build turn (a single `claude -p` turn
posts nothing observable until it finishes, minutes later) — the SECOND false-
stall a real L3 run would hit on its first block, the sibling of the liveness
one `core/liveness_working_rig.py` locks.

Unit-level (drives `core.sentry.pace` directly with an in-memory fake `eng` +
a plain manifest, deterministic clock — the existing `core/sentry_rig.py`
already proves the full real-git tick-driven nudge/cap flow). `casestate`
runs for real against the in-memory manifest.

Four proofs:
  A  working-through-the-cap: a gate whose worker is working, clock driven far
     past `GATE_IDLE_CAP` — never nudged, never escalated, holding_since kept
     fresh, gate stays live (the FIX).
  B  idle-still-escalates: a gate whose worker is NOT working, clock past the
     cap — escalated, a parked case opens (the fix did NOT disable capping).
  C  idle-nudges-first: not working, clock in [nudge, cap) — nudged once (a
     real order), nudged_at guards a second, not yet escalated.
  D  works-then-idles: working (re-anchored), THEN the turn ends (not working)
     and it holds past the cap -> escalates (a turn that hangs after starting
     still caps — worker_runner's turn-timeout flips it out of state:working).

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)`.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))
sys.path.insert(0, HERE)

import gate                # noqa: E402 — core/gate.py, terminal vocabulary
import sentry              # noqa: E402 — core/sentry.py, the module under test

NUDGE, CAP = sentry.GATE_NUDGE_AFTER, sentry.GATE_IDLE_CAP

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


class _Snap:
    def __init__(self, manifest):
        self.manifest = manifest
        self.gates = manifest.setdefault("gates", {})


class FakeEng:
    def __init__(self):
        self.dry = False
        self.ctx = None
        self.clock = 0.0
        self.working = {}
        self.orders = []
        self.released = []
        self.pages = []

    def _now(self):
        return self.clock

    def _worker_working(self, wid):
        return bool(self.working.get(wid, False))

    def _to_worker(self, wid, text, kind):
        self.orders.append((wid, kind, text))

    def _release_worker(self, wid, reason="released"):
        self.released.append(wid)

    def _page_operator(self, case_id, block, detail, worker_id=None,
                       manifest=None, page_kind="operator_page"):
        self.pages.append((case_id, block, detail))
        if manifest is not None:
            pages = manifest.setdefault("operator_pages", {})
            pid = f"{case_id}-p{len(pages) + 1}"
            pages[pid] = {"page_id": pid, "receipt": "delivered"}
        return "delivered"

    def log(self, channel, msg):
        pass


def _gate(manifest, block, wid, stage="gate.local"):
    manifest.setdefault("gates", {})[block] = {"wid": wid, "stage": stage}


def _nudged(eng, wid):
    return any(o for o in eng.orders if o[0] == wid and o[1].startswith("sentry.nudge"))


def _escalated_blocks(res):
    return [b for (b, _d) in res["escalated"]]


# A — working through the cap
def proof_A():
    eng = FakeEng()
    m = {}
    _gate(m, "b1", "build-01")
    eng.working["build-01"] = True
    nudged_ever = esc_ever = case_ever = False
    for t in (1.0, 3.0, 6.0, 30.0, 100.0):
        eng.clock = t
        res = sentry.pace(eng, _Snap(m))
        if _nudged(eng, "build-01"):
            nudged_ever = True
        if "b1" in _escalated_blocks(res):
            esc_ever = True
        if (m.get("cases") or {}):
            case_ever = True
    gstage = m["gates"]["b1"]["stage"]
    ok("A1: a gate whose worker is WORKING is never nudged, even past the cap",
       not nudged_ever, f"orders={eng.orders}")
    ok("A2: a gate whose worker is WORKING is never escalated, even past the cap",
       not esc_ever)
    ok("A3: no parked case opens for a working worker's gate", not case_ever)
    ok("A4: the gate stays live (not flipped to escalated/terminal)",
       gstage == "gate.local", f"stage={gstage!r}")
    ok("A5: holding_since stays re-anchored fresh to the working worker's clock",
       m["gates"]["b1"].get("holding_since") == 100.0,
       f"holding_since={m['gates']['b1'].get('holding_since')}")


# B — idle still escalates
def proof_B():
    eng = FakeEng()
    m = {}
    _gate(m, "b2", "idle-01")
    eng.working["idle-01"] = False
    esc = False
    for t in range(1, CAP + 3):
        eng.clock = float(t)
        res = sentry.pace(eng, _Snap(m))
        if "b2" in _escalated_blocks(res):
            esc = True
    ok("B1: a gate whose worker is NOT working IS escalated past the cap", esc)
    ok("B2: a parked operator case opens for the escalated gate",
       bool(m.get("cases")), f"cases={list((m.get('cases') or {}).keys())}")
    ok("B3: the escalated gate is flipped terminal (STAGE_ESCALATED)",
       m["gates"]["b2"]["stage"] == gate.STAGE_ESCALATED,
       f"stage={m['gates']['b2']['stage']!r}")


# C — idle nudges first
def proof_C():
    eng = FakeEng()
    m = {}
    _gate(m, "b3", "slow-01")
    eng.working["slow-01"] = False
    # anchor episode at t=0, then hold into [NUDGE, CAP)
    eng.clock = 0.0
    sentry.pace(eng, _Snap(m))
    eng.clock = float(NUDGE)
    res = sentry.pace(eng, _Snap(m))
    n1 = len([o for o in eng.orders if o[0] == "slow-01"])
    eng.clock = float(NUDGE)   # still holding same window
    sentry.pace(eng, _Snap(m))
    n2 = len([o for o in eng.orders if o[0] == "slow-01"])
    ok("C1: an idle gate in [nudge,cap) is nudged once (a real order)",
       _nudged(eng, "slow-01") and n1 == 1, f"orders={eng.orders}")
    ok("C2: it is not yet escalated at only the nudge threshold",
       "b3" not in _escalated_blocks(res))
    ok("C3: nudged_at guards a SECOND nudge while still holding", n2 == 1)


# D — works then idles -> escalates
def proof_D():
    eng = FakeEng()
    m = {}
    _gate(m, "b4", "turn-01")
    eng.working["turn-01"] = True
    for t in (1.0, 2.0, 3.0):
        eng.clock = t
        sentry.pace(eng, _Snap(m))              # working -> re-anchored, never caps
    anchored = m["gates"]["b4"].get("holding_since")
    eng.working["turn-01"] = False               # turn ended -> now idle at gate
    esc = False
    base = 3.0
    for k in range(1, CAP + 3):
        eng.clock = base + k
        res = sentry.pace(eng, _Snap(m))
        if "b4" in _escalated_blocks(res):
            esc = True
    ok("D1: while working the gate is re-anchored (holding_since tracks the clock)",
       anchored == 3.0, f"holding_since={anchored}")
    ok("D2: once the worker stops working and the gate idles past the cap, it escalates",
       esc)


def main():
    proof_A(); proof_B(); proof_C(); proof_D()
    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.sentry_working_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
