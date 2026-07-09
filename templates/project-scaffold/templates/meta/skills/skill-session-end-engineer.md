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

## The 6-Stage DoD Flow (context)

This skill owns **stage 6 only**. The full flow is mapped here for orientation — not for re-execution from this skill. Canon: `{shared_knowledge_path}/principles-base.md §12`, `principles.md §Workflow`.

| Stage | What | Owner / where |
|:--|:--|:--|
| 1 | Build — all tasks coded, tested locally, committed | engineer |
| 2 | Local validation (pre-PR) — Completion Report, every AC PASS | `skill-validate.md` |
| 3 | User-test gate — User Verification List, hand off to user | `skill-validate.md §5` |
| 4 | User approves → PR → CI green → authorized merge (engineer merges, monitors to verified deploy; auto-merge never armed) | engineer |
| 5 | Post-merge re-validation on trunk + deploy verification + self-attest | `skill-validate.md` |
| 6 | User acknowledges → triggers session-end → status flip, archive, doc sync | **this skill** |

**Reading discipline:** read `skill-validate.md` at every stage-2 and stage-5 invocation; read this skill only at stage 6. Never rely on memory. Block-status flip, block-file archival, and pipeline ✅ happen **only** at stage 6 under explicit user trigger — never inside validate.

---

## Precondition: validation must already have run

This skill is **paperwork only**. It does not validate. Validation lives in `skills/skill-validate.md` (the project's extension of `{shared_knowledge_path}/skills/skill-validate.md`) and must already have produced a clean Completion Report at:

- **Stage 2** — local validation (pre-PR), all ACs `PASS`.
- **Stage 5** — post-merge re-validation (on trunk), all ACs `PASS`, no regressions, **and a verified deploy where the block requires one** (a merge that is not deploy-verified is not done).

If either is missing or has any `UNVERIFIED` row → STOP. Run validation first, then return here. Do not substitute alternative evidence — see the no-silent-downgrade / legal-moves rule in `skill-validate.md §Constraints`.

Reviewers (code, security, data, branding/design) do **not** dispatch from this skill — they are dispatched by the supervising process on its review cadence (canon Reviewer-trigger map, `principles-base.md §12`).

---

## 1. User Acknowledgment Gate

Before any status flip, surface in chat:

```
Completion Report: meta/logs/engineering/log-…-{block-id}-…md (## Completion Report) — N/N PASS (stage 2)
Post-merge re-validation: N/N PASS (stage 5)
Trigger session-end? (explicit yes required)
```

Ambiguous responses ("looks good", "sounds fine", "ok") are **not** authorization — re-prompt for an explicit go-ahead. If the user pushes back on a verified PASS without producing new evidence, do not capitulate — see the no-capitulation rule in `skill-validate.md §Constraints`. Re-state the evidence; if the user produces new evidence, re-open the relevant criterion via `skill-validate.md`.

---

## 2. Pre-Close Checks

- [ ] All tasks completed this session are tested and committed (already enforced by stage-2 validation; double-check no last-minute uncommitted edits)
- [ ] No undisclosed hard blocks this session (per `{shared_knowledge_path}/principles-base.md §11`). Any hard block must have been escalated when detected — not deferred to this gate.

---

## 3. Core Docs Staleness Check

**Answer each explicitly in the session log. Do not skip any row.** Canonical Core Docs list lives in `principles.md §Core Docs`.

Rows are the Core Docs that ship with the scaffold. Skip any row whose doc this project doesn't ship; add a row for any project doc your work changed.

| Doc | Affected? | Updated? |
|:----|:----------|:---------|
| `context.md` | YES / NO | ✅ / N/A |
| `pipeline.md` | YES / NO | ✅ / N/A |
| `principles.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/docs/guidelines-coding.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/docs/playbook-infra.md` | YES / NO | ✅ / N/A |
| `../<APP_REPO_NAME>/app/AGENTS.md` | YES / NO | ✅ / N/A |

Also sweep the project structure tree (AGENTS.md): any new files created this session (routes, lib modules, components, migrations) must appear there. Missing entries → add them now.

---

## 4. Git Sync

Follow `skills/skill-worktree-and-branching.md` for the full procedure (feature branch + worktree + PR + monitored merge; never commit/push on a protected branch; never arm auto-merge). Project deltas — PR base by repo:

- **Meta repo:** `main`.
- **App repo:** the project's trunk (`main`) — CI auto-deploys staging for validation; `hotfix/*` → `main` only.

Promotion to prod is operator-only, outside the worker flow.

---

## 5. Logging

- [ ] Create session log at `meta/logs/engineering/log-YYMMDD-HHMM-{description}.md` using the **session-log format** in `ref-session-log-format.md`
- [ ] Final checklist for user — numbered list of remaining manual actions
- [ ] **Shared-KB session end:** run `{shared_knowledge_path}/meta/agent.md §4` (lessons) and `§7.2` (warning closure — verified fix only; reviewers never close).

---

## 6. Block Status Update *(stage 6 — the only status flip in this project)*

**Runs only after** §1 user acknowledgment is explicit, §2–§5 are clean, `skill-validate.md` has produced clean stage-2 and stage-5 Completion Reports, and — where the block declares a deploy check — the change has deployed clean and been verified post-deploy. This is the sole location in the project where `**Status:** ✅ Done` is set.

For each block completed this session:

- [ ] Update block doc status: `**Status:** ✅ Done`
- [ ] Add `**Completed:** YYYY-MM-DD` and the PR link(s)
- [ ] Move the block file from `blocks/` to `blocks/archive/` (`git mv blocks/{id}.md blocks/archive/{id}.md`); the Completion Report lives in the engineer's session log under `meta/logs/engineering/` and stays there
- [ ] Update `pipeline.md` status markers for the block's tasks
- [ ] Commit the status-flip + archival as part of a feature branch → PR (per §4 Git Sync)
- [ ] Report to user: block completion summary, PR links, Completion Report path

Cycle-review archival runs under the same user-triggered invariant — see `skill-review-cycle.md`.

---

**Last Updated:** 2026-05-07 — Split: validation extracted into `skill-validate.md` (fires at stages 2 and 5); this skill is now paperwork-only at stage 6. Removed §0 Post-Merge Re-Validation, §0.5 Critic Gate, build verification — all moved to validate.
