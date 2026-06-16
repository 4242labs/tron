# SUPER-M: Project Context — <PROJECT_NAME>

Persistent state for SUPER-M sessions on `<PROJECT_NAME>`. Updated after every run.

This is the **canonical project-local template** for `super-m-local.md`. The kit ships it; `{shared_knowledge_path}/agents/super-m/super-m.md §Project-Local Context Template` and `{shared_knowledge_path}/agents/super-m/skills/skill-bootstrap.md` step 4 both defer to this file — it is the single source of the structure.

**Project-local wrapper.** SUPER-M's full procedure lives in the canonical agent at `{shared_knowledge_path}/agents/super-m/super-m.md` — load that first, then apply the context below. Do not run from this file alone; it only supplies project-specific state.

---

## Project

- **Name:** `<PROJECT_NAME>`
- **Meta path:** `<META_REPO_NAME>/`
- **App repo:** `<APP_REPO_NAME>/`
- **Workspace path:** `<WORKSPACE_PATH>`
- **Log path:** `<META_REPO_NAME>/logs/super-m/`
- **Context path:** `<META_REPO_NAME>/agents/super-m-local.md`

## Agent Registry

| Role | File |
|------|------|
| Architect | `<META_REPO_NAME>/agents/architect.md` |
| Engineer | `<META_REPO_NAME>/agents/engineer.md` |
| Data Architect | `<META_REPO_NAME>/agents/data-architect.md` |
| Code Reviewer | `<META_REPO_NAME>/agents/reviewer-code.md` |
| Security Reviewer | `<META_REPO_NAME>/agents/reviewer-security.md` |

## Run History

- **Last run:** never
- **Last deep-dive:** never (no FULL AUDIT yet)
- **Total sessions:** 0

## Category Check Dates

| ID | Category | Last Checked | Last Finding |
|:--|:--|:--|:--|
| C1 | Checklist Compliance | never | none |
| C2 | Session Log Quality | never | none |
| C3 | Pipeline & Block Plan Health | never | none |
| C4 | Agent Doc Accuracy | never | none |
| C5 | Documentation Drift | never | none |
| C6 | Cross-Session Patterns | never | none |

## Persistent Watch Items

Items that need monitoring across sessions. Remove when resolved.

| # | Since | Category | Item | Status |
|:--|:--|:--|:--|:--|

## Improvement Backlog

Proposed improvements pending review. Remove when actioned or rejected.

| # | Proposed | Description | Status |
|:--|:--|:--|:--|

## Project-Specific Rules

Curated subset of project rules SUPER-M must follow. References canonical sources — does not duplicate them. Update when project conventions change.

- **Git workflow:** {e.g., "PR-only across all repos including meta/ — see `principles.md §Git`. No direct push to a protected branch, ever."}
- **Naming conventions:** {e.g., "proper service names per `principles.md §Communication`"}
- **Security constraints:** {e.g., "never expose service-role keys — see `principles.md §Security`"}
- **Other:** {any project-specific rule that affects SUPER-M's behavior}

## Configuration

- **SUPER_META_STALE_DAYS:** 5
- **shared_knowledge_path:** {path, or blank if not configured — SUPER-M then skips all shared-KB steps}
