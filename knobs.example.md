# knobs.yaml — Example (embedded default)

The per-project **knobs** for this project. TRON ships with this default already in place — it works
out of the box. During seeding TRON explains it and asks whether it fits; the operator changes any
knob in natural language and TRON applies the edit (it owns `knobs.yaml`). TRON re-reads on
session start.

**What this file is — and isn't.** TRON's *behaviour* is a fixed **event table** (the canon flow:
`trigger → step → on-complete`, driven by PULSE + SWITCHBOARD) — the engine's table, the same for
every project. It is **not** edited here. This file holds only the **per-project knobs** the engine
reads. The live counters TRON tracks (pipeline statuses, cadence, architect queue, active workers)
live in the MANIFEST (`manifest.yaml`).

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
- **R4 — Reviewer cadence is PULL.** A per-type counter increments on every block that lands `✅`
  on trunk; when it reaches that type's threshold, SWITCHBOARD dispatches a reviewer and resets the
  counter. **Review is a milestone, not a verdict** — the reviewer delivers a findings log; the
  architect's log-review decides what becomes work.
- **R6 — Fresh worker per block.** Each block gets a freshly spawned worker. A block is dispatchable
  only when its block file is `📋` with every `Depends on` already `✅` on trunk; the architect clears
  the path forward by authoring block files. Pipeline order is preference; block `Depends on` are the
  hard gates.
- **R7 — Workers never self-terminate.** Only the engine releases a worker, after an explicit RELEASE.
- **R8 — Protected branches.** No agent commits directly to a protected branch; work lands on a
  feature branch through review.

---

## Per-session knobs (TRON asks at start; each shows a recommended default where one applies)

TRON asks for these at the start of every session and will not proceed until they're answered.
Live values land in the MANIFEST (`manifest.yaml`); the model answer also writes straight into
`knobs.yaml`'s `worker_model` map.

| Knob | Notes |
|:--|:--|
| `worker_count` | Size of the worker pool — **engineers + reviewers share it**. The architect is **extra** (not counted). Actual concurrency = min(this, dispatchable work). |
| `worker_model.architect` | The model the persistent architect runs on. TRON offers a recommended default (a strong tier, e.g. Opus — or the project's own `agents[].model` if declared) to confirm or override. |
| `worker_model.other` | The model every non-architect role runs on — engineers and reviewers **share this one tier**. TRON offers a recommended default (a fast tier, e.g. Sonnet) to confirm or override. |

## Fail-closed, per role (no baked default anywhere in the engine)

`worker_model` is a MAP with two keys, `architect` and `other`, each an explicit, declared,
project-owned input resolved **independently**. Unlike `worker_count` (which just re-prompts on a
bad answer), a role whose key ends up null/absent is **never** silently given a default: that
role's spawn path refuses outright rather than run a worker on the host CLI's own ambient default
(the root cause of an unattributed credit drain this knob closes — 01-21, made per-role by 01-30).
This holds identically for a **headless** caller that bypasses the interactive bootup prompt
entirely (calls `eng.start()` directly): the model must already be resolved in `knobs.yaml` before
that call, or the spawn for that role refuses the same way.

## Fixed knobs (set once; edit `knobs.yaml` to change)

| Knob | Default | Notes |
|:--|:--|:--|
| `architect_count` | 1 | Persistent architect queue drainers — the throughput bottleneck knob. |
| `git` | on | Whether the build commits via git (feature branch + review). |
| `silence_ping_min` | 6 | Worker silent this many minutes → heartbeat ping. Multiple of the wake cadence. |
| `silence_escalate_min` | 8 | Silent past this → engine emits `worker:stalled` (> ping). |
| `gate_nudge_after` | 2 | × `wake_ceiling_sec` of continuous runner-idle at a gate stage → re-send the stage prompt once. Keep < `gate_idle_cap`. (Default ceiling 30s → nudge at 60s idle.) |
| `gate_idle_cap` | 3 | × `wake_ceiling_sec` of continuous idle at one gate stage → escalate. (Default → 90s idle.) |
| `gate_close_cap` | 3 | × `wake_ceiling_sec` of idle at close → force-release the slot. (Default → 90s idle.) |
| `case_reping_after` | 20 | × `wake_ceiling_sec` between operator re-pings of a parked case. (Default → every 10 min.) |
| `case_reping_max` | 3 | Unanswered re-pings before the case **safe-parks** — named, resumable; the session runs on and the case settles on your reply at any later time. (Defaults → parked at 40 min.) |
| `wake_cooldown_sec` | 5 | WAKE min-gap floor (seconds): the shortest interval between ticks — debounces a chatty fleet so messages don't multiply fetches. |
| `wake_ceiling_sec` | 30 | WAKE max-latency ceiling (seconds): a tick fires by now even with no message — the cadence timer that lived in the old METRONOME. Must be ≥ `wake_cooldown_sec`. |

The two WAKE knobs bound every pulse: `cooldown ≤ gap ≤ ceiling`. The daemon (the in-process
scheduler) reads them; they are never asked at start and never changed by a runtime command.

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

## Counters (live in the MANIFEST `manifest.yaml` — do not hand-edit)

TRON updates these every tick:

- `pipeline` — the read-only trunk view, rebuilt each wake (id, order, status, deps, gates); never authority
- `active_workers` — spawned workers (id, role, status, block) + the architect (status, current_job)
- `architect_queue` — queued forward/log jobs
- `gate` — per-block DONE-gate progress; `seen_done` — ✅ blocks already counted for cadence
- `cadence` — per-type count of ✅-on-trunk blocks since last review
- `counters` — stall counts, paused-for-operator, etc.
- `session.started_at`, `last_sweep` — set on cold start / each tick

**Changing a knob:** describe it to TRON in natural language; TRON edits `knobs.yaml`.
`validate` flags any mismatch on next session start.
