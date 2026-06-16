#!/usr/bin/env bash
# canon-drift-check.sh
#
# Compares project skills marked `source: canon` against their CANONICAL COUNTERPART
# in the canon repo — per file, not against global canon HEAD. A skill drifts only
# when its own canonical source changed after the pinned `canon_version` (so unrelated
# canon commits no longer raise false positives).
#
# Skips skills marked `source: project` (legitimate project customization).
#
# Usage: canon-drift-check.sh <meta-repo-path> <canon-root>...
#   <canon-root> = "REPO_PATH::SKILL_SUBDIR" — a canon checkout plus the skills dir
#   within it. Pass one root per canon source; roots are tried in the order given and
#   the first basename match wins. Canonical skills may live across more than one repo, e.g.:
#     "<kb-checkout>::knowledge-base/skills"
#     "<scaffold-checkout>::templates/project-scaffold/templates/meta/skills"
#   so each root carries its own repo — per-file git history runs in the repo that
#   actually owns the matched counterpart, not a single global canon checkout.
#
# Output: lines starting with "OK:" or "DRIFT:" — the workflow greps for "DRIFT:".
# Requires each canon checkout to have FULL history (workflow: fetch-depth: 0).
#
# Schema reference: knowledge-base/skills/REGISTRY-frontmatter.md

set -euo pipefail

META_PATH="${1:?meta repo path required}"
shift
if [ "$#" -eq 0 ]; then
  echo "ERROR: at least one canon root required (REPO_PATH::SKILL_SUBDIR)" >&2
  exit 2
fi
# Canonical search roots, in priority order. Each entry is "REPO_PATH::SKILL_SUBDIR".
CANON_ROOTS=("$@")

# Per-run temp file for frontmatter extraction (no fixed /tmp path — avoids
# concurrent-run collision and keeps work inside the runner's temp dir).
FM="$(mktemp)"
trap 'rm -f "$FM"' EXIT

echo "Meta path:  $META_PATH"
for root in "${CANON_ROOTS[@]}"; do
  repo="${root%%::*}"; sub="${root#*::}"
  head=$(cd "$repo" && git rev-parse --short=7 HEAD)
  echo "Canon root: $repo ($sub) @ $head"
done
echo "(drift is computed per-file: a skill drifts only when its canonical counterpart changed since canon_version)"
echo "---"

# Iterate skill files only — REGISTRY-frontmatter.md scope is skill files, not agents.
find "$META_PATH/skills" -maxdepth 2 -name "*.md" -type f 2>/dev/null | sort | while read -r file; do
  rel_path="${file#"$META_PATH/"}"

  # Extract frontmatter block (between first two --- lines)
  if ! awk 'NR==1 && /^---$/ {flag=1; next} flag && /^---$/ {exit} flag' "$file" > "$FM" 2>/dev/null; then
    continue
  fi

  if [ ! -s "$FM" ]; then
    # No frontmatter → not a tracked canon skill; ignore.
    continue
  fi

  source_field=$(grep -E '^source:[[:space:]]*' "$FM" | sed -E 's/^source:[[:space:]]*//; s/[[:space:]]+$//' | head -1 || true)
  canon_version_field=$(grep -E '^canon_version:[[:space:]]*' "$FM" | sed -E 's/^canon_version:[[:space:]]*//; s/[[:space:]]+$//' | head -1 || true)
  name_field=$(grep -E '^name:[[:space:]]*' "$FM" | sed -E 's/^name:[[:space:]]*//; s/[[:space:]]+$//' | head -1 || true)

  # Skip non-canon skills
  if [ "$source_field" != "canon" ]; then
    continue
  fi

  # Validate name matches basename
  expected_name=$(basename "$file" .md)
  if [ "$name_field" != "$expected_name" ]; then
    echo "DRIFT: $rel_path — name mismatch (expected $expected_name, got $name_field)"
    continue
  fi

  if [ -z "$canon_version_field" ]; then
    echo "DRIFT: $rel_path — source: canon but canon_version field missing"
    continue
  fi

  if [ "$canon_version_field" = "HEAD" ]; then
    echo "OK: $rel_path — canon_version: HEAD (always current)"
    continue
  fi

  # Locate the canonical counterpart by basename across all canon roots.
  # Track the owning repo so git history runs where the file actually lives.
  base=$(basename "$file")
  canonical=""; canon_repo=""
  for root in "${CANON_ROOTS[@]}"; do
    repo="${root%%::*}"; sub="${root#*::}"
    if [ -f "$repo/$sub/$base" ]; then
      canon_repo="$repo"; canonical="$sub/$base"
      break
    fi
  done

  if [ -z "$canonical" ]; then
    echo "DRIFT: $rel_path — source: canon but no canonical counterpart found in any canon root (${CANON_ROOTS[*]})"
    continue
  fi

  # The pinned version must exist in the owning repo's history (needs fetch-depth: 0).
  if ! (cd "$canon_repo" && git cat-file -e "${canon_version_field}^{commit}" 2>/dev/null); then
    echo "DRIFT: $rel_path — canon_version $canon_version_field not found in $canon_repo history (ensure workflow uses fetch-depth: 0)"
    continue
  fi

  # Per-file drift: did the canonical file change AFTER the pinned version?
  changes=$(cd "$canon_repo" && git rev-list --count "${canon_version_field}..HEAD" -- "$canonical" 2>/dev/null || echo "ERR")
  if [ "$changes" = "ERR" ]; then
    echo "DRIFT: $rel_path — could not compute per-file history for $canonical in $canon_repo"
  elif [ "$changes" = "0" ]; then
    echo "OK: $rel_path — $canonical unchanged since canon_version $canon_version_field"
  else
    latest=$(cd "$canon_repo" && git log -1 --format=%h -- "$canonical")
    echo "DRIFT: $rel_path — $canonical changed since $canon_version_field ($changes commit(s)); bump canon_version to $latest"
  fi
done
