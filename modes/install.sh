#!/usr/bin/env bash
# Install TRON's modes as Claude Code slash commands.
#
#   modes/install.sh            → /tron-flynn and /tron-clu, available in every project
#   modes/install.sh <project>  → same, but scoped to one project (<project>/.claude/commands/)
#
# The only thing this writes is the command file itself, with the mode's absolute path baked in.
# No pointer files, no environment variables, no machine-level state of ours.
set -euo pipefail

MODES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"
if [ -n "$TARGET" ]; then
  DEST="$(cd "$TARGET" && pwd)/.claude/commands"
else
  DEST="${HOME}/.claude/commands"
fi
mkdir -p "$DEST"

sed "s|<FLYNN_ROOT>|${MODES_DIR}/flynn|g" \
  "${MODES_DIR}/flynn/install/tron-flynn-command.md" > "${DEST}/tron-flynn.md"
sed "s|<CLU_ROOT>|${MODES_DIR}/clu|g" \
  "${MODES_DIR}/clu/install/tron-clu-command.md" > "${DEST}/tron-clu.md"

echo "installed: ${DEST}/tron-flynn.md  → /tron-flynn"
echo "installed: ${DEST}/tron-clu.md    → /tron-clu"
echo
echo "Terminal shortcuts (optional) — add to your shell rc:"
echo "  export PATH=\"${MODES_DIR}/bin:\$PATH\"   # gives you: tron-flynn / tron-clu"
