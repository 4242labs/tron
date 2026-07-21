# Getting started

How to install and run TRON. For what it is and how it works, see [`README.md`](README.md).

## Install

```bash
curl -fsSL https://tron.42labs.io/seed.sh | sh
```

That clones TRON into `~/.tron` and symlinks the `tron` launcher into `~/.local/bin`, so you can
run `tron` from anywhere. It's idempotent — re-run it any time to update to the latest. It never
edits your shell rc and never uses `sudo`; if `~/.local/bin` isn't on your `PATH`, it prints the one
line to add. Pin a version with `... | TRON_REF=v0.4.2 sh`; override `TRON_HOME` / `TRON_BIN` to
relocate. The script is [`install.sh`](install.sh) at the repo root — the URL just redirects to it.

Prefer to do it by hand? `git clone https://github.com/4242labs/tron && cd tron && ./tron start`.

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
# Installed on PATH (via the one-liner above); from a clone, use ./tron instead.
tron start                   # run TRON on this repo: a short bootup (where to start,
                             #   how many workers), then it dispatches the fleet and
                             #   drives the pipeline to done, printing milestones
tron start <project>         # point it at a project path directly
tron --watch                 # long-running: after the pipeline is complete it idles,
                             #   wakes on new register work; a STOP file in the project exits
tron --selftest              # engine selftests — no agents, no tokens
```

TRON runs autonomously — it isn't a chat REPL. It prints **milestone** notes as blocks land, and
**pages** you (terminal `OPERATOR>` prompt, or Telegram if configured) only when it needs a decision.
You reach TRON by dropping a file in the project root: **`parley.md`** (a question or instruction — the
architect answers, recorded under `parley/`) or **`report-request.md`** (the architect writes a status
report, recorded under `reports/`). Under `--watch`, a **`STOP`** file ends the run.

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
