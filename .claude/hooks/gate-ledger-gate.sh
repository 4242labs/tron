#!/bin/bash
# tron kit — gate-ledger gate (PreToolUse hook, matcher: Bash).
# Contract it enforces: {meta}/skills/skill-gate-ledger.md (canon home:
# tortuga/dead-mans-chest/skills/skill-gate-ledger.md) + deterministic-fleet plan §1.8.
#
# No record, no advance: a stage-advancing command may run only when every prior
# stage of the active block has a ledger record (`## {stage} — DONE` or the
# block-start `## {stage} — n/a` declaration).
#
# Activation is explicit: the supervising process writes the active block id to
# .tron-active-block (project root) at block start and removes it at close. No
# active-block file → no supervised block in flight → this hook passes everything
# (supervisors still self-enforce the ledger as canon text).
#
# Guarded surfaces (defaults; override via config):
#   merge  — `git merge`, `gh pr merge`         → requires build..ci recorded
#   deploy — `vercel ... --prod`, deploy runs   → requires build..merge recorded
#
# Config (optional): .claude/hooks/gate-ledger.config.json
#   { "ledger_dir": "myproj-meta/blocks/ledger",
#     "active_block_file": ".tron-active-block",
#     "merge_pattern": "...", "deploy_pattern": "..." }
# Installed per project at retrofit — inert until wired into .claude/settings.json.

input=$(cat)

if ! command -v jq >/dev/null 2>&1; then
  echo "gate-ledger-gate: jq not found — gate skipped, ledger UNENFORCED this call. Install jq to arm this gate." >&2
  exit 0
fi

cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

proj="${CLAUDE_PROJECT_DIR:-.}"
cfg="$proj/.claude/hooks/gate-ledger.config.json"

active_file="$proj/.tron-active-block"
ledger_dir=""
merge_pattern='(^|[;&|[:space:]])git([[:space:]]+-[^[:space:]]+)*[[:space:]]+merge|gh[[:space:]]+pr[[:space:]]+merge'
deploy_pattern='vercel[[:space:]][^;|&]*--prod|gh[[:space:]]+workflow[[:space:]]+run[[:space:]][^;|&]*deploy'
if [ -f "$cfg" ]; then
  v=$(jq -r '.active_block_file // empty' "$cfg" 2>/dev/null); [ -n "$v" ] && active_file="$proj/$v"
  v=$(jq -r '.ledger_dir // empty' "$cfg" 2>/dev/null);        [ -n "$v" ] && ledger_dir="$proj/$v"
  v=$(jq -r '.merge_pattern // empty' "$cfg" 2>/dev/null);     [ -n "$v" ] && merge_pattern="$v"
  v=$(jq -r '.deploy_pattern // empty' "$cfg" 2>/dev/null);    [ -n "$v" ] && deploy_pattern="$v"
fi

[ -f "$active_file" ] || exit 0

stage=""
printf '%s' "$cmd" | grep -qE "$merge_pattern"  && stage="merge"
printf '%s' "$cmd" | grep -qE "$deploy_pattern" && stage="deploy-verify"
[ -n "$stage" ] || exit 0

block_id=$(tr -d '[:space:]' < "$active_file")
if [ -z "$block_id" ]; then
  echo "gate-ledger-gate: REFUSED — $active_file exists but names no block id. Fix the active-block file (block id) or remove it at block close." >&2
  exit 2
fi

# Locate the ledger: configured dir first, then the kit's standard homes.
ledger=""
for d in "$ledger_dir" "$proj"/*-meta/blocks/ledger "$proj/blocks/ledger" "$proj/meta/blocks/ledger"; do
  [ -n "$d" ] && [ -f "$d/$block_id.ledger.md" ] && { ledger="$d/$block_id.ledger.md"; break; }
done
if [ -z "$ledger" ]; then
  echo "gate-ledger-gate: REFUSED — active block '$block_id' has no ledger file ({meta}/blocks/ledger/$block_id.ledger.md). No record, no advance (skill-gate-ledger.md): create the ledger and record the completed stages before a $stage action." >&2
  exit 2
fi

case "$stage" in
  merge)         required="build challenge validation review ci" ;;
  deploy-verify) required="build challenge validation review ci merge" ;;
esac

missing=""
for s in $required; do
  grep -qE "^## $s — (DONE|n/a)" "$ledger" || missing="$missing $s"
done

if [ -n "$missing" ]; then
  echo "gate-ledger-gate: REFUSED — block '$block_id' is missing ledger record(s) for:$missing (ledger: $ledger). No record, no advance (skill-gate-ledger.md): append '## {stage} — DONE' with when/by/evidence for each completed stage (or the block-start '## {stage} — n/a' declaration), then retry. Skipping a stage is a defect regardless of whether the work 'was actually done'." >&2
  exit 2
fi

exit 0
