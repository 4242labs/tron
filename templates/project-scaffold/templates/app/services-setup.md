# Services Setup

Per-service setup for this project. Each section covers what the service does, exact setup steps, required env vars, and how to verify. Only sections for services confirmed in this project's profile are included.

---

## Railway / LiteLLM AI Proxy

**What:** Hosts LiteLLM as an AI proxy on Railway, providing per-user spend caps, a spend dashboard, and virtual model aliases so AI provider credentials are never exposed to the app.

**Steps:**

1. Create a Railway project → add a Postgres add-on (required for spend tracking)

2. Use the shipped `infra/Dockerfile.litellm`. The template is pinned and correct — do not modify the image tag without testing. Key properties:
   - Image: `docker.litellm.ai/berriai/litellm:main-v1.63.14-stable` (pinned — do NOT use `main-stable`)
   - Build context is the app repo root, so COPY paths use `infra/` prefix
   - Delegates to `litellm-entrypoint.sh` which drops the Prisma view before startup

3. Use the shipped `infra/litellm_config.yaml`. Fill `<MONTHLY_SPEND_CAP_USD>` with the monthly per-user spend cap (e.g. `5` for $5/user/month) and replace `<alias-N>` with your project's virtual model names. Key rules:
   - Use `max_user_budget` (per-user cap) + `user_budget_duration: monthly` — these are the correct LiteLLM field names
   - Do NOT add `tag_budget_config` — Enterprise-only, causes fatal startup crash
   - Example of correct structure:
   ```yaml
   general_settings:
     master_key: os.environ/LITELLM_MASTER_KEY
     database_url: os.environ/DATABASE_URL
     max_user_budget: 5
     user_budget_duration: monthly
   ```

4. Use the shipped `infra/litellm-entrypoint.sh` verbatim — do not re-author it. It drops the Postgres view (`LiteLLM_VerificationTokenView`) that otherwise blocks `prisma db push` on every cold start, then execs `litellm`. The Dockerfile already wires it as the entrypoint.

5. Deploy to Railway: set env vars in Railway project settings:
   - `LITELLM_MASTER_KEY` — generate a strong random key
   - `DATABASE_URL` — auto-set by Railway Postgres add-on (internal URL)
   - `ANTHROPIC_API_KEY` (or equivalent per model provider)
   - `LITELLM_UI_USERNAME` + `LITELLM_UI_PASSWORD` — for spend dashboard access

6. Set in Vercel (all scopes):
   - `LITELLM_API_KEY=<same as LITELLM_MASTER_KEY>`
   - `LITELLM_BASE_URL=<railway_service_url>`

**Env vars:**

| Var | Where | Notes |
|-----|-------|-------|
| `LITELLM_MASTER_KEY` | Railway | Master API key for the proxy |
| `LITELLM_BASE_URL` | Vercel (all scopes) | Railway public URL for the LiteLLM service |
| `LITELLM_API_KEY` | Vercel (all scopes) | Same value as master key — used by the app |
| `LITELLM_UI_USERNAME` | Railway | Spend dashboard login |
| `LITELLM_UI_PASSWORD` | Railway | Spend dashboard password |
| `DATABASE_URL` | Railway (internal) | Auto-set by Railway Postgres add-on |

**Verify:**
- `curl <railway_url>/health` → `{"status":"healthy"}`
- Make a test AI call through the proxy → confirm spend recorded in `<railway_url>/ui`

---

## Slack Notification Channels

**What:** Structured Slack channels for financial events, affiliate events, deploys, digests, infra, errors, and support.

**Channel map:**

| Channel | Source | Webhook env var |
|---------|--------|----------------|
| `#financial-polar` | Polar subscription events | `SLACK_WEBHOOK_FINANCIAL` |
| `#affiliates-fp` | FirstPromoter referral/commission events | `SLACK_WEBHOOK_AFFILIATES` |
| `#deploys-staging` | Vercel staging deploys | `SLACK_WEBHOOK_DEPLOYS_STAGING` |
| `#deploys-prod` | Vercel prod deploys | `SLACK_WEBHOOK_DEPLOYS_PROD` |
| `#digest-brevo` | Daily email stats cron | `SLACK_WEBHOOK_DIGEST` |
| `#infra-railway` | Railway deploy/crash events (via Pipedream) | `SLACK_WEBHOOK_INFRA` |
| `#errors-sentry` | Sentry alerts | Native Sentry integration — no webhook var |
| `#support-plain` | Plain ticket events | Native Plain integration — no webhook var |

**Steps:**

1. Create all channels in Slack workspace

2. For each channel that needs a webhook: Slack → channel → Settings → Integrations → Add a Webhook → copy URL → set env var in Vercel

3. Native integrations (no code required):
   - Wire Sentry → `#errors-sentry` via Sentry's Slack app
   - Wire Plain → `#support-plain` via Plain's Slack integration

4. **Railway → Slack via Pipedream** (required — Railway's native Slack Muxer returns HTTP 400 due to a confirmed null-blocks bug):
   - Create free Pipedream account
   - New workflow: HTTP trigger → Slack "Send a Message to a Channel" step targeting `#infra-railway`
   - In Railway: project settings → Webhooks → add webhook pointing to Pipedream HTTP trigger URL
   - Subscribe to events: `DEPLOY_SUCCESS`, `DEPLOY_FAILED`, `CRASH_RESTART`, `OUT_OF_MEMORY`
   - Document Pipedream workflow URL + rotation instructions in `docs/playbook-infra.md`

**Verify:** Trigger a Railway deploy → confirm message in `#infra-railway` within 30s; merge a staging PR → confirm Vercel deploy notification in `#deploys-staging`.

---

## Brevo Transactional Email

**What:** Transactional email API for batch notifications, release notes, and system emails. No-ops when `BREVO_API_KEY` is unset — staging/preview environments are safe by default.

**Steps:**

1. Create Brevo account → verify sender domain (DNS records: SPF, DKIM, DMARC)

2. Get API key: Brevo → SMTP & API → API Keys → Generate new key

3. Set in Vercel **production scope only**: `BREVO_API_KEY=<key>`
   - When unset (staging + preview), all send paths must no-op gracefully — guard in `lib/notifications.ts`

4. Set in Vercel (all scopes): `BREVO_SENDER_EMAIL` + `BREVO_SENDER_NAME`

5. Verify domain reputation: send a test email via Brevo dashboard → check spam score

**Env vars:**

| Var | Scope | Notes |
|-----|-------|-------|
| `BREVO_API_KEY` | Vercel production only | Empty = no-op |
| `BREVO_SENDER_EMAIL` | Vercel all scopes | Verified sender address |
| `BREVO_SENDER_NAME` | Vercel all scopes | Display name |

**Verify:** Temporarily set `BREVO_API_KEY` on staging → trigger a notification → confirm email arrives; check Brevo Logs → status `delivered`.

---

## Polar Payments

**What:** Subscription payments with sandbox (staging) and production (prod) separation.

**Steps:**

1. Create Polar organization

2. Create products + pricing tiers in Polar dashboard — sandbox first, then production

3. Set in Vercel:
   - Staging: `POLAR_SERVER=sandbox`, `POLAR_ACCESS_TOKEN=<sandbox_token>`
   - Production: `POLAR_SERVER=production`, `POLAR_ACCESS_TOKEN=<prod_token>`

4. Configure webhooks in Polar dashboard:
   - Staging: `https://staging.<domain>/api/webhooks/polar`
   - Production: `https://<domain>/api/webhooks/polar`
   - Events: `subscription.created`, `subscription.updated`, `subscription.canceled`, `subscription.revoked`
   - Copy webhook secret → set `POLAR_WEBHOOK_SECRET` in Vercel per environment

5. Implement webhook handler at `app/api/webhooks/polar/route.ts` — always verify signature before processing

**Env vars:**

| Var | Scope | Notes |
|-----|-------|-------|
| `POLAR_SERVER` | Vercel per env | `sandbox` (staging) / `production` (prod) |
| `POLAR_ACCESS_TOKEN` | Vercel per env | Different token per environment |
| `POLAR_WEBHOOK_SECRET` | Vercel per env | Different secret per environment |

**Verify:** Use Polar test credentials on staging → complete checkout → confirm `subscription.created` webhook fires → confirm user tier updates in DB.

---

## Sentry Error Monitoring

**What:** Runtime error capture and alerting. Disabled on non-production by leaving `SENTRY_DSN` unset in staging/preview.

**Steps:**

1. Create Sentry project (Next.js type)

2. Get DSN: Sentry → project settings → Client Keys → DSN

3. Set in Vercel **production scope only**: `SENTRY_DSN=<dsn>`

4. Install: `npm install @sentry/nextjs` from `app/`

5. Run Sentry wizard or manually create:
   - `sentry.client.config.ts`
   - `sentry.server.config.ts`
   - `sentry.edge.config.ts`

6. Wrap `next.config.ts` with `withSentryConfig()`

7. Add GitHub secret `SENTRY_AUTH_TOKEN` for source map uploads in CI:
   - Sentry → Settings → Auth Tokens → Create new internal integration token

8. Set `SENTRY_ORG` + `SENTRY_PROJECT` in Vercel (used by CI for source map uploads)

9. Wire Sentry → `#errors-sentry` Slack channel via Sentry's native Slack integration

**Env vars:**

| Var | Where | Notes |
|-----|-------|-------|
| `SENTRY_DSN` | Vercel production only | Unset = disabled |
| `SENTRY_AUTH_TOKEN` | GitHub secret | For source map uploads in CI |
| `SENTRY_ORG` | Vercel all scopes | Sentry org slug |
| `SENTRY_PROJECT` | Vercel all scopes | Sentry project slug |

**Verify:** Throw a test error in a server action on production → confirm it appears in Sentry within 30s.

---

## Matomo Analytics

**What:** Self-hosted privacy-first analytics. Disabled on non-production `VERCEL_ENV`.

**Steps:**

1. Deploy a Matomo instance on separate hosting (Railway, Coolify, or managed Matomo Cloud)

2. Create site in Matomo → note the Site ID

3. Set in Vercel (all scopes):
   - `NEXT_PUBLIC_MATOMO_URL=<matomo_url>`
   - `NEXT_PUBLIC_MATOMO_SITE_ID=<id>`

4. Add Matomo tracking script to root layout:
   ```tsx
   {process.env.VERCEL_ENV === 'production' && (
     <script
       dangerouslySetInnerHTML={{ __html: `
         var _paq = window._paq = window._paq || [];
         _paq.push(['trackPageView']);
         _paq.push(['enableLinkTracking']);
         (function() {
           var u="${process.env.NEXT_PUBLIC_MATOMO_URL}/";
           _paq.push(['setTrackerUrl', u+'matomo.php']);
           _paq.push(['setSiteId', '${process.env.NEXT_PUBLIC_MATOMO_SITE_ID}']);
           var d=document, g=d.createElement('script'), s=d.getElementsByTagName('script')[0];
           g.async=true; g.src=u+'matomo.js'; s.parentNode.insertBefore(g,s);
         })();
       `}}
     />
   )}
   ```

5. Create `lib/analytics.ts`:
   ```ts
   export function trackEvent(category: string, action: string, name?: string) {
     if (typeof window === 'undefined' || !window._paq) return;
     window._paq.push(['trackEvent', category, action, name]);
   }
   ```

6. Instrument key user actions: signup, subscription, key feature use

**Env vars:** `NEXT_PUBLIC_MATOMO_URL`, `NEXT_PUBLIC_MATOMO_SITE_ID`

**Verify:** On production, open Matomo real-time dashboard → perform a tracked action → confirm event appears within 10s.

---

## FirstPromoter Affiliate Tracking

**What:** Affiliate program with conversion tracking. Tracking script is self-hosted (not CDN) to avoid CSP issues and external dependencies.

**Steps:**

1. Create FirstPromoter account → set up program (commission type, rates)

2. Note Account ID from FirstPromoter dashboard

3. Set in Vercel:
   - All scopes: `NEXT_PUBLIC_FP_ACCOUNT_ID=<id>`
   - Production only: `FP_API_KEY=<key>`

4. Self-host tracking script: download `fpr.js` from FirstPromoter → place at `app/public/fpr.js`
   - **Do NOT load from CDN** — external script load is a performance and CSP risk

5. Add to root layout (before closing `</body>`):
   ```tsx
   <script dangerouslySetInnerHTML={{ __html: `
     (function(w){w.fpr=w.fpr||function(){w.fpr.q=w.fpr.q||[];w.fpr.q.push(arguments)}})(window);
     fpr("init", {cid:"${process.env.NEXT_PUBLIC_FP_ACCOUNT_ID}"});
     fpr("click");
   `}} />
   <script src="/fpr.js" defer />
   ```

6. Wire signup attribution: in auth callback, read `_fprom_ref` cookie → `POST https://firstpromoter.com/api/v1/track/signup` (fire-and-forget, never block signup on failure)

7. Wire sale attribution: in Polar `subscription.created` webhook handler → `POST https://firstpromoter.com/api/v1/track/sale` (fire-and-forget)

8. Validate env on boot: log warning if `NEXT_PUBLIC_FP_ACCOUNT_ID` is unset

**Env vars:**

| Var | Scope | Notes |
|-----|-------|-------|
| `NEXT_PUBLIC_FP_ACCOUNT_ID` | Vercel all scopes | Public — safe to expose |
| `FP_API_KEY` | Vercel production only | Used for server-side tracking calls |

**Verify:** Visit site with `?fpr=<test_ref>` → sign up → check FirstPromoter dashboard → conversion recorded.

---

## Pipedream (Railway → Slack Relay)

**What:** Relays Railway webhook events to Slack. Required because Railway's native Slack Muxer has a confirmed null-blocks bug that returns HTTP 400 from the Slack API.

**Steps:**

1. Create free Pipedream account at pipedream.com

2. New workflow → HTTP trigger → copy the trigger URL

3. Add step: "Send a Message to a Channel" → target `#infra-railway`:
   ```
   Channel: #infra-railway
   Message: {{ steps.trigger.event.body.type }} — {{ steps.trigger.event.body.projectName }}
   ```

4. Map Railway payload fields to a useful Slack message (event type, service name, deploy URL, timestamp)

5. In Railway: project settings → Webhooks → add webhook → URL = Pipedream trigger URL
   - Subscribe to: `DEPLOY_SUCCESS`, `DEPLOY_FAILED`, `CRASH_RESTART`, `OUT_OF_MEMORY`

6. Document in `docs/playbook-infra.md`:
   - Pipedream workflow URL
   - How to rotate (delete and recreate — update Railway webhook URL)
   - Which events are subscribed

**Env vars:** None in the app — Pipedream holds `SLACK_WEBHOOK_INFRA` internally in its environment.

**Verify:** Trigger a Railway deploy → confirm message in `#infra-railway` within 30s.
