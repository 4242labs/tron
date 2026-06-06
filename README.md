<p align="center">
  <img src=".github/tron-logo.svg" alt="TRON" width="340" />
</p>

<p align="center">
  A deterministic supervisor that builds software from specs — one agent you talk to; it runs the fleet.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue.svg" alt="License: AGPL-3.0" /></a>
  <a href="https://github.com/42piratas/tron/graphs/contributors"><img src="https://img.shields.io/github/contributors/42piratas/tron" alt="Contributors" /></a>
  <a href="https://github.com/42piratas/tron/wiki"><img src="https://img.shields.io/badge/docs-wiki-success.svg" alt="Wiki" /></a>
</p>

---

## What this is

You hand TRON a pipeline of spec'd work. TRON dispatches and supervises a fleet of worker agents —
an architect, engineers, reviewers — and drives the work to done. **You talk to TRON. TRON talks to
everyone else.**

The core is a **deterministic engine**, not a chatbot improvising. A fixed dispatch loop decides what
happens next by lookup, never by guesswork; the language model is called only for the actual building
and for two narrow, typed judgments. That makes the flow predictable, inspectable, and lint-checked
before it ever runs.

## What this isn't

- A production runtime for unattended app traffic.
- A multi-machine fleet manager.

---

## How it works

- **Pipeline.** Your work is a list of blocks, each tied to a spec, each with a status:
  `pending · cleared · in-progress · blocked · done · abandoned`.
- **The architect clears the way.** A single persistent architect — *forward-looking only* — reviews
  the work ahead and marks the next block `cleared`. Only a `cleared` block is dispatchable. It never
  reopens finished work; remediation is always a new block ahead.
- **Engineers build; reviewers check.** Engineers and reviewers share a worker pool (you set its size).
  An engineer takes one cleared block, validates against its acceptance criteria, and reports done.
- **Review is a milestone, not a verdict.** On a cadence you set (every N completed blocks), a reviewer
  delivers a findings log; the architect turns real findings into upcoming blocks.
- **Walls go to you.** Anything no worker can clear — an operator-only task, an external blocker, a
  call only you can make — parks the block and asks you. Everything short of that stays in the fleet.
- **It runs on its own.** A cron heartbeat wakes the engine on a fixed cadence; each wake is one
  bounded tick — fill free slots, clear ahead, wait, or end — and surfaces to you only what matters.

The engine spine (the dispatch loop + the work-selector) is code and never an LLM call. The LLM is
asked exactly two questions: *classify this inbound message* and, rarely, *is this really the
operator's problem?* Each is schema-in, schema-out — never free prose steering the flow.

## The flow

![TRON supervisor workflow — BPMN](diagrams/flow-bpm.svg)

---

## Requirements

- `python3` and `git`.
- `jq` (the shell connectors parse JSON).
- `crontab` (the autonomous heartbeat).
- A background-capable agent runtime on `PATH` — the runtime that runs the worker agents TRON
  dispatches. TRON drives it; you never address it directly.

## Commands

Two commands. Everything else is internal (the heartbeat, recovery, and validation run themselves).

| Command | What it does |
|:--|:--|
| `tron seeder` | Seed TRON into a target project — an interview that detects your repo, settles the knobs, and writes the instance. Touches only TRON's own folder. Run from the project root. |
| `tron start`  | Wake TRON — a short bootup (where to start, how many workers) then the live console: watch the fleet, talk to TRON, `stop` when you're done. |

```bash
# 1. From a canon clone, seed TRON into your project:
cd ~/code/my-project
~/code/tron/tron seeder

# 2. Wake it (from the seeded instance):
<agents>/tron/tron start
```

Inside `tron start`: type to talk to TRON; `status` / `pipeline` to look; `stop` to end.

---

## File layout — canon (this repo)

```
tron/
├── tron                    # the operator entrypoint (seeder · start)
├── README.md · LICENSE
├── tron.md                 # the judgment context (the two LLM calls run under this)
├── tron-seed.md            # the seeding protocol
├── routing.yaml            # the trigger grammar + inbound-message map (canon, never per-project)
├── workflow.yaml           # the default knobs (worker/architect counts, cadence, git)
├── messages.yaml           # every line TRON says, by template
├── engine/                 # the deterministic engine (dispatch loop, selector, judgment, lint)
├── skills/                 # how a worker behaves: engineer · reviewer · architect
├── protocols/              # lifecycle: bootup · session-end
├── scripts/                # thin shell connectors (heartbeat, worker→engine report, notifications)
├── templates/              # runtime-state seeds
├── contracts/              # design contracts + schemas
├── spec.example.md         # the spec contract a block is built from
├── project.example.yaml    # the project-profile shape the seeder fills
├── workflow.example.md     # the knobs, explained
└── pipeline.example.md     # the pipeline format + statuses
```

## File layout — your project (after `tron seeder`)

```
<agents>/tron.md            # the judgment context (copied)
<agents>/tron/
├── tron · engine/          # the entrypoint + the deterministic engine (canon, copied)
├── project.yaml            # this project's pointers, agents, repo facts
├── workflow.yaml           # this project's knobs
├── routing.yaml · messages.yaml · skills/ · protocols/ · scripts/   # canon, copied verbatim
├── pipeline.md             # the live pipeline (if the host keeps none)
└── …runtime state…         # workflow-state, logs, inboxes (gitignored, edited in place)
```

To remove TRON entirely: delete `<agents>/tron.md` and `<agents>/tron/`. No other traces.

---

## Design principles

> **Blueprint first, model second.** TRON's founding principle. The flow is a deterministic
> *blueprint* — a closed trigger grammar and an explicit event table, lint-validated before it ever
> runs. The *model* comes second: called only to do the building and to answer two bounded,
> schema-checked judgments — never to choose a step. Everything below follows from this.

- **Deterministic spine.** Flow is decided by code and a closed trigger grammar — lint-validated at
  seed time, so a malformed workflow fails before it runs, not during.
- **Two bounded judgments.** The only LLM calls into the flow are typed and schema-checked; the model
  never returns prose that steers a transition.
- **Architect out of the pool, forward-only.** Clearing throughput is the one knob that bounds speed;
  finished work is never reopened.
- **Every word is canon copy.** All operator- and worker-facing text comes from one registry — no
  backend narration ever reaches a human.
- **Crash-safe ticks.** State is persisted atomically; dispatch intent is committed before any spawn,
  and messages are processed at-least-once — a crashed wake retries cleanly.
- **Canon purity.** This repo carries zero project- or machine-specific traces; per-project values
  live only in the seeded instance.

---

## Contributing

Pull requests welcome. TRON is a canon repo — one source of truth — so contributions extend the canon
itself: a new worker skill or reviewer lens, a sharper protocol, an engine or lint improvement, better
docs. Per-project or machine-specific assumptions live in seeded instances, never here. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the clone → branch → PR → CI → merge flow.

Found a bug or have an idea? [Open an issue](https://github.com/42piratas/tron/issues/new/choose).

## Contributors

<!-- contributors:start -->
<a href="https://github.com/42piratas" title="42piratas"><img src="https://avatars.githubusercontent.com/u/18232600?v=4&s=64" width="64" height="64" alt="42piratas" /></a>
<!-- contributors:end -->

## License

Open source — [AGPL-3.0](LICENSE). | Commercial — contact **ahoy[at]42labs.io**.
