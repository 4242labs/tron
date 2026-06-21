# BPMN diagram — source of truth & publishing

The interactive BPMN flow lives **here** and is **published** to the public site. Two files, one owner.

## Source of truth (edit here)

- **`docs/workflow.html`** — the core map + every drill-down sub-process (one generator).
- **`docs/flow-description.html`** — the per-node descriptions / annotations (loaded by `workflow.html`'s
  annotations panel).

These two are the **single source of truth**. The companion docs that govern them live in `tron-meta/`:
`flow-diagram-guidelines.md` (layout rules), `backlog.md` (decisions/status), `context-revamp.md` (agent
orientation). Read those before changing the flow.

## Published copy (do NOT edit)

The site serves a **generated copy** at **`tron.42labs.io/workflow/`**, stored in the `tron-www` repo at
`public/workflow/` (`index.html` = `workflow.html`, plus `flow-description.html`). That copy carries a
`GENERATED — do not edit` banner. **Never hand-edit it** — it is overwritten on every sync. Two editable
copies always drift; there is exactly one owner (this repo) and one derived copy (the site).

## The rule (for engineers & architects)

**Any change to `docs/workflow.html` or `docs/flow-description.html` here MUST be published to `tron-www`.**
This is part of the normal flow defined in `tron-meta/` — a diagram change isn't "done" until the public
copy matches.

- **Automated:** the CI Action `.github/workflows/publish-diagram.yml` runs on a merge that touches either
  file and opens a sync PR on `tron-www`; merging that PR deploys (GitHub Pages, on push to `main`).
- **Manual fallback** (until the Action's token is provisioned, or for an out-of-band publish): copy the
  two files into `tron-www/public/workflow/` (`workflow.html` → `index.html`), keep the generated banner,
  commit, push `main`. Verify live at `tron.42labs.io/workflow/`.

## Notes

- Asset paths are **absolute** (`/favicon-…`) so the page works both locally (served from `docs/`) and at
  `/workflow/` on the site. `workflow.html` references `flow-description.html` relatively — the two must
  stay co-located.
- Required CI secret: a token with write access to `tron-www` (see the workflow file). Until it exists,
  use the manual fallback.
