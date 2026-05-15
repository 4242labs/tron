# skill-session-end-tron

End the TRON session cleanly. Distinct from worker session-end skills.

## When to invoke

- Operator says session is done (e.g. "TRON, end session").
- `workflow-state.md` shows all blocks complete, no `paused_for_operator`, no `reviewer_findings_open`, and operator has not assigned a new block in N minutes.

## Steps

1. **Snapshot state:** copy `workflow-state.md` to `logs/state-snapshot-{date}-{time}.md`.

2. **RELEASE all active workers** in `active_workers`:
   - For each worker: `claude --resume {session_id} -p "[TRON] @{id}: RELEASED — session complete. Run your session-end skill, then idle."`
   - Update worker status to `released`.

3. **Wait for worker session-end completion** (up to 60s per worker):
   - Poll `~/.claude/jobs/{id}/state.json` `status` field.
   - Worker should report final close-out activity, then go idle.

4. **Kill worker processes:**
   - For each worker: `claude stop {session_id}` (or equivalent kill via Agent View).
   - Remove from `active_workers`.

5. **Write session log:**
   - Path: `logs/log-{YYMMDD-HHMM}-{slug}.md`
   - Contents: session start time, blocks completed, workers spawned, escalations, findings, anomalies.

6. **Update lifetime counters** in `state.md`:
   - `total_sessions` += 1
   - `total_blocks_completed` += blocks finished this session
   - `total_workers_spawned` += spawns this session
   - `total_operator_escalations` += escalations this session
   - `last_session_id` = current TRON session id

7. **Truncate `dispatched.log`** (or rotate to `logs/dispatched-{date}.log`). Fresh start next session.

8. **Clear `current-id`:** truncate to empty. Workers from prior sessions trying to resume will fail loudly, which is correct.

9. **Reset `workflow-state.md`** for next session:
   - `current_block`: null
   - `active_workers`: []
   - Keep counters intact unless operator says "fresh start".

10. **Final message to operator:**
    ```
    TRON: session ended.
    - Blocks: {N}
    - Workers: {N}
    - Escalations: {N}
    - Log: logs/log-{date}-{slug}.md
    ```

11. **TRON idles.** Operator closes the terminal session when ready. TRON does not call `claude stop` on itself — let the operator end the parent session.

## Failure modes

- **Worker won't acknowledge RELEASE within 60s:** force-stop and log discrepancy. Operator notified.
- **`gh` or filesystem error mid-shutdown:** continue best-effort, log what failed, escalate to operator via Telegram if possible.
- **Operator interrupts mid-shutdown:** abort cleanly — re-validate state and resume normal mode.
