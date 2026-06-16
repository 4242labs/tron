---
name: skill-session-end-engineer
description: Paperwork-only close-out at stage 6 of the DoD flow; status flip, archive, log, doc sync. Validation is a precondition.
source: canon
canon_version: HEAD
---

# Skill: Engineer Session End

**This skill runs only when the user explicitly triggers session-end.** Do not run automatically after PR merge, after validation passes, or because the conversation feels "done." The user-trigger-only rule is the canonical 6-stage flow's stage 6 — see `{shared_knowledge_path}/principles-base.md §12` and the project's `principles.md §Workflow`.

Read this file **now** — do not rely on memory from session start.

---

## Precondition: validation must already have run

This skill is **paperwork only**. It does not validate. Validation lives in `skills/skill-validate.md` (the project's extension of `{shared_knowledge_path}/skills/skill-validate.md`) and must already have produced a clean Completion Report at:

- **Stage 2** — local validation (pre-PR), all ACs `PASS`.
- **Stage 5** — post-merge re-validation (on trunk), all ACs `PASS`, no regressions, **and a verified deploy where the block requires one** (a merge that is not deploy-verified is not done).

If either is missing or has any `UNVERIFIED` row → STOP. Run validation first, then return here. Do not attempt to substitute alternative evidence (`{shared_knowledge_path}/principles-base.md §11`).

Reviewers (code, security, data, branding/design) do **not** dispatch from this skill — they are dispatched by the supervising process on its review cadence (canon Reviewer-trigger map, `principles-base.md §12`).

---

## 1. User Acknowledgment Gate

Before any status flip, surface in chat:

```
Completion Report: blocks/<id>/completion-report.md — N/N PASS (stage 2)
Post-merge re-validation: N/N PASS (stage 5)
Trigger session-end? (explicit yes required)
```

Ambiguous responses ("looks good", "sounds fine", "ok") are **not** authorization — re-prompt for an explicit go-ahead. If the user pushes back on a verified PASS without producing new evidence, do not capitulate (`principles-base.md §13`). Re-state the evidence; if the user produces new evidence, re-open the relevant criterion via `skill-validate.md`.

---

## 2. Pre-Close Checks

- [ ] All tasks completed this session are tested and committed (already enforced by stage-2 validation; double-check no last-minute uncommitted edits)
- [ ] No undisclosed hard blocks this session (per `{shared_knowledge_path}/principles-base.md §11`). Any hard block must have been escalated when detected — not deferred to this gate.

---

## 3. Core Docs Staleness Check

**Answer each explicitly in the session log. Do not skip any row.** Canonical Core Docs list lives in `principles.md §Core Docs`.

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

Also sweep the project structure tree (CLAUDE.md / AGENTS.md): any new files created this session (routes, lib modules, components, migrations) must appear there. Missing entries → add them now.

---

## 4. Git Sync

**Feature branch + PR in all cases. Never push directly to a protected trunk branch.**

- **Meta repo:** branch → commit → `git push -u origin {branch}` → `gh pr create --base main`.
- **App repo (two-gate):** feature branch → PR → `staging` (default). `hotfix/*` branches → PR → `main` only.
- **App repo (single-branch, if the project doesn't run a staging gate):** feature branch → PR → `main`.
- Monitor CI until green. Never arm auto-merge. Merge is performed by the engineer once authorized (by the user, or by the supervising process per its merge policy) — then monitor the merge through to a verified deploy.

---

## 5. Logging

- [ ] Create session log at `logs/engineering/log-YYMMDD-HHMM-{description}.md` using the **session-log format** in `skills/ref-session-log-format.md`
- [ ] Final checklist for user — numbered list of remaining manual actions
- [ ] **Shared-KB session end:** run `{shared_knowledge_path}/meta/agent.md §4` (lessons) and `§7.2` (warning closure — verified fix only; reviewers never close).

---

## 6. Block Status Update *(stage 6 — the only status flip in this project)*

**Runs only after** §1 user acknowledgment is explicit, §2–§5 are clean, `skill-validate.md` has produced clean stage-2 and stage-5 Completion Reports, and — where the block declares a deploy check — the change has deployed clean and been verified post-deploy. This is the sole location in the project where `**Status:** ✅ Done` is set.

For each block completed this session:

- [ ] Update block doc status: `**Status:** ✅ Done`
- [ ] Add `**Completed:** YYYY-MM-DD` and the PR link(s)
- [ ] Move the block file from `blocks/` to `blocks/archive/` (`git mv blocks/{id}.md blocks/archive/{id}.md`); the Completion Report travels with it
- [ ] Update `pipeline.md` status markers for the block's tasks
- [ ] Commit the status-flip + archival as part of a feature branch → PR (per §4 Git Sync)
- [ ] Report to user: block completion summary, PR links, Completion Report path

Cycle-review archival runs under the same user-triggered invariant — see `skill-review-cycle.md`.

---

**Last Updated:** 2026-05-07 — Split: validation extracted into `skill-validate.md` (fires at stages 2 and 5); this skill is now paperwork-only at stage 6. Removed §0 Post-Merge Re-Validation, §0.5 Critic Gate, build verification — all moved to validate.
