---
name: skill-worktree-and-branching
description: Worktree + branch + PR discipline for all agents; the parallel-safe Git entry point. Never commit on the base branch.
source: canon
canon_version: HEAD
---

# Skill: Worktree + Branching (<PROJECT_NAME>)

The entry point for all parallel-agent-safe work in <PROJECT_NAME>. Read this before touching any file.

---

## Canonical references

This skill is the **<PROJECT_NAME> adaptation** of the shared multi-agent Git procedure. The shared file is the source of truth for lifecycle, hygiene, and branch flow; this file restates the parts an agent needs and adds the <PROJECT_NAME>-specific deltas.

- `{shared_knowledge_path}/skills/skill-git-multi-agent.md` — full Git workflow: worktree lifecycle, branch naming, rebase, CI monitoring, cleanup

You do **not** need to open the shared file to execute this skill. It exists so the procedure can evolve in one place.

---

## Setup (once per clone)

Required before adding any worktree. Each repo ships `scripts/setup-repo.sh` (a tracked bootstrap script) that configures portable-worktree settings (`worktree.useRelativePaths=true`, which implicitly enables `extensions.relativeWorktrees`). Requires Git ≥ 2.48.

- **`<APP_REPO_NAME>`** — auto-runs via `npm install` / `pnpm install` (wired through the `prepare` lifecycle script in `app/package.json`). No manual step needed after a fresh clone.
- **`<META_REPO_NAME>`** — no Node package manager, so run once after cloning:

  ```
  cd <WORKSPACE_PATH>/<META_REPO_NAME>
  ./scripts/setup-repo.sh
  ```

Both scripts are idempotent (safe to re-run). Implements `{shared_knowledge_path}/principles-base.md §14 Portability — Relative-path worktrees`. Canonical template: `{shared_knowledge_path}/templates/setup-repo.sh`.

---

## <PROJECT_NAME>-specific rules

- **Two repos.** <PROJECT_NAME> is split into `<GITHUB_ORG>/<APP_REPO_NAME>` (app code, docs, infra) and `<GITHUB_ORG>/<META_REPO_NAME>` (this repo — agents, skills, pipeline, blocks, logs). App work branches from `<APP_REPO_NAME>`; meta work branches from `<META_REPO_NAME>`.
- **No direct push to `staging` or `main`.** Every change — `app/`, `meta/`, `docs/`, root files — goes through a feature branch + worktree + PR + CI + **a monitored merge**. There are no exceptions for either protected branch.
- **Two-gate flow.** All work flows through feature branches into `staging` (default) or `main` (hotfix only). Solo-dev repo: `required_approving_review_count: 0` on both branches (GitHub blocks self-approval). Auto-merge is banned — `gh pr merge --auto` is never armed; the agent merges once authorized and monitors the merge through to a verified deploy. Repo default branch is `staging`, so new PRs auto-target the correct gate.
  - **Default:** `feat|fix|chore|docs/<slug>` → PR targets `staging` → per-PR Vercel preview + `app-ci` → merge authorized → agent merges → integration-tested on `staging.<PROJECT_NAME>` → `staging → main` promotion PR → merge authorized → agent merges → ships to prod.
  - **Hotfix lane:** `hotfix/<slug>` → PR targets `main` directly → per-PR preview + `app-ci` → merge authorized → agent merges → ships immediately. Use only when the staging gate would cost more than the bug it patches. Backport after: `git checkout staging && git pull && git merge main`.
  - The `pr-base-guard` CI job mechanically enforces that only `staging` or `hotfix/*` branches can PR into `main`.
- **Worktree base path.** Worktrees live **inside the workspace** at `<WORKSPACE_PATH>/worktrees/`, prefixed by repo:

  ```
  <WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--{branch-name}   ← for app code work
  <WORKSPACE_PATH>/worktrees/<META_REPO_NAME>--{branch-name}  ← for meta work
  ```

  The double-dash separator is mandatory. The slash in the branch name becomes a hyphen in the directory name — e.g. `<WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--feat-b06-13-github-actions-ci`.

  Worktrees live inside the workspace (not `~/worktrees/`) so the entire workspace tree is portable as a unit. Combined with `worktree.useRelativePaths=true` (set by `scripts/setup-repo.sh` — see §Setup below), the workspace can be moved or renamed without `git worktree repair`.

- **Main checkout stays on `staging`.** `<WORKSPACE_PATH>/<APP_REPO_NAME>/` is always checked out to `staging` — never a feature branch, never `main`. It is read-only: no edits, no commits, no staged files. It exists only as the base for creating worktrees and for read-only reference against `staging`. If you find yourself about to edit a file under `<WORKSPACE_PATH>/<APP_REPO_NAME>/`, stop and create a worktree.
- **Always rebase on `staging` before pushing.** Run `git fetch origin && git rebase origin/staging` before every push. Skipping causes out-of-date rejections and integration conflicts — no exceptions.
- **Monitor CI after every push. Do not proceed until all checks are green.** Run `gh pr checks {PR} --watch` immediately after opening a PR. Fix failures before any next step.
- **One agent per branch.** Two agents must not share a worktree. If a branch carries WIP into a later session, the next agent **resumes the same worktree** rather than creating a new one on the same branch.
- **Session start is read-only; tear down your own at session end.** Run the session-start scan (inspect + conflict check) every session — but never remove another agent's worktree there. Remove the worktree *you* created once *your* PR merges (block 6). Orphaned worktrees (remote gone + no open PR) are garbage-collected by SUPER-M's health check, not at session start — see `{shared_knowledge_path}/skills/skill-git-multi-agent.md §Worktree teardown & orphan GC`.

---

## Cross-repo changes

Some tasks touch both repos in the same session — e.g. a code change that also requires updating `pipeline.md`, a block completion that ships app code and marks the block done, or a Core Docs update that spans `<APP_REPO_NAME>/docs/` and `<META_REPO_NAME>/`.

**Rules:**

- **Two independent PRs — one per repo.** There is no shared gate between repos. Each PR goes through its own CI and merge click.
- **Same branch slug, different prefix.** Use the same slug in both repos so the pair is traceable: `feat/b14-05-schema-governance` in <APP_REPO_NAME> and `feat/b14-05-schema-governance` in <META_REPO_NAME>.
- **Order: app first, meta second** when one depends on the other. App code ships a feature; meta documents it. If they are truly independent (e.g. a docs fix alongside a pipeline note), order doesn't matter — open both PRs, merge as each goes green.
- **Never hold up an app PR waiting for a meta PR.** Meta changes (pipeline, logs, agents) are documentation — they do not block app CI. Merge app when green; merge meta when green. They are decoupled.
- **Same session-start hygiene applies to both.** Before touching <META_REPO_NAME> files, verify its main checkout is on `staging` at `<WORKSPACE_PATH>/<META_REPO_NAME>/` and create a worktree there.

**Quick reference — opening a cross-repo pair:**

```bash
# App worktree
cd <WORKSPACE_PATH>/<APP_REPO_NAME>
git worktree add <WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--{type}-{slug} -b {type}/{slug} origin/staging

# Meta worktree (same slug)
cd <WORKSPACE_PATH>/<META_REPO_NAME>
git worktree add <WORKSPACE_PATH>/worktrees/<META_REPO_NAME>--{type}-{slug} -b {type}/{slug} origin/staging
```

Push, open PRs, and monitor CI for each independently.

---

## Branch naming convention

| Kind of work | Pattern | Example |
|:-------------|:--------|:--------|
| Block work | `{type}/b{phase}-{seq}-{slug}` | `feat/b06-13-github-actions-ci` |
| Ad-hoc block | `{type}/b{phase}-adhoc-{slug}` | `chore/b06-adhoc-worktree-foundation` |
| Non-block ad-hoc | `{type}/adhoc-{slug}` | `fix/adhoc-typo-in-faq` |
| Hotfix | `hotfix/{slug}` | `hotfix/broken-login-redirect` |

- Type prefixes: `feat/`, `fix/`, `chore/`, `docs/`, `hotfix/`
- Lowercase only. Hyphens only inside the slug. The slash after the type prefix is preserved verbatim in the branch name and the worktree path.
- Block branches must match the block file name in `blocks/`.
- `hotfix/` branches are the only type that may PR directly into `main` — all others target `staging`.

---

## Quick reference (copy-paste)

### 1. Session-start hygiene scan

Run at the top of every session, before opening any editor.

**Step 1 — Verify main checkout is on `staging`.**

```
cd <WORKSPACE_PATH>/<APP_REPO_NAME>
git branch --show-current
```

If the output is not `staging`:

```
git checkout staging
git pull --ff-only origin staging
```

**Step 2 — Fetch and inspect.**

```
git fetch --prune origin
git worktree list
git branch -vv
```

Any branch tagged `[gone]` in `git branch -vv` has no remote counterpart — it is orphaned. **Note it; do not remove it here** — orphan GC is SUPER-M's job, not a session-start chore.

**Step 3 — Note orphans (read-only).**
Session start is read-only — you never remove another agent's worktree here. For each worktree shown (excluding the main checkout):
- Branch still exists on `origin` → leave it alone.
- Branch shows `[gone]` **and** no open PR → orphaned. Leave it for SUPER-M's orphan GC (`{shared_knowledge_path}/skills/skill-git-multi-agent.md §Worktree teardown & orphan GC`).
- Has an open PR → leave it; the next agent resumes it.

You only ever remove the worktree **you** created, and only at session end once **your** PR merges (block 6).

**Step 4 — Parallel conflict check.**

```
gh pr list --base staging --state open
```

Review open PR titles. If any open PR touches the same area as your task, report to the user and wait for explicit confirmation before writing any code.

### 2. Create a worktree on a new branch

Before creating a branch, verify the name follows §Branch naming convention. The worktree directory must be `<WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--{type}-{branch-suffix}` for app work, or `<META_REPO_NAME>--{type}-{branch-suffix}` for meta work (slash replaced with hyphen in the path).

```
cd <WORKSPACE_PATH>/<APP_REPO_NAME>
git fetch origin
git worktree add <WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--{type}-{branch-suffix} -b {type}/{branch-suffix} origin/staging
cd <WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--{type}-{branch-suffix}
```

Substitute `{type}` / `{branch-suffix}` with your branch name (e.g. `feat` / `b06-13-github-actions-ci`).

PR target: `staging` (default). Only `hotfix/` branches target `main`.

### 3. Resume an in-progress branch

When a prior session left WIP on a branch (still has an open PR) and you're picking it up:

```
cd <WORKSPACE_PATH>/<APP_REPO_NAME>
git fetch origin
git worktree add <WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--{type}-{branch-suffix} {type}/{branch-suffix}
cd <WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--{type}-{branch-suffix}
git pull --ff-only origin {type}/{branch-suffix}
```

If the branch only exists on `origin` (no local ref yet):

```
git worktree add <WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--{type}-{branch-suffix} -b {type}/{branch-suffix} origin/{type}/{branch-suffix}
```

### 4. Push

First push:

```
git fetch origin
git rebase origin/staging
git push -u origin {branch}
```

Re-push after rebase or amend:

```
git fetch origin
git rebase origin/staging
git push --force-with-lease origin {branch}
```

Rebase conflict during push:

```
# resolve conflict in file(s)
git add {resolved-files}
git rebase --continue
git push --force-with-lease origin {branch}
```

### 5. Monitor CI

```
gh pr checks {PR-number} --watch
```

Do not proceed to the next task until all checks pass. If any check fails → fix, commit, push, rebase, repeat.

### 6. Final cleanup after the PR merges

Confirm the PR is merged before running:

```
gh pr view {PR-number} --json state --jq '.state'   # must return MERGED
cd <WORKSPACE_PATH>/<APP_REPO_NAME>
git fetch --prune origin
git worktree remove <WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--{type}-{branch-suffix}
git branch -D {type}/{branch-suffix}
git pull --ff-only origin staging
```

If `git worktree remove` refuses because the worktree is dirty and you've already confirmed the work is merged:

```
git worktree remove --force <WORKSPACE_PATH>/worktrees/<APP_REPO_NAME>--{type}-{branch-suffix}
```

### 7. Recovery from a broken worktree

If `git worktree list` shows a path that no longer exists, or a directory exists but git doesn't know about it:

```
cd <WORKSPACE_PATH>/<APP_REPO_NAME>
git worktree prune
git worktree list
```

If a directory was deleted manually but git still thinks the worktree exists, `git worktree prune` removes the stale admin entry. If a directory exists but is not registered, recreate it via block 3 above (resume) — do not try to register the existing directory.

---

## Session-Start Hygiene

Every agent doc's `## Session Start` checklist points here. Run block 1 (all four steps: staging verification, fetch + inspect, note orphans read-only, conflict check) before any read steps. Then create your worktree if needed (block 2 or 3). **Never edit files in the main checkout. The main checkout must always be on `staging`.**
