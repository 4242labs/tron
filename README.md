<p align="center">
  <img src=".github/tron-logo.svg" alt="TRON" width="340" />
</p>

<p align="center">
  A deterministic, spec-driven supervisor that builds software from specs (blocks) — one agent you talk to; it runs the fleet.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue.svg" alt="License: AGPL-3.0" /></a>
  <a href="https://github.com/4242labs/tron/graphs/contributors"><img src="https://img.shields.io/github/contributors/4242labs/tron" alt="Contributors" /></a>
  <a href="https://github.com/4242labs/tron/wiki"><img src="https://img.shields.io/badge/docs-wiki-success.svg" alt="Wiki" /></a>
</p>

---

## What this is

You point TRON at your project's pipeline. TRON dispatches and supervises a fleet of worker agents —
architects, engineers, reviewers — and drives the work to done. **You talk to TRON. TRON talks to
everyone else.**

The core is a **deterministic engine**, not a chatbot improvising. A fixed dispatch loop decides what
happens next by lookup, never by guesswork; the language model does the building and a few narrow,
well-scoped judgments. The flow is predictable, inspectable, and lint-checked before it ever runs.

**Not** a production runtime for unattended app traffic, and not a multi-machine fleet manager.

> **New here?** [`GETTING_STARTED.md`](GETTING_STARTED.md) — requirements, the two commands, and the file layout.

---

## How it works

- **Pipeline.** Your work is your project's own git-tracked pipeline — a living doc plus one file per
  block, each with an emoji status (`📋 to-do · 🔄 in-progress · ✅ done`, and a few non-active states).
  TRON only **reads** it; your agents write it via PR. TRON owns no pipeline, no agents, no work-unit format.
- **The architect clears the way.** A single persistent architect — *forward-looking only* — scopes the
  work ahead by authoring the next block's file. A block is dispatchable once its file is `📋` with every
  dependency `✅` on trunk. It never reopens finished work; remediation is always a new block ahead.
- **Engineers build; reviewers check.** Engineers and reviewers share a worker pool (you set its size).
  An engineer takes one block, validates against its acceptance criteria, and reports done.
- **Done means done.** "Reports done" is just a trigger. TRON runs the canon definition-of-done on the
  *evidence* — local checks, PR + green CI, merge, post-merge re-validation on trunk, deploy-clean +
  verify — and a block counts only when it shows `✅` on trunk. A merged branch that fails to deploy is
  not-done, and gets fixed.
- **Review is a milestone, not a verdict.** On a cadence you set (every N blocks that land `✅`), a
  reviewer delivers a findings log; the architect turns real findings into upcoming blocks.
- **Walls go to you.** Anything no worker can clear — an operator-only task, an external blocker, a call
  only you can make — parks the block and asks you. Everything short of that stays in the fleet.
- **It runs on its own.** A built-in heartbeat wakes the engine — early on a new message, at least every
  cadence ceiling otherwise. Each wake is one bounded tick: fill free slots, clear ahead, wait, or end.

The engine spine (dispatch loop + work-selector) is code, never an LLM call. The model is asked exactly
one question — *classify this inbound message* — schema-in, schema-out, never free prose steering the
flow. Anything it can't classify goes to the architect, not a second model call.

## The flow

The full workflow lives as interactive BPMN under [`workflow/`](workflow/): [`workflow.html`](workflow/workflow.html)
(core + drill-down sub-processes) and [`flow-description.html`](workflow/flow-description.html) (per-node notes).

---

## What TRON needs from your project

TRON reads your project's structure — it never scaffolds it. Before you seed, the project must provide
three things, all git-tracked and written by your agents via PR:

- **Agents.** Your own worker personas as `agents/<role>.md`. TRON dispatches them; it ships none and
  imposes none.
- **Blocks.** Your work, broken into right-sized units — one file per block (`blocks/<id>.md`) with a
  fixed header (status, dependencies, reviewer class, merge and deploy gates) plus acceptance criteria.
  A block is the unit TRON dispatches, gates, and drives to done.
- **A pipeline.** A living `pipeline.md` that orders the blocks into phases and tracks each one's status —
  fixed enough to read deterministically, loose enough to stay human-authored.

The 42labs `new-project-template` ships this structure ready-made — adopt it for a new project, or bring
an existing one up to it before seeding.

---

## Design principles

> **Blueprint first, model second.** TRON's founding principle. The flow is a deterministic *blueprint* —
> a closed trigger grammar and an explicit event table, lint-validated before it ever runs. The *model*
> comes second: called only to build and to answer one bounded, schema-checked judgment (classify a
> message) — never to choose a step. Everything below follows from this.

- **Deterministic spine.** Flow is decided by code and a closed trigger grammar, lint-validated at seed
  time — a malformed blueprint fails before it runs, not during.
- **One bounded judgment.** The only LLM call into the flow (classify a message) is typed and
  schema-checked; the model never returns prose that steers a transition.
- **Architect out of the pool, forward-only.** Clearing throughput is the one knob that bounds speed;
  finished work is never reopened.
- **Every word is canon copy.** All operator- and worker-facing text comes from one registry.
- **Crash-safe ticks.** State is persisted atomically; dispatch intent is committed before any spawn,
  and messages are processed at-least-once — a crashed wake retries cleanly.
- **Canon purity.** This repo carries zero project- or machine-specific traces; per-project values live
  only in the seeded instance.

---

## Contributing

Pull requests welcome. TRON is a canon repo — one source of truth — so contributions extend the canon
itself: a new worker skill or reviewer lens, a sharper protocol, an engine or lint improvement, better
docs. Per-project or machine-specific assumptions live in seeded instances, never here. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the clone → branch → PR → CI → merge flow.

Found a bug or have an idea? [Open an issue](https://github.com/4242labs/tron/issues/new/choose).

## Contributors

<!-- contributors:start -->
<a href="https://github.com/42piratas" title="42piratas"><img src="https://avatars.githubusercontent.com/u/18232600?v=4&s=64" width="64" height="64" alt="42piratas" /></a><a href="https://github.com/Basmatiii" title="Basmatiii"><img src="https://avatars.githubusercontent.com/u/91470583?v=4&s=64" width="64" height="64" alt="Basmatiii" /></a>
<!-- contributors:end -->

## License

Open source — [AGPL-3.0](LICENSE). | Commercial — contact **ahoy[at]42labs.io**.
