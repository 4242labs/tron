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
#     ancestor of trunk AND confirms the grant's own patch-id in the branch's recent
#     history (F5, review round 1 — never bare ancestry alone, a stale/regressed
#     branch tip must never read as a false already-landed no-op) before consuming
#     administratively and exiting 0 — a non-event, never a spurious failure on a
#     successful land. TRON detects the same window independently (its own
#     patch-id-over-the-observed-range read) and consumes it itself if this script
#     never gets to retry.
#   - an EXPIRED grant refuses outright (ask TRON to re-approve — never a silent
#     re-mint from inside this script).
#   - an empty/unresolvable patch-id is fail-closed on BOTH sides (grants.py never
#     mints one; this script never treats an empty compare as a match).
#   - CASE_ID is validated against a safe token pattern before any path interpolation
#     (F6, review round 1) — never trusted raw.
set -euo pipefail

CASE_ID="${1:?usage: land.sh <case-id> [--main <branch>] [--grants-dir <dir>]}"
shift || true

# F6 (review round 1): CASE_ID rides straight into path interpolation below
# ($GRANTS_DIR/${CASE_ID}.grant, consumed/${CASE_ID}.grant) — reject anything that
# isn't a safe token BEFORE any of that happens (never after — a `../` or embedded
# path separator must never reach a path construction, even once).
case "$CASE_ID" in
  *[!A-Za-z0-9._-]*)
    echo "land.sh: invalid case id '$CASE_ID' — must match [A-Za-z0-9._-]+, refusing before any path interpolation" >&2
    exit 2
    ;;
esac

# ADR-0003 D-G (02-12 T1): `--show-toplevel` resolves the CURRENT worktree, not the
# shared project root the grants dir lives under — landing from a worker's own worktree
# would look for grants in the wrong place. `--git-common-dir/..` resolves the shared root.
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
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
# ancestor of trunk -> nothing left to advance.
#
# F5 fix (review round 1, ADR-0002 D2): bare ancestry used to be trusted outright —
# but a STALE/REGRESSED branch tip (a bad reset that walks the branch back to its own
# unchanged base, or any ancestor trunk already contains for unrelated reasons) is
# ALSO trivially "an ancestor of trunk", with NOTHING of the grant's actual content
# ever delivered. Before trusting ancestry, confirm the grant's own patch-id is
# actually found in BRANCH_TIP's own history: walk BRANCH_TIP~1, BRANCH_TIP~2, ...
# (a bounded lookback — a branch carries a handful of commits, never hundreds) and
# check `diff(BRANCH_TIP~k..BRANCH_TIP)`'s patch-id against the grant — mirroring the
# engine's own administrative-consume discipline (`patch_id_range` over an observed
# window) rather than trusting ancestry alone. For the ordinary single-landing-window
# shape this is exactly the SAME range the grant's patch-id was minted over in the
# first place (BRANCH_TIP~1 == the branch's own merge-base at mint time, since the
# worker rebases onto trunk immediately before requesting the grant).
CONFIRM_LOOKBACK=50
if git -C "$REPO_ROOT" merge-base --is-ancestor "$BRANCH_TIP" "$OLD_TIP" 2>/dev/null; then
  LANDED_CONFIRMED=0
  K=1
  while [ "$K" -le "$CONFIRM_LOOKBACK" ]; do
    ANCESTOR="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "${BRANCH_TIP}~${K}" 2>/dev/null || true)"
    [ -n "$ANCESTOR" ] || break     # ran off the root of history — nothing further back to try
    CAND_PID="$(git -C "$REPO_ROOT" diff "${ANCESTOR}..${BRANCH_TIP}" 2>/dev/null | git -C "$REPO_ROOT" patch-id --stable 2>/dev/null | awk '{print $1}')"
    if [ -n "$CAND_PID" ] && [ "$CAND_PID" = "$GRANT_PID" ]; then
      LANDED_CONFIRMED=1
      break
    fi
    K=$((K + 1))
  done
  if [ "$LANDED_CONFIRMED" -eq 1 ]; then
    _consume "already-landed"
    echo "land.sh: $BRANCH ($BRANCH_TIP) is already an ancestor of $MAIN_BRANCH and the grant's content is confirmed landed — idempotent retry, grant $CASE_ID consumed, exit 0"
    exit 0
  else
    echo "land.sh: $BRANCH ($BRANCH_TIP) is an ancestor of $MAIN_BRANCH, but the grant's patch-id ($GRANT_PID) could not be confirmed anywhere in its recent history (checked $CONFIRM_LOOKBACK commits back) — refusing; ask TRON (a stale/regressed branch tip must never read as a silent already-landed no-op)" >&2
    exit 1
  fi
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
