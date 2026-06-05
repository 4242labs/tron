#!/usr/bin/env bash
# cron-install.sh — install/refresh the heartbeat that ticks the engine + polls
# Telegram. Run at seed end and re-runnable any time. Idempotent: dedupes by tag.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SWEEP_PATH="$SCRIPT_DIR/sweep.sh"
TG_POLL_PATH="$SCRIPT_DIR/tg-poll.sh"

TAG="# tron-cron:$TRON_DIR"
SWEEP_LINE="*/2 * * * * bash $SWEEP_PATH $TAG"
EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(echo "$EXISTING" | grep -v "$TAG" || true)"

# TG polling only when the connector + .env exist (telegram enabled).
TG_LINE=""
if [ -f "$TG_POLL_PATH" ] && [ -f "$TRON_DIR/.env" ]; then
  TG_LINE="* * * * * bash $TG_POLL_PATH $TAG"
fi

{
  echo "$FILTERED"
  echo "$SWEEP_LINE"
  [ -n "$TG_LINE" ] && echo "$TG_LINE"
} | sed '/^$/d' | crontab -

echo "cron-install: heartbeat for $TRON_DIR"
echo "  sweep:   $SWEEP_PATH (every 2 min)"
[ -n "$TG_LINE" ] && echo "  tg-poll: $TG_POLL_PATH (every 1 min)"
echo "  remove:  crontab -l | grep -v \"$TAG\" | crontab -"
