# skill-update

Pull updates from the canon `tron/` repo into the local instance (Premise 10). Diff / accept / reject per file.

## When to invoke

- Operator says "TRON, check for canon updates."
- Quarterly check (manual; no auto-update).
- After a canon repo release tag the operator wants to adopt.

## Inputs

- `canon_path` — local path to a clone of `github.com/42piratas/tron` (operator must clone or pull first).
- `target_version` (optional) — git ref to update against. Default: latest tag.

## Steps

1. **Confirm canon path** exists and is a git repo. Pull latest: `git -C {canon_path} pull`.

2. **Identify candidates** — files that exist in both canon and local instance:
   - `skills/skill-*.md` (each one independently diffable)
   - `templates/*.md`
   - `scripts/*.sh`
   - `tron-scripts.md` (operator-extended; needs care)
   - `tron-seed.md` (not user-facing; safe to update)
   - `project.example.md`, `workflow.example.md` (reference only; safe to update silently)

3. **Skip from update** — files that are operator-owned in the local instance:
   - `project.md`, `workflow.md`, `workflow-state.md`, `state.md`, `scripts.md` (after operator customization), `dispatched.log`, `current-id`, `seed-trace.md`, `logs/*`, `tg-inbox.jsonl`

4. **For each candidate, diff:**
   ```
   diff -u {canon_path}/{file} {local_path}/{file}
   ```
   Present to operator concisely:
   ```
   skill-dispatch.md — 3 hunks changed
     +12 -8 lines
     Summary: <one-line summary of change intent>
   Accept? (y/n/show)
   ```

5. **Operator response per file:**
   - `y` → copy canon file over local; log to `logs/update-{date}.log`.
   - `n` → skip; log decision.
   - `show` → print full diff; re-prompt.

6. **After all files processed:**
   - Re-run `skill-validate` (doc-drift mode) to ensure local docs still cohere.
   - Re-run `skill-doctor` to ensure structural integrity.
   - Update `state.md` notes: `last_canon_update_at = {timestamp}, canon_ref = {tag or sha}`.

7. **Report to operator:**
   ```
   TRON: canon update applied.
   - Accepted: {N} files
   - Skipped: {N} files
   - Validate: pass / drift
   - Doctor: pass / issues
   ```

## Failure modes

- **Canon path not provided / not a clone:** ask operator to clone `github.com/42piratas/tron` and provide the path.
- **Operator-customized file diverges from canon and operator wants to keep both:** flag for manual merge; do not auto-resolve.
- **`scripts.md` divergence:** treat as operator-customized by default. Show diff but require explicit accept; never auto-overwrite.
