<p align="center">
  <img src=".github/tron-logo.svg" alt="TRON" width="340" />
</p>

<p align="center">
  A deterministic orchestrator that builds software from specs (blocks) — one agent you talk to; it runs the fleet.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue.svg" alt="License: AGPL-3.0" /></a>
  <a href="https://github.com/4242labs/tron/graphs/contributors"><img src="https://img.shields.io/github/contributors/4242labs/tron" alt="Contributors" /></a>
  <a href="https://github.com/4242labs/tron/wiki"><img src="https://img.shields.io/badge/docs-wiki-success.svg" alt="Wiki" /></a>
  <a href="https://www.repostatus.org/#active"><img src="https://www.repostatus.org/badges/latest/active.svg" alt="Project Status: Active" /></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/maintenance-passively--maintained-yellowgreen.svg" alt="Maintenance: passively maintained" /></a>
</p>

---

## What this is

You point TRON at your project's pipeline. TRON dispatches and orchestrates a fleet of worker agents —
architects, engineers, reviewers — and drives the work to done. **You talk to TRON. TRON talks to
everyone else.**

The core is a **deterministic engine**, not a chatbot improvising. The process is *data*: `workflow.toml`
composes the pass spine (how a block advances) and `workflow.ESCALATION` the exception spine (where a
stuck seat's signal goes, architect-first). The engine executes both; the diagrams are generated from
those same tables, so drift is impossible. The model builds and makes a few narrow judgments; the engine
verifies, records, escalates, and lands.

**Not** a production runtime for unattended app traffic, and not a multi-machine fleet manager.

**What it needs from you.** TRON expects **complete, well-specified inputs**: each
block needs exact acceptance criteria, a declared test the engine can run, and
every dependency and asset present in the scaffold *before* it is dispatched. The
gate judges evidence, not intent — an under-specified block, a missing asset, or a
scaffold whose declared test can't run on a fresh trunk checkout will wall or halt
rather than improvise. A landing that leaves trunk red halts the run; recovery is
fix-the-spec-and-restart (boot re-dispatches crash-safely) or a remediation block
ahead — not an in-flight patch. TRON front-loads the work of a robust scaffold; it
doesn't substitute for it.

## Install

```bash
curl -fsSL https://tron.42labs.io/seed.sh | sh
```

Clones into `~/.tron`, puts `tron` on your `PATH`, then `tron start`. Idempotent, no `sudo`, no rc
edits — details and the manual `git clone` route in the [Getting Started](https://github.com/4242labs/tron/wiki/Getting-Started) wiki.

> **New here?** The [wiki](https://github.com/4242labs/tron/wiki) is the manual — [Getting Started](https://github.com/4242labs/tron/wiki/Getting-Started) covers requirements, the commands, and the file layout.

---

## How it works

- **The process is data.** `engine/workflow.toml` is the pass spine (phases = actor+persona seats, words,
  gates, transitions, limits); `workflow.ESCALATION` is the exception spine. A lint refuses an unsound
  flow before it ever runs. The diagrams (`docs/WORKFLOW.md`, the interactive `workflow/` BPMN) are
  **generated** from those tables — never hand-edited.
- **The architect clears the way.** A single persistent, forward-only architect scopes the work ahead by
  authoring the next block. A block is dispatchable once its file is ready with every dependency landed on
  trunk. Finished work is never reopened; remediation is always a new block ahead.
- **Engineers build; reviewers check.** Engineers and reviewers share a worker pool (you set its size).
  Each block runs in a fresh engine-made worktree arena on its own branch; judges read the delivery in
  their **own** detached checkout pinned to the engine-attested sha. The personas these agents run on
  (`engine/prompts/persona_*.md`) are a **default set you can edit or replace** for your own project.
- **The gate never trusts a claim.** "Reports done" is only a trigger. The gate runs the definition of
  done on the *evidence* — commits + untouched trunk + engine-run tests + an acceptance challenge; the
  worker owns the merge inside the single engine-wide window; the engine lands, re-validates **on trunk**,
  then the worker wraps (docs + session log + clean tree). Done = landed + trunk-green + wrapped.
- **Walls go to you.** Anything no worker can clear routes architect-first; the operator is the last
  resort — and answers from anywhere via Telegram.
- **Crash-safe.** Crashed runs recover at boot: stray agents killed, unverified branches preserved as
  `orphan/*`, blocks re-dispatched fresh. Every engine decision is one typed JSON line in `events.jsonl`
  — the single measurement source.

> **Blueprint first, model second.** The flow is a deterministic *blueprint* — a closed trigger grammar
> and an explicit event table, lint-validated before it runs. The *model* comes second: called only to
> build and to answer bounded, well-scoped judgments — never to choose a step.

## Layout

```
tron/
├── tron                # launcher — `tron start [project]`
├── install.sh          # the `curl … | sh` installer (the pretty URL redirects here)
├── README.md · CONTRIBUTING.md · LICENSE · LICENSING.md · VERSION
├── engine/             # the deterministic engine
│   ├── tron.py         #   the flow driver + dispatch + WAKE
│   ├── workflow.toml   #   THE process, as data (pass spine + limits)
│   ├── workflow.py     #   parse + lint + ESCALATION (exception spine)
│   ├── gate.py         #   the truth gate (commits/trunk/tests/merge)
│   ├── glossary.py     #   the closed vocabulary — single source
│   ├── events.py       #   the typed event log (the measurement source)
│   ├── bpmn.py         #   BPMN generator (pass spine + escalation overlay)
│   ├── agents.py · roster.py · pipeline.py · transcript.py · tg.py
│   ├── bootup.py       #   the FROZEN operator bootup journey
│   └── prompts/        #   every engine/persona prompt, one file each
├── docs/               # GENERATED reference: GLOSSARY.md · EVENTS.md · WORKFLOW.md; voice.md
├── workflow/           # GENERATED interactive BPMN diagram (vendored bpmn-js)
├── evaluation/         # the SIM validation suite (harness + templates)
└── paper/              # the preprint + evidence bundle (event logs, probes)
```

Change discipline: a new word goes in `engine/glossary.py` (`--write` regenerates the doc); a new
boilerplate is a new file under `engine/prompts/`; a process change is a `engine/workflow.toml` edit that
must survive the lint. Nothing is defined twice.

## Research

TRON's design and validation are written up in a preprint — *Demoting the Master
Control Program: Deterministic Orchestration of a Fleet of LLM Agents*
([doi.org/10.5281/zenodo.21613791](https://doi.org/10.5281/zenodo.21613791)).
The paper and the full evidence bundle (typed event logs, ablations, and two
third-party-oracle probes — MIT 6.5840 MapReduce and Raft) live under
[`paper/`](paper/); the [Validation &amp; Research](https://github.com/4242labs/tron/wiki/Validation-and-Research)
wiki page summarizes the results and how to cite.

## Contributing

**Closed to outside contributions.** TRON is the system measured in the preprint above, and a patch
stream through it would quietly invalidate what was published. Pull requests are not being accepted
and will be closed unmerged — that is about the paper, not about you.

Still open: **bug reports** ([open an issue](https://github.com/4242labs/tron/issues/new/choose)) and
**forks** — the AGPL-3.0 grants you exactly that, and a fork that moves faster than this repo is a
good outcome, not a betrayal. [`CONTRIBUTING.md`](CONTRIBUTING.md) stays published because it
describes how the repo actually works, which is what a fork inherits.

And if you'd like to talk — about the design, a result, or using TRON somewhere — reach out:
<ahoy@42labs.io>. That door is open even though this one isn't.

## Contributors

<!-- contributors:start -->
<a href="https://github.com/42piratas" title="42piratas"><img src="https://avatars.githubusercontent.com/u/18232600?v=4&s=64" width="64" height="64" alt="42piratas" /></a><a href="https://github.com/Basmatiii" title="Basmatiii"><img src="https://avatars.githubusercontent.com/u/91470583?v=4&s=64" width="64" height="64" alt="Basmatiii" /></a>
<!-- contributors:end -->

## License

Open source — [AGPL-3.0](LICENSE). Commercial — contact ahoy@42labs.io.

---
If it earned its keep, [coffee is appreciated](https://buymeacoffee.com/42piratas). ☕
