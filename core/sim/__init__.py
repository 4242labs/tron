"""core.sim — the fresh, unbiased L2 SIM harness (ADR-0004 §11.5; rewrite
wave 14). Boots `core.engine.Engine` over a FRESH real-git mockup project
(seeded from `templates/project-scaffold`, never the old, design-biased
`tron-meta/sims/` harness) and drives a full session to a clean end with
SCRIPTED workers (transcript-replay-ready) — real git surface throughout,
NO real worker processes, NO LLM. The pre-L3 gate: L3 swaps scripted->real
workers onto this SAME driver (`run_sim`).

  `scaffold.py`  — builds the fresh real-git mockup (a tiny real app +
                  `meta/` seeded from `templates/project-scaffold`).
  `worker.py`    — the scripted worker/architect/reviewer driver (a
                  `Transcript` seam a future recorded transcript replays
                  through unchanged).
  `run.py`       — `run_sim(...)`, the reusable L2 driver: seed -> Engine.
                  start -> loop Engine.tick playing the scripted workers ->
                  session-end (or the tick cap) -> a structured result.
  `sim_l2_rig.py`— the graded proof: a realistic mockup (a real declared
                  test command) driven to a clean session-end, PLUS a
                  failing-test variant (gate.trunk holds -> sentry escalates
                  -> a parked case).

Purely additive: nothing here modifies `engine/*.py`, `land.sh`, any
contract, or any existing `core/*.py` module's behavior.
"""
