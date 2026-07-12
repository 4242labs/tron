---
name: skill-linear-cards
description: How any agent creates and maintains this project's work as Linear cards — MCP setup, workspace discovery, label tiers, the mandatory agent signature, and the full card lifecycle.
source: canon
canon_version: HEAD
---

# Skill: Linear Cards

The project's task list lives in **Linear**. This skill is how an agent turns work into
well-formed, traceable cards and keeps them current. Linear is the source of truth for
open work — cards are primary, not a mirror of some other doc.

**Read this file at every invocation — do not rely on memory from session start.**
**Discover the live workspace every run (§2) — never hardcode state/label IDs from memory.**

Placeholders below are filled once, at scaffold time, from the table in §3.

---

## 1. When to Use

- A unit of work needs tracking → create a card (§5).
- Work started / changed state / finished → update the card (§6).
- A card is wrong or obsolete → retire it (§7). Linear has **no hard-delete via API** —
  you cancel or archive, never destroy.
- Multi-step work → one parent + sub-issues, not one fat card (§5).

Do **not** create a second card for something already tracked — search first (§2).

---

## 2. Prerequisite + Workspace Discovery

### 2a. MCP must be connected
The Linear MCP is required. Verify with a `list_teams` call. If it errors / returns nothing,
it is not connected — set it up (global config, once per machine):

```bash
claude mcp add --transport http linear https://mcp.linear.app/mcp -s user
```

Then `/mcp` → **linear** → complete the browser OAuth. **Use the `/mcp` (streamable-HTTP)
endpoint, NOT `/sse`** — the `/sse` endpoint's OAuth advertises the `/mcp` resource and
fails with a `Protected resource … does not match` mismatch. Tools are `mcp__linear__*`
(deferred — load via ToolSearch before calling).

### 2b. Discover before you write
Team workflow **states and labels are custom per workspace** — never assume them. Each run,
before creating/transitioning, resolve the live values:

- `list_teams` → confirm `<LINEAR_TEAM>` exists.
- `list_issue_statuses` (team) → the real state names (they are often ALL-CAPS / non-default).
- `list_issue_labels` (workspace + team) → confirm the labels in §4 exist; create any missing
  one with `create_issue_label` before first use.
- `list_issues` (filter by title/label) → **check the work isn't already carded.**

---

## 3. Scaffold Placeholders

Fill these once when the skill is copied into a project. Keep the template generic — no real
project/host/agent names in the canon copy.

| Placeholder | Meaning | Example |
|:--|:--|:--|
| `<LINEAR_TEAM>` | Team name or key cards belong to | `AcmeCore` |
| `<LINEAR_PROJECT>` | Project cards land in (or `none`) | `AcmeCore` |
| `<DEFAULT_STATE>` | Starting workflow state for new cards | `TO-DO` |
| `<DEFAULT_ASSIGNEE>` | Owner of new cards | `me` |
| `<DEFAULT_PRIORITY>` | Default priority (0–4) | `3` (Medium) |
| `<PROJECT_LABELS>` | Fixed label(s) on **every** card in this project | `Infra` |
| `<SCOPE_LABELS>` | Optional conditional-dimension label set + when each applies | machine: `HOST-A` / `HOST-B` |
| `<AGENT_ROLE>` | This agent's role/persona — used for both the persona label (§4) and the signature (§6) | `SYSADMIN` |

---

## 4. Label Model — five tiers

Every card carries labels from these tiers, resolved in order:

1. **Universal (MUST, all projects):** `🤖 beep-boop` — the workspace-wide marker that a card
   was created by an AI agent, not hand-authored. **Every agent stamps it on every card,
   regardless of project or team.** Create it once at workspace scope if absent.
2. **Persona (MUST, all projects):** the label naming the agent that authored the card — its
   own `<AGENT_ROLE>` (§3), lowercase (e.g. `tron`, `architect`, `engineer`, `data-architect`).
   **Every agent stamps its own persona on every card it creates**, so authorship is filterable,
   not just readable in the signature. Create the label at workspace scope if absent; never
   stamp another agent's persona.
3. **Project (fixed):** `<PROJECT_LABELS>` — always applied in this project.
4. **Scope (conditional):** a `<SCOPE_LABELS>` value when the card targets one thing in that
   dimension (e.g. a specific host/service/area); omit for project-wide cards.
5. **Session (optional):** whatever extra label the operator names for a batch/session at
   runtime. Ask/accept, don't invent.

`labels` on `save_issue` **replaces** the full set — always send universal + persona + project +
any scope/session labels together, or you'll drop the ones you omit.

---

## 5. Creating a Card

`save_issue` (no `id` = create). Required: `title`, `team`. Set, at minimum:

- `team: <LINEAR_TEAM>` · **`project: <LINEAR_PROJECT>` — MANDATORY. Never create a project-less card** (unless the project is explicitly configured `<LINEAR_PROJECT> = none`).
- `state: <DEFAULT_STATE>` · `assignee: <DEFAULT_ASSIGNEE>` · `priority: <DEFAULT_PRIORITY>`
- `labels`: the resolved §4 set (universal + persona + project + scope/session)
- `description`: Markdown — real newlines, **not** `\n`. **End with the signature (§6).**

**Multi-step work** → create the parent, then each sub-issue with `parentId: <parent identifier>`.
Order sub-issues with `blockedBy` where a real dependency exists. Progress rolls up to the parent.
**⚠ Sub-issues do NOT inherit the parent's project — pass `project` explicitly on every sub-issue**, or they land project-less.

Optional per-card fields as they apply: `dueDate`, `estimate` (only if the team has estimates
on), `links` (append-only URL attachments), `blocks`/`relatedTo`, `milestone`/`cycle` (only if
the team has them).

---

## 6. Agent Signature (MUST)

**Every card description ends with a signature line**, after a `---`, so any card is traceable
back to the agent, model, host, and session that produced it:

```markdown
---
🤖 _<AGENT_ROLE> · <MODEL> @ <HOST> · Session `<SESSION_ID>` · <YYYY-MM-DD HH:MM UTC>_
```

- `<MODEL>` — human name of the model running (e.g. `Claude Opus 4.8`).
- `<HOST>` — the machine the agent is running on (e.g. its hostname).
- `<SESSION_ID>` — the current session id (short prefix is enough); this is the traceability
  anchor — it ties the card to the exact transcript that created it.
- `<YYYY-MM-DD HH:MM UTC>` — legible timestamp, always in **UTC** (e.g. `2026-07-08 13:07 UTC`).

Fill these from the live runtime at create time, not from the placeholder literals. On an
**update** that materially changes the card, you may append a second signature line rather than
overwrite the first.

---

## 7. Updating & Retiring

- **Transition / edit:** `save_issue` with `id` (identifier, e.g. `<TEAM>-123`). Send only the
  fields you're changing — except `labels`, which is a full replace (§4).
- **Comments:** `save_comment` for discussion / status notes; supports the same Markdown,
  threading (`parentId`), and @mentions.
- **Retire:** no hard-delete. Obsolete → `state: Canceled`; done → `state: Done`; genuine
  duplicate → `state: Duplicate` (+ `duplicateOf`). Archive only if the workspace prefers it.

---

## 8. Optional — agent-app delegation (future)

Assignee resolves to the **authenticated OAuth identity** (the operator), so `assignee: "me"`
is the operator, not the agent — which is why authorship is carried by the **label + signature**,
not the assignee. If the workspace later installs a Linear **agent app**, the `delegate` field
can attribute cards to that agent user; until then, label + signature are the mechanism.

---

## Constraints

- **Never destroy.** No hard-delete exists — cancel/duplicate/archive only. Before retiring a
  card someone else may own, confirm it's actually yours/obsolete.
- **Discover, don't assume.** States and labels are workspace-custom; resolve them live (§2b)
  every run. A guessed state/label name silently fails or mislabels.
- **No duplicate cards.** Search before creating (§2b).
- **Every card MUST have a project.** A project-less card is never acceptable. Sub-issues do
  NOT inherit the parent's project — set it explicitly on each (§5). The only exception is a
  project explicitly configured `<LINEAR_PROJECT> = none`.
- **Universal label + persona label + signature are non-negotiable** — they are what make an
  agent-authored card identifiable, filterable by author, and traceable. A card missing any of
  the three is malformed.
- **Description Markdown uses literal newlines**, never `\n` escape sequences.

---

**Last Updated:** 2026-07-12 — §4 label model extended to five tiers: a **persona label** (the
authoring agent's own `<AGENT_ROLE>`, e.g. `tron` / `architect` / `engineer` / `data-architect`)
is now mandatory alongside `🤖 beep-boop`, so card authorship is filterable and not only visible
in the signature. Earlier 2026-07-08 — initial authoring. Reusable across projects; fill §3 per project.
