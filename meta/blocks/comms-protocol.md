# TRON Comms Protocol Spec v0.2

Message format, tagging, heartbeat, stall detection, and validation loop specifications for TRON's TG message bus architecture.

**Status:** Draft
**Date:** 2026-03-13
**Parent:** `tron/meta/blocks/adr-v02.md`

---

## 1. Transport Layer

The protocol is transport-agnostic. Messages follow the same format regardless of transport.

### 1.1 TG Transport (Primary)

**Send:**
```bash
tron_send() {
  local msg="[${TRON_AGENT_ID}] $1"
  eval "$(cat ${TRON_META_PATH}/.env)" && curl -s -X POST \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_TRON_CHAT_ID}" \
    -d parse_mode="Markdown" \
    -d text="${msg}" > /dev/null
}
```

**Poll:**
```bash
tron_poll() {
  eval "$(cat ${TRON_META_PATH}/.env)" && curl -s \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?offset=${TRON_POLL_OFFSET}&timeout=5" \
    | jq -r '.result[] | select(.message.text) | .message'
}
```

**Offset tracking:** After each poll, update `TRON_POLL_OFFSET` to `last_update_id + 1`. Store in environment variable (per process) — not persisted to disk.

**TG message length limit:** 4096 chars. Messages exceeding this must be split. The sender appends `(1/N)`, `(2/N)` to each chunk. The receiver reassembles by matching sender tag + chunk markers.

### 1.2 CLI-Only Fallback

When TG is unavailable, the SQLite bus still operates identically — agents write and poll as normal. The only difference is TRON does not forward messages to TG. The user must read the terminal or query `bus.db` directly.

CLI-only mode is degraded: no remote access, no user interaction via phone. Terminal-only.

---

## 2. Message Format

Every message follows this structure:

```
[{AGENT_ID}] {EMOJI} {MESSAGE_TYPE}: {content}
```

### 2.1 Agent IDs

Format: `[{ROLE}-{N}]` where N is the instance number.

| Role | ID Pattern | Examples |
|:--|:--|:--|
| TRON | `[TRON]` | Always single instance |
| Engineer | `[ENG-{N}]` | `[ENG-1]`, `[ENG-2]` |
| Reviewer | `[REV-{N}]` | `[REV-1]` (usually single) |
| Architect | `[ARCH-{N}]` | `[ARCH-1]` |
| Other roles | `[{ABBREV}-{N}]` | TRON assigns abbreviation at spawn |
| User | (untagged) | Messages without a tag are from the user |

**Assignment:** TRON assigns agent IDs at spawn time. The ID is set as `TRON_AGENT_ID` environment variable and injected into the spawn prompt.

### 2.2 Message Types

#### Status Messages (agent → TG)

```
[ENG-1] ✅ MILESTONE: PR merged for my-service (#45)
[ENG-1] ⏳ HEARTBEAT: Still working on T15 deploy validation
[ENG-1] 🚀 STARTED: Beginning block-04-02-auth-middleware
[ENG-1] 🏁 DONE: All tasks complete, ready for verification
[ENG-1] ⚠️ BLOCKER: CI failing on my-common — needs investigation
[ENG-1] ❓ QUESTION: Should I use OAuth or direct auth for this endpoint?
```

| Emoji | Type | When |
|:--|:--|:--|
| 🚀 | `STARTED` | Agent begins a block or major phase |
| ✅ | `MILESTONE` | Discrete achievement (PR merged, deploy complete, test passing) |
| ⏳ | `HEARTBEAT` | No milestone in 5min — still alive and working |
| 🏁 | `DONE` | Agent reports block/task complete (triggers SV-01) |
| ⚠️ | `BLOCKER` | Agent is stuck, needs help |
| ❓ | `QUESTION` | Agent needs a decision from user |
| 🚨 | `ERROR` | Something broke |

#### TRON Messages (TRON → TG)

```
[TRON] 🤖 SESSION: Starting — reading pipeline and handovers
[TRON] ⚙️ SPAWNED: ENG-1 for block-04-02 (Sonnet)
[TRON] 🔍 VALIDATING: ENG-1 reported done — running SV-01
[TRON] 🔄 SV-FAIL: ENG-1 has incomplete tasks — sent back
[TRON] ✅ SV-PASS: ENG-1 validated — presenting to user for approval
[TRON] 🚨 STALL: ENG-1 has not reported in 7min — possibly stalled
[TRON] 📋 PIPELINE: Exhausted — no more blocks in roadmap
[TRON] 📨 ROUTING: Message routed to ENG-1
[TRON] 🏁 SESSION: Complete — log committed
```

#### Routing Messages (user → specific agent)

```
@ENG-1: skip tests for now, focus on core logic
@REV-1: also check the cache key patterns in my-service
@ARCH-1: what's the impact of adding a new RabbitMQ exchange?
@TRON: abort session
```

**Parsing rule:** Messages starting with `@{AGENT_ID}:` are routed to that agent. TRON monitors all messages but only acts on `@TRON:` directly. Agents only act on messages tagged to them.

**Untagged user messages:** TRON reads and decides whether to act or route. If ambiguous, TRON asks the user who the message is for.

---

## 3. Heartbeat Protocol

### 3.1 Agent-Side

Every agent must:

1. Send a `MILESTONE` message after every discrete achievement
2. If no milestone is achieved within `HEARTBEAT_INTERVAL` (default: 5 min), send a `HEARTBEAT` message with current activity
3. Before starting a long operation (>2min expected), send: `[ENG-1] ⏳ HEARTBEAT: Starting {operation} — may take up to {estimate}`

**Implementation:** Between every major step, the agent checks elapsed time since last message. If > `HEARTBEAT_INTERVAL`, send heartbeat before proceeding.

### 3.2 TRON-Side (Stall Detection)

TRON tracks `last_message_timestamp` per agent ID. Initialized to spawn time — agents are expected to send `STARTED` within 5 minutes of being spawned, or TRON will treat them as stalled.

**Detection thresholds:**

| Condition | Threshold | Action |
|:--|:--|:--|
| No message from agent | > `HEARTBEAT_INTERVAL` + `GRACE_PERIOD` (default: 5min + 2min = 7min) | Send stall warning to TG + ping the agent |
| Agent pinged, no response | > 5 minutes after stall ping (default: 12min total from last message) | Escalate to user: "Agent unresponsive. Manual intervention likely needed." |
| Agent sent "starting long operation" | Timer paused until operation estimate expires | No stall alert during expected long operations |

**Stall ping:**
```
[TRON] 🚨 STALL: @ENG-1 status check — are you still running?
```

**Escalation:**
```
[TRON] 🔴 UNRESPONSIVE: ENG-1 has not reported in {N}min. Manual intervention likely needed. Last known activity: {last message content}
```

---

## 4. Supervisor Validation Protocol

### 4.1 SV-01: Task Completion Verification

**Trigger:** Agent sends `DONE` message.

**TRON sends:**
```
[TRON] 🔍 @ENG-1: Has every single task from the block been successfully delivered, tested, and validated directly in the server(s)? Any UI or TG tasks the user may need to test?
```

**Expected response from agent:**
```
[ENG-1] ✅ VERIFIED: All tasks complete. No pending items.
```
or
```
[ENG-1] ⚠️ INCOMPLETE: T15 deploy not validated yet. Working on it now.
```

**Loop:** If incomplete → agent works → sends `DONE` again → TRON asks again. Repeats until agent confirms zero open items.

### 4.2 SV-02: Session End Enforcement

**Trigger:** SV-01 passed.

**TRON sends:**
```
[TRON] 📋 @ENG-1: Read and execute `meta/skills/skill-session-end-engineer.md` — read it first, now, then execute it without skipping ANY APPLICABLE STEP AT ALL!
```

**Verification:** TRON checks for evidence of session-end completion:
- Handover file updated (check file modification time)
- Session log written (check `meta/logs/{role}/`)
- Pipeline updated (check `pipeline.md` modification time)

If evidence missing → TRON sends agent back.

### 4.3 SV-03: Startup Directives

**Trigger:** Agent's first `STARTED` or `MILESTONE` message (indicates startup complete).

**TRON sends:**
```
[TRON] ⚡ @ENG-1: CRITICAL DIRECTIVE: ALWAYS BE VERY CONCISE! RELEVANT CONSIDERATIONS, QUESTIONS, AND ACTIONABLE ITEMS ONLY!

WARNING: There are other AGENTS working in parallel to this session. Follow all best practices regarding BRANCHES and WORKTREES to make sure there are no conflicts. Any questions or considerations?
```

**One-time only:** Sent once per agent per session, not repeated.

### 4.4 SV-04: Reviewer Coverage Verification

**Trigger:** Reviewer sends `DONE` message.

**TRON action (automated check):**
1. Run `git log --since="{review_scope_timestamp}" --name-only --pretty=""` across all repos in scope
2. Deduplicate file list
3. Compare against reviewer's reported scope
4. If files missing:

```
[TRON] 🔍 @REV-1: You missed the following files in your review: {file list}. Review them before returning.
```

**Loop:** Same as SV-01.

---

## 5. Environment Variables

Set by TRON at agent spawn time:

| Variable | Purpose | Example |
|:--|:--|:--|
| `TRON_AGENT_ID` | Agent's unique identifier | `ENG-1` |
| `TRON_AGENT_ROLE` | Agent's role | `engineer` |
| `TRON_BLOCK` | Block being worked on | `block-04-02-auth-middleware` |
| `TRON_META_PATH` | Path to project's meta/ | `/path/to/project/meta` |
| `TRON_POLL_OFFSET` | ~~Last TG update ID seen~~ | **Deprecated** — bus uses SQLite cursors |
| `TRON_HEARTBEAT_INTERVAL` | Seconds between heartbeats | `300` (5 min) |
| `TRON_POLL_INTERVAL` | Seconds between TG polls | `30` |
| `TRON_TRANSPORT` | Active transport | `tg` or `cli` |
| `TRON_LAST_MSG_TIME` | Timestamp of agent's last sent message | Unix timestamp (set at spawn) |

---

## 6. Configuration Defaults

Stored in `meta/logs/tron/tron-state.md` per project:

```markdown
## TRON Configuration

- **HEARTBEAT_INTERVAL:** 300 (5 min)
- **GRACE_PERIOD:** 120 (2 min)
- **POLL_INTERVAL:** 30 (30 sec)
- **MAX_CONCURRENT_AGENTS:** 5
- **TRANSPORT:** tg
- **TG_NOTIFICATIONS:** all (or list of disabled events)
```

---

## 7. Message Flow Examples

### 7.1 Normal Session (Single Engineer + Reviewer)

```
[TRON]  🤖 SESSION: Starting — reading pipeline and handovers
[TRON]  ⚙️ SPAWNED: ENG-1 for block-04-02 (Sonnet, interactive)
[TRON]  ⚙️ SPAWNED: REV-1 scope: commits since 260312-1400 (Sonnet, headless)
[TRON]  ⚡ @ENG-1: CRITICAL DIRECTIVE: BE CONCISE... (SV-03)
[ENG-1] 🚀 STARTED: block-04-02-auth-middleware
[ENG-1] ✅ MILESTONE: Frontend rewired to OAuth
[ENG-1] ✅ MILESTONE: Old auth backend removed
[ENG-1] ⏳ HEARTBEAT: Still working on nginx auth_request config
[ENG-1] ✅ MILESTONE: Deploy triggered — my-frontend, my-infra
[ENG-1] ⏳ HEARTBEAT: Starting deploy — may take up to 5min
[ENG-1] ✅ MILESTONE: Deploy green, server validated
[ENG-1] 🏁 DONE: All tasks complete
[TRON]  🔍 @ENG-1: Has every single task been delivered, tested, validated? (SV-01)
[ENG-1] ⚠️ INCOMPLETE: Tests not updated yet
[ENG-1] ✅ MILESTONE: Tests updated and passing
[ENG-1] 🏁 DONE: All tasks complete
[TRON]  🔍 @ENG-1: Has every single task been delivered, tested, validated? (SV-01, round 2)
[ENG-1] ✅ VERIFIED: All tasks complete. No pending items.
[TRON]  📋 @ENG-1: Read and execute skill-session-end-engineer.md (SV-02)
[ENG-1] ✅ MILESTONE: Session end complete — handover written, log committed, pipeline updated
[TRON]  ✅ SV-PASS: ENG-1 validated — presenting to user
[TRON]  📊 USER: ENG-1 completed block-04-02. Approve? (details in terminal)
        ... user approves ...
[REV-1] 🏁 DONE: Review complete — 3 findings (1 HIGH, 2 LOW)
[TRON]  🔍 Checking REV-1 coverage (SV-04)
[TRON]  ✅ SV-PASS: REV-1 covered all changed files
[TRON]  📊 USER: REV-1 found 3 issues. See findings. Approve adding to engineer's next task list?
        ... user approves ...
[TRON]  📋 Findings added to handover-engineer.md
[TRON]  ❓ USER: Proceed to next block? Pipeline has block-04-03 available.
        ... user decides ...
[TRON]  🏁 SESSION: Complete — log committed to meta/logs/tron/
```

### 7.2 Phase-End Gate (Last Block of Phase)

```
[ENG-1] 🏁 DONE: block-04-03 complete (last block of phase 04)
[TRON]  🔍 @ENG-1: Has every single task been delivered, tested, validated? (SV-01)
[ENG-1] ✅ VERIFIED: All tasks complete.
[TRON]  📋 @ENG-1: Read and execute skill-session-end-engineer.md (SV-02)
[ENG-1] ✅ MILESTONE: Session end complete
[TRON]  ⚙️ SPAWNED: REV-1 scope: commits for block-04-03 (Sonnet, headless)
[REV-1] 🏁 DONE: 5 findings (2 HIGH, 2 MEDIUM, 1 LOW)
[TRON]  🔍 REV-1 coverage check (SV-04) — all files covered
[TRON]  📋 @ENG-1: Reviewer found 5 issues. Fix ALL before proceeding. No deferrals unless you have a logically justified reason.
[ENG-1] ✅ MILESTONE: Fixed 4 findings. Finding #3 (naming convention) — intentional: matches upstream API response field names.
[TRON]  📊 USER: ENG-1 fixed 4/5 findings, justified skipping #3. Accept justification?
        ... user approves ...
[TRON]  ✅ Phase 04 engineering + review complete
[TRON]  ⚙️ SPAWNED: ARCH-1 for phase-end cleanup (Opus)
[TRON]  📋 @ARCH-1: Phase 04 is complete. Review all block specs (block-04-01 through block-04-03 + adhocs), session logs, and pipeline. Verify everything is accurate and up-to-date. Archive completed block specs to meta/blocks/archive/.
[ARCH-1] ✅ MILESTONE: Block specs reviewed — all accurate
[ARCH-1] ✅ MILESTONE: Pipeline verified — phase 04 marked complete
[ARCH-1] ✅ MILESTONE: 3 block specs + 1 adhoc archived to meta/blocks/archive/
[ARCH-1] 🏁 DONE: Phase-end cleanup complete
[TRON]  📊 USER: Phase 04 fully complete. Architect signed off. Proceed to phase 05?
```

### 7.3 Stall Detection

```
[ENG-1] ✅ MILESTONE: Starting Terraform plan
        ... 8 minutes pass, no message ...
[TRON]  🚨 STALL: @ENG-1 status check — are you still running?
        ... 5 more minutes, no response ...
[TRON]  🔴 UNRESPONSIVE: ENG-1 has not reported in 12min. Last activity: "Starting Terraform plan". Manual intervention likely needed.
```

### 7.4 User Command Routing

```
        @ENG-1: pause the deploy, I need to check something first
[TRON]  📨 Routing to ENG-1
[ENG-1] ✅ MILESTONE: Deploy paused per user request. Waiting for go-ahead.
        @ENG-1: ok continue
[ENG-1] 🚀 STARTED: Resuming deploy
```

---

**Last Updated:** 2026-03-13
