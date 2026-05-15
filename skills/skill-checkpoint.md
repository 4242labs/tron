# skill-checkpoint

Handle a worker callback message (STARTED, HEARTBEAT, MILESTONE, DONE, WALL, QUESTION, FINDINGS).

## When to invoke

Any inbound message TRON receives via `claude --resume` with a `[ROLE-ID]` prefix.

## Steps

1. **Parse the prefix** to identify the worker. Match against `active_workers` in `workflow-state.md`. If unknown sender → log to `logs/` and ignore (could be a stale RESUME from a prior session).
2. **Classify the message:**
   - `STARTED` → update worker status to `working`. Log timestamp. No further action.
   - `HEARTBEAT` → update `last_seen_at` for worker. No further action.
   - `MILESTONE` → log. Update worker status. No further action.
   - `DONE` → see § DONE path.
   - `WALL` → see § WALL path.
   - `QUESTION` or `[ROLE-ID → ARCH]` → see § Question routing.
   - `FINDINGS` (reviewer) → see § Reviewer findings.
   - `R5_REPORT` (architect) → see § Architect review.

## DONE path

1. Extract PR URL from message. Verify: `gh pr view {N} --json url,state,statusCheckRollup`. PR open + CI green required.
2. If not green: send back `[TRON] @{ID}: FAIL — CI not green: {summary}`. Worker idles.
3. Send SV-01: `[TRON] @{ID}: SV-01 — confirm AC line-by-line against {block_spec_path}.`
4. Wait up to 2 sweep cycles. If no SV-01 reply → invoke `skill-validate` self-check (TRON reads block spec + PR diff itself).
5. If validation PASS: forward execute-phase log path to architect (R5): `[TRON] @ARCH-PERSIST: EXECUTE_LOG_REVIEW block={BLOCK_ID} log={LOG_PATH}`.
6. On architect R5_REPORT:
   - `"no changes"` → send RELEASE.
   - findings → spawn fresh engineer via `skill-dispatch` for remediation.
7. **RELEASE:** `[TRON] @{ID}: RELEASED — session complete. Run session-end-engineer, then idle.`
8. Wait 60s for worker's session-end completion (state.json activity).
9. `claude stop {SESSION_ID}`.
10. Update `workflow-state.md`: remove from `active_workers`, increment `blocks_since_review`, clear `current_block` if it matches.
11. If `blocks_since_review >= reviewer_threshold`: dispatch reviewer.

## WALL path

1. Compose escalation: worker, block, summary, what TRON has tried.
2. Invoke `skill-escalate`.
3. Set `paused_for_operator = {WORKER_ID}` in `workflow-state.md`.
4. Reply to worker: `[TRON] @{ID}: HOLD — operator notified, await further instructions.`
5. Do not RELEASE the worker. It idles.

## Question routing

1. If sender is engineer and `→ ARCH` present: forward verbatim to architect via `claude --resume {ARCH_SESSION_ID}`.
2. Wait for architect reply (sweep cycle).
3. Relay reply back to engineer via `claude --resume {ENG_SESSION_ID}`.

## Reviewer findings

1. Parse findings list. Count blockers / majors / minors.
2. Update `workflow-state.md`: `reviewer_findings_open = blocker_count + major_count`.
3. If blockers + majors > 0: dispatch fresh engineer via `skill-dispatch` for remediation. Pass findings as block spec.
4. If clean: send RELEASE to reviewer.

## Architect review (R5_REPORT)

1. Parse report.
2. If recommends adjustments to upcoming blocks: invoke `skill-edit-self` to update `workflow-state.md` notes + adjust dispatch params for the next engineer.
3. Architect stays alive (persistent).

## Failure modes

- **Worker session no longer alive when we try to RELEASE:** log discrepancy, purge from `active_workers`, move on.
- **PR check via `gh` fails (auth, network):** retry once; if still failing, escalate to operator.
