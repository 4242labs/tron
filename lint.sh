#!/usr/bin/env bash
# lint.sh — blueprint-lint over this canon instance (wraps the engine's validate).
# A malformed blueprint must fail here, at seed/validate time, not at runtime.
# Exit nonzero on any failed rule. Run from anywhere; resolves its own dir.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRON_DIR="$DIR" exec python3 "$DIR/engine/engine.py" validate
