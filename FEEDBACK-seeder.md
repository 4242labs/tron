# FEEDBACK — `tron-seed`

Source: live seeding of the `zovv` instance on 2026-05-15. Canon at start of seed: `v0.3.0`. Canon at end of seed: `v0.3.5` (five operator-authorized canon PRs were merged mid-seed — they are summarized at the bottom of this doc).

Findings are spec-level (canon docs in `~/42labs/tron/`), not project-level. Anything that was already fixed in v0.3.1–v0.3.5 is listed only as historical context. **Open recommendations** are the actionable items.

---

## TL;DR

1. **Seeder has no session-end protocol.** `seed-trace.md` (Step 11) is the only audit artifact and it is written mid-seed — frozen before Step 12/13. No close-out stamp, no "what got actually executed" record.
2. **Step 12 dry-run is operator-run with no follow-up.** The seeder hands off and exits; the operator may run the dry-run weeks later, with no link back to seed-trace.
3. **Workflow Q&A is unscripted.** Step 3 says "author workflow.md and validate" but provides no operator-question checklist. The whole R1–R7 walkthrough was improvised — long, fragile, and biased toward whichever canon defaults the seeder happens to remember.
4. **Multi-reviewer / multi-cadence is project-shape, not example-shape.** Canon `workflow.example.md` models one reviewer, one architect-review cadence. Real projects (zovv has 3 reviewer roles + split mid-session/cycle review) need a documented variant to copy from.
5. **Multi-repo workspaces work but require deep canon §14 reading.** `tron-seed.md` Step 1 only weakly accommodates a workspace-root-that-is-not-a-repo (zovv's shape: `~/42labs/zovv/` is a directory containing two git repos).
6. **Pre-flight detection is shallow.** Seeder doesn't inspect the target project's existing docs (`principles.md`, `context.md`) to surface candidate values for knobs, so every Q is asked cold.
7. **The seed is non-atomic.** Seeded files land in the target repo's working tree as untracked changes, but the seeder never commits them. The operator inherits an uncommitted instance and has to decide PR shape themselves.
8. **Telegram setup discovery flow is undocumented.** `getUpdates` → chat-id discovery took multiple round-trips. Canon mentions `.env` keys but never how to *obtain* `TELEGRAM_CHAT_ID`. Group-chat-per-project (one bot, many groups) convention is not stated.

---

## Open recommendations

### 1. Add `skill-session-end-tron-seed.md`

Mirrors `skill-session-end-tron.md` but for the seeder role. Required actions:

- Append a "Session close" block to `seed-trace.md` with: close timestamp, list of canon PRs landed mid-seed, list of files written, list of any deviations from `tron-seed.md` step order, and the operator decisions that landed (knobs, workflow rules).
- Verify all worktrees opened during the seed are removed.
- Verify the target repo has no uncommitted seed output (either commit it or open a PR; never leave the operator with untracked files).
- Print the Step 13 sign-off block.

### 2. Step 12 closes the loop, not Step 13

Today Step 12 is operator-run and the seeder exits before it runs. Better:

- Step 12 is operator-run **but** the seeder either (a) waits for the operator to report `validate: pass + doctor: clean` before signing off, or (b) splits sign-off into Step 13a (seeder closes) + Step 13b (operator reports dry-run result, which seeder appends to seed-trace.md on resume).
- If neither is acceptable to canon, at minimum: Step 11 (seed-trace) instructs the operator to manually paste the dry-run output back into seed-trace.md after Step 12.

### 3. Step 3 needs a scripted operator Q&A

Walk the operator through each rule **before** authoring `workflow.md`. Suggested checklist (canon should ship this as `templates/workflow-questionnaire.md`):

- **R1** — persistent architect: keep, drop, or rename?
- **R2** — keep peer-consult (post-v0.3.1)? Project-defined peers (Step 3 must ask which worker→peer pairs exist; canon ships none).
- **R3** — operator-only tasks list (free-form; ask explicitly).
- **R4** — reviewer cadence(s). **Ask "how many reviewer roles?" first**, then per-role threshold. Default canon question is single-reviewer; multi-reviewer is the common real case.
- **R5** — architect review: single cadence (canon) or split (mid-session + cycle)? If split: thresholds + overlap rule (recommend cycle-wins-overlap).
- **R6** — confirm fresh-engineer-per-block (almost always yes).
- **R7** — locked; no question.
- **Knobs** — per-session: `max_concurrent_engineers`, `session_end_idle_min` (no defaults). Fixed: silence thresholds, all R4/R5 cadences.
- **Repo shape** — single-repo / multi-repo (workspace root) / monorepo. Branch naming. Worker ID pattern. PR target branch per repo.
- **Telegram** — configure now / defer.
- **Free-form** — operator-only tasks, local-validation gaps, CI behavior, deploy flow, other notes.

### 4. Add `workflow.example-multireviewer.md` as a second canon example

Shows the zovv shape: three reviewer roles with independent counters, R5 split into mid-session + cycle, cycle-wins-overlap. Seeder Step 3 picks the right example based on the operator's R4 answer.

### 5. Encode multi-repo workspace shape explicitly

`tron-seed.md` Step 1 should accept three workspace shapes and ask the operator which one applies:

- **Single-repo**: target IS a git repo. `repo_root = target_repo`. Worktrees at `target_repo/.worktrees/<branch>/`.
- **Multi-repo workspace**: target is a directory containing multiple git repos. Operator picks which one hosts the TRON instance (typically the meta repo). Worktrees at `workspace_root/worktrees/<repo>--<branch>/`. The seeder must record the per-repo integration branch (e.g. `zovv-meta=main`, `zovv-app=staging`).
- **Monorepo**: single repo with multiple deploy targets. Treat as single-repo for TRON; per-target branching is project convention.

Step 1's "Detect" can do most of this automatically: `git rev-parse` on the target → if not a repo, scan immediate children for `.git` dirs.

### 6. Pre-flight project doc scan

Before Step 1 Q&A, the seeder should read (if present):

- `<meta>/principles.md` — pull existing agent rules, conventions, commit style
- `<meta>/context.md` — pull project background; surface anything that contradicts assumed canon defaults
- `<meta>/CLAUDE.md` — pull declared agents list, key files
- `<meta>/pipeline.md` — confirm work is already in flight

…and **pre-fill** the Q&A defaults from these. Operator only confirms or overrides. Cuts seed time roughly in half.

### 7. Seeder commits its output

Either:

- Seeder opens a PR in the target meta repo with the new `agents/tron/` instance + `agents/tron.md` (mirrors how every other artifact lands in this codebase). Operator merges as part of Step 13.
- Or: seeder writes to a `.worktrees/seed-tron-YYMMDD/` worktree and prints the merge command in Step 13.

Leaving untracked files in the target repo's working tree is sloppy and asymmetric with how the rest of canon operates.

### 8. Telegram bootstrap helper script

`scripts/tg-bootstrap.sh`:

1. Prompts for bot token, writes `.env`.
2. Prints the chat-discovery instructions (DM the bot `/start`, or add the bot to a group and send any message).
3. Calls `getUpdates`, parses the latest `chat.id`, asks operator to confirm.
4. Writes `TELEGRAM_CHAT_ID` to `.env`.

`tron-seed.md` Step 9 invokes this script instead of describing the API call inline. Also document the **one-bot-many-groups** convention: same `TELEGRAM_BOT_TOKEN` reused across projects, each project gets its own group with a distinct `chat_id`.

### 9. `project.example.md` schema for free-form sections

Today the free-form sections (operator-only, local-validation gaps, CI, deploy, other notes) are mentioned only in `project.example.md` headers. Seeder should ask each one explicitly during Step 1 and not invent values (this seed slipped twice: once on "LLM API key provisioning (OpenAI)" — there is no OpenAI in zovv; once by half-drafting all four free-form sections in one turn instead of one at a time).

Canon rule worth adding to `tron-seed.md` "What the seeder must NOT do":

> Do not assume a vendor / provider / external service that is not in `<meta>/principles.md` or explicitly named by the operator. `TBD` is a valid value.

### 10. Seed-trace.md gets a structured tail section

Today `seed-trace.md` is freeform under a 2026-05-15 heading. Better template:

```
## Seed — YYYY-MM-DD
### Canon source / Prerequisites / Operator decisions / Deviations / Steps executed / Key values NOT logged
### Session close (added at Step 13)
- Close timestamp:
- Dry-run result: (pending | pass | issues — list)
- Worktrees cleaned: yes / no
- Outstanding operator action: (list)
```

This makes future re-seeds, audits, and skill-recover much faster.

---

## Lower-priority polish

- **Step 4 "templates seeded"** copies canon templates verbatim. There's no question asked about project-specific edits. Most projects will edit `templates/tron.md` later; canon should note "edit after seed, then commit".
- **Step 6 chmod +x** is reliable but worth wrapping in `scripts/install.sh` for atomic re-seed.
- **`tron-seed.md` Step 13 sign-off** doesn't tell the operator what comes *after* the dry-run. Add one line: "After dry-run reports clean, start regular operation with the same command minus 'audit-only' wording."
- **The "always invoke from project root" rule** is implicit. Canon should make it a Premise (it currently leaks into multiple skill docs and was almost violated when the spawn command went absolute-path).
- **Workflow-state.md schema** is hardcoded to single-reviewer. Multi-reviewer required a hand-edit to add the role-suffixed counters. Canon should ship a `templates/workflow-state.multireviewer.md` keyed off the operator's R4 answer.

---

## Canon PRs landed during this seed (historical)

These are no longer open — already merged — listed for traceability.

| PR | Tag | What it fixed |
|:--|:--|:--|
| #7 | v0.3.1 | Collapsed ENG↔ARCH relay (R2) into direct peer-consult per Premise 18. |
| #8 | v0.3.2 | Per-session knobs (`max_concurrent_engineers`, `session_end_idle_min`) have no defaults; TRON asks every session. |
| #9 | v0.3.3 | Peer-consult table is project-defined (canon ships none); silence sweep rewritten with `silence_ping_min` / `silence_escalate_min`, exclusions, dead-process purge, no auto-RELEASE. |
| #10 | v0.3.4 | `.env` lives at `<meta>/agents/tron/.env` (encapsulated with TRON), not at repo root. |
| #11 | v0.3.5 | Spawn command is project-relative + instructs TRON which file to read first. |

---

## Suggested canon priorities (next bumps)

In rough order of value-per-effort:

1. **v0.3.6** — `skill-session-end-tron-seed.md` + structured `seed-trace.md` template (Recs 1, 10).
2. **v0.3.7** — Step 3 operator questionnaire + Rec 9 vendor-assumption Premise (Recs 3, 9).
3. **v0.3.8** — Multi-reviewer + multi-repo workspace docs / examples (Recs 4, 5, plus workflow-state.multireviewer template).
4. **v0.3.9** — Pre-flight project doc scan (Rec 6).
5. **v0.4.0** — Seeder commits its output (Rec 7) + `tg-bootstrap.sh` (Rec 8). This is the bump that makes the seeder feel "atomic".
