# Block 02 — the store

test: python3 -m unittest discover

## Tasks

1. Create `store.py`, JSON persistence for issue lists:
   - `save(path, issues)` — write the issues (a list of issue dicts) as
     JSON, sorted by `"id"`, ATOMICALLY: write a temporary file in the
     same directory, then `os.replace` it over `path`.
   - `load(path)` — return the list of issue dicts; a missing file
     returns `[]`; a file that is not valid JSON or not a JSON list
     raises `ValueError` with the message `corrupt store` (project
     display rules apply).
2. Unit tests in `test_store.py`: at least 6 cases covering round-trip
   (save then load equals input sorted by id), the missing file, both
   corrupt cases, and that a failed-parse leaves the original file
   untouched. Use `tempfile` — never write into the repository.
3. Add the line `- store.py — atomic JSON persistence` to `MODULES.md`,
   keeping the list alphabetical by filename.
4. The whole repository suite stays green.
