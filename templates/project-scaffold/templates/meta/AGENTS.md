# <PROJECT_NAME> — meta/

Project management, agents, skills, and session logs for `<PROJECT_NAME>`.

**Always invoke the agent runtime from the workspace root, not from inside this repo.**

## Agents

| Agent | File | Purpose |
|-------|------|---------|
| Architect | `agents/architect.md` | System design, scoping, trade-off analysis |
| Engineer | `agents/engineer.md` | Build, maintain, ship |
| Data Architect | `agents/data-architect.md` | Schema design, RLS policy review, PII governance |
| Code Reviewer | `agents/reviewer-code.md` | Code quality audits |
| Security Reviewer | `agents/reviewer-security.md` | Security posture audits |
| TRON-FLYNN | `agents/flynn-local.md` | Workflow health monitoring |

## Skills

Single home: `principles.md §Skills Registry` (skill ↔ file ↔ trigger). Don't restate the table here — read it there. Skill files live in `skills/`.

## Key Files

- `pipeline.md` — Single source of truth for all active work
- `pipeline-archive.md` — Completed phases + resolved tech debt
- `backlog.md` — Diverse ideas not yet roadmapped
- `context.md` — Project context: background, goals, constraints
- `principles.md` — Agent behavior rules
- `blocks/block-template.md` — Canonical block spec template
- `lens/` — Read-only HTML lens over pipeline / TD / backlog / archive (see `lens/README.md` for build + Cloudflare deploy)
