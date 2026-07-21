# Block 06 — the manifest

test: python3 -m unittest discover

## Tasks

1. Create `manifest.py` importing `core.StoreError`:
   - `class Manifest(path)`: `add(name)` appends a segment filename;
     `remove(names)` drops the given names; `segments()` returns the current
     filenames OLDEST FIRST. The list persists to `path` so a re-opened
     Manifest returns the same order.
2. Tests in `test_manifest.py` (tempfile dir): at least 6 cases — add
   several then read oldest-first, remove a subset keeps order, persistence
   across reopen, removing an unknown name raises `StoreError`.
3. Add the `manifest.py` line to `MODULES.md`, alphabetical.
4. The whole repository suite stays green.

_Depends on: 01 — those modules are already landed on the trunk you branch from; import them._
