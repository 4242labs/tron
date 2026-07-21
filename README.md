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

> **New here?** [`GETTING_STARTED.md`](GETTING_STARTED.md) — requirements, the commands, and the file layout.

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
  their **own** detached checkout pinned to the engine-attested sha.
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
├── README.md · GETTING_STARTED.md · LICENSE · VERSION
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
└── evaluation/         # the SIM validation suite (harness + templates)
```

Change discipline: a new word goes in `engine/glossary.py` (`--write` regenerates the doc); a new
boilerplate is a new file under `engine/prompts/`; a process change is a `engine/workflow.toml` edit that
must survive the lint. Nothing is defined twice.

## Contributing

Pull requests welcome. TRON is a canon repo — one source of truth — so contributions extend the canon
itself: a sharper protocol, an engine or lint improvement, better docs. Per-project or machine-specific
assumptions live in seeded instances, never here.

Found a bug or have an idea? [Open an issue](https://github.com/4242labs/tron/issues/new/choose).

## Contributors

<!-- contributors:start -->
<a href="https://github.com/42piratas" title="42piratas"><img src="https://avatars.githubusercontent.com/u/18232600?v=4&s=64" width="64" height="64" alt="42piratas" /></a><a href="https://github.com/Basmatiii" title="Basmatiii"><img src="https://avatars.githubusercontent.com/u/91470583?v=4&s=64" width="64" height="64" alt="Basmatiii" /></a>
<!-- contributors:end -->

## License

Open source — [AGPL-3.0](LICENSE). Commercial — contact ahoy@42labs.io.
Both, in full: [LICENSING.md](LICENSING.md).

---
If it earned its keep, [coffee is appreciated](https://buymeacoffee.com/42piratas). ☕
