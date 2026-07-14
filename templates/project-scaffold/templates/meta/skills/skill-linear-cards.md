---
name: skill-linear-cards
description: Project instance of the canon Linear-cards skill — fills team/project/state values; full structure and custody live in canon.
source: canon
canon_version: HEAD
---

# Skill: Linear Cards (<PROJECT_NAME>)

Instance of the canon skill at **`~/42labs/42hq/knowledge-base/skills/skill-linear-cards.md`** —
that file is the single source of structure. This one only fills the values. Where the two
disagree, canon's *structure* wins; the concrete values here win.

**Read canon every time before touching Linear.** Discover the live workspace each run — never
hardcode state or label IDs from memory.

---

## Filled values (canon §3)

| Field | Value |
|:--|:--|
| Team | **<LINEAR_TEAM>** |
| Project | **<LINEAR_PROJECT>** — MANDATORY on every card *and every sub-issue* |
| Default state | **<DEFAULT_STATE>** |
| Default assignee | **<DEFAULT_ASSIGNEE>** (resolves to the operator — authorship and custody ride on labels + owner line + signature history, not the assignee) |
| Default priority | **<DEFAULT_PRIORITY>** |
| Universal label | **🤖 beep-boop** (MUST, every card) |
| Persona label | the authoring agent's own role, lowercase (MUST, every card it authors) |
| Project label | **<PROJECT_LABELS>** |
| Scope labels (conditional) | **<SCOPE_LABELS>** |

`labels` is a full replace — send the whole set every time.

---

## Everything else → canon

Prerequisites and MCP setup (§2) · five-tier label model (§4) · creating cards and sub-issues (§5)
· **custody: owner line + append-only signature history, and when to stamp each (§6)** · updating
and retiring (§7) · constraints.

Custody is the part most often skipped: never take over another session's card without rewriting
the owner line and appending a `took ownership` signature.

---

**Last Updated:** 2026-07-14 — reduced to a pointer. The full body moved to the shared knowledge
base so agents outside a scaffolded project can reach it; a second full copy here would only drift.
