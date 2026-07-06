#!/usr/bin/env bash
# setup-repo.sh — one-time (idempotent) per-clone bootstrap. Activates the canon trunk-root
# guard and portable-worktree settings. Run once after cloning; safe to re-run.
#   - worktree.useRelativePaths=true  -> the workspace tree is movable without `git worktree repair`
#   - the .githooks/ guard            -> direct commits/pushes to a protected branch are refused
# If lefthook owns the hooks (lefthook.yml present), it already invokes .githooks/ — we leave
# core.hooksPath alone so lefthook's other checks keep running. Otherwise we point git at .githooks.
set -euo pipefail

# No-op on build runners (this runs via `prepare` on every install) — nothing to configure there.
if [ "${CI:-}" = "true" ] || [ -n "${VERCEL:-}${GITHUB_ACTIONS:-}${NETLIFY:-}${RAILWAY_PROJECT_ID:-}${RENDER:-}" ]; then
  exit 0
fi
git rev-parse --git-dir >/dev/null 2>&1 || exit 0   # not a git context (e.g. tarball) — quiet success

cd "$(git rev-parse --show-toplevel)"

# worktree.useRelativePaths needs git >= 2.48; warn-and-skip on older git rather than erroring.
if printf '2.48.0\n%s\n' "$(git --version | awk '{print $3}')" | sort -V -C; then
  git config worktree.useRelativePaths true
else
  echo "setup-repo: git >= 2.48 needed for portable worktrees; skipping (hooks still install)." >&2
fi

if [ -d .githooks ]; then
  chmod +x .githooks/* 2>/dev/null || true
  if [ -f lefthook.yml ] || [ -f lefthook.yaml ]; then
    echo "setup-repo: lefthook present — it invokes .githooks/; core.hooksPath left unchanged."
  else
    git config core.hooksPath .githooks
    echo "setup-repo: core.hooksPath -> .githooks (trunk-root guard active)."
  fi
else
  echo "setup-repo: no .githooks/ directory — nothing to activate." >&2
fi

echo "setup-repo: done."
