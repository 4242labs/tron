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
| `gate.py` | The DONE ladder as a PURE predicate-driven state machine: `gate.local → gate.merge → gate.trunk → gate.record → close`. Honest distinct outcome per tick; never self-caps, never a silent hang. Merge = land the feature branch; trunk = declared test on the merged sha; record = block-doc completion commit (one file — the `**Status:**` flip plus the skill-prescribed `**Completed:**` date; code/other files still escalate) — its baseline is re-anchored at order time to the block doc's on-trunk last-toucher so an earlier block-doc-touching merge commit is never mistaken for the record (C4); close = **land the worker's session-end close-out paperwork via its own content-bound grant** (C1), then release only on `replica_clean`. |
| `state.py` | The MANIFEST store — atomic (`*.tmp`→`os.replace`) durable run-state. The only writer of `manifest.yaml`. |
| `snapshot.py` | The immutable per-tick view — fresh manifest load + persist-gated inbox drain + trunk read. `decide` reads only the snapshot. |
| `tick.py` | The bounded crash-safe loop: `observe → route → drive gates → switchboard.fill → sentry.pace → persist (atomic, after the whole pass)`. A crash before persist re-runs safely (every mutation re-derivable from real git/grants). |
| `pipeline.py` | Deterministic pipeline/blocks reader — `dispatchable()` = 📋 + deps ✅ on trunk + not in-flight + reconcile-gate cleared. |
| `switchboard.py` | SPAWN half — deterministic agent-id recorded **before** the (stubbed) process spawn (crash-window closed), state-guarded (no double-dispatch). |
| `router.py` | Structured-report routing (no LLM yet): `worker.online`/`worker.branch` → ASSIGN (open `gate.local` on the reported branch); `worker.wall` → open case; `operator.decision` → settle; `architect.reconciled` → clear reconcile-gate. |
| `session.py` | Fail-loud session-end terminal — a clean marker only when every in-scope block is done + nothing in-flight; `RuntimeError` on a genuinely stuck state (never a silent "end"). |
| `sentry.py` | ONE pacing ladder for every gate stage — nudge at `gate_nudge_after`, escalate at `gate_idle_cap`; progress resets pacing. The only place capping lives. |
| `casestate.py` | Parked-case FSM — raise-and-defer (wall/escalation → parked case, block blocked, slot freed) + operator `resume`/`amend`/`abandon` settle ≤1 tick. Wall kinds route **architect-first** (triage); only an architect `operator` verdict pages. Operator-page **floor**: an unanswered page re-pings, never a permanent silent drop. Fleet-outage self-release (systemic death → bounded pause → architect-first). |
| `architect.py` | Persistent, pool-excluded architect — FIFO queue with `forward` (author a missing block file) + `reconcile` (M-05 gate the next block) + `triage` (verdict on a wall) + `log` (review remediation). |
| `reviewers.py` | Cadence PULL — a landed-block counter reaches threshold → switchboard dispatches a reviewer (never auto-fired); DONE-REVIEW gate (first hand-back challenges full coverage → held → attest → release); a review is a milestone, its log-review becomes adhoc blocks (or none). |
| `liveness.py` | Timer side-system (not classify) — a worker silent past `silence_ping_min` → `heartbeat.ping`; past `silence_escalate_min` → engine-produced `worker.stalled` → recover (re-dispatch / parked case). A live worker is never pinged; a **`released`** worker (its block ✅-closed — the tick marks the slot released on close) is out of scope entirely, never stalled (C3). A worker whose runner is provably `working` re-anchors its liveness episode. |
| `engine.py` | The `Engine` entrypoint — assembles every module; `start(scope, worker_count, models)` (bootup: write manifest, spawn persistent architect, first dispatch) + `tick()`/`run()`. The whole engine runs bootup→done through here. |
| `classify.py` | The ONE LLM judgment, pinned to the **observe** phase so `decide` stays pure. Structured `tag`+`slots` reports bypass it (no model call); free-text → `judge.call` → tag → route; invalid → bounded retry → `unclassified` → architect triage. The only module that calls the model. |
| `knobs.py` | The fail-loud config seam — schema-nested reads (fields under the top-level `knobs:` map, per `contracts/schema/knobs.schema.yaml`); a missing knob raises `KnobsError`, never silently resolves to `None`. |
| `sim/` | SIM apparatus. **L2 (scripted, ~0 tokens):** `scaffold.py` (fresh mockup builder), `worker.py` (scripted worker+architect+reviewer driver), `run.py` (`run_sim`), `sim_l2_rig.py`, `boot_real_scaffold_rig.py`, `report_channel_rig.py` (report.sh→inbox→classify integration lock). **L3 (real-LLM):** `live.py` — the live runner (real wall-clock pacing, proactive PULSE + pid probes, the COURIER harvesting turn-output→inbox, SIGTERM→graceful-teardown 0-orphans); `boot_real_scaffold_rig.copy_real_scaffold` now materialises an **honest seed** (`scaffold_ref` app + HEAD `meta` via `git archive`; SEED-HONEST/SEED-PLAN gates) — never the answer-key working tree; `seed_canon.py` (installs messages/routing/prompts/report.sh into the instance); `real_tier.py` (real `jobs.spawn_runner`). Run: `python3 -m core.sim.live --adapter host-cli --workers 1 --budget-min 60 --poll-sec 20`. |

## Running the rigs (deterministic, ~0 tokens)

```bash
cd tron-app/.worktrees/l1-harness-landing-fix/core
for r in landing gate gate_full tick dispatch multiblock sentry casestate architect \
         reviewers liveness liveness_working sentry_working engine classify knobs \
         opfloor wallrouting outage trunkchurn archive_dep; do
  python3 ${r}_rig.py
done
python3 sim/sim_l2_rig.py           # L2 scripted full-workflow SIM (happy + adversarial)
python3 sim/boot_real_scaffold_rig.py   # real trivial-tip-converter scaffold boots through core.Engine
python3 sim/report_channel_rig.py   # report.sh -> inbox -> classify -> worker.done integration lock
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

**L3 acceptance NOT YET MET (corrected 2026-07-11).** The 2026-07-10 "L3 met" claim (T2-01-08) was
**hollow**: `boot_real_scaffold_rig.copy_real_scaffold` seeded the instance from the scaffold source
*working tree* (= HEAD answer key), so the worker validated pre-existing code rather than building it. The
engine loop ran for real; the worker-build half did not. The four close/record fixes from that campaign
(C1 close-out land, C2 archived-dep, C3 released-slot, C4 record-baseline; commits `6123ae5`/`4c9f48a`/
`e5b7177`) remain valid.

**Honest-seed campaign (2026-07-11, PR #128, branch `feat/sim-honest-seed`):** the seed is now
`scaffold_ref` app (unbuilt) + HEAD `meta` via `git archive`, gated by **SEED-HONEST/SEED-PLAN**. Eight
further root fixes — each tying a deterministic completion to *engine state*, not classify-parsed prose,
and making the architect unable to wall/triage/wedge itself — drove the engine to *all three blocks built +
closed + reviewed clean, 0 pages* from run `s3` on, but **0 fully-clean honest E2E in 7 launches**. Two
blockers remain: (A) a worker can carve its branch off the stale detached-HEAD seed instead of current
`main`, missing landed deps; (B) the phantom-grace backstop is `classify.unclassified`-only, so a real
block-less `worker.wall` the architect can't verdict wedges it. Write-up + full ledger:
`tron-meta/logs/architecture/log-260711-overnight-simple-sim-campaign.md`.
