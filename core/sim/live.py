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
hard-kill any survivor); the driver then asserts NO orphan survived. The
orphan check is SCOPED to this run's own fleet (`_owned_orphans`): a worker
THIS driver spawned (its id is in `rs.spawn_calls`) still alive after teardown,
or a real `worker_runner.py`/`claude` EXECUTABLE for this run's root. It is NOT
a global command-line sweep — a bystander that merely references the copy root
(a monitor shell, a `tail`, an editor whose path contains `.claude`) is
structurally excluded, so it can never false-REJECT an otherwise-clean run.

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
import architect                    # noqa: E402 — core/architect.py, ARCHITECT_WID (courier the architect too)
from operator_proxy import tick as operator_proxy_tick   # noqa: E402 — core/sim/operator_proxy.py, moderate-tier LLM operator (ADR-0007)
# the real-scaffold copy + live-instance seed, reused verbatim (never re-derived)
from boot_real_scaffold_rig import copy_real_scaffold, seed_live_instance   # noqa: E402
from seed_canon import install_canon   # noqa: E402 — installs the instance canon a real run needs

_ARCHITECT_WID = architect.ARCHITECT_WID

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


_SHELL_EXES = ("bash", "-bash", "sh", "dash", "zsh", "ksh", "env", "tail",
               "grep", "cat", "less", "vi", "vim", "nano", "python3-monitor")


def _is_worker_exec(cmdline):
    """True iff `cmdline` is a REAL worker process — a `worker_runner.py` run or
    a `claude` executable — NOT a shell/tool that merely references a path
    containing `.claude` or the run root. Classifies by the EXECUTABLE (argv[0]
    basename), so `/bin/bash -c '... /home/x/.claude/... /tmp/<root>/... '` (a
    monitor/tail bystander) is excluded, while `.../claude.exe --session-id ...`
    (a real re-parented worker child) is kept. This is the discriminator the old
    substring sweep lacked — it matched `.claude` anywhere in any command line."""
    if "worker_runner.py" in cmdline:
        return True
    toks = cmdline.split()
    if not toks:
        return False
    exe = os.path.basename(toks[0])
    if exe in _SHELL_EXES:
        return False                       # a shell is never a worker, whatever it mentions
    return exe.startswith("claude") or (exe.startswith("node") and "claude" in cmdline)


def _proc_cwd(pid):
    """Best-effort `readlink /proc/<pid>/cwd` — '' when unavailable (non-Linux,
    a race, permissions). Factored out so the orphan rig can stub it."""
    try:
        return os.readlink(f"/proc/{int(pid)}/cwd")
    except (OSError, ValueError):
        return ""


def _proc_pgid(pid):
    """Best-effort `os.getpgid(pid)` — None when unavailable (the process exited,
    or a permission/OS error). Factored out so the orphan rig can stub it."""
    try:
        return os.getpgid(int(pid))
    except (ProcessLookupError, PermissionError, OSError, ValueError):
        return None


def _worker_owned_by_root(pid, root, cmdline, run_pgids=frozenset()):
    """True iff a worker-exec process belongs to THIS run's `root`, by ANY of
    three POSITIVE ownership signals (never a fail-open assumption of absence —
    ADR-0006 R2a):
      1. `root` in argv — a `worker_runner.py` is spawned as
         `python3 <root>/.../worker_runner.py`, so its root is in the command line.
      2. pgid-LINEAGE — a real `claude` CHILD gets `root` only via `Popen(cwd=…)`,
         NEVER in argv, so signal 1 alone MISSES a re-parented `claude` that
         outlived its crashed runner. But the runner leads its own process group
         (`jobs.spawn_runner` start_new_session=True) and the runner forks `claude`
         WITHOUT start_new_session, so the child INHERITS the runner's pgid — which
         equals the runner's pid, and STAYS that even after the runner dies and the
         child re-parents to init. `run_pgids` is the set of this run's spawned-
         runner pids; a survivor whose pgid is in it is deterministically ours.
      3. CWD under `root` — a belt-and-suspenders positive signal (a real worker's
         cwd is its worker dir under `root`); retained but no longer the sole net.
    Signal 2 is what closes the B1 false-NEGATIVE: a re-parented `claude` whose
    argv lacks `root` AND whose `/proc/<pid>/cwd` is unreadable (a race) is still
    caught by its inherited pgid. Every signal is POSITIVE, so a foreign `claude`
    (another Claude Code session) — foreign pgid, no root in argv, foreign cwd —
    is never spuriously flagged (no false-positive REJECT)."""
    if root in cmdline:
        return True
    if run_pgids:
        pgid = _proc_pgid(pid)
        if pgid is not None and pgid in run_pgids:
            return True
    r = root.rstrip("/")
    cwd = _proc_cwd(pid)
    return cwd == r or cwd.startswith(r + "/")


def _owned_orphans(rs, root):
    """Teardown-hygiene check SCOPED to this driver's OWN fleet — never a global
    process sweep (that was `_pgrep_scoped`, which false-flagged any bystander
    whose command line referenced the copy root or contained `.claude`). An
    orphan is EITHER a worker THIS run spawned — its id is in `rs.spawn_calls`,
    and its recorded pid is still alive after teardown (OS-truth via
    `jobs.is_alive`) — OR a real `worker_runner.py`/`claude` EXECUTABLE for this
    run's `root` that outlived its record (a re-parented child, matched by CWD —
    see `_worker_owned_by_root` — since its argv never carries root). A monitor
    shell, a `tail`, or an editor that merely names the root is structurally
    excluded on every arm: it is not in the spawn ledger, and it is not a worker
    executable (`_is_worker_exec`). Returns human-readable survivor lines (empty ==
    a clean teardown)."""
    survivors = []
    idx = jobs.index()
    # ADR-0006 R2a: this run's OWNED process-group ids — each spawned runner's pid
    # (it leads its own pgid; every `claude` it forks inherits it). A crashed
    # runner's runner.json persists on disk, so its pid is still recoverable here
    # for lineage matching after death. Used to attribute a re-parented `claude`
    # child by pgid when neither its argv nor its cwd resolves ownership.
    run_pgids = set()
    for wid in sorted({c["worker_id"] for c in (rs.spawn_calls or [])}):
        rec = jobs.find(wid, idx) or {}
        pid = rec.get("pid")
        if pid:
            run_pgids.add(int(pid))
        if jobs.is_alive(wid, idx):
            survivors.append(f"{wid} (pid={rec.get('pid')}) — spawned worker still alive after teardown")
    self_pid = os.getpid()
    for pat in ("worker_runner.py", "claude"):
        out = subprocess.run(["pgrep", "-fa", pat], capture_output=True, text=True)
        for ln in out.stdout.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            parts = ln.split(None, 1)
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            # Order matters: exclude bystanders (shells/monitors) FIRST via the
            # executable class, THEN test ownership by root — so a monitor whose
            # argv happens to contain root never triggers a readlink, and a real
            # worker child whose argv LACKS root is still caught by its cwd.
            if pid == self_pid or not _is_worker_exec(parts[1]):
                continue
            if not _worker_owned_by_root(pid, root, parts[1], run_pgids):
                continue          # a worker exec for some OTHER run's root — not ours
            if ln not in survivors:
                survivors.append(ln)
    return survivors


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
    # Harvest the persistent ARCHITECT too — it is pool-EXCLUDED (never in
    # manifest["workers"]), so a workers-only loop would never deliver its
    # turn output. Without this, a real architect's `architect.reconciled`/
    # triage completion never reaches the engine -> the reconcile-gate never
    # clears -> the next block is gated FOREVER (the historical "01-03 never
    # closed", forward-wall #4).
    harvest_ids = list(workers.keys())
    if _ARCHITECT_WID not in harvest_ids:
        harvest_ids.append(_ARCHITECT_WID)
    couriered = 0
    for wid in harvest_ids:
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
             adapter="host-cli", operator_proxy=False):
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
    proxy_settled = 0   # ADR-0007: operator-proxy-settled case count (result surface)

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
        proxy_decided = set()   # ADR-0007: case_ids the operator-proxy already settled this run
        proxy_attempts = {}     #           per-case decide attempts (malformed-output cap)
        if operator_proxy:
            print("live: operator-proxy ENABLED (moderate tier — an LLM decides "
                  "escalated operator cases on the operator's behalf)", flush=True)
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

            # ADR-0007: the MODERATE-tier operator-proxy runs right after the courier
            # and before the tick, so the SAME tick drains+settles any decision it
            # injects. OFF by default — a complex SIM's pages reach the real human.
            if operator_proxy:
                try:
                    inj = operator_proxy_tick(eng, state.load(ctx),
                                              proxy_decided, proxy_attempts)
                    if inj:
                        proxy_settled += inj
                        print(f"  operator-proxy: injected {inj} operator.decision "
                              f"report(s) (total settled this run: {proxy_settled})", flush=True)
                except Exception as e:   # noqa: BLE001 — the proxy must never kill the loop
                    print(f"  operator-proxy: error (non-fatal): {e}", flush=True)

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
        orphans = _owned_orphans(rs, root)
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
        "proxy_settled": proxy_settled,   # ADR-0007: operator cases the LLM proxy settled
        "abandoned_blocks": final_manifest.get("abandoned_blocks") or [],   # ADR-0007 §7: must be []
    }
    print("=" * 72)
    print(f"live: OUTCOME={outcome} reason={reason}")
    print(f"live: loops={loop_i} elapsed_min={result['elapsed_min']:.1f} "
          f"final_trunk_tip={final_tip}")
    print(f"live: orphans_at_exit={orphans} (hard-killed: {escalated_kills})")
    if outcome == "session_end" and escalated_kills:
        # ADR-0006 R2e (WARNING, not a verdict REJECT): a clean session_end should
        # release every worker gracefully — a hard-kill here is a shutdown-cleanliness
        # signal worth an eyeball (possibly a >10s claude SIGTERM latency, possibly an
        # ignored release), surfaced but never auto-failing the run.
        print(f"live: ⚠ R2e WARNING — clean session_end still needed a hard-kill: "
              f"{escalated_kills} (verify: mid-turn SIGTERM latency vs ignored release)")
    print(f"live: cases={list(result['cases'].keys())} "
          f"pages={list(result['operator_pages'].keys())} "
          f"escalations={len(result['escalations'])}")
    if operator_proxy:
        print(f"live: operator-proxy settled {proxy_settled} operator case(s) "
              f"(moderate-tier LLM stand-in)")
    if result["abandoned_blocks"]:
        print(f"live: ⚠ abandoned blocks: {result['abandoned_blocks']} — app NOT built to "
              f"the fullest (ADR-0007 §7: any abandoned block is a REJECT)")
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
    ap.add_argument("--expect-pages", type=int, default=0, dest="expect_pages",
                    help="R3-ACCEPT escalation fidelity: how many operator pages a "
                        "CLEAN run of this SIM should have produced — 0 for a trivial "
                        "SIM (any page is a spurious escalation = FAIL), or the count "
                        "of planted walls for a moderate SIM (each must reach the "
                        "operator AND be settled). The acceptance gate FAILS on a "
                        "dangling open case or a distinct-escalation-count mismatch, so "
                        "a hollow 'session_end' that swallowed or dropped a planted wall "
                        "can never be reported clean.")
    ap.add_argument("--expect-signature", default=None, dest="expect_signature",
                    help="R3-ACCEPT: a moderate SIM's planted-wall marker string; at "
                        "least one operator page must carry it, so a swallowed planted "
                        "wall masked by an unrelated escalation of the same count fails.")
    ap.add_argument("--operator-proxy", action="store_true", dest="operator_proxy",
                    help="MODERATE tier (ADR-0007): stand an LLM in for the operator — "
                        "each escalated operator-owned case is decided by a one-shot "
                        "claude call (resume/amend/abandon), injected via the real "
                        "settle path. OFF by default: a COMPLEX SIM omits this and its "
                        "pages reach the real human — NEVER enable it for a complex run.")
    return ap


def _acceptance_verdict(result, expect_pages=0, expect_signature=None):
    """R3-ACCEPT (ADR-0005) — escalation-fidelity acceptance gate. A clean pass is
    NOT merely `session_end and not orphans` (which proves nothing about whether a
    planted wall reached the operator — the false-green vehicle). It additionally
    requires:
      • outcome == session_end and no orphan processes;
      • NO dangling open case (every `manifest["cases"]` entry settled, decision set)
        — R3's terminal fidelity, re-asserted here defensively;
      • the number of DISTINCT operator escalations matches `expect_pages` exactly —
        0 for a trivial SIM (a spurious escalation is a defect), or the planted-wall
        count for a moderate SIM (a swallowed/dropped wall shows up as a shortfall).
        NB: `manifest["operator_pages"]` accumulates one entry per page DELIVERY
        ATTEMPT — THE FLOOR (`casestate.reping`) re-pages an unsettled case every
        tick, and no `_deliver_page` hook is wired in a live host-cli run, so a single
        genuine escalation produces MANY page entries before the proxy settles it.
        Counting raw entries would false-REJECT every clean run; we count distinct
        escalated `case_id`s instead.
      • if `expect_signature` is given (a moderate SIM's planted-wall marker), at least
        one page must carry it in its detail — so a swallowed planted wall masked by an
        unrelated escalation of the same count cannot pass.
      • NO abandoned block (ADR-0007 §7) — the app must be built to the FULLEST. `session_end`
        only proves every NON-abandoned in-scope block reached `done`; an operator/proxy
        `abandon` drops a block from must-reach-done, so a valid `abandon` could otherwise
        reach a clean `session_end` without the block ever being built. A SIM passes only
        when EVERY block reaches done — `manifest["abandoned_blocks"]` must be empty.
    Returns (ok, reasons[])."""
    reasons = []
    if result.get("outcome") != "session_end":
        reasons.append(f"outcome={result.get('outcome')!r} (not a clean session_end)")
    if result.get("orphans"):
        reasons.append(f"orphan processes at exit: {result.get('orphans')}")
    abandoned = result.get("abandoned_blocks") or []
    if abandoned:
        reasons.append(f"abandoned block(s): {abandoned} — the app was NOT built to the "
                       f"fullest (ADR-0007 §7). A SIM passes only when EVERY block reaches "
                       f"done; an operator/proxy `abandon` drops a block from must-reach-done, "
                       f"so a valid abandon can reach session_end without building the block.")
    open_cases = [cid for cid, c in (result.get("cases") or {}).items()
                  if c.get("decision") is None]
    if open_cases:
        reasons.append(f"dangling OPEN operator case(s) at end: {open_cases} "
                       f"(an escalation was never settled — R3 terminal fidelity)")
    # ADR-0008 — a case the engine PROVABLY self-resolved on trunk (a landing
    # worker.wall whose block closed out; `decision=="stale-resolved-on-trunk"`,
    # set only by casestate.reping's trunk-truth guard) is a transient the engine
    # retracted, not a standing escalation. Its historical page/escalation-log
    # entries stay on the durable append-only ledger (auditable), but they are
    # discounted from the GRADED counts below. Tightly scoped: an unbuilt block
    # is never `closed`, a genuine standing escalation is never so-decided, a
    # sentry/gate cap carries no matching `case`, an architect self-escalation is
    # not an `engineer-` worker — so this can mask no other page class.
    stale_resolved = {cid for cid, c in (result.get("cases") or {}).items()
                      if isinstance(c, dict) and c.get("decision") == "stale-resolved-on-trunk"}
    pages = result.get("operator_pages") or {}
    escalated_cases = {p.get("case_id") for p in pages.values()
                       if isinstance(p, dict) and p.get("case_id")
                       and p.get("case_id") not in stale_resolved}
    n_escalations = len(escalated_cases)
    if n_escalations != expect_pages:
        reasons.append(f"distinct operator escalations {n_escalations} != expected "
                       f"{expect_pages} (a planted wall was swallowed/dropped, or a "
                       f"spurious escalation fired): cases={sorted(escalated_cases)}")
    if expect_signature is not None:
        carrying = [pid for pid, p in pages.items()
                    if isinstance(p, dict) and expect_signature in str(p.get("detail") or "")]
        if not carrying:
            reasons.append(f"no operator page carried the planted-wall signature "
                           f"{expect_signature!r} — the planted escalation never reached "
                           f"the operator (swallowed), even if the count matched")
    # ADR-0006 R2d: the deterministic escalation LOG must be empty for a trivial
    # SIM. `manifest["escalations"]` records every sentry gate-idle cap / channel
    # escalation — durable OS/engine state the page/case surface can MISS (a cap
    # the architect later resolved benignly leaves no page and no open case, yet a
    # gate demonstrably stalled to a cap). Only asserted for a trivial SIM
    # (`expect_pages==0`, where zero is the honest expectation); a moderate SIM's
    # planted walls legitimately populate it. Sound now that R1a/R1e make pacing
    # working-aware (a long-but-live turn no longer spuriously caps).
    # ADR-0008 — discount the channel-escalation record of a stale-resolved case
    # (a paging-retry cap on a landing wall the engine self-resolved on trunk;
    # keyed by `case`). A sentry/gate cap carries no matching `case`, so every
    # genuine gate/worker stall still counts.
    escalations = [e for e in (result.get("escalations") or [])
                   if not (isinstance(e, dict) and e.get("case") in stale_resolved)]
    if expect_pages == 0 and escalations:
        kinds = sorted({(e.get("stage") or e.get("kind") or "?")
                        for e in escalations if isinstance(e, dict)})
        reasons.append(f"{len(escalations)} sentry/channel escalation(s) recorded "
                       f"(kinds={kinds}) — a gate/worker stalled to a cap even if no page "
                       f"survived on the case surface; a trivial SIM must have zero "
                       f"(R2d honest escalation log)")
    # ADR-0006 R2e is a WARNING, NOT a hard REJECT (ADR §7: a worker legitimately
    # mid-turn at teardown can only exit once its `claude` child dies from the group
    # SIGTERM; if that real CLI-shutdown latency exceeds the 10s graceful window it
    # is SIGKILLed — being killed mid-turn is architecture, not "ignored release" —
    # so a hard conjunct here would false-REJECT a clean run). `escalated_kills` is
    # surfaced prominently by `run_live`'s own output (a clean session_end that
    # needed a hard-kill is flagged ⚠ there); it never fails the verdict on its own.
    # Upgrade path (deferred): exempt only a provably-`working`-at-teardown actor and
    # REJECT a non-working one — needs `teardown` to record each kill's state.
    return (not reasons), reasons


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
                          scope=args.scope, adapter=args.adapter,
                          operator_proxy=args.operator_proxy)
    except LiveRunError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    # exit 0 only on a clean session-end with no orphan AND full escalation fidelity
    # (R3-ACCEPT): no dangling open case + the expected operator-page count. A bare
    # `session_end and not orphans` gate could report a hollow run — one that swallowed
    # or dropped a planted wall — as clean; this cannot.
    ok, reasons = _acceptance_verdict(result, expect_pages=args.expect_pages,
                                      expect_signature=args.expect_signature)
    if ok:
        print(f"live: ACCEPT — clean session-end, no orphans, escalation fidelity OK "
              f"(pages={len(result.get('operator_pages') or {})}=={args.expect_pages}, "
              f"no dangling case)")
    else:
        print(f"live: REJECT — " + " ; ".join(reasons))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
