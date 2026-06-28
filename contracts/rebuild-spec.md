# Rebuild spec — behavior model + SENTRY design

**Status:** canon · **Block:** 01-01 (S1-01) · **Date:** 2026-06-28
**Authority above this doc:** the drawn flow (`workflow/workflow.html` + `workflow/flow-description.html`)
and `ADR-0001` (`tron-meta/adr/`). This spec bridges them to code; on any conflict the flow + ADR win.
**Consumed by:** 01-02 (config + PMT layer), 01-03 (SENTRY engine), 01-04…01-06. Nothing downstream is
pickable until this lands.

This is the **written behavior model**: the situations the engine answers (T1), the deterministic/judgment
boundary (T2), the sentry↔PMT map (T3), DONE as a prompted exchange (T4), and SENTRY's internal design
(T5). **Spec only** — no engine code; implementation is 01-02…01-06.

> Replaces, as the live reference, the stale `blueprint-contracts.md` (2026-06-05, on ADR §5's *replace*
> list — it still describes SCRIPTS, cron, and `block:next:done` against the pre-rebuild model). That file
> is rewritten in 01-03; until then this spec is the behavior authority.

---

## T1 — Situations catalog

Every situation the engine must answer end-to-end, each traced to its node(s) on the drawn flow. A
situation absent here is **out of scope for Phase 1**.

### A. Bootup (`ND-01 BOOTUP` — once per `tron start`)
| # | Situation | Node | Behavior |
|:--|:--|:--|:--|
| A1 | Refresh trunk + open PRs, build snapshot | ND-01 | read-only (`fetch` + ff-only + `gh pr list`); TRON never writes trunk |
| A2 | Stale trunk — refresh failed | ND-01 | **halt loud**, operator line sent *synchronously* (no MANIFEST exists yet); never a silent death |
| A3 | Fresh run — set scope | ND-01-08 SET SCOPE | AIDE converses free-form intent → concrete block ids; validate each exists + deps satisfiable; empty scope is legitimate on a first run |
| A4 | Fresh run — set counts | ND-01-09 SET COUNTS | `worker_count` (engineers+reviewers, shared pool) + `architect_count` (dedicated, pool-excluded); floor 1 each |
| A5 | Fresh run — write MANIFEST | ND-01 | scope + counts persisted to the MANIFEST (durable run-memory) |
| A6 | Resume — reconcile MANIFEST vs reality | ND-01 | a leftover MANIFEST means an interrupted run (clean end archives it); reconcile scope vs current pipeline |
| A7 | Resume — unreconcilable conflict | ND-01-14 RESOLVE | AIDE briefs operator → `repair` (re-reconcile) \| `restart` (discard, start clean) \| `halt` (archive MANIFEST first, then terminate); resolves entirely here |
| A8 | Bootup → first tick | ND-01 → convergence gateway → ND-02 | BOOTUP spawns **no agents**; hands to PULSE within the pool cap set here |
| A9 | Bootup conditional — TG opt-in | ND-01 | if seed configured Telegram, ask whether to notify via TG this run (terminal-only otherwise) — R-AWAIT |

### B. The tick (`ND-02 PULSE` — recurring bounded tick)
| # | Situation | Node | Behavior |
|:--|:--|:--|:--|
| B1 | Re-entry vs first-entry | convergence gateway (BOOTUP ⊕ WAKE → PULSE) | first tick enters from BOOTUP; every later tick from WAKE |
| B2 | Full tick (ceiling cadence) | ND-02 | refresh snapshot from trunk (costly `fetch`+PR), assess in-flight, advance gates, drain hopper, persist |
| B3 | Cheap tick (message-driven) | ND-02 | skip the network refresh (the message carries the news) — a chatty fleet never multiplies fetches |
| B4 | Drain the hopper — classify inbound | ND-02 (Route) | the sole LLM entrypoint (T2) — `classify_message` once per hopper message; each tagged then routed |
| B5 | Assess + settle each in-flight worker | ND-02-08 Settle | safe cases free the slot; ambiguous cases escalate (B7) |
| B6 | Flag DONE candidates | ND-02 (Flag candidates) | marks blocks that *might* be done — candidates only; the gate confirms (T4), never a trunk-read |
| B7 | Worker case needs operator | 02-09 Escalate? → 02-26 → ND-02-10 RESOLVE | raise-and-defer: brief operator, mark pending, tick continues; reply applied on a later tick by Settle |
| B8 | Operator-needed case (non-worker) | 02-25 Escalate? → 02-26 → ND-02-10 RESOLVE | same convergence; outcomes are case-dependent, carried in the reply |
| B9 | Reviews are PULL | ND-02 / ND-03 | each tick checks whether a review is due and fires it; never pushed on its own timer |
| B10 | Persist + exit | ND-02 | atomic save (`*.tmp` → `mv`); a crashed tick re-runs safely (at-least-once + dedupe) |
| B11 | Idle tick — no actionable signal | ND-02 → ND-03 (TICK END) | persist liveness marker, end the tick; next pulse re-arms via WAKE |

### C. Dispatch (`ND-03 SWITCHBOARD` — exclusive 3-arm gateway, exactly one per tick)
| # | Situation | Node | Behavior |
|:--|:--|:--|:--|
| C1 | Work to dispatch | ND-03 → AGENT | spawn/assign with its BRIEF (T3); priority: oldest adhoc → due-cadence reviewer (consume counter) → next block by pipeline order |
| C2 | Run-end condition holds | ND-03 → ANCHOR | the run terminates (teardown) |
| C3 | Idle tick | ND-03 → TICK END | this tick ends only; the run continues |
| C4 | Dispatch a **worker** (engineer) | AGENT | for a ready block; a block is in-flight iff it has a worker **or** an open PR **or** an active gate (safe re-assignment) |
| C5 | Dispatch a **reviewer** | AGENT | for a due milestone (cadence pull) |
| C6 | Dispatch/queue the **architect** | AGENT | persistent, pool-excluded, drains a FIFO `architect_queue` (MANIFEST); clears the path ahead, never reopens a done block |

### D. The AGENT sub-process (`AGENT` — one shape, every role)
| # | Situation | Node | Behavior |
|:--|:--|:--|:--|
| D1 | Merge-in: spawn or inbox | AGENT (BRIEF ⊕ AGENT INBOX) | a spawn BRIEF **or** an inbox message enters the work; only variables (name, work, prompt) differ by role |
| D2 | Do the work | AGENT | reads its per-task prompt (a PMT, T3) |
| D3 | Outcome leaves | AGENT → FLEET INTAKE | result \| in-flight problem \| question \| verdict — all exit via FLEET INTAKE into TRON's transport |
| D4 | Wait for reply/next work | AGENT INBOX | the agent waits at its **ID-addressed** inbox; no agent ends its own process (R7) |

### E. The DONE gate (prompted challenge — detailed in T4)
| # | Situation | Behavior |
|:--|:--|:--|
| E1 | Candidate flagged → open the gate | start the prompted exchange against PMT-GATE-DONE |
| E2 | Validate-local | judge on evidence the worker ran the local suite — not its `✅` |
| E3 | Authorize-push | gate authorizes the push only after E2 passes |
| E4 | PR → trunk | confirm the PR + its CI on trunk |
| E5 | Deploy-if-declared | if the block's `Deploy:` says so, confirm the deploy check |
| E6 | Gate fails a step | re-prompt with the specific gap (`gate.step`); never advance on a bare claim |

### F. Operator channel (`ND-09 PARLEY` — synchronous, separate from PULSE + hopper)
| # | Situation | Verb | Behavior |
|:--|:--|:--|:--|
| F1 | pause | command (act) | **hard**: broadcast "pause asap" to every agent + interrupt in-flight (R-HALT) |
| F2 | drain | command (act) | **soft**: stop dispatching new work; in-flight finishes (R-HALT) |
| F3 | resume | command (act) | clear pause/drain; dispatch restarts next tick (R-HALT) |
| F4 | halt | command (act) | terminate the run (archive-on-end); no resume (R-HALT) |
| F5 | rescope | command (act) | change the in-scope range mid-run |
| F6 | operator.decision | decision (act→PULSE) | reply to a parked escalation; handed to 02-08 Settle |
| F7 | status / inspect | query (answer) | read snapshot/MANIFEST; no state change |
| F8 | ask | ask (answer) | AIDE answers from Project Docs; if it can't, the question goes to the architect and AIDE relays the answer on a later tick |

### G. Agent consult (peer, R2)
| # | Situation | Behavior |
|:--|:--|:--|
| G1 | Worker → declared peer (e.g. engineer ↔ architect) | addressed directly; classify tags `worker.question_peer` → side: observe — the engine stays put, TRON does not relay |

### H. Liveness, restart, teardown
| # | Situation | Node | Behavior |
|:--|:--|:--|:--|
| H1 | Silence sweep → ping | engine side-system | worker silent `silence_ping_min` → `heartbeat.ping`; **engine-driven, not worker heartbeats** |
| H2 | Stalled/dead worker | engine side-system → `worker:stalled` | silent past `silence_escalate_min` → single `worker:stalled` trigger; recover per R-SUBSTRATE |
| H3 | Resume-by-id recovery | R-SUBSTRATE | reattach a crashed agent session; (1) resuscitate its tmux session and resume in place, else (2) fresh tmux session, resume the agent session into it — never re-dispatch from scratch |
| H4 | Run-end / teardown | ND-03 → ANCHOR | end the run; archive the MANIFEST; release agents (engine releases, never self-terminate) |
| H5 | WAKE scheduling | ND-08 WAKE | after a COOLDOWN floor, wake on first of {message in hopper, CEILING timer}; bounded both ways (cooldown ≤ gap ≤ ceiling) |

---

## T2 — Deterministic vs. the one judgment

**`classify_message` is the sole LLM entrypoint; every other step is deterministic code.** It is the only
place the engine calls the model — a tick draining *k* hopper messages calls it *k* times (once per
message, B4 / ND-02 Route); a tick with an empty hopper makes no LLM call at all. The invariant is *which
step is the model touch*, not a per-tick count. The R-MOD seal depends on this boundary being unambiguous.

### The single judgment — `classify_message`
- **Input:** `{text, sender}`. **Output:** `{tag ∈ closed-enum ∪ unclassified, slots, confidence}`.
- It **only tags** an inbound message — it never reads or rewrites the body, and never chooses the next
  step. The engine maps the tag → a trigger/side/tick deterministically.
- Schema-in / schema-out, retry-bounded (`invalid_output.max_retries`); on exhaustion → `unclassified`.

### Everything else is deterministic — no LLM
| Step | Why deterministic |
|:--|:--|
| Transport (intake → hopper → claim → route → deliver) | mechanical pipeline; classify only *tags*, never routes |
| Routing grammar / tag→trigger map | a closed table lookup (`routing.yaml`) |
| SWITCHBOARD work selection (ND-03) | fixed priority: adhoc → due-cadence → next block |
| DONE gate (T4) | evidence checks at each step — a checklist, not a judgment call |
| Settle / escalation routing (02-08/09/25/26) | state-guarded branches; the *content* of a reply is the operator's, not the model's |
| Cadence (PULL) | counter arithmetic vs threshold |
| Liveness sweep (H1/H2) | timers vs `silence_*` knobs |
| Scheduling (WAKE, ND-08) | COOLDOWN/CEILING timers |
| Bootup scope/count validation (A3/A4) | id-exists + deps-satisfiable checks (AIDE *converses* to gather intent, but the **validation that crosses to the engine** is deterministic) |

### Not a judgment tool, by design (retired/never)
`assess_wall` — **retired**. An unclassifiable input routes to the **architect** (T5), who steers it with
project context; TRON makes **no** second LLM judgment about whether something is the operator's problem.
Also not judgment calls: review verdicts (review is a milestone → architect log-review), findings-triage
(architect's log-review skill), stall detection (engine liveness side-system).

> **Drift to fix (01-03), surfaced not reconciled:** `tron.md` currently says "exactly **two**" judgment
> calls (a residue of the retired `assess_wall`), while describing only `classify_message` and stating "the
> only judgment you make." `routing.yaml`, `blueprint-contracts.md`, `context.md`, and ADR-0001 all say
> **one**. The settled model is **one**; the `tron.md` "two" is stale copy on ADR §5's *replace* list — fix
> it when `tron.md`'s judgment sections are rewritten in 01-03.

---

## T3 — Sentry↔PMT map

Which milestones/nodes **prompt an agent** (carry a `PMT-*`) and which don't. Per ADR R-PMT: a PMT is a
self-contained, slot-filled prompt, referenced **by id** through a registry and imported **at tick**.
Id scheme **`PMT-<ROLE>-<PURPOSE>`** (or `PMT-<PURPOSE>` when generic) — R-PMT.5. The diagram draws these
generically (`PMT-BRIEF`, `<PMT-*>`); the role-keyed file is the variable the single AGENT fills (ADR §13).
A PMT may surface through a **node** *or* through a **message** (R-PMT.2) — the worker-channel
`messages.yaml` lines **reference** a PMT body, never inline it (M-04).

### Prompts an agent — carries a PMT
| Node / milestone | Origin | PMT id | Today's `messages.yaml` ref |
|:--|:--|:--|:--|
| Dispatch engineer (C4) | ND-03 → AGENT BRIEF | `PMT-ENG-BRIEF` | `spawn.engineer` |
| Spawn architect (C6) | ND-03 → AGENT BRIEF | `PMT-ARCH-BRIEF` | `spawn.architect` |
| Architect clear-ahead (C6) | AGENT INBOX | `PMT-ARCH-FORWARD` | `arch.forward` |
| Architect log-review (C6) | AGENT INBOX | `PMT-ARCH-LOGREVIEW` | `arch.log` |
| Architect triage (T5 unclassified path) | AGENT INBOX | `PMT-ARCH-TRIAGE` | `arch.triage` |
| Dispatch reviewer (C5) | ND-03 → AGENT BRIEF | `PMT-REV-BRIEF` | `spawn.reviewer` |
| DONE gate challenge (T4) | ND-02 gate | `PMT-GATE-DONE` | `gate.step` |
| Liveness ping (H1) | engine side-system | `PMT-PING` | `heartbeat.ping` |
| Release worker (H4) | ND-02 Settle / ANCHOR | `PMT-RELEASE` | `release.worker` |

### Does **not** carry a PMT — operator/terminal copy stays inline (human-facing, `messages.yaml`)
`terminal.*` (between-task feedback), `escalate.*` (operator/wall copy — AIDE composes the freeform
`detail` inside escalation), `tg.*` (Telegram), `session.*` (lifecycle). These address the **operator**,
not an agent, so they are rendered copy — not prompts. (AIDE is operator-facing only; its sole worker
contact is the stateless classify tag.)

> **Authorship boundary (R-PMT).** This map names the PMT **set + ids** the engine references; the operator
> authors the prompt **content** later (R-PMT seam 2). The id list above is movable (T5) — adding/removing a
> PMT is a content decision, not an engine change.

---

## T4 — DONE as prompted exchanges

The DONE milestone is a **prompted challenge sequence**, never the worker's `✅` and never bare trunk
presence (D1). `Flag candidates` (ND-02) only marks a block that *might* be done; the gate settles it.
Driven by `PMT-GATE-DONE`; the engine judges on **evidence at each step**.

```
Flag candidate (ND-02)
   └─> validate-local   ── evidence the local suite ran clean ──> pass ─┐  fail ─> re-prompt (gate.step)
   └─> authorize-push   ── only after validate-local passes ──────────> │
   └─> PR → trunk       ── PR exists + CI green on trunk ──────────────> │
   └─> deploy-if-declared ─ block `Deploy: check` → deploy verified ───> │
                                                                         └─> DONE
```

- **Validate-local** — the gate prompts for, and judges, evidence the worker ran the block's acceptance
  suite locally. A bare "done" fails the step.
- **Authorize-push** — the push is gated; the engine authorizes it only once local validation holds.
- **PR → trunk** — the engine confirms the PR landed and its CI is green on trunk (read-only).
- **Deploy-if-declared** — only when the block header declares `Deploy: check`; otherwise skipped.
- **Fail** at any step → re-prompt with the specific gap (`gate.step`), never advance.
- **PULSE never merges** — gates only advance state; the engineer merges once a review passes (the
  two-gate merge model is 01-05's; this gate is the *DONE* challenge, not the merge act).
- **No operator-approve-before-merge** (D5 / TD-02): a completed review fans out (release reviewer +
  architect log-review); the operator gate is the wall/escalation path only. `escalate.merge` /
  `operator.decision = approve(merge)` are **removed**, not modeled here.

01-03 builds the engine gate from this section.

---

## T5 — SENTRY internal design

SENTRY is the **reactive element** of the standing trio (PULSE · SWITCHBOARD · SENTRY) — the `*` catch-all,
**redrafted from scratch**, replacing SCRIPTS. It is the path every inbound message takes once classified,
and the safety net for anything that doesn't fit. (ADR §8's one deferred piece; resolves ADR §12 item 2.)

### Classify grammar (the closed tag enum)
`classify_message` returns exactly **one** tag. Each tag maps to exactly one action — `trigger` (the flow
advances), `side` (a handler runs, no advance), or `tick` (run one bounded tick). Closed enum + total
coverage, lint-enforced.

**Trigger grammar (closed)** — every trigger matches exactly one form:
`domain:object` (dispatch) · `subject:event` (completion) · `subject:object:event` (qualified completion);
plus `*` (the SENTRY catch-all), `|` (alternatives), terminals `end` / `-`. Match is **most-specific-wins**
(literal > `<type>`/`<block>` > `*`).

### The tag set (updated from the drifted `routing.yaml` per ADR)
| Origin | Tag | Action |
|:--|:--|:--|
| worker | `worker.done` | trigger → DONE gate candidate (T4) |
| worker | `worker.wall` | trigger → operator escalation (02-09) |
| worker | `worker.review_done` | trigger `review:<type>:done` |
| worker | `worker.await_confirm` | trigger → **always reaches the operator** (D7 / R-AWAIT); no rung auto-clears |
| worker | `worker.question_peer` | side: observe (R2 peer-consult; no advance) |
| worker | `worker.question_tron` | side: answer-from-context |
| worker | `worker.progress` | side: none (heartbeat) |
| architect | `architect.reconciled` | trigger `block:<block>:reconciled` (**renamed** from `cleared`/`clear`, M-05) |
| architect | `architect.logged` | trigger → adhoc blocks authored |
| operator | `operator.decision` | trigger → Settle (02-08) |
| operator | `operator.status_query` | side: reply digest |
| operator | `operator.knob_change` | side: edit knob/rule (**renamed** off the prior "workflow" misnomer — M-01/ADR §12.1) |
| operator | `operator.directive` | side: best-effort |
| system | `worker.stalled` / `worker.dead` | trigger `worker:stalled` (engine liveness; **not** from classify) |
| reserved | `unclassified` | trigger `*` → SENTRY catch-all → **architect triage** |

**Changes from the current (drifted) tag map, per ADR §5:**
- `architect.cleared` → **`architect.reconciled`**; `block:<block>:clear` → `block:<block>:reconciled`
  (M-05 — "reconciled" = re-checked an upcoming block against the just-finished one's drift; `cleared`
  collided with the retired done-status).
- **Add `worker.await_confirm`** (D7 / R-AWAIT) — terminal always, +TG if opted in.
- **Remove** the operator merge-approve path (`escalate.merge`, `operator.decision = approve(merge)`) (D5).
- **`operator.knob_change`** (operator side-action) — named off the "workflow" misnomer the rebuild is
  killing (M-01 / ADR §12.1); it edits a per-project knob, not "the workflow".
- Every message is **ID-addressed** to a specific agent (D4) — delivery targets `<AGENT-ID>`'s inbox, never
  a role; classify tags the message, the engine resolves the target id.
- `sweep.tick` is subsumed by WAKE-driven ticks (ND-08); the cron tick source is removed (D6).

### Unclassified → architect triage (the catch-all path)
When a message won't sit in the enum — or the invalid-output retry budget is exhausted — it becomes
**`unclassified`** → the `*` catch-all → the engine **hands it to the architect** (`PMT-ARCH-TRIAGE`):
- solvable as upcoming work → the architect scopes it forward;
- truly the operator's call → the architect says so, and **only then** does it become a wall (R3).

TRON makes **no** second LLM judgment about whether something is the operator's problem — that steering
belongs to an agent with project context, never to a one-shot model call. **Nothing dead-ends at Route.**

### Invalid-output policy
Schema-validate every classify return → **valid:** use it · **invalid/out-of-enum:** retry with the
validation error appended (budget `invalid_output.max_retries`, default 2) · **exhausted:** `unclassified`
→ architect triage. Raw invalid outputs are logged (forensic record, 01-06).

### Locked vs. movable
**Locked** (canon — a change here is a diagram/ADR change, consult-first):
- the four-layer architecture (transport / control / judgment / content) and the **single-classify** boundary (T2);
- the `unclassified → architect` rule (no second LLM judgment; `assess_wall` stays retired);
- the trigger grammar **forms** + most-specific-wins matching;
- **ID-addressing** every message (D4); **prompted-DONE** (T4); reviews are **PULL**; raise-and-defer escalation.

**Movable** (S1-era work may still adjust, within the locked discipline):
- the exact **tag enum membership** — tags may be added/renamed (e.g. `await_confirm` shape) as long as the
  enum stays closed + totally covered;
- the **PMT set + ids** (T3) — content authorship is the operator's (R-PMT);
- knob **defaults** (COOLDOWN ≈ 5s, CEILING ≈ 30s, cadence, `silence_*`) — fixed knobs, edited in the file;
- the precise **trigger/handler names** the engine binds, pending 01-03;
- the **MANIFEST run-state filename** — **resolved in 01-02**: the run-state file is now `manifest.yaml`
  (ADR §12.1, off the prior "workflow" misnomer; the run-state *is* the MANIFEST).

---

## Conformance

This spec asserts no item that contradicts ADR-0001 or the drawn flow (AC-5). Open items are explicitly
deferred to their owning block (01-02 naming/PMT-content, 01-03 engine + `tron.md` fix, 01-05 two-gate
merge, 01-06 forensic log) — none reopen a locked decision.
