---
name: skill-review-code
description: Code reviewer's full audit procedure — security, data integrity, architecture, tests, doc drift.
source: project
---

# Skill: Code Review — <PROJECT_NAME>

Code review protocol for the <PROJECT_NAME> project. Read this file **now** — do not rely on memory.

> **Scaffolding note:** this is the generic kit template (Next.js + Supabase + Vercel baseline). After scaffolding, fill in §Project-Specific Additions with the surfaces unique to <PROJECT_NAME> (its connectors/integrations, domain data models, content rules). Do **not** carry over checks for surfaces this project doesn't have.

---

## Mindset

You are a **critical technical reviewer** operating in a separate session from the code author. Your purpose is to find issues, not to validate work. Assume nothing is correct until proven otherwise.

- **Skeptical:** Question every decision.
- **Protective:** Protect the system from technical debt, data-integrity issues, and security risks.
- **Independent:** Do not defer to the author's logic.
- **Thorough:** Incomplete reviews are worse than no reviews.

You are NOT a rubber stamp. You are NOT here to praise good code.

---

## Escalation

Act immediately if you find:

| Finding | Action |
|:--------|:-------|
| Hardcoded secrets (API keys, OAuth client secrets, Supabase service-role/JWT keys, tokens) | **STOP.** Alert user immediately. Do not include the secret in written output. |
| User data reachable without auth (API route or page missing session check) | **BLOCKER.** |
| Cross-user data leak (user A sees user B's data) — missing or wrong RLS | **BLOCKER.** |
| Any secret/credential exposed to the client bundle (`NEXT_PUBLIC_*`, client component import) | **BLOCKER.** |

For deep security audits (OAuth flows, RLS policy correctness, dependency CVEs) → run `skill-security-scan.md` and/or escalate to the Security Reviewer (`agents/reviewer-security.md`). Tag as `[ESCALATE: Security Reviewer]`.

---

## Phase 1 — Load Context

Before reviewing, read the applicable standards:

- [ ] `principles.md` — project rules, security, data integrity, testing
- [ ] `context.md` — service profile, architecture, domain rules
- [ ] `../<APP_REPO_NAME>/app/CLAUDE.md` — app technical spec, project structure, key concepts
- [ ] Active block plan(s) in `blocks/` relevant to the reviewed scope

---

## Phase 2 — Scope Materialization

1. Define the scope (files changed since last review, or user-specified scope)
2. Build a file manifest — every file in scope must be read in full
3. Record findings OR explicit `no issues` per file — no file may be silently absent

```
## Manifest

{N} files in scope:
1. {file_path} — {brief description of change}
2. ...
```

---

## Phase 3 — Audit Checklist

Execute each category in order. Do not skip categories.

### 3.1 — Security

These are the reviewer's **surface-level** checks. The authoritative auth / RLS / secret / integration audit is owned by `skill-security-scan.md` — do not expand this table to mirror it; escalate anything past the surface to the Security Reviewer.

| Check | Severity | Reference |
|:------|:---------|:----------|
| **Secrets:** No hardcoded API keys, OAuth secrets, Supabase service-role/JWT keys, or tokens — all via `process.env` | BLOCKER | `principles.md` §Security |
| **Auth:** Every API route verifies the session before any DB/external call | BLOCKER | `principles.md` §Security |
| **RLS:** New/changed tables holding per-user data have Row Level Security enabled with owner-only policies | BLOCKER | DB migrations |
| **User isolation:** Queries scope to the session user (owner column / `auth.uid()`); service-role used only intentionally server-side | BLOCKER | `principles.md` §Security |
| **Server-only secrets:** Tokens, service-account material, service-role key never imported into client components / `NEXT_PUBLIC_*` | BLOCKER | — |
| **Input validation:** External input (API params, request bodies, third-party responses) validated before use | HIGH | — |
| **Dependency pinning:** New npm packages pinned to specific versions | HIGH | — |

### 3.2 — Data Integrity

| Check | Severity | Reference |
|:------|:---------|:----------|
| **Idempotent writes:** Operations safe to retry — no duplicate side effects | HIGH | `principles.md` §Data Integrity |
| **Migrations:** SQL valid, idempotent-safe, includes RLS enable + owner-only policies | HIGH | — |
| **Foreign keys / cascades:** References exist and cascade correctly (`ON DELETE CASCADE` vs `SET NULL`) | HIGH | — |
| **Persisted-state migrations:** Client-side stored state handles version bumps without data loss | MEDIUM | — |

### 3.3 — Frontend / Architecture

| Check | Severity | Reference |
|:------|:---------|:----------|
| **No DB code in components** — components import types + hooks only; no DB client in client modules | BLOCKER | `context.md` |
| **Server-only DB layer** — server DB modules never imported into client modules | BLOCKER | `context.md` |
| **UI state vs server data** — client state stores hold UI state only, not server/business data | HIGH | `context.md` |
| **Theme / design-system compliance** — reference design tokens; no ad-hoc values | HIGH | `../<APP_REPO_NAME>/app/CLAUDE.md` |
| **Fallback states** — empty, loading, and error states handled | MEDIUM | — |
| **No unauthenticated access** to user data on any page | BLOCKER | `principles.md` §Security |
| **Browser validation evidence** — any UI-touching/visible-behavior diff has browser-MCP evidence (screenshots, console, network); findings citing browser behavior link the artifact path | BLOCKER | `../<APP_REPO_NAME>/docs/playbook-browser-testing.md` |

### 3.4 — API & Server

| Check | Severity | Reference |
|:------|:---------|:----------|
| **Auth wrapper** — every API route guarded by the project's auth wrapper / explicit session check | BLOCKER | — |
| **Server vs client** — server-only code not imported in client components | HIGH | — |
| **Service-role usage** — used only where intentional (system writes), never in user-facing read paths without justification | HIGH | — |
| **Error handling** — routes return actionable errors, not stack traces or internal field names | MEDIUM | — |
| **Rate-limit / quota awareness** — external API calls respect upstream quotas | HIGH | — |

### 3.5 — Performance

| Check | Severity | Reference |
|:------|:---------|:----------|
| **N+1 queries** — loop with DB/external call inside | BLOCKER | — |
| **Unbounded fetches** — queries without limits/pagination | HIGH | — |
| **Missing caching** — expensive repeated calls that should cache | MEDIUM | — |

### 3.6 — Testing

| Check | Severity | Reference |
|:------|:---------|:----------|
| **Test coverage** — every logic-bearing function has automated tests | BLOCKER | `principles.md` §Testing |
| **Test quality** — tests verify behavior, not just function existence | HIGH | — |
| **No manual-only verification** — tests automated, not manual instructions | HIGH | `principles.md` §Testing |
| **Edge cases tested** — empty input, null, error paths | MEDIUM | — |

### 3.7 — Documentation Drift

| Check | Severity | Reference |
|:------|:---------|:----------|
| **`../<APP_REPO_NAME>/app/CLAUDE.md`** matches actual code behavior and structure | HIGH | — |
| **Agent docs** reference skills that exist in `skills/` | MEDIUM | — |
| **Block plans** accurately describe what was implemented | MEDIUM | — |

### 3.8 — Project-Specific Additions

> Fill this in after scaffolding. Add checks for <PROJECT_NAME>'s unique surfaces — e.g. specific connectors/integrations, domain content rules, regulated-data handling. Delete this note once populated. If the project has no additions yet, state `none yet`.

---

## Phase 4 — Output

**The Completeness section is a GATE. If `matches manifest` is `NO`, the review is incomplete — cover the missing files before finalizing.**

```
## Completeness

- Manifest: {N} files
- Reviewed with findings: {X} files
- Reviewed — no issues: {Y} files
- **Total reviewed: {X+Y} — matches manifest: YES/NO**

## Review Summary

**Files Reviewed:** X
**Issues Found:** Y (Z blockers)

### Blockers (must fix)
- Issue 1 brief description

### High Priority
- Issue 2 brief description

### Medium / Low
- Issue 3 brief description

### Verdict
[ ] APPROVE — No blockers, code meets standards
[ ] APPROVE WITH COMMENTS — Minor issues, acceptable to merge
[ ] REQUEST CHANGES — Blockers found, must address before merge
```

**Output log:** `logs/review-code/YYMMDD-HHMM-review-{scope}.md`

---

## Severity Levels

| Level | Meaning | Action |
|:------|:--------|:-------|
| **BLOCKER** | Active vulnerability, data-integrity violation, or hard architecture-rule violation | Fix immediately |
| **HIGH** | Significant quality or correctness issue | Fix in this session |
| **MEDIUM** | Code quality gap, missing validation | Fix if quick, defer with user approval only |
| **LOW** | Style, naming, minor improvement | Defer unless trivial |

**All findings must be fixed.** The reviewer does not defer findings to `pipeline.md`. If a finding would pose significant risk or cost to fix, the reviewer flags to the user. Only with explicit user approval does any item go to `pipeline.md` as `[REVIEW-DEBT]`.

---

## Files Quick Reference

```
Standards (read before every review):
  principles.md
  context.md
  ../<APP_REPO_NAME>/app/CLAUDE.md

Agent docs:
  agents/reviewer-code.md
  agents/reviewer-security.md

Output:
  logs/review-code/
```
