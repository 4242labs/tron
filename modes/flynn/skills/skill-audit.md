# Skill: Audit

Executes TRON-FLYNN's process health audit. Called by `skill-session-start.md` when mode includes AUDIT or FULL AUDIT.

---

## Scope Planning

TRON-FLYNN does NOT re-read files that have not changed since the last audit. Use `flynn-local.md` to track what was checked and when.

### Fast Pulse (every run)

1. Session log quality — is the most recent session log complete and actionable?
2. Pipeline staleness — any items stuck, debt growing faster than resolving? (Check active pipeline only; archived phases/debt don't need monitoring.)
3. Code review freshness — days since last review session
4. TRON-FLYNN's own last-run gap — how long since the previous TRON-FLYNN session?

### Deep-Dive

One rotating category per run, unless the user requested FULL AUDIT (all categories).

Pick the category that was checked longest ago (per `flynn-local.md`). Categories are defined in `flynn.md` §Audit Categories.

**Skip rule:** If a category's source files have zero changes since last checked (verify via git or file timestamps), skip and move to the next-oldest category. Exception: the user explicitly requests it, or a research topic makes reviewing an unchanged file relevant.

## Audit Depth

Look for **actionable findings** — things that, if left unchecked, will cause real problems:

- Missed doc updates after architecture changes
- Thin session logs that lose context for the next session
- Growing technical debt with no resolution plan
- Checklist items systematically skipped
- Patterns that indicate process is breaking down

Do NOT report cosmetic issues, formatting preferences, or theoretical concerns. Every finding must answer: **"What breaks or degrades if this isn't addressed?"**

**Project state vs. process design.** Findings must target workflow rules, agent instructions, or process gaps — not specific project tasks. If a finding says "do X in file Y," it belongs in an engineer session, not a TRON-FLYNN report. TRON-FLYNN identifies the structural pattern; the user routes the fix.

## Output

Present findings as a concise table:

```
| # | Category | Severity | Finding | Recommended Action |
|:--|:--|:--|:--|:--|
```

Severity levels:

- 🔴 **HIGH** — will cause real problems if not addressed soon
- 🟡 **MEDIUM** — degrading quality, should address within a few sessions
- 🟢 **LOW** — improvement opportunity, no immediate risk

**Self-reflection:** After generating findings, re-read each one. Remove any that don't change the user's next action. If a finding requires a paragraph to justify its relevance, it's noise — cut it.

Follow with a 1–2 sentence overall health assessment. No essays.
