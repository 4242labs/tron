# Principles — <PROJECT_NAME>

Apply `{shared_knowledge_path}/principles-base.md` first, then `{shared_knowledge_path}/codex.md` — the fleet engineering **Codex** (core canon: change-flow & branch protection, the LGTM CI gate, design-system compliance). Both are core canon for every project. Below are <PROJECT_NAME>-specific additions and overrides. **When a rule here conflicts with the shared base or the Codex, this file wins** — the Codex itself defers to project rulebooks and TRON's mode rulebook.

Agent behavior rules for this project. All agents must read and internalize this file before any session.

---

## Configuration

Single source for project-level paths. Every agent reads this file at session start (Prerequisites), so these resolve **once, here** — agent docs and skills use the variable, never a hardcoded path.

| Variable | Value | Notes |
|:--|:--|:--|
| `{shared_knowledge_path}` | _(blank — set per project; TBD in canon, see TD-10)_ | The canonical shared knowledge base (principles-base, the engineering **codex**, shared skills, `meta/agent.md` notifications/warnings). Every `{shared_knowledge_path}/…` reference resolves against this. If this project has **no** shared KB, set blank — then skip every `{shared_knowledge_path}/…` step. |

Keep this value in sync with `agents/flynn-local.md → Configuration → shared_knowledge_path`.

---

## Core Rules

1. **Never code without approval.** Discuss spec first, get explicit approval, then implement.
2. **Branch before touching any file.** No exceptions, including meta/logs/pipeline. Always branch + PR.
3. **Always rebase before push.** `git pull --rebase origin staging` before every push. Never push stale branches.
4. **Tests are mandatory.** Never defer tests or offer them as optional. Include in same PR as the code.
5. **Merge only when authorized.** Open the PR; merge it yourself only after merge is authorized — by the user, or by the supervising process per its merge policy — and all gates are green. Deploys are automatic on merge; never trigger a deploy by hand.
6. **Never arm auto-merge.** Perform the merge yourself and monitor it through to a verified deploy — a merge left unmonitored or not deploy-verified is not done.
7. **Monitor CI after every push.** Watch CI. Fix failures before calling the user.
8. **Fix what you find.** Engineer: fix immediately. Reviewer: report only (no code changes).
9. **No shortcuts.** Lead with root-cause, highest-standard, long-term fix. No band-aids.
10. **Never defer issues.** Every finding gets fixed. Never ask whether to defer.
11. **Be terse.** One sentence per finding. Lead with conclusion. No headers for simple answers.
12. **Update docs continuously.** Update pipeline.md, context.md, and session logs throughout the session. Never defer to session end.
13. **Keep staging current locally.** After branch work: `git checkout staging && git pull`.

---

## Workflow — canonical 6-stage flow

Every block, every agent. PR-open is **not** block-done — and neither is PR-merged: when the block declares a deploy check (`Deploy:` field, or the project default in `context.md → Deploy`), the change must be **deployed clean and verified post-deploy** before the block can be done. A merged branch that fails to deploy is **not-done and must be fixed**, not flipped. Status flips only under explicit user trigger (session-end or cycle-review), never automatically at PR-merge or at block-completion gate pass. Canonical rule: `{shared_knowledge_path}/principles-base.md §12`.

1. **Build** — tasks coded, tested locally, committed.
2. **Local validation** — run `skill-validate.md` (stage-2 invocation). Every acceptance criterion verified, including UI via browser MCPs. Evidence to the project's artifact directory; Completion Report produced.
3. **User-test gate** — User Verification List (`skill-validate.md §5 Post-Stage-2 Hand-off`) handed off to user. Mandatory for any visible / behavioral / workflow-altering change. Engineer does not proceed past this step without explicit user go-ahead.
4. **User approves → PR opened → CI green → merge authorized → engineer merges.** Never arm auto-merge; perform the merge and monitor it through to a verified deploy. Authorization comes from the user or from the supervising process per its merge policy.
5. **Post-merge re-validation + deploy verification + engineer self-attest** — re-run `skill-validate.md` (stage-5 invocation) against trunk; if the block has a deploy check, confirm the change deployed clean and verify post-deploy; engineer self-attests. Reviewers are dispatched by the supervising process on its review cadence — never here (canon Reviewer-trigger map, `principles-base.md §12`). Regressions or a failed deploy → new feature branch + PR, re-enter flow from step 1.
6. **User triggers session-end** — only then `skill-session-end-engineer.md §6 Block Status Update` flips `**Status:** ✅ Done`, archives the block file, updates `pipeline.md`.

Cycle reviews (`skill-review-cycle.md §7`) run under the same invariant — they are themselves user-initiated events, and their archival + status-flip is the cycle equivalent of session-end step 6.

Mapping:

| Step | Skill | Section |
|:-----|:------|:--------|
| 1 Build | (engineer's normal coding loop) | — |
| 2 Local validation + 3 User-test gate | `skill-validate.md` | §1–§5 (stage-2 invocation) |
| 4 PR + CI | `skill-session-end-engineer.md` | §4 Git Sync (feature branch + PR, never direct-push) |
| 5 Post-merge re-validation + engineer self-attest | `skill-validate.md` | §1–§4, §6 (stage-5 invocation) |
| 6 Status flip | `skill-session-end-engineer.md` | §6 (engineer) or `skill-review-cycle.md` §7 (architect cycle review) |

---

## Skills Registry

| Skill | File | Trigger |
|-------|------|---------|
| Validate | `skills/skill-validate.md` | Stage 2 (local, pre-PR) and stage 5 (post-merge re-validation) |
| Block Forward Review | `skills/skill-block-forward-review.md` | Architect — dispatched by the supervising process when a block lands done; reconcile upcoming blocks against learnings/drift |
| Review Cycle | `skills/skill-review-cycle.md` | Architect — standalone, user-initiated cycle review (not the supervisor's review cadence) |
| Code Review | `skills/skill-review-code.md` | Code quality audits — dispatched on the review cadence |
| Security Scan | `skills/skill-security-scan.md` | Security audits — dispatched on the review cadence |
| Worktree & Branching | `skills/skill-worktree-and-branching.md` | Before creating any branch |
| Session End | `skills/skill-session-end-{role}.md` | End of every session |

---

## Branching Convention

- Default branch: `staging`
- Feature flow: `feat|fix|chore|docs/<slug>` → PR targets `staging`
- Hotfix lane: `hotfix/<slug>` → PR targets `main`
- Worktree location: `<WORKSPACE_PATH>/worktrees/<repo>--<branch>/` (workspace-internal — see `skills/skill-worktree-and-branching.md §Setup`)
- Commit subjects: fully lowercase (commitlint enforced)

---

## Core Docs

Every agent reads these at session start:

- `pipeline.md` — always
- `context.md` — always
- `<APP_REPO_NAME>/docs/guidelines-coding.md` — code standards + secure coding (when touching app code)
- `<APP_REPO_NAME>/docs/playbook-infra.md` — infra, secrets, services (when touching app code or infra)
- `<APP_REPO_NAME>/app/AGENTS.md` — when touching app code

**Rules:**

- [ ] **Same-session update.** If your work changes what a Core Doc describes — update it in the same session. A code change without a doc update is incomplete delivery.
- [ ] **One-line `Last Updated`.** Replace the existing line — never append `Previous:` chains or essay paragraphs. Format: `**Last Updated:** YYYY-MM-DD — short reason.` History lives in git log, not in the doc. Same rule for any block `Notes` cell or block-file changelog: short, current state only.
- [ ] **Block titles are short.** Pipeline `Task` column = single short sentence. Detail belongs in the block file or modal description (rendered by the lens), not the title.
