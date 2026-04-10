# TRON — Session Orchestrator

TRON is a session orchestration system for AI agent workflows. It coordinates parallel agent sessions — an Engineer working foreground while a Reviewer audits in background — eliminating the need for manual context handoffs and ensuring code review never drifts.

---

## How It Works

### Architecture

TRON is a **two-layer system**:

1. **`tron-seed.md`** (this repo) — a one-shot agent that plants a project-local TRON instance. Runs once per project, never again.
2. **`{project}/meta/agents/tron.md`** — the live, project-specific orchestrator that runs every session.

### Session Flow

```
User: "You are meta/agents/tron.md. Execute Session Start."
         │
         ▼
    TRON reads handover-engineer.md + pipeline.md
    Checks for open HIGH debt items
    Finds last code review timestamp
         │
         ▼
    Presents SESSION PLAN to user
    Waits for explicit confirmation
         │
         ├──────────────────────────────────┐
         ▼                                  ▼
  [FOREGROUND]                        [BACKGROUND]
  Spawn Engineer                      Spawn Reviewer
  "Execute Session Start"             "Execute Session Start"
         │                                  │
         ▼                                  ▼
  Engineer works,                    Reviewer audits all commits
  completes tasks,                   since last review log,
  returns ENGINEER RETURN            returns REVIEWER RETURN
         │                                  │
         └──────────────┬───────────────────┘
                        ▼
               TRON collects both returns
               Updates handover-engineer.md
               Appends reviewer findings if any
               Writes TRON session log
               Presents final summary to user
```

### Handover Files

| File                                    | Written by                      | Read by                                                                       |
| :-------------------------------------- | :------------------------------ | :---------------------------------------------------------------------------- |
| `meta/blocks/handover-engineer.md`      | Engineer (session end)          | Engineer (deletes at start), TRON (read-only), Architect/Analysts (read-only) |
| `meta/blocks/handover-reviewer-code.md` | TRON (before spawning reviewer) | Reviewer (read-only)                                                          |

**The engineer handover is the system's memory.** It carries task state, system health, blockers, and next steps between sessions. It is never overwritten by anyone except the Engineer.

### Agent Roles

| Agent    | Mode       | Blocks TRON?          | Returns         |
| :------- | :--------- | :-------------------- | :-------------- |
| Engineer | Foreground | Yes — TRON waits      | ENGINEER RETURN |
| Reviewer | Background | No — runs in parallel | REVIEWER RETURN |

TRON collects both returns, resolves findings, and updates state before closing the session.

### Reviewer Scope

The Reviewer's scope is always **git-based** — commits since the timestamp of the last review log file in `meta/logs/code-review/`. TRON extracts this automatically. The Reviewer never reads working tree files — committed state only.

---

## Files in This Directory

```
tron/
├── README.md               ← this file
├── tron-seed.md            ← one-shot seeder agent
├── templates/              ← project-local file templates (used by tron-seed)
│   ├── tron-local.md       ← project-local orchestrator template
│   ├── tron-state.md       ← TRON state template
│   ├── skill-tg-comms.md   ← agent communication skill template
│   └── handover-reviewer-code.md ← reviewer scope template
├── scripts/
│   └── tron-spawn.sh       ← agent spawn wrapper (macOS/iTerm + headless)
├── meta/
│   ├── blocks/             ← architecture & protocol docs
│   │   ├── adr-v02.md      ← ADR: TG message bus & active supervision
│   │   └── comms-protocol.md ← message format, heartbeat, validation specs
│   └── logs/               ← cross-project seed logs
│       └── log-YYMMDD-HHMM-seed-{project}.md
└── tron-avatar.jpg
```

Project-local TRON files (created by seeding):

```
{project}/meta/
├── agents/
│   └── tron.md                     ← live orchestrator for this project
├── blocks/
│   ├── handover-engineer.md        ← engineer inter-session state
│   └── handover-reviewer-code.md   ← reviewer scope (written by TRON each session)
└── logs/
    └── tron/
        └── log-YYMMDD-HHMM-{desc}.md
```

---

## How to Seed a New Project

Seeding plants a project-local `tron.md` tailored to that project's structure. It runs once. After seeding, you never invoke `tron-seed.md` again for that project.

### Prerequisites

Before seeding, the target project must have:

- `meta/agents/` — with at least `engineer.md` and `reviewer-code.md`
- `meta/blocks/` — for handover files (may contain `session-handover.md` to rename)
- `meta/logs/` — for log folders
- `meta/pipeline.md` — TRON reads this at every session start

### Step-by-Step

**1. Invoke TRON-SEED:**

```
You are tron/tron-seed.md.
The target project is {project-root}/.
Execute the Seeding Procedure.
```

**2. TRON-SEED will:**

- Scan the project structure
- Present a full plan (files to create, rename, update) — **nothing is written until you confirm**
- Run a reference sweep for any stale `session-handover.md` references
- Create `tron.md`, log folder, and both handover files
- Update all agent docs that reference the engineer handover
- Write a seed log to `tron/logs/`

**3. After seeding, run First Run:**

```
You are {project}/meta/agents/tron.md. Execute First Run.
```

TRON will read the agent docs, ask questions until it fully understands the project, then confirm readiness.

**4. From then on, every session:**

```
You are {project}/meta/agents/tron.md. Execute Session Start.
```

### What Gets Created

| Action | Path                                                       | Note                                               |
| :----- | :--------------------------------------------------------- | :------------------------------------------------- |
| CREATE | `meta/agents/tron.md`                                      | Project-local orchestrator                         |
| CREATE | `meta/logs/tron/`                                          | TRON session log folder                            |
| CREATE | `meta/logs/tron/bus.db`                                    | SQLite message bus (WAL mode)                      |
| CREATE | `meta/logs/tron/tron-state.md`                             | TRON persistent state                              |
| CREATE | `meta/blocks/handover-reviewer-code.md`                    | Reviewer scope file                                |
| CREATE | `meta/skills/skill-tg-comms.md`                            | Agent communication skill                          |
| CREATE | `meta/.env`                                                | TG credentials (gitignored)                        |
| RENAME | `meta/blocks/session-handover.md` → `handover-engineer.md` | If it exists                                       |
| UPDATE | `meta/agents/engineer.md`                                  | Handover path + Engineer Return format             |
| UPDATE | `meta/agents/reviewer-code.md`                             | Handover path + git scope + Reviewer Return format |
| UPDATE | `meta/agents/architect.md`                                 | Handover path (read-only reference)                |
| SWEEP  | All files referencing `session-handover.md`                | Zero remaining references guaranteed               |

---

## Expandability

To add a new agent to a running TRON instance:

1. Add it to the Agent Roster table in `tron.md`
2. Create a handover file in `meta/blocks/` if needed
3. Define its return message format in `tron.md` §Return Message Formats
4. Add a spawn step to `tron.md` §Execution Phase 1
5. Add a return-handling step to §Execution

No rearchitecting required. Practical ceiling: 3–4 parallel agents before coordination overhead outweighs benefit.

---

## Guardrails

- **TRON-SEED runs once per project.** If `tron.md` already exists, TRON-SEED stops and asks before doing anything.
- **Nothing is written without user confirmation.** TRON-SEED presents its full plan and waits for explicit approval.
- **The reference sweep is non-negotiable.** Every stale `session-handover.md` reference must be updated — no deferrals.
- **TRON does not orchestrate on First Run.** First Run is orientation only. Session Start is the first real orchestration.
- **Engineer handover is never overwritten by TRON, Architect, or Analysts.** Only the Engineer writes it. Everyone else reads.

---

## Known Limitations

- TRON cannot literally run two agents in parallel within a single AI context — "background" means the user spawns the Reviewer in a separate session/tab while the Engineer runs in the main one. TRON coordinates the handoffs, not the actual parallelism.
- First Run validation on a real project is a one-time opportunity. Once a project is seeded (by any means), that validation cannot be repeated.

---

## Telegram Notifications

TRON sends notifications to a dedicated Telegram channel at key workflow milestones, keeping you informed when away from the terminal.

**Two tiers:**

- 🔴 **Requires action** — always on, non-configurable: `BLOCKER`, `QUESTION`, `ERROR`, `STALL`, `UNRESPONSIVE`, `WATCHDOG_KILL`, `SESSION_ABORTED`
- ℹ️ **Informational** — configurable per project: `SESSION_START`, `SPAWNED`, `SV-PASS`, `SESSION_COMPLETE`, `PIPELINE_EXHAUSTED`

**Setup per project:**

1. Create a dedicated Telegram **group** for the project's TRON instance (groups only — channels are not supported)
2. Add the project's bot to that group
3. Create `{meta_path}/.env` (local only, gitignored):
   ```
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_TRON_CHAT_ID=...
   ```
4. Ensure `{meta_path}/.gitignore` includes `.env`

TRON-SEED will ask for these credentials during Step 2 and create the `.env` file as part of seeding. On First Run, TRON will ask which ℹ️ informational notifications to enable and record the active set in the local `tron.md`.

**No server required.** Notifications are sent via `curl` to the Telegram Bot API directly from local — no infrastructure dependency.

**If `.env` is missing or credentials are unset:** notifications are skipped silently. A warning is logged in the session log. The workflow is never blocked by a failed notification.

---

**Canonical source:** `tron/tron-seed.md`
**Last Updated:** 2026-04-10
