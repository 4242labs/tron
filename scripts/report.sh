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
#   report.sh "<worker-id>" --tag <done|recorded|wall|branch|review-done|clean|retract> \
#             [--block <id>] [--branch <name>] [--type <reviewer-type>] \
#             [--kind <scope|blueprint|design|...>] "<message>"
#
# T1 (01-24 F-1a): flags come BEFORE the message, never after — a trailing `--tag wall`
# on what was meant as a plain positional message (typically a branch declaration) is
# the exact fat-finger that opens a false wall, so it is a HARD ERROR here, never
# silently swallowed into the message text. The canonical branch declaration needs no
# `--tag` at all: `report.sh "<worker-id>" --branch <name> "<message>"`.
#
# T3 (01-24 F-2, review cycle 1): `--kind` is a MODIFIER — it rides like --branch/--block,
# only meaningful on a `--tag wall` report. It lets a worker DECLARE the wall's kind
# structurally (scope|blueprint|design route to the architect first, who owns the block
# spec; anything else, or no --kind at all, pages the operator directly exactly as
# before) — the engine routes on this declared kind, never on prose classification.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INBOX="$TRON_DIR/worker-inbox.jsonl"

usage() {
  echo "usage: report.sh <worker-id> [--tag <done|recorded|wall|branch|review-done|clean|retract>] [--block <id>] [--branch <name>] [--type <reviewer-type>] [--kind <scope|blueprint|design|...>] \"<message>\"" >&2
  echo "flags must come BEFORE the message, never after." >&2
}

WID="${1:-unknown}"
shift || true
TAG=""; BLOCK=""; BRANCH=""; RTYPE=""; KIND=""
while [ $# -gt 1 ]; do
  case "$1" in
    --tag)    TAG="$2";    shift 2 ;;
    --block)  BLOCK="$2";  shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --type)   RTYPE="$2";  shift 2 ;;
    --kind)   KIND="$2";   shift 2 ;;
    *) break ;;
  esac
done
# T1 (01-24 F-1a): once the flag prefix ends, NOTHING left may look like a flag — a
# stray `--tag wall` (or any other recognized flag) appearing after the message has
# started reads identically to a real one to anything downstream. Reject it here,
# at the worker, before it ever becomes free text the engine has to guess at.
for arg in "$@"; do
  case "$arg" in
    --tag|--block|--branch|--type|--kind)
      echo "report: flag '$arg' appears AFTER the message started — flags-after-message is not allowed." >&2
      usage
      exit 2
      ;;
  esac
done
MSG="$*"
[ -n "$MSG" ] || { echo "report: empty message" >&2; exit 2; }

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -cn --arg id "$WID" --arg text "$MSG" --arg at "$TS" \
  --arg tag "$TAG" --arg block "$BLOCK" --arg branch "$BRANCH" --arg rtype "$RTYPE" \
  --arg kind "$KIND" \
  '{at:$at, text:$text, sender:{kind:"worker", id:$id}}
   + (if $tag != "" then {tag:$tag} else {} end)
   + (if ($block != "" or $branch != "" or $rtype != "" or $kind != "") then
        {slots: ((if $block != "" then {block:$block} else {} end)
               + (if $branch != "" then {branch:$branch} else {} end)
               + (if $rtype != "" then {type:$rtype} else {} end)
               + (if $kind != "" then {kind:$kind} else {} end))}
      else {} end)' >> "$INBOX"
