# Skill: Data Architect Session End

**This skill runs only when the user explicitly triggers session-end.** Do not run automatically after any check passes or because the conversation feels "done." The user-trigger-only rule is the canonical 6-stage flow's stage 6 — see `{shared_knowledge_path}/principles-base.md §12` and the project's `principles.md §Workflow`.

Read this file **now** — do not rely on memory from session start.

---

## 1. Validation

- [ ] Verify all outputs are complete and actionable
- [ ] Verify the user approved any significant proposals

## 2. Record Assessments

- [ ] Lightweight assessments → inline note in session log
- [ ] Significant assessments → full record in `logs/data-architect/da-YYMMDD-{title}.md`
- [ ] Check: do any prior assessments in `logs/data-architect/` need to be marked superseded?

## 3. Update Registries

**Answer each explicitly. Do not skip any row.**

| Registry | Affected? | Updated? |
|:---------|:----------|:---------|
| `logs/data-architect/registry-pii-inventory.md` | YES / NO | ✅ / N/A |
| `logs/data-architect/registry-data-lineage.md` | YES / NO | ✅ / N/A |
| `logs/data-architect/registry-caching-contracts.md` | YES / NO | ✅ / N/A |

## 4. Core Docs Staleness Check

**Answer each explicitly. Do not skip any row.** Canonical list: `principles.md` §Core Docs.

| Doc | Affected? | Updated? |
|:----|:----------|:---------|
| `context.md` | YES / NO | ✅ / N/A |
| `pipeline.md` | YES / NO | ✅ / N/A |
| `principles.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/app/CLAUDE.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/app/RULES.md` | YES / NO | ✅ / N/A |
| `app/README.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/docs/guidelines-design.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/docs/guidelines-brand.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/docs/playbook-infra.md` | YES / NO | ✅ / N/A |

## 5. Git Sync

**Feature branch + PR in all cases. Never push directly to a protected trunk branch.**

- Meta repo: branch → commit → `git push -u origin {branch}` → `gh pr create --base main`.
- If the data-architect assessment touches app-repo files (e.g., migration SQL, schema docs): separate PR to app, default base `staging` (or `main` if the project runs single-branch); `hotfix/*` → `main` only.
- Monitor CI until green. Never arm auto-merge. Merge is performed by the agent once authorized (by the user, or by the supervising process per its merge policy) — then monitor the merge through to a verified deploy.

## 6. Final Report

- [ ] Final checklist for user — numbered list of remaining decisions or actions
- [ ] **Shared-KB session end:** run `{shared_knowledge_path}/meta/agent.md §4` (lessons) and `§7.2` (warning closure — verified fix only; reviewers never close).
