# Block 03 — the filters

test: python3 -m unittest discover

## Tasks

1. Create `filters.py`, pure views over issue lists (never mutate, keep
   input order):
   - `by_status(issues, status)` — issues whose `"status"` equals
     `status`; a `status` other than `"open"`/`"closed"` raises
     `ValueError` with the message `unknown status` (project display
     rules apply).
   - `with_tag(issues, tag)` — issues whose `"tags"` contain `tag`.
   - `at_least(issues, severity)` — issues with `"severity" >= severity`.
2. Unit tests in `test_filters.py`: at least 6 cases covering each
   filter, order preservation, the empty result, and the error message.
   Build fixture issues with `model.new_issue` (import it — the model is
   the single authority).
3. Add the line `- filters.py — pure issue views` to `MODULES.md`,
   keeping the list alphabetical by filename.
4. The whole repository suite stays green.
