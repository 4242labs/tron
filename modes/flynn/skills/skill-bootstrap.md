# Skill: Bootstrap

First-run setup when TRON-FLYNN touches a project for the first time. Called automatically by `skill-session-start.md` when `flynn-local.md` doesn't exist.

---

## Steps

1. **Ask the user to confirm paths and configuration:**
   - Project's `meta/logs/` path (or equivalent)
   - **Shared knowledge base:** Ask if the user has a shared knowledge folder (principles, reference material, shared skills). If yes → record the path as `shared_knowledge_path` in `flynn-local.md`. If no → leave blank; TRON-FLYNN skips all knowledge-base steps.

2. **Alignment check:** Verify that all paths, conventions, and references in `flynn.md` match the local project structure. Check:
   - Does `meta/logs/` exist? Does `meta/agents/` exist?
   - Does the project have `meta/pipeline.md`? Session logs?
   - Do the audit categories (C1–C6, defined in `flynn.md`) reference artifacts that exist in this project?
   - Flag any mismatches to the user before proceeding. Adapt paths in `flynn-local.md` accordingly.

3. **Create** `meta/logs/flynn/` directory if absent (projects scaffolded from the kit already ship it).

4. **Create** `flynn-local.md` in `meta/agents/` from the **canonical kit template** at `tron/tron-app/templates/project-scaffold/templates/meta/agents/flynn-local.md` (the single source — `flynn.md §Project-Local Context Template` defers to it), substituting the kit placeholders (`<PROJECT_NAME>`, `<META_REPO_NAME>`, `<APP_REPO_NAME>`, `<WORKSPACE_PATH>`) with the paths confirmed in step 2. If the project was scaffolded from the kit, the file already exists — adopt it as-is and only fill runtime values.

5. **Add** the project to `$FLYNN_ROOT/projects.md` — same row shape as `skill-session-start.md` §2, creating the file with that header if it doesn't exist yet.

6. **Run a full initial audit** — execute `skills/skill-audit.md` in FULL AUDIT mode to establish baseline.

7. **Record** findings and initial context state.
