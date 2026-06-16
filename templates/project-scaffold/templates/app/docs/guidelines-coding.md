# Coding Guidelines — <PROJECT_NAME>

Durable code standards for **anyone** touching `<APP_REPO_NAME>/app/` — human or agent. These are standing rules, not bootup content; agent docs point here rather than restating them.

This doc holds the *standards*. The procedures that enforce them live elsewhere and are referenced inline:
- **Local verification / test gate** → `<META_REPO_NAME>/skills/skill-validate.md` (DoD stages 2 and 5)
- **Security scan gate** → `<META_REPO_NAME>/skills/skill-security-scan.md`

---

## Code Standards

- No hardcoded secrets — `.env` only; access via `process.env.X`, never a string literal.
- Validate at system boundaries (user input, external APIs); trust internal code.
- No comments explaining *what* code does — only *why* (a hidden constraint, a subtle invariant, a workaround).
- No half-finished implementations. If something can't be completed, escalate — don't leave it partial.
- No features, refactoring, or abstractions beyond what the task requires.

---

## Secure Coding

The standing secure-coding baseline. The active per-block audit that enforces it (with severity gates and a findings report) is `skill-security-scan.md` — this section is what that scan checks against.

- No SQL injection, XSS, command injection, or open redirects.
- Validate and sanitize all user input before it reaches the DB, an external API, or render.
- Never expose service-role / admin keys to the client; server-side only, never in `NEXT_PUBLIC_*`.

---

**Last Updated:** <SCAFFOLD_DATE> — durable standards single-homed here; agent docs reference this file.
