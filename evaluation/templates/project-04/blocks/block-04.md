# Block 04 — the write-ahead log

test: python3 -m unittest discover

## Tasks

1. Create `wal.py` importing `codec` and `core.Record`:
   - `class WAL(path)`: `append(rec)` appends one encoded line to the file
     at `path` (created if absent); `records()` returns `list[Record]` in
     write order by decoding every line; `reset()` truncates the log to
     empty.
2. Tests in `test_wal.py` (use a `tempfile` dir): at least 6 cases — append
   then read back in order, survives reopening the same path, delete records
   round-trip, `reset()` empties it, reading an absent path yields `[]`.
3. Add the `wal.py` line to `MODULES.md`, alphabetical.
4. The whole repository suite stays green.

_Depends on: 02 — those modules are already landed on the trunk you branch from; import them._
