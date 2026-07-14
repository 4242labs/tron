#!/usr/bin/env bash
# l1.sh — block 01-40 T1 (ADR-0012 §3 P1): the ONE command that discovers and
# runs every mutation-proof rig under core/ — glob-based (core/*_rig.py +
# core/sim/*_rig.py), never a hand-maintained list, so a newly added rig is
# picked up here with zero code edits. This is the CI L1 gate (~2 min budget).
# Paired with the R3 honesty lint (core/r3_lint.py, wired as its own CI step) —
# a rig that lies is worthless to run fast.
#
# RUNTIME WRITE-GUARD (Opus-pivot item 1, ruling-independent half): every rig
# below runs with core/r3_guard.py's sys.addaudithook installed via a
# sitecustomize.py directory prepended to PYTHONPATH (see materialize_site_dir
# in core/r3_guard.py — never PYTHONSTARTUP, which does not fire for
# scripts). THIS SCRIPT IS THE ONLY PLACE THE PROTECTED-PATH POLICY LIVES —
# core/r3_guard.py itself hardcodes no path.
#
# Block 01-38 (R8/R6): operator-inbox.jsonl is NO LONGER protected here. It
# used to be — R8 had no real transport yet, so ANY in-process touch was
# inherently a fabrication. Now `core/snapshot.py::build`'s operator-channel
# drain (T3) is REAL PRODUCTION CODE that legitimately rotates/reads/removes
# `ctx.operator_inbox` every tick, in-process, whenever a rig drives a real
# `core.engine.Engine` — exactly the same reason worker-inbox.jsonl was
# ALREADY excluded below (several rigs legitimately write it in-process as a
# currently-legal shape). Blanket-protecting operator-inbox.jsonl now would
# false-RED that legitimate drain (`core/sim/operator_channel_rig.py`'s own
# proof of it). The remaining protection against a rig FABRICATING operator
# content directly (a Python `.write()`/`open(...,'w')` on `ctx.
# operator_inbox`) is `core/r3_lint.py`'s static OPERATOR_INBOX_WRITE rule
# — unchanged, still enforced, still scans every harness file; the real
# door stays `scripts/operator-reply.sh`, a genuine subprocess (see `core/
# sim/operator_proxy.py`'s block 01-38 T4 rebuild). worker-inbox.jsonl
# remains unprotected too — flipping either policy later is a ONE-LINE
# change to R3_GUARD_PROTECT below, never a code change.
#
# A rig's own instance dir is minted at RUNTIME (tempfile.mkdtemp(), a random
# suffix this script can't predict) — TMPDIR is pointed at a fresh sandbox for
# the whole run so every rig's instance dir lands under one known root; that
# sandboxing stays even with an empty protect list (fresh, isolated instance
# dirs per run is its own hygiene, independent of the guard).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

R3_SANDBOX="$(mktemp -d)"
R3_SITE_DIR="$(mktemp -d)"
cleanup() { rm -rf "$R3_SANDBOX" "$R3_SITE_DIR"; }
trap cleanup EXIT

python3 core/r3_guard.py --write-site-dir "$R3_SITE_DIR" >/dev/null

export TMPDIR="$R3_SANDBOX"
export PYTHONPATH="$R3_SITE_DIR${PYTHONPATH:+:$PYTHONPATH}"
export R3_GUARD_PROTECT=""

shopt -s nullglob
rigs=(core/*_rig.py core/sim/*_rig.py)
if [ "${#rigs[@]}" -eq 0 ]; then
  echo "l1.sh: no rigs discovered under core/*_rig.py or core/sim/*_rig.py — that's a broken glob, not an empty proof suite." >&2
  exit 1
fi

fail=0
pass_n=0
echo "l1.sh: discovered ${#rigs[@]} rig(s)"
echo "l1.sh: runtime write-guard active — protecting: $R3_GUARD_PROTECT"
for r in "${rigs[@]}"; do
  echo "::group::$r"
  if R3_GUARD_RIG="$r" python3 "$r"; then
    pass_n=$((pass_n + 1))
  else
    echo "FAILED: $r"
    fail=1
  fi
  echo "::endgroup::"
done

echo "l1.sh: ${pass_n}/${#rigs[@]} rig(s) passed"
exit $fail
