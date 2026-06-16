# <PROJECT_NAME>

<One-line description of what this project does.>

**Always invoke Claude from `<WORKSPACE_PATH>` (this directory).** Invoking from inside a sub-repo creates a separate memory context.

## Structure

| Directory | Description |
|-----------|-------------|
| `<APP_REPO_NAME>/` | Git repo — Next.js app (app/, docs/, infra/, scripts/) |
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
| Product-Designer | `42hq/product-designer/product-designer-local.md` | Idea → backlog → pipeline block frame (problem framing, market scan, JTBD) |
| Analyst-Marketing | `42hq/analyst-marketing/analyst-marketing-local.md` | Positioning, go-to-market, pricing presentation |
| Analyst-Finance | `42hq/analyst-finance/analyst-finance-local.md` | Pricing strategy, cost analysis, unit economics |
| Advisor-Legal | `42hq/advisor-legal/advisor-legal-local.md` | Legal, compliance, privacy |
| i18n | `42hq/i18n/i18n-local.md` | Multi-language localization strategy, translation quality, locale coverage |

## Skills

Procedural skills in `<META_REPO_NAME>/skills/`. Agents read and follow these during specific workflows.

| Skill | File | Used by |
|:------|:-----|:--------|
| Block Forward Review | `skill-block-forward-review.md` | Architect — dispatched by the supervising process when a block lands done; reconcile upcoming blocks against learnings/drift |
| Review Cycle | `skill-review-cycle.md` | Architect — standalone, user-initiated cycle review (not the supervisor's review cadence) |
| Validate | `skill-validate.md` | Engineer — DoD stages 2 (local) and 5 (post-merge re-validation) |
| Code Review | `skill-review-code.md` | Code Reviewer — full audit procedure (dispatched on the review cadence) |
| Security Scan | `skill-security-scan.md` | Security Reviewer — security audit procedure (auth, RLS, secrets, integrations, deps) |
| Session End (per agent) | `skill-session-end-{role}.md` | All agents — session closure checklist |
| Worktree & Branching | `skill-worktree-and-branching.md` | All agents — branching, worktree, commit discipline |

## Key Files

- `<META_REPO_NAME>/pipeline.md` — Single source of truth for all active work
- `<META_REPO_NAME>/context.md` — Project context for all agents
- `<META_REPO_NAME>/principles.md` — Agent behavior rules (includes Skills registry and Core Docs list)
- `<APP_REPO_NAME>/app/CLAUDE.md` — App technical spec
- **42labs Design System (canon, cross-app)** — <https://42labs.io/design> (repo `github.com/42piratas/42labs`; optional offline mirror at `<DESIGN_SYSTEM_LOCAL_PATH>` if the contributor keeps one — never hardcode a machine-specific absolute path here per `principles-base.md §14`). Color, typography, radius, spacing, base components — shared by all Labs apps. Project-local design guidelines extend but never contradict this canon.
- `<APP_REPO_NAME>/docs/guidelines-coding.md` — Durable code standards + secure-coding baseline (anyone touching `app/`)
- `<APP_REPO_NAME>/docs/playbook-infra.md` — Infrastructure operational guide (secrets, services, rotation)
