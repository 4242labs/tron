# Infrastructure Playbook — <PROJECT_NAME>

Operational guide for infrastructure, secrets, and services. Keep this document current.

---

## 1. Supabase

### Projects

| Environment | Project | URL |
|-------------|---------|-----|
| Staging | `<project>-staging` | `<STAGING_SUPABASE_URL>` |
| Production | `<project>-prod` | `<PROD_SUPABASE_URL>` |

### Migrations

Applied via `supabase db push` or automatically via `staging-db.yml` CI workflow.

Always test migrations on staging before applying to production.

### Secret Rotation

| Secret | Rotation frequency | Location |
|--------|-------------------|----------|
| `SUPABASE_SERVICE_ROLE_KEY` | On team change | Vercel env + `.env.local` |
| `SUPABASE_JWT_SECRET` | On breach | Supabase dashboard → JWT Settings |
| `ENCRYPTION_KEY` | On breach | Vercel env + `.env.local` |

---

## 2. Vercel

### Environments

| Surface | URL | Source |
|---------|-----|--------|
| Production | `https://<domain>` | `main` branch |
| Staging | `https://staging.<domain>` | `staging` branch |
| Per-PR Preview | `https://<project>-git-<branch>.vercel.app` | Feature branches |

### Environment Variables

Managed via Vercel dashboard → Project → Settings → Environment Variables.

Production-only secrets (never set on staging/preview):
- `BREVO_API_KEY`
- `SENTRY_DSN`
- `FP_API_KEY`

---

## 3. Railway / LiteLLM

### Deployment

- Project: `<project>-litellm` on Railway
- Config: `infra/litellm_config.yaml`
- Entrypoint: `infra/litellm-entrypoint.sh` (drops conflicting Prisma view on cold start)
- Image: `ghcr.io/berriai/litellm:main-v1.63.14-stable` (pinned — do NOT update without testing)

### Spend Dashboard

Access: `<railway_url>/ui`  
Credentials: `LITELLM_UI_USERNAME` / `LITELLM_UI_PASSWORD` (Railway env vars)

### Secret Rotation

Rotate `LITELLM_MASTER_KEY`:
1. Generate new key
2. Update Railway env var `LITELLM_MASTER_KEY`
3. Update Vercel env var `LITELLM_API_KEY` (same value)
4. Redeploy Railway service

---

## 4. Slack

### Channel Map

| Channel | Webhook env var | Source |
|---------|----------------|--------|
| `#financial-polar` | `SLACK_WEBHOOK_FINANCIAL` | Polar subscription events |
| `#affiliates-fp` | `SLACK_WEBHOOK_AFFILIATES` | FirstPromoter events |
| `#deploys-staging` | `SLACK_WEBHOOK_DEPLOYS_STAGING` | Vercel staging deploys |
| `#deploys-prod` | `SLACK_WEBHOOK_DEPLOYS_PROD` | Vercel prod deploys |
| `#digest-brevo` | `SLACK_WEBHOOK_DIGEST` | Daily email stats cron |
| `#infra-railway` | via Pipedream | Railway deploy/crash events |
| `#errors-sentry` | native integration | Sentry alerts |
| `#support-plain` | native integration | Plain ticket events |

### Pipedream Relay (Railway → Slack)

Railway's native Slack Muxer returns HTTP 400 (null-blocks bug). Events are relayed via Pipedream:

- Pipedream workflow URL: `<PIPEDREAM_WORKFLOW_URL>`
- Events: `DEPLOY_SUCCESS`, `DEPLOY_FAILED`, `CRASH_RESTART`, `OUT_OF_MEMORY`
- Rotation: delete workflow in Pipedream + recreate + update Railway webhook URL

---

## 5. Secrets Reference

| Secret | Where | Rotation |
|--------|-------|---------|
| `SUPABASE_SERVICE_ROLE_KEY` | Vercel + `.env.local` | On team change |
| `SUPABASE_JWT_SECRET` | Vercel + `.env.local` | On breach |
| `ENCRYPTION_KEY` | Vercel + `.env.local` | On breach |
| `LITELLM_MASTER_KEY` | Railway + Vercel (as `LITELLM_API_KEY`) | Annually |
| `BREVO_API_KEY` | Vercel (prod only) | Annually |
| `POLAR_ACCESS_TOKEN` | Vercel (per env) | Annually |
| `POLAR_WEBHOOK_SECRET` | Vercel (per env) | On breach |
| `SENTRY_DSN` | Vercel (prod only) | Never (DSN is public) |
| `SENTRY_AUTH_TOKEN` | GitHub secret | Annually |
| `PLAIN_API_KEY` | Vercel + `.env.local` | On team change |
| `FP_API_KEY` | Vercel (prod only) | Annually |
| Slack webhooks | Vercel | On channel deletion |
| `GITHUB_PAT` | `~/.zshrc` (agent-side) | Every 90 days |
| `SUPABASE_ACCESS_TOKEN` | `~/.zshrc` (agent-side) | Every 90 days |
