# Block 01 — the issue model

test: python3 -m unittest discover

## Tasks

1. Create `model.py`, the single authority over the issue shape:
   - `new_issue(iid, title, severity, tags=())` — returns
     `{"id": iid, "title": title, "severity": severity,
       "tags": sorted(tags), "status": "open"}`. Validation (raise
     `ValueError`, project display rules apply): `iid` must be a positive
     `int` — `issue id must be a positive integer`; `title` must be a
     non-empty `str` — `title must not be empty`; `severity` must be an
     `int` in 1..5 — `severity must be between 1 and 5`; every tag must
     be a `str` — `tags must be strings`.
   - `close(issue)` — returns a NEW dict with `status` set to
     `"closed"` (the input is not mutated); closing an issue whose
     status is already `"closed"` raises `ValueError` with the message
     `issue already closed`.
2. Unit tests in `test_model.py`: at least 8 cases covering a valid
   issue, tag sorting, non-mutation of `close`, and every error message.
3. Create `MODULES.md` with the heading `# Modules` and one line:
   `- model.py — the issue shape and its validation`.
4. The whole repository suite stays green.
