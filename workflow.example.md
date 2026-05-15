# workflow.md — Example

This is the operator's default workflow. The seeder copies this to `meta/agents/tron/workflow.md` as a starting point. Edit freely afterwards — TRON re-reads on session start and updates `workflow-state.md` accordingly.

These are prose rules. The live counters TRON tracks (current block, blocks-since-review, etc.) live in `workflow-state.md`.

---

## Rules

### R1 — Architect runs persistent in background

One architect is spawned at session start and stays alive in BG for the whole session, regardless of how many engineers run. The architect is the standing consultant — not bound to a block.

### R2 — Engineer technical question → architect

If an engineer hits a technical/design question (architecture, library choice, schema, API shape), TRON routes the question to the architect. Architect answers; TRON relays answer back. Operator is not interrupted for in-domain questions.

### R3 — Wall hits involving UI / user journey → operator

If the work hits a wall outside backend (UI rendering, copy, end-to-end user flow, third-party dashboard config, DNS, anything T1/T5), TRON escalates to the operator via Telegram. Engineer pauses; operator decides next step.

### R4 — Reviewer cadence

Every N engineer blocks completed, TRON spawns a reviewer over the merged work. Default N = 3 (override in `workflow-state.md`). If the reviewer reports findings, TRON routes remediation back to a fresh engineer (not the original one — see R6).

### R5 — Architect mid-session review

After every engineer session-end, before dispatching the next block, TRON sends the just-completed execute-phase logs to the architect. Architect reviews for consistency with prior blocks and may recommend adjustments to upcoming blocks. TRON applies adjustments to `workflow-state.md` and the next dispatch.

### R6 — Fresh engineer per block

Each new block gets a freshly spawned engineer. No re-use of prior engineer sessions across blocks. Worker IDs follow `ENG-MM-DD` (block ID). Operator preference for clean state per block.

### R7 — Workers never self-terminate

Engineers, architects, and reviewers do not call `claude stop` on themselves. Their session-end skill writes a closeout log, idles, and waits for TRON's explicit RELEASE. Only TRON kills processes. (Premise 20, derived from incident 260411.)

---

## Peer consults (Premise 18)

Workers may consult declared peers without going through TRON, **only on this list**. Consultation is logged; TRON picks it up on next sweep.

| Worker | May consult | For |
|:--|:--|:--|
| engineer | architect | technical/design questions |
| reviewer | architect | architectural concerns during review |

Anything outside this list goes through TRON.

---

## Counters (live in `workflow-state.md`)

TRON updates these every turn — do not hand-edit:

- `current_block` — block ID currently in progress
- `blocks_since_review` — increments on engineer DONE; resets when reviewer dispatched
- `reviewer_findings_open` — count of unresolved findings
- `active_workers` — list of currently-spawned worker IDs
- `session_started_at` — TRON session start time

---

**Want to change a rule?** Talk to TRON. TRON owns `workflow.md`, `workflow-state.md`, and `scripts.md` edits — it keeps all three in sync. Hand-editing one risks drift; the validator skill will flag mismatches on next session start.
