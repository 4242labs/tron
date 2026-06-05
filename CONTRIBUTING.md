# Contributing to TRON

Welcome. TRON is a deterministic supervisor that builds software from specs — a small, sharp canon
repo. Contributions are genuinely appreciated, and most of them extend the canon itself. This guide
gets you from clone to merged PR.

## Quick start

```bash
git clone https://github.com/42piratas/tron.git
cd tron
./tron validate      # blueprint-lint over the grammar + event table + knobs (must be green)
./tron doctor        # environment check + lint
```

There's no build step — the engine is plain Python (`python3`), the connectors are POSIX shell.
`./tron validate` is the gate: a malformed flow fails here, not at runtime.

## What you can contribute

| Surface | Where | Adds |
|:--|:--|:--|
| **Worker skill** | `skills/<role>.md` | how an agent behaves (a new role, or a sharper method) |
| **Reviewer lens** | `workflow.yaml › cadence` + a reviewer skill | a review pass (security, data, a11y, …) |
| **Protocol** | `protocols/<name>.md` | a lifecycle flow (bootup / session-end / …) |
| **Engine** | `engine/` | the dispatch loop, selector, judgment, lint — keep it deterministic |
| **Copy** | `messages.yaml` | TRON's voice (dark, dry, sardonic; never name the host runtime) |
| **Docs** | `README.md`, the [wiki](https://github.com/42piratas/tron/wiki), `contracts/` | guides, references |

The behaviour itself — the trigger grammar and the event table — is canon and intentionally stable.
A genuinely new *shape* of control is a bigger conversation: open an issue first.

## Ground rules

- **Canon purity.** This repo carries zero project- or machine-specific traces. No absolute paths,
  no host repo assumptions. Per-project values live only in a seeded instance.
- **Blueprint first, model second.** TRON's founding principle. Flow is decided by code and a closed
  grammar — the blueprint — never by an LLM. The model is second: only the two bounded, schema-checked
  judgments. Keep contributions on that side of the line.
- **Never name the host runtime** in any TRON-facing copy (operator/worker/seeder text).
- **Lint stays green.** `./tron validate` must pass; the closed vocabulary stays closed.

## Branching + PR workflow

1. Branch off `main` (`feat/…`, `fix/…`, `docs/…`). No direct commits to `main`.
2. Make the change; run `./tron validate` (and `./tron doctor`).
3. Open a PR into `main`. Keep it focused; describe what and why.
4. CI green → merge. Squash or merge — keep history readable.

Found a bug or have an idea? [Open an issue](https://github.com/42piratas/tron/issues/new/choose).
We're glad you're here.
