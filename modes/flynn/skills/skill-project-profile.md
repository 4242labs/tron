# Skill: Project Profile

Shared profiling step for project scaffold and upgrade flows. Determines which templates, services, and audit rows apply.

Two modes:
- **`fresh`** — new project from zero. Ask the user every question; no inference.
- **`infer`** — existing project. Read the repo, infer answers, present for confirmation.

Lock the confirmed profile and value table before handing off to `skill-project-scaffold.md` or `skill-project-audit.md`. **No stubs for skipped services** — if a service is not confirmed, its templates, audit rows, and service-setup sections are omitted entirely.

**TRON is out of scope.** TRON seeds itself when the operator activates it in a project — scaffold, audit, and upgrade flows do not ask about it, do not copy `tron.md`/`skill-tg-comms.md`, and do not audit TRON wiring. If a project has TRON, that's TRON's own onboarding, not this skill's concern.

---

## Step 1 — Service profile (11 questions)

| # | Question | Determines |
|---|----------|-----------|
| 1 | Project type? (SaaS / internal tool / API service / other) | Tier of services to include |
| 2 | Hosting: Vercel? Railway? Both? Neither? | `deploy-notify.yml`, Vercel plugin, `services-setup.md#railway` |
| 3 | DB: Supabase? Other? None? | `staging-db.yml`, `mcp-setup.md#supabase-mcp` |
| 4 | Payments: Polar? Stripe? None? | `services-setup.md#polar` |
| 5 | Email notifications: Brevo? Resend? None? | `services-setup.md#brevo` |
| 6 | Error monitoring: Sentry? None? | `services-setup.md#sentry` |
| 7 | Analytics: Matomo? None? | `services-setup.md#matomo` |
| 8 | Affiliates: FirstPromoter? None? | `services-setup.md#firstpromoter` |
| 9 | Support ticketing: Plain? None? | `mcp-setup.md#plain` |
| 10 | Slack notifications? (yes / no) | `services-setup.md#slack`, `deploy-notify.yml` |
| 11 | AI proxy: LiteLLM on Railway? Direct API? None? | `services-setup.md#railway`, `infra/` templates |

### `infer` mode procedure

Read each of the following before asking the user; fill the table with inferred answers and a confidence note, then ask the user to confirm or correct each row:

- Workspace + app `CLAUDE.md`
- `app/package.json`, `app/.env.example`
- `app/.github/workflows/`
- `app/infra/` (if present)
- `meta/agents/`, `meta/skills/`
- `meta/principles.md`, `meta/context.md`

Unconfirmed services are excluded from downstream scaffold/audit work.

---

## Step 2 — Project values

| Value | Example |
|-------|---------|
| `PROJECT_NAME` | `myproject` |
| `WORKSPACE_PATH` | `~/projects/myproject` |
| `APP_REPO_NAME` | `myproject-app` |
| `APP_REPO_ROOT` | `~/projects/myproject/myproject-app` |
| `APP_SUBDIR` | `~/projects/myproject/myproject-app/app` |
| `META_REPO_NAME` | `myproject-meta` |
| `META_REPO_ROOT` | `~/projects/myproject/myproject-meta` |
| `GITHUB_ORG` | `alice` |
| `NODE_LTS_VERSION` | `24` |
| `STAGING_SUPABASE_URL` | `https://xyz.supabase.co` *(if Supabase)* |
| `PROD_SUPABASE_URL` | `https://abc.supabase.co` *(if Supabase)* |
| `VERCEL_PROJECT_NAME` | `myproject` *(if Vercel)* |

`infer` mode fills these from disk; `fresh` mode collects them from the user.

---

## Output

A locked `{profile, values}` pair, passed verbatim to the next skill. Re-confirm with the user before handoff — no scaffolding or upgrade work proceeds without explicit lock.
