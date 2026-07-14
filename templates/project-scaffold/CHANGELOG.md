# Changelog — 42Labs project-scaffold

Versions the meta/app/workspace template payload. Every entry pairs with the mode
skill that reads it (`skill-project-scaffold` / `-audit` / `-upgrade`) — the skill is the
contract, the template is the payload (see `README.md → Maintenance`).

## 1.6.0 — 2026-07-14

Wires the **fleet engineering Codex** (`~/42labs/tortuga/knowledge-base/codex.md`) into the
scaffold as core canon, so every new project inherits it. `meta/principles.md` now applies the
Codex right after `principles-base.md` (change-flow & branch protection, the LGTM CI gate,
design-system compliance); the `{shared_knowledge_path}` note lists it; `AGENTS.md → Key Files`
points to it alongside `principles.md`. The Codex defers to the project's `principles.md` and
TRON's mode rulebook on conflict — no behavior change to an un-edited scaffold beyond the added
canon pointer.

## 1.5.0 — 2026-07-08

Adds **`meta/tron/roles.yaml`** (ADR-0002 Decision 4, "fleet as config"): the
project-authored binding of the fleet's roles to TRON's sealed capability-class enum
(BUILD/REVIEW/TRIAGE/CLOSE) — model, persona path, dispatch-selector, paperwork scope,
`spec_owner`/`persistent`/`close_fallback`, per role. TRON ships zero personas and
hardcodes no role name; this file (plus the existing `meta/agents/*.md` personas) is the
one and only fleet-composition source the engine reads. Ships pre-populated with the
scaffold's trivial default fleet (`engineer` / `reviewer-code` / `architect`) so an
un-edited scaffold boots exactly as before. `meta/blocks/block-template.md` gains the
two OPTIONAL block headers `**Role:**` / `**Tags:**` feeding the same selector — absent
on (nearly) every block, meaning "default binding match" (unchanged behavior).

## 1.4.0 — 2026-07-01

Renames the block header field `**Merge:** self | needs-user` → `**Merge approval:** auto |
needs-user` (`meta/blocks/block-template.md`). `self` read as an instruction for the *engineer* to
self-merge — it was never that; it meant the supervising process's gate merges without a human.
Renamed to remove the ambiguity; parser key `merge` → `merge_approval`, default value `self` →
`auto`. `needs-user` is unchanged. Additive to the parsed pipeline row shape only (`merge` →
`merge_approval`), no other project-facing behavior change.

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
- **Contract sync**: `skill-project-audit`, `skill-project-upgrade`, and `flynn.md → C3`
  updated to validate the above (the maintenance rule — skill follows payload).

## 1.0.0 — baseline

The two-repo (meta + app) template as it stood before 1.1.0: agents, skills, principles,
pipeline + blocks, ref formats, CI/hooks, MCP/services setup, portable-worktree bootstrap.
