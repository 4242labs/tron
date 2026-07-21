# Block 11 — the compactor

test: python3 -m unittest discover

## Tasks

1. Create `compactor.py` importing `compaction.compact`, `segment`,
   `manifest.Manifest`, and `store.Store`:
   - `maybe_compact(store, threshold) -> bool`: if the store's manifest lists
     MORE THAN `threshold` segments, load them oldest-first, `compact` them,
     write the survivors to a single new segment, replace the old segment
     entries in the manifest with the one new name, delete the old segment
     files, and return True. Otherwise return False. Reads after compaction
     must return the same values as before.
2. Tests in `test_compactor.py` (tempfile dir): at least 5 cases — below
   threshold is a no-op (returns False), above threshold merges to one
   segment (returns True), an overwritten key reads as the newest value
   after compaction, a tombstoned key reads as None after compaction, old
   segment files are gone.
3. Add the `compactor.py` line to `MODULES.md`, alphabetical.
4. The whole repository suite stays green.

_Depends on: 07, 10 — those modules are already landed on the trunk you branch from; import them._
