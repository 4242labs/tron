# TRON Modes

A **mode** is a persona TRON can be booted as. Each mode is one self-contained directory: the agent
doc, its skills, and whatever state it owns.

| Mode | Boot | What it is |
|:--|:--|:--|
| [`flynn/`](flynn/) | `/tron-flynn` | **Advisor.** Workflow health, process audit, canon custody, agent design, project upgrade. Reports; the operator decides. |
| [`clu/`](clu/) | `/tron-clu` | **Supervisor.** Runs a fleet of worker agents against a project's pipeline — dispatch, gates, merge, escalation. |
| [`scaffold/`](scaffold/) | `/tron-scaffold` | **Scaffold.** Stands a new project up on the canon kit — profile, two wired repos, CI, hooks, services. New projects only. |
| [`alfredo/`](alfredo/) | `/tron-alfredo` | **Generalist.** Ad-hoc engineering, debugging, everyday architecture, research, review. Advises *and* acts. One session, one task. |

Planned: **NEW** (scope a project from zero, before it's stood up) and **AUDIT** (bring an existing
project up to standard — currently FLYNN's) — see the TRON operating-modes card.

## Which one

| The work is… | Mode |
|:--|:--|
| ad-hoc, finishable this session, whatever the domain | ALFREDO |
| a deep call on agent design, RAG, architecture, canon, or process health | FLYNN |
| a pipeline of blocks needing a fleet, gates, and merges | CLU |
| a project that does not exist yet | SCAFFOLD |

ALFREDO is the default when the work doesn't fit the other three. He is the only mode that both
advises and executes; FLYNN reports and waits, CLU dispatches and never touches the code.

## The law — one source of truth

Everything true of *every* mode lives once, in [`shared/`](shared/). A mode doc says only what makes
that mode **different**; the shared layer says what makes them all TRON. Every mode reads it at boot,
before its own persona doc, and when the two disagree the shared layer wins.

| File | Holds |
|:--|:--|
| [`shared/tron.md`](shared/tron.md) | **The law.** Verify before you assert · escalate never guess · the operator clicks every merge · own the mistake first · never present a menu · never touch the runtime · least privilege by role · working on another machine. |
| [`shared/skill-voice.md`](shared/skill-voice.md) | The voice — register, hard limits, the fixed closer. Each mode keeps only its own situational palette beside its skills. |
| [`shared/skill-operator-comms.md`](shared/skill-operator-comms.md) | The communication contract — ANSWER / ACT / FLAG / FYI, one type per reply. Governs every operator-facing channel. |
| [`shared/skill-branching.md`](shared/skill-branching.md) | Worktree paths, branch names, and the session-end commit → push → land → clean-up protocol. Each mode contributes only its slug. |

Change a rule there, and all four modes change with it. **Never fork it into a mode.**

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
with the mode's absolute path baked in, and the `tron-flynn` / `tron-clu` / `tron-scaffold` /
`tron-alfredo` terminal shortcuts get wired onto your PATH. Re-running is safe. `install.sh <project>`
scopes the commands to a single project instead of the machine; `--no-path` skips the shell-rc line.

The command files and one PATH line are the **only** things written. No pointer files, no
environment variables, no other machine state. Secrets (CLU's Telegram token) live in the
gitignored `.env` at the tron-app repo root — never outside the project.

```zsh
tron-flynn "audit this project"       # → claude "/tron-flynn audit this project"
tron-clu                              # → claude "/tron-clu"
tron-scaffold                         # → claude "/tron-scaffold"
tron-alfredo "the build broke"        # → claude "/tron-alfredo the build broke"
```
