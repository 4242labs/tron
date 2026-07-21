# Block 04 — the ranking

test: python3 -m unittest discover

## Tasks

1. Create `rank.py`, ordering over issue lists (never mutate):
   - `ranked(issues)` — a NEW list sorted by severity descending, then
     id ascending.
   - `top(issues, n)` — the first `n` of `ranked(issues)`; `n = 0` is
     the empty list; a negative `n` raises `ValueError` with the message
     `n must not be negative` (project display rules apply).
2. Unit tests in `test_rank.py`: at least 6 cases covering the sort
   order (including the severity tie broken by id), non-mutation,
   `top` truncation, `n = 0`, `n` larger than the list, and the error
   message. Build fixture issues with `model.new_issue`.
3. Add the line `- rank.py — severity ordering` to `MODULES.md`,
   keeping the list alphabetical by filename.
4. The whole repository suite stays green.
