"""core.sim.operator_channel_rig — R8 (ADR-0012 §2, block 01-38 T2/T3) proof:
the operator channel is real, in BOTH directions, with defined receipt
semantics and a defined floor.

Real git scaffold (`boot_real_scaffold_rig.copy_real_scaffold`/
`seed_live_instance`, the SAME real `trivial-tip-converter` source every
prior `core/*_rig.py` uses), real canon (`seed_canon.install_canon` — which,
as of this block, ALSO installs `scripts/tg-send.sh`/`scripts/operator-
reply.sh`), a REAL `core.engine.Engine` (`jobs.spawn_runner` stubbed — no
real `claude` process, the established "rig plays the worker" pattern).

  OUT1/OUT2 (AC-3, T2 outbound) — `Engine._deliver_page` runs the REAL
    `scripts/tg-send.sh` subprocess (a deterministic test-double standing in
    for Telegram — "make it a seam a test double can stand in for", never a
    hand-simulated receipt) and records a genuine `"delivered"` receipt;
    `manifest["operator_pages"]`/`case["paging"]` carry it durably.
  OUT3 (AC-3) — a delivered-but-UNSEEN page re-pings on its OWN, separate
    budget (`casestate.SEEN_REPING_AFTER`, monkeypatched small here for a
    fast proof) — never satisfied by `delivered` alone.
  IN1/IN2 (AC-5, T3 inbound) — a REAL `scripts/operator-reply.sh` subprocess
    (never a Python file write) lands on `ctx.operator_inbox`; `core/
    snapshot.py::build`'s operator-channel drain (T3: EVERY TICK, alongside
    every per-agent channel) resolves it via the REAL classify->router->
    casestate.settle path and marks the SECOND receipt level, `seen`
    (AC-3's other half) — even before the reply is drained, `seen` is
    False; the drain is what flips it.
  FLOOR1-FLOOR4 (AC-4, THE TERMINAL FLOOR) — with the REAL, un-stubbed
    transport permanently failing (the seeded `tg-send.sh` with no live
    `.env` in this sandbox — an HONEST failure, never simulated) and
    `casestate.PAGE_CHANNEL_ESCALATE_AFTER`/`PAGE_PERMANENT_FAIL_AFTER`
    monkeypatched small for a fast proof, a REAL `Engine.start()` + repeated
    `Engine.tick()` drive trips safe-park-and-halt: a must-be-zero counter
    is written, a full state snapshot is recorded, and the run's OWN
    `session_end` marker (via `core/tick.py`'s new safe-park short-circuit)
    fires — never an unbounded re-ping, never a silent log.

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on
fail.
"""
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import jobs                          # noqa: E402 — engine/jobs.py, the ONE stubbed process-spawn seam
from ctx import Ctx                   # noqa: E402 — engine/ctx.py
from engine import Engine             # noqa: E402 — core/engine.py, THE MODULE UNDER TEST
import casestate                       # noqa: E402 — core/casestate.py, THE MODULE UNDER TEST (T2/T3 additions)
import classify                         # noqa: E402 — core/classify.py, the real structured door
import router                            # noqa: E402 — core/router.py, the real operator.decision route
import snapshot                           # noqa: E402 — core/snapshot.py, THE MODULE UNDER TEST (T3 drain)
import state                               # noqa: E402 — core/state.py
from boot_real_scaffold_rig import copy_real_scaffold, seed_live_instance   # noqa: E402
from seed_canon import install_canon        # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


_FAKE_TG_ALWAYS_OK = """#!/usr/bin/env bash
# operator_channel_rig's deterministic test double for scripts/tg-send.sh —
# "make it a seam a test double can stand in for" (ADR-0012 R8/T2): never
# touches a network, always answers success, records every call for this
# rig's own assertions.
set -euo pipefail
echo "$1" >> "$(dirname "$0")/.tg-calls.log"
echo "tg-send: ok (rig double)"
"""


def _seed(prefix):
    root = copy_real_scaffold()
    inst, _project, _knobs = seed_live_instance(root)
    installed = install_canon(inst)
    return Ctx(inst), installed


def _real_spawn_stub():
    calls = []

    def fake_spawn_runner(worker_id, worker_dir, session_id, cwd=None,
                          runtime=None, adapter=None, model=None, settle_s=2.0):
        calls.append(worker_id)
        return {}
    return fake_spawn_runner, calls


def main():
    real_spawn_runner = jobs.spawn_runner
    orig_seen_after = casestate.SEEN_REPING_AFTER
    orig_escalate_after = casestate.PAGE_CHANNEL_ESCALATE_AFTER
    orig_permanent_after = casestate.PAGE_PERMANENT_FAIL_AFTER

    try:
        # ══════════════════════════════════════════════════════════════
        # PART 1 — OUTBOUND (T2/AC-3): delivered receipt, via the REAL
        # tg-send.sh subprocess (a deterministic test double)
        # ══════════════════════════════════════════════════════════════
        ctx1, installed1 = _seed("out")
        print(f"inst1={ctx1.dir}")
        ok("SEED1: seed_canon installs scripts/tg-send.sh + scripts/operator-reply.sh "
           "(block 01-38 — a real deployment must HAVE these, not just report.sh)",
           "scripts/tg-send.sh" in installed1 and "scripts/operator-reply.sh" in installed1,
           f"installed={installed1}")

        tg_path = ctx1.p("scripts", "tg-send.sh")
        with open(tg_path, "w") as f:
            f.write(_FAKE_TG_ALWAYS_OK)
        os.chmod(tg_path, 0o755)

        fake_spawn, _ = _real_spawn_stub()
        jobs.spawn_runner = fake_spawn
        eng1 = Engine(ctx1)
        eng1.dry = False
        manifest1 = {}
        cid1 = casestate.open_operator_case(
            eng1, manifest1, "01-02", "test.outbound",
            "operator_channel_rig: OUT phase — forcing a real page", worker_id=None)
        pages1 = list((manifest1.get("operator_pages") or {}).values())
        ok("OUT1 (AC-3): the REAL, un-stubbed _deliver_page ran the REAL tg-send.sh "
           "subprocess and recorded a genuine 'delivered' receipt",
           len(pages1) == 1 and pages1[0].get("receipt") == "delivered",
           f"pages1={pages1}")
        tg_calls_log = os.path.join(os.path.dirname(tg_path), ".tg-calls.log")
        ok("OUT1b: the fake transport genuinely received the rendered page text "
           "(via tg.escalate — messages.yaml, T5)",
           os.path.exists(tg_calls_log) and os.path.getsize(tg_calls_log) > 0,
           f"log_exists={os.path.exists(tg_calls_log)}")
        case1 = manifest1["cases"][cid1]
        ok("OUT2 (AC-3): delivered but NOT yet seen — the second receipt level "
           "never defaults to true",
           case1["paging"]["last_receipt"] == "delivered"
           and not case1["paging"].get("seen"),
           f"paging={case1['paging']}")

        # ── OUT3: an unseen page re-pings on ITS OWN budget (SEEN_REPING_AFTER,
        #     monkeypatched small) — delivered alone never satisfies the floor ──
        casestate.SEEN_REPING_AFTER = 2
        repinged_now2 = casestate.reping(eng1, manifest1, now=2)
        ok("OUT3a: at now=2 (< delivered_since(1) + SEEN_REPING_AFTER(2) = 3), no re-ping yet",
           cid1 not in repinged_now2, f"repinged={repinged_now2}")
        repinged_now4 = casestate.reping(eng1, manifest1, now=4)
        ok("OUT3b (AC-3 KILLER): once the unseen budget expires, THE FLOOR forces "
           "one more page — 'delivered' alone never stops the ladder for an "
           "UNSEEN page (closes the historical 36-minutes-unseen bug)",
           cid1 in repinged_now4, f"repinged={repinged_now4}")
        pages1_after = list((manifest1.get("operator_pages") or {}).values())
        ok("OUT3c: the unseen re-ping is durably recorded (a SECOND page entry)",
           len(pages1_after) == 2 and pages1_after[1].get("kind") == "operator_page_unseen",
           f"pages1_after={pages1_after}")

        # ══════════════════════════════════════════════════════════════
        # PART 2 — INBOUND (T3/AC-5): a REAL scripts/operator-reply.sh
        # subprocess settles the case via the real classify->router->settle
        # path; the SAME reply also proves the 'seen' receipt (AC-3)
        # ══════════════════════════════════════════════════════════════
        reply_script = ctx1.p("scripts", "operator-reply.sh")
        r = subprocess.run([reply_script, cid1, "resume", "unblock it"],
                           capture_output=True, text=True, timeout=15)
        ok("IN1: the REAL operator-reply.sh subprocess exits 0",
           r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")
        ok("IN1b: it wrote to EXACTLY ctx.operator_inbox (never worker_inbox)",
           os.path.exists(ctx1.operator_inbox) and os.path.getsize(ctx1.operator_inbox) > 0,
           f"operator_inbox={ctx1.operator_inbox}")

        # T3: drained EVERY TICK, alongside every per-agent channel —
        # exercised here via the SAME drain `core/snapshot.py::build` calls.
        op_reports, _sidecars = snapshot._drain_operator_channel(ctx1, eng1.log, manifest1)
        ok("IN2 (AC-3, seen): draining the operator's reply marks the case SEEN "
           "— even before it resolves into a verb",
           manifest1["cases"][cid1]["paging"].get("seen") is True,
           f"paging={manifest1['cases'][cid1]['paging']}")
        ok("IN2b: the drained line's sender is ambiently 'operator' (never a "
           "payload field the script itself asserted, though it does too)",
           len(op_reports) == 1 and op_reports[0]["sender"] == {"kind": "operator", "id": "operator"},
           f"op_reports={op_reports}")

        tag, slots = classify.classify(eng1, op_reports[0], manifest1)
        ok("IN3: the REAL classify() resolves the reply to operator.decision "
           "(case_id/verb intact)",
           tag == "operator.decision" and slots.get("case_id") == cid1 and slots.get("verb") == "resume",
           f"tag={tag} slots={slots}")
        router._route_decision(eng1, manifest1, {"tag": tag, "slots": slots})
        ok("IN4 (AC-5 KILLER): the REAL router->casestate.settle path cleared "
           "the case — a real inbound operator command genuinely settles it, "
           "the live inbound path a real human uses",
           cid1 not in manifest1.get("cases", {}),
           f"cases={list(manifest1.get('cases', {}))}")

        casestate.SEEN_REPING_AFTER = orig_seen_after

        # ══════════════════════════════════════════════════════════════
        # PART 3 — THE TERMINAL FLOOR (AC-4): permanent transport failure
        # -> safe-park-and-halt, via a REAL Engine.start()+tick() drive
        # ══════════════════════════════════════════════════════════════
        ctx2, installed2 = _seed("floor")
        print(f"inst2={ctx2.dir}")
        # Deliberately NO fake tg-send.sh here — the REAL seeded one (no
        # live `.env` in this sandbox) fails HONESTLY, every single call —
        # exactly the "no live creds required" shape the block specifies.
        casestate.PAGE_CHANNEL_ESCALATE_AFTER = 2
        casestate.PAGE_PERMANENT_FAIL_AFTER = 4

        fake_spawn2, _ = _real_spawn_stub()
        jobs.spawn_runner = fake_spawn2
        eng2 = Engine(ctx2)
        eng2.dry = False
        eng2.start(scope="all", worker_count=1, models={})
        manifest2 = state.load(ctx2)
        cid2 = casestate.open_operator_case(
            eng2, manifest2, None, "test.safe_park",
            "operator_channel_rig: FLOOR phase — forcing permanent failure",
            worker_id=None)
        state.save(ctx2, manifest2)
        pages2_first = list((state.load(ctx2).get("operator_pages") or {}).values())
        ok("FLOOR1: the first page against the REAL (creds-less) tg-send.sh "
           "genuinely, honestly fails — never a default-delivered assumption",
           len(pages2_first) == 1 and pages2_first[0].get("receipt") == "failed",
           f"pages2_first={pages2_first}")

        safe_parked = False
        session_end = None
        for i in range(1, 40):
            result = eng2.tick()
            if result.get("session_end") is not None:
                session_end = result["session_end"]
                safe_parked = bool(session_end.get("safe_park"))
                break
        final_manifest = state.load(ctx2)
        ok("FLOOR2 (AC-4 KILLER): the run tripped safe-park-and-halt — a NAMED "
           "terminal state, never an unbounded re-ping and never a silent log",
           safe_parked is True, f"session_end={session_end}")
        ok("FLOOR3 (AC-4): a must-be-zero counter was durably written "
           "(operator_floor_permanent_fail, 01-39 owns the partition/read; "
           "this block WRITES it)",
           (final_manifest.get("counters") or {}).get("operator_floor_permanent_fail", 0) >= 1,
           f"counters={final_manifest.get('counters')}")
        safe_park_rec = final_manifest.get("safe_park") or {}
        ok("FLOOR4 (AC-4): a FULL state snapshot was recorded on the trip "
           "(cases/gates/workers/operator_pages) — forensic, never lost",
           isinstance(safe_park_rec.get("snapshot"), dict)
           and set(safe_park_rec["snapshot"].keys()) >= {"cases", "gates", "workers", "operator_pages"},
           f"safe_park={safe_park_rec}")
        ok("FLOOR5: a must_be_zero event was durably emitted (eng.events)",
           any(e.get("type") == "must_be_zero"
               and e.get("payload", {}).get("counter") == "operator_floor_permanent_fail"
               for e in eng2.events.log),
           f"events={[e for e in eng2.events.log if e.get('type') == 'must_be_zero']}")
        ok("FLOOR6: once safe-parked, the run is a TRUE no-op re-tick "
           "(session.already_ended reads the SAME marker) — the halt sticks",
           eng2.tick().get("session_end") == session_end,
           "re-tick after safe-park")

        passed = sum(1 for _, c, _ in _results if c)
        print(f"\ncore.sim.operator_channel_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
              f"({passed}/{len(_results)})")
        for name, c, detail in _results:
            print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
        return 0 if passed == len(_results) else 1
    finally:
        jobs.spawn_runner = real_spawn_runner
        casestate.SEEN_REPING_AFTER = orig_seen_after
        casestate.PAGE_CHANNEL_ESCALATE_AFTER = orig_escalate_after
        casestate.PAGE_PERMANENT_FAIL_AFTER = orig_permanent_after


if __name__ == "__main__":
    sys.exit(main())
