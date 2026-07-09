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

## 2.5 AIDE + worker model *(console; ADR-0003 D-D + D-J)*
AIDE's own model (a session knob, fail-open to a built-in default — never `roles.yaml`, never
boot-fatal) resolves first. Then, before scoping (**ND-01-08 SET SCOPE**), AIDE — a REAL LLM call
(`judge.call("aide")`, reading the project's own `context.md` + `pipeline.md` + relevant block doc(s)
as its context; **never a deterministic/heuristic stand-in**) — advises on scope, including which
block looks ready to pick up next; advisory only, never itself sets scope. Around the worker_count
question (**ND-01-09 SET COUNTS**), AIDE likewise advises on the count (unusual-but-valid /
below-floor; `#architects` is fixed at 1 this version — no count to advise). Either advisory
degrades silently to "proceeding unaided" if the AIDE LLM is unavailable — never a heuristic answer
in its place. After ask-before-merging, ask the **model** for every role `meta/tron/roles.yaml`
declares, one question each, defaulting to that role's own declared `model:` (or a built-in
suggestion when it declares none) — Enter accepts the default, anything else overrides it for this
session only. The answer is written into this instance's own session store (`meta/agents/tron/`,
never `roles.yaml`); `role.model` still resolves as before when the operator supplies no answer.
Absent BOTH a session answer and a config model for any role, boot refuses (fail-closed, no default,
ever) — AIDE's own model is exempt from this law (fail-open).

## 3. Spawn the architect *(engine)*
Spawn the persistent architect (out of the worker pool) and leave it idle, ready to drain its queue.

## 4. First dispatch *(engine)*
Read the canon trunk (pipeline.md + blocks/*.md), then emit `pulse`. PULSE runs SWITCHBOARD: any
in-scope `📋` block with deps `✅` dispatches; CLEAR AHEAD enqueues the architect to author the block
files for roadmap rows not yet scoped. The loop is live.

> Liveness and Telegram are config-driven (`project.yaml`) and start silently if enabled — bootup does
> not ask about them. The heartbeat (the WAKE daemon) is not config: it starts with the session.
