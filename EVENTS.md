# tron-reborn — the event vocabulary

> GENERATED from `events.py` (the single source). Edit the EVENTS
> table there, then run `python3 events.py --write`. Selftests
> fail when this file is stale.

Each run writes `runs/<run>.events.jsonl` — one JSON object per
line: `ts` (epoch seconds), `t` (a type below), plus the fields
named at the emission site. The engine is the only writer. An
unknown type raises at emit time — the vocabulary is CLOSED.

| Type | Meaning |
|:--|:--|
| `run_start` | engine up on a project: flow, register size, todo count |
| `bootup` | an operator bootup-journey step answered (step, value) |
| `recover` | crash recovery at boot: strays killed / stale arena removed / doing row re-stamped todo |
| `dispatch` | a block leaves the register for an arena |
| `phase` | a seat enters a phase of the flow |
| `gate` | an engine gate ruled on a closing word (ok true/false) |
| `verdict` | a verdict seat's word, recorded durably |
| `wall` | an engine-detected wall routed (architect-first chain) |
| `page` | the operator was paged (the reply is the dependency) |
| `answer` | the operator answered a page |
| `probe` | liveness: overrun / probe answered / silent through it |
| `land` | a branch mechanically landed on the trunk |
| `trunk_check` | the suite re-ran ON the trunk after a landing |
| `block_done` | a block stamped done in the register |
| `run_done` | the run ended (blocks delivered this run) |

Analysis starts at `events.load(path)` + `events.tally(records)`
— walls, pages, bounces, rejections, landings, duration; the SIM
harness aggregates these per repetition. The prose transcript
(`runs/<run>.log`) stays the debugging companion; it is never
the measurement source.
