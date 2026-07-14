#!/usr/bin/env bash
# report-agent.sh — the AMBIENT-ONLY worker -> engine channel (ADR-0012 R6,
# block 01-38 T1, hostile-review hardening). This is the file `core/
# engine.py::Engine._install_agent_channel` copies, byte-identical, to
# every spawned agent's OWN install point (`<instance>/workers/<agent-id>/
# report.sh`) — NEVER `scripts/report.sh` itself (see that file's own
# header for why it still exists and what still needs it).
#
# UNLIKE `scripts/report.sh`, this script carries NO legacy self-typed-id
# branch at all — there is no `<worker-id>` positional argument this script
# will ever honor, under ANY invocation shape. Identity comes ENTIRELY from
# WHERE this copy physically lives (`basename` of its own install
# directory) — no argv, no overridable env value, structurally. A hostile
# review found the prior generation of this split re-used `scripts/
# report.sh` byte-for-byte as the per-agent copy TOO, which meant a real
# spawned worker could still invoke ITS OWN installed copy with a
# legacy-shaped first argument (`./report.sh architect --tag verdict ...`)
# — the asymmetry the review named: "refusing ambient-invocation-from-
# wrong-path but still honoring legacy-shaped argv is the hole." This file
# closes it by construction: there is no code path here that ever reads
# argv[1] as an identity claim, so there is nothing to trust or distrust.
#
#   report-agent.sh [--tag <verb>] [--block <id>] [--branch <name>] \
#                   [--type <t>] [--triage-id <id>] \
#                   [--verdict <scope_forward|answer|operator>] "<message>"
#   report-agent.sh --schema     # print the legal --tag verb set
#
# A worker that types a self-styled worker id as its first argument
# (`report-agent.sh architect --tag verdict ...`) does NOT get a different
# identity or a different inbox — the pre-existing flags-after-message
# guard (below, T1/01-24) rejects the shape outright (a `--tag` appearing
# after a non-flag first token reads as "flags after the message started")
# BEFORE anything is ever written to any inbox. A self-typed id with no
# further flags at all just becomes the first word of an ordinary free-text
# report, landing — like every other line this script ever writes — on
# THIS agent's own channel with THIS agent's own ambient identity; it can
# never relabel itself as anyone else's report.
#
# THE DOOR (block 01-37 T3, R2): a `--tag` the generated schema does not
# know is REFUSED HERE — the legal set is printed and this exits nonzero, so
# the WORKER sees its own report failed and can retry, in the SAME turn,
# rather than believing a bad report succeeded. The attempted line is STILL
# appended to the inbox (never silently discarded) — the engine's own
# admission door (`core/classify.py`/`core/door.py`) is the SECOND,
# authoritative check (R2) and is what actually RECORDS the refusal durably
# and opens a case — this script's own check is a fast, local courtesy only,
# reading the SAME generated schema, never a second hand-maintained copy.
#
# T1 (01-24 F-1a): flags come BEFORE the message, never after — a trailing
# `--tag wall` on what was meant as a plain positional message (typically a
# branch declaration) is a HARD ERROR here, never silently swallowed into
# the message text.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  echo "usage (a real spawned agent's OWN installed copy, workers/<id>/report.sh):" >&2
  echo "       report-agent.sh [--tag <verb>] [--block <id>] [--branch <name>] [--type <reviewer-type>] [--triage-id <id>] [--verdict <scope_forward|answer|operator>] \"<message>\"" >&2
  echo "       report-agent.sh --schema     # print the legal --tag verb set" >&2
  echo "flags must come BEFORE the message, never after." >&2
  echo "NOTE: this copy carries NO self-typed worker-id shape — identity is" >&2
  echo "always THIS agent's own channel, never an argv/env claim." >&2
}

if [ "$#" -eq 0 ]; then
  usage
  exit 2
fi

# Walk up from this copy's own directory until the instance root is found
# (marked by messages.yaml, always present at instance root —
# `engine/ctx.py::messages`) — robust to install depth: `workers/<id>/
# report.sh` sits two levels down.
d="$SCRIPT_DIR"
while [ "$d" != "/" ] && [ ! -f "$d/messages.yaml" ]; do
  d="$(dirname "$d")"
done
if [ ! -f "$d/messages.yaml" ]; then
  echo "report-agent: no instance root (messages.yaml) found walking up from $SCRIPT_DIR" >&2
  exit 3
fi
TRON_DIR="$d"
PARENT_NAME="$(basename "$(dirname "$SCRIPT_DIR")")"
if [ "$PARENT_NAME" != "workers" ] && [ "${1:-}" != "--schema" ]; then
  echo "report-agent: this copy is not installed under <instance>/workers/<agent-id>/ — it carries no ambient identity to report as. Run YOUR OWN spawned copy (the {report} path your SPAWN order named), never this shared template." >&2
  exit 3
fi
WID="$(basename "$SCRIPT_DIR")"
INBOX="$TRON_DIR/inbox/$WID.jsonl"
SCHEMA="$TRON_DIR/vocab.schema.json"

if [ "${1:-}" = "--schema" ]; then
  if [ -f "$SCHEMA" ]; then
    jq -r '.tags | to_entries[] | select(.value.verb != null) |
           "  --tag \(.value.verb)  slots: \(.value.slots | join(", "))"' "$SCHEMA" | sort
  else
    echo "  (no generated schema at $SCHEMA — this instance was not seeded under block 01-37's door; every --tag is accepted unchecked)" >&2
  fi
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
# at the worker, before it ever becomes free text the engine has to guess at. THIS
# is also what makes a legacy-shaped invocation (`report-agent.sh architect --tag
# verdict ...`) a hard error, never a write: "architect" is not a recognized flag,
# so the flag-parse loop above stops immediately, and the SAME `--tag` a few tokens
# later trips this exact guard — no self-typed id shape can ever reach the write
# below carrying a --tag/--triage-id/--verdict at all.
for arg in "$@"; do
  case "$arg" in
    --tag|--block|--branch|--type|--triage-id|--verdict)
      echo "report-agent: flag '$arg' appears AFTER the message started — flags-after-message is not allowed." >&2
      usage
      exit 2
      ;;
  esac
done
MSG="$*"
[ -n "$MSG" ] || { echo "report-agent: empty message" >&2; exit 2; }

REFUSED=0
if [ -n "$TAG" ] && [ -f "$SCHEMA" ]; then
  if ! jq -e --arg v "$TAG" '[.tags[] | select(.verb == $v)] | length > 0' "$SCHEMA" >/dev/null; then
    REFUSED=1
    echo "report-agent: '--tag $TAG' is not in the closed vocabulary. Legal --tag values:" >&2
    jq -r '.tags | to_entries[] | select(.value.verb != null) |
           "  --tag \(.value.verb)  slots: \(.value.slots | join(", "))"' "$SCHEMA" | sort >&2
  fi
fi

mkdir -p "$(dirname "$INBOX")"
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
