# Lens

Read-only HTML view over `pipeline.md`, `pipeline-archive.md`, `backlog.md`, and the in-pipeline tech-debt + ad-hoc tables. Static, self-contained, no runtime DB.

## Local

```sh
cd meta/lens
npm install
npm run build      # → dist/
npm run serve      # http://localhost:4422
```

The build parses the markdown sources at the meta root (`../pipeline.md`, etc.) — no source changes needed; the lens follows the docs.

## Deploy — Cloudflare Pages + Access (private subdomain)

The lens is private. It must never be on the public web. Deployment uses **Cloudflare Pages** for static hosting and **Cloudflare Access** for auth.

### One-time per project

1. **Cloudflare Pages — create project**
   - Dashboard → Workers & Pages → Create → Pages → Connect to Git
   - Repo: project's meta repo (e.g. `<org>/<project>-meta`)
   - Production branch: `main`
   - Build command: `cd lens && npm install && npm run build`
   - Output directory: `lens/dist`
   - Root directory: leave default (repo root)

2. **Custom domain**
   - Pages project → Custom domains → Set up → `lens.<project-domain>`
   - Cloudflare auto-provisions the CNAME if the apex is on Cloudflare DNS.

3. **Cloudflare Access — protect the subdomain**
   - Zero Trust dashboard → Access → Applications → Add → Self-hosted
   - Application domain: `lens.<project-domain>`
   - Session duration: 24h (or per org policy)
   - Add policy: Allow → include rule → Emails: `<owner@email>` (or Google Workspace group)
   - Identity provider: Google / GitHub / one-time PIN — at least one configured at the team level.

4. **Verify** — open `lens.<project-domain>` in an incognito window. Cloudflare Access challenge must appear before any lens content loads.

### Per-deploy

Pushing to the meta repo's `main` branch triggers a Cloudflare Pages build automatically. No manual step.

### Cost

Cloudflare Pages free tier covers static-only deploys (500 builds/month). Cloudflare Access free tier covers up to 50 users. Total cost: $0 at small-team scale.

## Customising for a new project

Two edits — that's the contract:

1. `build.mjs` → `PROJECT_NAME` constant (single source of truth; injected into `<title>` and `<h1>`)
2. `package.json` → `name` field

Optional:

- `assets/favicons/` → swap if the project has its own brand assets

Source-doc paths (`../pipeline.md`, etc.) follow the canonical meta layout — no changes needed.

## Source-doc rules

The lens depends on disciplined source docs. See `principles.md §Core Docs` for the canonical rule set:

- One-line `Last Updated` (no `Previous:` chains, no essay paragraphs).
- Pipeline `Task` column = single short sentence; full detail lives in the block file (rendered in the modal).

Drift from these rules degrades the lens silently — the parser still works, but the cards become unreadable.
