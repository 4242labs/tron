#!/usr/bin/env bash
# tg-send.sh — send one line to the operator's Telegram.
# Layered config: TELEGRAM_BOT_TOKEN (+ default TELEGRAM_CHAT_ID) from ~/.claude/tron-clu.env
# — a MACHINE file, never inside the repo: CLU now ships inside the public tron-app repo, so a
# repo-root .env would put the bot token one `git add -A` away from being published.
# A .tron-clu.env in the CURRENT project root overrides the chat id — one bot, one channel per
# project. Run from the project root, as CLU does.
#   tg-send.sh "<message>"
set -euo pipefail
[ "$#" -ge 1 ] || { echo "tg-send: usage: $0 <message>" >&2; exit 2; }
MSG="$1"
ENV_FILE="${HOME}/.claude/tron-clu.env"
PROJECT_ENV="$PWD/.tron-clu.env"

env_get() { grep -E "^$2=" "$1" | head -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }

[ -f "$ENV_FILE" ] || { echo "tg-send: $ENV_FILE not found" >&2; exit 4; }
TOKEN="$(env_get "$ENV_FILE" TELEGRAM_BOT_TOKEN)"
CHAT="$(env_get "$ENV_FILE" TELEGRAM_CHAT_ID || true)"
if [ -f "$PROJECT_ENV" ]; then
  P_CHAT="$(env_get "$PROJECT_ENV" TELEGRAM_CHAT_ID || true)"
  [ -n "${P_CHAT:-}" ] && CHAT="$P_CHAT"
fi
[ -n "${TOKEN:-}" ] || { echo "tg-send: TELEGRAM_BOT_TOKEN not set in $ENV_FILE" >&2; exit 5; }
[ -n "${CHAT:-}" ] || { echo "tg-send: no TELEGRAM_CHAT_ID (project $PROJECT_ENV or default $ENV_FILE)" >&2; exit 5; }

CODE="$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
  "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -d "chat_id=${CHAT}" --data-urlencode "text=${MSG}")"
[ "$CODE" = "200" ] || { echo "tg-send: HTTP $CODE" >&2; exit 6; }
echo "tg-send: ok"
