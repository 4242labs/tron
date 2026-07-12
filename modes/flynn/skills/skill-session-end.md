# Skill: Session End

Default session end protocol for TRON-FLYNN. Run at the end of every session.

---

## Steps

1. **Write session log** to `{meta}/logs/flynn/log-YYMMDD-HHMM-{desc}.md` (format in `flynn.md` §Session Log Format)

2. **Update project-local context** (`{meta}/agents/flynn-local.md`):
   - Update `last_run` date
   - Update `## Category Check Dates` with today's date for each category audited
   - Update `last_deep_dive` to the category deep-dived this session
   - Record any persistent observations under `## Persistent Watch Items`
   - Trim resolved watch items

3. **Surface improvements** — if improvements were proposed during the session → list them as a numbered checklist for the user

4. **Flag needed updates** to the active pipeline, agent docs, block plans, or shared skills to the user. If user approves → apply the changes. (If the project has a pipeline archive, do not modify it — archival decisions belong to whoever owns project architecture.)

5. **Cross-project knowledge check** — review session findings for anything applicable beyond this project — workflow patterns, templates, skill refinements, KB sections. If a shared knowledge base is configured → update the relevant files in `{shared_knowledge_path}/`.

6. **Self-improvement check** — review session for replicable improvements to TRON-FLYNN's own agent doc, skills, templates, or output formats. Run `skills/skill-self-improvement.md` if improvements are identified.

7. **Commit, merge, push, clean up.** Never commit on `main`; never push direct to `main`. Per repo with changes:
   - Branch must already match `chore/flynn-YYYYMMDD-<slug>` from `flynn.md` §Operating Rules vocabulary. If it doesn't → rename or escalate (C1 finding).
   - `git add -A && git commit -m "{conventional message}"` and `git push -u origin <branch>`
   - **`.repo-class=app`** → `gh pr create --base main` and `gh pr checks {PR} --watch`. User performs the merge click; do not arm auto-merge.
   - **`.repo-class=canon|meta`** → no PR required. From the main checkout: `git fetch origin && git checkout main && git pull --ff-only && git merge --ff-only <branch> && git push origin main`. Push the branch (it's already pushed in the previous step) so the pre-push reachability check has a target ref.

8. **Branch + worktree cleanup (C1).** After merge:
   - [ ] `git branch -d <branch>` (local) and `git push origin --delete <branch>` (remote)
   - [ ] `git worktree remove <path>` (or `git worktree prune` if the directory was already deleted)
   - [ ] Verify clean state: `git branch --list 'chore/flynn-*'` and `git branch -r --list 'origin/chore/flynn-*'` both empty; `git worktree list` shows no leftover TRON-FLYNN worktrees. Anything left = C1 finding to log.

9. **Confirm next run** — recommend next TRON-FLYNN run date based on session frequency.
