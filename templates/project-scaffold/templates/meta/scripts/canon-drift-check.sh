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
# Usage: canon-drift-check.sh <meta-repo-path> <canon-repo-path>
# Output: lines starting with "OK:" or "DRIFT:" — the workflow greps for "DRIFT:".
# Requires the canon checkout to have FULL history (workflow: fetch-depth: 0).
#
# Schema reference: knowledge-base/skills/REGISTRY-frontmatter.md

set -euo pipefail

META_PATH="${1:?meta repo path required}"
CANON_PATH="${2:?canon repo path required}"

CANON_HEAD=$(cd "$CANON_PATH" && git rev-parse --short=7 HEAD)

echo "Canon HEAD: $CANON_HEAD"
echo "Meta path:  $META_PATH"
echo "(drift is computed per-file: a skill drifts only when its canonical counterpart changed since canon_version)"
echo "---"

# Canonical search roots, in priority order.
CANON_SKILL_DIRS=(
  "new-project-template/templates/meta/skills"
  "knowledge-base/skills"
)

# Iterate skill files only — REGISTRY-frontmatter.md scope is skill files, not agents.
find "$META_PATH/skills" -maxdepth 2 -name "*.md" -type f 2>/dev/null | sort | while read -r file; do
  rel_path="${file#"$META_PATH/"}"

  # Extract frontmatter block (between first two --- lines)
  if ! awk 'NR==1 && /^---$/ {flag=1; next} flag && /^---$/ {exit} flag' "$file" > /tmp/frontmatter.yml 2>/dev/null; then
    continue
  fi

  if [ ! -s /tmp/frontmatter.yml ]; then
    # No frontmatter → not a tracked canon skill; ignore.
    continue
  fi

  source_field=$(grep -E '^source:[[:space:]]*' /tmp/frontmatter.yml | sed -E 's/^source:[[:space:]]*//; s/[[:space:]]+$//' | head -1 || true)
  canon_version_field=$(grep -E '^canon_version:[[:space:]]*' /tmp/frontmatter.yml | sed -E 's/^canon_version:[[:space:]]*//; s/[[:space:]]+$//' | head -1 || true)
  name_field=$(grep -E '^name:[[:space:]]*' /tmp/frontmatter.yml | sed -E 's/^name:[[:space:]]*//; s/[[:space:]]+$//' | head -1 || true)

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

  # Locate the canonical counterpart by basename.
  base=$(basename "$file")
  canonical=""
  for dir in "${CANON_SKILL_DIRS[@]}"; do
    if [ -f "$CANON_PATH/$dir/$base" ]; then
      canonical="$dir/$base"
      break
    fi
  done

  if [ -z "$canonical" ]; then
    echo "DRIFT: $rel_path — source: canon but no canonical counterpart found in canon (${CANON_SKILL_DIRS[*]})"
    continue
  fi

  # The pinned version must exist in canon history (needs fetch-depth: 0).
  if ! (cd "$CANON_PATH" && git cat-file -e "${canon_version_field}^{commit}" 2>/dev/null); then
    echo "DRIFT: $rel_path — canon_version $canon_version_field not found in canon history (ensure workflow uses fetch-depth: 0)"
    continue
  fi

  # Per-file drift: did the canonical file change AFTER the pinned version?
  changes=$(cd "$CANON_PATH" && git rev-list --count "${canon_version_field}..HEAD" -- "$canonical" 2>/dev/null || echo "ERR")
  if [ "$changes" = "ERR" ]; then
    echo "DRIFT: $rel_path — could not compute per-file history for $canonical"
  elif [ "$changes" = "0" ]; then
    echo "OK: $rel_path — $canonical unchanged since canon_version $canon_version_field"
  else
    latest=$(cd "$CANON_PATH" && git log -1 --format=%h -- "$canonical")
    echo "DRIFT: $rel_path — $canonical changed since $canon_version_field ($changes commit(s)); bump canon_version to $latest"
  fi
done

rm -f /tmp/frontmatter.yml
