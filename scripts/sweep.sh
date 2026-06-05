#!/usr/bin/env bash
# sweep.sh — cron's wake into the deterministic engine. One bounded tick, then exit.
# This drives the engine directly (via `tron tick`): the engine is the poller, not a
# chat being nudged. Silent when not started.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Nothing to do until a session has started (workflow-state.yaml present + a cursor).
[ -f "$TRON_DIR/workflow-state.yaml" ] || exit 0

bash "$TRON_DIR/tron" tick >/dev/null 2>&1 || {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) sweep: tick failed" >> "$TRON_DIR/logs/sweep-errors.log"
  exit 7
}
exit 0
