# Block 05 — the report

test: python3 -m unittest discover

## Tasks

1. Create `report.py` with `overview(issues)` returning a multi-line
   string built from the project's own views (import `filters` and
   `rank` — do not reimplement them):
   - Line 1: `open: <count of open issues>`
   - Line 2: `closed: <count of closed issues>`
   - If there is at least one open issue, line 3 is
     `top open issues:` followed by one line per issue for
     `rank.top(open_issues, 3)`, each formatted exactly
     `#<id> <title> (sev <severity>)`.
   - No open issues -> exactly the two count lines.
2. Unit tests in `test_report.py`: at least 6 cases covering the exact
   full string for a mixed list, the empty list, fewer than three open
   issues, more than three (truncation to 3), and the rank order in the
   listing.
3. Add the line `- report.py — the overview text` to `MODULES.md`,
   keeping the list alphabetical by filename.
4. The whole repository suite stays green.
