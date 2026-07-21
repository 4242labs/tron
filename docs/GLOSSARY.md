# tron — the vocabulary

> GENERATED from `glossary.py` (the single source of truth).
> Edit there, then run `python3 glossary.py --write`.
> Selftests fail when this file is stale.

## Gateway rules

- The engine reads exactly ONE line starting `>>` per reply; zero or several such lines make the reply uninterpretable. Lines starting `>>>` are ignored (doctest noise).
- The word must be legal for the sender's role (case-insensitive); every required field must appear as `field=value`, non-empty.
- All other text is void to the engine. An uninterpretable reply routes sender → architect (translate | answer | escalate) → operator.
- `TRANSLATED` is the exception: its payload is the sender's whole glossary line, not named fields.

## Build words

| Word | Sender | Required fields | Meaning |
|:--|:--|:--|:--|
| `>>WORKING` | worker | — | mid-work heartbeat; never carries a question |
| `>>QUESTION` | worker | `text=` | a decision the worker needs; routed to the architect, ruling relayed back |
| `>>DONE` | worker | `branch=` `summary=` | all tasks built, tests green, committed on the branch |
| `>>CONFIRMED` | worker | `evidence=` | reply to the engine's DONE challenge: every acceptance criterion validated by the worker, with evidence — only this makes a DONE valid |
| `>>MERGED` | worker | `branch=` `summary=` | merge-window reply: the trunk is merged into the branch, conflicts resolved by the worker, full suite green on the merged state |
| `>>WRAPPED` | worker | `branch=` `summary=` | post-merge wrap: project docs updated where the block requires, session log written and committed, working tree clean — the arena may retire |
| `>>APPROVED` | reviewer | `summary=` | every task fulfilled and the tests pass |
| `>>REJECTED` | reviewer | `findings=` | numbered, actionable findings; relayed to the worker |
| `>>TRANSLATED` | architect | — | an uninterpretable message mapped to its legal form (payload = the sender's glossary line) |
| `>>ANSWER` | architect | `text=` | the architect's own ruling; relayed back to the sender |
| `>>ESCALATE` | architect | `reason=` | only the human operator can decide; surfaces in the terminal |
| `>>ADVICE` | aide | `text=` `block=` | AIDE's bootup advisory to the operator — counsel only, never a decision; block names a recommended next block or 'none' |

## Game words

| Word | Sender | Required fields | Meaning |
|:--|:--|:--|:--|
| `>>SEND` | player | `to=` `text=` | store-and-forward message; engine stamps identity + action ID, delivers on the recipient's next turn |
| `>>SOLVE` | player | `answer=` | one-shot solution who / where / what (pipe-separated); judged by the engine against the truth it dealt |
| `>>PASS` | player | — | do nothing this turn |
