---
name: skill-session-end-architect
description: Architect stage-6 close-out — record decisions/ADRs, Core Docs staleness, git sync, session log.
source: canon
canon_version: HEAD
---

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

Rows are the Core Docs that ship with the scaffold. Skip any row whose doc this project doesn't ship; add a row for any project doc your work changed.

| Doc | Affected? | Updated? |
|:----|:----------|:---------|
| `context.md` | YES / NO | ✅ / N/A |
| `pipeline.md` | YES / NO | ✅ / N/A |
| `principles.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/docs/guidelines-coding.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/docs/playbook-infra.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/app/CLAUDE.md` | YES / NO | ✅ / N/A |

## 4. Git Sync

Follow `skills/skill-worktree-and-branching.md` for the full procedure (feature branch + worktree + PR + monitored merge; never commit/push on a protected branch; never arm auto-merge). Project delta: meta-repo work PRs to `main`.

## 5. Logging

- [ ] Create session log at `logs/architecture/log-YYMMDD-HHMM-{description}.md` using the **session-log format** in `ref-session-log-format.md`
- [ ] Final checklist for user — numbered list of remaining decisions or actions
- [ ] **Shared-KB session end:** run `{shared_knowledge_path}/meta/agent.md §4` (lessons) and `§7.2` (warning closure — verified fix only; reviewers never close).
