# <PROJECT_NAME> — meta/

Project management, agents, skills, and session logs for `<PROJECT_NAME>`.

**Always invoke Claude from the workspace root, not from inside this repo.**

## Agents

| Agent | File | Purpose |
|-------|------|---------|
| Architect | `agents/architect.md` | System design, scoping, trade-off analysis |
| Engineer | `agents/engineer.md` | Build, maintain, ship |
| Data Architect | `agents/data-architect.md` | Schema design, RLS policy review, PII governance |
| Code Reviewer | `agents/reviewer-code.md` | Code quality audits |
| Security Reviewer | `agents/reviewer-security.md` | Security posture audits |
| SUPER-M | `agents/super-m-local.md` | Workflow health monitoring |

## Skills

| Skill | File | Used by |
|:------|:-----|:--------|
| Validate | `skills/skill-validate.md` | Engineer (stages 2 and 5 of DoD flow) |
| Block Forward Review | `skills/skill-block-forward-review.md` | Architect (supervisor-dispatched when a block lands done) |
| Review Cycle | `skills/skill-review-cycle.md` | Architect (user-initiated) |
| Code Review | `skills/skill-review-code.md` | Code Reviewer |
| Security Scan | `skills/skill-security-scan.md` | Security Reviewer |
| Worktree & Branching | `skills/skill-worktree-and-branching.md` | All agents |
| Session End — Architect | `skills/skill-session-end-architect.md` | Architect |
| Session End — Engineer | `skills/skill-session-end-engineer.md` | Engineer |
| Session End — Data Architect | `skills/skill-session-end-data-architect.md` | Data Architect |
| Session End — Code Reviewer | `skills/skill-session-end-reviewer-code.md` | Code Reviewer |
| Session End — Security Reviewer | `skills/skill-session-end-reviewer-security.md` | Security Reviewer |

## Key Files

- `pipeline.md` — Single source of truth for all active work
- `pipeline-archive.md` — Completed phases + resolved tech debt
- `backlog.md` — Diverse ideas not yet roadmapped
- `context.md` — Project context: background, goals, constraints
- `principles.md` — Agent behavior rules
- `blocks/block-template.md` — Canonical block spec template
- `lens/` — Read-only HTML lens over pipeline / TD / backlog / archive (see `lens/README.md` for build + Cloudflare deploy)
