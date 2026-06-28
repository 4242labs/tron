# Blueprint contracts — TRON deterministic FSM (B0 · reconciled to the converged flow)

**Status:** RECONCILED to the rebuilt engine in block 01-03 — the behavior model below matches the built
`engine/fsm.py`, `routing.yaml`, and `messages.yaml`. Companion to `contracts/rebuild-spec.md` (the 01-01
behavior spec); on any conflict the spec + the built engine win.
· **Block:** 01-03 (reconcile) · **Date:** 2026-06-28
**Implements:** `42hq/agents/super-m/plans/tron-adr-001-deterministic-rebuild.md` (FSM + scripted I/O)
**Conforms to:** the frozen flow — `42hq/agents/super-m/plans/tron-workflow-v2-skills.csv` (the event table + PULSE/SWITCHBOARD + grammar).

This is the authoritative contract set the rest of TRON is built against. **Design only** — no real
copy. It locks: the event-table model, the standing layer (PULSE + SWITCHBOARD), the trigger
grammar, the closed inbound-tag map, the judgment-tool contracts, the invalid-output policy, the
tick model, copy scope, the `pipeline: host` accepted format, the pipeline-tracking decision, and
the blueprint-lint rules.

Schema stubs live in `contracts/schema/` (`project`, `knobs`, `routing`, `messages`).

---

## 0. How the pieces fit

```
WAKE daemon ──> tick ──>               engine (the spine, deterministic)
                                          │  PULSE — the dispatch loop
                                          │  SWITCHBOARD — per-slot work selection
                                          │  runs the engine's event table (the fixed TABLE)
                                          │  with knobs.yaml knobs + routing.yaml (grammar + tag map)
                                          │  calls the LLM ONLY for a typed judgment tool (schema-in/out)
                                          ▼
                                   advance ──> persist (atomic) ──> exit
```

- **The engine** is the only executor (Python core + the WAKE daemon + thin `tron` shell connectors). It reads
  the engine's fixed **event table** (the TABLE), the project's **knobs** (`knobs.yaml`), and the canon **grammar + tag map** (`routing.yaml`)
  and drives the flow. The LLM never reads the routing path.
- **PULSE** = the standing dispatch loop (the engine spine). **SWITCHBOARD** = the deterministic
  per-slot work selector PULSE calls. Both are code — **never** an LLM call.
- The LLM is *called out to* only for a bounded **judgment tool** (§3), then control returns to the engine.
- All emitted text comes from **`messages.yaml`** via `render(tag, slots)` (§6). No backend narration
  ever reaches a human.
- `tron.md` (D5) is the prompt context the judgment tools run under — **not** an executor.

Two vocabularies, kept strictly separate:
- **Triggers** (§1, grammar in `routing.yaml`) — the event-table edges. Every step's *on-complete* is
  itself a trigger; the table is a closed loop.
- **Message tags** (§2) — what `classify_message` returns for an inbound message; each maps to a trigger
  or a side action.

---

## 1. The event-table model (canon-invariant)

TRON's behaviour is an **explicit event table**, not a library of primitives. Each row is:

```
trigger → step (actor, skill) → outputs → on-complete (== a trigger)
```

- **Steps are explicit.** A step names its actor (TRON / engineer / architect / reviewer) and, for a
  TRON step, the **skill** it runs. Worker steps carry no TRON skill (the actor owns its method).
- **On-complete is a trigger.** Outcomes feed straight back as triggers; `pulse` returns control to
  the dispatcher. Terminals: `end` (session over), `-` (no trigger).
- **Multi-outcome** steps stack alternatives with `|`; the named **selector** (a skill or the worker's
  reported outcome) decides which fires.
- **Fan-out** is allowed and declared: one trigger may drive more than one row (e.g. a review-completion
  fires *release reviewer* AND *log review* in parallel).

### Standing layer
- **PULSE** — runs at `tron:start` and on every `pulse` return. It keeps every worker slot busy and
  hands off to SWITCHBOARD; any unexpected input → SENTRY (the `*` catch-all). It is the loop, not a row.
- **SWITCHBOARD** — per free worker slot, in priority: (a) oldest available **adhoc** block →
  (b) a **due cadence** reviewer (consume its counter) → (c) next available block by pipeline order.
  Then **clear-ahead**: enqueue the architect (`review:next:<block>`) to author the block file for every
  in-scope roadmap row that has none yet. Then **wait** or **session:end**. A block is dispatchable
  **iff** its file is `📋` with every `Depends on` already `✅` on trunk and it isn't already in flight
  (no live worker, no open PR). Dispatch writes **no status** — TRON owns no pipeline; the spawned
  worker record is the in-flight marker (idempotent against concurrent passes).
- **SENTRY** — the reactive third of the standing trio (**PULSE · SWITCHBOARD · SENTRY**): the `*` catch-all
  every classified message ultimately falls through, and the safety net for anything that doesn't fit. An
  out-of-enum input takes `unclassified` → `*` → the SENTRY catch-all → **the architect** to sort (no second
  LLM judgment).

### Roles
- **Architect** — a **persistent, dedicated** agent, **excluded from the worker slot pool**, draining a FIFO
  `architect_queue` (MANIFEST). Architect jobs ENQUEUE (never need a free slot, never contend with workers)
  in two **distinct job-kinds**: `forward` — **author** a missing upcoming block file (PR'd to trunk); and
  `reconcile` — re-check the next scoped block against a just-finished block's drift, then report it good to
  dispatch. A landed `✅` enqueues a `reconcile` (M-05), and the next scoped block's dispatch readiness is
  **gated until that reconcile completes**. The architect is **forward-looking only**: it also turns reviewer
  findings into **upcoming** adhoc block files (`log-review`) and never reopens a done block. `architect-count`
  is the knob that drains the queue faster (the throughput bottleneck).
- **Engineers + reviewers** share the worker slot pool. Reviewer types are open (code / security / data / …).
- **Review is a milestone, not a verdict.** A reviewer delivers a log + "done"; the architect's
  log-review decides what becomes work.
- **Cadence is PULL** — SWITCHBOARD checks the clock; a `<type>` counter increments on every block that
  lands `✅` on trunk (deduped via `seen_done`) and is reset on dispatch. Never auto-fired.
- **Wall → operator.** A wall parks its block `blocked` + frees the slot; `operator.decision` then
  **resumes / amends / abandons** it (those three only — the operator-approves-before-merge path is gone).
  Every escalation stamps a correlation **`case` id**; parked cases live in the MANIFEST keyed by that id, and
  the operator reply carries the id back so Settle (02-08) clears the right case within ≤1 tick. Liveness
  (stall / dead worker) is the engine's side-system; it feeds a single `worker:stalled` trigger into the table.
- **Bootup & Session-End are protocols** (TRON lifecycle), not rows; SENTRY handles the `*` catch-all.
  **Bootup is a first-run gateway:** a truly-empty pipeline exits with a "plan first" message; a range/phase
  scope naming a block the pipeline lacks is refused as a typo; an empty-but-valid scope is legitimate. A
  clean end / `halt` archives the MANIFEST.
- **Operator run-control (PARLEY commands, not classified messages).** `PAUSE` (hard-freeze dispatch,
  resumable) · `DRAIN` (finish in-flight, start nothing new, resumable) · `RESUME` · `HALT` (terminal,
  archives the MANIFEST). The engine checks these via a per-tick **run-state flag in the MANIFEST** (R-HALT) —
  they are operator-channel commands, never `classify_message` tags.

The canon-invariant part is the **trigger grammar** (`routing.yaml`) + the engine's fixed event table.
Projects set only **knobs** (counts, cadence, git, WAKE) in `knobs.yaml` — never the table itself; a
genuinely new *shape* of control (beyond the grammar) is the only thing that is a canon change here.

---

## 2. Inbound message tags (closed) → triggers

`classify_message(text, ctx) → {tag, slots}` returns exactly one tag from this closed set (or
`unclassified`). Each maps to a **trigger** (the FSM advances) or a **side** action (no advance) or a
**tick**. Full map in `routing.yaml`; summary:

### Worker-origin
| Tag | Meaning | Maps to |
|:--|:--|:--|
| `worker.done` | block built | `block:next:done` |
| `worker.wall` | hit a wall needing the operator | `wall:raised:<block>` |
| `worker.review_done` | reviewer delivered its log | `review:<type>:done` |
| `worker.await_confirm` | pause mid-block for go-ahead | `worker:await:<block>` |
| `worker.question_peer` | peer consult (e.g. architect) | side: observe (no advance) |
| `worker.question_tron` | question for TRON | side: answer from context |
| `worker.progress` | heartbeat | side: none |

`worker.await_confirm` picks its rung **deterministically** (no LLM): (a) an operator-registered checkpoint →
the operator (a parked case, never auto-resolved); (b) a scope/blueprint question → the architect; (c) nothing
substantive → a deterministic auto-ack. When a checkpoint is registered it **always reaches the operator** (R-AWAIT).

### Architect-origin (the persistent, forward-only consultant)
| Tag | Meaning | Maps to |
|:--|:--|:--|
| `architect.reconciled` | forward/reconcile done — upcoming block re-checked & signed off on trunk (M-05) | `block:<block>:reconciled` |
| `architect.logged` | log-review done — findings shaped into adhoc block files | `block:adhoc:reconciled` |

### Operator-origin (session or TG)
| Tag | Meaning | Maps to |
|:--|:--|:--|
| `operator.decision` | reply to a wall | `operator:decision:<block>` |
| `operator.status_query` | asking for state | side: reply digest |
| `operator.knob_change` | change a rule/knob | side: edit_self |
| `operator.directive` | general instruction | side: best-effort |

### System (engine-produced, not from classify)
| Tag | Source | Maps to |
|:--|:--|:--|
| `worker.stalled` / `worker.dead` | engine liveness side-system | `worker:stalled` (→ recover) |

### Reserved
| Tag | Meaning | Maps to |
|:--|:--|:--|
| `unclassified` | out-of-enum, or invalid-output budget exhausted (§4) | `*` → SENTRY catch-all → architect triage |

"Side" actions are global engine handlers that do not advance the FSM; the active step is re-entered.

---

## 3. Judgment-tool contracts

Every LLM touch is one of these. Schema-in / schema-out; the model returns a tag + structured slots,
never free prose to the flow.

| Tool | Input | Output | Called by |
|:--|:--|:--|:--|
| **`classify_message`** | `{text, sender:{kind:worker\|operator, id?, role?}}` | `{tag ∈ enum∪unclassified, slots:{…}, confidence:0..1}` | the engine on any inbound worker/operator/TG message |

**Tiering:** `classify_message` → cheap model. **One** judgment tool only. Wired in the engine (D2).

**Not judgment tools, by design:** *"is this the operator's problem?"* (the old second judgment — **retired**:
an unclassifiable input routes to the architect, who steers it — TRON makes no second LLM call),
review verdicts (review is a milestone), findings-triage (→ the architect's `log-review` skill), and
stall detection (→ the engine liveness side-system). These were LLM tools in the old model and are removed.

---

## 4. Invalid-output policy

The engine schema-validates every judgment-tool return.

1. **Valid** → use it.
2. **Invalid / malformed / out-of-enum tag** → retry the same call, appending the validation error.
   Budget: `invalid_output.max_retries` (default 2), read from `routing.yaml` by the engine.
3. **Budget exhausted** → `unclassified` → the `*` SENTRY catch-all, which hands the input to the
   architect to sort (no second LLM judgment). Raw outputs logged (`logs/invalid-output-{date}.log`).

TRON never guesses a flow decision from malformed output. An out-of-enum `tag` is itself a validation
failure (the enum is closed in the tool schema).

---

## 5. Tick model

Turn-based. The **WAKE daemon** (the in-process scheduler) decides *when* to wake; each wake is **one
bounded tick** that carries no state between wakes — the daemon owns timing only, never run state.
**One wake = one bounded tick.**

- **Trigger:** the WAKE daemon (ND-08) fires a `tick` — early on a new inbox message (after a COOLDOWN
  floor) or at the CEILING cadence otherwise, bounded both ways (cooldown ≤ gap ≤ ceiling). Every tick
  runs single-flight (an flock), so two never overlap. Operator inbound is drained in the same tick.
- **A tick:**
  1. **Load** the MANIFEST `manifest.yaml` (the FSM cursor, counters, trunk-read cache, worker/architect-queue state).
  2. **One bounded pass:** refresh from trunk (`git` ff + read `pipeline.md`/`blocks/*.md` + `gh pr list`) — a
     failed refresh is **never swallowed into a stale snapshot**: consecutive failures are counted and the
     engine halts **loud** (at bootup, synchronously, before any MANIFEST exists; or at a death-cap during
     ticks); sweep liveness (engine side-system → `worker:stalled` if dead/stuck); drain inbound
     → `classify_message` → trigger or side; drive in-flight **DONE gates** (the prompted challenge, below);
     then run **PULSE** (which calls SWITCHBOARD) to fill free slots, clear ahead, wait, or end.
  3. **Persist atomically.**
  4. **Exit.**
- **Atomic writes:** write `*.tmp`, then `mv` over the live file (atomic rename). Never half-written.
- **Idempotency:** state persists only *after* the pass completes, so a crashed tick re-runs safely.
  World-mutating actions are state-guarded:
  - spawn — guarded by `active_workers` + open-PR check (no double-dispatch); TRON writes no status;
  - clear-ahead enqueue — guarded by "already queued for review";
  - escalate — guarded by the runtime `blocked` list;
  - release/kill — guarded by worker `status`;
  - dispatch history — `dispatched.log` keyed by `block_id + attempt`.
- A tick with no actionable signal persists `last_sweep_at` and exits — no transition.

Atomic state + idempotent ticks ⇒ a crashed wake is safely retried.

**The DONE gate (the prompted challenge, T4 of `rebuild-spec.md`).** A `worker.done` only *flags a candidate*;
the gate then judges on **evidence** at each stage — never the worker's `✅`, never bare trunk presence:
validate-local → authorize-push (PR open) → CI green on trunk → deploy-if-declared (only when the block header
declares `Deploy:`) → `✅`. A failed stage re-prompts with the specific gap (`gate.step`), never advancing.
**PULSE never merges** — the engineer lands it all via PR; there is **no operator-approve-before-merge**.

---

## 6. Copy scope

- **`messages.yaml` = runtime copy only.** Every line TRON emits during a *session* — operator, worker,
  terminal, Telegram — keyed by template id, with named slots. Rendered via `render(tag, slots)`.
- **Seeder voice is separate.** `tron-seed.md` greeting/prompts are seeding-time copy and do **not** draw
  from `messages.yaml`. The two registries never share keys.
- **Tone authority:** the built-in TRON persona (dark, dry, sardonic; no host-runtime names ever) is the
  canon floor and ships complete. The operator overrides individual templates by editing `messages.yaml`;
  edited keys win, unedited keep the persona default.

---

## 7. Canon pipeline format (what TRON reads)

TRON owns no pipeline. It **reads** the project's git-tracked canon — the format the
`new-project-template` defines — and parses it deterministically (no LLM):

- **Living doc** (`pipeline.md`): `## ` sections (Roadmap, Technical Debt, Ad-hoc Blocks, Backlog),
  `### Phase N: <Title>` headers, and `ID | Task | Status | Notes` tables. The Status cell is **exactly
  one emoji** from `📋 🔄 ✅ 📌 🔧 ❌ 📦 ✂️`; a row with a block file names it in Notes as `Block `blocks/<id>.md``.
- **Block files** (`blocks/<id>.md`): fixed `**Key:** value` headers — `Status`, `Depends on`,
  `Reviewer class`, `Merge`, `Deploy`, `Phase`. The block file is **dispatch truth**; the living doc gives order.

Emoji → status: `📋`→to-do (dispatchable when deps `✅`), `🔄`→in-progress, `✅`→done; the rest
(`📌 🔧 ❌ 📦 ✂️`) are not dispatchable. The seeder confirms the project complies; it never rewrites the
project's pipeline or blocks.

---

## 8. Truth model: canon is authority, TRON reads

The pipeline is the project's **git-tracked** canon, written by agents via PR — not TRON state. TRON
holds only a **disposable read cache** (`manifest.yaml › pipeline`), rebuilt every wake from trunk
+ open PRs + alive workers, so a crash, an off-session, or tron→no-tron→tron leaves **no drift** — and a
failed refresh halts **loud** rather than caching a stale snapshot (§5). TRON
writes **nothing** to git: it never sets status. A block is done only when it shows `✅` on trunk
(merged, re-validated, deployed-clean — all landed by an agent). Status *history* is version-controlled
in the project repo, as it should be.

---

## 9. Blueprint-lint rules

Runs in `validate` / `doctor` (D3, implemented in `engine/lint.py`). A malformed instance fails at
**seed/validate time, not runtime**. The rules are grammar-driven: the legal token set is read FROM
`routing.yaml › grammar`, so the checks verify internal consistency rather than a hardcoded duplicate.

### Canon-level (over `routing.yaml` + the engine event TABLE)
- **L1** Grammar block complete — every required field present (forms, subjects, events, params,
  wildcard, alternatives, terminals, control, match).
- **L2** Inbound tag enum is closed (== the engine's known set) and `unclassified` maps to the `*` catch-all.
- **L3** Total tag coverage: every tag action is exactly one of `{trigger, side, tick}`.
- **L4** Every tag's `trigger` satisfies the grammar (2–3 legal segments, or `*`).
- **L5** The judgment tools are exactly the canon one (`classify_message`), with a
  structured (non-prose) `out` list.
- **L6** Invalid-output policy present: `max_retries` an int, `on_exhaustion` a grammar-valid trigger.
- **L7** Every event-TABLE pattern satisfies the grammar.
- **L8** Every TABLE handler resolves to a callable `Engine` method (a `None` handler = a worker-activity row).
- **L9** Every tag `trigger` resolves to a TABLE row (no orphan classification); `<type>` never binds `next`.

### Composition-level (over `knobs.yaml` against `project.yaml`)
- **L10** `worker_count` knob is declared (value may be null → asked at runtime).
- **L11** Every cadence `<type>` maps to a positive-int threshold.
- **L12** Session shape valid (`persistent_architect` is a bool).
- **L13** Project roles sane (skipped if no `project.yaml › agents`).
- **L14** WAKE timing knobs are positive ints.
- **L15** WAKE cooldown floor ≤ ceiling.

### Prompt-level (over `prompts/registry.yaml` against `messages.yaml`)
- **L16** Every registry PMT id resolves to a self-contained file that exists.
- **L17** Every worker-channel message references a PMT id the registry knows (closed + total).

The data layer + the engine TABLE are the author-error surface; L1–L9 are what the gate most needs to catch.

---

## 10. Boundary vs the data layer (knobs.yaml / routing.yaml / messages.yaml / prompts/)

This block defines **shapes**: the event-table model + grammar, the closed tag map, the judgment-tool
contracts, the file schemas, and the lint rules. The **data layer authors the instances**: the
embedded default knobs (`knobs.yaml`), the actual `routing.yaml` grammar + tag map, the
`messages.yaml` templates, and the `prompts/` PMT bodies (referenced by id).

## 11. Open / carried watch-items
- **R-1** keep the bash connectors small; FSM/JSON/render fragility lives in the Python engine core.
- **R-4** the data layer may ship placeholder copy keyed to the tag map so the engine can be tested before final copy lands.
