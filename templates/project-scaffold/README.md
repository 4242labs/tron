# 42Labs Project Templates

**Templates only.** The operational logic for scaffolding new projects and upgrading existing ones lives in SUPER-M.

| What | Where |
|------|-------|
| Service profile (12-Q + values) | _(shared-KB path TBD — see TD-10)_ |
| Scaffold procedure (zero → live project) | _(shared-KB path TBD — see TD-10)_ |
| Audit checklist (existing project gap analysis) | _(shared-KB path TBD — see TD-10)_ |
| Upgrade procedure (close gaps to 100%) | _(shared-KB path TBD — see TD-10)_ |
| Modes that trigger the chains | `SCAFFOLD PROJECT` and `UPGRADE PROJECT` in `super-m/super-m.md` §Session Start |

## How to use

Invoke SUPER-M and pick `SCAFFOLD PROJECT` (new) or `UPGRADE PROJECT` (existing). SUPER-M runs the profile skill, then the scaffold/audit/upgrade chain, reading template files from this directory.

## What's in `templates/`

Workspace-level, meta repo, and app repo file templates with `<PLACEHOLDER>` tokens. The scaffold skill copies these into a fresh project and fills tokens from the locked value table. The canonical list of every fill-in token (and the `<...>` / `{...}` conventions) is [`tokens.md`](./tokens.md) — a seed is not complete until no `<ALL_CAPS>` token remains in the copied tree.

| Subdir | Holds |
|--------|-------|
| `templates/` (root) | Workspace `AGENTS.md`, `.claude/settings.json` |
| `templates/meta/` | Meta-repo agents, skills, principles, pipeline, blocks, ref formats, lens |
| `templates/app/` | App-repo `lefthook.yml`, `.nvmrc`, `.env.example`, MCP/services setup, `.github/workflows/`, optional `infra/` |

## Versioning

Template releases are tracked in [`CHANGELOG.md`](./CHANGELOG.md). Current: **1.2.0**.

## Maintenance

Any change to a template file must be paired with a same-PR update to whichever SUPER-M skill references it, and a `CHANGELOG.md` entry. The skill is the contract; the template is the payload.
