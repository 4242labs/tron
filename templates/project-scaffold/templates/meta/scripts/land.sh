#!/usr/bin/env bash
# land.sh — the ONLY sanctioned way to advance trunk locally (ADR-0002 D2, block
# 01-32 T3). TRON never merges/rebases/advances trunk itself (Decision 1's sealed
# write-boundary allowlist would refuse the git write outright) — on gate approval
# it mints a patch-id-bound grant in its own folder
# (meta/agents/tron/grants/<case-id>.grant) and tells the responsible worker to run
# THIS script. TRON then only OBSERVES the committed result.
#
# Usage: meta/scripts/land.sh <case-id> [--main <branch>] [--grants-dir <dir>]
#
# Protocol (verbatim from the ADR): take an exclusive lock, re-derive the branch's
# patch-id against CURRENT trunk and validate it against a LIVE grant, verify a
# strict fast-forward, advance the ref by compare-and-swap (`update-ref <new>
# <old>` — a concurrent advance fails loudly; rebase and retry), consume the grant
# (rename into consumed/ + a result receipt), release the lock. Merge-then-consume
# ordering makes every crash window safe:
#   - crash BEFORE the ref advance -> the grant is still live; a retry re-validates
#     from scratch, exactly as if nothing had run.
#   - crash AFTER the advance but BEFORE consume -> trunk moved, grant still live.
#     A retry's own "already landed" check (below) finds the branch tip already an
#     ancestor of trunk and consumes administratively, exiting 0 — a non-event,
#     never a spurious failure on a successful land. TRON detects the same window
#     independently (its own patch-id-over-the-observed-range read) and consumes
#     it itself if this script never gets to retry.
#   - an EXPIRED grant refuses outright (ask TRON to re-approve — never a silent
#     re-mint from inside this script).
#   - an empty/unresolvable patch-id is fail-closed on BOTH sides (grants.py never
#     mints one; this script never treats an empty compare as a match).
set -euo pipefail

CASE_ID="${1:?usage: land.sh <case-id> [--main <branch>] [--grants-dir <dir>]}"
shift || true

REPO_ROOT="$(git rev-parse --show-toplevel)"
MAIN_BRANCH="${LAND_MAIN_BRANCH:-main}"
GRANTS_DIR="${LAND_GRANTS_DIR:-$REPO_ROOT/meta/agents/tron/grants}"

while [ $# -gt 0 ]; do
  case "$1" in
    --main) MAIN_BRANCH="$2"; shift 2 ;;
    --grants-dir) GRANTS_DIR="$2"; shift 2 ;;
    *) echo "land.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
done

GRANT_FILE="$GRANTS_DIR/${CASE_ID}.grant"
CONSUMED_DIR="$GRANTS_DIR/consumed"
CONSUMED_FILE="$CONSUMED_DIR/${CASE_ID}.grant"
LOCK_FILE="$GRANTS_DIR/.landlock"

mkdir -p "$CONSUMED_DIR"

# `kv_get <file> <key>` — the grant file's flat key=value format (grants.py's own
# convention: no jq/python3 dependency guaranteed on every seated project).
kv_get() {
  awk -F= -v k="$2" '$1==k {v=substr($0, length(k)+2); found=1} END{if(found) print v}' "$1" 2>/dev/null
}

# Exclusive lock for the whole read-validate-advance-consume sequence (advisory —
# the reference-transaction hook, where installed, is the mechanical backstop that
# doesn't depend on every writer respecting this flock).
exec 9>"$LOCK_FILE"
flock -x 9

# Already-consumed (receipt on file) -> the idempotent already-landed retry arm,
# happy-path half: a re-run after a clean prior land is a non-event.
if [ -f "$CONSUMED_FILE" ]; then
  echo "land.sh: case $CASE_ID already consumed (receipt on file) — nothing to do, exit 0"
  exit 0
fi

if [ ! -f "$GRANT_FILE" ]; then
  echo "land.sh: no live grant for case $CASE_ID under $GRANTS_DIR — refusing to land anything (ADR-0002 D2: land.sh is grant-gated, no exceptions)" >&2
  exit 1
fi

BRANCH="$(kv_get "$GRANT_FILE" branch)"
GRANT_PID="$(kv_get "$GRANT_FILE" patch_id)"
MINTED_AT="$(kv_get "$GRANT_FILE" minted_at)"
TTL_MIN="$(kv_get "$GRANT_FILE" ttl_min)"
[ -n "$MINTED_AT" ] || MINTED_AT=0
[ -n "$TTL_MIN" ] || TTL_MIN=60

if [ -z "$BRANCH" ]; then
  echo "land.sh: grant $CASE_ID has no branch field — malformed, refusing" >&2
  exit 1
fi
if [ -z "$GRANT_PID" ]; then
  # Fail-closed rider (ADR-0002 D2, verbatim): an empty patch-id is never a match.
  echo "land.sh: grant $CASE_ID has an empty/unresolvable patch-id — fail-closed, refusing" >&2
  exit 1
fi

NOW="$(date +%s)"
AGE_MIN="$(awk -v now="$NOW" -v minted="$MINTED_AT" 'BEGIN{printf "%.4f", (now-minted)/60}')"
if awk -v age="$AGE_MIN" -v ttl="$TTL_MIN" 'BEGIN{exit !(age>ttl)}'; then
  echo "land.sh: grant $CASE_ID expired ($AGE_MIN min > ${TTL_MIN} min TTL) — refusing; ask TRON to re-approve (loud re-open, never a silent re-mint from here)" >&2
  exit 1
fi

BRANCH_TIP="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "$BRANCH" 2>/dev/null || true)"
if [ -z "$BRANCH_TIP" ]; then
  echo "land.sh: branch $BRANCH does not resolve in this repo" >&2
  exit 1
fi
OLD_TIP="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/heads/$MAIN_BRANCH")"
if [ -z "$OLD_TIP" ]; then
  echo "land.sh: trunk branch '$MAIN_BRANCH' does not exist" >&2
  exit 1
fi

_consume() {   # _consume <result>
  cp "$GRANT_FILE" "$CONSUMED_FILE"
  {
    echo "consumed_at=$(date +%s)"
    echo "result=$1"
  } >> "$CONSUMED_FILE"
  rm -f "$GRANT_FILE"
}

# Already-landed idempotent retry arm (crash-after-advance-before-consume, OR a
# plain re-run of an already-successful land): the branch tip is ALREADY an
# ancestor of trunk -> nothing left to advance, consume administratively, exit 0.
if git -C "$REPO_ROOT" merge-base --is-ancestor "$BRANCH_TIP" "$OLD_TIP" 2>/dev/null; then
  _consume "already-landed"
  echo "land.sh: $BRANCH ($BRANCH_TIP) is already an ancestor of $MAIN_BRANCH — idempotent retry, grant $CASE_ID consumed, exit 0"
  exit 0
fi

# Re-derive the patch-id against CURRENT trunk and validate it against the grant —
# a pure rebase (same diff) still matches; a content-changing rebase does not
# (ADR-0002 D2: "that is fail-toward-gate, by design" — re-ask TRON, never land it).
MERGE_BASE="$(git -C "$REPO_ROOT" merge-base "$MAIN_BRANCH" "$BRANCH" 2>/dev/null || true)"
if [ -z "$MERGE_BASE" ]; then
  echo "land.sh: no merge-base between $MAIN_BRANCH and $BRANCH — refusing" >&2
  exit 1
fi
CUR_PID="$(git -C "$REPO_ROOT" diff "${MERGE_BASE}..${BRANCH}" 2>/dev/null | git -C "$REPO_ROOT" patch-id --stable 2>/dev/null | awk '{print $1}')"
if [ -z "$CUR_PID" ] || [ "$CUR_PID" != "$GRANT_PID" ]; then
  echo "land.sh: re-derived patch-id ($CUR_PID) does not match the grant's ($GRANT_PID) — content changed since approval; ask TRON to re-approve, never landing an unseen diff" >&2
  exit 1
fi

# Strict fast-forward check.
if ! git -C "$REPO_ROOT" merge-base --is-ancestor "$OLD_TIP" "$BRANCH_TIP" 2>/dev/null; then
  echo "land.sh: not a fast-forward ($MAIN_BRANCH is not an ancestor of $BRANCH) — rebase your branch onto trunk and retry (your grant's patch-id carries if the diff is unchanged)" >&2
  exit 1
fi

# The advance itself: compare-and-swap, atomic. A concurrent advance (another
# lander racing this one) fails this loudly — rebase and retry (AC-5).
if ! git -C "$REPO_ROOT" update-ref "refs/heads/$MAIN_BRANCH" "$BRANCH_TIP" "$OLD_TIP"; then
  echo "land.sh: update-ref CAS failed (concurrent advance?) — rebase onto the new trunk tip and retry" >&2
  exit 1
fi

_consume "landed"
echo "land.sh: landed $BRANCH (${OLD_TIP:0:7}..${BRANCH_TIP:0:7}) onto $MAIN_BRANCH — grant $CASE_ID consumed"
