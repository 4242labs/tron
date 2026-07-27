# Paper — data, code, and evidence

This directory is the companion archive for the paper:

> **Demoting the Master Control Program: Deterministic Orchestration of a Fleet of LLM Agents**
> Ânderson Q. · 42labs · *preprint* · Zenodo: [10.5281/zenodo.21613792](https://doi.org/10.5281/zenodo.21613792)

TRON is the deterministic finite-state orchestrator the paper describes; its full
engine lives at the root of this repository. For concepts, installation, and how
to run TRON on your own project, see the [wiki](https://github.com/4242labs/tron/wiki).

## What's here

| Path | Contents |
|:--|:--|
| `demoting-the-mcp.pdf` | The preprint (rendered). |
| `PAPER.md` | The paper source (Markdown; diagrams render on GitHub). |
| `evidence/EXPERIMENTS.md` | Index of the by-construction false-done fixtures (Experiments A/B) and how they map to the engine's gate stages. |
| `evidence/ablation-analysis.md` | Event-level ablation findings (`truth_gate` / `judge_isolation` / `architect_first` arms). |
| `evidence/crash-resume.md` | The four live crash-and-resume trials. |
| `evidence/mit-6.5840-mapreduce/` | Third-party-oracle probe 1 — MIT 6.5840 Lab 1. Engine decision log (`events.jsonl`), run report, manifest, provenance, and the pre-run scaffold. |
| `evidence/mit-6.5840-raft/` | Third-party-oracle probe 2 — MIT 6.5840 Lab 3 (Raft), blocks 01–04. Same set. |

The typed `events.jsonl` traces are the engine-emitted ground truth (the sole
source of truth in the paper's accounting); the run reports are engine-written.
All traces are path- and user-scrubbed.

## Reproducibility

The archive is for **inspection and audit, not re-execution**. Worker and judge
steps are stochastic LLM calls, so a re-run does not reproduce a trace
byte-for-byte; the *published record* is the evidence.

Two things here **are** directly runnable against the current engine:

- **The false-done fixtures** — the seeded shortcut templates the paper reports as
  6/6 rejected live under [`evaluation/templates/`](../evaluation/templates)
  (`exp-a1`…`exp-a5`, `exp-b-trunkonly`) and run through the engine's own gate.
- **The third-party probes** — each MIT scaffold under `scaffold-pre-run/` can be
  re-set-up against the course's own starter (fetch MIT's `6.5840` starter, apply
  the scaffold, run TRON; the gate is MIT's unmodified `go test` suite).

The reported campaign ran on an earlier pin of this engine — a predecessor
version line since evolved into the maintained public build in this repository.

## Withheld

The MIT lab **solutions** are not published: the course prohibits posting lab
solutions, and the starter code is MIT's copyright. Only our authored scaffold and
the engine's decision logs are included here. The benchmarks themselves are public
and citable — see each probe's `PROVENANCE.md`.

## Citing

```bibtex
@misc{quadros_tron_2026,
  title     = {Demoting the Master Control Program: Deterministic Orchestration of a Fleet of LLM Agents},
  author    = {Quadros, {\^A}nderson},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.21613792},
  note      = {Preprint},
  url       = {https://doi.org/10.5281/zenodo.21613792}
}
```
