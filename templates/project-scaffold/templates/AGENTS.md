# <PROJECT_NAME>

<One-line description of what this project does.>

**Always invoke the agent runtime from `<WORKSPACE_PATH>` (this directory).** Invoking from inside a sub-repo creates a separate memory context.

## Structure

| Directory | Description |
|-----------|-------------|
| `<APP_REPO_NAME>/` | Git repo — <APP_STACK_SUMMARY> (app/, docs/, infra/, scripts/) |
| `<META_REPO_NAME>/` | Git repo — agents, skills, pipeline, blocks, logs |

## Agents

Invoked from `<WORKSPACE_PATH>` (this directory).

| Agent | File | Purpose |
|-------|------|---------|
| Architect | `<META_REPO_NAME>/agents/architect.md` | System design, scoping, trade-off analysis |
| Engineer | `<META_REPO_NAME>/agents/engineer.md` | Build, maintain, ship |
| Data Architect | `<META_REPO_NAME>/agents/data-architect.md` | Schema design, RLS policy review, PII governance, data contracts |
| Code Reviewer | `<META_REPO_NAME>/agents/reviewer-code.md` | Code quality audits |
| Security Reviewer | `<META_REPO_NAME>/agents/reviewer-security.md` | Security posture audits |
| SUPER-M | `<META_REPO_NAME>/agents/super-m-local.md` | Workflow health monitoring |
| Product-Designer | _(shared-KB path TBD — see TD-10)_ | Idea → backlog → pipeline block frame (problem framing, market scan, JTBD) |
| Emily | _(shared-KB path TBD — see TD-10)_ | Marketing & discoverability — positioning, go-to-market, pricing presentation, SEO, GEO/AEO |
| Analyst-Finance | _(shared-KB path TBD — see TD-10)_ | Pricing strategy, cost analysis, unit economics |
| Advisor-Legal | _(shared-KB path TBD — see TD-10)_ | Legal, compliance, privacy |
| i18n | _(shared-KB path TBD — see TD-10)_ | Multi-language localization strategy, translation quality, locale coverage |

## Skills

Procedural skills in `<META_REPO_NAME>/skills/`. Agents read and follow these during specific workflows.

Single home for the skill ↔ file ↔ trigger registry: `<META_REPO_NAME>/principles.md §Skills Registry`. Read it there rather than restating it here.

## Key Files

- `<META_REPO_NAME>/pipeline.md` — Single source of truth for all active work
- `<META_REPO_NAME>/context.md` — Project context for all agents
- `<META_REPO_NAME>/principles.md` — Agent behavior rules (includes Skills registry and Core Docs list)
- `<APP_REPO_NAME>/app/AGENTS.md` — App technical spec
- **42labs Design System (canon, cross-app)** — <https://42labs.io/design> (repo `github.com/42piratas/42labs`; optional offline mirror at `<DESIGN_SYSTEM_LOCAL_PATH>` if the contributor keeps one — never hardcode a machine-specific absolute path here per `principles-base.md §14`). Color, typography, radius, spacing, base components — shared by all Labs apps. Project-local design guidelines extend but never contradict this canon.
- `<APP_REPO_NAME>/docs/guidelines-coding.md` — Durable code standards + secure-coding baseline (anyone touching `app/`)
- `<APP_REPO_NAME>/docs/playbook-infra.md` — Infrastructure operational guide (secrets, services, rotation)
