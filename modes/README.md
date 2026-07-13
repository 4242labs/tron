# TRON Modes

A **mode** is a persona TRON can be booted as. Each mode is one self-contained directory: the agent
doc, its skills, and whatever state it owns.

| Mode | Boot | What it is |
|:--|:--|:--|
| [`flynn/`](flynn/) | `/tron-flynn` | **Advisor.** Workflow health, process audit, canon custody, agent design, project scaffold/upgrade. Reports; the operator decides. |
| [`clu/`](clu/) | `/tron-clu` | **Supervisor.** Runs a fleet of worker agents against a project's pipeline — dispatch, gates, merge, escalation. |

Planned: **SCAFFOLD** (stand a project up to the canon scaffold) and **NEW** (scope a project from
zero) — see the TRON operating-modes card.

## Boundary

Modes are the **persona layer**: prose, skills, and prompts an LLM reads. They never touch
`engine/`, `core/`, or `contracts/` — the deterministic runtime — and the runtime never depends on
them. A mode can be deleted without breaking a TRON run.

## Install

```zsh
git clone https://github.com/4242labs/TRON.git tron-app
tron-app/modes/install.sh
```

That is the whole fresh-machine setup: the slash commands land in Claude's `commands/` directory
with the mode's absolute path baked in, and the `tron-flynn` / `tron-clu` terminal shortcuts get
wired onto your PATH. Re-running is safe. `install.sh <project>` scopes the commands to a single
project instead of the machine; `--no-path` skips the shell-rc line.

The command file and one PATH line are the **only** things written. No pointer files, no
environment variables, no other machine state. Secrets (CLU's Telegram token) live in the
gitignored `.env` at the tron-app repo root — never outside the project.

```zsh
tron-flynn "audit this project"   # → claude "/tron-flynn audit this project"
tron-clu                          # → claude "/tron-clu"
```
