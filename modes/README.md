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

## Terminal shortcuts

Each mode boots from a slash command, and each slash command has a shell shortcut (see the mode's
`install/README.md`):

```zsh
tron-flynn "audit this project"   # → claude "/tron-flynn audit this project"
tron-clu                          # → claude "/tron-clu"
```
