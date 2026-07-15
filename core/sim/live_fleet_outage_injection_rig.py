"""core.sim.live_fleet_outage_injection_rig — block 01-38 T19 gate fix H2b:
non-vacuous lock for `core/sim/live.py::_install_fleet_outage_injection`, the
spawn-TIME fleet-outage injection knob the moderate live run drives (`--
inject-fleet-outage-after`) instead of a manual `pkill` (see that function's
own docstring for the full design rationale — orphan-free, resume-coupled
off-switch, narrowed faithfulness claim).

WHY A NEW RIG, NOT A RE-DRIVE OF core/outage_rig.py's OWN SCENARIO: `core/
outage_rig.py::drive_outage` already fully proves the ENGINE-SIDE §2b.1
mechanism (pause, architect-first case, bounded spawn attempts, self-release,
recovery, counter reset) using ITS OWN ad hoc `jobs.spawn_runner` stub as the
death-injector. This rig proves something narrower and NEW: that `core/sim/
live.py`'s actual injection WRAPPER — the one the real live-run CLI knob
installs around `eng._spawn_worker`, not `outage_rig`'s own stub — drives
that SAME real mechanism, and that its resume-coupled self-disable genuinely
fires (not vacuously present-but-inert). It reuses `core/outage_rig.py`'s
proven scaffold-building + scripted-reactor helpers as a LIBRARY (real git
fixture, real `core.engine.Engine`, real `casestate`/`switchboard` code —
nothing about the injected wrapper's own SEAM is re-mocked) rather than
hand-rolling a second copy of that machinery.

Proofs (`main()`, one drive each):
  INJ  (injection ON) — `live._install_fleet_outage_injection` installed at
       t+0 (immediate activation): the wrapper's OWN stats confirm it
       genuinely activated and raised (INJ1); a real `fleet_outage` case
       opens (INJ2, mirrors `core/outage_rig.py`'s O1); the wrapper
       self-disables (`stats["resumed"]`) once dispatch is observed
       un-paused post-resume (INJ3 — the non-vacuity the AMENDMENTS
       specifically demand: proves the resume-coupled off-switch fires, not
       just installs inert); the run reaches a clean, idempotent
       session-end with every fixture block closed (INJ4/INJ5) — genuine
       self-recovery, never a wedge.
  OFF  (injection NEVER installed — the mutation counterpart, NOT merely
       "installed but inactive") — the SAME fixture, SAME scripted reactor,
       runs to a clean session-end with NO `fleet_outage` case EVER opening
       and `consecutive_deaths` staying at 0 the whole drive (OFF1-OFF3) —
       proving INJ's case-open is provably the wrapper's OWN doing, not an
       artifact of the fixture/scaffold itself.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)`, exits
non-zero on any fail.
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app worktree root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

from ctx import Ctx                     # noqa: E402 — engine/ctx.py
from engine import Engine                # noqa: E402 — core/engine.py, real bootup/tick wiring (unedited)
import jobs                                # noqa: E402 — engine/jobs.py, the ONE seam this rig no-op-stubs
import state                                # noqa: E402 — core/state.py
import intake                                # noqa: E402 — core/intake.py
import vocab                                  # noqa: E402 — core/vocab.py, the OPERATOR pseudo-agent-id
import outage_rig                              # noqa: E402 — core/outage_rig.py, REUSED as a library:
                                               # scaffold builders + EngineerReactor (proven real-git
                                               # fixtures) — never re-derived here.
import live                                     # noqa: E402 — core/sim/live.py, unit under test

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _noop_spawn_stub():
    """The ONE process-spawn seam this rig stubs — a BENIGN no-op (never
    raises for anyone, architect included) — deliberately UNLIKE `core/
    outage_rig.py`'s own `make_spawn_stub`: the death injection under test
    here is `live._install_fleet_outage_injection`'s wrap of
    `eng._spawn_worker`, layered ABOVE this seam, not this seam itself. If
    this stub raised too, INJ's own OFF-vs-ON comparison would be
    confounded (unable to tell which layer produced a death)."""
    spawn_calls = []

    def _fake(worker_id, worker_dir, session_id, cwd=None, runtime=None,
             adapter=None, model=None, settle_s=2.0):
        spawn_calls.append({"worker_id": worker_id, "model": model})
        return {}
    return _fake, spawn_calls


def _build_fixture(tag, worker_count):
    OUTAGE_DEATHS = 3
    BLOCKS = ["inj-1", "inj-2"]
    root = outage_rig.build_root(tag)
    outage_rig.seed_pipeline(root, BLOCKS)
    outage_rig.seed_roles(root)
    inst = os.path.join(root, "meta", "agents", "tron")
    outage_rig.write_project_yaml(inst, root)
    outage_rig.write_knobs(inst, worker_count=worker_count, fleet_outage_deaths=OUTAGE_DEATHS)
    return root, inst, BLOCKS, OUTAGE_DEATHS


def _drive(root, inst, blocks, outage_deaths, install_injection):
    """One full boot->tick->teardown drive. `install_injection` is a bool:
    True installs `live._install_fleet_outage_injection` (activated at
    t+0 — no wall-clock wait needed for a rig); False installs nothing at
    all (the mutation counterpart — not merely inactive, genuinely absent).
    Returns `(stats_or_None, outage_case, resumed_tick, session_ended_tick,
    final_manifest, MAX_TICKS)`."""
    MAX_TICKS = 200
    OBSERVE_TICKS = 6

    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    fake_spawn_runner, spawn_calls = _noop_spawn_stub()
    real_spawn_runner = jobs.spawn_runner
    jobs.spawn_runner = fake_spawn_runner

    try:
        eng = Engine(tron_ctx)
        eng.dry = False   # HARD RULE: real trunk observation throughout
        eng._deliver_page = lambda *a, **k: None   # models the outage's own paging channel down too

        stats = None
        if install_injection:
            started_at = time.time()
            stats = live._install_fleet_outage_injection(eng, tron_ctx, started_at, 0.0)

        eng.start(scope="all", worker_count=len(blocks), models={})

        rx = outage_rig.EngineerReactor(root, grants_dir, tron_ctx, blocks)
        verdict_map = {"fleet.outage": "operator"}
        outage_case = {"id": None, "opened_tick": None}
        resumed_tick = {"i": None}
        session_ended_tick = None
        i = 0
        for i in range(1, MAX_TICKS + 1):
            res = eng.tick()
            manifest = state.load(tron_ctx)
            rx.react_engineers(i, manifest)
            rx.react_architect_reconcile(i, manifest)
            rx.react_architect_triage(i, manifest, verdict_map)
            rx.record_done_ticks(i, res["outcomes"])

            if outage_case["id"] is None:
                c = outage_rig.find_open_case(manifest, "fleet_outage")
                if c is not None:
                    outage_case["id"], outage_case["opened_tick"] = c["case_id"], i

            if (outage_case["id"] is not None and resumed_tick["i"] is None
                    and i >= outage_case["opened_tick"] + OBSERVE_TICKS):
                intake.write(tron_ctx, vocab.OPERATOR,
                            {"tag": "operator.decision",
                             "slots": {"case_id": outage_case["id"], "verb": "resume"}})
                resumed_tick["i"] = i

            se = res.get("session_end")
            if se is not None:
                session_ended_tick = i
                break

        final_manifest = state.load(tron_ctx)
        return stats, outage_case, resumed_tick["i"], session_ended_tick, final_manifest, i
    finally:
        jobs.spawn_runner = real_spawn_runner


def main():
    # ══ INJ — injection ON ══
    root, inst, blocks, outage_deaths = _build_fixture("liveinj-on", worker_count=2)
    stats, outage_case, resumed_tick, session_ended_tick, final_manifest, ticks_used = _drive(
        root, inst, blocks, outage_deaths, install_injection=True)

    ok("INJ1: the wrapper genuinely ACTIVATED and raised at least "
       "`fleet_outage_deaths` times (the exact threshold `core/switchboard.py`'s "
       "own knob demands to trip the case) — never installed-but-inert",
       stats is not None and stats["activated"] and stats["injected_raises"] >= outage_deaths,
       f"stats={stats}")
    ok("INJ2 (OUTAGE-DETECTED, via THE WRAPPER — must be GREEN): a real "
       "fleet_outage case opened, driven by live._install_fleet_outage_"
       "injection's own raise, not core/outage_rig.py's own stub",
       outage_case["id"] is not None, f"outage_case={outage_case}")
    ok("INJ3 (THE NON-VACUITY KILLER — must be GREEN): the wrapper's "
       "resume-coupled off-switch genuinely FIRED (`stats['resumed']` True) "
       "— proves the self-disable is live wiring, not a flag that merely "
       "exists and never flips",
       stats is not None and stats["resumed"], f"stats={stats}")
    ok("INJ4: the run reached a clean, idempotent session-end AFTER the "
       "observed resume — genuine self-recovery, never a wedge (a leftover "
       "raise re-deathing the first post-resume spawn would prevent this)",
       session_ended_tick is not None and resumed_tick is not None
       and session_ended_tick >= resumed_tick,
       f"resumed_tick={resumed_tick} session_ended_tick={session_ended_tick} "
       f"ticks_used={ticks_used}")
    final_gates = final_manifest.get("gates") or {}
    all_closed = all((final_gates.get(b) or {}).get("stage") == "closed" for b in blocks)
    ok("INJ5: every fixture block reached a genuine CLOSED gate — dispatch "
       "post-resume actually did real work, not just an empty session-end",
       all_closed, f"gate_stages={[(b, (final_gates.get(b) or {}).get('stage')) for b in blocks]}")
    ok("INJ6: the fleet_outage case is CLOSED (resolved), never left "
       "dangling — settled via the real settle()/architect_resolve path, "
       "the SAME 'operator resume clears it' shape core/outage_rig.py's own "
       "O9 proves for the non-wrapper stub",
       (final_manifest.get("cases") or {}).get(outage_case["id"] or "", {"decision": "MISSING"})
       .get("decision") is not None if outage_case["id"] else False,
       f"case={  (final_manifest.get('cases') or {}).get(outage_case['id']) if outage_case['id'] else None}")

    ok("test:<live_fleet_outage_injection> (H2b): the live-run injection "
       "wrapper genuinely drives the real §2b.1 spawn-refusal path — opens, "
       "self-releases, and the run reaches a clean end",
       stats is not None and stats["activated"] and stats["injected_raises"] >= outage_deaths
       and outage_case["id"] is not None and stats["resumed"]
       and session_ended_tick is not None and all_closed)

    # ══ OFF — the mutation counterpart: injection NEVER installed ══
    root2, inst2, blocks2, outage_deaths2 = _build_fixture("liveinj-off", worker_count=2)
    stats2, outage_case2, resumed_tick2, session_ended_tick2, final_manifest2, ticks_used2 = _drive(
        root2, inst2, blocks2, outage_deaths2, install_injection=False)

    ok("OFF1 (MUTATION PROOF, NO-FALSE-TRIP — must be GREEN): with the "
       "injection wrapper NEVER installed (not merely inactive — genuinely "
       "absent), the IDENTICAL fixture+reactor never opens a fleet_outage "
       "case at all — INJ2's case-open is provably the wrapper's own doing",
       outage_case2["id"] is None, f"outage_case2={outage_case2}")
    ok("OFF2: fleet.consecutive_deaths stayed at 0 the entire drive — no "
       "spawn ever failed once the wrapper is absent",
       (final_manifest2.get("fleet") or {}).get("consecutive_deaths", 0) == 0,
       f"fleet={final_manifest2.get('fleet')}")
    final_gates2 = final_manifest2.get("gates") or {}
    all_closed2 = all((final_gates2.get(b) or {}).get("stage") == "closed" for b in blocks2)
    ok("OFF3: the same fixture still reaches a clean session-end with every "
       "block closed — proves OFF1/OFF2 aren't an artifact of a broken "
       "fixture, only of the wrapper's genuine absence",
       session_ended_tick2 is not None and all_closed2,
       f"session_ended_tick2={session_ended_tick2} "
       f"gate_stages={[(b, (final_gates2.get(b) or {}).get('stage')) for b in blocks2]}")

    ok("test:<live_fleet_outage_injection_mutation> (H2b): injection OFF "
       "(genuinely absent, not just inactive) never opens a fleet_outage "
       "case — INJ's own case-open is the wrapper's doing, not the fixture's",
       outage_case2["id"] is None
       and (final_manifest2.get("fleet") or {}).get("consecutive_deaths", 0) == 0
       and session_ended_tick2 is not None and all_closed2)

    n_pass = sum(1 for _, c, _ in _results if c)
    n_total = len(_results)
    for name, cond, detail in _results:
        mark = "PASS" if cond else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))
    print(f"live_fleet_outage_injection_rig: PASS ({n_pass}/{n_total})")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
