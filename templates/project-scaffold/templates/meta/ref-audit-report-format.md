# Ref: Audit Report Format

Standard format for audit reports (broad system audits, cycle reviews, infrastructure audits). Fillable template — not a procedure.

For code-specific or security-specific reviews, use `ref-review-report-format.md` instead.

---

```
# Audit: {scope} — {YYYY-MM-DD}

**Auditor:** {role}
**Executed by Model:** {model name}
**Scope:** {what was audited — repos, files, systems}
**Method:** {how — read-through, automated checks, live probes}

---

## Executive Summary

{3–6 sentences. What was audited, what was found, what needs to happen.}

## Findings

| ID | Severity | Area | Finding | Recommendation |
|:---|:---------|:-----|:--------|:---------------|
| F-1 | HIGH / MEDIUM / LOW / INFO | {area} | {one-line description} | {one-line recommendation} |

### F-1: {title} ({severity})

**Location:** `path/to/file.ext:line`
**Observed:** {what is true today}
**Risk / Impact:** {what happens if unfixed}
**Recommendation:** {specific action}
**References:** {links to related docs / prior findings / standards}

(Repeat per finding.)

## Out of Scope

- {bullet — what was not audited and why}

## Compliance

- **Core Docs staleness flagged:** {yes/no — list affected docs}
- **Follow-up block proposed:** {block id or "none"}
```
