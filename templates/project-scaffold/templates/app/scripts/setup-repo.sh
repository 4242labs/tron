#!/usr/bin/env sh
# Idempotent repo bootstrap — seeded by the scaffold, owned by no agent.
# Run once per clone (the app repo also auto-runs it via the package.json `prepare` script).
# Requires Git >= 2.48 for relative-path worktrees.
#
# It does two things:
#   1. Portable relative-path worktrees, so the workspace can be moved/renamed
#      without `git worktree repair`.
#   2. Activates the committed base-branch guard in .githooks/ (pre-commit + pre-push),
#      which refuses any commit or push directly on `main` / `staging`.
set -e
cd "$(git rev-parse --show-toplevel)"

git config worktree.useRelativePaths true || true
chmod +x .githooks/* 2>/dev/null || true

if [ -f lefthook.yml ]; then
  # lefthook is the hook manager; it invokes .githooks/* as pre-commit / pre-push commands.
  if command -v lefthook >/dev/null 2>&1; then
    lefthook install
  elif command -v npx >/dev/null 2>&1; then
    npx --yes lefthook install
  fi
else
  # No hook manager: activate the committed hooks path directly.
  git config core.hooksPath .githooks
fi

echo "setup-repo: relative-path worktrees on; base-branch guard active (.githooks/)."
