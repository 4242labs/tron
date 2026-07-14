#!/usr/bin/env bash
# l1.sh — block 01-40 T1 (ADR-0012 §3 P1): the ONE command that discovers and
# runs every mutation-proof rig under core/ — glob-based (core/*_rig.py +
# core/sim/*_rig.py), never a hand-maintained list, so a newly added rig is
# picked up here with zero code edits. This is the CI L1 gate (~2 min budget).
# Paired with the R3 honesty lint (core/r3_lint.py, wired as its own CI step) —
# a rig that lies is worthless to run fast.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

shopt -s nullglob
rigs=(core/*_rig.py core/sim/*_rig.py)
if [ "${#rigs[@]}" -eq 0 ]; then
  echo "l1.sh: no rigs discovered under core/*_rig.py or core/sim/*_rig.py — that's a broken glob, not an empty proof suite." >&2
  exit 1
fi

fail=0
pass_n=0
echo "l1.sh: discovered ${#rigs[@]} rig(s)"
for r in "${rigs[@]}"; do
  echo "::group::$r"
  if python3 "$r"; then
    pass_n=$((pass_n + 1))
  else
    echo "FAILED: $r"
    fail=1
  fi
  echo "::endgroup::"
done

echo "l1.sh: ${pass_n}/${#rigs[@]} rig(s) passed"
exit $fail
