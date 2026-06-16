# Skill: Architect Session End

**This skill runs only when the user explicitly triggers session-end.** Do not run automatically after any check passes or because the conversation feels "done." The user-trigger-only rule is the canonical 6-stage flow's stage 6 — see `{shared_knowledge_path}/principles-base.md §12` and the project's `principles.md §Workflow`.

Read this file **now** — do not rely on memory from session start.

---

## 1. Validation

- [ ] Verify all outputs are complete and actionable
- [ ] Verify the user approved any significant decisions

## 2. Record Decisions

- [ ] Lightweight decisions → note in session log
- [ ] Significant decisions → full ADR in `logs/architecture/adr-YYMMDD-{title}.md`
- [ ] Check: do any prior ADRs in `logs/architecture/` need to be marked superseded?

## 3. Core Docs Staleness Check

**Answer each explicitly in the session log. Do not skip any row.** Canonical list: `principles.md` §Core Docs.

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

## 4. Git Sync

**Feature branch + PR in all cases. Never push directly to a protected trunk branch.**

- Meta repo: branch → commit → `git push -u origin {branch}` → `gh pr create --base main`.
- Monitor CI until green. Never arm auto-merge. Merge is performed by the agent once authorized (by the user, or by the supervising process per its merge policy) — then monitor the merge through to a verified deploy.

## 5. Logging

- [ ] Create session log at `logs/architecture/log-YYMMDD-HHMM-{description}.md` using the **session-log format** in `skills/ref-session-log-format.md`
- [ ] Final checklist for user — numbered list of remaining decisions or actions
- [ ] **Shared-KB session end:** run `{shared_knowledge_path}/meta/agent.md §4` (lessons) and `§7.2` (warning closure — verified fix only; reviewers never close).
