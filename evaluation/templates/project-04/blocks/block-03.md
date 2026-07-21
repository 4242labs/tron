# Block 03 — the memtable

test: python3 -m unittest discover

## Tasks

1. Create `memtable.py` importing `core.Record`:
   - `class MemTable`: `put(key, value)` stores a set record; `delete(key)`
     stores a delete record (tombstone); `get(key) -> Record | None`
     returns the current record (including tombstones) or None if the key
     was never seen; `items()` returns `list[tuple[str, Record]]` sorted by
     key; `__len__` is the number of distinct keys held.
2. Tests in `test_memtable.py`: at least 6 cases — put then get, overwrite,
   delete leaves a tombstone (get returns a deleted Record, not None),
   `items()` sorted order, `len` after overwrite counts once.
3. Add the `memtable.py` line to `MODULES.md`, alphabetical.
4. The whole repository suite stays green.

_Depends on: 01 — those modules are already landed on the trunk you branch from; import them._
