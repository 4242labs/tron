"""core.sim.report_channel_rig — TOKEN-FREE integration lock for the worker→
engine REPORT CHANNEL (the T2-01 wall). Proves the whole inbound path a REAL
`claude` worker uses, with NO LLM: a real `scripts/report.sh` invocation lands
a structured line in `ctx.worker_inbox`, and `core.snapshot.build`'s observe
pass resolves it — via `core.classify` (structured bypass, model never called)
— to the CANONICAL `worker.*` tag the router/gate read, with the block slot
promoted, so `gate.local`'s own `local_reports` predicate sees it.

Covers the three fixes that unblock a real run together:
  1. `core.sim.seed_canon.install_canon` puts `messages.yaml`/`prompts/`/
     `scripts/report.sh` in the instance a real seeder would.
  2. `scripts/report.sh` self-locates the engine inbox as `../worker-inbox.
     jsonl` — proven by RUNNING it and reading `ctx.worker_inbox`.
  3. `core.classify._structured` maps report.sh's raw verb (`done`/`wall`/
     `review-done`) to the canonical `worker.*` tag (an already-namespaced
     tag — what every scripted rig writes — passes through untouched).

Real git scaffold (a fresh COPY, source untouched), real `report.sh`
subprocess, real `Ctx`/`Engine`/`snapshot`. `jobs.spawn_runner` never called
(no worker process at all — this tests the CHANNEL, not the fleet).

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on fail.
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

from ctx import Ctx                 # noqa: E402 — engine/ctx.py
from engine import Engine           # noqa: E402 — core/engine.py
import snapshot                     # noqa: E402 — core/snapshot.py, the observe pass under test
import vocab                        # noqa: E402 — core/vocab.py, the verb->tag map under test (AC-1)
from boot_real_scaffold_rig import copy_real_scaffold, seed_live_instance   # noqa: E402
from seed_canon import install_canon   # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _report(inst, *args):
    """Run the REAL installed report.sh exactly as a worker would."""
    script = os.path.join(inst, "scripts", "report.sh")
    r = subprocess.run(["bash", script, *args], capture_output=True, text=True)
    return r


def main():
    root = copy_real_scaffold()
    inst, _project, _knobs = seed_live_instance(root)
    installed = install_canon(inst)
    print(f"root={root}")
    print(f"inst={inst}")
    print(f"canon installed={installed}")

    ok("C0: canon installed — messages.yaml + prompts/ + scripts/report.sh present",
       all(os.path.exists(os.path.join(inst, p)) for p in
           ("messages.yaml", "prompts/registry.yaml", "scripts/report.sh")),
       f"installed={installed}")

    ctx = Ctx(inst)
    eng = Engine(ctx)
    eng.dry = False

    # report.sh must land its line in EXACTLY ctx.worker_inbox (its own
    # `../worker-inbox.jsonl` resolution == the file the tick drains).
    inbox = ctx.worker_inbox

    # ── 1. a real `--tag done` local-pass report ──
    r = _report(inst, "engineer-01-02", "--tag", "done", "--block", "01-02",
                "done 01-02 — local: acceptance suite green")
    ok("R1: report.sh exited 0", r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")
    ok("R2: report.sh wrote to EXACTLY ctx.worker_inbox (its ../ resolution is correct)",
       os.path.exists(inbox) and os.path.getsize(inbox) > 0,
       f"inbox={inbox} exists={os.path.exists(inbox)}")

    snap = snapshot.build(eng)
    done = [r for r in snap.worker_reports if r.get("tag") == "worker.done"]
    ok("R3: the raw `--tag done` line resolved to CANONICAL worker.done (verb->tag map)",
       len(done) == 1, f"worker_reports tags={[r.get('tag') for r in snap.worker_reports]}")
    ok("R4: the --block slot promoted to the report's top level",
       bool(done) and done[0].get("block") == "01-02",
       f"report={done[0] if done else None}")
    ok("R5: gate.local's own predicate sees it — local_reports['01-02'] populated",
       "01-02" in snap.local_reports, f"local_reports={dict(snap.local_reports)}")
    snapshot.release(snap)

    # ── 2. a real `--tag wall` ──
    _report(inst, "engineer-01-02", "--tag", "wall", "--block", "01-02",
            "wall 01-02: the spec contradicts the acceptance criteria")
    snap = snapshot.build(eng)
    ok("R6: `--tag wall` resolved to canonical worker.wall",
       any(r.get("tag") == "worker.wall" for r in snap.worker_reports),
       f"tags={[r.get('tag') for r in snap.worker_reports]}")
    snapshot.release(snap)

    # ── 3. a real `--tag review-done` (dash form) ──
    _report(inst, "reviewer-code-1", "--tag", "review-done", "--type", "code",
            "review done code: coverage complete")
    snap = snapshot.build(eng)
    ok("R7: `--tag review-done` resolved to canonical worker.review_done",
       any(r.get("tag") == "worker.review_done" for r in snap.worker_reports),
       f"tags={[r.get('tag') for r in snap.worker_reports]}")
    snapshot.release(snap)

    # ── 4. flags-after-message is a HARD ERROR at report.sh (fat-finger guard) ──
    r = _report(inst, "engineer-01-02", "a plain message", "--tag", "wall")
    ok("R8: report.sh rejects a flag AFTER the message (the --tag-wall fat-finger guard)",
       r.returncode != 0, f"rc={r.returncode}")

    # ── 5. the verb map itself (block 01-37, AC-1): an already-namespaced
    #     tag passes through unchanged; every report.sh verb maps to its
    #     canonical worker.*/architect.* tag — single source, core/vocab.py ──
    ok("R9: vocab.verb_to_tag passes an already-namespaced tag through unchanged (rigs untouched)",
       vocab.verb_to_tag("worker.done") == "worker.done"
       and vocab.verb_to_tag("architect.reconciled") == "architect.reconciled",
       "")
    ok("R10: vocab.verb_to_tag maps every report.sh verb to its canonical tag",
       vocab.verb_to_tag("done") == "worker.done"
       and vocab.verb_to_tag("recorded") == "worker.recorded"
       and vocab.verb_to_tag("wall") == "worker.wall"
       and vocab.verb_to_tag("review-done") == "worker.review_done"
       and vocab.verb_to_tag("clean") == "worker.done"
       and vocab.verb_to_tag("flag") == "worker.flag"
       and vocab.verb_to_tag("verdict") == "architect.triage_verdict",
       "")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.sim.report_channel_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
