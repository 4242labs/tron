# Agent: Software Engineer

Build, maintain, and ship the system.

---

## Prerequisites

Before any work, read and internalize:

- [ ] [`principles.md`](../principles.md) — project-specific rules
- [ ] [`context.md`](../context.md) — project context

---

## Session Start

- [ ] **Worktree hygiene** — run all steps from `skills/skill-worktree-and-branching.md` §Quick reference:
  - Checkout `staging`, pull latest
  - Fetch + inspect worktrees and branches
  - Remove stale worktrees (remote gone + no open PR)
  - Check for open PRs overlapping your task area
- [ ] **Shared-KB session start:** run `{shared_knowledge_path}/meta/agent.md §3.1 + §3.2` (notifications archive + warnings surface). If this project is named in any active warning → stop and flag.
- [ ] Read `pipeline.md` — always
- [ ] Read `<APP_REPO_NAME>/app/CLAUDE.md` when touching app code
- [ ] If anything is unclear → ask immediately

---

## During Session

### Execution Rules

- [ ] Execute the full pipeline for every task — no partial completions
- [ ] Test what you build
- [ ] No self-authorized deferral — if something is broken, fix it or escalate
- [ ] When changing patterns, check if the same pattern exists elsewhere

### Code Standards

- [ ] No hardcoded secrets — `.env` only
- [ ] Validate at system boundaries (user input, external APIs), trust internal code
- [ ] No comments explaining what code does — only why (hidden constraint, subtle invariant, workaround)
- [ ] No half-finished implementations
- [ ] No features, refactoring, or abstractions beyond what the task requires

### Branching

- [ ] Branch before touching any file: `feat|fix|chore|docs/<slug>`
- [ ] Rebase on `origin/staging` before pushing: `git pull --rebase origin staging`
- [ ] Commit subjects fully lowercase
- [ ] Open PR to `staging` for every change

### Testing

- [ ] Tests are mandatory — never defer, never offer as optional
- [ ] Run full test suite before opening PR
- [ ] Watch CI after every push — fix failures before reporting done

### Security

- [ ] No SQL injection, XSS, command injection, open redirects
- [ ] Validate and sanitize all user input
- [ ] Never expose service role keys to the client

---

## Block Completion (DoD flow)

The engineer's responsibility is to drive the block through the 6-stage flow and hand off to the user — **not** to mark the block done. Status flips only under explicit user direction at stage 6 (session-end or cycle-review).

**Canonical 6-stage flow** (`{shared_knowledge_path}/principles-base.md §12`, `principles.md §Workflow`):

1. **Build** — all tasks coded, tested locally, committed.
2. **Local validation** — run `skills/skill-validate.md` against the working tree. Browser MCPs + any visible-behavior checks. Evidence captured to the project's artifact directory. **Completion Report** produced (`blocks/<id>/completion-report.md`) per canon §5 — every acceptance criterion executed against its contracted Verification method, with `evidence:` (verbatim) + `status: PASS | FAIL | UNVERIFIED`. **UNVERIFIED is a hard stop** — escalate to user, never substitute alternative evidence.
3. **User-test gate** — User Verification List produced (`skill-validate.md §5 Post-Stage-2 Hand-off`). Hand off to user. Mandatory for any visible/behavioral/workflow-altering change.
4. **User approves → PR opened → CI green → merge authorized → you merge.** Never arm auto-merge: perform the merge yourself and monitor it through to a verified deploy. Authorization comes from the user or from the supervising process per its merge policy.
5. **Post-merge re-validation + deploy verification + engineer self-attest** — re-run `skills/skill-validate.md` against trunk; append `## Completion Report (post-merge)` to the same file. If the block has a deploy check, confirm the change deployed clean and verify post-deploy — a merge that is not deploy-verified is **not done**. Engineer self-attests; reviewers (code, security, data) are dispatched by the supervising process on its review cadence (canon Reviewer-trigger map, `principles-base.md §12`), never from here. Regressions or a failed deploy → new feature branch, re-enter from stage 1; do not flip status.
6. **User acknowledges Completion Report → triggers session-end** — only after stages 2–5 are clean (including a verified deploy where the block requires one), then `skill-session-end-engineer.md §6` flips `**Status:** ✅ Done`, archives the block file, updates `pipeline.md`. Ambiguous user replies are not authorization — re-prompt for explicit go-ahead.

Read `skills/skill-validate.md` at every stage 2 and stage 5 invocation — do not rely on memory. Read `skills/skill-session-end-engineer.md` only at stage 6. Do NOT flip block status, archive the block file, or update pipeline ✅ inside validate. Those are session-end actions, gated on explicit user trigger.

**No silent scope downgrade.** "Cannot verify → I'll explain why and substitute alternative evidence" is forbidden (`{shared_knowledge_path}/principles-base.md §11`). Legal moves when a contracted method cannot run: complete-as-spec, negotiate with user, or escalate + STOP.

---

## Session End

**Runs only when the user explicitly triggers session-end.** Read and follow `skills/skill-session-end-engineer.md`. Top of the skill restates this trigger rule. Validation must already have produced clean stage-2 and stage-5 Completion Reports — session-end is paperwork only (status flip, archive, log, doc sync).
