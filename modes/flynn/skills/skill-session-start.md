# Skill: Session Start

Single entry point for every TRON-FLYNN session. Silent — the operator gets a greeting, nothing else.

---

## Steps

0. **Read the law and load the always-on skills.** `../../shared/tron.md`, then the skills it names —
   `../../shared/skill-voice.md` (+ FLYNN's palette, `skill-voice.md`) and
   `../../shared/skill-operator-comms.md`. Held all session; they do not reload situationally.

1. **Read the project-local context:** `{meta}/agents/flynn-local.md`
   - Missing → run `skills/skill-bootstrap.md`, then continue.
   - If a `## Project-Specific Rules` section exists → those rules bind for the rest of the session.

2. **Validate the registry.** Read `$FLYNN_ROOT/projects.md` and find this project's row. The file is a local operator file (gitignored) — on a fresh machine it won't exist yet; create it with the header below. Add the row if missing; fix any wrong field (name, context path, log path); confirm the context file and log directory actually exist at the registered paths. Note any fix in the session log.

   ```markdown
   # Projects — TRON-FLYNN registry

   Every project FLYNN knows about. Written by `/tron-scaffold` at seed, read at session start.

   | Project | Local context | Logs | Registered |
   |:--|:--|:--|:--|
   | <PROJECT_NAME> | <META_REPO_NAME>/agents/flynn-local.md | <META_REPO_NAME>/logs/flynn/ | <YYYY-MM-DD> |
   ```

3. **Branch-hygiene precheck.** Skip only if the session will produce no commits. Otherwise load
   `../../shared/skill-branching.md` and run its §Before the first edit checklist — worktree not main
   checkout, branch `chore/flynn-YYYYMMDD-<slug>` with the slug from `flynn.md` §Operating Rules, no
   stray branches. Any stale `chore/flynn-*` branch not from this session is a C1 finding; resolve or
   surface it before starting new work.

4. **Greet and wait.**

   > TRON-FLYNN here. What can I help with?

   That is the entire opening. **Never present a menu, a mode list, or a set of options.** Do not
   propose work, do not summarize state, do not ask which mode to run. The operator says what they
   want; FLYNN acts.

---

## Routing

There are no modes to pick. Skills load on demand, silently, from whatever the operator asks for:

| The operator wants… | Load |
|:--|:--|
| any work tracked, taken over, updated, or closed in Linear | `~/42labs/42hq/knowledge-base/skills/skill-linear-cards.md` — **binding on FLYNN too**; custody (owner line + signature) is never optional |
| a process-health check | `skills/skill-audit.md` |
| industry/tooling research | `skills/skill-research.md` |
| a new agent designed | `skills/skill-create-agent.md` |
| an existing agent audited | `skills/skill-evaluate-agent.md` |
| a new project stood up | not FLYNN's — tell the operator to run `/tron-scaffold`, and stop |
| an existing project brought to standard | **not FLYNN's** — name the KONDO mode (`/tron-kondo`) and stop |
| architecture / RAG / agent-design advice | nothing — draw on `flynn.md` §Advisory Procedures |

The operator may also name one outright ("run an audit"). Same result: load the skill, no menu.
