# Ref: Session Log Format

Standard format for session logs written to `logs/{role}/log-YYMMDD-HHMM-{description}.md`. Fillable template — not a procedure.

---

```
# {Title} — {YYYY-MM-DD HH:MM}

**Role:** {architect / engineer / reviewer-code / reviewer-security / analyst-* / advisor-* / localizer-* / flynn}
**Executed by Model:** {model name}
**Block / scope:** {block id or scope description}
**Duration:** {approximate}

---

## Summary

{2–4 sentences — what this session accomplished and why it matters.}

## Work done

- {bullet — concrete actions, outputs, file paths}

## Decisions

- {bullet — decisions made this session. Significant ones get full ADRs separately.}

## Files changed

- `path/to/file.ext` — {one-line reason}

## Next steps

- {bullet — what comes next, who should pick it up}

## Compliance

- **Tests:** {pass count or N/A}
- **Docs:** {Core Docs updated, or "none"}
- **Core Docs staleness check:** {summary — see the per-role session-end skill for the table}
```
