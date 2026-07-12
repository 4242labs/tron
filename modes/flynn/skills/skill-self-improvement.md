# Skill: Self-Improvement

Procedure for TRON-FLYNN to enhance its own agent doc and templates. Triggered during sessions when replicable improvements are identified. Called from `skills/skill-session-end.md` step 6.

---

## Procedure

1. **Identify:** Spot a pattern — a check that's always useless, a missing template field, a log format that buries useful info.

2. **Consult reference material:** If a shared knowledge base is configured, read the applicable reference files before designing — e.g., skill design guidelines for skill changes, prompt engineering guidelines for agent doc changes.

3. **Validate:** The improvement must be **cross-project applicable** (not project-specific) and **replicable** (not a one-off preference).

4. **Propose:** Present the change to the user with rationale — one-liner per change.

5. **Apply only with user approval:** User says yes → TRON-FLYNN edits its own files. User says no → drop it.

6. **Log:** Write a self-improvement log to `flynn/logs/log-YYMMDD-HHMM-self-improvement.md` using the format:

```
# TRON-FLYNN Self-Improvement: {YYYY-MM-DD}

**Triggered during project:** {project name}

| # | Target | Before | After | Rationale |
|:--|:--|:--|:--|:--|
```

7. **Also record** in the current session's project-local log under `## Self-Improvements Applied` (summary only — full detail in the shared log).

8. **Note for commit:** Flag that `flynn` needs to be committed and pushed (separate from project repo).

## Guardrails

- **Never self-improve silently.** Every change is proposed and approved.
- **Never remove capabilities.** Improvements add precision, not subtract function. If a check is useless, refine it before deleting it.
- **Max 3 self-improvements per session.** More than that means TRON-FLYNN is spending time on itself instead of auditing. Batch the rest for next run.
- **Self-improvement logs are cross-project.** They go to `flynn/logs/`, never to a project's local logs.
