# tron

A deterministic workflow engine for a fleet of LLM builders. The process
is DATA — both spines: `workflow.toml` composes the pass spine (how a block
advances) and `workflow.ESCALATION` the exception spine (where a stuck seat's
signal goes, architect-first); the engine executes both, and the diagrams
(`WORKFLOW.md` + the interactive `workflow/` BPMN) are generated from those
same tables — drift is impossible. The model builds and judges; the engine
verifies, records, escalates, and lands.
Vocabulary: `GLOSSARY.md`. Voice to the operator: `voice.md`.

## Run

```
python3 tron.py            # asks for a project path (Enter = built-in demo)
python3 tron.py --watch    # long-running: idles, wakes on register work, STOP file exits
python3 tron.py --selftest # engine selftests — no agents, no tokens
python3 workflow.py        # flow lint + doc-sync selftests; --write regenerates WORKFLOW.md
python3 bpmn.py            # BPMN doc-sync selftests; --write regenerates workflow/
python3 gate.py            # truth-gate selftests (real throwaway git repos)
python3 tg.py              # telegram transport selftests (fake transport, no network)
python3 events.py          # event-vocabulary selftests; --write regenerates EVENTS.md
python3 harness.py project-01 3  # SIM harness: 3 SIMs of PROJECT-01, stats.md out
                           #   --parallel N seeds a project-owned flow with
                           #   [limits] max_parallel = N; --ablate ARM runs the
                           #   engine with ONE invariant disabled (experiment
                           #   arms for the paper: truth_gate, judge_isolation,
                           #   architect_first — loud at boot, typed in events)
python3 game.py            # the communication game (--seed N reproducible)
```

With `.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, gitignored) the
operator line rides Telegram: milestone notes at run start / block done /
run done, and pages that WAIT for the operator's reply there. Without it,
everything degrades to the terminal.

## Layout

```
workflow.toml  # THE process, as data: phases = actor+persona seats, words,
               #   gates, transitions, [limits] — lint refuses unsound flows
workflow.py    # parse + lint + WORKFLOW.md generator; ESCALATION = the
               #   exception spine as data (the engine routes from it)
WORKFLOW.md    # the diagram — GENERATED, never hand-edited
bpmn.py        # BPMN 2.0 generator: pass spine + escalation overlay, one source
workflow/      # workflow.bpmn + workflow.html (GENERATED, vendored bpmn-js
               #   viewer) — the interactive diagram; unpublished until 0.4.2
glossary.py    # the closed vocabulary: single-source dict + parser (+ doc gen)
GLOSSARY.md    # the vocabulary document — GENERATED from glossary.py
voice.md       # how TRON talks to operators (modular, editable)
prompts/       # every engine boilerplate, one file per prompt; personas too
prompts.py     # prompt loader; {gateway}/{persona} compose shared parts
agents.py      # persistent CLI seats + liveness guard (overrun -> probe the
               #   session -> re-issue once -> only then page: talk-first)
gate.py        # the truth gate: commits/trunk/tests/judge_copy/merge verbs
pipeline.py    # the register + engine-recorded documents (single writer)
roster.py      # session manifest + deterministic user report per run
transcript.py  # verbatim run logs (runs/) + operator paging (telegram-first)
tg.py          # the Telegram line (stdlib-only, graceful degrade)
events.py      # the typed event log: closed vocabulary (EVENTS.md GENERATED),
               #   one JSON line per engine decision — the measurement source
harness.py     # the SIM harness: N reps of a template, fresh git project
               #   each, aggregated stats.md from the event logs alone
bootup.py      # the FROZEN operator bootup journey (verbatim questions +
               #   AIDE, a REAL LLM advisor — advisory only, fail-open;
               #   piped stdin = no questions, all defaults)
tron.py        # the engine: one generic flow driver + dispatch + WAKE
game.py        # the communication game on the same engine parts
runs/          # per run: verbatim transcript + typed events.jsonl + manifest
               #   + report + the exact workflow.toml that drove it
sims/          # templates/<name>/ (plain-file SIM seeds) + one dir per
               #   harness batch: rep evidence + stats.md
```

## A project

Committed core docs: `context.md` (what it is), `principles.md` (conduct),
`playbook.md` (shared infra memory — agents UPDATE it when they learn
something durable), optional own `workflow.toml` (a committed flow
overrides the engine default — same lint bar), `policy.md` (acceptance
bar), `blocks/*.md` (each may declare `test:` and `trunk-test:` commands),
and `pipeline.md` — the permanent register, written ONLY by the engine.
`decisions.md` stays UNTRACKED (architect-exclusive by physics: worktrees
never materialize it). Operator channels, structural by filename:
`parley.md` (question -> architect answers from artifacts),
`report-request.md` (-> architect writes, engine records under reports/).

Dispatch: every block whose deps are done (parallel, cap 2), each to fresh
seats in an engine-made worktree arena on the block's own branch. Judges
read the delivery in their OWN detached checkout pinned to the
engine-attested sha. The gate never trusts a claim: commits + untouched
trunk + engine-run tests + AC challenge; verdicts are recorded verbatim in
`reviews.md`; the WORKER owns the merge inside the single engine-wide
window; the engine performs the mechanical land, re-validates ON the
trunk, then the worker wraps (docs + session log + clean tree) before the
arena retires. Done = landed + trunk-green + wrapped. Every wall routes
architect-first; the operator is the last resort — and answers from
anywhere via Telegram. Crashed runs recover at boot: stray agent processes
killed, unverified branches preserved as `orphan/*`, blocks re-dispatched
fresh.

Change discipline: a new word goes in `glossary.py` (`--write` regenerates
the doc); a new boilerplate is a new file under `prompts/`; a process
change is a `workflow.toml` edit that must survive the lint. Nothing is
defined twice.

## Contributors

<!-- contributors:start -->
<a href="https://github.com/42piratas" title="42piratas"><img src="https://avatars.githubusercontent.com/u/18232600?v=4&s=64" width="64" height="64" alt="42piratas" /></a><a href="https://github.com/Basmatiii" title="Basmatiii"><img src="https://avatars.githubusercontent.com/u/91470583?v=4&s=64" width="64" height="64" alt="Basmatiii" /></a>
<!-- contributors:end -->
