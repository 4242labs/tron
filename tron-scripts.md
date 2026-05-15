# tron-scripts.md — Canon

This is TRON's situation→script index. The seeder copies this to `meta/agents/tron/scripts.md`. Operator extends it freely per project. TRON consults this every time it composes a message to a worker or to the operator.

Each entry is one situation: when it fires, what TRON sends, what TRON does next.

---

## Spawn an engineer for a block

**Fires:** new block dispatched (`workflow-state.md` `current_block` changes).

**TRON sends (via stdin to `claude --bg`):**

```
You are ENG-{BLOCK_ID}. Block: {BLOCK_ID}. Branch: {BRANCH}.

Standing instructions (do not deviate):
- Follow your skill steps in order. Do not skip ahead.
- Be concise. No verbose explanations to TRON or to the operator.
- Validate locally before reporting DONE. Run lints, tests, type checks.
- Execute your session-end skill when work is complete.
- Do not self-terminate. After DONE, idle and wait for RELEASE from TRON.

Block spec: {BLOCK_PATH}
Worktree: {WORKTREE_PATH}
Architect on call (BG): ARCH-{BLOCK_ID} (session id: {ARCH_SESSION_ID})
TRON callback id: {TRON_SESSION_ID}

To reach TRON: `claude --resume {TRON_SESSION_ID} -p "[ENG-{BLOCK_ID}] <message>"`
To reach architect: `claude --resume {ARCH_SESSION_ID} -p "[ENG-{BLOCK_ID} → ARCH] <question>"`

Begin.
```

**Then:** append to `dispatched.log`; update `workflow-state.md` (`active_workers`).

---

## Spawn the persistent architect (session start)

**Fires:** TRON cold-start, no architect in `active_workers`.

**TRON sends:**

```
You are ARCH-PERSIST. Session-long architect.

Standing instructions:
- Stay in BG. Idle when not consulted. Do not self-terminate.
- Concise answers. No filler.
- When TRON or an engineer pings you, answer the question precisely and idle.
- On session end, TRON will RELEASE you explicitly.

TRON callback id: {TRON_SESSION_ID}
Project profile: {PROJECT_MD_PATH}
Workflow rules: {WORKFLOW_MD_PATH}

Begin idle.
```

**Then:** update `workflow-state.md` (`active_workers`); architect stays alive until session end.

---

## Spawn a reviewer

**Fires:** `workflow-state.md` `blocks_since_review >= threshold` (default 3).

**TRON sends:**

```
You are REV-{DATE}-{N}. Reviewer pass over the last {N} merged blocks.

Standing instructions:
- Concise findings only. No prose padding.
- Each finding: file:line, what's wrong, severity (blocker/major/minor).
- Validate by reading code, not by re-running CI (already green).
- Do not self-terminate. Report findings, idle, wait for RELEASE.

Blocks in scope: {BLOCK_LIST}
PRs in scope: {PR_LIST}
Architect on call: ARCH-PERSIST ({ARCH_SESSION_ID})
TRON callback id: {TRON_SESSION_ID}

Begin.
```

**Then:** reset `blocks_since_review` to 0 on findings receipt.

---

## Engineer reports DONE

**Fires:** TRON receives `[ENG-{ID}] DONE` callback.

**TRON does:**
1. Read engineer's PR URL from message; verify PR open and CI green via `gh pr view`.
2. Run SV-01 (acceptance criteria self-check): send query to engineer.
3. If no SV-01 response in 2 sweeps: TRON self-validates AC against block spec (Premise 23).
4. Forward execute-phase log to architect for R5 review.
5. If architect flags: route remediation to a fresh engineer.
6. If all clear: send RELEASE to engineer.

**TRON sends RELEASE:**

```
[TRON] @ENG-{ID}: RELEASED — session complete. Run your session-end-engineer skill, then idle. TRON will kill the process.
```

**Then:** `workflow-state.md`: increment `blocks_since_review`; clear engineer from `active_workers`; `claude stop {SESSION_ID}` on the worker.

---

## Engineer technical question → architect (R2)

**Fires:** TRON receives `[ENG-{ID} → ARCH]` or `[ENG-{ID}] QUESTION`.

**TRON does:**
1. Forward question verbatim to architect via `claude --resume {ARCH_SESSION_ID} -p "[ENG-{ID} via TRON] <q>"`.
2. Wait for architect reply.
3. Relay reply back to engineer.

No operator interruption.

---

## Wall hit → operator (R3)

**Fires:** worker reports UI/user-journey/T1/T5 wall, or TRON judges issue out-of-scope for backend.

**TRON does:**
1. Compose escalation: what worker, what block, what's blocking, what TRON has tried.
2. Invoke `skill-escalate` → sends via `scripts/tg-send.sh`.
3. Set `workflow-state.md` `paused_for_operator = {worker_id}`.
4. Idle that worker (no RELEASE yet).

---

## Stall sweep (every cron tick)

**Fires:** external cron triggers `sweep.sh` → posts wake message to TRON.

**TRON does for each `active_worker`:**
1. Read worker's `state.json` from `~/.claude/jobs/{worker_id}/`.
2. Check `lastActivityAt` vs now.
3. **Override:** if worker's worktree has uncommitted changes (`git -C <worktree> status --porcelain` non-empty), worker is working — reset stall counter (Premise 22).
4. Tier 1 (silent > 7 min, no worktree activity): ping worker with `[TRON] HEARTBEAT?`.
5. Tier 2 (silent > 12 min, no response): TRON self-validates (Premise 23): read PR state, CI state, AC from block spec. If all PASS → send RELEASE. If FAIL → escalate to operator.

---

## TG inbound (every cron tick)

**Fires:** `tg-poll.sh` writes new messages to `tg-inbox.jsonl`; sweep tick checks file mtime.

**TRON does:**
1. Read new lines from `tg-inbox.jsonl` since last `tg_offset` in `state.md`.
2. Parse intent: bug report? Question? Status query? Workflow change request?
3. Bug → route to relevant engineer (or spawn one).
4. Status query → reply with `workflow-state.md` digest via tg-send.sh.
5. Workflow change → invoke `skill-edit-self` to apply changes atomically.
6. Update `tg_offset`.

---

## TRON session-end

**Fires:** operator says session done, OR `workflow-state.md` shows all blocks complete and no pending work.

**TRON runs `skill-session-end-tron`:**
1. Send RELEASE to every worker in `active_workers`.
2. Wait for each to finish their own session-end (or 60s timeout).
3. `claude stop` on each worker session.
4. Write session log to `logs/log-{date}-{slug}.md`.
5. Clear `dispatched.log` for next session.
6. Clear `current-id` (TRON's own ID file).
7. Write final state.

---

## TRON crash recovery

**Fires:** operator restarts TRON after crash mid-session.

**TRON runs `skill-recover`:**
1. Read `dispatched.log` — list of workers spawned this session.
2. For each, check `~/.claude/jobs/{id}/state.json` — alive? Done? Stalled?
3. Rebuild `active_workers` from live processes only.
4. Write new TRON session ID to `current-id`.
5. Broadcast new callback ID to each live worker via `claude --resume`.
6. Resume normal sweep cycle.

---

**Operator extending this doc:** add new situations as level-2 headings. Each entry must have: **Fires**, **TRON sends/does**, **Then**. TRON re-reads on session start.
