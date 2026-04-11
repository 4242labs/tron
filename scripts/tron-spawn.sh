#!/usr/bin/env bash
# TRON Agent Spawn Wrapper
# Usage: tron-spawn.sh <mode> <agent_id> <role> <block> <model> <meta_path> <project_root> <agent_doc> [extra_prompt]
#
# mode:         "interactive" or "headless"
# agent_id:     e.g., "ENG-10-01" (engineers), "REV-1", "ARCH-1" (all other roles)
# role:         e.g., "engineer", "reviewer-code", "architect"
# block:        e.g., "block-04-02-auth-middleware" or "phase-04-cleanup"
# model:        e.g., "claude-sonnet-4-6", "claude-opus-4-6"
# meta_path:    absolute path to project's meta/
# project_root: absolute path to project root
# agent_doc:    agent doc filename (e.g., "engineer.md")
# extra_prompt: optional additional instructions

set -euo pipefail

MODE="${1:?Usage: tron-spawn.sh <mode> <agent_id> <role> <block> <model> <meta_path> <project_root> <agent_doc> [extra_prompt]}"
AGENT_ID="${2:?Missing agent_id}"
ROLE="${3:?Missing role}"
BLOCK="${4:?Missing block}"
MODEL="${5:?Missing model}"
META_PATH="${6:?Missing meta_path}"
PROJECT_ROOT="${7:?Missing project_root}"
AGENT_DOC="${8:?Missing agent_doc}"
EXTRA_PROMPT="${9:-}"

# Determine transport
if [ -f "${META_PATH}/.env" ]; then
  eval "$(cat "${META_PATH}/.env")"
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_TRON_CHAT_ID:-}" ]; then
    TRANSPORT="tg"
  else
    TRANSPORT="cli"
  fi
else
  TRANSPORT="cli"
fi

# Build prompt
PROMPT="You are ${META_PATH}/agents/${AGENT_DOC}. Your agent ID is [${AGENT_ID}]. You are working on ${BLOCK}. Read ${META_PATH}/skills/skill-tg-comms.md for communication protocol. Execute Session Start."
if [ -n "$EXTRA_PROMPT" ]; then
  PROMPT="${PROMPT} ${EXTRA_PROMPT}"
fi

if [ "$MODE" = "interactive" ]; then
  # Step 1: Write spawn script
  SPAWN_SCRIPT="${META_PATH}/logs/tron/spawn-${AGENT_ID}.sh"
  cat > "${SPAWN_SCRIPT}" <<SCRIPT
#!/bin/bash
source ~/.zshrc 2>/dev/null || source ~/.bash_profile 2>/dev/null || true
export PATH="\$HOME/.local/bin:\$PATH"
export TRON_AGENT_ID=${AGENT_ID}
export TRON_AGENT_ROLE=${ROLE}
export TRON_BLOCK=${BLOCK}
export TRON_META_PATH=${META_PATH}
export TRON_HEARTBEAT_INTERVAL=300
export TRON_POLL_INTERVAL=30
export TRON_TRANSPORT=${TRANSPORT}

cd ${PROJECT_ROOT}

claude --model ${MODEL} --allowedTools "Bash,Read,Write,Edit,Glob,Grep"
SCRIPT
  chmod +x "${SPAWN_SCRIPT}"

  # Step 2: Write prompt file
  PROMPT_FILE="${META_PATH}/logs/tron/spawn-${AGENT_ID}-prompt.txt"
  echo "${PROMPT}" > "${PROMPT_FILE}"

  # Step 3: Open iTerm window and run spawn script
  # Note: iTerm2's AppleScript app name is "iTerm" (not "iTerm2")
  osascript \
    -e 'tell application "iTerm"' \
    -e 'activate' \
    -e 'create window with default profile' \
    -e 'tell current session of current window' \
    -e "set name to \"${AGENT_ID}\"" \
    -e "write text \"${SPAWN_SCRIPT}\"" \
    -e 'end tell' \
    -e 'end tell'

  # Step 4: Wait for claude to initialize, then send prompt
  sleep 8
  osascript \
    -e "set promptText to do shell script \"cat ${PROMPT_FILE}\"" \
    -e 'tell application "iTerm"' \
    -e 'tell current session of current window' \
    -e 'write text promptText' \
    -e 'end tell' \
    -e 'end tell'

  echo "[TRON] Spawned ${AGENT_ID} in interactive terminal (${MODEL})"

elif [ "$MODE" = "headless" ]; then
  cd "${PROJECT_ROOT}"
  TRON_AGENT_ID="${AGENT_ID}" \
  TRON_AGENT_ROLE="${ROLE}" \
  TRON_BLOCK="${BLOCK}" \
  TRON_META_PATH="${META_PATH}" \
  TRON_HEARTBEAT_INTERVAL=300 \
  TRON_POLL_INTERVAL=30 \
  TRON_TRANSPORT="${TRANSPORT}" \
  TRON_LAST_MSG_TIME="$(date +%s)" \
  claude --model "${MODEL}" \
    -p "${PROMPT}" \
    --allowedTools "Bash,Read,Write,Edit,Glob,Grep" \
    --output-format stream-json &
  AGENT_PID=$!
  echo "[TRON] Spawned ${AGENT_ID} headless PID=${AGENT_PID} (${MODEL})"
  echo "${AGENT_PID}"

else
  echo "Error: mode must be 'interactive' or 'headless'" >&2
  exit 1
fi
