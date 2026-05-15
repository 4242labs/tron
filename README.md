# TRON

A canon-shaped supervisor agent for Claude Code's Agent View. One agent you talk to; it runs the rest.

---

## What this is

TRON is a thin, markdown-defined orchestrator. It spawns and supervises your fleet of worker agents — architects, engineers, reviewers — according to a workflow you author in plain markdown. You talk to TRON. TRON talks to everyone else.

It encapsulates the operator boilerplate ("no verbose," "follow your skill steps," "validate locally before reporting done," "execute session-end") into reusable scripts. You stop repeating yourself. Agents stay on rails.

## What this isn't

- A production runtime — use [LangGraph](https://langchain-ai.github.io/langgraph/) for unattended loops.
- A customer-facing surface.
- A multi-machine fleet manager.
- A SaaS — TRON is yours; it runs in your terminal.

---

## Requirements

- Claude Code CLI **>= 2.1.139** (Agent View support).
- `gh`, `curl`, `jq` on PATH.
- A `crontab` (macOS / Linux).
- A target project that already has canon-shaped `meta/agents/architect.md`, `engineer.md`, `reviewer.md`.

---

## Quickstart

```bash
# 1. Clone canon
git clone https://github.com/42piratas/tron.git ~/code/tron-canon

# 2. From your target project, open an interactive Claude Code session pointed at the seeder
cd ~/code/my-project
claude "Read ~/code/tron-canon/tron-seed.md and seed TRON into this project."
```

The seeder walks you through:
1. Project profile (paths, conventions, env keys).
2. Workflow rules (5 defaults; edit freely).
3. Templates, skills, scripts copied into `meta/agents/tron/`.
4. `.env` keys for Telegram.
5. Cron entries for the autonomous sweep + TG poll.
6. Dry-run validate + doctor.

Once seeded:

```bash
claude --bg -n TRON "Begin session."
```

TRON appears in Agent View. Talk to it.

---

## File layout — canon

```
tron/
├── README.md
├── tron-seed.md                # the seeder doc
├── tron-scripts.md             # situation→script index (operator-extensible)
├── workflow.example.md         # default workflow rules
├── project.example.md          # default project profile shape
├── templates/                  # tron.md, state.md, workflow-state.md, handovers
├── skills/                     # 9 markdown skills
├── scripts/                    # 4 shell helpers
└── LICENSE
```

## File layout — consumer project (after seed)

```
<project>/meta/agents/
├── tron.md                     # live TRON agent file
└── tron/
    ├── project.md              # this project's profile
    ├── workflow.md             # this project's workflow rules
    ├── workflow-state.md       # live counters (TRON-managed)
    ├── scripts.md              # this project's situation→script index
    ├── state.md                # persistent memory (counters, subs)
    ├── current-id              # TRON's live session ID
    ├── dispatched.log          # spawn history (append-only)
    ├── seed-trace.md           # audit of seed
    ├── tg-inbox.jsonl          # inbound TG messages
    ├── skills/                 # copied from canon
    ├── templates/              # copied from canon
    ├── scripts/                # copied from canon
    └── logs/                   # session logs
```

Plus, outside `meta/agents/tron/`:
- `<project>/.env` — Telegram keys.
- `<project>/meta/agents/architect.md`, `engineer.md`, `reviewer.md` — canon prereq.

To remove TRON entirely: delete `meta/agents/tron.md` and `meta/agents/tron/`. No other project traces.

---

## Design premises

The architecture is grounded in 23 locked premises (see `marketing-source-tron.md` in the related plan repo for the full list). A few highlights:

- **Canon purity.** The canon repo has zero project-specific or machine-specific traces.
- **Local encapsulation.** Two paths (`meta/agents/tron.md` + `meta/agents/tron/`) are the entire local surface.
- **Agent View native.** No custom bus, no daemon, no sidecar — everything rides on `claude --bg` / `claude --resume`.
- **Workers never self-terminate.** Only TRON kills (closes the bus-dead-post-DONE failure mode).
- **TRON owns its own edits.** Operator describes a change in natural language; TRON updates all docs atomically. No hand-editing of `workflow-state.md` / `scripts.md`.
- **External cron drives autonomy.** TRON is a turn-based agent; cron-driven sweeps + decoupled TG poller close the autonomous-loop gap.

---

## License

See `LICENSE`.

---

## Contributing

This canon repo is the single source of truth. Per-project customization happens in consumer projects, never here.

PRs that:
- Touch project-specific assumptions → rejected.
- Add machine-specific paths → rejected.
- Add new skills, refine handovers, improve scripts → welcome.

Open an issue first for non-trivial changes.
