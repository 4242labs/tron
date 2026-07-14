# 42Labs Project Templates

**Templates only.** This directory is payload — the procedures that read it live in TRON's modes.

| What | Where |
|------|-------|
| Profile + scaffold a new project | `modes/scaffold/skills/` — booted with `/tron-scaffold` |
| Profile + audit + discard + upgrade an existing project | `modes/kondo/skills/` — booted with `/tron-kondo` |

## How to use

Run `/tron-scaffold` for a new project, `/tron-kondo` for an existing one. The mode runs its profile skill, then the scaffold or audit/discard/upgrade chain, reading every template file from this directory.

## What's in `templates/`

Workspace-level, meta repo, and app repo file templates with `<PLACEHOLDER>` tokens. The scaffold skill copies these into a fresh project and fills tokens from the locked value table. The canonical list of every fill-in token (and the `<...>` / `{...}` conventions) is [`tokens.md`](./tokens.md) — a seed is not complete until no `<ALL_CAPS>` token remains in the copied tree.

| Subdir | Holds |
|--------|-------|
| `templates/` (root) | Workspace `AGENTS.md`, `.claude/settings.json` |
| `templates/meta/` | Meta-repo agents, skills, principles, pipeline, blocks, ref formats, lens |
| `templates/app/` | App-repo `lefthook.yml`, `.nvmrc`, `.env.example`, MCP/services setup, `.github/workflows/`, optional `infra/` |

## Versioning

Template releases are tracked in [`CHANGELOG.md`](./CHANGELOG.md). Current: **1.5.0**.

## Maintenance

Any change to a template file must be paired with a same-PR update to whichever mode skill references it, and a `CHANGELOG.md` entry. The skill is the contract; the template is the payload.
