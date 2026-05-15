#!/usr/bin/env bash
# tg-poll.sh — Poll Telegram for new messages and append to tg-inbox.jsonl.
# Runs independently of TRON's main loop (Premise 21).
# Designed to be invoked by cron every minute.
# Stores the polling offset in meta/agents/tron/.tg-offset so it survives restarts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# meta/agents/tron/ is two levels up from scripts/
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIR="$TRON_DIR"
while [ "$DIR" != "/" ] && [ ! -d "$DIR/.git" ]; do
  DIR="$(dirname "$DIR")"
done

if [ ! -d "$DIR/.git" ]; then
  echo "tg-poll: could not locate repo root from $SCRIPT_DIR" >&2
  exit 3
fi

REPO_ROOT="$DIR"
ENV_FILE="$REPO_ROOT/.env"
INBOX="$TRON_DIR/tg-inbox.jsonl"
OFFSET_FILE="$TRON_DIR/.tg-offset"

if [ ! -f "$ENV_FILE" ]; then
  echo "tg-poll: $ENV_FILE not found" >&2
  exit 4
fi

TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "tg-poll: TELEGRAM_BOT_TOKEN not set" >&2
  exit 5
fi

OFFSET=0
if [ -f "$OFFSET_FILE" ]; then
  OFFSET="$(cat "$OFFSET_FILE")"
fi

# Long-poll for up to 25 seconds; fits inside a one-minute cron with margin.
RESPONSE="$(curl -sS --max-time 30 \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?offset=${OFFSET}&timeout=25")"

if [ -z "$RESPONSE" ]; then
  echo "tg-poll: empty response"
  exit 0
fi

OK="$(echo "$RESPONSE" | jq -r '.ok')"
if [ "$OK" != "true" ]; then
  echo "tg-poll: telegram error: $RESPONSE" >&2
  exit 6
fi

UPDATE_COUNT="$(echo "$RESPONSE" | jq '.result | length')"
if [ "$UPDATE_COUNT" -eq 0 ]; then
  exit 0
fi

# Append each update as one JSON line. Advance offset to (max update_id + 1).
echo "$RESPONSE" | jq -c '.result[]' >> "$INBOX"
NEW_OFFSET="$(echo "$RESPONSE" | jq '[.result[].update_id] | max + 1')"
echo "$NEW_OFFSET" > "$OFFSET_FILE"

echo "tg-poll: $UPDATE_COUNT new message(s); offset → $NEW_OFFSET"
