#!/usr/bin/env bash
# cron-install.sh — Install (or refresh) the cron entries that drive TRON's
# autonomous loop: periodic sweep + Telegram polling.
#
# Run by the seeder at the end of seeding, and re-runnable safely any time.
# Idempotent: deduplicates by a tag comment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SWEEP_PATH="$SCRIPT_DIR/sweep.sh"
TG_POLL_PATH="$SCRIPT_DIR/tg-poll.sh"

# A unique tag so we can find and replace just our entries on re-install.
TAG="# tron-cron:$TRON_DIR"

# Cron cadence:
# - sweep every 2 min
# - tg-poll every 1 min (long-polls inside, so this is fine)
SWEEP_LINE="*/2 * * * * bash $SWEEP_PATH $TAG"
TG_POLL_LINE="* * * * * bash $TG_POLL_PATH $TAG"

# Get current crontab (or empty if none).
EXISTING="$(crontab -l 2>/dev/null || true)"

# Strip any prior tron-cron lines for this TRON_DIR.
FILTERED="$(echo "$EXISTING" | grep -v "$TAG" || true)"

# Append fresh entries.
{
  echo "$FILTERED"
  echo "$SWEEP_LINE"
  echo "$TG_POLL_LINE"
} | sed '/^$/d' | crontab -

echo "cron-install: installed entries for $TRON_DIR"
echo "  sweep:   $SWEEP_PATH (every 2 min)"
echo "  tg-poll: $TG_POLL_PATH (every 1 min)"
echo
echo "To verify: crontab -l | grep \"$TAG\""
echo "To remove: crontab -l | grep -v \"$TAG\" | crontab -"
