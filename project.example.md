# project.md — Example

This is a filled-in example. The seeder walks you through writing your own and saves it as `meta/agents/tron/project.md`. TRON reads this on every session start.

Keep it human. No YAML, no schema. Just facts about your project that TRON needs to know.

---

## Project

- **Name:** Example
- **Repo root:** `/Users/operator/projects/example`
- **Main branch:** `main`
- **Worktrees dir:** `.worktrees/` at repo root
- **Logs dir:** `meta/logs/` at repo root
- **GitHub org/repo:** `acme/example`

## Conventions

- **Branch naming:** `chore/<slug>-YYMMDD` for chores; `feat/<slug>-YYMMDD` for features; never `dev/*`.
- **Block IDs:** `block-MM-DD-<slug>` (e.g. `block-06-19-app-versioning`). Operator authors the block; TRON consumes it.
- **Worker IDs:** `<ROLE>-MM-DD` (e.g. `ENG-06-19`, `ARCH-06-19`, `REV-06-19`). One worker per role per block.
- **Commit convention:** present-tense, lower case, scope prefix (`fix:`, `feat:`, `chore:`).
- **PR title:** under 70 chars, body has Summary + Test plan.

## Env keys

Stored in `<repo-root>/.env` (gitignored). TRON reads via shell scripts, never inlines values into prompts.

- `TELEGRAM_BOT_TOKEN` — for operator escalation
- `TELEGRAM_CHAT_ID` — operator's chat
- `GITHUB_TOKEN` — for `gh` CLI (optional; `gh auth login` also works)

## Agents available

The project must have these canon-shaped agents already (Premise 17):

- `meta/agents/architect.md`
- `meta/agents/engineer.md`
- `meta/agents/reviewer.md`

TRON spawns instances from these. Do not invent new worker types here; if the project needs a new role, add a canon-shaped agent file first.

## Workflow doc

- Live workflow rules: `meta/agents/tron/workflow.md`
- Live counters/state: `meta/agents/tron/workflow-state.md`

## Notes

- This project ships to web + mobile; mobile builds require user verification (not automatable by engineers).
- CI uses GitHub Actions; expect ~6 min for full suite.
- Production deploys via Vercel on merge to `main`; preview URLs on every PR.
- T1/T5 tasks are operator-only (DNS, third-party dashboard config); engineers must not attempt these.

---

**Edit this freely.** TRON re-reads on every session start. To make TRON also adjust dependent docs, talk to TRON — don't hand-edit `workflow.md`, `workflow-state.md`, or `scripts.md` directly.
