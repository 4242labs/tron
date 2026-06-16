# Skill: Security Scan — <PROJECT_NAME>

**Read this file NOW — do not rely on memory from session start.**

Mandatory security gate for <PROJECT_NAME> (Next.js + Supabase + Vercel baseline). Run at two points:

1. **Validation (DoD stage 2 / 5)** — whenever a block adds/modifies API routes, auth/session logic, DB schema/RLS, or external integrations (called from `skill-validate.md §3 Project-Specific Audits`)
2. **Review cycle** — always, as part of the pre-archive pass

The block is NOT complete and the review cycle does NOT pass until this skill produces a clean report (no CRITICAL or HIGH findings unresolved).

> **Scaffolding note:** generic kit template. After scaffolding, populate §11 Project-Specific Surfaces with <PROJECT_NAME>'s integrations and domain data. Delete any check for a surface this project doesn't have.

---

## 1. Determine Scan Scope

Mark which layers this block touches:

| Layer | In scope? | Trigger |
|:------|:----------|:--------|
| API routes | YES / NO | New or modified route files |
| Auth / session handling | YES / NO | Session checks, auth wrapper, middleware |
| DB schema / RLS | YES / NO | New migrations, new tables, policy changes |
| External integrations | YES / NO | Third-party APIs / OAuth / service accounts |
| Frontend inputs | YES / NO | New user-facing forms, client→API calls |
| Dependencies | YES / NO | `package.json` / lockfile changed |

If no layer is in scope → skip this skill, note "security scan: not applicable" in the Completion Report.

---

## 2. API Route Auth Audit

**Every** route file added or modified must be checked. Verify:

- [ ] Route performs an explicit session check (or is wrapped by the project's auth wrapper) before any DB read/write or external call
- [ ] User-context DB access uses the user-scoped client — **not** the service-role client
- [ ] Missing session check before a DB/external operation → **CRITICAL** (unauthenticated access / IDOR)
- [ ] Service-role / admin client used only for intentional system writes server-side — any use in a user-facing read path → **HIGH**

---

## 3. Supabase RLS Audit

For each new migration in this block:

- [ ] New table holding per-user data has RLS enabled: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`
- [ ] Owner-only policies cover SELECT, INSERT, UPDATE, DELETE — no missing policy leaves an open surface
- [ ] Policy scopes rows to the session user (owner column tied to `auth.uid()` / `auth.users`) — not a spoofable column
- [ ] `service_role` bypass / grant is intentional and documented in a migration comment

Missing RLS on a user-data table → **CRITICAL**.

**Valid pattern:** deny-all RLS + access exclusively via `SECURITY DEFINER` RPC. Confirm intent is documented in the migration comment.

---

## 4. External-Integration Auth

For any third-party integration added/modified:

- [ ] OAuth tokens / API keys / service-account material stored server-side; never returned to the client or placed in `NEXT_PUBLIC_*`
- [ ] Per-user credentials scoped to the session user
- [ ] Outbound write-backs go through an authed route and are idempotent
- [ ] Third-party responses validated/escaped before render or DB write
- [ ] Webhook receivers verify the upstream signature/secret before processing

Credential reachable from the client bundle → **CRITICAL**. Missing per-user scoping or webhook signature → **HIGH**.

---

## 5. Secret & Env Var Check

```bash
grep -rn "SERVICE_ROLE_KEY\|JWT_SECRET\|CLIENT_SECRET\|_API_KEY\|_TOKEN" app/app app/lib --include="*.ts" | grep -v "process\.env"
```

- [ ] Zero hardcoded secrets in source
- [ ] All secrets accessed via `process.env.X` — never `const key = "..."`
- [ ] `.env.local` is gitignored — confirm not staged
- [ ] Startup env validation covers any new required env var (fails fast on missing critical vars)

Any hardcoded secret → **CRITICAL**.

---

## 6. PII & Logging Check

```bash
grep -rn "console\.log\|console\.error\|logger\." app/app/api app/lib --include="*.ts"
```

- [ ] No tokens, service-account material, or DB keys logged at any level
- [ ] No user content logged (whatever counts as user content for this project)
- [ ] User IDs may be logged for debugging, but not combined with secret/content fields in the same line
- [ ] Client-facing error messages don't expose internal field names or DB structure

Secret or user content in logs → **HIGH**.

---

## 7. Input Validation Check

For every new/modified API route that accepts a request body or query param:

- [ ] Body/params parsed and validated before use — type, required fields, length limits
- [ ] Unexpected fields ignored (no raw-body pass-through to DB or external API)
- [ ] Length-unbounded free-text capped before storage

Missing validation on user-supplied unbounded fields → **MEDIUM** (HIGH if it reaches an external API or the DB unbounded).

---

## 8. Security Headers Check

If the block adds routes or modifies `next.config.ts` / middleware:

- [ ] Security headers present and not regressed (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`)
- [ ] No auth-required route silently excluded from session enforcement

---

## 9. Dependency Audit

Run only if `package.json` / lockfile changed:

```bash
cd <PROJECT_NAME>-app/app
pnpm audit --audit-level=moderate
```

- [ ] Zero CRITICAL vulnerabilities
- [ ] HIGH vulnerabilities: document with a fix plan if no immediate patch
- [ ] Audit fix applied where safe (patch-only); breaking upgrades go to a dedicated block

---

## 10. Findings Report

Produce this table. Every finding gets a row — nothing omitted.

```
## Security Scan — {Block ID} — {YYYY-MM-DD}

| # | Severity | Category | File:Line | Finding | Resolution |
|:--|:---------|:---------|:----------|:--------|:-----------|
| 1 | CRITICAL | Auth | app/api/foo/route.ts:12 | Missing session check | Fixed: added auth |
| — | — | — | — | No findings | — |

**Risk score:** {CRITICAL×10 + HIGH×7 + MEDIUM×4 + LOW×1} / 100
**Verdict:** ✅ PASS  |  ❌ BLOCK
```

**Blocking rule:**
- Any unresolved CRITICAL → block completion blocked, review cycle blocked
- Any unresolved HIGH → block completion blocked unless user explicitly accepts risk in writing
- MEDIUM / LOW → document, fix in same block if trivial, otherwise open a tech-debt entry in `pipeline.md`

---

## 11. Project-Specific Surfaces

> Fill in after scaffolding: <PROJECT_NAME>'s integrations (which APIs/OAuth/service accounts), domain data sensitivity, any regulated-data obligations, and project-specific env vars. State `none yet` if unpopulated. Delete this note once populated.

---

## 12. Integration Points

**Called from `skill-validate.md §3`:** Runs as a project-specific audit; triggered when API routes, auth logic, DB schema, or external integrations are in scope. If not applicable, skip and note in the Completion Report.

**Called from `skill-review-cycle.md`:** Runs as §2 (before block-level validation). Scope = all blocks in the review cycle combined.

**Output goes into:**
- Completion Report (`## Completion Report` section in the engineer's session log) under `**Project audits:**`
- Review cycle log (`logs/architecture/log-YYMMDD-HHMM-cycle-review.md`)
