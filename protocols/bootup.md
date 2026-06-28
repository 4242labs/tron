---
name: bootup
kind: protocol
trigger: tron:start
---

# Bootup — the console-gated start

Runs once when the operator starts TRON (`tron start`). It settles the two things the engine can't
assume, spins up the standing architect, and hands control to the dispatch loop. After this, TRON
runs on its own until session-end.

The **interactive** steps (1–2) belong to the console; the **deterministic** steps (3–4) are the
engine (`engine.start`). They are one continuous flow.

## 1. Confirm the run scope *(console)*
The `session.scope` prompt offers three choices: **(1) all open phases and blocks · (2) a specific
phase · (3) a range of blocks**. The operator picks one; TRON dispatches only in-scope, still-open
blocks (`📋` with deps `✅`). Scope is never set by editing block status — `✅` always stays invisible
to dispatch.

## 2. Worker count *(console)*
Ask the **worker_count**: the size of the worker pool (engineers + reviewers share it). State the
detected default, take a number. The **architect is excluded** from this count — it is always one
dedicated, persistent agent on top of the pool (`architect_count`, default 1).

## 3. Spawn the architect *(engine)*
Spawn the persistent architect (out of the worker pool) and leave it idle, ready to drain its queue.

## 4. First dispatch *(engine)*
Read the canon trunk (pipeline.md + blocks/*.md), then emit `pulse`. PULSE runs SWITCHBOARD: any
in-scope `📋` block with deps `✅` dispatches; CLEAR AHEAD enqueues the architect to author the block
files for roadmap rows not yet scoped. The loop is live.

> Liveness and Telegram are config-driven (`project.yaml`) and start silently if enabled — bootup does
> not ask about them. The heartbeat (the WAKE daemon) is not config: it starts with the session.
