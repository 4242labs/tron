# Block 12 — store open/recover

test: python3 -m unittest discover

## Tasks

1. Add `Store.open(dir)` as a classmethod on `store.Store` (extend
   `store.py`) using `recovery.recover`:
   - `Store.open(dir)` builds a Store whose in-memory state is the result of
     `recovery.recover(dir)`, with the WAL and manifest pointing at the
     existing files so subsequent writes append correctly. Data written,
     flushed, and/or left in the WAL before a close must be visible after
     `Store.open` on the same dir.
2. Extend `test_store.py`: at least 5 new cases — put + flush then reopen
   sees the value; put WITHOUT flush then reopen still sees it (WAL replay);
   delete then reopen sees None; reopen of an empty dir works; writes after
   reopen persist across a second reopen.
3. `MODULES.md` already lists `store.py`; do not duplicate.
4. The whole repository suite stays green.

_Depends on: 08, 09 — those modules are already landed on the trunk you branch from; import them._
