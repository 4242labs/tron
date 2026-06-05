#!/usr/bin/env bash
# tg-poll.sh — poll Telegram, append new messages to tg-inbox.jsonl (the engine
# drains it each tick). Carried from v1 unchanged in spirit; the offset survives
# restarts in .tg-offset. Invoked by cron every minute (long-polls inside).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$TRON_DIR/.env"
INBOX="$TRON_DIR/tg-inbox.jsonl"
OFFSET_FILE="$TRON_DIR/.tg-offset"

[ -f "$ENV_FILE" ] || { echo "tg-poll: $ENV_FILE not found" >&2; exit 4; }
TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
[ -n "${TOKEN:-}" ] || { echo "tg-poll: TELEGRAM_BOT_TOKEN not set" >&2; exit 5; }

OFFSET=0; [ -f "$OFFSET_FILE" ] && OFFSET="$(cat "$OFFSET_FILE")"
RESP="$(curl -sS --max-time 30 "https://api.telegram.org/bot${TOKEN}/getUpdates?offset=${OFFSET}&timeout=25")"
[ -n "$RESP" ] || exit 0
[ "$(echo "$RESP" | jq -r '.ok')" = "true" ] || { echo "tg-poll: $RESP" >&2; exit 6; }
[ "$(echo "$RESP" | jq '.result | length')" -gt 0 ] || exit 0

# Normalize to the engine's inbound shape: {at, text, sender:{kind:operator}}.
echo "$RESP" | jq -c '.result[] | {at:(now|todate), text:(.message.text // ""), sender:{kind:"operator", id:(.message.from.id|tostring)}}' >> "$INBOX"
echo "$RESP" | jq '[.result[].update_id] | max + 1' > "$OFFSET_FILE"
