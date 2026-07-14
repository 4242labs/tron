# Skill: Project Discard

**Purpose:** The inverse of the audit. `skill-project-audit.md` asks *what does canon require that this
project is missing?* This skill asks *what does this project carry that canon never asked for, and
nothing uses?* — and proposes removing it.

**Prerequisite:** `skill-project-profile.md` has run and locked `{profile, values}`. The profile is what
makes this pass safe: a `staging-db.yml` is canon in a project with a database and cruft in one without.

**Output:** Discard Report in the format at the end of this skill. Presented to the operator **together
with** the Gap Report. Removals are executed by `skill-project-upgrade.md` — never by this skill.

---

## The Contract

Read `kondo.md → The Discard Contract` before starting. In short:

1. Per-item approval. Never batch.
2. Propose only what is **provably** dead. Suspicion goes in the report as *uncertain*, never as a proposal.
3. Never touch work in flight — an open PR, or a commit in the last 7 days, means live.
4. Never touch secrets, application source, tests, or git history.
5. Removals ship through a branch and a PR like any other change.

**The default verdict is KEEP.** A thing has to earn its way onto the discard list; it does not have to
earn its way off. When the evidence is thin, the item is uncertain, not dead.

---

## Evidence Standard

An item may be proposed for **DISCARD** only when all three hold, and the report shows the check for each:

| Test | How to establish it |
|:--|:--|
| **Canon doesn't ask for it** | It is not in the scaffold kit (`templates/project-scaffold/templates/`), not in the audit checklist, and not required by a service in the locked profile |
| **Nothing references it** | Grep the whole workspace — both repos, docs, CI, scripts, `package.json`, agent docs, skills. Zero live references. Cite the command you ran |
| **It isn't live** | No open PR, no commit in the last 7 days, not an active session's worktree, not claimed by the operator when asked |

Fail any one → the item is **UNCERTAIN**. Report it with what you found and let the operator rule.
Never "clean up while I'm in there."

---

## Sweep 1 — Git hygiene

- [ ] **Merged branches.** Local and remote branches whose commits are already reachable from the
      integration branch (`git branch --merged origin/staging`). Rebase-to-empty counts as merged —
      verify with `git rebase origin/staging` on a scratch copy before calling it dead
- [ ] **Abandoned branches.** Remote-tracking `[gone]`, no open PR, no commit in the last 7 days
- [ ] **Orphan worktrees.** Registered worktrees whose branch is merged or gone, and whose directory has
      no uncommitted work (`git worktree list` + `git status` in each). Prune registrations too
      (`git worktree prune`)
- [ ] **Worktrees outside the canonical base.** Live work in a legacy path is **not** discard — it's a
      relocation, and it goes in the Gap Report, not here

> Anything with an open PR or recent activity is another agent's session. Leave it, and name it in the
> report as **left alone: in flight**.

---

## Sweep 2 — Canon leftovers

Artifacts the canon once asked for and no longer does. These are the highest-confidence discards —
canon itself is the evidence.

- [ ] `blocks/<id>/completion-report.md` — superseded: the Completion Report lives inside the engineer's
      session log. Files on blocks created **on or after 2026-05-13** are drift; earlier ones are
      historical and exempt
- [ ] `blocks/<id>/critic-verdict.md` — same rule, same date, verdict lives in the reviewer's session log
- [ ] `blocks/<id>/screenshots/` — the whole per-block subdirectory is deprecated; validation artifacts
      live at `{meta}/artifacts/{YYYYMMDD}/{session}/`, with block traceability in the **filename**
- [ ] Any other `blocks/<id>/` subdirectory on a post-2026-05-13 block — its existence is itself the finding
- [ ] Tombstoned or renamed skills still present under their old name, with nothing pointing at them
- [ ] A localized `## Shared Knowledge Base` section in `principles.md` — canon is inherited, not copied

Do not delete a historical artifact to make a checklist tidy. History is not cruft.

---

## Sweep 3 — Dead documentation

- [ ] **Superseded docs.** A doc whose subject moved elsewhere and which nothing now links to (an old
      backlog or workflow doc after the work moved to the tracker). Grep for inbound links before proposing
- [ ] **Docs that describe a system that no longer exists** — a setup guide for a service the profile
      doesn't list, a README for a directory that was deleted
- [ ] **Duplicate sources of truth.** The same rule stated in two places that can now disagree. This is a
      **REPLACE**, not a discard: keep one, and make the other a pointer. Route it to the Gap Report
- [ ] **Maintainer-only docs in a published root.** Not a discard — a **relocation** into an excluded
      directory. Route it to the Gap Report, and flag it loudly if the site publishes it today

---

## Sweep 4 — Contaminated and duplicated agent content

- [ ] **Sibling-project contamination.** A `source: project` skill whose body is domain-specific to a
      *different* 42Labs project — the scaffolder copied it and never genericized it. Detect by scanning
      skill bodies for another project's vocabulary. Remediation is **genericize against the kit**, not
      delete: route to the Gap Report unless the skill has no purpose here at all
- [ ] **Canon duplicated locally.** A `source: canon` skill rewritten in place instead of inherited.
      Replace with the inheritance pointer
- [ ] **Agent docs for agents that don't exist** — a persona nothing dispatches and no pipeline names
- [ ] **Skills nothing routes to.** No agent doc, no skill chain, and no session-start routing table
      mentions it

---

## Sweep 5 — Service leftovers

Every service the operator did *not* confirm in the profile, but whose wiring is still in the repo:

- [ ] CI workflows for it (`staging-db.yml`, `deploy-notify.yml`, …)
- [ ] Its env vars in `.env.example` — and its keys in the CI secret list
- [ ] Its setup sections in `services-setup.md` / `mcp-setup.md`
- [ ] Its MCP entries in `.mcp.json` / `.claude/settings.json`
- [ ] Its dependencies in `package.json` — verify with a source-wide grep for the import before proposing;
      a transitive or build-time dependency is not an unused one

A service that is *planned but not yet wired* is not a leftover. Ask before proposing.

---

## Sweep 6 — Filesystem junk

- [ ] Committed `.DS_Store`, editor swap files, `*.orig` / `*.rej` merge residue
- [ ] Committed build output, coverage reports, or `node_modules` — and the missing `.gitignore` line that
      let them in (the ignore line is a **Gap**, the committed files are a **discard**)
- [ ] Scratch, temp, and one-off script files at a repo root with no reference anywhere
- [ ] Empty directories left by a move, and `.gitkeep` files holding open a directory nothing writes to

---

## What is Never Proposed

- Anything under a `.env*` name, any credential, any token — **out of scope entirely**
- Application source and tests. Dead app code is an engineering concern, not a workflow one
- Anything requiring history rewrite (`filter-repo`, force-push, `reflog` surgery)
- A file whose only evidence of death is "I don't recognise it"
- Another agent's in-flight branch, worktree, or PR
- Historical logs, archived pipelines, past artifacts — a record you don't need is still a record

---

## Discard Report Format

```
## Discard Report — <Project Name> — <Date>

### Proposed for removal

| # | Item | Why canon doesn't want it | Evidence it's dead | Risk |
|---|------|---------------------------|--------------------|------|
| 1 | `.github/workflows/staging-db.yml` | No database in the confirmed profile | Grep: no `SUPABASE_*` in app or CI. Workflow has never run | Low |
| 2 | `chore/old-migration` (local + remote) | — | Rebases to empty on staging; no open PR; last commit 94 days ago | Low |
| 3 | `blocks/01-12/completion-report.md` | Superseded: report lives in the engineer's session log (block created 2026-06-02) | — | Low |

### Uncertain — operator rules

| # | Item | What I found | Why I stopped short |
|---|------|--------------|---------------------|
| 1 | `docs/legacy-import.md` | Nothing links to it; describes a flow the app no longer has | Could be a deliberate record of the old flow — I can't tell |

### Left alone — in flight

| # | Item | Why |
|---|------|-----|
| 1 | worktree `app--feat/checkout` | Open PR #212, commit 2 days ago |

### Summary
- Proposed: N items
- Uncertain: N items
- Left alone: N items
```

Present it beside the Gap Report. Take a ruling **per numbered line** — an "approve the report" is not
a ruling, and must be turned back into per-item answers before anything is removed.

Approved lines go to `skill-project-upgrade.md → Removals`. Rejected lines are recorded in the report as
rejected, so the next KONDO run doesn't re-propose them.
