---
name: tron-clu-manifest
description: MANIFEST format and update triggers — the run-state file that survives context loss and enables succession.
---

# MANIFEST

One file at the project root: `<project-root>/.tron-clu-manifest.md`, gitignored in the target project, sibling to the other `.tron-clu-*` flag files. NOT the session scratchpad — job-local temp is deleted with the job and invisible to a fresh session, which would break the resumability guarantee below. It is run-state truth: after any context loss (compaction, session death), the run must be fully resumable from MANIFEST + git alone. Git is read-only truth for code; MANIFEST is truth for everything git can't hold.

## Sections (in order)
```markdown
# TRON MANIFEST — run <name> (started <date>) — <run status>

## Config
Scope, fleet (slots + models), gates, PULSE cadence, dependency map (e.g. 02-01 ⊣ {02-02, 02-03}).

## Workers
| ID | Agent handle | Role | Model | Block | State |
`ID` is the logical label (`ARCH-1`, `ENG-2`); `Agent handle` is the RESUMABLE agent id `SendMessage` needs — recorded the moment the agent is spawned, never left blank, so a long-lived agent (esp. the Architect) can be resumed after compaction instead of re-spawned fresh. State includes worktree path + branch while active; DEAD rows keep cause + successor.

## Block states
| Block | State |
Stage machine position + evidence pointers (commit SHAs, PR numbers, session-log paths).

## Port map
Assigned ports per purpose/worker.

## Parallel rules
Architect's file-ownership + merge-order rules, verbatim, while a parallel run is live.

## Gate ledger
One line per gate verdict: block, gate, date, verdict, evidence pointer.

## Deviations log
Anything a worker did off-blueprint with justification — feed for the phase reviewer.

## Scope notes
Dated operator amendments, verbatim.

## Operator click queue
Every pending operator action (merges, gates) — repeated in reports until cleared.
```

## Update triggers (write immediately, not batched)
- Any worker state change (spawn, stage advance, wall, death, release).
- Any gate verdict, operator amendment, deviation, click cleared.
- Quiet PULSE ticks do NOT touch the file.

## Rule out your own fleet before blaming an outside actor
Before attributing ANY anomaly (a numbering collision, a stray file, a stuck/racing merge) to a separate or external session, TRON first rules out its OWN fleet. The live task list is not sufficient — it silently drops older dispatches across a compaction, so audit the FULL dispatch history (Workers table + every dispatch this run, not just what's currently narrated). Contention between your own parallel blocks on a shared trunk is the default explanation, not outside interference. If it's still unexplained after that audit, say so plainly to the operator as an open question ("I don't know why yet") — never narrate a specific causal story (a fabricated external session) as settled fact. An honest "unknown" beats a confident wrong answer.

## Discipline
- Facts with evidence pointers (SHA, PR#, path) — no narrative.
- Never delete history within a run; supersede (strike or annotate).
- On run completion: final header line with end state, then stop writing.

End of line.
