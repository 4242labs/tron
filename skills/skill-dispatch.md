# skill-dispatch

Spawn a worker (engineer / architect / reviewer) into Agent View as a BG process.

## When to invoke

- New block dispatch (engineer)
- Session start with no persistent architect (architect)
- `blocks_since_review >= reviewer_threshold` (reviewer)
- Remediation of reviewer findings (fresh engineer)

## Inputs

- `role` ∈ `engineer | architect | reviewer`
- `block_id` (engineers + block-scoped reviewers; for persistent architect: use `PERSIST`)
- `branch` (engineers only; absent for architect/reviewer)
- `worktree_path` (engineers only)
- `block_spec_path` (engineers only)
- `pr_list`, `block_list`, `since_commit` (reviewers only)

## Steps

1. **Build worker ID.**
   - engineer: `ENG-{block_id without "block-" prefix}` → e.g. `ENG-06-19`
   - architect persistent: `ARCH-PERSIST`
   - architect block-scoped: `ARCH-{block_id stripped}`
   - reviewer: `REV-{YYMMDD}-{N}` where N is `reviewer_findings_open + 1` for that day
2. **Read your own session ID:** `cat meta/agents/tron/current-id`. This is the callback ID workers will use.
3. **Read the appropriate handover template** from `meta/agents/tron/templates/handover-{role}.md`.
4. **Substitute placeholders:**
   - `{BLOCK_ID}`, `{BRANCH}`, `{WORKTREE_PATH}`, `{BLOCK_SPEC_PATH}`
   - `{TRON_SESSION_ID}` (from step 2)
   - `{ARCH_SESSION_ID}` (read from `workflow-state.md` `active_workers`, role=architect-persistent; if absent for engineers, spawn architect first)
   - `{BLOCK_LIST}`, `{PR_LIST}`, `{SINCE_COMMIT}` (reviewers only)
5. **Spawn:** invoke `claude --bg -n {WORKER_ID} "<substituted handover>"`.
6. **Capture spawn confirmation.** Agent View returns a session ID. Capture it.
7. **Append to `dispatched.log`:**
   ```
   {ISO_TIMESTAMP} | spawn | {WORKER_ID} | {SESSION_ID} | block={BLOCK_ID} branch={BRANCH}
   ```
8. **Update `workflow-state.md`** via `skill-edit-self`:
   - Add to `active_workers`: `{id, role, session_id, spawned_at, status: "working"}`
   - For engineers: set `current_block`, `current_block_started_at`, `current_block_branch`
9. **Echo to operator:** `TRON: dispatched {WORKER_ID} ({SESSION_ID}) for {BLOCK_ID}.`

## Failure modes

- **No architect alive when dispatching engineer:** spawn architect first (recurse with role=architect-persistent), then proceed.
- **Worktree already exists with conflicting branch:** abort spawn, report to operator.
- **`current-id` missing:** TRON has not run session-start; bail and re-run session-start sequence.
