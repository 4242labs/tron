# Kit hooks — deterministic gates

Hook scripts shipped by the scaffold kit and wired into `../settings.json`. They are the
harness-enforcement layer of the deterministic-fleet plan: the model proposes, these
scripts validate. **A gate counts as landed only where its hook is installed** — the
canon text alone is explicitly inert.

| Script | Event · matcher | Enforces |
|:--|:--|:--|
| `linear-card-lint.sh` | `PreToolUse` · `mcp__linear__save_issue` | Card contract (`skill-linear-cards.md`): agent state vocabulary, fleet assignee, owner line + signature + universal label on create |
| `telegram-send-check.sh` | `PreToolUse` · `Bash` | Channel registry (`telegram-channels.md`): a send's chat ID must equal the registered channel for this project, or it is refused |
| `gate-ledger-gate.sh` | `PreToolUse` · `Bash` | Gate ledger (`skill-gate-ledger.md`): merge/deploy commands blocked while the active block is missing prior-stage records |
| `persona-anchor-inject.sh` | `SessionStart` · `compact` | Persona persistence (`principles-base.md` §17): re-injects `*-anchor.md` files after every compaction |

## Per-project configuration

Each script runs on built-in fleet defaults; optional config files beside the scripts
override them (all untracked-safe, none required to boot):

- `linear-lint.config.json` — `{ "allowed_states": [...], "assignee": "..." }`
- `telegram-channels.local.json` — **required before any Telegram send**; written once at
  project start after the operator confirms the channel. Prefer `chat_id_env` (secrets by
  ENV NAME only); keep this file untracked.
- `gate-ledger.config.json` — `{ "ledger_dir", "active_block_file", "merge_pattern", "deploy_pattern" }`
- `persona-anchors.config.json` — `{ "paths": ["glob", ...] }`

## Semantics

- Refusals exit `2` with the reason on stderr — the agent reads it and corrects course;
  it never works around a refusal.
- `jq` is required to parse hook input; if missing, the PreToolUse gates skip **loudly**
  (stderr warning) rather than break every tool call. Install `jq` to arm them.
- The gate-ledger gate activates only while `.tron-active-block` (project root) names a
  block; the supervising process writes it at block start and removes it at close.
- Retrofits install these same files unchanged; new projects are born with them.
