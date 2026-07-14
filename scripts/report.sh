#!/usr/bin/env bash
# report.sh — the worker -> engine channel. A worker runs this to deliver a line
# to TRON; the engine drains worker-inbox.jsonl every tick and classifies it.
# There is no LLM TRON session to resume — all worker traffic lands here.
#
# Usage (from a worker's handover):  report.sh "<worker-id>" "<message>"
#
# Block 01-37 (ADR-0012 R1/R2, T2/T3): this script embeds NO vocabulary of its
# own any more — it loads the GENERATED schema (`core/vocab.py::write_schema`,
# never hand-committed) a real seed materializes at `<instance>/
# vocab.schema.json`, next to this script's own `..`. Structured channel
# (A-2, tron-13): a gate-ladder reply carries its verb as data — the engine
# resolves it deterministically, no judgment call:
#   report.sh "<worker-id>" --tag <verb> \
#             [--block <id>] [--branch <name>] [--type <reviewer-type>] \
#             [--triage-id <id>] [--verdict <scope_forward|answer|operator>] \
#             "<message>"
# Run `report.sh <worker-id> --schema` to print the legal verb set.
#
# T1 (01-24 F-1a): flags come BEFORE the message, never after — a trailing `--tag wall`
# on what was meant as a plain positional message (typically a branch declaration) is
# the exact fat-finger that opens a false wall, so it is a HARD ERROR here, never
# silently swallowed into the message text. The canonical branch declaration needs no
# `--tag` at all: `report.sh "<worker-id>" --branch <name> "<message>"`.
#
# T3 (block 01-37): `--kind` is DELETED — dead since 01-31 made every wall
# architect-first; it no longer changes any routing (confirmed: no `core/*.py`
# reader of `slots.kind` remains). `--tag verdict --triage-id <id> --verdict
# <v>` is the architect's own verdict-wire reply (T9), ported from the
# ADR-0011 salvage lineage.
#
# THE DOOR (T3, R2): a `--tag` the generated schema does not know is REFUSED
# HERE — the legal set is printed and this exits nonzero, so the WORKER sees
# its own report failed and can retry, in the SAME turn, rather than
# believing a bad report succeeded (the historical disease: "a bad --tag
# exits 0 and is dropped downstream"). The attempted line is STILL appended
# to the inbox (never silently discarded) — the engine's own admission door
# (`core/classify.py`/`core/door.py`) is the SECOND, authoritative check
# (R2: "total in both directions, enforced at both ends") and is what
# actually RECORDS the refusal durably (full text + sender) and opens a
# case (AC-4) — this script's own check is a fast, local courtesy only,
# reading the SAME generated schema, never a second hand-maintained copy of
# the vocabulary.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INBOX="$TRON_DIR/worker-inbox.jsonl"
SCHEMA="$TRON_DIR/vocab.schema.json"

usage() {
  echo "usage: report.sh <worker-id> [--tag <verb>] [--block <id>] [--branch <name>] [--type <reviewer-type>] [--triage-id <id>] [--verdict <scope_forward|answer|operator>] \"<message>\"" >&2
  echo "       report.sh <worker-id> --schema     # print the legal --tag verb set" >&2
  echo "flags must come BEFORE the message, never after." >&2
}

legal_set() {
  if [ -f "$SCHEMA" ]; then
    jq -r '.tags | to_entries[] | select(.value.verb != null) |
           "  --tag \(.value.verb)  slots: \(.value.slots | join(", "))"' "$SCHEMA" | sort
  else
    echo "  (no generated schema at $SCHEMA — this instance was not seeded under block 01-37's door; every --tag is accepted unchecked)" >&2
  fi
}

WID="${1:-unknown}"
shift || true

if [ "${1:-}" = "--schema" ]; then
  legal_set
  exit 0
fi

TAG=""; BLOCK=""; BRANCH=""; RTYPE=""; TRIAGE_ID=""; VERDICT=""
while [ $# -gt 1 ]; do
  case "$1" in
    --tag)        TAG="$2";       shift 2 ;;
    --block)      BLOCK="$2";     shift 2 ;;
    --branch)     BRANCH="$2";    shift 2 ;;
    --type)       RTYPE="$2";     shift 2 ;;
    --triage-id)  TRIAGE_ID="$2"; shift 2 ;;
    --verdict)    VERDICT="$2";   shift 2 ;;
    *) break ;;
  esac
done
# T1 (01-24 F-1a): once the flag prefix ends, NOTHING left may look like a flag — a
# stray `--tag wall` (or any other recognized flag) appearing after the message has
# started reads identically to a real one to anything downstream. Reject it here,
# at the worker, before it ever becomes free text the engine has to guess at.
for arg in "$@"; do
  case "$arg" in
    --tag|--block|--branch|--type|--triage-id|--verdict)
      echo "report: flag '$arg' appears AFTER the message started — flags-after-message is not allowed." >&2
      usage
      exit 2
      ;;
  esac
done
MSG="$*"
[ -n "$MSG" ] || { echo "report: empty message" >&2; exit 2; }

# THE DOOR: a non-empty --tag must be a legal verb the generated schema
# knows. A tag-LESS report (the canonical branch declaration, or any other
# modifier-only line) carries no verb to check here at all — it is the
# engine's own `core/classify.py::_structured` that resolves it structurally.
REFUSED=0
if [ -n "$TAG" ] && [ -f "$SCHEMA" ]; then
  if ! jq -e --arg v "$TAG" '[.tags[] | select(.verb == $v)] | length > 0' "$SCHEMA" >/dev/null; then
    REFUSED=1
    echo "report: '--tag $TAG' is not in the closed vocabulary. Legal --tag values:" >&2
    legal_set >&2
  fi
fi

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -cn --arg id "$WID" --arg text "$MSG" --arg at "$TS" \
  --arg tag "$TAG" --arg block "$BLOCK" --arg branch "$BRANCH" --arg rtype "$RTYPE" \
  --arg triage_id "$TRIAGE_ID" --arg verdict "$VERDICT" \
  '{at:$at, text:$text, sender:{kind:"worker", id:$id}}
   + (if $tag != "" then {tag:$tag} else {} end)
   + (if ($block != "" or $branch != "" or $rtype != ""
          or $triage_id != "" or $verdict != "") then
        {slots: ((if $block != "" then {block:$block} else {} end)
               + (if $branch != "" then {branch:$branch} else {} end)
               + (if $rtype != "" then {type:$rtype} else {} end)
               + (if $triage_id != "" then {triage_id:$triage_id} else {} end)
               + (if $verdict != "" then {verdict:$verdict} else {} end))}
      else {} end)' >> "$INBOX"

# The attempted line is ALWAYS appended above (never silently discarded —
# the engine's own door records + cases a genuine refusal, AC-4) — but a
# LOCALLY-refused tag still exits nonzero here, so the worker's OWN turn
# sees the failure and can retry with a legal verb, never believing a
# dropped report succeeded.
[ "$REFUSED" -eq 0 ] || exit 2
