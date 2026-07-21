# Getting started

How to install and run TRON. For what it is and how it works, see [`README.md`](README.md).

## Requirements

- `python3` and `git`.
- A background-capable agent runtime on `PATH` — it runs the worker agents TRON dispatches. TRON drives
  it; you never address it directly.
- Complete agent personas + the skills they reference in your project. TRON's worker prompts are deltas
  over your project's personas, so every persona and every skill it points at must be present before you
  run against real work.
- Optional: a Telegram bot (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` in a gitignored `.env`) so milestone
  notes and operator pages ride Telegram. Without it, everything degrades to the terminal.

## Run

```bash
# From a clone:
./tron start                 # wake TRON: a short bootup (where to start, how many
                             #   workers), then the live console — watch the fleet,
                             #   talk to TRON, `stop` when done
./tron start <project>       # point it at a project path directly
./tron --watch               # long-running: idles, wakes on register work, STOP file exits
./tron --selftest            # engine selftests — no agents, no tokens
```

Inside the console: type to talk to TRON; `status` / `pipeline` to look; `stop` to end.

## Validate the engine

Every module ships runnable selftests (no agents, no tokens):

```bash
python3 engine/tron.py --selftest      # the engine
python3 engine/gate.py                 # the truth gate (real throwaway git repos)
python3 engine/glossary.py             # vocabulary doc-sync   (--write regenerates docs/GLOSSARY.md)
python3 engine/events.py               # event-vocabulary sync (--write regenerates docs/EVENTS.md)
python3 engine/workflow.py             # flow lint + doc-sync  (--write regenerates docs/WORKFLOW.md)
python3 engine/bpmn.py                 # BPMN doc-sync         (--write regenerates workflow/)
python3 evaluation/harness.py --selftest
```

The full suite also runs in CI on every push (`.github/workflows/engine-ci.yml`).

## Simulate a run

The `evaluation/` suite exercises the whole engine end-to-end against seeded projects:

```bash
python3 evaluation/harness.py project-01 3   # 3 SIMs of PROJECT-01; writes a stats.md
#   --parallel N   seed a project-owned flow with [limits] max_parallel = N
#   --ablate ARM   run with ONE invariant disabled (truth_gate | judge_isolation | architect_first)
```

Templates live in `evaluation/templates/` (`project-01/02/03` small→large, `project-04` scale rung,
`exp-*` fixtures). Run outputs are written under `evaluation/` and are gitignored.

## File layout

```
tron/
├── tron                # launcher
├── engine/             # the deterministic engine + workflow.toml + prompts/
├── docs/               # GENERATED reference (GLOSSARY · EVENTS · WORKFLOW) + voice.md
├── workflow/           # GENERATED interactive BPMN diagram
└── evaluation/         # the SIM validation suite (harness + templates)
```

A project you point TRON at brings its own committed core docs — `context.md`, `principles.md`,
`playbook.md`, an optional own `workflow.toml`, `policy.md`, `blocks/*.md`, and the engine-written
`pipeline.md` register. TRON reads the project's pipeline; it owns no pipeline and no agents of its own.
