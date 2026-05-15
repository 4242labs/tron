# tron-seed.md — Canon seeder

This document is read by Claude Code on the operator's machine to seed TRON into a target project. The operator opens an interactive Claude Code session, points it at this file, and tells it the target project path. Claude Code (acting as the seeder) walks the operator through the steps below and writes the local TRON instance.

The seeder must leave the canon `tron/` repo **untouched** (Premise 1). All writes land in the target project.

---

## Prerequisites the seeder must verify before starting

1. Target project is a git repository.
2. Target project has `meta/agents/architect.md`, `meta/agents/engineer.md`, `meta/agents/reviewer.md` (Premise 17). If any are missing: stop and ask the operator to add them first. Do not auto-create them.
3. Target project has a `.env` at the repo root (or seeder will create one). Ensure `.env` is gitignored.
4. `claude` CLI version >= 2.1.139 (Agent View support).
5. `gh`, `curl`, `jq` available on PATH.
6. `crontab` available (macOS / Linux).

If any prerequisite fails: report to operator and stop.

---

## Step 1 — Detect + collect project profile

**Detect first** from the local repo (do not ask the operator for anything detectable):

| Field | Detect via |
|:--|:--|
| Repo root | `git rev-parse --show-toplevel` |
| Project name | repo root dir name |
| Main branch | `git symbolic-ref refs/remotes/origin/HEAD` (fallback: `gh repo view --json defaultBranchRef`) |
| GitHub org/repo | `git remote get-url origin` |
| Worktrees dir | check `.worktrees/`; else default `.worktrees/` |
| Logs dir | check `meta/logs/`; else default `meta/logs/` |

Present a single summary to the operator: "Detected this — looks right?" Only prompt for fields detection couldn't resolve.

**Then ask** (these can't be detected):

- Conventions (branch naming, block ID pattern, worker ID pattern, commit/PR style) — show sensible defaults; operator confirms or overrides.
- Free-form sections — `Operator-only tasks (T1/T5)`, `Local-validation gaps`, `CI behavior`, `Deploy flow`, `Other notes`. Operator may leave any of these blank to fill later.

Save as: `{target_repo}/meta/agents/tron/project.md`.

## Step 2 — Validate agents (before workflow)

Confirm which canon-shaped agents the project has. Per Premise 17, the project must have at least one. The seeder runs:

- For each potential canon agent (`architect.md`, `engineer.md`, `reviewer.md`, plus any custom roles the operator names): check `meta/agents/<role>.md` exists.
- Build the declared-agents list (subset of the canonical 3, or extended).
- Write the declared-agents block into `project.md`.

**Refuse to proceed** if the project has zero canon agents — TRON cannot dispatch without at least one.

## Step 3 — Author workflow.md and validate against declared agents

Copy canon `workflow.example.md` to `{target_repo}/meta/agents/tron/workflow.md`. Walk the operator through each rule:

- R1 — persistent architect: keep / modify? (only ask if architect is in declared agents)
- R2 — engineer technical → architect: keep / modify? (only ask if both roles declared)
- R3 — UI walls → operator: keep / modify?
- R4 — reviewer threshold: confirm value (only ask if reviewer is in declared agents)
- R5 — architect mid-session review: keep / modify? (only ask if architect declared)
- R6 — fresh engineer per block: keep / modify?
- R7 — workers never self-terminate: locked, do not modify (Premise 20)
- Per-session knob defaults: `max_concurrent_engineers`, `session_end_idle_min` — confirm defaults
- Fixed config: `reviewer_threshold`, `tier1_silent_min`, `tier2_silent_min` — confirm defaults

**Validate workflow against declared agents.** If `workflow.md` references a role not declared in Step 2: refuse to proceed; ask operator to either add the agent or trim the rule.

## Step 4 — Seed templates

Copy from canon to `{target_repo}/meta/agents/tron/templates/`:

- `tron.md` → also copy to `{target_repo}/meta/agents/tron.md` (the live agent file)
- `state.md` → `{target_repo}/meta/agents/tron/state.md`
- `workflow-state.md` → `{target_repo}/meta/agents/tron/workflow-state.md`
- `handover-engineer.md`
- `handover-architect.md`
- `handover-reviewer.md`

Initialize `state.md` counters to zero; set `session_started_at: never`.

## Step 5 — Seed skills

Copy all files from canon `skills/` to `{target_repo}/meta/agents/tron/skills/`.

## Step 6 — Seed scripts

Copy all files from canon `scripts/` to `{target_repo}/meta/agents/tron/scripts/`. Run `chmod +x` on each.

## Step 7 — Initialize state files

Create empty:
- `{target_repo}/meta/agents/tron/current-id` (empty)
- `{target_repo}/meta/agents/tron/dispatched.log` (empty)
- `{target_repo}/meta/agents/tron/tg-inbox.jsonl` (empty)
- `{target_repo}/meta/agents/tron/logs/` (directory)

## Step 8 — Copy scripts.md from canon

Copy canon `tron-scripts.md` → `{target_repo}/meta/agents/tron/scripts.md`. (Note rename: canon ships as `tron-scripts.md` for clarity; local instance uses `scripts.md`.)

## Step 9 — Confirm .env keys (optional escalation channel)

Telegram is **optional**. Ask the operator:

> Configure Telegram escalation now? (recommended for unattended sessions; skip to run with degraded escalation — operator sees alerts on next CLI interaction.)

If yes:
- Check `{target_repo}/.env`. Create with placeholder lines if missing; ensure `.env` is gitignored.
- For each TG key (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`): if missing, prompt operator to paste; append to `.env`.
- Never log key values to seed-trace.

If skipped: log `tg_configured: false` in seed-trace; TRON will detect missing keys at runtime and degrade gracefully.

## Step 10 — Install cron

Run `bash {target_repo}/meta/agents/tron/scripts/cron-install.sh`. Verify with `crontab -l | grep tron-cron`.

## Step 11 — Write seed-trace.md

Create `{target_repo}/meta/agents/tron/seed-trace.md`. Record:
- Date of seed
- Canon repo path + git sha at seed time
- Operator choices for each step
- Any deviations from defaults
- Any prerequisites the seeder had to flag

This document is the audit trail. Operators and future re-seeds rely on it.

## Step 12 — Final validation

Run TRON in dry-run mode (cold-start sequence without spawning workers):
1. Have the operator run: `claude --bg -n TRON "Start session. Run validate + doctor in audit-only mode and report."`
2. TRON should output `validate: pass` and `doctor: clean`.
3. If issues: surface them, iterate.

## Step 13 — Sign-off

Print summary to operator:
```
Seed complete.
- Project: {NAME}
- TRON folder: {target_repo}/meta/agents/tron/
- Cron entries installed
- .env keys configured
- Seed trace: {target_repo}/meta/agents/tron/seed-trace.md

To start TRON: claude --bg -n TRON "Begin session."
```

---

## Re-seeding / updates

The seeder is safely re-runnable (Premise 16). On a re-run:
- Steps 1–2: if `project.md` / `workflow.md` already exist, show current values; ask before overwriting.
- Steps 3–5: file-by-file diff against canon; ask before overwriting any file the operator may have customized (especially `scripts.md`).
- Step 9: cron install is already idempotent.
- Step 10: append a new dated section to `seed-trace.md`; never truncate.

For pulling canon updates without a full re-seed, the operator should use TRON's `skill-update` from a running session — that is the surgical, per-file diff/accept/reject path.

---

## What the seeder must NOT do

- Modify any file in the canon `tron/` repo (Premise 1).
- Spawn TRON itself (operator does that, manually, post-seed).
- Inline secrets into any file other than `.env`.
- Create `architect.md`, `engineer.md`, `reviewer.md` (Premise 17 — operator owns these).
- Skip the `skill-validate` + `skill-doctor` dry run (Premise 11, 16).
