# MCP + Integration Setup

MCP and API integrations for the agent runtime on this project. Each section covers what the integration does, exact setup steps, and how to verify it works.

> **Terminology:** These are MCP integrations and API integrations. Plain in particular is a raw HTTP integration — not an MCP server.

---

## Supabase MCP

**What:** Lets the agent query your database, inspect schema, and review migrations directly from the conversation.

**Steps:**
1. Get a Supabase access token: supabase.com → Account → Access Tokens → Generate new token
2. Add to `~/.zshrc`:
   ```bash
   export SUPABASE_ACCESS_TOKEN=<token>
   ```
   Then: `source ~/.zshrc`
3. Configure the agent runtime MCP in `~/.claude/mcp.json` (or via the agent runtime settings):
   ```json
   {
     "supabase": {
       "command": "npx",
       "args": ["-y", "@supabase/mcp-server-supabase@latest", "--read-only"],
       "env": {
         "SUPABASE_ACCESS_TOKEN": "<token>"
       }
     }
   }
   ```
4. Restart the agent runtime session

**Verify:** Ask the agent "list tables in my Supabase project" — it should return your table list without errors.

**Token rotation:** Rotate access tokens every 90 days. Update `~/.zshrc` + the agent runtime MCP config. Document rotation date in `docs/playbook-infra.md`.

---

## GitHub MCP

**What:** Lets the agent manage PRs, issues, and repository settings directly from the conversation.

**Steps:**
1. Create a fine-grained PAT: github.com → Settings → Developer settings → Fine-grained personal access tokens → Generate new token
   - Required permissions: Contents (read/write), Pull requests (read/write), Issues (read/write), Repository metadata (read)
   - Set token expiration (90 days recommended)
2. Add to `~/.zshrc`:
   ```bash
   export GITHUB_PAT=<token>
   ```
   Then: `source ~/.zshrc`
3. Configure the agent runtime MCP:
   ```json
   {
     "github": {
       "command": "npx",
       "args": ["-y", "@modelcontextprotocol/server-github"],
       "env": {
         "GITHUB_PERSONAL_ACCESS_TOKEN": "<token>"
       }
     }
   }
   ```
4. Restart the agent runtime session

**Verify:** Ask the agent "list open PRs in `<org>/<repo>`" — it should return the current PR list.

**Token rotation:** Fine-grained PATs expire. Set a calendar reminder before expiry. Regenerate and update `~/.zshrc` + MCP config.

---

## Vercel Plugin

**What:** Lets the agent inspect deployments, read logs, and manage environment variables from the conversation.

**Steps:**
1. The plugin is already enabled in `.claude/settings.json`:
   ```json
   {
     "enabledPlugins": {
       "vercel@claude-plugins-official": true
     }
   }
   ```
2. In the agent runtime, type: `/vercel authenticate`
3. Follow the OAuth flow in your browser — authorize the agent runtime to access your Vercel account

**Verify:** Ask the agent "list my recent Vercel deployments" — it should return your deployment history.

**Non-Vercel projects:** Remove `vercel@claude-plugins-official` from `enabledPlugins` in `.claude/settings.json`.

---

## Plain API Integration (raw HTTP — not an MCP)

**What:** Support ticket creation from in-app escalation flows. Plain is called via raw `fetch` to their GraphQL API — not via an MCP server.

**Do NOT use the `@team-plain/graphql` SDK** — it over-fetches and requires undocumented permission scopes that are unavailable on standard plans.

**Steps:**
1. Create a machine user in Plain: plain.com → Settings → Machine Users → New machine user
   - Required permissions: `customer:create`, `customer:edit`, `thread:create`, `thread:read`
2. Copy the API key
3. Add to `.env.local`:
   ```bash
   PLAIN_API_KEY=<key>
   ```
4. Add to Vercel environment (production + preview scopes): `PLAIN_API_KEY`

**Usage pattern:**
```ts
const response = await fetch("https://core-api.uk.plain.com/graphql/v1", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${process.env.PLAIN_API_KEY}`,
  },
  body: JSON.stringify({ query: MUTATION, variables: { ... } }),
});
```

**Verify:** Trigger an escalation flow on staging → confirm the ticket appears in your Plain inbox within 30 seconds.

**Key rotation:** Rotate the machine user API key when team members with access leave. Update `.env.local`, Vercel env, and document in `docs/playbook-infra.md`.
