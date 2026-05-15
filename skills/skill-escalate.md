# skill-escalate

Escalate to the operator via Telegram. The mechanism (`tg-send.sh`) lives in `scripts/`; this skill defines when and what.

## When to invoke

- Worker hits a UI/user-journey wall (workflow R3).
- T1/T5 task (operator-only: DNS, third-party dashboard, manual verify).
- Worker silent past Tier 2 stall and TRON self-validate failed (Premise 23).
- Operator-required decision (workflow change, scope question, license/policy).
- Repeated failure (3+ consecutive engineer DONEs reverted by reviewer or by TRON self-validate).

## Inputs

- `worker_id` (or `null` for TRON-initiated)
- `block_id` (or `null`)
- `reason` — one-line category (e.g. `WALL`, `STALL`, `DECISION`, `REPEATED_FAILURE`)
- `summary` — concise (2–4 sentences); what's blocking, what TRON has tried, what TRON needs from operator

## Steps

1. **Compose the message:**
   ```
   [TRON ESCALATE — {reason}]
   block: {block_id or "—"}
   worker: {worker_id or "TRON"}
   {summary}
   
   Reply with: "TRON, <instruction>" to resolve.
   ```
   Keep under 800 chars; Telegram is operator-facing, not log-facing.

2. **Send:**
   ```
   bash meta/agents/tron/scripts/tg-send.sh "<composed message>"
   ```

3. **Verify send:** script exits 0 on success. On non-zero:
   - Retry once.
   - If still failing: log to `logs/escalate-failures-{date}.log` and surface to operator on next CLI interaction.

4. **Update state:**
   - In `workflow-state.md`: `paused_for_operator = {worker_id}` (if worker-bound) or `paused_for_operator = "TRON"`.
   - Increment `total_operator_escalations` in `state.md`.

5. **Hold the worker** (if applicable):
   - Send `[TRON] @{id}: HOLD — operator notified, await further instructions.`
   - Worker idles. Do not RELEASE.

6. **Resume on operator reply:**
   - Operator's reply comes back via `tg-poll.sh` → `tg-inbox.jsonl`.
   - Sweep picks up the message and routes back to TRON.
   - TRON parses operator instruction, lifts `paused_for_operator`, and either RELEASEs the worker or sends new directives.

## Failure modes

- **`tg-send.sh` not configured / `.env` missing keys:** invoke `skill-doctor` to diagnose; surface to operator next CLI message; do not retry blindly.
- **Telegram API rate limit:** back off, retry after sweep cycle; do not block other work.
- **Operator silent for > 30 min after escalation:** TRON does nothing — operator absence is operator absence. Worker idles; TRON keeps running sweeps and TG poll.
