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

## 1. Confirm the start point *(console)*
Default is the **whole pipeline**, from the first uncleared block. The operator may instead pick a
specific block, a subset, or a resume point. Confirm one, then proceed — TRON dispatches only what's
in scope.

## 2. Worker count *(console)*
Ask the **worker_count**: the size of the worker pool (engineers + reviewers share it). State the
detected default, take a number. The **architect is excluded** from this count — it is always one
dedicated, persistent agent on top of the pool (`architect_count`, default 1).

## 3. Spawn the architect *(engine)*
Spawn the persistent architect (out of the worker pool) and leave it idle, ready to drain its queue.

## 4. First dispatch *(engine)*
Emit `pulse`. PULSE runs SWITCHBOARD: with nothing cleared yet, CLEAR AHEAD enqueues the architect
to clear the pipeline forward; the first cleared block dispatches on the next pulse. The loop is live.

> Liveness, Telegram, and cron are config-driven (`project.yaml`) and start silently if enabled —
> bootup does not ask about them.
