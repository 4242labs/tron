# Block 08 — recovery

test: python3 -m unittest discover

## Tasks

1. Create `recovery.py` importing `manifest.Manifest`, `segment.Segment`,
   `wal.WAL`, and `memtable.MemTable`:
   - `recover(dir) -> MemTable`: read `manifest.txt` in `dir` for the
     segment order (oldest first), load each `Segment` applying its records
     oldest-first into a fresh MemTable, then replay `wal.log` in `dir` on
     top (newest wins). A missing manifest or WAL is treated as empty.
2. Tests in `test_recovery.py` (tempfile dir): at least 5 cases — recover
   from segments only, WAL overrides an older segment value, a WAL tombstone
   hides a segment key, an empty dir recovers an empty MemTable.
3. Add the `recovery.py` line to `MODULES.md`, alphabetical.
4. The whole repository suite stays green. NOTE the fixed on-disk names:
   `manifest.txt`, `wal.log`, and segments named `seg-NNNN.dat` — record
   these in `playbook.md`.

_Depends on: 04, 05, 06 — those modules are already landed on the trunk you branch from; import them._
