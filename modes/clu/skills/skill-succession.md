---
name: tron-clu-succession
description: Dead-worker detection and successor spawn — clean handover from git worktrees + MANIFEST.
---

# Succession

Workers die (session limits, resume failures). The design assumption: NO state lives only in a worker's head. Everything recoverable sits in git worktrees, open PRs, and the MANIFEST — so succession is routine, not crisis.

## Detection
- Resume/ping fails ("No transcript found" or equivalent) → dead. Operator session limits kill whole fleets at once — if one worker dies this way, probe the others.
- Do NOT retry resurrection more than once. Declare and replace.

## Before spawning
Forensic sweep of the corpse's estate (filesystem only):
- `git -C <worktree> log --oneline -5` + `status --porcelain` — last commit, uncommitted work.
- Open PRs on its branches, CI state.
- Compare against MANIFEST's last recorded state — the delta is what the successor must verify or redo.
Possible outcome: the worker FINISHED its orders before dying (PRs open, CI green). Then no successor is needed for that stage — just record it and route the next stage normally.

## Spawn
- New ID (ENG-3 → ENG-4; never reuse). Same persona, same model tier.
- Dispatch per `skill-dispatch` succession template: predecessor ID, worktree path, branch, MANIFEST state, order to verify inherited state before continuing.
- Successor inherits the block mid-stage — it does not restart the stage machine; it re-enters at the recorded stage.

## Record
MANIFEST worker table: mark predecessor DEAD with cause, add successor row, note the chain (e.g. "ENG-3→4→5→6, operator session limits"). Report the succession to the operator in the next status line — one line, no drama.

End of line.
