# workflow.md — Example (embedded default)

The per-project **knobs** for this project. TRON ships with this default already in place — it works
out of the box. During seeding TRON explains it and asks whether it fits; the operator changes any
knob in natural language and TRON applies the edit (it owns `workflow.yaml`). TRON re-reads on
session start.

**What this file is — and isn't.** TRON's *behaviour* is a fixed **event table** (the canon flow:
`trigger → step → on-complete`, driven by PULSE + SWITCHBOARD). That table is the same for every
project and is **not** edited here — see `contracts/blueprint-contracts.md` and the workflow CSV.
This file holds only the **per-project knobs** the engine reads. The live counters TRON tracks
(pipeline statuses, cadence, architect queue, active workers) live in `workflow-state.yaml`.

---

## Standing rules (the invariants the flow runs under)

These are canon — true on every project. They are not knobs.

- **R1 — Architect is persistent and forward-only.** One architect is spawned at start and stays
  alive until session-end. It is **excluded from the worker pool** and drains a FIFO queue. It
  **clears the next block** (forward-review) and turns reviewer findings into **upcoming** adhoc
  blocks (log-review); it never reopens a done block. It is also the standing peer-consult.
- **R2 — Workers consult workers.** Declared peer pairs (engineer ↔ architect, …) address each
  other directly. TRON observes; it does not relay or transition.
- **R3 — A wall goes to the operator.** A blocker no worker can clear (operator-only task, external
  blocker, human-eyes-on-a-journey, true impasse after the architect was consulted) parks the block
  `blocked`, frees the slot, and contacts the operator. `operator:decision` resumes / amends / abandons it.
- **R4 — Reviewer cadence is PULL.** A per-type counter increments on every completed block; when
  it reaches that type's threshold, SWITCHBOARD dispatches a reviewer and resets the counter.
  **Review is a milestone, not a verdict** — the reviewer delivers a findings log; the architect's
  log-review decides what becomes work.
- **R6 — Fresh worker per block.** Each block gets a freshly spawned worker. Only a `cleared` block
  is dispatchable; the architect clears blocks forward. Pipeline `Order` is preference; spec
  `Dependencies` are the hard gates.
- **R7 — Workers never self-terminate.** Only the engine releases a worker, after an explicit RELEASE.
- **R8 — Protected branches.** No agent commits directly to a protected branch; work lands on a
  feature branch through review.

---

## Per-session knob (TRON asks at start; no default)

TRON asks for this at the start of every session and will not proceed until it's answered. Live
value lands in `workflow-state.yaml`.

| Knob | Notes |
|:--|:--|
| `worker_count` | Size of the worker pool — **engineers + reviewers share it**. The architect is **extra** (not counted). Actual concurrency = min(this, dispatchable work). |

## Fixed knobs (set once; edit `workflow.yaml` to change)

| Knob | Default | Notes |
|:--|:--|:--|
| `architect_count` | 1 | Persistent architect queue drainers — the throughput bottleneck knob. |
| `git` | on | Workflow commits (feature branch + review). |
| `silence_ping_min` | 6 | Worker silent this many minutes → heartbeat ping. Multiple of the cron cadence. |
| `silence_escalate_min` | 8 | Silent past this → engine emits `worker:stalled` (> ping). |

## Reviewer cadence (PULL)

`cadence` maps each reviewer **type** to the number of completed blocks between its reviews. Types
are open (`code`, `security`, `data`, …). Default ships one:

```yaml
cadence:
  code: 3        # a code reviewer every 3 completed blocks
```

Add a type to schedule another lens; drop one to stop that cadence.

## Peer consults

Workers may consult declared peers without going through TRON — only on the project's list (canon
ships none; the seeder sets them per project). A markdown/`yaml` list of `worker → may-consult → for`
pairs. Enforcement is by construction: TRON only shares a peer's session in handovers per this list.

```yaml
peer_consults:
  - { worker: engineer, may_consult: architect, for: "technical/design questions" }
```

---

## Counters (live in `workflow-state.yaml` — do not hand-edit)

TRON updates these every tick:

- `pipeline` — the normalized block mirror (id, order, owner, status, kind)
- `active_workers` — spawned workers (id, role, status, block) + the architect (status, current_job)
- `architect_queue` — pending forward/log jobs
- `cadence` — per-type count since last review
- `counters` — stall counts, paused-for-operator, etc.
- `session.started_at`, `last_sweep` — set on cold start / each tick

**Changing a knob:** describe it to TRON in natural language; TRON edits `workflow.yaml`.
`validate` flags any mismatch on next session start.
