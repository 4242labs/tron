# SUPER-M (Local Wrapper)

Workflow health monitoring for <PROJECT_NAME>.

---

## What This Is

This is a **project-local wrapper** around the canonical SUPER-M agent at `42hq/super-m/super-m.md`. Load that file first, then apply the project context below.

Do NOT run this wrapper without first loading the canonical SUPER-M agent from 42Agents path. The wrapper only provides project-specific context — the full procedure is in the canonical file.

---

## Project Context

| Item | Value |
|------|-------|
| Project name | `<PROJECT_NAME>` |
| Pipeline file | `<META_REPO_NAME>/pipeline.md` |
| App repo | `<APP_REPO_NAME>/` |
| Meta repo | `<META_REPO_NAME>/` |
| Workspace path | `<WORKSPACE_PATH>` |

## Agent Registry

| Role | File |
|------|------|
| Architect | `<META_REPO_NAME>/agents/architect.md` |
| Engineer | `<META_REPO_NAME>/agents/engineer.md` |
| Data Architect | `<META_REPO_NAME>/agents/data-architect.md` |
| Code Reviewer | `<META_REPO_NAME>/agents/reviewer-code.md` |
| Security Reviewer | `<META_REPO_NAME>/agents/reviewer-security.md` |
