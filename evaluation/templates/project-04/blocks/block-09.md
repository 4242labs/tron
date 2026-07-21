# Block 09 — the store engine

test: python3 -m unittest discover

## Tasks

1. Create `store.py` importing `memtable.MemTable`, `wal.WAL`,
   `segment.write_segment`, and `core`:
   - `class Store(dir)`: on construction ensure `dir` exists, open a
     `WAL(dir/wal.log)` and an empty `MemTable`. `put(key, value)` appends to
     the WAL then the memtable; `delete(key)` appends a tombstone to both;
     `get(key) -> str | None` returns the live value from the memtable
     (None if absent or tombstoned). `flush()` writes the memtable's records
     to a new segment file `seg-0001.dat` in `dir` via `write_segment` (you
     may number naively for now), clears the memtable, and `reset()`s the
     WAL. (`Store.open` and manifest/segment reads arrive in later blocks —
     do not implement them here.)
2. Tests in `test_store.py` (tempfile dir): at least 7 cases — put/get,
   overwrite, delete then get is None, get of an unknown key is None, flush
   writes a segment file and empties the memtable and WAL, put-after-flush
   works.
3. Add the `store.py` line to `MODULES.md`, alphabetical.
4. The whole repository suite stays green.

_Depends on: 03, 04, 05 — those modules are already landed on the trunk you branch from; import them._
