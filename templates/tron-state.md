# TRON State

Persistent state for TRON sessions. Updated after every session.

---

## Session History

- **Last session:** never
- **Total sessions:** 0
- **Last reviewer run:** never

## Configuration

- **HEARTBEAT_INTERVAL:** 300
- **GRACE_PERIOD:** 120
- **POLL_INTERVAL:** 30
- **MAX_CONCURRENT_AGENTS:** 5
- **TRANSPORT:** tg
- **SPAWN_MODE:** role-based (engineer/architect → interactive, reviewer/analyst → headless allowed)

## Active Notifications

| Event | Active |
|:--|:--|
| `SESSION_START` | ✅ |
| `SPAWNED` | ✅ |
| `SV-PASS` | ✅ |
| `SESSION_COMPLETE` | ✅ |
| `PIPELINE_EXHAUSTED` | ✅ |
| `BLOCKER` | ✅ (always) |
| `QUESTION` | ✅ (always) |
| `ERROR` | ✅ (always) |
| `STALL` | ✅ (always) |
| `UNRESPONSIVE` | ✅ (always) |
| `WATCHDOG_KILL` | ✅ (always) |
| `SESSION_ABORTED` | ✅ (always) |

## Agent Session-End Skills

| Role | Skill Exists | Path |
|:--|:--|:--|

## Active Agent Manifest

Updated on every spawn and release. TRON reads this before spawning engineers to prevent duplicates. Cleared at session end.

| Agent ID | Block/Scope | Role | Model | Spawned | Status |
|:--|:--|:--|:--|:--|:--|
| (none) | — | — | — | — | — |

## Watch Items

None
