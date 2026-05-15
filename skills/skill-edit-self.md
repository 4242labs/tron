# skill-edit-self

TRON owns its own docs (Premise 14). Any edit to `workflow.md`, `workflow-state.md`, `scripts.md`, `state.md`, or `project.md` goes through this skill — never via direct `Edit` or operator hand-editing — to keep all docs in sync atomically.

## When to invoke

- Operator describes a workflow change in natural language ("change reviewer threshold to 5", "add a peer consult pair", "add a script for X situation").
- Internal state update (counters, active workers, session ID) — invoked automatically by `skill-dispatch`, `skill-checkpoint`, etc.
- `skill-validate` detected drift and operator approved fix.

## Inputs

- `intent` — what the operator wants changed (natural language) OR the structured update from another skill.
- `target_files` — usually inferred; one or more of `workflow.md`, `workflow-state.md`, `scripts.md`, `state.md`, `project.md`.

## Steps

1. **Parse intent.** Identify:
   - Which file(s) own the change.
   - Which dependent files need a consistent update.

   Example: operator says "change reviewer threshold to 5":
   - Primary: `workflow.md` R4 prose ("default N = 3" → "default N = 5").
   - Dependent: `workflow-state.md` `reviewer_threshold: 5` (was 3).
   - Dependent: `scripts.md` may reference the threshold in narrative — re-read and update if so.

2. **Stage edits in memory.** Compute the exact new content of each affected file.

3. **Show operator the diff** (if invoked by operator request, not by internal skill):
   ```
   TRON: applying these edits.
   - workflow.md: R4 threshold 3 → 5
   - workflow-state.md: reviewer_threshold 3 → 5
   Confirm? (y/n)
   ```
   For internal skill invocations (state updates), skip this step.

4. **Atomic write:**
   - Write all changed files in one batch.
   - On any write failure: revert all writes from this invocation.
   - Never leave the docs in a partially-updated state.

5. **Re-run `skill-validate` (doc-drift mode)** post-write. If drift detected: revert and escalate.

6. **Log the edit:** append to `logs/edits-{date}.log`:
   ```
   {ISO_TS} | edit-self | intent="{intent}" | files=[{list}] | result=ok
   ```

7. **Echo to operator** (if operator-invoked):
   ```
   TRON: applied. {N} files updated. Validate: pass.
   ```

## Failure modes

- **Operator describes a change that requires altering an immutable doc** (e.g. `project.md` `repo_root`): refuse; surface that this is a re-seed concern, not a runtime edit.
- **Drift after atomic write:** revert all changes; escalate to operator.
- **Operator hand-edits a TRON-owned file directly** (caught by `skill-validate` on next session start): refuse to start; ask operator to either revert or describe the change so TRON can re-apply it cleanly.
