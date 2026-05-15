# skill-recover

Reconcile state after a TRON crash or restart mid-session (Premise 15). Uses `dispatched.log` + per-worker `state.json` only — no full action journal.

## When to invoke

- Session start when `dispatched.log` contains entries from a prior session that didn't reach clean session-end (no truncation marker).
- Operator says: "TRON, recover" after a forced restart.

## Steps

1. **Confirm prior session is dead.** Read `dispatched.log` last line — if it's the session-end truncation marker, nothing to recover; return.

2. **Build spawn list from `dispatched.log`:** parse each `spawn` line → `{worker_id, session_id, block_id, branch, spawned_at}`.

3. **Probe each spawn:**
   - `cat ~/.claude/jobs/{worker_id}/state.json` — does the file exist? Is process alive?
   - Possible per-worker states:
     - **Alive + idle:** worker waiting for TRON callback. Keep it. Mark as recoverable.
     - **Alive + working:** worktree has uncommitted changes. Keep it. Mark as recoverable.
     - **Alive + done-pending-release:** state.json shows DONE was sent; worker idling, awaiting RELEASE. Recover and process the pending DONE.
     - **Dead / no state.json:** worker terminated. Log; do not attempt to revive.

4. **Write TRON's new session ID** to `current-id`:
   ```
   echo {NEW_TRON_SESSION_ID} > meta/agents/tron/current-id
   ```

5. **Broadcast new callback ID** to each live worker:
   ```
   claude --resume {worker_session_id} -p "[TRON] CALLBACK_UPDATE — new TRON id: {NEW_TRON_SESSION_ID}. Resume normal protocol."
   ```

6. **Rebuild `workflow-state.md` `active_workers`:**
   - From the alive-probe results in step 3, recreate the list.
   - Status field reflects current probe (idle / working / done-pending-release).
   - `current_block`, `current_block_branch` reconstructed from the most recent engineer spawn that's still alive.

7. **Process pending DONEs:** for any worker in `done-pending-release` state, invoke `skill-checkpoint` DONE path manually using the captured PR URL from state.json.

8. **Log recovery:** append to `logs/recover-{date}.log`:
   ```
   recovered={N_alive} purged={N_dead} pending_done_processed={N}
   ```

9. **Report to operator:**
   ```
   TRON: recovered.
   - Workers alive: {N}
   - Workers purged (dead): {N}
   - Pending DONEs processed: {N}
   - Active block: {block_id or "none"}
   ```

10. **Resume normal sweep cycle.** Architect persistent should be re-spawned if it was dead.

## Failure modes

- **`dispatched.log` corrupt / unreadable:** skip recovery, log error, escalate; operator must manually reconcile.
- **All workers dead:** clean slate — clear `active_workers`, `current_block`, continue as fresh start.
- **Live worker won't respond to `CALLBACK_UPDATE`:** treat as dead after one retry; force-stop and purge.
