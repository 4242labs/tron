# <PROJECT_NAME> — app/

<One-line description of the app.>

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | Next.js (App Router, `src/` directory) |
| Styling | Tailwind CSS v4 |
| Backend/DB | Supabase (Postgres + Auth + Storage) |
| Hosting | Vercel |
| AI | Claude API via LiteLLM |
| Email Sending | <Email provider> |
| Notifications | <Notification provider> |
| Error Monitoring | Sentry (`@sentry/nextjs`) |
| Testing | Vitest + React Testing Library |

## Branching + Deployment

Two-gate workflow. Repo default branch is `staging`. Feature PRs target `staging`; promotion to `main` is a separate PR. `pr-base-guard` CI job blocks non-`staging`/non-`hotfix/*` PRs to `main`. Auto-merge is banned — the agent merges once authorized (by the user, or by the supervising process per its merge policy) and monitors the merge through to a verified deploy.

## Project Structure

```
app/
├── src/
│   ├── app/                  # Next.js App Router pages
│   ├── components/           # Shared UI components
│   ├── lib/                  # Utilities and services
│   └── test/                 # Test files
├── supabase/
│   └── migrations/           # SQL migrations
├── .env.example
├── package.json
└── vitest.config.ts
```

## Development

```bash
cd app
npm run dev       # Start dev server (localhost:3000)
npm run build     # Production build
npm test          # Run tests (vitest)
```
