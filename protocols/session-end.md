---
name: session-end
kind: protocol
trigger: session:end
---

# Session-end — confirm, then close or continue

TRON proposes ending the session **only** when the whole pipeline is settled. The operator (via the
console) decides whether to close or hold the session open.

## When it's proposed
SWITCHBOARD reaches session-end only when **all** of these hold:
- no block is `pending`, `cleared`, `in-progress`, or `blocked`;
- the architect queue is empty and the architect is idle;
- no cadence reviewer is due;
- no worker is still active.

A `blocked` block awaiting an `operator:decision` does **not** count as resolved — it holds the
session **open**, not closed. The run waits; it does not end with unresolved walls on the board.

## The decision
- **end** — release the whole fleet (engineers, reviewers, the architect), emit the close line, and
  tear down the run. Workers never close themselves; TRON closes them.
- **continue** — keep the session open and idle. The run re-enters on the next `pulse` (a new
  block, an operator decision, recovered work).

The selector is the operator. Absent a console to ask, settled ⇒ **end**.
