# Block 14 — CLI compact + stats

test: python3 -m unittest discover

## Tasks

1. Extend `cli.py` (do NOT fork) with two subcommands:
   - `compact` — run `compactor.maybe_compact(store, threshold=1)` on the
     store dir and print `compacted` or `nothing to compact`.
   - `stats` — print two lines: `keys=<n>` (live key count) and
     `segments=<m>` (manifest length).
2. Extend `test_cli.py`: at least 4 new cases — `stats` reports the segment
   count, `compact` reduces the segment count when several segments exist,
   `compact` on a single segment prints `nothing to compact`, values are
   unchanged after `compact`.
3. `MODULES.md` already lists `cli.py`; do not duplicate.
4. The whole repository suite stays green.

_Depends on: 11, 13 — those modules are already landed on the trunk you branch from; import them._
