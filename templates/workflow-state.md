# workflow-state.md — Live workflow counters

Machine-readable state TRON updates every turn. Mirrors the rules in `workflow.md` with running values. Operator should not hand-edit — let TRON manage via `skill-edit-self`.

---

## Session

- `session_started_at`: (set on cold start)
- `tron_session_id`: (set on cold start; mirrors `current-id`)

## Current work

- `current_block`: (e.g. `block-06-19-app-versioning`, or `null`)
- `current_block_started_at`: (timestamp)
- `current_block_branch`: (e.g. `chore/app-versioning-260515`)

## Active workers

```
[]
```

Format: list of `{id, role, session_id, spawned_at, status}` where status ∈ `idle|working|stalled|done-pending-release|released`.

## Counters

- `blocks_since_review`: 0
- `reviewer_threshold`: 3   (operator-configurable; from workflow.md R4)
- `reviewer_findings_open`: 0
- `paused_for_operator`: null   (or worker_id awaiting operator decision)

## Reviewer scope (when blocks_since_review hits threshold)

```
[]
```

List of block IDs accumulated since last reviewer pass.

## Last sweep

- `last_sweep_at`: (timestamp)
- `sweeps_this_session`: 0

---

**Schema notes:**
- TRON re-reads this on session start and reconciles against live process state.
- If `active_workers` shows workers that are not alive in `~/.claude/jobs/`, TRON purges them and logs a recovery note.
- This file is the source of truth for "what's running now." Do not derive from `dispatched.log` (which is append-only spawn history).
