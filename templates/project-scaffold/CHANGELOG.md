# Changelog — 42Labs project-scaffold

Versions the meta/app/workspace template payload. Every entry pairs with the SUPER-M
skill that reads it (`skill-project-scaffold` / `-audit` / `-upgrade`) — the skill is the
contract, the template is the payload (see `README.md → Maintenance`).

## 1.3.0 — 2026-06-30

Adopts the model-agnostic **`AGENTS.md`** standard in place of `CLAUDE.md` — canon carries no
host-runtime name, and any assistant that reads `AGENTS.md` works out of the box.

- **Renamed** the three payload agent-doc templates `CLAUDE.md` → `AGENTS.md` (workspace root,
  `meta/`, `app/app/`) and repointed every reference to `app/AGENTS.md` across `principles.md`,
  `agents/engineer.md`, and the `skill-review-code` / `skill-review-cycle` / `skill-session-end-*`
  staleness tables.
- **Added `meta/.gitignore`** ignoring a stray `CLAUDE.md` so a host-runtime working file is never
  committed. (The app repo's `.gitignore` — generated at scaffold time — should ignore `CLAUDE.md`
  too; folded into the scaffolder skill, see pipeline P-06.)

## 1.2.0 — 2026-06-06

Realigns the workflow for supervisor-driven delivery (where a deterministic supervisor
such as TRON drives the pipeline) and scaffolds the block archive. The canonical source
of these rules is `knowledge-base/principles-base.md §12`; the template mirrors it.

- **Review ownership moved to the supervisor.** Reviewers (code, security, data) are no
  longer fired by CI or pulled in by the engineer at session-end. They are dispatched by
  the supervising process on a per-type **review cadence**. The Reviewer-trigger map's
  CI/PR-event mechanism is retired. Touches `principles.md`, `agents/engineer.md`,
  `skills/skill-session-end-engineer.md`, `blocks/block-template.md`, `templates/CLAUDE.md`.
  Review is no longer a per-block completion gate.
- **Merge unblocked for agents, but monitored.** The old "user clicks Merge / only open
  PRs" rule is replaced: the **agent merges its own PR** once merge is authorized (by the
  user, or by the supervising process per its merge policy — the supervisor only
  authorizes, it never touches the repo). Auto-merge stays banned; the agent monitors the
  merge through to a verified deploy. A merged change that is not deploy-verified is **not
  done**. Touches `principles.md`, `agents/engineer.md`, `skills/skill-session-end-{engineer,
  architect,data-architect}.md`, `skills/skill-worktree-and-branching.md`,
  `skills/skill-review-cycle.md`, `templates/app/app/CLAUDE.md`, `blocks/block-template.md`.
- **Deploy-gated done made explicit at every gate.** Status flips to ✅ only after merge +
  post-merge re-validation + (where the block declares a deploy check) a clean, verified
  deploy. Touches `agents/engineer.md`, `skills/skill-validate.md`,
  `skills/skill-session-end-engineer.md`, `blocks/block-template.md`.
- **New skill — `skills/skill-block-forward-review.md`.** Architect pass dispatched by the
  supervising process when a block lands done: reads the finished block's logs, harvests
  learnings/drift, and adjusts the upcoming block files + pipeline rows (via PR, no status
  flips). Registered in `principles.md` and `templates/CLAUDE.md`.
- **`skill-review-cycle.md` clarified** as the standalone, user-initiated phase-boundary
  sweep — distinct from the supervisor's review cadence and from forward review.
- **Block archive dir** (`meta/blocks/archive/`): the destination for a block file once
  its row is done — keeps the live `blocks/` listing to in-flight work. Shipped as an empty
  `.gitkeep` dir (distinct from `pipeline-archive.md`, which holds retired pipeline rows).

## 1.1.0 — 2026-06-06

Tighter pipeline hygiene and an explicit deploy gate. All additive and inert — a project
that ignores the new fields behaves exactly as before.

- **Pipeline format contract** (`meta/pipeline.md`): states the shape the doc already
  follows — phases are `### Phase N:` headers; tables are `ID | Task | Status | Notes`;
  the Status cell is exactly one emoji from the indicator set; a row with a block file
  names it in Notes as `Block `blocks/<id>.md``. Makes the living doc safe for a
  deterministic (non-LLM) reader without constraining a human author.
- **Block header fields** (`meta/blocks/block-template.md`): `**Merge:** self | needs-user`
  (default `self`; stamp `needs-user` for the genuinely risky blocks a human must sign off)
  and `**Deploy:** none | check` (optional per-block override of the project deploy check).
- **Definition-of-done deploy gate** (`meta/principles.md`): made explicit that
  PR-merged ≠ done — when a block declares a deploy check (its `Deploy:` field, or the
  `context.md → Deploy` default) the change must deploy clean and verify post-deploy
  before the block is done; a failed deploy is not-done and must be fixed.
- **Project deploy default** (`meta/context.md`): a `## Deploy` section (Enabled +
  Success check), inherited by blocks and overridable per block.
- **Contract sync**: `skill-project-audit`, `skill-project-upgrade`, and `super-m.md → C3`
  updated to validate the above (the maintenance rule — skill follows payload).

## 1.0.0 — baseline

The two-repo (meta + app) template as it stood before 1.1.0: agents, skills, principles,
pipeline + blocks, ref formats, CI/hooks, MCP/services setup, portable-worktree bootstrap.
