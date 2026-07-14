---
name: tron-branching
description: Worktree paths, branch names, and the session-end git protocol. Shared law for every TRON mode; each mode contributes only its slug.
---

# Branching & worktrees

Shared law. Every mode obeys it — there is no meta-agent exemption, and the rule TRON audits on
other agents is the rule TRON follows. Load this whenever the session will produce a commit; skip it
entirely when it won't. **Advice, research, and a question answered need no branch and no worktree.
Do not create ceremony for a conversation.**

---

## Before the first edit

- [ ] **Worktree, not the main checkout.** Editing from the main checkout → stop and create one.
      - multi-repo project: `{project}/worktrees/{repo}--{branch}/`
      - single-repo / canon: `{repo}/.worktrees/{branch}/`
- [ ] **Branch name:** `chore/{mode}-YYYYMMDD-{slug}` — the mode's own prefix, today's date, a slug.

      | Mode | Prefix | Slug |
      |:--|:--|:--|
      | FLYNN | `chore/flynn-` | fixed vocabulary — `flynn.md` §Operating Rules |
      | ALFREDO | `chore/alfredo-` | free-form kebab-case; the work is ad-hoc, so the slug is too |
      | CLU | — | CLU commits nothing. Its workers branch under the target repo's conventions. |
      | SCAFFOLD | — | SCAFFOLD creates repos; it does not branch inside them. |
      | KONDO | — | KONDO commits inside the project it tidies, under *that* repo's conventions: `chore/upgrade-{area}` for what it adds, `chore/kondo-discard-{area}` for what it removes — never the same branch for both. |

- [ ] **The target repo's rules win.** When the commits land in someone else's repo — a rollout, a
      retrofit, an ad-hoc fix in an app repo — follow *that repo's* conventions (`fix/`, `feat/`,
      `chore/<topic>-<YYMMDD>`), not TRON's. TRON's prefix governs TRON's own canon-side commits.
- [ ] **One session, one branch.** If the operator pivots to unrelated work, that's a new branch.
- [ ] **Check for strays.** `git branch --list 'chore/{mode}-*'` and
      `git branch -r --list 'origin/chore/{mode}-*'` — anything left from a previous session gets
      surfaced to the operator before new work starts.

---

## Session end — commit, push, land, clean

Never commit on the integration branch. Never push direct to it.

**1. Commit and push**

```
git add -A && git commit -m "{conventional message}"
git push -u origin <branch>
```

**2. Land it — by repo class** (`.repo-class` in the repo root)

| Class | Protocol |
|:--|:--|
| `app` | `gh pr create` against the integration branch → `gh pr checks {PR} --watch` to green → **hand the operator the PR link.** They click. Never merge, never arm auto-merge. |
| `canon` · `meta` | No PR. **Rebase first, then fast-forward:** `git fetch origin && git rebase origin/main` on the feature branch — this is what makes the FF possible at all. Then from the main checkout: `git checkout main && git pull --ff-only && git merge --ff-only <branch> && git push origin main`. Push the feature branch too (force-with-lease after the rebase), so the pre-push reachability check has a target ref. |

**If `--ff-only` is refused, `main` moved under you.** Do not reach for `--no-ff`, and never
`--force` over `main`. Go back, rebase the feature branch onto the new `origin/main`, re-run the
local validation (the rebase may have silently broken it), and try the fast-forward again.

**3. Clean up** — only after the merge actually lands

- [ ] `git branch -d <branch>` and `git push origin --delete <branch>`
- [ ] `git worktree remove <path>` (or `git worktree prune` if the directory is already gone)
- [ ] Verify: `git branch --list 'chore/{mode}-*'` and `git branch -r --list 'origin/chore/{mode}-*'`
      both empty, and `git worktree list` shows no leftover TRON worktree

Anything left behind is a finding — log it, don't hide it. A squash-merged branch will not show up
under `git branch --merged`; check the PR state, not the merge base, before calling it stale.

---

## The one exception: repo birth

SCAFFOLD pushes the first commit straight to `main` / `staging` when it creates a repo
(`scaffold/skills/skill-project-scaffold.md` §9). That is not a violation — at repo birth there is no
integration branch to branch *from* and no PR to open *against*. The rule binds from the second
commit onward, and SCAFFOLD ships the hooks that enforce it.

## Enforcement

`.repo-class` plus the tracked `.githooks/` pre-commit and pre-push hooks structurally enforce
worktree-mandatory and no-direct-to-main on canon, meta, and app repos. TRON still self-checks,
because hooks can be bypassed with `--no-verify`.

End of line.
