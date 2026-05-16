# skill-edit-self

TRON owns its own docs (Premise 14). Any edit to `workflow.md`, `workflow-state.md`, `scripts.md`, `state.md`, or `project.md` goes through this skill — never via direct `Edit` or operator hand-editing — to keep all docs in sync atomically.

## When to invoke

- Operator describes a workflow change in natural language ("change reviewer threshold to 5", "add a peer consult pair", "add a script for X situation").
- Internal state update (counters, active workers, session ID) — invoked automatically by `skill-dispatch`, `skill-checkpoint`, etc.
- `skill-validate` detected drift and operator approved fix.

## Edit modes

Two modes — they differ in commit policy. Decide which mode applies before editing.

**Mode A — Config edits** (tracked files): `workflow.md`, `scripts.md`, `project.md`, `tron.md`, anything under `skills/`, `templates/`. These changes go through a feature branch in a worktree → commit → PR → CI green → manual merge into the repo's protected default branch (per `workflow.md` R8). Direct edits in the main checkout are forbidden — TRON has no exception. The operator approves the diff before commit; the merge happens through the normal PR review path.

**Mode B — Runtime state updates** (gitignored files): `workflow-state.md`, `state.md`, `dispatched.log`, `current-id`, `tg-inbox.jsonl`, `logs/`. Edited in place — no branch, no commit. These files are never tracked, so changes never become commits. Atomic-write semantics still apply within Mode B (all dependent runtime files updated together; on write failure, revert).

If unsure which mode: check `meta/agents/tron/.gitignore`. Listed → Mode B. Not listed → Mode A.

## Inputs

- `intent` — what the operator wants changed (natural language) OR the structured update from another skill.
- `target_files` — usually inferred; one or more of `workflow.md`, `workflow-state.md`, `scripts.md`, `state.md`, `project.md`.
- `mode` — A (config / branched) or B (runtime / in-place); inferred from `target_files` against `.gitignore`.

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

4. **Pick the working tree (Mode A only).**
   - If a TRON-owned worktree for an open feature branch already exists (e.g. from earlier in this session): reuse it.
   - Otherwise create one: `git -C {meta_repo} worktree add {worktrees_dir}/{repo}--{branch} -b {branch} {protected_branch}` where `{branch}` follows the project's branch-naming convention (e.g. `chore/tron-update-<slug>`).
   - All Mode A writes happen inside the worktree, never in the main checkout.
   - For Mode B (runtime state): writes happen in place at `meta/agents/tron/<file>`. Skip this step.

5. **Atomic write:**
   - Write all changed files in one batch (in the worktree for Mode A; in place for Mode B).
   - On any write failure: revert all writes from this invocation.
   - Never leave the docs in a partially-updated state.

6. **Re-run `skill-validate` (doc-drift mode)** post-write. If drift detected: revert and escalate.

7. **Commit + push + open PR (Mode A only).**
   - `git -C {worktree} add <files>` (named files only — never `git add -A`, runtime state must not be staged).
   - Commit with a scoped lowercase subject (e.g. `chore(tron): <short summary>`).
   - `git push -u origin {branch}`.
   - `gh pr create --base {protected_branch} --title "<subject>" --body "<intent + files changed>"`.
   - Skip for Mode B.

8. **Log the edit:** append to `logs/edits-{date}.log`:
   ```
   {ISO_TS} | edit-self | mode={A|B} | intent="{intent}" | files=[{list}] | branch={branch_or_-} | pr={pr_url_or_-} | result=ok
   ```

9. **Echo to operator** (if operator-invoked):
   - Mode A: `TRON: branched + PR'd. {N} files updated. PR: {url}. Awaiting your merge.`
   - Mode B: `TRON: applied in place (runtime). {N} files updated.`

## Failure modes

- **Operator describes a change that requires altering an immutable doc** (e.g. `project.md` `repo_root`): refuse; surface that this is a re-seed concern, not a runtime edit.
- **Drift after atomic write:** revert all changes; escalate to operator.
- **Operator hand-edits a TRON-owned file directly** (caught by `skill-validate` on next session start): refuse to start; ask operator to either revert or describe the change so TRON can re-apply it cleanly.
- **Mode A attempted while CWD is a protected default branch:** abort the write, create the worktree first per Step 4, then redo. Never write Mode A files into the main checkout.
- **Mode B file accidentally tracked** (e.g. a state file appears in `git status` because gitignore is missing an entry): refuse to write; surface to operator that the gitignore needs fixing first (treat the gitignore fix itself as Mode A).
