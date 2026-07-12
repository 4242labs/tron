# Skill: Project Scaffold

**Purpose:** Exact procedural sequence to scaffold a new 42Labs project from zero.

**Prerequisite:** `skills/skill-project-profile.md` must have run in `fresh` mode and locked `{profile, values}`. Do not proceed without them.

**Scope:** Scaffolds the workflow infrastructure (meta repo, config, CI, hooks, portable-worktree bootstrap, MCPs, services) around a Next.js application. Does NOT create the Next.js app itself — the user must run `npx create-next-app` in `APP_SUBDIR` either before step 4 (to have a real `package.json` for npm install) or after step 5 (before step 13). Remind the user if they haven't initialized the app yet.

**Templates source of truth:** `tron/tron-app/templates/project-scaffold/templates/` — every file copy step below reads from there.

---

## Steps

### 1. Create workspace directory structure

```bash
mkdir -p WORKSPACE_PATH/PROJECT_NAME-meta
mkdir -p WORKSPACE_PATH/PROJECT_NAME-app/app
mkdir -p WORKSPACE_PATH/.claude
mkdir -p WORKSPACE_PATH/worktrees
```

The workspace-internal `worktrees/` directory is where all per-branch worktrees will live (see step 4b — Portable-worktree bootstrap). Keeping worktrees inside the workspace tree makes the whole project portable as a unit.

### 2. Copy and fill workspace-level templates

Copy from `tron/tron-app/templates/project-scaffold/templates/`:

| Source | Destination | Fill |
|--------|-------------|------|
| `templates/AGENTS.md` | `WORKSPACE_PATH/AGENTS.md` | `<PROJECT_NAME>`, `<META_REPO_NAME>`, `<APP_REPO_NAME>`, 42Agents paths |
| `templates/.claude/settings.json` | `WORKSPACE_PATH/.claude/settings.json` | `<ABSOLUTE_PATH_TO_APP_SUBDIR>` → `APP_SUBDIR`; remove Vercel plugin if non-Vercel; use `npm test --if-present` so the hook doesn't error on projects without a test script yet |
| `templates/.mcp.json` | `WORKSPACE_PATH/.mcp.json` | Verbatim — wires GitHub MCP (always) plus one devtools-class and one automation-class browser MCP (always); add per-profile MCPs (Supabase, Plain) if confirmed |

### 3. Copy and fill meta repo templates

Copy from `templates/meta/`:

| Source | Destination |
|--------|-------------|
| `templates/meta/AGENTS.md` | `META_REPO_ROOT/AGENTS.md` |
| `templates/meta/pipeline.md` | `META_REPO_ROOT/pipeline.md` |
| `templates/meta/context.md` | `META_REPO_ROOT/context.md` |
| `templates/meta/principles.md` | `META_REPO_ROOT/principles.md` |
| `templates/meta/agents/architect.md` | `META_REPO_ROOT/agents/architect.md` |
| `templates/meta/agents/engineer.md` | `META_REPO_ROOT/agents/engineer.md` |
| `templates/meta/agents/data-architect.md` | `META_REPO_ROOT/agents/data-architect.md` |
| `templates/meta/agents/reviewer-code.md` | `META_REPO_ROOT/agents/reviewer-code.md` |
| `templates/meta/agents/reviewer-security.md` | `META_REPO_ROOT/agents/reviewer-security.md` |
| `templates/meta/agents/flynn-local.md` | `META_REPO_ROOT/agents/flynn-local.md` |
| `templates/meta/skills/*.md` (all 10 core) | `META_REPO_ROOT/skills/` |
| `templates/meta/blocks/block-template.md` | `META_REPO_ROOT/blocks/block-template.md` |
| `templates/meta/ref-*.md` (all 3) | `META_REPO_ROOT/` |

Log directories ship with the kit — `templates/meta/logs/{architecture,data-architect,engineering,review-code,review-security,flynn}/` each carry a tracked `.gitkeep`, so the copy step above brings them over as structure. No `mkdir` needed; verify all six exist after copy.

Fill all `<PROJECT_NAME>` and `<PLACEHOLDER>` tokens.

> TRON is out of scope here. If the project uses TRON, TRON seeds its own `tron.md` and `skill-tg-comms.md` via its own onboarding — do not pre-create them in scaffold.

### 4. Copy and fill app repo templates

Copy from `templates/app/`:

| Source | Destination | Notes |
|--------|-------------|-------|
| `templates/app/.nvmrc` | `APP_REPO_ROOT/.nvmrc` | Replace `<NODE_LTS_VERSION>` → `NODE_LTS_VERSION` |
| `templates/app/lefthook.yml` | `APP_REPO_ROOT/lefthook.yml` | Verbatim |
| `templates/app/.env.example` | `APP_REPO_ROOT/.env.example` | Add project-specific vars |
| `templates/app/mcp-setup.md` | `APP_REPO_ROOT/mcp-setup.md` | Omit non-applicable sections |
| `templates/app/services-setup.md` | `APP_REPO_ROOT/services-setup.md` | Omit non-applicable sections |
| `templates/app/docs/playbook-infra.md` | `APP_REPO_ROOT/docs/playbook-infra.md` | Fill project-specific URLs |
| `templates/app/docs/playbook-browser-testing.md` | `APP_REPO_ROOT/docs/playbook-browser-testing.md` | Verbatim; required by the always-applicable browser-validation audit row |
| `templates/app/app/commitlint.config.js` | `APP_SUBDIR/commitlint.config.js` | Verbatim |
| `templates/app/app/AGENTS.md` | `APP_SUBDIR/AGENTS.md` | Fill tech stack, project name |

**Profile-trim pass.** Four files ship with all-service content and MUST be trimmed to the confirmed profile before continuing:

| File | What to trim |
|------|--------------|
| `APP_REPO_ROOT/.env.example` | Remove env-var blocks for every unconfirmed service (Supabase, Vercel, Sentry, Matomo, Brevo, Polar, Plain, FirstPromoter, Slack) |
| `APP_REPO_ROOT/mcp-setup.md` | Remove sections for unconfirmed integrations (Supabase MCP, Vercel plugin, Plain API). GitHub MCP always stays |
| `APP_REPO_ROOT/services-setup.md` | Remove sections for unconfirmed services (Railway/LiteLLM, Slack, Brevo, Polar, Sentry, Matomo, FirstPromoter, Pipedream) |
| `APP_REPO_ROOT/docs/playbook-infra.md` | Remove service sections (Supabase, Vercel, Slack, Brevo, Polar, Sentry, etc.) not in profile; collapse Secrets Reference to only the secrets the project actually owns |

Add a banner at the top of each trimmed file naming the active profile: "**Profile at scaffold:** \<list\>. Other services intentionally omitted — added via `UPGRADE PROJECT` if introduced."

**Conditional — Railway/LiteLLM only:**
```
APP_REPO_ROOT/infra/Dockerfile.litellm
APP_REPO_ROOT/infra/litellm_config.yaml
APP_REPO_ROOT/infra/litellm-entrypoint.sh
```

### 4b. Portable-worktree bootstrap

Implements `42hq/knowledge-base/principles-base.md §14 Portability — Relative-path worktrees`. Required before either repo gets its first worktree.

**Verify Git version (≥ 2.48):**

```bash
git --version
```

If older, fail loudly — the user must `brew upgrade git` (or platform equivalent) before continuing.

**Copy bootstrap script to each repo.** Source: the TRON scaffold templates (`tron/tron-app/templates/project-scaffold/templates/` — the single source of truth for all scaffold payload; see §Templates source of truth). Body must remain byte-identical to the template so a future fix reapplies with `diff` confidence.

| Source | Destination | chmod |
|--------|-------------|-------|
| `templates/app/scripts/setup-repo.sh` | `APP_REPO_ROOT/scripts/setup-repo.sh` | 755 |
| `templates/meta/scripts/setup-repo.sh` | `META_REPO_ROOT/scripts/setup-repo.sh` | 755 |

The leading comment block and final echo line **may** be project-localized (e.g. mention `<APP_REPO_NAME>` / `<META_REPO_NAME>`); the executable body **must remain byte-identical** to the template.

```bash
TPL=tron/tron-app/templates/project-scaffold/templates
mkdir -p APP_REPO_ROOT/scripts META_REPO_ROOT/scripts
cp $TPL/app/scripts/setup-repo.sh  APP_REPO_ROOT/scripts/setup-repo.sh
cp $TPL/meta/scripts/setup-repo.sh META_REPO_ROOT/scripts/setup-repo.sh
chmod +x APP_REPO_ROOT/scripts/setup-repo.sh META_REPO_ROOT/scripts/setup-repo.sh
```

The app repo wires the script into `package.json prepare` — done in step 13 (after `npx create-next-app` creates `package.json`). The meta repo has no Node package manager, so it runs manually once per clone.

**Copy canon hook scripts into both repos.** Required for the worktree-mandatory + no-direct-integration-branch enforcement.

```bash
TPL=tron/tron-app/templates/project-scaffold/templates
mkdir -p APP_REPO_ROOT/.githooks META_REPO_ROOT/.githooks
cp $TPL/app/.githooks/pre-commit  APP_REPO_ROOT/.githooks/
cp $TPL/app/.githooks/pre-push    APP_REPO_ROOT/.githooks/
cp $TPL/meta/.githooks/pre-commit META_REPO_ROOT/.githooks/
cp $TPL/meta/.githooks/pre-push   META_REPO_ROOT/.githooks/
chmod +x APP_REPO_ROOT/.githooks/* META_REPO_ROOT/.githooks/*
```

**Write repo-class + integration-branch markers** (read by the hooks at runtime — without them hooks are no-op, per `principles-base.md §14`):

```bash
echo "meta"    > META_REPO_ROOT/.repo-class
echo "main"    > META_REPO_ROOT/.integration-branch
echo "app"     > APP_REPO_ROOT/.repo-class
echo "staging" > APP_REPO_ROOT/.integration-branch
```

Per `principles-base.md §14` integration branch convention: canon + meta use `main`; apps use `staging` (canonical, not optional).

### 5. Copy CI workflow templates

Always include:
- `ci.yml`
- `pr-base-guard.yml`

Include only if confirmed:

| Workflow | Condition |
|----------|-----------|
| `staging-db.yml` | Supabase |
| `deploy-notify.yml` | Vercel + Slack |
| `release-please.yml` | Public changelog |
| `release-notify.yml` | Subscriber emails + Brevo |
| `e2e.yml` | Playwright |
| `stress.yml` | Load requirements |

Destination: `APP_REPO_ROOT/.github/workflows/`

### 6. Verify no `<PLACEHOLDER>` tokens remain

```bash
grep -r "<PLACEHOLDER>\|<PROJECT_NAME>\|<APP_SUBDIR>\|<APP_REPO_ROOT>\|<NODE_LTS_VERSION>\|<ABSOLUTE_PATH_TO_APP_SUBDIR>" WORKSPACE_PATH/
```

Fix all hits before continuing.

### 7. Init git — meta repo

Meta uses `main` as the integration branch (`principles-base.md §14`).

```bash
cd META_REPO_ROOT
git init -b main
git add -A
git commit -m "chore: init project scaffold"
./scripts/setup-repo.sh   # configures core.hooksPath=.githooks + worktree.useRelativePaths
```

### 8. Init git — app repo

App uses `staging` as the integration branch (`principles-base.md §14`).

```bash
cd APP_REPO_ROOT
git init -b staging
git add -A
git commit -m "chore: init project scaffold"
./scripts/setup-repo.sh   # detects lefthook → leaves core.hooksPath unset; sets worktree.useRelativePaths
```

### 9. Create GitHub repos + initial push (with bootstrap-feature-branch workaround)

The first push of a fresh repo to its protected integration branch fails the canon `.githooks/pre-push` reachability check: the initial commit lives only on the integration branch, with no other ref containing it. The hook then blocks the push as if it were a direct-to-integration commit.

Workaround: push a feature branch first so the integration commit becomes reachable from another ref, then push the integration branch, then delete the feature branch.

**Meta repo** (integration = `main`):

```bash
cd META_REPO_ROOT
gh repo create GITHUB_ORG/PROJECT_NAME-meta --private --source=. --remote=origin
git branch chore/bootstrap-YYMMDD main
git push -u origin chore/bootstrap-YYMMDD
git push -u origin main
gh api repos/GITHUB_ORG/PROJECT_NAME-meta --method PATCH -f default_branch=main > /dev/null
git push origin --delete chore/bootstrap-YYMMDD
git branch -d chore/bootstrap-YYMMDD
```

**App repo** (integration = `staging`; lefthook not yet installed at this point so canon pre-push doesn't fire from the app repo — single-pass push is fine):

```bash
cd APP_REPO_ROOT
gh repo create GITHUB_ORG/PROJECT_NAME-app --private --source=. --remote=origin --push
gh api repos/GITHUB_ORG/PROJECT_NAME-app --method PATCH -f default_branch=staging > /dev/null
git branch main staging
git push -u origin main
```

### 10. Default branch is set during step 9

Meta default: `main`. App default: `staging`. The `gh api ... default_branch=` calls in step 9 land this — verify with `gh repo view <repo> --json defaultBranchRef`.

### 11. Configure branch protection

Meta: protect `main` only (the only branch — meta has no `staging`).
App: protect both `main` (production) and `staging` (integration).

```bash
PROTECTION_BODY='{"required_status_checks":null,"enforce_admins":false,"required_pull_request_reviews":{"required_approving_review_count":0},"restrictions":null}'
echo "$PROTECTION_BODY" | gh api repos/GITHUB_ORG/PROJECT_NAME-meta/branches/main/protection    --method PUT --input - > /dev/null
echo "$PROTECTION_BODY" | gh api repos/GITHUB_ORG/PROJECT_NAME-app/branches/main/protection     --method PUT --input - > /dev/null
echo "$PROTECTION_BODY" | gh api repos/GITHUB_ORG/PROJECT_NAME-app/branches/staging/protection  --method PUT --input - > /dev/null
```

### 12. Install commitlint deps + Lefthook

The app-side commitlint config extends `@commitlint/config-conventional` — without it the commit-msg hook errors with `Cannot find module "@commitlint/config-conventional"`. Lefthook itself is installed as a devDep so contributors don't need a global lefthook.

```bash
cd APP_SUBDIR
npm install --save-dev @commitlint/cli @commitlint/config-conventional lefthook
cd APP_REPO_ROOT
npx lefthook install
./scripts/setup-repo.sh   # re-run post-lefthook-install per the §Hook integration patterns warning
```

Verify (from inside an added worktree only — the canon pre-commit blocks direct commits from the main checkout):

```bash
echo "BAD MESSAGE" | (cd APP_SUBDIR && npx commitlint)   # should print 2 errors
```

### 13. Wire portability bootstrap + install npm dependencies

**13a — Wire `prepare` hook in app `package.json`.** Add this entry to the `scripts` object in `APP_SUBDIR/package.json` so the bootstrap auto-runs on every fresh clone install:

```json
"scripts": {
  "prepare": "../scripts/setup-repo.sh"
}
```

The path is `../scripts/setup-repo.sh` because `package.json` lives in `APP_SUBDIR/` while the script lives at the app repo root in `scripts/`.

**13b — Install dependencies.** This triggers the `prepare` hook which runs `setup-repo.sh` and configures the app repo for portable worktrees:

```bash
cd APP_SUBDIR
npm install
```

Verify:

```bash
git -C APP_REPO_ROOT config --local --get worktree.useRelativePaths   # → true
```

**13c — Run meta repo bootstrap manually.** No Node package manager, so run the script directly once:

```bash
cd META_REPO_ROOT
./scripts/setup-repo.sh
```

Verify:

```bash
git -C META_REPO_ROOT config --local --get worktree.useRelativePaths   # → true
```

### 14. Activate PostToolUse hook

The `.claude/settings.json` was already written in step 2 with the correct absolute `APP_SUBDIR` path.

Instruct user: **Open `/hooks` in Claude Code, then dismiss.** The settings watcher only reloads files present when the session started — this dismissal forces a config reload within the current session.

### 15. Walk mcp-setup.md

Go through `APP_REPO_ROOT/mcp-setup.md` section by section. Complete only sections matching the confirmed service profile:
- Supabase MCP (if Supabase)
- GitHub MCP (always)
- Vercel plugin (if Vercel)
- Plain API (if Plain)
- Devtools-class browser MCP (always)
- Automation-class browser MCP (always)

Check off each section as completed.

### 16. Walk services-setup.md

Go through `APP_REPO_ROOT/services-setup.md` section by section. Complete only sections matching the confirmed service profile. Check off each section as completed.

### 17. Seed pipeline.md

Open `META_REPO_ROOT/pipeline.md`. Prompt user to fill:
- Project context (1-2 sentences)
- First active block (name, status, first task)

### 18. Completion checklist

Verify and check off every applicable item. Items not in the confirmed service profile are marked N/A.

**Always required:**
- [ ] `<project>-meta/` git repo initialized, default branch `main`, pushed to GitHub
- [ ] `<project>-app/` git repo initialized, default branch `staging`, pushed to GitHub
- [ ] Branch protection: meta `main`; app `main` + `staging` (no direct push)
- [ ] `.repo-class` + `.integration-branch` markers present in both repos
- [ ] `.githooks/pre-commit` + `pre-push` present + executable in both repos
- [ ] `scripts/setup-repo.sh` present + executable in both repos
- [ ] `app/lefthook.yml` wires canon `.githooks/pre-commit` + `pre-push` as additional commands (Pattern B from `skill-git-multi-agent.md §Hook integration patterns`)
- [ ] App `package.json` has `"prepare": "../scripts/setup-repo.sh"` and `@commitlint/cli`, `@commitlint/config-conventional`, `lefthook` in `devDependencies`
- [ ] Workspace `.mcp.json` present with GitHub MCP + one devtools-class + one automation-class browser MCP
- [ ] `.claude/settings.json` PostToolUse hook live (user has opened `/hooks`)
- [ ] `app/lefthook.yml` installed → `git commit` with bad message blocked by commitlint
- [ ] `app/app/commitlint.config.js` present
- [ ] `app/.nvmrc` present at repo root
- [ ] `app/.env.example` present
- [ ] `ci.yml` + `pr-base-guard.yml` present in `.github/workflows/`
- [ ] `meta/pipeline.md` open — user has filled project context + first block

**Conditional:**
- [ ] Supabase MCP configured and verified (if Supabase)
- [ ] GitHub MCP configured and verified (always)
- [ ] Vercel plugin authenticated (if Vercel)
- [ ] `staging-db.yml` present (if Supabase)
- [ ] `deploy-notify.yml` present (if Vercel + Slack)
- [ ] Plain API key set, `mcp-setup.md#plain` steps completed (if Plain)
- [ ] Railway project created, LiteLLM deployed, `/health` green (if LiteLLM on Railway)
- [ ] Slack channels created, webhooks set, Pipedream relay live (if Slack)
- [ ] Brevo API key set, domain verified (if Brevo)
- [ ] Polar org + products created, webhooks wired (if Polar)
- [ ] Sentry project created, DSN set, `@sentry/nextjs` installed (if Sentry)
- [ ] Matomo instance live, `trackEvent` utility wired (if Matomo)
- [ ] FirstPromoter account + `fpr.js` self-hosted, signup + sale hooks wired (if FirstPromoter)
- [ ] Pipedream workflow live, Railway webhook pointed at it (if Railway + Slack)

**Browser validation (always — no project is exempt):**
- [ ] One devtools-class browser MCP configured in `.mcp.json` and verified (page list returns non-error)
- [ ] One automation-class browser MCP configured in `.mcp.json` and verified (DOM snapshot returns a tree)
- [ ] `app/docs/playbook-browser-testing.md` present (project-local copy or pointer to `knowledge-base/reference/guidelines-browser-testing.md`)
- [ ] Emitted `meta/skills/skill-validate.md` has a §3 Browser MCP Validation section pre-wired
- [ ] Emitted `meta/skills/skill-review-code.md` (if project maintains its own copy) has the browser-validation row in the Phase 1 audit
- [ ] Evidence directory convention documented (where screenshots / console dumps / network lists / perf traces land — project-specific; default `~/Downloads/`)

**6-stage validation flow (always — no project is exempt):**
- [ ] Emitted `meta/principles.md` includes a §Workflow — canonical 6-stage flow section with the stage-to-skill mapping table
- [ ] Emitted `meta/skills/skill-validate.md` is project-extension form (references canon `knowledge-base/skills/skill-validate.md`); fires at stages 2 and 5; produces the Completion Report; no §Block Status Update in this file
- [ ] Emitted `meta/skills/skill-session-end-engineer.md` starts with a user-trigger-only top note, is paperwork-only at stage 6, and the only §Block Status Update in the meta/skills/ tree lives here
- [ ] Emitted `meta/skills/skill-session-end-{architect,data-architect,reviewer-code,reviewer-security}.md` each start with the user-trigger-only top note
- [ ] Emitted `meta/skills/skill-review-cycle.md` archival step references the same user-triggered invariant
- [ ] Emitted `meta/agents/engineer.md` §Block Completion encodes the 6-stage flow — no "PR-open = done" wording
- [ ] No emitted session-end skill pushes directly to a protected trunk branch — Git Sync steps go through a feature branch + PR (meta → main; app → staging; `hotfix/*` → main only)

Do not declare scaffolding done until all applicable items are checked.

### 19. Register the project with TRON-FLYNN

Add a row to `modes/flynn/projects.md`:

```
| <PROJECT_NAME> | <META_REPO_NAME>/agents/flynn-local.md | <META_REPO_NAME>/logs/flynn/ | <YYYY-MM-DD> |
```

This makes the project discoverable for future `AUDIT` and `UPGRADE PROJECT` sessions.
