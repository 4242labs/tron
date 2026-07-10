# `core/` — the rewritten TRON engine control plane (ADR-0004)

Clean-room replacement for the 6087-line god-object `engine/fsm.py`. Small, single-responsibility
modules; every behavior proven on a **real-git** rig (real `git` + real `meta/scripts/land.sh`, no
faked trunk). Reuses the sane substrate (`engine/{trunk,grants,eventlog,ctx,jobs,roles,reader}.py`)
through **one** git-observation seam (`gitobs.py`) — the only `core/` module that imports `trunk`.

Design record: `tron-meta` `logs/architecture/adr-0004-engine-rewrite.md` + `log-260710-engine-rewrite-waves.md`.

## Module map

| Module | Responsibility |
|---|---|
| `landing.py` | The ONE landing primitive — mint→order→observe→consume, **content-bound case identity** (case-id embeds the patch-id, so a stale receipt can never mask unlanded content — the confirmed root). Reuses `engine/grants.py` + `land.sh`. |
| `gitobs.py` | The single git-observation seam. All `core/` git/test reads go through here; the one documented bridge to `engine/trunk.py` + `engine/reader.py`. No other control module does raw git. |
| `gate.py` | The DONE ladder as a PURE predicate-driven state machine: `gate.local → gate.merge → gate.trunk → gate.record → close`. Honest distinct outcome per tick; never self-caps, never a silent hang. Merge = land the feature branch; trunk = declared test on the merged sha; record = ✅ status commit (one file, Status only); close = release only on `replica_clean`. |
| `state.py` | The MANIFEST store — atomic (`*.tmp`→`os.replace`) durable run-state. The only writer of `manifest.yaml`. |
| `snapshot.py` | The immutable per-tick view — fresh manifest load + persist-gated inbox drain + trunk read. `decide` reads only the snapshot. |
| `tick.py` | The bounded crash-safe loop: `observe → route → drive gates → switchboard.fill → sentry.pace → persist (atomic, after the whole pass)`. A crash before persist re-runs safely (every mutation re-derivable from real git/grants). |
| `pipeline.py` | Deterministic pipeline/blocks reader — `dispatchable()` = 📋 + deps ✅ on trunk + not in-flight + reconcile-gate cleared. |
| `switchboard.py` | SPAWN half — deterministic agent-id recorded **before** the (stubbed) process spawn (crash-window closed), state-guarded (no double-dispatch). |
| `router.py` | Structured-report routing (no LLM yet): `worker.online`/`worker.branch` → ASSIGN (open `gate.local` on the reported branch); `worker.wall` → open case; `operator.decision` → settle; `architect.reconciled` → clear reconcile-gate. |
| `session.py` | Fail-loud session-end terminal — a clean marker only when every in-scope block is done + nothing in-flight; `RuntimeError` on a genuinely stuck state (never a silent "end"). |
| `sentry.py` | ONE pacing ladder for every gate stage — nudge at `gate_nudge_after`, escalate at `gate_idle_cap`; progress resets pacing. The only place capping lives. |
| `casestate.py` | Parked-case FSM — raise-and-defer (wall/escalation → parked case, block blocked, slot freed) + operator `resume`/`amend`/`abandon` settle ≤1 tick. |
| `architect.py` | Persistent, pool-excluded architect — FIFO queue with `forward` (author a missing block file) + `reconcile` (M-05 gate the next block). *(in progress)* |

## Running the rigs (deterministic, ~0 tokens)

```bash
cd tron-app/.worktrees/l1-harness-landing-fix/core
for r in landing gate gate_full tick dispatch multiblock sentry casestate; do python3 ${r}_rig.py; done
```
Each prints `PASS (n/m)` and drives real git + real `land.sh`. A rig is the WAKE daemon + the
worker(s): it calls `tick.tick(eng)` in a loop and, when the engine orders work/land/close, does the
real git and runs `land.sh` itself — faking the worker *process*, never the trunk.

## Build order (no-false-green discipline, ADR §6/§11)

L0 property tests → **L1 real-git seam rigs** (these) → L2 rigged mockup-project SIM (transcript-replay
workers) → L3 full-LLM graded SIM = the 100% assertive acceptance. Landing/identity seam is
L1-proven before the tick/gate that drives it; classify stays stubbed until L3; L2 is gated behind all
L1 greens; the L2/L3 worker surface is calibrated against real-agent transcripts so it can't
false-green.
