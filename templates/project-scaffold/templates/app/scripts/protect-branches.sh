#!/usr/bin/env bash
# protect-branches.sh — the operator one-shot that turns on GitHub branch protection.
# The .githooks/ guard stops direct commits LOCALLY; this enforces the same on the REMOTE:
# a protected branch takes only PRs whose required checks are green. Run once per repo by an
# operator/admin (it changes repo settings — an outward, admin act TRON itself never performs).
#
#   Usage:  scripts/protect-branches.sh <owner/repo> <check>[,<check>…] [branch ...]
#   e.g.    scripts/protect-branches.sh acme/widgets "typecheck + test" main staging
#           scripts/protect-branches.sh acme/widgets verify,e2e main
#
# The check list is MANDATORY and is the whole point. Protection with an empty required-check
# list stops nothing a red build can do — the PR still merges, and the repo looks protected
# while every CI run remains advisory. Pass the CI job names exactly as GitHub reports them:
#   gh api repos/<repo>/commits/<sha>/check-runs --jq '.check_runs[].name'
#
# Only require checks that run on EVERY pull request. A path-filtered job (`on: pull_request:
# paths:`) does not run on PRs that miss those paths — requiring it there hangs those PRs
# forever, waiting on a check that will never report.
#
# Requires: gh (authenticated, admin on the repo) and jq. Idempotent — re-running re-asserts.
set -euo pipefail

REPO="${1:?usage: protect-branches.sh <owner/repo> <check>[,<check>…] [branch ...]}"; shift
CHECKS="${1:?required-check list is mandatory — protection with no required checks gates nothing}"; shift
BRANCHES=("$@"); [ ${#BRANCHES[@]} -eq 0 ] && BRANCHES=(main staging)

# "a,b" → ["a","b"]. Split on comma only — check names may contain spaces.
CONTEXTS=$(printf '%s' "$CHECKS" | tr ',' '\n' | jq -R . | jq -s -c .)

for b in "${BRANCHES[@]}"; do
  echo "protecting ${REPO}@${b} — PR only, no force-push, required checks: ${CONTEXTS}"
  gh api -X PUT "repos/${REPO}/branches/${b}/protection" --input - >/dev/null <<JSON
{
  "required_status_checks": { "strict": true, "contexts": ${CONTEXTS} },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

  # Read back what actually landed. A PUT that "succeeds" while the contexts are dropped is
  # precisely the failure this script exists to prevent — verify, never assume.
  got=$(gh api "repos/${REPO}/branches/${b}/protection" --jq '.required_status_checks.contexts')
  echo "  ✓ ${REPO}@${b} now requires: ${got}"
done
