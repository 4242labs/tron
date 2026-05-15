# skill-doctor

Audit project structure against `project.md` (Premise 16). Detects missing files, broken paths, absent env keys, missing canon agents. Re-runnable safely.

## When to invoke

- Every session start (after `skill-validate` doc-drift mode).
- After `skill-update` to confirm structural integrity.
- On operator demand: "TRON, run doctor."
- Periodically (every 10 sweeps) as a background sanity check.

## Steps

1. **Read `project.md`.** Extract:
   - `repo_root`, `main_branch`, `worktrees_dir`, `logs_dir`, `github_org_repo`
   - `env_keys` list
   - Canon agent paths (`architect.md`, `engineer.md`, `reviewer.md`)

2. **Path checks:**
   - `repo_root` exists, is a git repo.
   - `worktrees_dir` exists or is creatable.
   - `logs_dir` exists or is creatable.
   - Each canon agent file exists at expected path.

3. **Branch checks:**
   - Run `git -C {repo_root} branch --show-current` — note current branch.
   - Run `git -C {repo_root} remote -v` — confirm remote matches `github_org_repo`.

4. **Env key checks:**
   - `.env` exists at `repo_root`.
   - Each declared key in `env_keys` is set (non-empty).
   - `.env` is gitignored (`grep -q "^\.env" {repo_root}/.gitignore`).

5. **TRON folder structure:**
   - `meta/agents/tron.md` exists.
   - `meta/agents/tron/` exists.
   - Required subfolders exist: `skills/`, `templates/`, `scripts/`, `logs/`.
   - Required files exist: `project.md`, `workflow.md`, `workflow-state.md`, `scripts.md`, `state.md`.
   - `current-id` exists (may be empty if TRON not running).
   - `dispatched.log` exists (may be empty).
   - `seed-trace.md` exists.

6. **Cron check:**
   - Operator-installed cron job for `sweep.sh` and `tg-poll.sh` is registered (`crontab -l | grep tron`).

7. **Tooling checks:**
   - `claude` CLI on PATH, version >= 2.1.139 (Agent View support).
   - `gh` CLI on PATH, authenticated (`gh auth status`).
   - `curl` and `jq` available (Telegram scripts).

8. **Report:**
   - **All clear** → `TRON: doctor clean.`
   - **Issues** → list each, severity (blocker / warning), suggested fix. Example:
     ```
     TRON: doctor found issues.
     [BLOCKER] meta/agents/engineer.md missing — canon agent prereq (Premise 17). Fix: add the file.
     [WARNING] cron job for sweep.sh not installed. Fix: bash meta/agents/tron/scripts/cron-install.sh
     ```
9. **Blockers** halt the session — TRON refuses to dispatch workers until resolved. Warnings are logged and surfaced once per session.

## Failure modes

- **`project.md` missing:** seeder was not run or was interrupted. Escalate immediately.
- **Doctor can't run due to filesystem permission errors:** escalate; do not silently continue.
