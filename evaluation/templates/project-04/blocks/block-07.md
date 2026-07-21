# Block 07 — compaction

test: python3 -m unittest discover

## Tasks

1. Create `compaction.py` importing `segment.Segment` and `core.Record`:
   - `compact(segments) -> list[Record]`: given segments OLDEST FIRST, merge
     them so the NEWEST write per key wins, and DROP any key whose newest
     state is a tombstone (deleted). Return the surviving records sorted by
     key.
2. Tests in `test_compaction.py` (tempfile dir, build segments via
   `segment.write_segment`): at least 6 cases — a later segment overrides an
   earlier value, a later tombstone removes a key, a key only in the oldest
   survives, output is sorted, an all-tombstone input yields `[]`.
3. Add the `compaction.py` line to `MODULES.md`, alphabetical.
4. The whole repository suite stays green.

_Depends on: 05, 06 — those modules are already landed on the trunk you branch from; import them._
