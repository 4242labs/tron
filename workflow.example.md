# workflow.md — Example

The orchestration rules for this project. The seeder copies this as a starting point; edit freely afterwards. TRON re-reads on session start and updates `workflow-state.md` accordingly.

This file is the source of truth for rules + tunable knobs. The live counters TRON tracks (current block, blocks-since-review, etc.) live in `workflow-state.md`.

---

## Rules

### R1 — Architect runs persistent in background

One architect is spawned at session start and stays alive in BG for the whole session, regardless of how many engineers run. The architect is the standing consultant — not bound to a block.

### R2 — Engineer technical question → architect (peer-consult)

If an engineer hits a technical/design question (architecture, library choice, schema, API shape), the engineer consults the architect **directly** via `claude --resume {ARCH_SESSION_ID} -p "[ENG-{ID} → ARCH] <q>"` per Premise 18. Architect replies **directly** via `claude --resume {ENG_SESSION_ID} -p "[ARCH-PERSIST → ENG-{ID}] <a>"`. TRON does not relay; TRON observes the exchange on its next sweep. Operator is not interrupted for in-domain questions.

### R3 — Wall hits involving UI / user journey → operator

If the work hits a wall outside backend (UI rendering, copy, end-to-end user flow, third-party dashboard config, DNS, anything in `project.md` "Operator-only tasks"), TRON escalates to the operator. Engineer pauses; operator decides next step.

### R4 — Reviewer cadence

Every N engineer blocks completed, TRON spawns a reviewer over the merged work. If the reviewer reports findings, TRON routes remediation back to a fresh engineer (per R6).

### R5 — Architect mid-session review

After every engineer session-end, before dispatching the next block, TRON sends the just-completed execute-phase logs to the architect. Architect reviews for consistency with prior blocks and may recommend adjustments to upcoming blocks. TRON applies adjustments to `workflow-state.md` and the next dispatch.

### R6 — Fresh engineer per block

Each new block gets a freshly spawned engineer. No re-use of prior engineer sessions across blocks. Worker IDs follow the project's pattern from `project.md`.

### R7 — Workers never self-terminate

Engineers, architects, and reviewers do not call `claude stop` on themselves. Their session-end skills write closeout logs, then idle. Only TRON kills processes, and only after sending explicit RELEASE.

### R8 — Protected branches (no direct commits)

The per-repo protected default branches are listed in `project.md` § Protected branches. **No agent — including TRON itself — may commit directly to a protected branch.** All edits go through a feature branch (`feat|fix|chore/<slug>`) in a worktree → PR → CI green → manual merge. Workers (engineer / architect / reviewer / data-architect) follow the project's worktree-and-branching skill. TRON's own *config* edits follow `skill-edit-self` Mode A; TRON's *runtime state* (gitignored files like `workflow-state.md`, `state.md`, `dispatched.log`, `current-id`, `tg-inbox.jsonl`, `logs/`) is edited in place via Mode B and is not subject to this rule.

---

## Per-session knobs (TRON asks at session start; no defaults)

TRON asks the operator for these values at the start of every session. No defaults — TRON does not proceed until both are answered. Live values land in `workflow-state.md`.

| Knob | Notes |
|:--|:--|
| `max_concurrent_engineers` | Hard cap; TRON refuses to spawn beyond this in the session |
| `session_end_idle_min` | If no operator activity for this many minutes and no work in flight, TRON proposes session end |

## Fixed config (set once; never asked)

Project-stable values. Operator edits this file (or asks TRON to edit) to change them.

| Knob | Default | Notes |
|:--|:--|:--|
| `reviewer_threshold` | 3 | R4 N value — every N blocks triggers a reviewer |
| `silence_ping_min` | 6 | Worker silent this long (no `lastActivityAt` growth, no uncommitted worktree changes) → TRON pings `[TRON] HEARTBEAT?`. Must be a multiple of the cron sweep cadence (default `*/2` → 6 is the 3rd tick). |
| `silence_escalate_min` | 8 | Worker silent past this with no ping response → TRON escalates to operator. Must be a multiple of cron cadence; difference from `silence_ping_min` defines the response window (2 min = one tick by default). |

## Peer consults (Premise 18)

Workers may consult declared peers without going through TRON, only on the project-defined list. The list is set by the seeder per project (Step 3 of `tron-seed.md`) — **canon ships no defaults**. Pairs may be added or removed during the project's life via `skill-edit-self`. Consultation is logged; TRON picks it up on next sweep.

Format: a markdown table with columns `Worker | May consult | For`. Each row declares a peer pair the project allows.

Example (illustrative; not seeded by default):

```
| Worker | May consult | For |
|:--|:--|:--|
| engineer | architect | technical/design questions |
| reviewer | architect | architectural concerns during review |
```

Anything outside the project's list goes through TRON. Enforcement is by construction: TRON only shares peer session IDs in handovers per this table; workers cannot reach undeclared peers because they don't know the IDs.

---

## Counters (live in `workflow-state.md`)

TRON updates these every turn — do not hand-edit:

- `current_block` — block ID currently in progress
- `active_workers` — list of currently-spawned worker IDs with roles + statuses
- `blocks_since_review` — increments on engineer DONE; resets when reviewer dispatched
- `reviewer_findings_open` — count of unresolved findings
- `paused_for_operator` — worker ID (or `TRON`) currently awaiting operator
- `session_started_at`, `tron_session_id` — set on cold start
- Live values of the per-session knobs above

---

**Changing a rule or knob:** describe the change to TRON in natural language. TRON owns `workflow.md`, `workflow-state.md`, and `scripts.md` edits — it keeps all three in sync atomically. Hand-editing one risks drift; `skill-validate` will flag mismatches on next session start.
