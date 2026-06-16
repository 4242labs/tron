# Scaffold Token Manifest

Canonical list of every fill-in token used in `templates/`. The scaffold procedure
(`skill-project-scaffold.md`) fills these from its locked value table; a seed is not
complete until **none of these ALL-CAPS tokens remain** in the copied tree.

## Placeholder conventions

- `<ALL_CAPS>` — **seed-time fill-in.** Set once when the project is scaffolded. Every token below is one of these. A leftover `<ALL_CAPS>` token in a seeded project is a scaffold defect.
- `<lower-case>` — **inline example / use-time placeholder** (e.g. `<slug>`, `<id>`, `<token>`, `<org>/<repo>`, `<domain>`, `<alias-1>`, `<financial-channel>`). Filled by a human or agent at point of use, not at seed time. Not tracked here.
- `{curly}` — **runtime token** resolved during execution (e.g. `{shared_knowledge_path}`, `{block-id}`, `{role}`, `{branch}`). Never a seed fill-in.

## Identity & layout

| Token | Meaning |
|:--|:--|
| `<PROJECT_NAME>` | Human-readable project name |
| `<APP_REPO_NAME>` | App repo directory/name (sibling of the meta repo) |
| `<META_REPO_NAME>` | Meta repo directory/name |
| `<WORKSPACE_PATH>` | Workspace root — **relative, never an absolute machine path** |
| `<GITHUB_ORG>` | GitHub org / owner |
| `<APP_STACK_SUMMARY>` | One-line app stack summary (e.g. "Next.js app") |

## Build & validation commands

| Token | Meaning |
|:--|:--|
| `<TYPECHECK_CMD>` · `<LINT_CMD>` · `<TEST_CMD>` · `<BUILD_CMD>` | Static-analysis / test / build commands |
| `<MIGRATION_CMD>` · `<CONTRACT_TEST_CMD>` | Conditional verifications (schema migrate, contract tests) |
| `<NODE_LTS_VERSION>` | Node version for `.nvmrc` / CI |

## Browser / evidence

| Token | Meaning |
|:--|:--|
| `<PROJECT_DEFAULT>` | Default devtools-class / automation-class MCP |
| `<PROJECT_ARTIFACT_DIR>` · `<EVIDENCE_DIR>` | Where validation evidence is written |
| `<PORT>` | Local dev server port |

## AI / LiteLLM

| Token | Meaning |
|:--|:--|
| `<AI_PROVIDER>` | AI provider name (app spec) |
| `<PRIMARY_MODEL_ID>` · `<SECONDARY_MODEL_ID>` | `provider/model-id` for each alias |
| `<MODEL_PROVIDER_API_KEY>` | Env var name holding the model provider key |
| `<MONTHLY_SPEND_CAP_USD>` | Per-user monthly spend cap |

## Services & infra

| Token | Meaning |
|:--|:--|
| `<EMAIL_PROVIDER_API_KEY>` | Env var name for the email provider key |
| `<STAGING_SUPABASE_URL>` · `<PROD_SUPABASE_URL>` | Per-env database URLs |
| `<PIPEDREAM_WORKFLOW_URL>` | Railway→Slack relay URL (if used) |
| `<DESIGN_SYSTEM_LOCAL_PATH>` | Optional offline design-system mirror (never hardcode an absolute path) |

## CI: drift, E2E, stress

| Token | Meaning |
|:--|:--|
| `<CANON_KB_REPO>` · `<CANON_SCAFFOLD_REPO>` | Canon source repos for the drift check (drop `<CANON_KB_REPO>` if no shared KB) |
| `<E2E_API_GLOB>` · `<E2E_UI_GLOB>` | Test path globs for the E2E workflow |
| `<SCENARIO_NAME>` · `<SCENARIO_FILE>` · `<STRESS_SESSION_TOKENS>` | Stress-suite step name / file / secret |
| `<INTEGRATION>` | Per-integration mock-mode flag prefix |

## Dates & misc

| Token | Meaning |
|:--|:--|
| `<SCAFFOLD_DATE>` | Date the project was scaffolded |
| `<YYYY-MM-DD>` | A date the author fills at write time (living-doc `Last Updated`) |
| `<ID>` | Generic identifier placeholder |
