# project.md — Example

TRON's own config record for one project. It lives inside TRON's folder (`<agents>/tron/project.md`) and the host never owns it. The seeder builds it by **detecting** what it can, **asking** for the rest, and documenting the result. TRON re-reads it on every session start.

`<agents>` = the directory where the project's worker agent definitions live; TRON installs itself there too (`<agents>/tron.md` + `<agents>/tron/`). It's project-specific and arbitrary — never hardcode it. `<specs>` = where the spec files live.

The example below uses a fictional project (`acme-widgets`) for illustration only.

---

## Pointers

The two locations TRON must know. These are the heart of the config — everything else is detail.

| Pointer | What it is | Example |
|:--|:--|:--|
| **Agents path** (`<agents>`) | Where the worker agent definitions live. TRON dispatches from here and installs itself here. | `meta/agents/` |
| **Specs path** (`<specs>`) | Where the host keeps its spec files (local MD). TRON reads these to cut blocks. | `specs/` |

**Specs read-contract:** specs carry the fields in `spec.example.md` (ID, goal, acceptance criteria, scope, dependencies, owner). Note any project-specific reading rule here.

**Pipeline ledger:** the status + sequence record (see `pipeline.example.md`).

```
pipeline: host            # host keeps its own pipeline doc — TRON uses it as the live ledger
pipeline_path: PIPELINE.md
# --- or ---
pipeline: internal        # host had none — ledger lives at <agents>/tron/pipeline.md
```

## Agents available

The roles found at the agents path, and the subset the workflow uses. The seeder enumerates the files present and validates `workflow.md` only references roles that exist — it does **not** create agent files.

```
agents:
  - architect: meta/agents/architect.md
  - engineer:  meta/agents/engineer.md
  - reviewer:  meta/agents/reviewer.md
```

A project may have a subset (e.g. no reviewer) or custom roles (e.g. `designer`). If `workflow.md` references a role not found here, the seeder stops and asks the operator to add the agent or trim the rule.

## Workflow doc

- Workflow rules: `<agents>/tron/workflow.md`
- Live counters (TRON-managed): `<agents>/tron/workflow-state.md`

---

## Detected repo facts

Auto-detected; the seeder shows a summary ("looks right?") and prompts only for what it can't resolve. They matter only to workflows that use them (e.g. the default git workflow).

| Field | Detected from | Example |
|:--|:--|:--|
| Name | repo dir name | `acme-widgets` |
| Repo root | `git rev-parse --show-toplevel` | `~/code/acme-widgets` |
| Main branch | `git symbolic-ref refs/remotes/origin/HEAD` | `main` |
| GitHub org/repo | `git remote get-url origin` | `acme/widgets` |
| Worktrees dir | check `.worktrees/`, else default | `.worktrees/` |
| Logs dir | check, else default | `meta/logs/` |

## Conventions

Project-specific patterns TRON's spawn scripts read rather than hardcoding.

- **Branch naming:** `chore/<slug>-YYMMDD`; `feat/<slug>-YYMMDD`.
- **Block ID pattern:** `block-MM-DD-<slug>`.
- **Worker ID pattern:** `<ROLE>-<block-stripped>` (e.g. `ENG-06-19`).
- **Commit convention:** present-tense, lowercase, scope prefix.
- **PR title:** under 70 chars; body has Summary + Test plan.

## Env keys

Stored in `<agents>/tron/.env` (encapsulated with TRON, gitignored). TRON reads via shell scripts, never inlines values into prompts.

| Key | Required? | Used for |
|:--|:--|:--|
| `TELEGRAM_BOT_TOKEN` | optional | operator escalation channel |
| `TELEGRAM_CHAT_ID` | optional | operator's chat |
| `GITHUB_TOKEN` | optional | `gh` CLI (or `gh auth login`) |

**Telegram is optional.** If unconfigured, escalations surface in the operator's next session rather than via push.

## Notifications + heartbeat

Config the seeder and TRON **follow without asking**. Edit here to change behavior.

```
telegram: off    # off | on   (on routes escalations via Telegram; keys go in .env; implies heartbeat on)
cron: auto       # auto | on | off   (auto = on whenever telegram is on; force on for stall-sweeps without TG)
```

Effective heartbeat = `telegram == on` OR `cron == on`. The heartbeat (cron) is what polls Telegram and runs stall-sweeps — so Telegram can't work without it, hence the coupling.

## Protected branches

Used only by workflows that commit (e.g. the default git workflow). Branches no agent — TRON included — may commit to directly; work flows through a feature branch + PR (see `workflow.md` R8).

```
protected_branches:
  - <repo-name>: <branch>   # e.g. acme-widgets: main
```

---

## Operator-only tasks

Tasks engineers must NOT attempt — TRON escalates these directly without dispatching.

- DNS / domain configuration
- Third-party dashboard configuration (Stripe, Vercel, Auth0, …)
- Production billing / paid plan changes
- Anything requiring physical access

## Local-validation gaps

Tasks engineers perform but cannot fully verify alone. TRON flags these for manual operator testing.

- Mobile builds (device install)
- Live integration tests with paid third-party services
- End-to-end flows requiring a real account

## CI behavior

- Runner / typical duration / any stall-threshold override.

## Deploy flow

- Trigger / target / preview URL / what TRON monitors past merge.

## Other notes

Free-form context TRON should know but doesn't act on programmatically (monorepo boundaries, migration rules, …).

---

**Editing this file:** safe to hand-edit; TRON re-reads on session start. To change knobs TRON also tracks live (workflow rules, counters), describe the change to TRON — it owns those edits to keep dependent docs in sync.
