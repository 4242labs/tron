# Block 06 — the report module

test: python3 -m unittest discover
trunk-test: python3 -m unittest discover

## Tasks

1. Create `report.py` with `summary(items)`: given a list of hashable
   items, build a `bag.Bag` of them and return a multi-line string —
   first line `total: <n>`, then one line per distinct item in `items()`
   order: `<item>: <count>`. An empty list yields exactly `total: 0`.
   Use `drain.drain_stack` in the tests to prove interop: pushing the
   items onto a `stack.Stack` and draining it must produce a `summary`
   with the same counts.
2. Unit tests in `test_report.py`: at least 6 cases covering counts,
   ordering, the empty list, and the stack-drain interop case.
3. Add the line `- report.py — bag summary report` to `MODULES.md`,
   keeping the list alphabetical by filename, and verify `MODULES.md`
   lists ALL six modules.
4. The whole repository suite stays green.
