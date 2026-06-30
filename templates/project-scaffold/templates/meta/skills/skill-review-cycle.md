---
name: skill-review-cycle
description: Architect's user-initiated phase-boundary consistency sweep, archival, and doc reconciliation.
source: project
---

# Skill: Cycle Review

**This skill runs only when the user explicitly requests a cycle review.** Archival + status-flip inside §7 is the cycle-review equivalent of session-end stage 6 — it runs only under explicit user direction, never automatically. See `{shared_knowledge_path}/principles-base.md §12` and the project's `principles.md §Workflow`.

Review performed by the **Architect** at the user's request. Can be triggered at any point — after a full phase completes, after a subset of blocks, or whenever the user calls for it. It does NOT need to wait for a full phase to finish. Read this file **now** — do not rely on memory.

**Purpose:** Validate that execution fully reflects documentation, and documentation fully reflects execution. Nothing drifts. Nothing is left behind.

---

## 1. Determine Cycle Scope

Identify which blocks are being reviewed. The scope is determined by the user's request:
- **Full phase review:** All blocks for that phase in `blocks/`
- **Partial review:** A specific set of blocks named by the user, or all ✅ blocks in a phase even if others remain open

```bash
ls blocks/{PP}-*.md    # replace {PP} with the phase number prefix (e.g., 03-*.md for Phase 3)
```

Only in-scope blocks are reviewed. Other blocks (including open ones from the same phase) are ignored.

- [ ] List all in-scope block docs
- [ ] Confirm all in-scope blocks have status ✅ — if any in-scope block is not ✅, stop and report to user

---

## 2. Security Scan

Run `skill-security-scan.md` §1–12 with scope = all blocks in this review cycle combined.

**If any CRITICAL or HIGH finding is unresolved → stop. Do not archive blocks or mark phase complete.**

---

## 3. Block-Level Validation

**For each in-scope block, verify ALL of the following. Do not skip blocks.**

- [ ] **Status is ✅** in the block doc header
- [ ] **Acceptance criteria satisfied** — verify each AC was delivered (code committed, tests passing, `npx tsc --noEmit` clean). AC checkboxes in block docs are the build spec, not a completion tracker — the status field is the single source of truth.
- [ ] **Pipeline entry matches block** — the one-liner in `pipeline.md` accurately describes what was delivered (not what was planned, if scope changed during execution)
- [ ] **Tests passing** — run `cd app && npm test` to confirm all tests pass for the current state

Record any discrepancies. Do not fix silently — report to user for decision.

---

## 4. Pipeline Consistency

Read `pipeline.md` for the in-scope phase section:

- [ ] **Phase status** — if all blocks in the phase are ✅, phase status should be ✅
- [ ] **Task one-liners** — each matches the actual delivered scope (cross-check with block doc)
- [ ] **Tech debt references** — any debt items resolved by this cycle are updated (status changed or removed)
- [ ] **Depends on** — any blocks in other phases that depended on this cycle's work are updated if the dependency is now satisfied
- [ ] **No orphaned references** — no block mentioned in pipeline that doesn't have a corresponding block doc

---

## 5. Core Docs Staleness Check

**Read each doc. For each, answer: does it accurately reflect the current system after this cycle's changes? Answer explicitly — do not skip any row.**

Canonical list: `principles.md` §Core Docs.

Rows are the Core Docs that ship with the scaffold. Skip any row whose doc this project doesn't ship; add a row for any project doc this cycle's work touched.

| # | Doc | Location | Accurate? | If stale, what's wrong? |
|:--|:----|:---------|:----------|:------------------------|
| 1 | `context.md` — project structure, conventions | `context.md` | YES / NO | |
| 2 | `pipeline.md` — scope, status, technical debt | `pipeline.md` | YES / NO | |
| 3 | `principles.md` — agent behavior rules | `principles.md` | YES / NO | |
| 4 | `guidelines-coding.md` — code standards + secure coding | `../<APP_REPO_NAME>/docs/guidelines-coding.md` | YES / NO | |
| 5 | `playbook-infra.md` — infra, secrets, services | `../<APP_REPO_NAME>/docs/playbook-infra.md` | YES / NO | |
| 6 | `CLAUDE.md` — app technical spec | `../<APP_REPO_NAME>/app/CLAUDE.md` | YES / NO | |

**If any doc is stale:**
- Fix it now if the change is factual and unambiguous (e.g., new route, new component, new migration)
- Escalate to user if the change requires a design decision

---

## 6. Cross-Doc Consistency

Verify docs don't contradict each other or the actual system:

- [ ] Project structure in `../<APP_REPO_NAME>/app/CLAUDE.md` matches actual `app/` directory layout
- [ ] Routes listed in `../<APP_REPO_NAME>/app/CLAUDE.md` match actual routes in `src/app/`
- [ ] Tech stack in `../<APP_REPO_NAME>/app/CLAUDE.md` matches `package.json` dependencies
- [ ] Pipeline phase statuses match block doc statuses
- [ ] Any new tables referenced in block docs exist in `app/supabase/migrations/`
- [ ] Agent docs reference skills that actually exist in `skills/`

---

## 7. Archive Completed Blocks

**Note on status-flip invariant:** cycle review is a user-initiated event — running through §1–§6 does not by itself authorize any flip. Archival here is the cycle-review equivalent of `skill-session-end-engineer.md §Block Status Update`. Both run only under explicit user direction. Do not remove this equivalence in future rewrites.

**Cycle review does NOT flip status.** Each in-scope block must already be `✅ Done` before this skill runs — meaning it has already passed the canonical 6-stage flow (`{shared_knowledge_path}/principles-base.md §12`): Completion Report all-PASS, critic gate PASS (for ≥2-criterion blocks), user-acknowledged at session-end. Cycle review is archival + cross-doc validation, not a backdoor to mark blocks done.

After §1–§6 validation passes:

- [ ] **Pre-archival status gate:** For each in-scope block, verify `**Status:** ✅ Done` in the block doc header AND a Completion Report (the `## Completion Report` section) in the engineer's session log for the block AND, when `Reviewer class:` ≠ `none`, a `## Critic Verdict` section showing PASS in the reviewer's session log for the block. If any of these is missing or any block is still `📋 To do` or `🔄 In progress` → STOP. Do **not** flip status here. Report to user; the engineer must run the proper session-end flow first.
- [ ] Move all in-scope block docs to `blocks/archive/` (the Completion Report and Critic Verdict live in session logs under `logs/` and stay there — only the block doc is archived)
- [ ] If the **entire phase** is complete (all blocks ✅, none remaining): update the phase status in `pipeline.md` to ✅
- [ ] If only a **partial review** (some blocks still open in the phase): archive only the reviewed ✅ blocks, leave the phase section as-is
- [ ] Verify archived blocks are no longer in `blocks/` (only in `blocks/archive/`)

---

## 8. Persist & Report

**Git sync:**

Follow `skills/skill-worktree-and-branching.md` for the full procedure (feature branch + worktree + PR + monitored merge; never commit/push on a protected branch; never arm auto-merge). Project deltas: meta-repo work PRs to `main`; app-repo changes PR to the project's trunk (`main`) — CI auto-deploys staging for validation; `hotfix/*` → `main` only. Promotion to prod is operator-only, outside this cycle.

**Review log:**

- [ ] Write review log to `logs/architecture/log-YYMMDD-HHMM-cycle-review.md`
  - Cycle scope (blocks reviewed, which phases they belong to)
  - Block validation results (all pass, or discrepancies found)
  - Pipeline changes made
  - Core docs staleness table (filled in)
  - Cross-doc issues found and resolved
  - Items escalated to user (if any)
  - Confirmation that block docs are archived
  - Include "Executed by Model: {Model Name}"

**Report to user:**

- [ ] Summary: cycle scope, any discrepancies, any items requiring user decision, confirmation that docs are current and blocks are archived

---

**Last Updated:** 2026-04-23 — user-triggered top note; §7 Archive adds status-flip invariant note (cycle-review equivalent of session-end §Block Status Update); §8 Git sync switched from direct push to feature-branch + PR.
