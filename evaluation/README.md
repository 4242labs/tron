# evaluation/ — the SIM validation suite

The empirical harness that validates the engine end-to-end, isolated from the
product code it exercises.

- `harness.py` — batch runner. Seeds a fresh git repo per SIM from a template,
  runs the engine (`../tron.py`) against it, collects the typed `events.jsonl`,
  and scores each run CLEAN / walled / paged. `python3 evaluation/harness.py
  --selftest` runs its self-checks against fake engines (no agents, no tokens).
- `templates/` — the SIM scaffold. `project-01/02/03` are the canonical rungs
  (small → large); `project-04` is the long-horizon scale rung; `exp-*` are the
  causal falsification fixtures. Each template is orchestrator-agnostic.

Run outputs (`runs/`, `sims/`) are runtime-generated and gitignored. The
campaign's historical run data lives in the `tron-meta` repo; the paper's cited
proof is curated under `../paper/evidence/`.
