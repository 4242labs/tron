#!/usr/bin/env bash
# tg-send.sh — send one line to the operator's Telegram chat. Carried from v1.
# Reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from .env. Exits nonzero on failure.
#   tg-send.sh "<message>"
set -euo pipefail
[ "$#" -ge 1 ] || { echo "tg-send: usage: $0 <message>" >&2; exit 2; }
MSG="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$TRON_DIR/.env"

[ -f "$ENV_FILE" ] || { echo "tg-send: $ENV_FILE not found" >&2; exit 4; }
TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
CHAT="$(grep -E '^TELEGRAM_CHAT_ID=' "$ENV_FILE" | head -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
[ -n "${TOKEN:-}" ] && [ -n "${CHAT:-}" ] || { echo "tg-send: token/chat not set" >&2; exit 5; }

CODE="$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
  "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -d "chat_id=${CHAT}" --data-urlencode "text=${MSG}")"
[ "$CODE" = "200" ] || { echo "tg-send: HTTP $CODE" >&2; exit 6; }
echo "tg-send: ok"
