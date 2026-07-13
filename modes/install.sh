#!/usr/bin/env bash
# Install TRON's modes. One command, fresh machine to working /tron-flynn + /tron-clu.
#
#   modes/install.sh              → slash commands available in every project, PATH shortcuts wired
#   modes/install.sh <project>    → slash commands scoped to one project (<project>/.claude/commands/)
#   modes/install.sh --no-path    → skip the shell-rc PATH line
#
# Writes exactly two kinds of thing: the slash-command files (into Claude's own commands/ dir,
# with the mode's absolute path baked in) and one PATH line in your shell rc. No pointer files,
# no environment variables, no other machine state. Re-running is safe.
set -euo pipefail

# Resolve this script's real directory, following symlinks — a convenience symlink on PATH must
# still find the modes/ tree, not the symlink's own directory.
SELF="${BASH_SOURCE[0]}"
while [ -L "$SELF" ]; do
  link="$(readlink "$SELF")"
  case "$link" in
    /*) SELF="$link" ;;
    *)  SELF="$(cd "$(dirname "$SELF")" && pwd)/$link" ;;
  esac
done
MODES_DIR="$(cd "$(dirname "$SELF")" && pwd)"

TARGET=""
WIRE_PATH=1
for arg in "$@"; do
  case "$arg" in
    --no-path) WIRE_PATH=0 ;;
    *) TARGET="$arg" ;;
  esac
done

# 1. Slash commands — machine-wide, or scoped to one project.
if [ -n "$TARGET" ]; then
  DEST="$(cd "$TARGET" && pwd)/.claude/commands"
else
  DEST="${HOME}/.claude/commands"
fi
mkdir -p "$DEST"

# `&` and `\` are special on sed's replacement side — a path containing them would silently
# corrupt the baked-in root rather than fail. Escape before substituting.
sed_escape() { printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'; }
FLYNN_ESC="$(sed_escape "${MODES_DIR}/flynn")"
CLU_ESC="$(sed_escape "${MODES_DIR}/clu")"

sed "s|<FLYNN_ROOT>|${FLYNN_ESC}|g" \
  "${MODES_DIR}/flynn/install/tron-flynn-command.md" > "${DEST}/tron-flynn.md"
sed "s|<CLU_ROOT>|${CLU_ESC}|g" \
  "${MODES_DIR}/clu/install/tron-clu-command.md" > "${DEST}/tron-clu.md"

echo "installed: ${DEST}/tron-flynn.md  → /tron-flynn"
echo "installed: ${DEST}/tron-clu.md    → /tron-clu"

# 2. Terminal shortcuts — one PATH line in the shell rc, idempotent.
if [ "$WIRE_PATH" -eq 1 ]; then
  case "${SHELL##*/}" in
    zsh)  RC="${HOME}/.zshrc" ;;
    bash) RC="${HOME}/.bashrc" ;;
    *)    RC="" ;;
  esac
  LINE="export PATH=\"${MODES_DIR}/bin:\$PATH\""
  # The rc may already carry the line in $HOME- or ~-relative form; match those too, or we append
  # a duplicate on every run.
  BIN_ABS="${MODES_DIR}/bin"
  BIN_HOME="${BIN_ABS/#$HOME/\$HOME}"
  BIN_TILDE="${BIN_ABS/#$HOME/\~}"
  if [ -z "$RC" ]; then
    echo "note: unknown shell (${SHELL:-none}) — add this to your rc yourself:"
    echo "  ${LINE}"
  elif grep -qF -e "$BIN_ABS" -e "$BIN_HOME" -e "$BIN_TILDE" "$RC" 2>/dev/null; then
    echo "shortcuts: already on PATH via ${RC}"
  else
    printf '\n# TRON modes — tron-flynn (advisor) / tron-clu (supervisor)\n%s\n' "$LINE" >> "$RC"
    echo "shortcuts: PATH line added to ${RC} → tron-flynn / tron-clu (open a new shell)"
  fi
fi

# 3. Secrets — CLU's Telegram escalation is optional; say so only when it isn't set up.
ENV_FILE="$(cd "${MODES_DIR}/.." && pwd)/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo
  echo "optional: CLU escalates over Telegram. To enable, create ${ENV_FILE} (gitignored) with:"
  echo "  TELEGRAM_BOT_TOKEN=<token>"
  echo "  TELEGRAM_CHAT_ID=<default chat id>"
fi
