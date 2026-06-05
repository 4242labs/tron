#!/usr/bin/env bash
# report.sh — the worker -> engine channel. A worker runs this to deliver a line
# to TRON; the engine drains worker-inbox.jsonl every tick and classifies it.
# There is no LLM TRON session to resume — all worker traffic lands here.
#
# Usage (from a worker's handover):  report.sh "<worker-id>" "<message>"
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INBOX="$TRON_DIR/worker-inbox.jsonl"

WID="${1:-unknown}"
shift || true
MSG="$*"
[ -n "$MSG" ] || { echo "report: empty message" >&2; exit 2; }

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -cn --arg id "$WID" --arg text "$MSG" --arg at "$TS" \
  '{at:$at, text:$text, sender:{kind:"worker", id:$id}}' >> "$INBOX"
