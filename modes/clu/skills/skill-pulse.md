---
name: tron-clu-pulse
description: PULSE timer mechanics — arming, filesystem liveness forensics, escalation ladder, operator report cadence.
---

# PULSE

The heartbeat. Event wake-ups (worker completions) are supplements — the timer is the guarantee.

## Arming
- Background `sleep 180` (Bash, `run_in_background: true`) fired at boot and RE-ARMED at the end of every turn, no exceptions. If a tick fires mid-work, finish the action, sweep, re-arm.
- On EVERY arm, refresh the guard flag: `echo $(( $(date +%s) + 240 )) > .tron-clu-active` (project root). The Stop hook blocks any turn that ends with a lapsed flag — memory backed by mechanism.
- If you discover the timer lapsed (e.g. after a session resume), sweep immediately, then re-arm.
- At boot (once), scope the guard to YOUR session: write your session id to `.tron-clu-session` (project root). Your own transcript is the most recently written one at boot: `ls -t ~/.claude/projects/$(pwd | sed 's/[^a-zA-Z0-9]/-/g')/*.jsonl | head -1 | xargs basename | sed 's/\.jsonl$//' > .tron-clu-session`. Claude Code maps the cwd to the transcript dir by replacing EVERY non-alphanumeric with `-`, so use the `sed` transform above, never `tr '/' '-'` — on a dotted path (e.g. `example.ai`) `tr` leaves the `.` in, `ls` matches nothing, and the redirect still writes an EMPTY sidecar with no error. Immediately verify it's non-empty (`[ -s .tron-clu-session ]`) and treat empty as a wall: without a valid sid the Stop hook fires in EVERY session of the project.
- Run end: `skill-session-end` owns the teardown — run log first, THEN delete `.tron-clu-active` and `.tron-clu-session`. Never delete the flags outside that skill.

## Tick sweep (each tick, per active worker)
Read the filesystem, never the worker's transcript (transcripts overflow context):
- `git -C <worktree> log --oneline -3` — new commits since last tick?
- `git -C <worktree> status --porcelain | wc -l` — dirty-file count moving?
- Artifact mtimes (test reports, logs, MANIFEST-adjacent files).
- Worktree discipline: the shared checkout should stay clean — every worker writes only inside its own assigned worktree. Stray uncommitted files or edits in the shared root are a smell (a worktree-isolation breach, or TRON itself editing outside a worktree — see `skill-dispatch`); investigate as your OWN fleet's doing first, never assume an outside actor.
Record the sweep result mentally; write MANIFEST only on state change.

Signals can lie — cross-check, never trust one channel. An output/transcript file's mtime can lag far behind real activity (lazy flushing), and an agent's own heartbeat can be self-refreshing (it looks alive because it keeps saying so). The most trustworthy signal is fresh commits/edits to real work files (git log/status); weight those over mtimes and self-reported liveness.

## Escalation ladder
1. No progress ~2 ticks (≈6 min) → deep sweep (branch list, PR state, ports).
2. Still silent → ping the worker (SendMessage): "status <block> — reply in fixed format."
3. Ping fails / unresumable ("No transcript found") → declare dead → `skill-succession`.

Thrash is a separate signal: a worker that is ACTIVE but looping — 3+ failed attempts at the same gate, or repeated revert commits on the same files — is walled to the operator, not left to grind. Silence ≠ stuck, and activity ≠ progress.

## Active-ping liveness (not just artifact polling)
Artifact polling (git/PR/CI state) silently fails exactly when a worker finishes its visible work — CI goes green — then stalls before the final cheap mechanical step (clicking merge). A green, unchanging PR is indistinguishable from a quietly-dead agent by filesystem signal alone, so "still open, no new blockers" reported off artifact state can hide an idle worker for hours. Therefore: once a worker's PR checks have gone green and stayed unchanged past one cycle, add an active `SendMessage` ping to that worker EVERY cycle (not just after the 2-tick silence rule) — resuming an idle agent is cheap and its reply reveals liveness (a resumed agent answering "had no active task" is the tell). For any unattended/overnight stretch this active-ping-every-cycle is the DEFAULT, not a fix applied after something stalls; once a run enters "waiting on the last few blockers," tighten the cadence (e.g. 3 min) — one extra ping round is trivial next to hours lost to an unnoticed idle agent.

## Operator cadence
- Status report every ≤10 min: one line per worker or a short block-state table. Lead with state changes.
- Operator-relevant items (walls, clicks, gates) additionally route per `skill-operator-comms` the moment they're created — the in-session report is the record, not the signal.
- Quiet ticks: one line ("PULSE quiet — ENG-1 building, 4 commits, no walls.").
- Pending operator clicks (merges, gates) are repeated in EVERY report until cleared.

End of line.
