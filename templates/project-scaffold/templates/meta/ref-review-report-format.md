# Ref: Review Report Format

Standard format for code & security review reports written to `logs/review-{code|security}/YYMMDD-HHMM-{scope}.md`. Fillable template — not a procedure.

For broader system / infrastructure audits, use `ref-audit-report-format.md` instead.

---

```
# {Code|Security} Review: {scope} — {YYYY-MM-DD}

**Reviewer:** {reviewer-code / reviewer-security}
**Executed by Model:** {model name}
**Scope:** {block id / files / commit range / branch}
**Baseline:** {commit SHA or branch the review targets}

---

## Executive Summary

{3–6 sentences. Overall posture, count of findings by severity, blocking vs non-blocking.}

## Findings

| ID | Severity | File | Finding | Status |
|:---|:---------|:-----|:--------|:-------|
| CR-H1 / SR-H1 | BLOCKER / HIGH / MEDIUM / LOW / INFO | `path/to/file.ext:line` | {one-line description} | open / fixed-in-session / deferred-with-approval |

### {ID}: {title} ({severity})

**File:** `path/to/file.ext:line`
**Observed:**
```{lang}
{minimal code excerpt showing the issue}
```
**Why it matters:** {concrete impact — security risk, correctness bug, performance, maintainability}
**Recommendation:** {specific fix — code-level when possible}
**References:** {prior CR/SR IDs, standards, related findings}

(Repeat per finding.)

## What was checked

- {bullet — coverage map of files/areas reviewed}

## What was NOT checked

- {bullet — explicit gaps so the next reviewer knows}

## Compliance

- **Core Docs staleness flagged:** {yes/no — list}
- **Block status impact:** {does this block the originating block? yes/no}
```
