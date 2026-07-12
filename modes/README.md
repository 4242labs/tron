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
modes/install.sh              # /tron-flynn + /tron-clu in every project
modes/install.sh ~/path/proj  # scoped to one project (<project>/.claude/commands/)
```

The command file — with the mode's absolute path baked in — is the **only** thing written. No
pointer files, no environment variables, no machine-level state of ours. Secrets (the Telegram bot
token) live in the gitignored `.env` at the tron-app repo root, never outside the project.

Terminal shortcuts, one line in your shell rc:

```zsh
export PATH="<tron-app>/modes/bin:$PATH"

tron-flynn "audit this project"   # → claude "/tron-flynn audit this project"
tron-clu                          # → claude "/tron-clu"
```
