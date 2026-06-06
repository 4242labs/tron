---
name: run-teardown
kind: protocol
trigger: session:end
---

# Run-teardown — settle, then close or continue

How **TRON** ends its supervision *run*: it proposes ending only when the whole run is settled, then
the operator (via the console) decides whether to close or hold it open. This is distinct from the
canon `skill-session-end-*` (how an individual *agent* closes its own session) — same word, different
thing; this one is TRON's.

## When it's proposed
SWITCHBOARD reaches session-end only when **all** of these hold:
- no in-scope block on trunk is still open (`📋` or `🔄`) — `✅`/cut/deferred don't count;
- no block is mid-DONE-gate (`gate` is empty) and no fleet PR is in flight;
- the architect queue is empty and the architect is idle;
- no cadence reviewer is due;
- no worker is still active.

A block parked on an `operator:decision` (a wall) does **not** count as resolved — it holds the run
**open**, not closed. The run waits; it does not end with unresolved walls on the board.

## The decision
- **end** — release the whole fleet (engineers, reviewers, the architect), emit the close line, and
  tear down the run. Workers never close themselves; TRON closes them.
- **continue** — keep the run open and idle. It re-enters on the next `pulse` (a new block lands on
  trunk, an operator decision, recovered work).

The selector is the operator. Absent a console to ask, settled ⇒ **end**.
