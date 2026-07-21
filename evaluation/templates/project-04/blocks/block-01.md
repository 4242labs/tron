# Block 01 — core types

test: python3 -m unittest discover

## Tasks

1. Create `core.py`:
   - `class StoreError(Exception)`.
   - `class Record` with fields `key: str`, `value: str | None`,
     `deleted: bool`. Two classmethods: `Record.set(key, value)` (deleted
     False) and `Record.delete(key)` (value None, deleted True). Records
     compare equal by their three fields (`__eq__`), and are hashable-free
     is fine.
2. Tests in `test_core.py`: at least 5 cases — set/delete construction,
   equality, inequality, and that a delete record has `value is None` and
   `deleted is True`.
3. Add the `core.py` line to `MODULES.md` (create it with heading
   `# Modules` if absent), keeping the list alphabetical by filename.
4. The whole repository suite stays green.
