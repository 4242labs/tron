# skill-validate

Detect drift between TRON's own docs (Premise 11) and self-validate worker work when worker is unresponsive (Premise 23).

Two modes: **doc-drift** (session start) and **worker-AC** (worker silent post-DONE).

---

## Mode A — doc-drift (session start)

### When to invoke

- Every session start, after reading the 6 boot files.
- After any `skill-edit-self` run, to confirm no drift was introduced.

### Steps

1. **Read** `workflow.md`, `workflow-state.md`, `scripts.md`, `project.md`.
2. **Cross-check rules vs counters:**
   - `workflow.md` mentions a counter (e.g. `blocks_since_review`)? → confirm it exists in `workflow-state.md`.
   - `workflow-state.md` has counters with no corresponding rule? → flag as orphan.
3. **Cross-check rules vs scripts:**
   - `workflow.md` mentions a situation (e.g. wall → operator)? → confirm `scripts.md` has a matching entry.
4. **Cross-check `project.md` paths:**
   - Worktrees dir exists?
   - Required canon agent files exist (`architect.md`, `engineer.md`, `reviewer.md`)?
   - `.env` exists and has declared keys?
5. **Report findings:**
   - Clean → log `validate: pass` and return.
   - Drift → present to operator:
     ```
     TRON: drift detected between docs.
     - <issue 1>
     - <issue 2>
     Want me to fix via skill-edit-self? (y/n)
     ```
   - Wait for operator confirmation. Do not auto-fix.

### Failure modes

- Missing file → escalate immediately (TRON cannot function without all 6 docs).

---

## Mode B — worker-AC (worker unresponsive post-DONE)

### When to invoke

- Worker sent DONE; SV-01 query unanswered after 2 sweep cycles.

### Steps

1. **Read block spec** from `current_block` path. Extract AC list.
2. **Read PR diff:** `gh pr diff {N}`.
3. **Read PR status:** `gh pr view {N} --json url,state,statusCheckRollup,reviewDecision`.
4. **For each AC item:**
   - Grep the diff for the expected file/change.
   - If AC is testable: confirm tests for it exist and CI is green.
   - Mark PASS / FAIL / UNCERTAIN.
5. **Decide:**
   - All PASS → proceed to architect R5 review path in `skill-checkpoint`. Effectively treat worker as having SV-01 passed.
   - Any FAIL → invoke `skill-escalate` with `reason=REPEATED_FAILURE` or `reason=WORKER_UNRESPONSIVE`. Do not RELEASE the worker.
   - Any UNCERTAIN → escalate; ask operator to verify manually.
6. **Log:** append result to `logs/self-validate-{date}.log`.

### Failure modes

- **`gh` not authenticated:** escalate to operator immediately; cannot self-validate without GitHub access.
- **PR not found:** worker reported a bogus URL; escalate.
