# TRON — Stop coordinating agents. Start shipping.

*Built for developers who want AI agents that work like a team, not a prompt.*

**Structured, repeatable multi-agent workflows for Claude Code.**

TRON coordinates parallel AI agent sessions so you don't have to. While your Engineer builds, a Reviewer audits in the background. Context carries forward automatically. Code review never drifts. You stay in control.

*Used daily across multiple active codebases.*

---

## The Problem

Running multiple AI agents on a real project is messy. Context gets lost between sessions. Code review is skipped or forgotten. Agents go off-script. You end up doing coordination work instead of actual work.

A stalled session means reorienting from scratch. A skipped review means a bug that ships. Manual status updates between sessions eat 20 minutes before a line of code gets written.

TRON fixes this.

---

## What TRON Does

- **Orchestrates parallel sessions** — Engineer foreground, Reviewer background, both running simultaneously
- **Carries context forward** — a structured handover file replaces manual status updates between sessions
- **Enforces code review** — every session end triggers an automatic review scoped to what actually changed; findings feed directly into the next session
- **Validates before closing** — TRON doesn't accept "done" at face value; it runs a structured verification loop before signing off
- **Keeps you informed remotely** — Telegram notifications at key milestones; reply from your phone to unblock a stalled agent
- **Never acts without confirmation** — every session starts with a plan you approve before anything runs

---

## How It Works

Here's a full session in 30 seconds:

```
You say: "Execute Session Start"
              │
              ▼
     TRON reads project state
     presents SESSION PLAN
     waits for your go-ahead
              │
        ┌─────┴──────┐
        ▼            ▼
   Engineer      Reviewer
   [foreground]  [background]
   builds        audits commits
        │            │
        └─────┬──────┘
              ▼
     TRON collects returns
     resolves findings
     updates handover
     closes session
```

One command to start. TRON handles the rest.

---

## Key Features

**Persistent context** — the handover file is the system's memory. Task state, blockers, and next steps carry forward across every session without you lifting a finger.

**Automatic reviews** — the Reviewer runs every session, covering only what changed since the last review. Nothing slips through; nothing gets reviewed twice.

**Active supervision** — TRON monitors agent activity, detects stalls, and escalates to you if something goes dark. Sessions don't hang silently.

**Concurrent-safe communication** — agents coordinate through a dedicated message bus. No collisions, no lost messages, no coordination overhead on your end.

**Project-local instances** — each project gets its own TRON tailored to its structure. Seed once, run forever. One seeder, many projects, zero coupling.

**No infrastructure** — runs entirely from your local machine. No servers, no cloud dependencies, no paid services beyond Claude and Telegram.

---

## Quick Start

**1. Seed your project** (one-time):

```
You are tron/tron-seed.md.
The target project is {project-root}/.
Execute the Seeding Procedure.
```

**2. Run First Run** (orientation only):

```
You are {project}/meta/agents/tron.md. Execute First Run.
```

**3. Every session from then on:**

```
You are {project}/meta/agents/tron.md. Execute Session Start.
```

That's it.

---

## Requirements

- macOS (interactive spawn) or any Unix (headless)
- [iTerm2](https://iterm2.com) — for interactive agent windows
- [Claude Code CLI](https://claude.ai/code) — installed and authenticated
- `sqlite3`, `python3`, `curl` — pre-installed on macOS

---

## Technical Reference

Architecture, session flow, message bus, supervisor validation protocol, seeding reference, and Telegram setup → **[ARCHITECTURE.md](ARCHITECTURE.md)**

---

## License

[Creative Commons Attribution-NonCommercial 4.0](LICENSE) — free to use, not for commercial purposes.

---
