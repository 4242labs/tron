"""core.liveness_working_rig — the regression lock for the WORKING-AWARE
silence fix (GAP-H): a worker that is inbox-SILENT but whose real runner is
provably MID-TURN (`eng._worker_working(wid) is True`) must NOT be pinged or
stalled, however long the turn runs — while a worker that is silent AND not
working must still ping then stall exactly as before. This closes the wall a
real L3 run would otherwise hit on its FIRST build turn: a single `claude -p`
turn posts nothing to the engine inbox until it finishes (minutes), so the
report-only silence ladder would falsely stall every legitimately-working
worker at `silence_escalate_min`.

Unit-level on purpose (drives `core.liveness.sweep` directly with an in-memory
fake `eng` + a plain manifest — NO real git, NO Ctx, deterministic clock): the
behavior under test is entirely inside `sweep`'s per-worker branch, and the
existing `core/liveness_rig.py` already proves the full real-git tick-driven
silence->ping->stall->parked->resume flow. `core.liveness._silence_knobs` is
monkeypatched to a fixed `Knobs(ping=3, escalate=5)` so the two thresholds are
exact; everything else (`casestate.open_case` on stall, the gate flip, the
parked case) runs for REAL against the in-memory manifest.

Five proofs:
  A  working-through-the-cap: silent but `_worker_working=True`, clock driven
     far past escalate — never pinged, never stalled, no case, last_seen kept
     fresh (the FIX).
  B  dead-still-stalls: silent AND not working, clock past escalate — stalled,
     a parked case opens, its gate escalates (the fix did NOT disable liveness).
  C  ping-still-fires: silent, not working, clock in [ping, escalate) — pinged
     once (a real `eng._to_worker` order), pinged_at guards a second, not
     stalled.
  D  working-suppresses-ping: silent but working, clock in [ping, escalate) —
     NOT pinged (an active worker resets its episode before the ping arm).
  E  hung-after-working-recovers: working (seen), THEN the turn ends and it
     goes silent (not working) past escalate — stalls, proving a turn that
     hangs after starting still recovers (worker_runner's turn-timeout is what
     flips it out of `state:working`).

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)`, exits
non-zero on any fail.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # ctx/grants/trunk substrate
sys.path.insert(0, HERE)                                 # core/*.py

import knobs as knobs_mod   # noqa: E402 — core/knobs.py, to build the fixed Knobs
import casestate            # noqa: E402 — core/casestate.py, the real recovery primitive
import liveness             # noqa: E402 — core/liveness.py, the module under test

PING_MIN, ESCALATE_MIN = 3, 5

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


class _Snap:
    """The one field `core.liveness.sweep` reads off a Snapshot."""
    def __init__(self, manifest):
        self.manifest = manifest


class FakeEng:
    """The duck-typed surface `core.liveness.sweep` + `core.casestate.open_case`
    touch — an in-memory stand-in with a DRIVEN clock (`_now`) and a per-worker
    working map (`_worker_working`). `ctx=None` so `casestate.open_case`'s own
    `knobs_mod.load(None)` degrades to the empty-knobs default (its reping
    cadence isn't what THIS rig proves)."""

    def __init__(self):
        self.dry = False
        self.ctx = None
        self.clock = 0.0
        self.working = {}          # wid -> bool
        self.orders = []           # (wid, kind, text)
        self.released = []         # wid
        self.pages = []            # (case_id, block, detail)

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


_FIXED_KNOBS = knobs_mod.Knobs(
    {"silence_ping_min": PING_MIN, "silence_escalate_min": ESCALATE_MIN}, {}, [])


def _install_fixed_knobs():
    liveness._silence_knobs = lambda eng: _FIXED_KNOBS   # noqa: E731 — test seam


def _worker(manifest, wid, block, last_seen=0.0, status="online"):
    manifest.setdefault("workers", {})[wid] = {
        "block": block, "last_seen": last_seen, "status": status}
    manifest.setdefault("gates", {})[block] = {"wid": wid, "stage": "gate.local"}


def _pinged(eng, wid):
    return any(o for o in eng.orders if o[0] == wid and o[1] == "heartbeat.ping")


def _stalled_ids(res):
    return [wid for (_b, wid, _c) in res["stalled"]]


# ══════════════════════════════════════════════════════════════════════════
# A — working through the cap: never pinged, never stalled, last_seen fresh
# ══════════════════════════════════════════════════════════════════════════
def proof_A():
    eng = FakeEng()
    m = {}
    _worker(m, "build-01", "b1", last_seen=0.0)
    eng.working["build-01"] = True
    pinged_ever = stalled_ever = case_ever = False
    for t in (2.0, 6.0, 20.0, 100.0):          # each step > escalate since last_seen=0
        eng.clock = t
        res = liveness.sweep(eng, _Snap(m))
        if _pinged(eng, "build-01"):
            pinged_ever = True
        if "build-01" in _stalled_ids(res):
            stalled_ever = True
        if (m.get("cases") or {}):
            case_ever = True
    last_seen = m["workers"]["build-01"]["last_seen"]
    ok("A1: a silent-but-WORKING worker is NEVER pinged, even past the cap",
       not pinged_ever, f"orders={eng.orders}")
    ok("A2: a silent-but-WORKING worker is NEVER stalled, even past the cap",
       not stalled_ever, f"cases={m.get('cases')}")
    ok("A3: no parked case is ever opened for a working worker", not case_ever)
    ok("A4: last_seen stays anchored fresh to the working worker's clock",
       last_seen == 100.0, f"last_seen={last_seen}")
    ok("A5: the working worker's slot is never freed (still in-flight)",
       "build-01" in (m.get("workers") or {}) and not eng.released,
       f"workers={list((m.get('workers') or {}).keys())} released={eng.released}")


# ══════════════════════════════════════════════════════════════════════════
# B — dead & silent still stalls (the fix did NOT disable liveness)
# ══════════════════════════════════════════════════════════════════════════
def proof_B():
    eng = FakeEng()
    m = {}
    _worker(m, "dead-01", "b2", last_seen=0.0)
    eng.working["dead-01"] = False
    eng.clock = 100.0
    res = liveness.sweep(eng, _Snap(m))
    ok("B1: a silent AND not-working worker IS stalled past the cap",
       "dead-01" in _stalled_ids(res), f"stalled={res['stalled']}")
    ok("B2: a parked operator case is opened for the stalled worker",
       bool(m.get("cases")), f"cases={m.get('cases')}")
    gate_stage = ((m.get("gates") or {}).get("b2") or {}).get("stage")
    ok("B3: the stalled worker's gate is flipped to an escalated (slot-freeing) stage",
       gate_stage == casestate.STAGE_ESCALATED if hasattr(casestate, "STAGE_ESCALATED")
       else gate_stage != "gate.local",
       f"gate_stage={gate_stage!r}")


# ══════════════════════════════════════════════════════════════════════════
# C — ping still fires for a silent, not-working worker (ladder intact)
# ══════════════════════════════════════════════════════════════════════════
def proof_C():
    eng = FakeEng()
    m = {}
    _worker(m, "slow-01", "b3", last_seen=0.0)
    eng.working["slow-01"] = False
    eng.clock = 4.0                              # in [ping=3, escalate=5)
    res = liveness.sweep(eng, _Snap(m))
    first_ping = _pinged(eng, "slow-01")
    n_after_first = len([o for o in eng.orders if o[0] == "slow-01"])
    eng.clock = 4.0                              # still silent, same window
    liveness.sweep(eng, _Snap(m))
    n_after_second = len([o for o in eng.orders if o[0] == "slow-01"])
    ok("C1: a silent, not-working worker in [ping,escalate) is pinged (a real order)",
       first_ping and n_after_first == 1, f"orders={eng.orders}")
    ok("C2: it is NOT stalled while only past ping, not escalate",
       "slow-01" not in _stalled_ids(res))
    ok("C3: pinged_at guards a SECOND ping on a later still-silent call",
       n_after_second == 1, f"orders={eng.orders}")


# ══════════════════════════════════════════════════════════════════════════
# D — a working worker in [ping,escalate) is NOT pinged
# ══════════════════════════════════════════════════════════════════════════
def proof_D():
    eng = FakeEng()
    m = {}
    _worker(m, "wbuild-01", "b4", last_seen=0.0)
    eng.working["wbuild-01"] = True
    eng.clock = 4.0
    liveness.sweep(eng, _Snap(m))
    ok("D1: a WORKING worker in [ping,escalate) is not pinged (active resets episode)",
       not _pinged(eng, "wbuild-01"), f"orders={eng.orders}")


# ══════════════════════════════════════════════════════════════════════════
# E — hung-after-working: seen while working, THEN silent -> stalls
# ══════════════════════════════════════════════════════════════════════════
def proof_E():
    eng = FakeEng()
    m = {}
    _worker(m, "turn-01", "b5", last_seen=0.0)
    eng.working["turn-01"] = True
    eng.clock = 2.0
    liveness.sweep(eng, _Snap(m))               # working -> seen, last_seen=2
    seen = m["workers"]["turn-01"]["last_seen"]
    eng.working["turn-01"] = False               # turn ended / timed out -> no longer working
    eng.clock = 8.0                              # silent 6 >= escalate 5
    res = liveness.sweep(eng, _Snap(m))
    ok("E1: while working the worker is anchored seen (last_seen advanced)",
       seen == 2.0, f"last_seen={seen}")
    ok("E2: once it stops working and stays silent past the cap, it stalls (recovers)",
       "turn-01" in _stalled_ids(res), f"stalled={res['stalled']}")


# ══════════════════════════════════════════════════════════════════════════
# F/G — ADR-0006 R1b: liveness covers a `reviewing` reviewer (the hung-reviewer
# wedge), and SKIPS a `held` reviewer (sentry._pace_reviewers owns that window).
# A reviewer's block is a gate-less `review:<type>` pseudo-block.
# ══════════════════════════════════════════════════════════════════════════
def _reviewer(manifest, wid, status, last_seen=0.0, typ="code"):
    """A reviewer worker record — a gate-LESS `review:<type>` block (no gate
    entry is created, unlike `_worker`)."""
    manifest.setdefault("workers", {})[wid] = {
        "block": f"review:{typ}", "last_seen": last_seen, "status": status}


def proof_F_reviewing_is_paced():
    eng = FakeEng()
    m = {}
    _reviewer(m, "rev-01", status="reviewing", last_seen=0.0)
    eng.working["rev-01"] = False                # hung: never produced its first hand-back
    eng.clock = 100.0
    res = liveness.sweep(eng, _Snap(m))
    ok("F1: a silent `reviewing` reviewer IS stalled (was NEITHER-net'd before R1b)",
       "rev-01" in _stalled_ids(res), f"stalled={res['stalled']}")
    ok("F2: a parked case opens for the hung reviewer",
       bool(m.get("cases")), f"cases={m.get('cases')}")
    ok("F3: the gate-less reviewer's real runner is RELEASED (H5 — no teardown orphan)",
       "rev-01" in eng.released, f"released={eng.released}")
    ok("F4: the reviewer's slot is freed (record popped)",
       "rev-01" not in (m.get("workers") or {}),
       f"workers={list((m.get('workers') or {}).keys())}")


def proof_G_held_is_skipped():
    eng = FakeEng()
    m = {}
    _reviewer(m, "rev-02", status="held", last_seen=0.0)
    eng.working["rev-02"] = False
    eng.clock = 100.0                            # far past the cap
    res = liveness.sweep(eng, _Snap(m))
    ok("G1: a `held` reviewer is NOT stalled by liveness (sentry._pace_reviewers owns it)",
       "rev-02" not in _stalled_ids(res), f"stalled={res['stalled']}")
    ok("G2: a `held` reviewer is NOT pinged by liveness (no double-pace)",
       not _pinged(eng, "rev-02"), f"orders={eng.orders}")
    ok("G3: a `held` reviewer is NOT released by liveness (sentry owns its lifecycle)",
       "rev-02" not in eng.released, f"released={eng.released}")
    ok("G4: a `held` reviewer's record is left in place for sentry",
       "rev-02" in (m.get("workers") or {}))


def _source_clean():
    src = open(os.path.join(HERE, "liveness.py")).read()
    # real USAGE, not the docstring's own "no git/subprocess" prose
    return ("import subprocess" not in src) and ("subprocess.run" not in src) \
        and ("\nimport git" not in src)


def main():
    _install_fixed_knobs()
    proof_A(); proof_B(); proof_C(); proof_D(); proof_E()
    proof_F_reviewing_is_paced(); proof_G_held_is_skipped()
    ok("SRC: core/liveness.py still shells out to no raw git/subprocess of its own",
       _source_clean())

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.liveness_working_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
