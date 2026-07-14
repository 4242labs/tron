# Skill: Project Upgrade

**Purpose:** Procedural remediation for every gap found by `skills/skill-project-audit.md`, and execution
of every removal approved from `skills/skill-project-discard.md`.

**Prerequisite:** Gap Report produced and user-confirmed. Discard Report produced and ruled on **per item**.
Service profile locked.

**Templates source of truth:** `tron/tron-app/templates/project-scaffold/templates/`.

Additions first, removals last — see **Removals** below for why. Within the additions, apply Critical gaps
first, then Important, then Nice-to-have; within each tier, follow the ordering below.

---

## Per-Gap Procedure

For each ❌ or ⚠️ item:

1. **Branch** from staging: `git checkout -b chore/upgrade-<area>`
   - Group related gaps into one branch (e.g. all CI workflows = one branch)
   - Unrelated gaps = separate branches
2. **Apply** the gap:
   - Missing file: copy from `tron/tron-app/templates/project-scaffold/templates/`, fill placeholders
   - Partial/misconfigured: show the diff to the user, wait for explicit confirmation before writing
3. **Commit**: `chore(meta): add <artifact>` or `chore(app): add <artifact>`
   - Subject must be fully lowercase
4. **Open PR** to `staging` — even for meta-only changes (never commit directly to staging)
5. **Merge PR** after review
6. **Mark gap** ✅ in the gap report
7. Move to next gap

---

## Critical Gap Order

Apply in this exact order — each step establishes safety or capability required by later steps:

### 1. Branch protection on `main` + `staging`

Prevents accidental direct pushes while upgrading. Do this first — before any other changes.

```bash
# For each repo (meta + app), protect main and staging:
gh api repos/<org>/<repo>/branches/main/protection \
  --method PUT \
  --input - <<'EOF'
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null
}
EOF
```

### 2. `.claude/settings.json` + PostToolUse hook

Copy `templates/.claude/settings.json` to workspace root `.claude/settings.json`.
Fill `<ABSOLUTE_PATH_TO_APP_SUBDIR>` with the absolute path to the Next.js `app/` subdir.
Remove Vercel plugin if non-Vercel project.

After writing: instruct user to open `/hooks` in Claude Code → dismiss. The watcher requires this to reload config.

Verify: make a harmless Edit → confirm `npm test` runs in Claude terminal with no path errors.

### 3. `meta/pipeline.md`

Copy `templates/meta/pipeline.md`. Prompt user to fill project context + first active block.
Preserve the **Format contract** block (phase headers, `ID | Task | Status | Notes`, emoji-only Status, block-file ref in Notes) — a deterministic reader depends on it. If upgrading an existing pipeline, reshape it to that contract rather than dropping the contract.
Branch: `chore/upgrade-meta-pipeline`

### 4. `meta/agents/` + `meta/skills/`

Copy all 6 core agent files and 10 core skill files from templates. Fill `<PROJECT_NAME>` tokens.

> TRON is out of scope here. If the project uses TRON, TRON's own onboarding owns the copy of `tron.md` and `skill-tg-comms.md` — do not include them in the upgrade pass.

**Existing agent/skill files:** show diff before overwriting. Never silently replace — the project may have local customizations that must be preserved.

Branch: `chore/upgrade-meta-agents-skills`

### 5. `lefthook.yml` + `commitlint.config.js`

- Copy `templates/app/lefthook.yml` to app repo root (no dot prefix)
- Copy `templates/app/app/commitlint.config.js` to Next.js `app/` subdir
- Install: `cd <app_repo_root> && npx lefthook install`

Verify: `git commit --allow-empty -m "BAD FORMAT"` → blocked by commitlint.

Branch: `chore/upgrade-app-lefthook`

### 6. `ci.yml` + `pr-base-guard.yml`

Copy both from templates to `.github/workflows/`. Fill project-specific paths.
Verify: push branch → CI runs → check Actions tab.

Branch: `chore/upgrade-ci`

### 7. Portable-worktree bootstrap (`scripts/setup-repo.sh` + `prepare` wiring)

Implements `42hq/knowledge-base/principles-base.md §14 Portability`. Apply to **both** repos (app and meta) and ensure worktrees live under `<workspace>/worktrees/`, not `~/worktrees/`.

**Pre-check:** `git --version` must be ≥ 2.48 on every contributor's machine. If older, instruct user to `brew upgrade git` (macOS) or platform equivalent before continuing.

**Steps (one branch per repo, paired PRs):**

1. Create `<workspace>/worktrees/` if missing.
2. Copy `tron/tron-app/templates/project-scaffold/templates/meta/scripts/setup-repo.sh` → `<repo>/scripts/setup-repo.sh` (`chmod +x`). Body must remain byte-identical to canonical; only the leading comment block and final echo line may be project-localized.
3. **App repo only:** add `"prepare": "../scripts/setup-repo.sh"` to the `scripts` object in `<app>/app/package.json`. (Path is `../scripts/setup-repo.sh` because `package.json` is in the Next.js subdir.)
4. **App repo:** run `cd <app>/app && npm install` (or `pnpm install`) — triggers the `prepare` hook which runs the bootstrap.
   **Meta repo:** run `cd <meta> && ./scripts/setup-repo.sh` manually (no Node package manager).
5. Verify on both: `git config --local worktree.useRelativePaths` returns `true`.
6. If existing worktrees were created before this upgrade, the script's `git worktree repair` call converts their pointers to relative paths automatically.
7. Update `meta/skills/skill-worktree-and-branching.md` so worktree base is `<workspace>/worktrees/` (not `~/worktrees/`) and includes a §Setup section pointing to `scripts/setup-repo.sh`. If existing worktrees live under `~/worktrees/`, migrate them: `git worktree move ~/worktrees/<repo>--<branch> <workspace>/worktrees/<repo>--<branch>` (or remove + recreate if dirty).
8. Update app repo `README.md` to mention Git ≥ 2.48 requirement and the auto-bootstrap on install.

Branches: `chore/upgrade-portable-worktree-app` and `chore/upgrade-portable-worktree-meta`. Open as a paired set (same slug, different repo) per the cross-repo rule in `skill-worktree-and-branching.md`.

---

## Important Gap Order

After all Critical gaps are closed:

- `meta/context.md` (if missing, or missing its `## Deploy` section — Enabled + Success check), `meta/principles.md` (ensure the definition-of-done carries the deploy gate: merged ≠ done; deploy-clean + verify required when a block declares a deploy check), `meta/CLAUDE.md` (if missing)
- `meta/blocks/block-template.md` — ensure it carries the `Merge:` (`self | needs-user`) and `Deploy:` (`none | check`) header fields after `Reviewer class:`
- `app/.nvmrc` at repo root (if missing or wrong location)
- `app/.env.example` (if missing or incomplete)
- `app/app/CLAUDE.md` (if missing)
- `mcp-setup.md` + MCP configuration (if missing)
- `services-setup.md` (if missing)
- `docs/playbook-infra.md` (if missing)
- Conditional CI workflows applicable to the project profile (staging-db, deploy-notify, etc.)
- Memory initialization (if missing)

---

## Nice-to-Have Gap Order

- Remaining optional CI workflows (release-please, release-notify, e2e, stress)
- Ref format files (`ref-*.md`)
- Log subdirectory structure
- Block template
- Services not yet configured (each in its own branch)

---

## Removals

The approved lines of the Discard Report — and **only** those lines. An item that was rejected, or left
uncertain, or never ruled on, is not removed. If the operator approved the report in bulk rather than line
by line, go back and get the per-item answers first.

Removals run **after** every addition is merged. An addition can reveal that a "dead" file was the only
copy of something canon now wants in a different place — and it is cheaper to skip a removal than to
resurrect one.

Per approved item:

1. **Branch** from staging: `git checkout -b chore/kondo-discard-<area>`
   - Group related removals into one branch (all leftover CI workflows = one branch)
   - Removals never share a branch with additions — a revert must be able to take back the deletion alone
2. **Re-verify at the moment of deletion.** The evidence was gathered before the additions landed. Re-run
   the reference grep. If anything now points at the file, **stop** — the item goes back to the operator
3. **Delete** with `git rm` (files) / `git branch -d` + `git push origin --delete` (branches) /
   `git worktree remove` + `git worktree prune` (worktrees). Never `rm -rf` a tracked path
4. **Commit**: `chore(meta): remove <artifact>` / `chore(app): remove <artifact>` — subject fully lowercase,
   body naming the evidence ("no database in profile; no inbound references")
5. **Open PR** to `staging`. Removals are reviewed like any other change — never a direct commit
6. **Merge**, then mark the line executed in the Discard Report

**Stop conditions.** Abandon the removal and return to the operator if: a reference appears that wasn't
there before; the branch or worktree has gained a commit or an open PR since the sweep; deleting it would
need a history rewrite; or the item turns out to touch `.env`, application source, or tests. A removal you
are not certain of is a removal you do not make.

---

## Post-Upgrade Re-Audit

After all gaps are applied and all approved removals are merged:

1. Re-run `skills/skill-project-audit.md` scoped to the confirmed service profile
2. Every applicable item must score ✅ — no ⚠️ or ❌ remain
3. Re-run `skills/skill-project-discard.md`. It must come back empty of proposals — anything it still finds
   is either a removal that didn't land, or something an addition dragged in
4. Report final score to the user
5. If any items are still ⚠️ or ❌, apply them before declaring done

Do not declare the upgrade complete until the re-audit score is 100% and the discard sweep is clean.

---

## Completion

Upgrade is complete when:
- [ ] Re-audit scores 100% on all items applicable to the confirmed service profile
- [ ] Re-run discard sweep proposes nothing new
- [ ] Every approved removal is merged; every rejected one is recorded as rejected, so the next run doesn't re-propose it
- [ ] Browser MCPs configured and verified (both classes — no project is exempt), and `app/docs/playbook-browser-testing.md` present
- [ ] Emitted completion-gate and code-review skills have browser-validation wiring present
- [ ] All PRs merged to `staging`
- [ ] User has confirmed the upgrade is done
