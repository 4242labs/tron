#!/usr/bin/env bash
# tg-send.sh — Send a message to operator's Telegram chat.
# Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from <repo-root>/.env.
# Usage: bash meta/agents/tron/scripts/tg-send.sh "<message>"
# Exits non-zero on any failure so callers can detect.

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "tg-send: usage: $0 <message>" >&2
  exit 2
fi

MESSAGE="$1"

# Resolve repo root by walking up from this script's location until we hit a .git dir.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$SCRIPT_DIR"
while [ "$DIR" != "/" ] && [ ! -d "$DIR/.git" ]; do
  DIR="$(dirname "$DIR")"
done

if [ ! -d "$DIR/.git" ]; then
  echo "tg-send: could not locate repo root from $SCRIPT_DIR" >&2
  exit 3
fi

REPO_ROOT="$DIR"
ENV_FILE="$REPO_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "tg-send: $ENV_FILE not found" >&2
  exit 4
fi

# Source .env without leaking other vars into the environment; only pick what we need.
TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
TELEGRAM_CHAT_ID="$(grep -E '^TELEGRAM_CHAT_ID=' "$ENV_FILE" | head -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
  echo "tg-send: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in $ENV_FILE" >&2
  exit 5
fi

RESPONSE="$(curl -sS -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "text=${MESSAGE}" \
  -w "\n%{http_code}")"

HTTP_CODE="$(echo "$RESPONSE" | tail -n1)"
BODY="$(echo "$RESPONSE" | sed '$d')"

if [ "$HTTP_CODE" != "200" ]; then
  echo "tg-send: HTTP $HTTP_CODE — $BODY" >&2
  exit 6
fi

echo "tg-send: ok"
