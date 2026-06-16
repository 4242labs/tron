---
name: skill-validate
description: Project-local extension of canon validate; supplies concrete commands, evidence paths, and project-specific audits.
source: canon
canon_version: HEAD
---

# Skill: Validate (Project Extension)

Reads and enforces `{shared_knowledge_path}/skills/skill-validate.md` first. The sections below supply project-specific commands and audits. Where canon and project disagree, project-specific wins (per `principles-base.md` extension rule).

**Read this file at every invocation — do not rely on memory from session start.**

---

## When to Use

Per canon: stages 2 (local validation, pre-PR) and 5 (post-merge re-validation, on trunk) of the DoD flow (`principles-base.md §12`). Same skill, two checkpoints.

---

## 1. Build Hygiene — Concrete Commands

Project's static-analysis and test commands (replace placeholders during scaffold):

```bash
cd <APP_REPO_NAME>/app
<TYPECHECK_CMD>          # e.g. npx tsc --noEmit
<LINT_CMD>               # e.g. npm run lint
<TEST_CMD>               # e.g. npm test
<BUILD_CMD>              # e.g. npm run build
```

Add project-specific verifications below (e.g. migration apply, contract tests, schema validation). Examples:

- [ ] `<MIGRATION_CMD>` — when the block includes schema migrations
- [ ] `<CONTRACT_TEST_CMD>` — when inter-service messaging contracts changed

If any check fails → STOP. Fix it before continuing. No silent-PASS-with-caveats.

---

## 2. Browser MCP — Project Conventions

Per canon: mandatory for any UI / visible-behavior change. N/A only for purely invisible backend.

- **Devtools-class MCP:** `<PROJECT_DEFAULT>` (e.g. Chrome DevTools MCP)
- **Automation-class MCP:** `<PROJECT_DEFAULT>` (e.g. Playwright MCP)
- **Evidence directory:** `<PROJECT_ARTIFACT_DIR>` (e.g. `~/Downloads/` or `<APP_REPO_NAME>/test-results/`)
- **File-name convention:** `b{block-id}-{check}-{timestamp}.{png|json}`

Project-specific browser playbook (if one exists): `<APP_REPO_NAME>/docs/playbook-browser-testing.md`.

---

## 3. Project-Specific Audits

Project-localized audits run alongside the canonical AC verification. Each runs only when its trigger condition is met:

| Audit | Trigger | Skill / Procedure | Severity gate |
|:--|:--|:--|:--|
| `<security-scan>` | API routes / auth / secrets / RLS / external integrations changed | `skills/skill-security-scan.md` | CRITICAL or HIGH unresolved → STOP |
| `<deploy-validation>` | Deploy-tracked change | `<APP_REPO_NAME>/docs/playbook-infra.md` | Service down or change-specific check fails → STOP |
| `<schema-audit>` | Migrations added | `agents/data-architect.md` | Open RLS / missing policy → STOP |

Add project-specific rows here. Each audit's output feeds the Completion Report (canon §5) under `**Project audits:**`.

---

## 4. Completion Report — Where It Lives

The Completion Report **is** the session-end log — there is no separate completion-report file. It is the `## Completion Report` section of the engineer's session log (`logs/engineering/log-YYMMDD-HHMM-{block-id}-{slug}.md`, block-id included when applicable). Stage 2 writes that section; stage 5 appends a `## Completion Report (post-merge)` section to the same log.

Format and rules: canon §5. Do not deviate.

---

## 5. Post-Stage-2 Hand-off

After stage 2 validation completes clean:

- Produce **User Verification List** as a section at the bottom of the block doc:

```
## User Verification Required

1. {what to check} — {URL / page / location} — evidence: {path to screenshot / trace}
2. ...

No items require user verification: [ ] (check only if truly nothing needs visual/manual testing)
```

- Items that always need user verification:
  - UI changes — specific page URL (`localhost:<PORT>/...`)
  - Visual effects (animations, transitions, responsive behavior) — device/viewport to test
  - Email rendering — how to trigger and what to look for
  - OAuth / payment / external-integration flows — steps to test manually
  - Any user-facing behavior change — how to trigger and what to observe

Hand off to user. Do **not** open a PR until the user signs off (stage 3 of the DoD flow).

---

## 6. Post-Stage-5 Hand-off

After stage 5 validation completes clean on trunk:

- Engineer self-attests against the Completion Report (per canon §6)
- If the block declares a deploy check, confirm the change deployed clean and verify post-deploy — a merge that is not deploy-verified is **not done** and cannot proceed to status flip
- If clean (and deploy-verified where required), hand off to the user acknowledgment gate (`skill-session-end-engineer.md §1`)
- If a regression or a failed deploy is detected → do not flip status; open a new feature branch and re-enter the flow from stage 1

---

## Constraints

These bind every validate invocation (stages 2 and 5) and are the single project-level home for the two rules below — other docs reference this section rather than restating it. Canonical source: `{shared_knowledge_path}/principles-base.md §11` and `§13`.

- **No silent scope downgrade / legal moves.** "Cannot verify → I'll explain why and substitute alternative evidence" is forbidden. `UNVERIFIED` is a hard stop. When a contracted Verification method cannot run, the only legal moves are: (a) complete as specified, (b) negotiate the spec with the user, or (c) escalate and STOP. (`principles-base.md §11`)
- **No capitulation on a verified PASS.** If the user pushes back on a criterion that passed without producing new evidence, do not flip it or soften the report — re-state the evidence. Re-open a criterion only when the user supplies new evidence. (`principles-base.md §13`)

---

**Last Updated:** 2026-05-07 — initial extraction. Project extension of `{shared_knowledge_path}/skills/skill-validate.md`. §Constraints added 2026-06-16 (single-home legal-moves + anti-sycophancy).
