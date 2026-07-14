#!/usr/bin/env bash
# report.sh — the worker -> engine channel. A worker runs this to deliver a line
# to TRON; the engine drains it every tick and classifies it.
#
# HOSTILE-REVIEW SPLIT (block 01-38, post-review hardening): a REAL spawned
# agent's OWN installed copy at `<instance>/workers/<agent-id>/report.sh` is
# NO LONGER a byte-identical copy of THIS file — it is `scripts/report-
# agent.sh` (`core/engine.py::Engine._install_agent_channel`), an
# AMBIENT-ONLY variant with NO legacy self-typed-id branch at all. A review
# found that installing this file (legacy branch included) per-agent left a
# genuine worker able to invoke its OWN copy with a self-typed id
# (`./report.sh architect --tag verdict ...`) and reach the shared legacy
# inbox from a live agent's own reach — the asymmetry named: "refusing
# ambient-invocation-from-wrong-path but still honoring legacy-shaped
# argv is the hole." THIS file keeps BOTH branches (below) ONLY because it
# is also the door the frozen pre-rewrite engine (`engine/fsm.py`) and
# several pre-01-38 `core/*_rig.py`/`engine/block_01_24_test.py`/
# `engine/block_01_29_test.py` fixtures still depend on — it is seeded at
# `<instance>/scripts/report.sh` (the canon path those depend on) but is
# NEVER copied into a live agent's own installed reach anymore; see
# `scripts/report-agent.sh`'s own header for the file a real spawn actually
# gets. Independently, `core/vocab.py::resolve_origin` no longer trusts a
# self-typed id arriving via the shared legacy inbox for a PRIVILEGED
# (architect/operator) grant either way — defense in depth, not just this
# split.
#
# Block 01-38 (ADR-0012 R6 — identity is ambient, not asserted): a REAL
# spawned agent runs its OWN installed copy, `<instance>/workers/<agent-id>/
# report.sh` — `scripts/report-agent.sh`, copied verbatim at spawn
# (`core/engine.py::Engine._install_agent_channel`, never templated). That
# copy carries NO typed worker-id argv and NO overridable env value for its
# identity: identity comes ENTIRELY from where the copy physically lives —
# `basename` of its own install directory — so a worker can no longer type
# a different name and mint as someone else (the D8 hole R6 closes). It
# writes to that same agent's own private channel, `inbox/<agent-id>.jsonl`
# — never the shared file below.
#
#   report.sh [--tag <verb>] [--block <id>] [--branch <name>] [--type <t>] \
#             [--triage-id <id>] [--verdict <scope_forward|answer|operator>] \
#             "<message>"
#   report.sh --schema     # print the legal --tag verb set
#
# LEGACY mode (pre-01-38): a first argument that does NOT start with "--" is
# read as a SELF-TYPED worker id — `report.sh "<worker-id>" ...` — writing to
# the single shared `worker-inbox.jsonl`. Kept alive, byte-for-byte
# unchanged from before this block, ONLY because this one physical file is
# also the door the frozen pre-rewrite engine (`engine/fsm.py`, its own CI
# suite: `engine/block_01_24_test.py`/`block_01_29_test.py`) and several
# pre-01-38 `core/*_rig.py` fixtures already depend on — none of which block
# 01-38's own Tasks name or touch, and breaking them is out of this block's
# scope (recorded in the PR body as a deliberate, documented resolution of a
# real scope tension, never a silent guess). A legal worker id NEVER begins
# with "--" (the established naming: `engineer-01-02`, `ENG-A`, `REV-code`,
# the architect's own WID), so the two shapes are unambiguous by
# construction — no flag/positional collision possible. A REAL `core/
# engine.py` spawn (this block's own concern) NEVER invokes this script the
# legacy way; every canon prompt slot (`{report}`) a real agent is ever
# handed points at ITS OWN ambient copy (`core/engine.py::Engine.emit`),
# never at this shared source file.
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
  echo "usage (ambient — a real spawned agent's OWN installed copy, workers/<id>/report.sh):" >&2
  echo "       report.sh [--tag <verb>] [--block <id>] [--branch <name>] [--type <reviewer-type>] [--triage-id <id>] [--verdict <scope_forward|answer|operator>] \"<message>\"" >&2
  echo "       report.sh --schema     # print the legal --tag verb set" >&2
  echo "usage (legacy — self-typed worker id, pre-01-38 rigs / the retired engine only):" >&2
  echo "       report.sh <worker-id> [--tag <verb>] ... \"<message>\"" >&2
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

if [ "$#" -eq 0 ]; then
  usage
  exit 2
fi

# ── AMBIENT vs LEGACY (block 01-38, R6) — see the header comment above for
#    the full rationale; detection is unambiguous by construction. ──
case "${1:-}" in
  --*) AMBIENT=1 ;;
  *)   AMBIENT=0 ;;
esac

if [ "$AMBIENT" -eq 1 ]; then
  # Walk up from this copy's own directory until the instance root is found
  # (marked by messages.yaml, always present at instance root —
  # `engine/ctx.py::messages`) — robust to install depth: `workers/<id>/
  # report.sh` sits two levels down; the seeded source template this was
  # copied from (`scripts/report.sh`) sits one.
  d="$SCRIPT_DIR"
  while [ "$d" != "/" ] && [ ! -f "$d/messages.yaml" ]; do
    d="$(dirname "$d")"
  done
  if [ ! -f "$d/messages.yaml" ]; then
    echo "report: ambient invocation but no instance root (messages.yaml) found walking up from $SCRIPT_DIR" >&2
    exit 3
  fi
  TRON_DIR="$d"
  PARENT_NAME="$(basename "$(dirname "$SCRIPT_DIR")")"
  if [ "$PARENT_NAME" != "workers" ] && [ "${1:-}" != "--schema" ]; then
    echo "report: this copy is not installed under <instance>/workers/<agent-id>/ — it carries no ambient identity to report as. Run YOUR OWN spawned copy (the {report} path your SPAWN order named), never this shared template." >&2
    exit 3
  fi
  WID="$(basename "$SCRIPT_DIR")"
  INBOX="$TRON_DIR/inbox/$WID.jsonl"
else
  WID="$1"
  shift
  TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  INBOX="$TRON_DIR/worker-inbox.jsonl"
fi
SCHEMA="$TRON_DIR/vocab.schema.json"

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
