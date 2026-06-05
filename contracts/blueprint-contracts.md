# Blueprint contracts — TRON deterministic FSM (B0)

**Status:** canon · **Block:** B0 (Phase 0, Foundations) · **Date:** 2026-06-04
**Implements:** `42agents/super-m/plans/tron-adr-001-deterministic-rebuild.md`

This is the authoritative contract set the rest of TRON is built against. It is **design only** — no executable engine, no real copy. It locks: the step-primitive library, the closed situation-tag enum, the judgment-tool contracts, the invalid-output policy, the tick model, copy scope, the `pipeline: host` accepted format, the pipeline-tracking decision, and the blueprint-lint rules.

Schema stubs live in `contracts/schema/` (`project`, `workflow`, `routing`, `messages`).

---

## 0. How the pieces fit

```
cron ──> sweep.sh ──> [SWEEP] tick ──> run.sh (the spine, deterministic)
                                          │
                                          │ executes routing.yaml (primitives) + workflow.yaml (composition)
                                          │ calls claude -p ONLY for a typed judgment tool, schema-in/schema-out
                                          ▼
                                   advance FSM ──> persist (atomic) ──> exit
```

- **`run.sh`** is the only executor. It reads the project's **composition** (`workflow.yaml`) and the canon **primitive library + edges** (`routing.yaml`), and drives the flow. The LLM never reads the routing path.
- The LLM is *called out to* only for a bounded **judgment tool** (§3), then control returns to `run.sh`.
- All emitted text comes from **`messages.yaml`** via `render(tag, slots)` (§6). No backend narration ever reaches a human.
- `tron.md` (built in B4) is the prompt context those judgment tools run under — **not** an executor.

Two tag namespaces, kept strictly separate:
- **Message tags** (§2) — what `classify_message` returns for an inbound message. Closed enum.
- **Step outcome edges** (§1) — the named exits each primitive exposes; the composition binds them.

---

## 1. Step-primitive library (canon-invariant)

A small fixed menu of step *types*. Projects **compose** them (order, roles, checks, knobs) in `workflow.yaml`; they never author primitives. Adding CI / security-review / data-architect = naming them into existing primitives. Only a genuinely new *kind* of step (fan-out/join, loop-until, wait-for-event) is a canon change here.

Each primitive declares: its parameters, the judgment tool(s) it may call, and a **fixed set of outcome edges**. The composition must bind every exposed edge to a target (`next`, `end`, or a step id). Reserved targets: `next` (advance to the next composed step / next block), `end` (session-end), `escalate` (the escalate step).

| Primitive | Params | Judgment tool(s) | Outcome edges |
|:--|:--|:--|:--|
| **`dispatch(role)`** | `role` (∈ agents map); `concurrency?` (default: `max_concurrent_engineers` for `engineer`) | `classify_message` (worker inbound); `assess_stall` (during sweep) | `done`, `wall`, `stalled` |
| **`review(role)`** | `role`; `cadence?` (`every_n_blocks: <knob>` → periodic; absent → runs once on the triggering block) | `classify_message` (reads the report into clean/findings) | `clean`, `findings` |
| **`gate(kind)`** | `kind` (`ci`, `lint`, `<custom>`) | none by default (deterministic external check); `classify_message` only if a kind needs interpretation | `pass`, `fail` |
| **`escalate`** | `reason` (slot) | `classify_message` (operator reply) | `resolved`, `abort` |
| **`findings-triage`** | — (operates on the findings list in state) | `triage`, `scope_fix` | `fixes`, `none` |

Notes grounded in v1 (`tron-scripts.md`):
- `dispatch(engineer)` = "Spawn an engineer for a block"; `done` ← `worker.done`; `wall` ← `worker.wall`; `stalled` ← `assess_stall` past `silence_escalate_min`.
- `review(architect)` with no cadence = the **R5** post-block architect review; `review(reviewer)` with `cadence: every_n_blocks: reviewer_threshold` = the **R4** periodic reviewer.
- `findings-triage` is where the architect's judgment turns reviewer findings into fix blocks (R4→R6 path): `fixes` inserts fresh blocks into the pipeline and loops to `dispatch`; `none` advances.
- `escalate` covers **R3** (wall → operator) and `WORKER_UNRESPONSIVE` (stall). `resolved` resumes per the operator's `operator.decision`; `abort` ends the block/session per `operator.abort`.

**Persistent architect (R1)** is not a composed step — it is a session-lifecycle action `run.sh` performs at session start (`dispatch(architect)` once, stays alive in BG until session-end). The composition's `dispatch` steps are per-block workers.

**Peer-consult (R2)** is not a transition — engineer↔architect exchanges bypass TRON entirely; `classify_message` tags them `worker.question_peer` and the runner stays in place (observe only).

---

## 2. Situation-tag enum (closed)

`classify_message(text, ctx) → {tag, slots}` returns exactly one tag from this closed set (or `unclassified`). The enum is canon; blueprint-lint checks against it, never an open set.

### Worker-origin
| Tag | Meaning | Maps to |
|:--|:--|:--|
| `worker.done` | reports work complete | step edge `done` |
| `worker.wall` | hit a wall needing operator (UI/journey/operator-only/external) | step edge `wall` |
| `worker.findings` | reviewer/architect reporting findings | step edge `findings` |
| `worker.question_peer` | technical question for a declared peer (architect) | side: observe, no transition |
| `worker.question_tron` | question/decision directed at TRON | side: TRON answers from context, no transition |
| `worker.blocked_dep` | blocked on another block/dependency | side: mark block `blocked` in pipeline, no transition |
| `worker.progress` | status/heartbeat | side: none |

### Operator-origin (session or TG)
| Tag | Meaning | Maps to |
|:--|:--|:--|
| `operator.decision` | answer to an open escalation | step edge `resolved` (in `escalate`) |
| `operator.abort` | stop this block / the session | step edge `abort` |
| `operator.bug_report` | a defect to fix | side: scope a fix block into the pipeline |
| `operator.status_query` | asking for state | side: reply with digest |
| `operator.workflow_change` | change a rule/knob | side: `skill-edit-self` |
| `operator.directive` | general instruction | side: best-effort, may scope a block |

### System (produced deterministically, not by classify)
| Tag | Source | Maps to |
|:--|:--|:--|
| `sweep.tick` | cron → sweep.sh | run one bounded tick (§5) |
| `worker.stalled` | `assess_stall` true past `silence_escalate_min` | step edge `stalled` |
| `worker.dead` | process gone / `state.json` missing | side: purge + recover (re-dispatch same block) |
| `gate.pass` / `gate.fail` | gate check result | step edges `pass` / `fail` |

### Reserved
| Tag | Meaning | Maps to |
|:--|:--|:--|
| `unclassified` | classify returned out-of-enum, or invalid-output budget exhausted (§4) | **hardwired** edge → `escalate(reason=unclassified)` (canon, not composable) |

"Side" actions are global handlers in `run.sh` that do not advance the composed FSM; the active step is re-entered after handling.

---

## 3. Judgment-tool contracts

Every LLM touch is one of these. Schema-in / schema-out; the model returns a tag + structured slots, never free prose to the flow. Full schemas in `contracts/schema/` references; signatures here.

| Tool | Input | Output | Called by |
|:--|:--|:--|:--|
| **`classify_message`** | `{text, sender:{kind:worker\|operator, id?, role?}, current_step, open_escalation?}` | `{tag ∈ enum∪unclassified, slots:{…}, confidence:0..1}` | every primitive on inbound; the runner on TG/operator messages |
| **`triage`** | `{findings:[{id,file_line?,severity,desc}], block_ctx}` | `{verdicts:[{finding_id, agree:bool, severity}], fix_needed:bool}` | `findings-triage` |
| **`scope_fix`** | `{finding}` | `{goal, acceptance_criteria:[…], scope_bounds:{in:[…],out:[…]}, owner_role, deps:[…]}` | `findings-triage` (per agreed finding) |
| **`assess_wall`** | `{situation, block_ctx, project_operator_only:[…]}` | `{wall:bool, kind:backend\|ui\|operator-only\|external, rationale}` | `dispatch` when a worker message is ambiguous wall-vs-solvable |
| **`assess_stall`** | `{activity:{last_activity_delta_s, worktree_dirty:bool, mtime_grew:bool}, transcript_tail}` | `{stalled:bool, rationale}` | `dispatch`/sweep. Deterministic pre-filter first (if any activity signal is positive → `stalled:false` without an LLM call); LLM only resolves the ambiguous "slow vs stuck" case |

**Tiering:** `classify_message`, `scope_fix` → cheap model. `triage`, `assess_wall`, `assess_stall` (the ambiguous branch) → strong model. Wired in B3.

---

## 4. Invalid-output policy (G-2)

`run.sh` schema-validates every judgment-tool return.

1. **Valid** → use it.
2. **Invalid / malformed / out-of-enum tag** → retry the same call, appending `your previous output failed validation: <error>`. Budget: `MAX_LLM_RETRIES = 2`.
3. **Budget exhausted** → emit `unclassified` → hardwired `escalate(reason=invalid_output)`. Log the raw outputs to `logs/invalid-output-{date}.log`.

TRON never guesses, never improvises a flow decision from malformed output. An out-of-enum `tag` is itself a validation failure (the enum is closed in the tool schema).

---

## 5. Tick model (G-3)

Turn-based, no daemon. **One wake = one bounded tick.**

- **Trigger:** cron → `sweep.sh` → `claude --resume {TRON_ID} -p "[SWEEP] tick …"` (this exact path already exists in `scripts/sweep.sh`). Operator messages and TG inbound are drained within the same tick.
- **A tick:**
  1. **Load** `workflow-state.yaml` (the FSM cursor + counters + pipeline mirror).
  2. **One bounded pass:** poll TG inbox; sweep active workers (liveness probe, `assess_stall`); drain inbound messages → `classify_message` → map each to a step outcome edge or a side action; advance the FSM **at most as far as the available signals allow**.
  3. **Persist atomically.**
  4. **Exit.**
- **Atomic writes:** write `workflow-state.yaml.tmp`, then `mv` over the live file (rename is atomic on one filesystem). The live file is never left half-written.
- **Idempotency:** state is persisted only *after* the bounded pass completes, so a tick that crashes mid-LLM-call leaves the pre-tick state intact and the next wake safely re-runs the same classify/advance. World-mutating actions are state-guarded so a retried tick cannot double-fire:
  - spawn — guarded by `active_workers` (worker already present → skip);
  - escalate — guarded by `paused_for_operator` (already paused → skip);
  - release/kill — guarded by worker `status`;
  - dispatch history — `dispatched.log` keyed by `block_id + attempt`.
- A tick that has no actionable signal (worker still building) simply persists `last_sweep_at` and exits — no transition.

This is the "Temporal-lite durability" claim: atomic state + idempotent ticks ⇒ a crashed wake is safely retried.

---

## 6. Copy scope (G-4)

- **`messages.yaml` = runtime copy only.** Every line TRON emits during a *session* — to operator, worker, terminal, or Telegram — keyed by template id, with named slots. Rendered via `render(tag, slots)`.
- **Seeder voice is separate.** The greeting / sign-off / prompts in `tron-seed.md` are seeding-time copy and do **not** draw from `messages.yaml`. The two registries never share keys.
- **Tone authority:** the built-in TRON persona (landing-page voice — dark, dry, sardonic; no host-runtime names ever) is the canon floor and ships complete. The operator may **override individual templates** by editing `messages.yaml`; edited keys win, unedited keys keep the persona default. Persona and operator copy **coexist** — the operator extends, never has to author from empty.

---

## 7. `pipeline: host` accepted format (R-2)

When `pipeline: host`, TRON accepts the host doc **only** in this constrained shape:

- A single GitHub-flavored Markdown table.
- A header row whose columns map (by name or obvious equivalent) to **Order, ID, Owner, Status** (Notes optional).
- Each `Status` cell ∈ `{todo, in-progress, blocked, review, done}` (case-insensitive).
- One block per row.

Determinism guard: TRON parses the host table **once at session start** into a **normalized internal mirror** (`workflow-state.yaml › pipeline`), reads the mirror every tick, and **writes back to the host file only on status-change events** (done / blocked / review) — never a full rewrite every tick. If the host doc deviates from this shape, the **seeder** flags it and offers: reformat (operator) or switch to `pipeline: internal`. The rails never parse free-form prose.

---

## 8. Pipeline-tracking decision (R-3)

Internal `pipeline.md` **stays gitignored** (runtime state). Rationale: it mutates on every status change; tracking it would create churny commits and merge friction, and host-owned **specs** (tracked) already encode intent. **Accepted trade-off:** block-status *history* is not version-controlled. End-of-session status is captured in the session log (`logs/`). If history later matters, revisit by committing periodic snapshots — out of scope for the rebuild. A later block must not silently reverse this.

---

## 9. Blueprint-lint rules

Runs in `skill-doctor` / `skill-validate` (B3). A malformed flow fails at **seed/validate time, not runtime**.

### Canon-level (over `routing.yaml` + the tag enum)
- **L1** Each primitive declares exactly its fixed outcome-edge set (§1); no extra, no missing.
- **L2** Message-tag enum is closed; `unclassified` present with a hardwired `escalate` edge.
- **L3** Total tag coverage: every message tag maps to a step-outcome mapping or a global side action — no unhandled tag.
- **L4** Every judgment tool a primitive references has a contract (input + output schema) in `contracts/schema/`.
- **L5** No tool output reaches the flow as free prose — every tool's output schema is tag + structured slots.

### Composition-level (over `workflow.yaml` against `routing.yaml` + `project.yaml`)
- **L6** Every step's `primitive` exists in the library.
- **L7** Every outcome edge the primitive exposes is bound to a target — no unbound edge.
- **L8** Every target resolves to a real step id or a reserved target (`next`, `end`, `escalate`).
- **L9** No orphan steps — every step reachable from session-start.
- **L10** A terminal (`end`) is reachable from every step — no trap.
- **L11** Every `role` named in a step exists in `project.yaml › agents`.
- **L12** The `escalate` step is defined and the `unclassified` hardwired edge resolves to it.
- **L13** Every knob reference (`reviewer_threshold`, `cadence.every_n_blocks`, `max_concurrent_engineers`, …) resolves to a declared knob.

The composition is the seed-time author-error surface — L6–L13 are what the gate most needs to catch.

---

## 10. Boundary vs B2

This block defines **shapes**: the primitive library + edges, the closed tag enum, the judgment-tool contracts, the four file schemas, and the lint rules. **B2 authors the instances**: the embedded default composition (`workflow.yaml`), the actual `routing.yaml` edges + tag→action map, and the `messages.yaml` templates. No file content beyond schema stubs is authored here.

## 11. Open / carried watch-items
- **R-1** keep `run.sh` small; if YAML/JSON/render grows fragile in bash, factor a tiny non-bash helper (B3).
- **R-4** B2 may ship placeholder copy keyed to this tag enum so B3 can test before final copy lands.
