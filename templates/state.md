# state.md — TRON persistent memory

Cross-session memory. Survives TRON restarts. Edited only by TRON.

---

## Notification subscriptions

Channels TRON proactively reports to. Operator opts in/out via natural-language request.

- **Telegram:** active (chat id from `.env`)
- **Email:** off
- **Slack:** off

## Session counters

Lifetime counters across all sessions.

- `total_sessions`: 0
- `total_blocks_completed`: 0
- `total_workers_spawned`: 0
- `total_operator_escalations`: 0

## TG poll cursor

- `tg_offset`: 0
- `tg_last_poll_at`: never

## Last-known TRON session ID

- `last_session_id`: (set on each session start)

## Operator preferences (learned)

Free-form. TRON appends as it learns. Persists across sessions.

- (none yet)

---

**TRON edits this file via `skill-edit-self`.** Operator should not hand-edit; describe the change in natural language and let TRON apply it.
