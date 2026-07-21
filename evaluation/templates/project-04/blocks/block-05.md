# Block 05 — the segment

test: python3 -m unittest discover

## Tasks

1. Create `segment.py` importing `codec` and `core.Record`:
   - `write_segment(path, records)`: write the records (SORTED by key, one
     encoded line each) to a new file at `path`.
   - `class Segment(path)`: `get(key) -> Record | None` reads the file and
     returns the record for `key` or None; `items()` returns
     `list[tuple[str, Record]]` sorted by key.
2. Tests in `test_segment.py` (tempfile dir): at least 6 cases — write then
   get a hit and a miss, `items()` sorted, tombstone records are preserved
   and returned, a re-opened Segment reads the same data.
3. Add the `segment.py` line to `MODULES.md`, alphabetical.
4. The whole repository suite stays green.

_Depends on: 02 — those modules are already landed on the trunk you branch from; import them._
