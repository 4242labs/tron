# tron-reborn — roadmap rulings

**0.4.2 is RESERVED — the operator alone declares it, never before an
explicit approval** (operator ruling 260716). Current version: **v0.0.30**
(tag) — the 0.4.2 *candidate*: selftests green across all suites, every
generated doc in sync, three SIM levels validated live (PROJECT-01,
PROJECT-02 @2+@4 workers, PROJECT-03 — templates renamed from
mini/contention/triage, 260717), ablation arms + the frozen bootup journey
live-proven.

**Campaign COMPLETE (260717):** 70/74 clean, 0 false completions; two causal
supplements landed — Exp A false-done testbed (5/5 seeded shortcuts rejected)
+ Exp B trunk-only fixture (`sims/EXPERIMENTS.md`); PROJECT-04 scale rung
**5/5 CLEAN** (15-block / 7-layer / 2-diamond KV store — paper §15 scale
result); crash-resume VALIDATED across **four live trials** (T1–T4,
`sims/crash-resume.md`). Runs complete. Remaining: paper assembly finished
(§8 four-trial, §15 scale) — awaits operator review + gated decisions.
Everything below is explicitly OUT of 0.4.2, documented here so it is not lost.

## Post-0.4.2 (ruled out of the first official version, 260716)

- **Cost ledger** — capture per-turn token/cost at the one
  `agents.turn()` chokepoint (the CLI's JSON output reports usage);
  engine-recorded per seat/block/run like every other document. Phase 2:
  a `[limits] block_budget` routing over-spend through the existing
  wall chain. No proxy, no gateway — zero new moving parts.
- **BPMN publish sync** — the tron-www auto-deploy hook for
  `workflow/` (mirror of tron-app's `publish-diagram.yml`, same
  cross-repo token). The diagram itself ships generated + committed;
  only the publishing lands at 0.4.2.

## Set aside earlier (operator, 260716) — not scheduled

- Architect block-intake (goal → block files).
- Project scaffold/init.
- Bootup journey (frozen journey, AIDE-as-LLM — needs operator input).

## Growth discipline

- Parallelism grows in steps (2 → 4 …), never a jump to full fleet;
  each step is a proven SIM before the next.

## The paper plan (ruled 260716)

- **Order:** finish every ≤0.4.2 feature and validate the system on at
  least THREE SIM levels (L1 trivial ledger/mini — done; L2 contention:
  multi-block + deps, stepwise workers; L3 a non-trivial project) —
  ONLY THEN start paper-focused runs.
- **Sample sizes (agreed):** ~30 runs for the main configuration, ~30
  per parallelism step, ~10 per ablation arm (~3 arms) — ≈90 runs total;
  rule-of-three bounds the zero-failure claims, large effect sizes carry
  the ablations.
- **Apparatus (built, live-proven v0.0.23–24):** typed events.jsonl per
  run + harness batches aggregating stats from events alone; verbatim
  prose transcripts ride along for debugging, never for measurement.
- **Validation bar MET (260716 night):** L1 mini 2/2, L2 contention 2/2
  @2 AND 2/2 @4 workers (3-wide dispatch proven), L3 triage 2/2 (8-block
  depth-5 graph, delivered app live-probed correct).
- **Ablation arms (v0.0.26):** `TRON_ABLATE` engine switch (deliberately
  NOT workflow.toml — the lint refuses invariant edits); closed arm
  vocabulary `truth_gate` / `judge_isolation` / `architect_first`, one
  invariant disabled per arm, loud at boot, recorded in run_start;
  `harness.py --ablate ARM` is the batch instrument.
- **LangGraph ruled out** (260716): its offers (graph orchestration,
  checkpointing, human-in-the-loop) duplicate workflow.toml + arenas +
  walls in-process instead of as observable git facts; adopting it would
  surrender the paper's own thesis. Watch, don't adopt.
