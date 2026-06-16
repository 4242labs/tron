# <PROJECT_NAME> Pipeline

**Status:** Living Document
**Purpose:** Single source of truth for all product scope — what's being built, what's envisioned, and what needs fixing.

**Last Updated:** <DATE>

> Historical phases and resolved technical debt live in [`pipeline-archive.md`](./pipeline-archive.md). Diverse ideas not yet roadmapped live in [`backlog.md`](./backlog.md).

---

## How to Read This Document

**This is the ONLY status tracker for active work.** No other document tracks what's in progress, planned, or needs fixing.

**Status indicators:**

- **✅** — Done (implemented, tested, validated)
- **📋** — To do (scoped, not yet started)
- **🔄** — In progress
- **📌** — Deferred (reason noted)
- **🔧** — Open debt
- **❌** — Cut / Superseded
- **📦** — Folded into another block
- **✂️** — Split into multiple blocks

**Format contract.** This document follows a fixed shape so it stays parseable at a glance (and by tooling):

- Phases are `### Phase N: <Title>` headers; each owns one table.
- Every table has the columns `ID | Task | Status | Notes`, in that order.
- The **Status** cell holds exactly one emoji from the set above — no prose, no second glyph.
- When a row has a block file, its **Notes** cell names it as `` Block `blocks/<id>.md` ``.

---

## Roadmap

### Phase 1: <First Phase Title>

📋 **Status:** To do

<One-sentence phase description.>

| ID | Task | Status | Notes |
|:---|:-----|:-------|:------|
| S1-01 | <First block title — one short sentence> | 📋 | Block `blocks/01-01-<slug>.md` |

---

## Technical Debt

Items that exist but are not yet scoped into a block.

| ID | Issue | Status | Notes |
|:---|:------|:-------|:------|
| TD-01 | <Short description of the debt> | 🔧 | <Origin / link> |

---

## Ad-hoc Blocks

Blocks not tied to a roadmap phase (cross-cutting fixes, hardening, hygiene).

| ID | Task | Status | Notes |
|:---|:-----|:-------|:------|
| ADHOC-01 | <Title> | 📋 | <Notes> |

---

## Backlog

Pipeline-adjacent items waiting to be promoted into a phase.

| ID | Task | Status | Notes |
|:---|:-----|:-------|:------|
| BL-01 | <Title> | 📋 | <Notes> |
