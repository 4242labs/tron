"""core.sim.report_channel_rig — TOKEN-FREE integration lock for the worker→
engine REPORT CHANNEL (the T2-01 wall), extended by block 01-38 T1 (the root
invariant) to also lock the private-per-agent-intake channel itself. Proves
the whole inbound path a REAL `claude` worker uses, with NO LLM: a real
`scripts/report.sh --intake <path>` invocation lands a structured line in
THAT agent's own private intake (`core.intake`, never a single shared file
any more), and `core.snapshot.build`'s observe pass resolves it — via
`core.classify` (structured bypass, model never called) — to the CANONICAL
`worker.*` tag the router/gate read, with the block slot promoted, so
`gate.local`'s own `local_reports` predicate sees it, AND pairs it with an
`Origin` (`core.intake.Origin`) resolved purely from WHICH intake it drained
from.

Covers the fixes that unblock a real run together:
  1. `core.sim.seed_canon.install_canon` puts `messages.yaml`/`prompts/`/
     `scripts/report.sh` in the instance a real seeder would.
  2. `scripts/report.sh --intake <path>` lands its line in EXACTLY that
     agent's own private intake (`core.intake.intake_path`) — proven by
     RUNNING it and reading that file back.
  3. `core.classify._structured` maps report.sh's raw verb (`done`/`wall`/
     `review-done`) to the canonical `worker.*` tag (an already-namespaced
     tag — what every scripted rig writes — passes through untouched).
  4. **T1's own root-invariant proofs** — `test:<ambient_identity>` (a
     report's identity is the intake it arrived on; the script cannot name
     another agent) and `test:<origin_from_channel_only>` (the door
     produces an `Origin` whose id is the channel's, independent of any
     name in the message body) — both through the REAL `report.sh`
     subprocess, never a rig-internal injection.

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
import intake                       # noqa: E402 — core/intake.py, block 01-38 T1's per-agent intake + Origin
import architect                    # noqa: E402 — core/architect.py, ARCHITECT_WID
from boot_real_scaffold_rig import copy_real_scaffold, seed_live_instance   # noqa: E402
from seed_canon import install_canon   # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _report(inst, intake_path, *args):
    """Run the REAL installed report.sh exactly as the engine renders it for
    a worker (`core/engine.py::Engine._report_invocation` — block 01-38 T1:
    `--intake <path>` is now the FIRST argument, baked in by the engine,
    never chosen by the caller of this helper the way a worker-id claim
    once was)."""
    script = os.path.join(inst, "scripts", "report.sh")
    r = subprocess.run(["bash", script, "--intake", intake_path, *args],
                       capture_output=True, text=True)
    return r


def _report_no_intake(inst, *args):
    """R11: the adversarial/malformed shape — no `--intake` at all — proving
    the script has no fallback identity to guess."""
    script = os.path.join(inst, "scripts", "report.sh")
    return subprocess.run(["bash", script, *args], capture_output=True, text=True)


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

    AGENT_1 = "engineer-01-02"
    REVIEWER_1 = "reviewer-code-1"
    intake_1 = intake.intake_path(ctx, AGENT_1)
    intake_rev = intake.intake_path(ctx, REVIEWER_1)
    intake_arch = intake.intake_path(ctx, architect.ARCHITECT_WID)

    # ── 1. a real `--tag done` local-pass report, on AGENT_1's OWN intake ──
    r = _report(inst, intake_1, AGENT_1, "--tag", "done", "--block", "01-02",
                "done 01-02 — local: acceptance suite green")
    ok("R1: report.sh exited 0", r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")
    ok("R2 (block 01-38 T1): report.sh wrote to EXACTLY the --intake path it was "
       "handed — AGENT_1's own private intake, never a single shared file",
       os.path.exists(intake_1) and os.path.getsize(intake_1) > 0,
       f"intake_1={intake_1} exists={os.path.exists(intake_1)}")

    snap = snapshot.build(eng)
    done = [r for r in snap.worker_reports if r.get("tag") == "worker.done"]
    ok("R3: the raw `--tag done` line resolved to CANONICAL worker.done (verb->tag map)",
       len(done) == 1, f"worker_reports tags={[r.get('tag') for r in snap.worker_reports]}")
    ok("R4: the --block slot promoted to the report's top level",
       bool(done) and done[0].get("block") == "01-02",
       f"report={done[0] if done else None}")
    ok("R5: gate.local's own predicate sees it — local_reports['01-02'] populated",
       "01-02" in snap.local_reports, f"local_reports={dict(snap.local_reports)}")
    ok("R5b (block 01-38 T1): the drained report carries a real, typed Origin "
       "(never a bare string) matching AGENT_1's own intake",
       bool(done) and done[0].get("origin") == intake.Origin(vocab.WORKER, AGENT_1),
       f"origin={done[0].get('origin') if done else None}")
    snapshot.release(snap)

    # ── 2. a real `--tag wall` ──
    _report(inst, intake_1, AGENT_1, "--tag", "wall", "--block", "01-02",
            "wall 01-02: the spec contradicts the acceptance criteria")
    snap = snapshot.build(eng)
    ok("R6: `--tag wall` resolved to canonical worker.wall",
       any(r.get("tag") == "worker.wall" for r in snap.worker_reports),
       f"tags={[r.get('tag') for r in snap.worker_reports]}")
    snapshot.release(snap)

    # ── 3. a real `--tag review-done` (dash form), on REVIEWER_1's OWN intake ──
    _report(inst, intake_rev, REVIEWER_1, "--tag", "review-done", "--type", "code",
            "review done code: coverage complete")
    snap = snapshot.build(eng)
    ok("R7: `--tag review-done` resolved to canonical worker.review_done",
       any(r.get("tag") == "worker.review_done" for r in snap.worker_reports),
       f"tags={[r.get('tag') for r in snap.worker_reports]}")
    snapshot.release(snap)

    # ── 4. flags-after-message is a HARD ERROR at report.sh (fat-finger guard) ──
    r = _report(inst, intake_1, AGENT_1, "a plain message", "--tag", "wall")
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

    # ── 11. report.sh REQUIRES --intake — no name-based fallback, no guess ──
    r = _report_no_intake(inst, AGENT_1, "--tag", "flag", "--block", "01-02", "still here")
    ok("R11 (block 01-38 T1): report.sh REFUSES to run at all without --intake — "
       "there is no other mechanism, name-based or otherwise, that decides where "
       "a report lands",
       r.returncode != 0, f"rc={r.returncode} stderr={r.stderr!r}")

    # ══════════════════════════════════════════════════════════════════════
    # T1 THE ROOT INVARIANT — the two required proofs, both through the REAL
    # report.sh subprocess (never a rig-internal injection).
    # ══════════════════════════════════════════════════════════════════════

    # test:<ambient_identity> — a report's identity is the intake it arrived
    # on; the script cannot name another agent. Hand report.sh AGENT_1's OWN
    # real --intake path, but a WID POSITIONAL claiming to be a DIFFERENT
    # worker ("engineer-not-01-02") — the resulting report's Origin must
    # still be AGENT_1's own, because --intake, not the claimed name, is
    # what decided where the line landed. (A claim of the literal ARCHITECT
    # id is a SEPARATE, already-closed impersonation surface — ADR-0011 S-1's
    # minters check, unmodified by this task — so this proof uses an
    # ordinary worker-shaped claim, the one shape minters never gated.)
    _report(inst, intake_1, "engineer-not-01-02", "--tag", "flag", "--block", "01-02",
            "impersonation attempt: WID claims a different worker, --intake says otherwise")
    snap = snapshot.build(eng)
    flags = [r for r in snap.worker_reports if r.get("tag") == "worker.flag"
             and r.get("block") == "01-02"]
    ok("test:<ambient_identity> — the report's identity is the intake it "
       "arrived on (AGENT_1's own), NEVER the WID the script's own positional "
       "argument claimed ('engineer-not-01-02') — the script has no mechanism "
       "to name another agent",
       bool(flags) and flags[-1]["origin"] == intake.Origin(vocab.WORKER, AGENT_1),
       f"origin={flags[-1].get('origin') if flags else None}")
    snapshot.release(snap)

    # test:<origin_from_channel_only> — the door produces an Origin whose id
    # is the channel's, independent of any name in the message body. Hand
    # report.sh the ARCHITECT's own real --intake path, but a WID positional
    # naming neither the architect nor any real worker — the resulting
    # Origin must still resolve ARCHITECT/architect's own id, purely from
    # WHICH intake the line was drained from.
    #
    # Block 01-38 T2 (CHANGED from T1): the probe tag is now `reconciled`
    # (architect.reconciled, minters=(ARCHITECT,)), not `flag` (worker.flag,
    # minters=(WORKER,)). Under T1 this used `--tag flag` and still passed,
    # because admission (`vocab.minters_ok`) still ran off the message's OWN
    # forgeable `sender`/`agent_id` claim at that point (T2's own job was
    # deleting that) — a worker-shaped body claim satisfied worker.flag's
    # minters regardless of which channel the line actually arrived on. Now
    # that T2 has deleted the payload-trusting fallback, minters is checked
    # against the TRUE channel origin: the architect's own intake can never
    # mint a WORKER-only tag, so `--tag flag` here would now be correctly
    # REFUSED (the exact impersonation gap this task closes) — a `flag`
    # probe can no longer prove "origin resolves from channel, body claim
    # ignored" for an ARCHITECT channel, because it would never reach
    # admission at all. `reconciled` is architect-legal, so the message is
    # admitted, letting this test isolate the SAME "channel decides, body
    # claim is powerless" property it always meant to prove.
    _report(inst, intake_arch, "definitely-not-architect", "--tag", "reconciled", "--block", "01-09",
            "channel says architect; the message body names nobody real")
    snap = snapshot.build(eng)
    arch_reconciled = [r for r in snap.worker_reports if r.get("tag") == "architect.reconciled"
                       and r.get("block") == "01-09"]
    ok("test:<origin_from_channel_only> — the door's Origin is resolved purely "
       "from WHICH intake the line drained from (the architect's own), "
       "independent of the 'definitely-not-architect' name the message body "
       "itself carries",
       bool(arch_reconciled)
       and arch_reconciled[-1]["origin"] == intake.Origin(vocab.ARCHITECT, architect.ARCHITECT_WID),
       f"origin={arch_reconciled[-1].get('origin') if arch_reconciled else None}")
    snapshot.release(snap)

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.sim.report_channel_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
