# Skill: Project Scaffold

**Purpose:** Exact procedural sequence to scaffold a new 42Labs project from zero.

**Prerequisite:** `skills/skill-project-profile.md` must have run and locked `{profile, values}`. Do not proceed without them.

**Scope:** Scaffolds the workflow infrastructure (meta repo, config, CI, hooks, portable-worktree bootstrap, MCPs, services) around a Next.js application. Does NOT create the Next.js app itself — the operator runs `npx create-next-app`, and they must do it at **step 1b, before any kit file lands in `APP_SUBDIR`**. `create-next-app` refuses to run in a directory holding files it doesn't recognise, and step 2 puts two there.

**Templates source of truth:** the scaffold kit at `tron-app/templates/project-scaffold/templates/` — `$SCAFFOLD_ROOT/../../templates/project-scaffold/templates`, referred to below as `$TPL`. Every file copy step reads from there, and only from there. The kit's current version is in its `CHANGELOG.md`; record that version in the completion report.

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

### 1b. The operator creates the app — now, before anything else lands in it

**Blocking.** `npx create-next-app` aborts if `APP_SUBDIR` already holds files it doesn't recognise, and step 2 copies `AGENTS.md` + `commitlint.config.js` into exactly that directory. So the app is created **first**, into an empty `APP_SUBDIR`:

```bash
cd APP_REPO_ROOT
npx create-next-app@latest app     # the operator's call: TypeScript, router, lint, alias
```

Wait for it. If the operator would rather not decide the stack yet, stop here — do not proceed and then "come back to it": every later step (npm install, lefthook, commitlint, the `prepare` hook) assumes a real `package.json` in `APP_SUBDIR`.

### 2. Copy the kit — whole tree, then trim

The kit is the payload; copy **all of it**, then remove what the profile excludes. Never hand-pick a
file list — a list drifts the moment the kit gains a file, and a project scaffolded from a stale list
is silently missing canon.

```bash
cp -R $TPL/AGENTS.md $TPL/.mcp.json  WORKSPACE_PATH/
cp -R $TPL/.claude/.                 WORKSPACE_PATH/.claude/
cp -R $TPL/meta/.                    META_REPO_ROOT/
cp -R $TPL/app/.                     APP_REPO_ROOT/     # merges into the app created in 1b
```

The last line lands `AGENTS.md` and `commitlint.config.js` **beside** the Next.js app `create-next-app`
already wrote in `APP_SUBDIR` — it adds files, it never overwrites the app. That ordering is exactly why
step 1b is blocking.

Everything the kit ships now exists in the new project — agents, skills, hooks, scripts, CI workflows,
log directories (`.gitkeep`-tracked), the lens, `meta/tron/roles.yaml`, the block and pipeline
templates. Steps 3–5 fill it, trim it, and delete the parts this project doesn't use.

Verify the copy: `diff -r $TPL/meta META_REPO_ROOT` and `diff -r $TPL/app APP_REPO_ROOT` should report
only files you have not filled yet (and the app's own files) — nothing "only in `$TPL`".

### 3. Fill the workspace + meta files

| File | Fill |
|--------|------|
| `WORKSPACE_PATH/AGENTS.md` | `<PROJECT_NAME>`, `<META_REPO_NAME>`, `<APP_REPO_NAME>`, agent paths |
| `WORKSPACE_PATH/.claude/settings.json` | `<ABSOLUTE_PATH_TO_APP_SUBDIR>` → `APP_SUBDIR`; drop the Vercel plugin if non-Vercel; use `npm test --if-present` so the hook doesn't error before the app has tests |
| `WORKSPACE_PATH/.mcp.json` | Verbatim — GitHub MCP (always) plus one devtools-class and one automation-class browser MCP (always); add per-profile MCPs (Supabase, Plain) if confirmed |
| `META_REPO_ROOT/**` | Every `<PROJECT_NAME>` and `<PLACEHOLDER>` token, in every copied file |
| `META_REPO_ROOT/tron/roles.yaml` | The project's fleet — role → model, persona path, capability class. Leave the shipped default if the project has no TRON fleet decision yet |
| `META_REPO_ROOT/skills/skill-linear-cards.md` | §3's seed placeholders — `<LINEAR_TEAM>`, `<LINEAR_PROJECT>`, `<DEFAULT_STATE>`, `<DEFAULT_ASSIGNEE>`, `<DEFAULT_PRIORITY>`, `<PROJECT_LABELS>`, `<SCOPE_LABELS>` — from the profile's Linear values. **`<AGENT_ROLE>` is not a seed token**: each agent substitutes its own persona at card-writing time. Leave it standing |
| `META_REPO_ROOT/.github/workflows/canon-drift.yml` | `<CANON_KB_REPO>` / `<CANON_SCAFFOLD_REPO>` from the profile's shared-KB answer. **No shared KB → delete this workflow and `meta/scripts/canon-drift-check.sh`**; a drift check with no canon to check against fails on the first push |

**The lens has placeholders the token grep cannot see.** Two of them are plain strings, not `<TOKEN>`s, so step 6 will never flag them — fill both here or the project ships a dashboard permanently titled "PROJECT":

| File | Fill |
|--------|------|
| `META_REPO_ROOT/lens/build.mjs` | `const PROJECT_NAME = "PROJECT";` → the real name |
| `META_REPO_ROOT/lens/package.json` | `"name": "project-lens"` → `"<project>-lens"` |

Confirm the six log directories survived the copy: `meta/logs/{architecture,data-architect,engineering,review-code,review-security,flynn}/`.

> TRON's own onboarding is out of scope. TRON seeds `tron.md` and `skill-tg-comms.md` itself when the operator activates it — do not pre-create them.

### 4. Fill and trim the app files

| File | Fill |
|--------|-------|
| `APP_REPO_ROOT/.nvmrc` | `<NODE_LTS_VERSION>` → `NODE_LTS_VERSION` |
| `APP_REPO_ROOT/.env.example` | Project-specific vars |
| `APP_REPO_ROOT/docs/playbook-infra.md` | Project-specific URLs |
| `APP_SUBDIR/AGENTS.md` | Tech stack, project name |
| `APP_SUBDIR/.gitignore` | Append `CLAUDE.md` — the agent doc the project tracks is `AGENTS.md`; a host-runtime file that appears beside it stays local (the meta repo already ships this rule; `create-next-app`'s `.gitignore` does not) |

`lefthook.yml`, `commitlint.config.js`, `docs/playbook-browser-testing.md`, `docs/guidelines-coding.md`, `.githooks/`, and `scripts/` are taken verbatim — do not edit them per project. A per-project deviation belongs in the kit, not in the copy.

**Profile-trim pass.** Four files ship with all-service content and MUST be trimmed to the confirmed profile before continuing:

| File | What to trim |
|------|--------------|
| `APP_REPO_ROOT/.env.example` | Remove env-var blocks for every unconfirmed service (Supabase, Vercel, Sentry, Matomo, Brevo, Polar, Plain, FirstPromoter, Slack) |
| `APP_REPO_ROOT/mcp-setup.md` | Remove sections for unconfirmed integrations (Supabase MCP, Vercel plugin, Plain API). GitHub MCP always stays |
| `APP_REPO_ROOT/services-setup.md` | Remove sections for unconfirmed services (Railway/LiteLLM, Slack, Brevo, Polar, Sentry, Matomo, FirstPromoter, Pipedream) |
| `APP_REPO_ROOT/docs/playbook-infra.md` | Remove service sections (Supabase, Vercel, Slack, Brevo, Polar, Sentry, etc.) not in profile; collapse Secrets Reference to only the secrets the project actually owns |

Add a banner at the top of each trimmed file naming the active profile: "**Profile at scaffold:** \<list\>. Other services intentionally omitted — add them later through the upgrade flow if the project takes them on."

**Delete what the profile excludes.** The whole kit was copied in step 2; now remove what this project doesn't use:

```bash
# LiteLLM on Railway not in profile → the infra templates have no business here
rm -rf APP_REPO_ROOT/infra
```

### 4b. Portable-worktree bootstrap

Implements `42hq/knowledge-base/principles-base.md §14 Portability — Relative-path worktrees`. Required before either repo gets its first worktree.

**Verify Git version (≥ 2.48):**

```bash
git --version
```

If older, fail loudly — the operator must `brew upgrade git` (or platform equivalent) before continuing.

**Make the copied scripts and hooks executable.** Step 2 brought `scripts/setup-repo.sh` and `.githooks/` into both repos; `cp` does not always preserve the mode bit.

```bash
chmod +x APP_REPO_ROOT/scripts/*.sh  META_REPO_ROOT/scripts/*.sh
chmod +x APP_REPO_ROOT/.githooks/*   META_REPO_ROOT/.githooks/*
```

Their bodies stay **byte-identical to the kit** — a future kit fix must reapply with `diff` confidence. Only the leading comment and final echo may name the project.

The app repo wires `setup-repo.sh` into `package.json prepare` — step 13, once `npx create-next-app` has produced a `package.json`. The meta repo has no Node package manager, so it runs the script manually once per clone.

**Write repo-class + integration-branch markers** (read by the hooks at runtime — without them hooks are no-op, per `principles-base.md §14`):

```bash
echo "meta"    > META_REPO_ROOT/.repo-class
echo "main"    > META_REPO_ROOT/.integration-branch
echo "app"     > APP_REPO_ROOT/.repo-class
echo "staging" > APP_REPO_ROOT/.integration-branch
```

Per `principles-base.md §14` integration branch convention: canon + meta use `main`; apps use `staging` (canonical, not optional).

### 5. Trim the CI workflows

All workflows came over in step 2. Keep `ci.yml` and `pr-base-guard.yml` always; **delete** every one below the project didn't confirm:

| Workflow | Keep only if |
|----------|----------|
| `staging-db.yml` | Supabase |
| `deploy-notify.yml` | Vercel + Slack |
| `release-please.yml` | Public changelog (also delete `release-please-config.json` + `.release-please-manifest.json` if dropped) |
| `release-notify.yml` | Subscriber emails + Brevo |
| `e2e.yml` | Playwright |
| `stress.yml` | Load requirements |

They live in `APP_REPO_ROOT/.github/workflows/`. A workflow left behind for a service the project doesn't have will fail on the first push — an unused workflow is a defect, not a spare.

### 6. Verify no `<PLACEHOLDER>` tokens remain

Catch every token, not just the ones this skill happens to name — the kit's full token list is in `$TPL/../tokens.md`, and a seed is not complete while a *seed* token survives:

```bash
grep -rnE "<[A-Z][A-Z0-9_]+>" WORKSPACE_PATH/ --exclude-dir=.git --exclude-dir=node_modules
```

Fix every hit **except the stencils** — tokens that are meant to survive, because they're filled per *use*, not per project:

| Survives | Why |
|:--|:--|
| `META_REPO_ROOT/blocks/block-template.md` — `<ID>`, `<Title>`, … | It's the stencil every future block is cut from. Filling it destroys it |
| `<AGENT_ROLE>` in `skills/skill-linear-cards.md` | Each agent stamps its own persona when it writes a card |

Anything else still bracketed is an unfinished seed. Fix it before continuing.

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

The kit ships the script that does this — `scripts/protect-branches.sh`, copied into the app repo at step 2. Run it; do not hand-roll the API call. (A second, weaker inline policy is how a repo ends up with `enforce_admins: false` and force-push still allowed.)

Meta: protect `main` only (the only branch — meta has no `staging`).
App: protect both `main` (production) and `staging` (integration).

```bash
cd APP_REPO_ROOT
scripts/protect-branches.sh GITHUB_ORG/PROJECT_NAME-meta main
scripts/protect-branches.sh GITHUB_ORG/PROJECT_NAME-app  main staging
```

The script requires an authenticated `gh` with admin on the repo, and it is idempotent. It leaves `required_status_checks.contexts` empty — once CI has run once, set it to the job names so a protected branch actually gates on green.

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

`.claude/settings.json` was copied in step 2 and filled with the absolute `APP_SUBDIR` path in step 3.

Tell the operator: **open the `/hooks` panel, then dismiss it.** The settings watcher only reloads files that were present when the session started — the dismissal forces a config reload inside the current session.

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

Open `META_REPO_ROOT/pipeline.md`. Prompt the operator to fill:
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
- [ ] `ci.yml` + `pr-base-guard.yml` present in `.github/workflows/`; every unconfirmed workflow deleted
- [ ] `meta/lens/build.mjs` + `meta/lens/package.json` carry the real project name — not `"PROJECT"` / `"project-lens"`
- [ ] `meta/skills/skill-linear-cards.md` §3 seed placeholders filled (`<AGENT_ROLE>` deliberately left standing)
- [ ] `meta/.github/workflows/canon-drift.yml` filled — or deleted, with `meta/scripts/canon-drift-check.sh`, if there's no shared KB
- [ ] `meta/blocks/block-template.md` still holds its `<ID>` / `<Title>` stencils (filling them breaks every future block)
- [ ] The project has a row in FLYNN's registry (step 19)
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

The registry lives at `$SCAFFOLD_ROOT/../flynn/projects.md` — inside the TRON checkout, beside FLYNN, not in the project you just built. It is a local operator file (gitignored: it names private client work), so on a fresh machine **it will not exist**. Create it with this exact header, then append the row:

```markdown
# Projects — TRON-FLYNN registry

Every project FLYNN knows about. Written by `/tron-scaffold` at seed, read at session start.

| Project | Local context | Logs | Registered |
|:--|:--|:--|:--|
| <PROJECT_NAME> | <META_REPO_NAME>/agents/flynn-local.md | <META_REPO_NAME>/logs/flynn/ | <YYYY-MM-DD> |
```

If the file already exists, append the row only — never rewrite rows you didn't add.

This registry is what makes the project discoverable for later audit and upgrade sessions. A scaffold is not finished until the row is there.
