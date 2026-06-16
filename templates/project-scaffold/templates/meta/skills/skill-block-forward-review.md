---
name: skill-block-forward-review
description: Architect folds a finished block's learnings into upcoming blocks; supervisor-dispatched, flips no status.
source: project
---

# Skill: Block Forward Review

**The supervising process dispatches this skill when a block lands done (✅) on trunk.** It is not user-initiated and it is not session-end — it flips no status and closes no block. Its job is to carry forward what the just-done block taught us, so upcoming blocks stay correct. Read this file **now** — do not rely on memory. Canonical flow: `{shared_knowledge_path}/principles-base.md §12` (Reviewer-trigger map → *Architect forward review*).

Performed by the **Architect**.

**Purpose:** A block rarely lands exactly as scoped — assumptions shift, an interface changes, a dependency turns out heavier or lighter than planned, tech debt is logged. Left unreconciled, those learnings silently invalidate downstream blocks. This pass reads the finished block's record and adjusts the **upcoming** blocks (and their pipeline rows) before they are dispatched.

---

## 1. Determine Forward Scope

The done block is named by the dispatch. Build the set of blocks to reconcile:

- [ ] The **done block** itself (the source of learnings — read-only here; it is already ✅, never edit it)
- [ ] Every **not-done** block that lists the done block in its `Depends on:` (direct downstream)
- [ ] Remaining **not-done** blocks in the same phase and the next phase (candidates for drift)

```bash
grep -l "{DONE_BLOCK_ID}" blocks/*.md      # find blocks that reference the done one
```

Only **not-done** blocks (`📋 / 🔄 / 📌 / 🔧`) are in scope for editing. Done (✅), cut (❌), folded (📦), and split (✂️) blocks are never touched here.

---

## 2. Harvest Learnings

Read the done block's record:

- [ ] The block file `blocks/{DONE_BLOCK_ID}.md` — final scope vs. original (any mid-flow scope change noted in `Out of Scope` or `Notes`)
- [ ] The engineer's session log for the block (`logs/engineering/log-*-{DONE_BLOCK_ID}-*.md`) — the `## Completion Report` and `## Completion Report (post-merge)` sections
- [ ] Any reviewer `## Critic Verdict` log for the block, if a reviewer fired on it

Extract, as a short list, only what changes future work:
- Interface / contract / schema changes that differ from what downstream blocks assume
- New constraints or prerequisites surfaced during the build
- Dependencies that proved unnecessary, or new ones that emerged
- Tech debt logged that a later block was meant to rely on
- Scope that moved into or out of the block (so a downstream block now over- or under-laps)

If nothing in the record changes future work, record "no forward impact" and stop at §5 (log only, no edits).

---

## 3. Assess Each Upcoming Block

For each in-scope not-done block, decide whether a learning forces a change:

- [ ] **Scope** — does the delivered reality make a task redundant, insufficient, or wrong?
- [ ] **Depends on** — is a dependency now satisfied, newly required, or no longer valid?
- [ ] **Approach** — does a surfaced constraint change how the block should be built?
- [ ] **Acceptance criteria** — does a changed interface/contract invalidate an AC's verification method?

No change needed is the common case — say so and move on. Do not invent work.

---

## 4. Apply Adjustments

Edit the in-scope block files and their `pipeline.md` rows directly:

- [ ] Update block `Depends on:` / `Blocks:` headers, tasks, acceptance criteria, or `Out of Scope` as the learnings dictate
- [ ] Update the matching `pipeline.md` rows (`Task` one-liner, `Notes`) so the living doc stays true; **never change a block's `Status` emoji here** — this pass does not advance work, only re-scopes pending work
- [ ] Add a one-line note in each edited block's `Notes`/changelog stating the source: `adjusted per learnings from {DONE_BLOCK_ID}`

**Escalate to the user, do not silently rewrite, when** a learning invalidates a block wholesale, materially changes a phase's scope, or would cut/split a block. Propose the change; let the user decide. Material structural changes (cut/fold/split, new blocks, phase reshaping) are the architect's scoping call with the user, not an automatic edit.

---

## 5. Persist

Follow `skills/skill-worktree-and-branching.md` for the full procedure (feature branch + worktree + PR + monitored merge; never commit/push on a protected branch; never arm auto-merge). Project delta: this is meta-repo work — PR targets `main`.
- [ ] Write a forward-review log to `logs/architecture/log-YYMMDD-HHMM-{DONE_BLOCK_ID}-forward.md` using the **session-log format** (`ref-session-log-format.md`): the learnings harvested (§2), the blocks assessed (§3), the adjustments applied or escalated (§4). If there was no forward impact, the log says so in one line.

---

## Guardrails

- This skill **never flips block status** and **never archives** — that is session-end (`skill-session-end-engineer.md §6`) only.
- It edits **only not-done blocks**. The done block and all terminal-status blocks are read-only.
- It does not review code or run the critic — that is the reviewer's cadence (`skill-review-code.md` / `skill-security-scan.md`), dispatched separately by the supervising process.
- It is distinct from `skill-review-cycle.md` (the standalone, user-initiated phase-boundary consistency sweep). This pass is per-block, forward-looking, and supervisor-dispatched.
