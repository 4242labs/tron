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

7. **Commit, land, clean up.** Run the shared protocol — `../shared/skill-branching.md` §Session end.
   Per repo with changes: commit → push → `app` gets a PR the operator clicks, `canon|meta` gets an
   FF-merge → then branch and worktree cleanup.

   FLYNN's delta: the branch must already match `chore/flynn-YYYYMMDD-<slug>` with a slug from the
   `flynn.md` §Operating Rules vocabulary — if it doesn't, rename or escalate (C1 finding). Anything
   left behind after cleanup is a C1 finding to log, not to hide.

9. **Confirm next run** — recommend next TRON-FLYNN run date based on session frequency.
