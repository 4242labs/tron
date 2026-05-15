# project.md — Example

This is an illustrative example of a project profile. The seeder builds your project's own `meta/agents/tron/project.md` by **detecting** most fields from the local repo, **confirming** the summary with you, and **asking** only for what it can't determine. TRON re-reads this file on every session start.

The example below uses a fictional project (`acme-widgets`) for illustration only.

---

## Project

The seeder auto-detects most of these:

| Field | Auto-detected from | Example value |
|:--|:--|:--|
| Name | repo dir name | `acme-widgets` |
| Repo root | `git rev-parse --show-toplevel` | `~/code/acme-widgets` |
| Main branch | `git symbolic-ref refs/remotes/origin/HEAD` | `main` |
| GitHub org/repo | `git remote get-url origin` | `acme/widgets` |
| Worktrees dir | check `.worktrees/` exists, else default | `.worktrees/` |
| Logs dir | check `meta/logs/` exists, else default | `meta/logs/` |

The seeder shows a summary, asks "looks right?" — only prompts for fields it couldn't resolve.

## Conventions

Project-specific conventions. TRON's spawn scripts read patterns from here rather than hardcoding them, so each project can use its own ID schema.

- **Branch naming:** `chore/<slug>-YYMMDD` for chores; `feat/<slug>-YYMMDD` for features.
- **Block ID pattern:** `block-MM-DD-<slug>` (TRON uses `MM-DD` as the stripped form for worker IDs).
- **Worker ID pattern:** `<ROLE>-<block-stripped>` (e.g. `ENG-06-19`, `ARCH-06-19`, `REV-06-19`).
- **Commit convention:** present-tense, lowercase, scope prefix (`fix:`, `feat:`, `chore:`).
- **PR title:** under 70 chars; body has Summary + Test plan.

## Env keys

Stored in `meta/agents/tron/.env` (the TRON instance dir, gitignored via `meta/agents/tron/.gitignore`). The `.env` is encapsulated with TRON — not at the repo root — so deleting `meta/agents/tron/` and `meta/agents/tron.md` removes TRON cleanly. TRON reads via shell scripts, never inlines values into prompts.

| Key | Required? | Used for |
|:--|:--|:--|
| `TELEGRAM_BOT_TOKEN` | optional | operator escalation channel |
| `TELEGRAM_CHAT_ID` | optional | operator's chat |
| `GITHUB_TOKEN` | optional | `gh` CLI (also satisfied by `gh auth login`) |

**Telegram is optional.** If unconfigured, TRON degrades gracefully: escalations surface in the operator's next CLI interaction rather than via push notification.

## Agents available

Per Premise 17, TRON requires at least one canon-shaped agent in `meta/agents/` to dispatch. The seeder validates **which agents this project has**, then validates `workflow.md` references against that set.

Declare the agents this project uses:

```
agents:
  - architect: meta/agents/architect.md
  - engineer:  meta/agents/engineer.md
  - reviewer:  meta/agents/reviewer.md
```

A project may declare a subset (e.g. no reviewer) or extend with custom roles (e.g. `designer`). The seeder refuses to proceed if `workflow.md` references a role not declared here.

## Workflow doc

- Workflow rules (operator-authored): `meta/agents/tron/workflow.md`
- Live counters (TRON-managed): `meta/agents/tron/workflow-state.md`

---

## Operator-only tasks (T1/T5)

Tasks engineers must NOT attempt — TRON escalates these directly to the operator without dispatching work.

- DNS / domain configuration
- Third-party dashboard configuration (Stripe, Vercel project settings, Auth0, etc.)
- Production billing / paid plan changes
- Anything requiring physical access (hardware, device-side install)

## Local-validation gaps

Tasks engineers will perform but cannot fully verify alone. TRON flags these at SV-01 so the operator manually tests.

- Mobile builds (TestFlight upload + device install)
- Live integration tests with paid third-party services
- End-to-end user-journey flows requiring a real account
- Telegram bridge live message verification

## CI behavior

- Runner: GitHub Actions
- Typical full-suite duration: ~6 min
- Stall threshold override: applies after CI start (see `workflow.md` fixed config)

## Deploy flow

- Trigger: merge to `main`
- Target: Vercel (auto-deploys on merge)
- Preview URL: on every PR
- Monitor: TRON watches deployment status past merge (see [Monitor the full flow] feedback)

## Other notes

Free-form context TRON should know but doesn't act on programmatically. Examples:

- This is a monorepo; engineers should respect package boundaries.
- Migration files must be paired with rollback SQL.
- (Anything else worth capturing.)

---

**Editing this file:** safe to hand-edit; TRON re-reads on session start. To change knobs that TRON also tracks live (workflow rules, counters, scripts), describe the change to TRON in natural language — TRON owns those edits to keep dependent docs in sync.
