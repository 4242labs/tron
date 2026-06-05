# spec — Example + contract

A spec is a single local file that declares one unit of work. TRON reads specs from the project's **specs path** (recorded in `project.yaml`) and cuts blocks from them. TRON explains these requirements during seeding and checks each spec for compliance.

A spec is a **declaration of intent** — what to build and how "done" is judged. It does **not** carry status. Status and sequencing live in the **pipeline**, joined to the spec by its ID.

---

## Required fields

Every spec must contain all of these:

| Field | Meaning |
|:--|:--|
| **ID** | Unique identifier, stable for the spec's life. Joins to the pipeline. |
| **Goal** | What to build, in one or two plain sentences. |
| **Acceptance criteria** | The conditions that make this spec "done." How a reviewer/operator judges completion. |
| **Scope bounds** | What is in scope and explicitly out of scope. Keeps the block from sprawling. |
| **Dependencies** | Other spec IDs that must be done first. Empty if none. These are hard gates — TRON will not dispatch a spec whose dependencies are unmet. |
| **Owner role** | Which worker role builds it. Default `engineer`; may differ (e.g. `architect` for a design spec). |

No status field. (If a spec carries one, TRON ignores it — the pipeline is authoritative.)

---

## Example

```
ID: AUTH-02
Goal: Add email+password login backed by the existing users table.
Owner: engineer

Acceptance criteria:
- POST /login returns a session token for valid credentials.
- Invalid credentials return 401 with no token.
- Tokens expire after the configured TTL.

Scope:
- In: login endpoint, token issuance, credential check.
- Out: password reset, OAuth, rate limiting (separate specs).

Dependencies: AUTH-01
```

---

## Notes

- Specs are **host-owned content** — TRON reads them, never rewrites them.
- Format is flexible; the field *names* above are what TRON looks for. TRON maps what it finds and asks the operator to fill any gap rather than refusing on a cosmetic mismatch.
- One spec = one block of dispatchable work. Split large efforts into multiple specs with dependencies rather than one sprawling spec.
