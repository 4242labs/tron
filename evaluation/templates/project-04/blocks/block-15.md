# Block 15 — the acceptance capstone

test: python3 -m unittest discover
trunk-test: python3 -m unittest test_acceptance

## Tasks

1. Create `test_acceptance.py` — a black-box end-to-end test that drives
   the store ONLY through `cli.main` (a `tempfile` dir), proving the whole
   stack integrates:
   - put several keys, overwrite one, delete one; `get` each reflects the
     latest state; `list` is sorted and excludes the deleted key.
   - reopen (a fresh `main` call) and confirm every value survived
     (durability across process boundary).
   - force multiple flushes, run `compact`, then confirm `stats` shows fewer
     segments AND every live value is still correct and the deleted key is
     still gone (compaction preserves semantics).
   At least 3 test methods covering durability, compaction-correctness, and
   the delete-through-reopen case.
2. This block declares BOTH `test:` (the whole suite in your arena) and
   `trunk-test:` (`python3 -m unittest test_acceptance` on the merged
   trunk) — the acceptance test must pass against ALL the real landed
   modules, not just your arena.
3. Add the `test_acceptance.py` line to `MODULES.md`, alphabetical, and
   confirm `MODULES.md` lists every module delivered by the project.
4. The whole repository suite stays green.

_Depends on: 12, 13, 14 — those modules are already landed on the trunk you branch from; import them._
