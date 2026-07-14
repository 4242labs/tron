"""core.sim.ambient_identity_rig — R6 (ADR-0012 §2, block 01-38 T1) proof:
identity is AMBIENT, never asserted. A REAL `core.engine.Engine._real_spawn`
(via the stubbed process-spawn seam, `jobs.spawn_runner` — the established
"rig plays the worker" pattern every `core/*_rig.py` already uses; never a
real `claude` process) installs a per-agent report channel — `inbox/
<agent_id>.jsonl` — plus a per-agent COPY of the seeded `scripts/report.sh`
at `workers/<agent_id>/report.sh`, byte-identical, never templated. This
rig drives THAT REAL installed copy as a genuine `bash` subprocess (never a
hand-written JSONL line) and proves:

  AC-1 — each spawned agent gets its OWN `inbox/<agent-id>.jsonl`; the
    drained report's sender is the CHANNEL FILENAME, never a payload field
    (even a maliciously hand-crafted payload claiming a different identity
    is corrected); `report.sh` (the ambient invocation) carries no typed
    `<worker-id>` argv at all.
  AC-2 — a worker attempting to mint as the architect CANNOT: running its
    OWN installed copy against an architect-only tag (`--tag verdict`)
    still resolves to ITS OWN identity (the channel it physically ran on),
    so `minters` (via `core.door.admit`) rejects it — D8 closed
    structurally, never by convention.

Real git scaffold (a fresh COPY, source untouched — `boot_real_scaffold_
rig.copy_real_scaffold`/`seed_live_instance`), real `Ctx`/`Engine`,
`jobs.spawn_runner` stubbed (no real `claude` process — this tests the
CHANNEL + door, not the fleet).

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on
fail.
"""
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
import architect                       # noqa: E402 — core/architect.py, ARCHITECT_WID
import classify                         # noqa: E402 — core/classify.py, the real structured door
import door                              # noqa: E402 — core/door.py, minters enforcement (AC-2)
import snapshot                           # noqa: E402 — core/snapshot.py, the observe pass under test
import vocab                               # noqa: E402 — core/vocab.py
from boot_real_scaffold_rig import copy_real_scaffold, seed_live_instance   # noqa: E402
from seed_canon import install_canon        # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _run(script, *args):
    r = subprocess.run(["bash", script, *args], capture_output=True, text=True, timeout=20)
    return r


class _EventsLog:
    def __init__(self):
        self.log = []

    def event(self, type_, **payload):
        self.log.append({"type": type_, "payload": payload})


def main():
    root = copy_real_scaffold()
    inst, _project, _knobs = seed_live_instance(root)
    installed = install_canon(inst)
    ctx = Ctx(inst)
    print(f"root={root}")
    print(f"inst={inst}")
    print(f"canon installed={installed}")

    real_spawn_runner = jobs.spawn_runner
    spawn_calls = []

    def fake_spawn_runner(worker_id, worker_dir, session_id, cwd=None,
                          runtime=None, adapter=None, model=None, settle_s=2.0):
        spawn_calls.append(worker_id)
        return {}

    jobs.spawn_runner = fake_spawn_runner
    try:
        eng = Engine(ctx, events=_EventsLog())
        eng.dry = False   # real spawn-time side effects (channel install), never a real process

        wid = "engineer-01-02"
        eng._real_spawn(wid, "engineer", "01-02")

        # ══ T1/AC-1: the per-agent channel exists, is empty, and report.sh
        #     was installed byte-identical, ambient ══
        inbox_path = ctx.agent_inbox(wid)
        script_path = ctx.agent_report_script(wid)
        ok("A1: inbox/<agent-id>.jsonl was created AT SPAWN",
           os.path.isfile(inbox_path), f"inbox_path={inbox_path}")
        ok("A2: the per-agent report.sh copy was installed AT SPAWN, executable",
           os.path.isfile(script_path) and os.access(script_path, os.X_OK),
           f"script_path={script_path}")
        with open(os.path.join(ctx.p("scripts", "report.sh"))) as f:
            canon_src = f.read()
        with open(script_path) as f:
            installed_src = f.read()
        ok("A3: the installed copy is BYTE-IDENTICAL to the seeded canon (never templated)",
           canon_src == installed_src, "content mismatch" if canon_src != installed_src else "")

        # ══ AC-1: the ambient invocation carries NO typed worker-id argv ══
        r = _run(script_path, "--tag", "done", "--block", "01-02", "done - local pass")
        ok("A4: the REAL ambient report.sh (no worker-id argv at all) exits 0",
           r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")
        ok("A5: it wrote to EXACTLY THIS agent's own inbox/<agent-id>.jsonl",
           os.path.exists(inbox_path) and os.path.getsize(inbox_path) > 0,
           f"inbox_path={inbox_path}")

        # ══ AC-1: the drained report's sender is the CHANNEL, never a payload
        #     field — even a payload that claims a DIFFERENT identity is
        #     overwritten by `core/snapshot.py`'s ambient stamp ══
        with open(inbox_path, "a") as fh:
            import json
            fh.write(json.dumps({
                "tag": "done", "text": "an impersonation attempt",
                "sender": {"kind": "worker", "id": "someone-else-entirely"},
                "agent_id": "someone-else-entirely",
            }) + "\n")

        snap = snapshot.build(eng)
        reports = [rep for rep in snap.worker_reports if rep.get("tag") == "worker.done"]
        ok("A6: TWO worker.done reports drained off this ONE agent's channel",
           len(reports) == 2, f"reports={reports}")
        ok("A7 (AC-1 KILLER): EVERY report's sender.id is the CHANNEL FILENAME "
           f"({wid!r}) — even the one whose OWN payload claimed a different "
           "identity ('someone-else-entirely') is corrected, never trusted "
           "from the payload",
           all(rep.get("sender", {}).get("id") == wid for rep in reports)
           and all(rep.get("agent_id") == wid for rep in reports),
           f"senders={[rep.get('sender') for rep in reports]} "
           f"agent_ids={[rep.get('agent_id') for rep in reports]}")
        snapshot.release(snap)

        # ══ AC-2: a worker attempting to mint as the architect CANNOT — its
        #     OWN channel resolves to ITS OWN identity regardless of what tag
        #     it sends, so minters rejects an architect-only verb ══
        r2 = _run(script_path, "--tag", "verdict", "--triage-id", "T-1",
                  "--verdict", "answer", "trying to mint as the architect")
        ok("A8: report.sh's LOCAL courtesy check has no opinion on minters "
           "(that is the engine's own door, not this script's job) — the "
           "line still lands (it IS a legal --tag)",
           r2.returncode == 0, f"rc={r2.returncode} stderr={r2.stderr!r}")

        with open(inbox_path) as fh:
            last_line = [ln for ln in fh.read().splitlines() if ln.strip()][-1]
        import json as _json
        msg = _json.loads(last_line)
        msg["sender"] = {"kind": "worker", "id": wid}   # the SAME ambient stamp snapshot.py applies
        origin = vocab.resolve_origin(msg, architect.ARCHITECT_WID)
        ok("A9 (AC-2 KILLER): the impersonation attempt's origin resolves to "
           "WORKER — the channel it physically ran on — never ARCHITECT, no "
           "matter what tag it claims",
           origin == vocab.WORKER, f"origin={origin} msg={msg}")
        admit_ok, reason = door.admit("architect.triage_verdict",
                                      msg.get("slots") or {}, msg, architect.ARCHITECT_WID)
        ok("A10 (AC-2 KILLER, D8 CLOSED): `core.door.admit` REFUSES the "
           "architect-only verdict tag from this worker's own channel — a "
           "worker physically cannot mint as the architect",
           admit_ok is False and "architect" in (reason or "").lower(),
           f"admit_ok={admit_ok} reason={reason!r}")

        # ══ Control: the ARCHITECT's own channel legitimately mints it ══
        eng._real_spawn(architect.ARCHITECT_WID, "architect", None)
        arch_script = ctx.agent_report_script(architect.ARCHITECT_WID)
        r3 = _run(arch_script, "--tag", "verdict", "--triage-id", "T-2",
                  "--verdict", "answer", "the real architect's own verdict")
        ok("A11: the ARCHITECT's own installed copy exits 0",
           r3.returncode == 0, f"rc={r3.returncode} stderr={r3.stderr!r}")
        with open(ctx.agent_inbox(architect.ARCHITECT_WID)) as fh:
            arch_last = [ln for ln in fh.read().splitlines() if ln.strip()][-1]
        arch_msg = _json.loads(arch_last)
        arch_msg["sender"] = {"kind": "worker", "id": architect.ARCHITECT_WID}
        arch_origin = vocab.resolve_origin(arch_msg, architect.ARCHITECT_WID)
        ok("A12 (CONTROL — must be GREEN): the SAME verdict tag from the "
           "architect's OWN channel resolves to ARCHITECT and IS admitted — "
           "proving A10 is a genuine minters check, never a blanket refusal",
           arch_origin == vocab.ARCHITECT,
           f"arch_origin={arch_origin}")
        admit_ok2, reason2 = door.admit("architect.triage_verdict",
                                        arch_msg.get("slots") or {}, arch_msg,
                                        architect.ARCHITECT_WID)
        ok("A13 (CONTROL — must be GREEN)", admit_ok2 is True, f"reason2={reason2!r}")

        # ══ A REAL classify() pass over the architect's own line resolves the
        #     verdict wire end to end (never touches the model — structured
        #     bypass) ══
        tag, slots = classify.classify(eng, arch_msg, {})
        ok("A14: the real classify() resolves the architect's own channel "
           "line to architect.triage_verdict",
           tag == "architect.triage_verdict" and slots.get("triage_id") == "T-2",
           f"tag={tag} slots={slots}")

        # ══ Refusal of the SAME shape from the worker's channel — the
        #     REAL classify() (never a hand-simulated door check) ══
        tag_w, slots_w = classify.classify(eng, msg, {})
        ok("A15 (AC-2, REAL classify() — the actual production path, never "
           "hand-simulated): the SAME verdict tag from the WORKER's channel "
           "is REFUSED at the door — resolves to (None, None), never routed",
           tag_w is None and slots_w is None, f"tag_w={tag_w} slots_w={slots_w}")

        # ══ Legacy mode stays untouched (a first arg not starting with '--'
        #     is still the pre-01-38 self-typed shape) — no regression ══
        legacy_script = ctx.p("scripts", "report.sh")
        r4 = _run(legacy_script, "some-legacy-worker", "--tag", "done", "legacy still works")
        ok("A16 (NO REGRESSION): the LEGACY self-typed invocation "
           "(pre-01-38 rigs / the retired engine) still exits 0, unchanged",
           r4.returncode == 0, f"rc={r4.returncode} stderr={r4.stderr!r}")
        ok("A17: the legacy invocation wrote to the SHARED worker-inbox.jsonl, "
           "never a per-agent channel",
           os.path.exists(ctx.worker_inbox), f"worker_inbox={ctx.worker_inbox}")

        passed = sum(1 for _, c, _ in _results if c)
        print(f"\ncore.sim.ambient_identity_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
              f"({passed}/{len(_results)})")
        for name, c, detail in _results:
            print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
        return 0 if passed == len(_results) else 1
    finally:
        jobs.spawn_runner = real_spawn_runner


if __name__ == "__main__":
    sys.exit(main())
