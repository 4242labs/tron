---
name: skill-session-end-reviewer-security
description: Security reviewer close-out — Core Docs staleness flags, persist findings via PR, warning closure.
source: canon
canon_version: HEAD
---

# Skill: Security Reviewer Session End

**This skill runs only when the user explicitly triggers session-end.** Do not run automatically after the review report is produced. The user-trigger-only rule is the canonical 6-stage flow's stage 6 — see `{shared_knowledge_path}/principles-base.md §12` and the project's `principles.md §Workflow`.

Read this file **now** — do not rely on memory from session start.

---

## 1. Core Docs Staleness Check

**Answer each explicitly in the review report. Do not skip any row.** Canonical list: `principles.md` §Core Docs.

| Doc | Staleness found? | If yes, flagged in findings? |
|:----|:-----------------|:-----------------------------|
| `context.md` | YES / NO | ✅ / N/A |
| `pipeline.md` | YES / NO | ✅ / N/A |
| `principles.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/app/CLAUDE.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/app/RULES.md` | YES / NO | ✅ / N/A |
| `app/README.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/docs/guidelines-design.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/docs/guidelines-brand.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/docs/playbook-infra.md` | YES / NO | ✅ / N/A |

## 2. Persist Review Report

- [ ] Save review report to `logs/review-security/YYMMDD-HHMM-security-review-{scope}.md` using the **review report format** in `ref-review-report-format.md`
  - Include: outstanding findings table, baseline commit SHA, recommended next review trigger
- [ ] Persist via a feature branch + worktree + PR — never commit on the base branch (per `skill-worktree-and-branching.md`). Meta repo: branch → commit → `git push -u origin {branch}` → `gh pr create --base main`; monitor CI, merge once authorized.
- [ ] Report any unresolved items to user
- [ ] **Shared-KB session end:** run `{shared_knowledge_path}/meta/agent.md §4` (lessons) and `§7.2` (warning closure — verified fix only; reviewers never close; per §3.2 active warnings naming this project must appear in the outstanding findings table).
