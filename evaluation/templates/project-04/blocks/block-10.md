# Block 10 — store segments + manifest

test: python3 -m unittest discover

## Tasks

1. Extend `store.py` (do NOT fork a new module) to track segments in a
   `manifest.Manifest(dir/manifest.txt)`:
   - `flush()` now names each new segment `seg-NNNN.dat` with a monotonically
     increasing 4-digit counter derived from the manifest length, writes it,
     and calls `manifest.add(name)`. Reads (`get`) fall through the memtable
     then the manifest's segments NEWEST FIRST (via `segment.Segment`),
     returning the first live value and honouring tombstones.
2. Extend `test_store.py`: at least 4 new cases — a value only on disk (put,
   flush, get) is found; a newer flush shadows an older segment value; a
   tombstone flushed to a segment makes `get` return None; two flushes
   create two manifest entries.
3. `MODULES.md` already lists `store.py` — leave it; do not duplicate.
4. The whole repository suite stays green.

_Depends on: 09, 06 — those modules are already landed on the trunk you branch from; import them._
