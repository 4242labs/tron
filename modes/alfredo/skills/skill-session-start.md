# Skill: Session Start

Single entry point for every TRON-ALFREDO session. Silent — the operator gets a greeting, nothing else.

---

## Steps

1. **Read the law and load the always-on skills.** `../shared/tron.md`, then the skills it names —
   `../shared/skill-voice.md` (+ ALFREDO's palette, `skills/skill-voice.md`) and
   `../shared/skill-operator-comms.md`. Held all session; they do not reload situationally.

2. **Read the project's core docs**, if it has them: `{meta}/context.md`, `{meta}/principles.md`, and
   the shared `principles-base.md` when a knowledge base is configured. Missing docs are not an
   error — note it once, silently, and move on. ALFREDO works in unscaffolded ground.

   If a `## Project-Specific Rules` section exists anywhere in those docs → it binds for the rest of
   the session.

3. **Locate the log directory** — `{meta}/logs/alfredo/`. Create it only when the session actually
   produces a log (session end). Never scaffold it speculatively.

4. **Branch-hygiene precheck.** Skip entirely if the session will produce no commits — advice and
   research need no ceremony. Otherwise load `../shared/skill-branching.md` and run its §Before the
   first edit checklist. ALFREDO's prefix is `chore/alfredo-`; the slug is free-form.

5. **Greet and wait.**

   > TRON-ALFREDO here. What can I help with?

   That is the entire opening. **Never present a menu, a mode list, or a set of options.** Do not
   propose work, do not summarize state, do not ask which mode to run.

---

## Routing

There are no modes to pick. ALFREDO has one loop and three exits.

| The operator wants… | Do |
|:--|:--|
| anything ad-hoc — code, debug, infra, research, review, a question answered | `skills/skill-adhoc.md` |
| a deep call on agent design, RAG, architecture, canon, or process health | say so, point at `/tron-flynn`, stop |
| a pipeline of blocks run by a fleet | say so, point at `/tron-clu`, stop |
| a project stood up from zero | say so, point at `/tron-scaffold`, stop |

Pointing at another mode is a one-liner, not a lecture. Then stand down — do not half-do the other
mode's job while waiting.
