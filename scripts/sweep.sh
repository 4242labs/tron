#!/usr/bin/env bash
# sweep.sh — Wake TRON for a periodic sweep of worker state + TG inbox.
# Invoked by cron every N minutes (default 2). Closes the autonomous-loop gap (Premise 13).
#
# Behavior: reads TRON's current session ID from meta/agents/tron/current-id and
# sends a SWEEP message via `claude --resume`. TRON's main loop handles the actual
# state read on receipt. This script is just the trigger.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CURRENT_ID_FILE="$TRON_DIR/current-id"

if [ ! -f "$CURRENT_ID_FILE" ]; then
  # TRON not running. Silent exit — cron should not bark every minute.
  exit 0
fi

TRON_ID="$(cat "$CURRENT_ID_FILE" | tr -d '[:space:]')"

if [ -z "$TRON_ID" ]; then
  # current-id present but empty. TRON ended cleanly. Silent exit.
  exit 0
fi

# Verify TRON's session is still alive (state.json exists and process is reachable).
STATE_JSON="$HOME/.claude/jobs/$TRON_ID/state.json"
if [ ! -f "$STATE_JSON" ]; then
  # Stale current-id. Log once and exit.
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) sweep: stale current-id ($TRON_ID); state.json missing" >> "$TRON_DIR/logs/sweep-errors.log"
  exit 0
fi

# Send the SWEEP trigger. Non-blocking — claude --resume returns immediately after delivery.
claude --resume "$TRON_ID" -p "[SWEEP] tick at $(date -u +%Y-%m-%dT%H:%M:%SZ)" >/dev/null 2>&1 || {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) sweep: claude --resume failed for $TRON_ID" >> "$TRON_DIR/logs/sweep-errors.log"
  exit 7
}

exit 0
