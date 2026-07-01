# Block <ID>: <Title>

**Phase:** <Phase number and name>  
**Status:** 📋 To do  
**Apps:** <Which app/repo this touches>  
**Depends on:** <Block IDs this requires, or "none">  
**Blocks:** <Block IDs that depend on this, or "none">  
**Reviewer class:** <code | security | data | none>  ← which reviewer the supervising process dispatches on its review cadence; pinned at scoping, not pickable by engineer
**Merge approval:** <auto | needs-user>  ← default `auto` (the supervising process's gate drives the merge, no human sign-off); stamp `needs-user` for genuinely risky blocks that require explicit human sign-off before merge
**Deploy:** <none | check>  ← default inherits the project deploy check (`context.md → Deploy`); `none` opts this block out; `check` overrides with a block-specific success check
**Created:** <YYYY-MM-DD>

---

## Context

<Why this block exists. What problem it solves. What came before it. 2-4 sentences.>

---

## Tasks

### T1: <Task title>

<What to do. Be precise enough that the engineer doesn't need to ask questions.>

### T2: <Task title>

<...>

---

## Acceptance Criteria

Each criterion is a contract. The verification method is fixed at scoping time — engineer may not substitute "alternative evidence." If a method becomes infeasible mid-flow, escalate to user for renegotiation; do not proceed past it.

| # | Criterion | Verification method | Owner |
|:--|:--|:--|:--|
| AC-1 | <what must be true> | `test:<name>` \| `cmd:<exact command>` \| `screenshot:<trigger + URL>` \| `manual_by:<role>` | engineer |
| AC-2 | ... | ... | ... |

---

## Out of Scope

<Explicit exclusions — what this block does NOT cover. SUPER-M flags scope creep against this list. Any mid-flow scope change (add or drop) requires user approval and a note here.>

---

## Block Completion Gate

Do not mark this block done until:
- [ ] All acceptance criteria PASS in the Completion Report (no UNVERIFIED entries)
- [ ] Post-merge re-validation clean on trunk, and — where this block declares a deploy check — deployed clean and verified post-deploy
- [ ] User explicitly acknowledged the Completion Report and triggered session-end

Review is not a block-completion gate: the reviewer (per `Reviewer class:` above) is dispatched by the supervising process on its own review cadence, not pulled in here.
