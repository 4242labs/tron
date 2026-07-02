#!/usr/bin/env bash
# report.sh — the worker -> engine channel. A worker runs this to deliver a line
# to TRON; the engine drains worker-inbox.jsonl every tick and classifies it.
# There is no LLM TRON session to resume — all worker traffic lands here.
#
# Usage (from a worker's handover):  report.sh "<worker-id>" "<message>"
#
# Structured channel (A-2, tron-13): a gate-ladder reply carries its verb as data —
# the engine resolves it deterministically, no judgment call; free text still
# classifies as before:
#   report.sh "<worker-id>" --tag <done|recorded|wall|branch|review-done|clean> \
#             [--block <id>] [--branch <name>] [--type <reviewer-type>] "<message>"
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INBOX="$TRON_DIR/worker-inbox.jsonl"

WID="${1:-unknown}"
shift || true
TAG=""; BLOCK=""; BRANCH=""; RTYPE=""
while [ $# -gt 1 ]; do
  case "$1" in
    --tag)    TAG="$2";    shift 2 ;;
    --block)  BLOCK="$2";  shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --type)   RTYPE="$2";  shift 2 ;;
    *) break ;;
  esac
done
MSG="$*"
[ -n "$MSG" ] || { echo "report: empty message" >&2; exit 2; }

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -cn --arg id "$WID" --arg text "$MSG" --arg at "$TS" \
  --arg tag "$TAG" --arg block "$BLOCK" --arg branch "$BRANCH" --arg rtype "$RTYPE" \
  '{at:$at, text:$text, sender:{kind:"worker", id:$id}}
   + (if $tag != "" then {tag:$tag} else {} end)
   + (if ($block != "" or $branch != "" or $rtype != "") then
        {slots: ((if $block != "" then {block:$block} else {} end)
               + (if $branch != "" then {branch:$branch} else {} end)
               + (if $rtype != "" then {type:$rtype} else {} end))}
      else {} end)' >> "$INBOX"
