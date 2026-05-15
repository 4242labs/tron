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

## Step 1 — Collect project profile

Open `project.example.md` from the canon. Walk the operator through each section interactively. Build the project's own `project.md` based on operator answers.

Fields to confirm with the operator:

- Project name
- Repo root (absolute path)
- Main branch
- Worktrees directory (default `.worktrees/`)
- Logs directory (default `meta/logs/`)
- GitHub org/repo slug
- Branch naming convention
- Block ID convention
- Worker ID convention
- Commit / PR conventions
- `.env` keys needed (default: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
- Agents available (confirm canon-shaped files exist)
- T1/T5 / out-of-scope notes

Save as: `{target_repo}/meta/agents/tron/project.md`.

## Step 2 — Author workflow.md

Copy canon `workflow.example.md` to `{target_repo}/meta/agents/tron/workflow.md`. Walk the operator through each rule:

- R1 — persistent architect: keep / modify?
- R2 — engineer technical → architect: keep / modify?
- R3 — UI walls → operator: keep / modify?
- R4 — reviewer threshold: confirm N (default 3)
- R5 — architect mid-session review: keep / modify?
- R6 — fresh engineer per block: keep / modify?
- R7 — workers never self-terminate: locked, do not modify (Premise 20)

Save adjustments. The operator can edit further by hand or via TRON later.

## Step 3 — Seed templates

Copy from canon to `{target_repo}/meta/agents/tron/templates/`:

- `tron.md` → also copy to `{target_repo}/meta/agents/tron.md` (the live agent file)
- `state.md` → `{target_repo}/meta/agents/tron/state.md`
- `workflow-state.md` → `{target_repo}/meta/agents/tron/workflow-state.md`
- `handover-engineer.md`
- `handover-architect.md`
- `handover-reviewer.md`

Initialize `state.md` counters to zero; set `session_started_at: never`.

## Step 4 — Seed skills

Copy all files from canon `skills/` to `{target_repo}/meta/agents/tron/skills/`.

## Step 5 — Seed scripts

Copy all files from canon `scripts/` to `{target_repo}/meta/agents/tron/scripts/`. Run `chmod +x` on each.

## Step 6 — Initialize state files

Create empty:
- `{target_repo}/meta/agents/tron/current-id` (empty)
- `{target_repo}/meta/agents/tron/dispatched.log` (empty)
- `{target_repo}/meta/agents/tron/tg-inbox.jsonl` (empty)
- `{target_repo}/meta/agents/tron/logs/` (directory)

## Step 7 — Copy scripts.md from canon

Copy canon `tron-scripts.md` → `{target_repo}/meta/agents/tron/scripts.md`. (Note rename: canon ships as `tron-scripts.md` for clarity; local instance uses `scripts.md`.)

## Step 8 — Confirm .env keys

Check `{target_repo}/.env`:
- If file doesn't exist: create it with placeholder lines for declared keys, and add `.env` to `.gitignore` if not already.
- For each declared key: if missing, prompt operator to paste the value. Append to `.env`.
- Never log key values to the seed trace.

## Step 9 — Install cron

Run `bash {target_repo}/meta/agents/tron/scripts/cron-install.sh`. Verify with `crontab -l | grep tron-cron`.

## Step 10 — Write seed-trace.md

Create `{target_repo}/meta/agents/tron/seed-trace.md`. Record:
- Date of seed
- Canon repo path + git sha at seed time
- Operator choices for each step
- Any deviations from defaults
- Any prerequisites the seeder had to flag

This document is the audit trail. Operators and future re-seeds rely on it.

## Step 11 — Final validation

Run TRON in dry-run mode (cold-start sequence without spawning workers):
1. Have the operator run: `claude --bg -n TRON "Start session. Run validate + doctor in audit-only mode and report."`
2. TRON should output `validate: pass` and `doctor: clean`.
3. If issues: surface them, iterate.

## Step 12 — Sign-off

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
