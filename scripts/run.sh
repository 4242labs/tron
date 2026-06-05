#!/usr/bin/env bash
# run.sh — the engine entry point. A thin shim over the Python spine; all flow
# lives in engine/ (watch-item R-1). Resolves the TRON instance dir and forwards.
#
#   run.sh start --max N | tick | msg "<text>" | stop [--force] | recover | validate | doctor
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
export TRON_DIR
exec python3 "$TRON_DIR/engine/engine.py" "$@"
