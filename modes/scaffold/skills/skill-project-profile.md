# Skill: Project Profile (fresh)

Profiling step for a **new** project. Determines which templates, services, and setup sections apply.

Nothing is inferred from disk — the project does not exist yet. Answers come from the operator, or from a document the operator already wrote.

Lock the confirmed `{profile, values}` pair before handing off to `skill-project-scaffold.md`. **No stubs for skipped services** — if a service is not confirmed, its templates and setup sections are omitted entirely.

**TRON is out of scope.** TRON seeds itself when the operator activates it in a project — scaffold does not ask about it and does not copy `tron.md` / `skill-tg-comms.md`.

> Existing projects are not this skill's business. Auditing and upgrading a project that already exists belongs to the AUDIT mode.

---

## Step 0 — Ask for the spec first

Before asking a single question, ask:

> Do you already have a document with the project's specs — a brief, a charter, a README, notes? Point me at it (path or paste) and I'll take everything I can from it.

If the operator gives one:

1. Read it in full.
2. Fill every row of Step 1 and Step 2 you can defend from the text.
3. Present the filled table with a **Source** column: `doc` (cite the line) or `needs answer`.
4. Ask **only** the `needs answer` rows. Never re-ask what the document already settles.
5. Never invent a value the document doesn't support — an ambiguous mention is `needs answer`, not a guess.

If there is no document, run Steps 1 and 2 as a plain interview.

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

---

## Output

A locked `{profile, values}` pair, passed verbatim to `skill-project-scaffold.md`. Re-confirm the full table with the operator before handoff — no file is written without an explicit lock.
