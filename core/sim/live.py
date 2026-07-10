"""core.sim.live — the LIVE L3 driver (the acceptance-bar runner).

The one missing piece between `core.sim.launch` (boots the real scaffold +
wires real workers, but runs NO tick loop) and an actual real-LLM end-to-end
SIM: this module BOOTS `core.engine.Engine` over a fresh real-git COPY of the
real `trivial-tip-converter` scaffold with REAL `claude` workers (`core.sim.
real_tier`, `adapter="host-cli"`) + REAL `classify`, then DRIVES the tick loop
in real wall-clock time to a clean session-end — emitting a PROACTIVE PULSE
each loop and always tearing the real fleet down.

## The clock (why wall-clock MINUTES)

The engine's two timer subsystems read `eng._now()` when present. The real
`knobs.yaml` expresses `silence_ping_min`/`silence_escalate_min` in MINUTES
(6/8), and `core.sentry`'s gate idle-cap constants (3/6) are treated in the
same unit — so this driver injects `eng._now = lambda: time.time()/60.0`
(wall-clock minutes), making every threshold a real duration. The working-
aware pacing fixes (`core/liveness.py` + `core/sentry.py`, the
`eng._worker_working` hook this driver's `Engine` wires to real `runner.json`
`state:"working"`) mean a legitimately-working worker — a `claude -p` turn is
silent and posts nothing until it finishes, minutes later — is NEVER falsely
pinged/stalled/escalated; only genuine idle/dead time counts.

## PULSE — proactive, OS-level, every loop (not just an operator report)

Each loop, INDEPENDENT of anything a worker self-reports, PULSE probes real
liveness at the OS level: `os.kill(pid, 0)` (via `jobs.is_alive`) for every
worker the manifest knows, `pgrep -fa worker_runner.py|claude` scoped to this
run's own copy root to catch ghosts/orphans, plus gate stages, blocks ✅ on
trunk, and the trunk tip. Passive/self-reported signals eventually fail; the
pid probe is the ground truth. The PULSE is printed AND written to the home
log.

## Pause-and-report

The loop stops and hands back to the caller (never leaving a real fleet
running unmonitored — `finally` always releases + hard-kills) on:
  - a clean session-end (SUCCESS),
  - a NEW operator page (`manifest["operator_pages"]` grew — the engine itself
    escalated to a human, architect-first routing having decided so),
  - the wall-clock budget (`budget_min`) being exceeded,
  - a driver-level exception.
Project-walls that the architect can absorb never page the operator, so they
never pause the run — exactly the engine's own architect-first contract.

Safety: real processes are ALWAYS torn down in `finally` (release, then
hard-kill any survivor); the driver asserts + reports any orphan `worker_
runner.py`/`claude` still alive whose command line references this run's copy
root at exit.

CLI: `python3 -m core.sim.live --workers 1 --budget-min 60 [--poll-sec 20]
[--scaffold-src <dir>]`. Run SPARINGLY — this spends real tokens.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app worktree root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import jobs                       # noqa: E402 — engine/jobs.py, the OS-level liveness + fleet seam
from ctx import Ctx                # noqa: E402 — engine/ctx.py
from engine import Engine, BootupError   # noqa: E402 — core/engine.py, THE MODULE this drives
import state                       # noqa: E402 — core/state.py
import gitobs                       # noqa: E402 — core/gitobs.py, the ONE git-observation seam
import real_tier                    # noqa: E402 — core/sim/real_tier.py, the real host-cli spawn wiring
# the real-scaffold copy + live-instance seed, reused verbatim (never re-derived)
from boot_real_scaffold_rig import copy_real_scaffold, seed_live_instance   # noqa: E402
from seed_canon import install_canon   # noqa: E402 — installs the instance canon a real run needs

MAIN = "main"
DEFAULT_POLL_SEC = 20.0


class LiveRunError(RuntimeError):
    """A driver-owned refusal/abort — fails loud, never a silent best-effort."""


def _now_minutes():
    return time.time() / 60.0


def _pgrep_scoped(root):
    """Real `worker_runner.py`/`claude` processes whose cmdline references THIS
    run's own copy root — the OS-level ground-truth process list (scoped so a
    blind `claude` match never counts an unrelated host session)."""
    lines = []
    for pat in ("worker_runner.py", "claude"):
        out = subprocess.run(["pgrep", "-fa", pat], capture_output=True, text=True)
        lines += [ln for ln in out.stdout.splitlines() if ln.strip() and root in ln]
    return lines


def _pulse(eng, root, manifest, loop_i, started_at):
    """One PROACTIVE, OS-level PULSE line — printed and home-logged. Never
    trusts a self-reported field for liveness: `jobs.is_alive` is a pid
    probe, `_pgrep_scoped` is the real process scan."""
    workers = manifest.get("workers") or {}
    idx = jobs.index()
    worker_bits = []
    for wid, w in sorted(workers.items()):
        rec = idx.get(wid) or {}
        alive = jobs.is_alive(wid)
        worker_bits.append(f"{wid}[{w.get('block')}]:alive={int(alive)}"
                           f",state={rec.get('state')},turns={rec.get('turns')}")
    gates = manifest.get("gates") or {}
    gate_bits = [f"{b}:{g.get('stage')}" for b, g in sorted(gates.items())]

    try:
        trunk_tip = gitobs.tip_sha(root, MAIN, False)[:12]
    except Exception as e:   # noqa: BLE001
        trunk_tip = f"<err:{e}>"

    scope_ids = (manifest.get("scope") or {}).get("ids") or []
    procs = _pgrep_scoped(root)
    cases = manifest.get("cases") or {}
    pages = manifest.get("operator_pages") or {}
    elapsed = (time.time() - started_at) / 60.0

    line = (f"PULSE#{loop_i} t+{elapsed:.1f}min | workers: "
            f"{'; '.join(worker_bits) or '(none)'} | gates: "
            f"{', '.join(gate_bits) or '(none)'} | trunk={trunk_tip} "
            f"scope={scope_ids} | os_procs={len(procs)} cases={len(cases)} "
            f"pages={len(pages)}")
    print(line, flush=True)
    try:
        eng.log("pulse", line)
    except Exception:   # noqa: BLE001 — a log write must never kill the loop
        pass
    return {"os_procs": procs, "cases": len(cases), "pages": len(pages)}


def _courier(eng, manifest, delivered):
    """THE COURIER — harvest each worker's turn OUTPUT into the engine inbox.

    Delivery must NOT depend on the LLM choosing to run `report.sh` (a real
    agent replies in prose instead — the tron-06 wall). So each loop, read
    every worker's `timeline.jsonl` `turn_done` events and append any not-yet-
    delivered turn text to `ctx.worker_inbox` as a free-text `{text, sender}`
    report — exactly the shape `report.sh` free-text produces, which
    `core.classify` then resolves. A structured `report.sh --tag` line (when
    the agent DID run it) still lands directly and its deterministic tag wins;
    the courier is the robust fallback, never the only path. `delivered` (a
    set of `(wid, seq)`) dedupes across loops so a turn is couriered once."""
    inbox = eng.ctx.worker_inbox
    workers = manifest.get("workers") or {}
    couriered = 0
    for wid in list(workers.keys()):
        tl = os.path.join(eng.ctx.worker_dir(wid), jobs.TIMELINE)
        if not os.path.isfile(tl):
            continue
        try:
            with open(tl) as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for ln in lines:
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if ev.get("event") != "turn_done":
                continue
            key = (wid, ev.get("seq"))
            if key in delivered:
                continue
            delivered.add(key)
            text = (ev.get("text") or "").strip()
            if not text:
                continue
            try:
                with open(inbox, "a") as ib:
                    ib.write(json.dumps({"text": text,
                                         "sender": {"kind": "worker", "id": wid}}) + "\n")
                couriered += 1
            except OSError:
                pass
    return couriered


def run_live(scaffold_src=None, worker_count=1, budget_min=60.0,
             poll_sec=DEFAULT_POLL_SEC, scope="all", max_loops=100000,
             adapter="host-cli"):
    """Boot + drive a real-LLM E2E SIM to a clean session-end (or a pause
    condition). Returns a structured result dict. ALWAYS tears the real fleet
    down. See module docstring for the clock, PULSE, and pause semantics.

    `adapter="host-cli"` is the real-LLM run. `adapter="echo"` is the TOKEN-
    FREE integration smoke — real `worker_runner.py` OS processes, no `claude`,
    so the loop exercises boot -> tick -> PULSE (real pid probes) -> teardown
    -> 0-orphans without spending a token (echo workers never build/land, so
    it ends on `budget`, never `session_end`; that is expected)."""
    if scaffold_src:
        os.environ["TRON_REAL_SCAFFOLD_SRC"] = scaffold_src

    root = copy_real_scaffold()                 # fresh real-git COPY (source untouched)
    inst, _project, _knobs_path = seed_live_instance(root)
    canon = install_canon(inst)                 # messages.yaml/prompts/report.sh/... a real run needs
    print(f"live: canon installed -> {canon}")
    ctx = Ctx(inst)

    eng = Engine(ctx)
    eng.dry = False                              # real trunk observation throughout
    eng._now = _now_minutes                      # wall-clock MINUTES (see module docstring)

    print(f"live: copy root={root}")
    print(f"live: instance dir={inst}")
    print(f"live: worker_count={worker_count} budget_min={budget_min} "
          f"poll_sec={poll_sec} scope={scope}")

    started_at = time.time()
    reason = None
    outcome = "unknown"
    session_end = None
    loop_i = 0
    boot_spawn = None

    rs = real_tier.real_spawn(adapter=adapter)
    rs.__enter__()                                # install REAL spawn wiring (host-cli or echo)
    try:
        try:
            boot_spawn = eng.start(scope=scope, worker_count=worker_count, models={})
        except BootupError as e:
            raise LiveRunError(f"bootup refused: {e}") from e
        print(f"live: bootup complete — first dispatch={boot_spawn}")

        prev_pages = 0
        delivered = set()   # (wid, seq) already couriered — see _courier
        while loop_i < max_loops:
            loop_i += 1
            # THE COURIER runs BEFORE observe so this tick sees the harvested
            # reports — delivery never depends on the agent running report.sh.
            try:
                n = _courier(eng, state.load(ctx), delivered)
                if n:
                    print(f"  courier: delivered {n} turn-output report(s) to the inbox", flush=True)
            except Exception as e:   # noqa: BLE001 — the courier must never kill the loop
                print(f"  courier: error (non-fatal): {e}", flush=True)

            try:
                res = eng.tick()
            except Exception as e:   # noqa: BLE001 — surface a driver/engine fault, then tear down
                reason = f"engine tick raised: {type(e).__name__}: {e}"
                outcome = "error"
                traceback.print_exc()
                break

            manifest = state.load(ctx)
            pulse = _pulse(eng, root, manifest, loop_i, started_at)

            if res.get("session_end") is not None:
                session_end = res["session_end"]
                outcome = "session_end"
                reason = session_end.get("reason") if isinstance(session_end, dict) else str(session_end)
                break

            # DATA-GATHERING mode: a new operator page is LOGGED and the run
            # CONTINUES (never pause on the first wall) — one run surfaces every
            # downstream wall instead of one-at-a-time. Budget/session-end are
            # the only stops.
            if pulse["pages"] > prev_pages:
                print(f"  [WALL] operator page #{pulse['pages']} — logged, continuing "
                      f"to gather downstream walls", flush=True)
            prev_pages = pulse["pages"]

            if (time.time() - started_at) / 60.0 >= budget_min:
                outcome = "budget"
                reason = f"wall-clock budget {budget_min} min reached before session-end"
                break

            time.sleep(poll_sec)
    finally:
        escalated_kills = rs.teardown(timeout_s=10.0)
        rs.__exit__(None, None, None)
        orphans = _pgrep_scoped(root)
        final_manifest = state.load(ctx)
        try:
            final_tip = gitobs.tip_sha(root, MAIN, False)[:12]
        except Exception:   # noqa: BLE001
            final_tip = "<err>"

    result = {
        "root": root, "inst": inst, "outcome": outcome, "reason": reason,
        "loops": loop_i, "elapsed_min": (time.time() - started_at) / 60.0,
        "session_end": session_end,
        "boot_spawn": boot_spawn,
        "escalated_kills": escalated_kills,
        "orphans": orphans,
        "final_trunk_tip": final_tip,
        "cases": final_manifest.get("cases") or {},
        "operator_pages": final_manifest.get("operator_pages") or {},
        "escalations": final_manifest.get("escalations") or [],
        "scope": final_manifest.get("scope") or {},
    }
    print("=" * 72)
    print(f"live: OUTCOME={outcome} reason={reason}")
    print(f"live: loops={loop_i} elapsed_min={result['elapsed_min']:.1f} "
          f"final_trunk_tip={final_tip}")
    print(f"live: orphans_at_exit={orphans} (hard-killed: {escalated_kills})")
    print(f"live: cases={list(result['cases'].keys())} "
          f"pages={list(result['operator_pages'].keys())} "
          f"escalations={len(result['escalations'])}")
    print(f"live: copy root (forensics)={root}")
    print("=" * 72)
    return result


def build_parser():
    ap = argparse.ArgumentParser(
        prog="python3 -m core.sim.live",
        description="LIVE L3 driver: real claude workers + real classify over a "
                    "fresh real-git copy of the trivial-tip-converter scaffold, "
                    "driven to a clean session-end. Spends REAL tokens — run sparingly.")
    ap.add_argument("--workers", type=int, default=1, dest="worker_count")
    ap.add_argument("--budget-min", type=float, default=60.0, dest="budget_min")
    ap.add_argument("--poll-sec", type=float, default=DEFAULT_POLL_SEC, dest="poll_sec")
    ap.add_argument("--scope", default="all")
    ap.add_argument("--scaffold-src", default=None, dest="scaffold_src",
                    help="override the real scaffold source dir (default: the "
                        "boot rig's TRON_REAL_SCAFFOLD_SRC)")
    ap.add_argument("--adapter", choices=("host-cli", "echo"), default="host-cli",
                    help="host-cli = real claude (spends tokens); echo = token-free "
                        "integration smoke (real worker_runner processes, no LLM)")
    return ap


def _install_sigterm():
    """SIGTERM -> KeyboardInterrupt so `run_live`'s `finally` (fleet teardown)
    runs on an external `kill`, not just on a graceful exit — no orphans when
    the run is stopped from outside."""
    import signal

    def _handler(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, OSError):
        pass


def main(argv=None):
    _install_sigterm()
    args = build_parser().parse_args(argv)
    try:
        result = run_live(scaffold_src=args.scaffold_src, worker_count=args.worker_count,
                          budget_min=args.budget_min, poll_sec=args.poll_sec,
                          scope=args.scope, adapter=args.adapter)
    except LiveRunError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    # exit 0 only on a clean session-end with no orphan left behind
    ok = result["outcome"] == "session_end" and not result["orphans"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
