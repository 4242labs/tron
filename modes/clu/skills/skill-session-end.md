---
name: tron-clu-session-end
description: Run-end protocol — write the run log (problems + self-enhancement feedback), then deactivate the guard. Every run ends through this skill.
---

# Session end

Every run ends through this skill — clean finish, operator abort, or fleet death. No run
ends silently: the log is written BEFORE the guard comes down, so a run that dies mid-teardown
still left its trace armed.

## Preconditions to propose ending
**ALL blocks in scope CLOSED** — scope means the full phase/mandate the operator handed you, not
just the blocks that happened to be in flight. Re-read the scope before proposing end; do NOT
mistake "the batch I was running" for "the run" (P-114: 4/12 blocks were treated as the whole run —
the other 8 were never dispatched). Also: operator click queue empty, all workers released.

**Clean-location audit (hard gate, verified — not "swept" on faith).** The run does not end with
leftover run-created worktrees or branches in ANY repo. For every repo the run touched
(app / meta / gateway / …), run `git worktree list` and `git branch` and confirm ZERO run branches
or worktrees remain; a merged close PR is NOT done until its worktree AND branch are pruned. Pruning
is the engineer's session-end duty — dispatch the owner to finish it; TRON verifies with the audit,
never assumes. Leftovers = run stays OPEN.

A pending wall holds the run OPEN — never end around an unresolved wall. Ending is proposed to the
operator; the operator's word closes it.

## 1. Run log (before anything comes down)
Write `log-YYMMDD-HHMM-run-<project>.md` to `$CLU_ROOT/logs/` (`$CLU_ROOT` resolved at boot):

```markdown
# Run log — <project> (<scope>)

Started / ended, operator, fleet (slots + models).

## Outcome
Blocks through the loop (IDs + PR#s), blocks cut/deferred + why. Facts with evidence
pointers — no narrative.

## Problems faced
One line each: walls raised (+ resolution), successions (+ cause chain), thrash events,
gate rejections, port/tooling collisions. Empty section stays, marked "none".

## Self-enhancement feedback
The payoff section — honest, specific, actionable. What in MY OWN operation cost time or
risked the run: procedure gaps in persona/skills, orders workers misread, challenges that
missed, anything improvised off-blueprint because no skill covered it. Each item: what
happened → which file should change (path) → proposed change in one line. No item is too
small; "none" is a valid but suspicious answer.
```

Project-side paperwork (session logs in the target project's meta, per its own method) is the
workers' duty under their protocols — never duplicated here. This log is about TRON, for TRON.

## 2. Deactivate (only after the log is committed to disk)
1. Final MANIFEST header: end state (`COMPLETE` / `ABORTED <reason>`), then stop writing.
2. Kill any orphan processes TRON itself started (PULSE sleepers). Verify gate servers are
   already down (skill-gates owns their shutdown at merge; a survivor here is a deviation —
   log it in the run log, then kill it).
3. Delete `.tron-clu-active`, `.tron-clu-session`, and `.tron-clu-attention` — the
   guard goes dormant, the attention feed goes with it.
4. Close line to the operator — session AND Telegram (`run end` template, skill-operator-comms):
   blocks through, pings sent, log path. End of line.

## Feedback loop
The self-enhancement section is read at the START of the next maintenance session on this
agent — it is the backlog feeding `logs/` maintenance entries. Feedback nobody reads is
decoration; that's why it names files and proposed changes, not feelings.

End of line.
