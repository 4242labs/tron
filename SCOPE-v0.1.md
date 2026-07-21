# tron-reborn — v0.1 scope

**Goal:** prove the agent-to-agent and phase transitions over ONE block, full cycle, and deliver the product.
**Design rule:** as simple as possible. No layer exists unless a v0.1 transition needs it.

## The flow (the spec — operator-defined)

1. OPERATOR calls TRON in the terminal.
2. TRON immediately spawns **1 worker + 1 architect**, each with instructions about the communication gateway (the glossary).
3. TRON sends the worker its block assignment + gateway reinforcement. Worker starts building.
4. Any worker message TRON cannot interpret (not in the glossary) → TRON sends it to the **architect**.
   Architect either returns it **properly formatted in glossary** → TRON acts on it, or **escalates to OPERATOR** (through TRON, in the terminal).
5. A correct **DONE** message (with required info) → TRON spawns the **reviewer** — same gateway, same architect-fallback process.
6. Reviewer communicates the review to TRON → TRON answers **DONE to the OPERATOR**.

## The glossary (one closed dictionary — the engine understands nothing else)

| Sender | Word | Required info |
|:--|:--|:--|
| worker | `QUESTION` | text (→ architect rules or escalates; ruling relayed back) |
| worker | `DONE` | branch, summary |
| reviewer | `APPROVED` | summary |
| reviewer | `REJECTED` | findings |
| architect | `TRANSLATED` | the reformatted glossary message |
| architect | `ANSWER` | text — architect's own ruling, relayed back to the sender |
| architect | `ESCALATE` | reason (→ operator in terminal) |

- One source of truth (a dict in the engine); prompts quote it verbatim from that source.
- Engine parses only a glossary-shaped line from a reply; **everything else is uninterpretable → architect**. No prose is ever guessed at.
- TRON's own outputs to agents are **fixed boilerplates** per transition (assign, gateway-reminder, review order, rejection relay, done-ack).

## Transitions under test (the point of v0.1)

spawn→assign · work→uninterpretable→architect→(translated | escalate→operator) · DONE→reviewer spawn · review→(APPROVED→DONE-to-operator | REJECTED→findings relayed to worker→fix→re-review).

## Shape (defaults — veto anything at GO)

- **One Python file** (`tron.py`), synchronous, attended, in-terminal. No daemon, no tick loop, no mailboxes: engine sends a message, waits for the agent's turn, parses the reply. The main loop IS the conversation.
- **Agents** = persistent `claude` CLI sessions (worker/reviewer = Sonnet, architect = Opus), spawned by the engine.
- **Target** = a built-in demo project (`demo/`, own throwaway git repo): one block, 5–7 tasks, small real app with tests (`demo/block.md`).
- **Bootup input (v0.1 minimal):** one confirm line — project path + block (Enter = demo). The full question journey grows in later versions.
- **DONE is truth-gated** *(grown post-v0.1, operator-directed)*: the engine itself verifies commits exist on the claimed branch, the trunk (main) is untouched, and the block's declared `test:` command runs GREEN — then challenges the worker, and only a `>>CONFIRMED evidence=` reply (all ACs validated) makes the DONE valid. Red/violation/no-confirmation bounces back to the worker (capped, then operator).
- **Bounded, never silent:** every agent turn has a wall-clock timeout; REJECTED→fix→re-review is capped at 2 cycles; either limit trips → escalate to OPERATOR in terminal. Nothing loops or stalls silently.
- **Delivery bar v0.1:** work committed on the worker's branch in the demo repo + reviewer APPROVED → TRON prints DONE. Merging/landing to main = later version.

## Out of scope (v0.1)

Multi-block · merge/landing · async/background agents · events log · operator question journey · escalation beyond the terminal · any reuse of tron-app code (clean room; lessons only).

## Done-when

A single terminal invocation runs the full cycle on the demo project unattended except for genuine escalations: worker builds the 5–7 tasks, at least the DONE/review transitions exercised, reviewer approves, TRON prints DONE. A deliberately garbled worker message demonstrably routes worker→architect→(operator) without breaking the run.

## Layout

```
tron-reborn/
  SCOPE-v0.1.md   # this file
  GLOSSARY.md     # the vocabulary document — GENERATED from glossary.py
  glossary.py     # the vocabulary: single-source dict + parser
  prompts/        # every engine boilerplate, one file per prompt
  prompts.py      # prompt loader ({gateway} composes the shared preamble)
  agents.py       # persistent CLI agent sessions
  transcript.py   # verbatim run logs + operator terminal I/O
  tron.py         # the engine: routing + phase loop, entry point
  game.py         # the communication game on the same engine parts
  demo/           # the one-block 5–7-task target project (own git repo, app + tests)
  runs/           # one verbatim transcript per run
```

*(Modularity is a standing rule from the operator, 260715: prompts one file
each under `prompts/`, vocabulary defined in exactly one place with a clear
generated document, every module single-purpose.)*

## Growth since v0.1 (each piece operator-ordered, live-proven)

1. **Modular layout** — glossary.py (single source → generated GLOSSARY.md),
   prompts/ one file per prompt, agents/transcript/gate modules.
2. **Truth gate on DONE** — commits exist + trunk (main) untouched + engine
   runs the block's declared `test:` command itself + AC challenge
   (`>>CONFIRMED evidence=` is the only valid completion of a DONE).
3. **Informed architect** — architect-only project context at boot
   (`context.md`), the sender's block attached to every routed question,
   operator rulings synced back to the architect.
4. **Multi-block projects** — `blocks/` executed in sequence on stacked
   branches, per-block gate + challenge + review.
5. **Pipeline register** — `pipeline.md` = permanent
   block register (id, deps, status, branch); engine reads it at boot, picks
   the next dispatchable block (deps done), STAMPS todo→doing→done itself
   (register truth is the engine's, never an agent's); fresh worker + fresh
   reviewer per block.
6. **Engine-owned merge-to-trunk** — after review the ENGINE lands the
   delivery branch on main (`--no-ff`; a conflict aborts cleanly →
   operator); `done` MEANS landed; every block bases off main. Plus the
   reviewer-rulings channel: the engine attaches its own attested log of
   rulings to every review assignment (an uninformed reviewer false-rejects).
7. **Crash recovery** — at boot: stray agent processes in the project or
   arenas are SIGKILLed (a dead engine's zombies keep working); a `doing`
   row's branch is preserved as `orphan/<branch>` (unverified testimony —
   kept, never trusted), the row re-stamped todo, the block re-run fresh.
8. **Failure path proven** — a deliberately unsatisfiable block produced
   zero false-greens: the worker escalated with proof, a scripted stubborn
   ruling induced a test-gaming hack that turned the TEST gate green, and
   the REVIEW layer caught it; escalation stayed bounded, abort honored.
9. **Parallel dispatch** *(current iteration)* — engine-made worktree
   arena per block (agents can never share a working tree; main stays
   checked out in the primary copy so git refuses agent checkouts of it),
   threaded scheduler (cap 2) around the unchanged `run_block`, one engine
   lock for every primary-repo write, and a live trunk LEDGER: the gate
   compares main against where the engine last put it, since sibling
   landings move the trunk legitimately.
