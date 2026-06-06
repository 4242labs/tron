#!/usr/bin/env bash
# sweep.sh — cron's wake into the deterministic engine. One bounded tick, then exit.
# This drives the engine directly (via `tron tick`): the engine is the poller, not a
# chat being nudged. Silent until a session has started.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Nothing to do until a session has started. The engine also no-ops a pre-start
# tick; skip the call entirely until started_at carries a real value (an ISO
# timestamp -> begins with a quote or a digit; `null` does not match).
STATE="$TRON_DIR/workflow-state.yaml"
[ -f "$STATE" ] || exit 0
grep -Eq "^[[:space:]]*started_at:[[:space:]]*['\"]?[0-9]" "$STATE" || exit 0

bash "$TRON_DIR/tron" tick >/dev/null 2>&1 || {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) sweep: tick failed" >> "$TRON_DIR/logs/sweep-errors.log"
  exit 7
}
exit 0
