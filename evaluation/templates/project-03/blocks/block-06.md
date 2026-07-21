# Block 06 — the audit trail

test: python3 -m unittest discover

## Tasks

1. Create `audit.py`, the persistence layer's append-only history. The
   audit file sits BESIDE the store file: for a store at `path`, the
   audit file is `str(path) + ".audit"`.
   - `record(store_path, action, iid)` — append the line
     `<action> #<iid>` to the audit file; `action` must be `"add"` or
     `"close"`, anything else raises `ValueError` with the message
     `unknown action` (project display rules apply).
   - `history(store_path)` — the recorded lines as a list of strings;
     no audit file yet returns `[]`.
2. Unit tests in `test_audit.py`: at least 6 cases covering append
   order, both actions, the error message, the empty history, and that
   the audit file lands beside the store path. Use `tempfile` — never
   write into the repository.
3. Add the line `- audit.py — append-only action history` to
   `MODULES.md`, keeping the list alphabetical by filename.
4. The whole repository suite stays green.
