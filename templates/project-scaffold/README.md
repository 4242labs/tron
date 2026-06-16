# 42Labs Project Templates

**Templates only.** The operational logic for scaffolding new projects and upgrading existing ones lives in SUPER-M.

| What | Where |
|------|-------|
| Service profile (12-Q + values) | `42hq/super-m/skills/skill-project-profile.md` |
| Scaffold procedure (zero → live project) | `42hq/super-m/skills/skill-project-scaffold.md` |
| Audit checklist (existing project gap analysis) | `42hq/super-m/skills/skill-project-audit.md` |
| Upgrade procedure (close gaps to 100%) | `42hq/super-m/skills/skill-project-upgrade.md` |
| Modes that trigger the chains | `SCAFFOLD PROJECT` and `UPGRADE PROJECT` in `super-m/super-m.md` §Session Start |

## How to use

Invoke SUPER-M and pick `SCAFFOLD PROJECT` (new) or `UPGRADE PROJECT` (existing). SUPER-M runs the profile skill, then the scaffold/audit/upgrade chain, reading template files from this directory.

## What's in `templates/`

Workspace-level, meta repo, and app repo file templates with `<PLACEHOLDER>` tokens. The scaffold skill copies these into a fresh project and fills tokens from the locked value table.

| Subdir | Holds |
|--------|-------|
| `templates/` (root) | Workspace `CLAUDE.md`, `.claude/settings.json` |
| `templates/meta/` | Meta-repo agents, skills, principles, pipeline, blocks, ref formats, lens |
| `templates/app/` | App-repo `lefthook.yml`, `.nvmrc`, `.env.example`, MCP/services setup, `.github/workflows/`, optional `infra/` |

## Versioning

Template releases are tracked in [`CHANGELOG.md`](./CHANGELOG.md). Current: **1.1.0**.

## Maintenance

Any change to a template file must be paired with a same-PR update to whichever SUPER-M skill references it, and a `CHANGELOG.md` entry. The skill is the contract; the template is the payload.
