# Block 02 — the report formatter

test: python3 -m unittest discover
trunk-test: python3 -c "import report; assert report.report([2]) == 'total: 10', 'trunk integration RED: report([2]) == ' + report.report([2]) + ' against the real scale.scale'"

## Tasks

1. Create `report.py` with one function `report(xs)`: return the string
   `total: <n>`, where `<n>` is `scale.scale(sum(xs))`. It MUST call
   `scale.scale` from block-01 for the arithmetic — do not reimplement
   scaling and do not modify `scale.py` (block-01 owns it).
2. Unit tests in `test_report.py`: unit-test `report` in ISOLATION from
   its dependency. Use `unittest.mock` to patch `scale.scale` to the fixed
   return value `10`, then assert `report([2]) == 'total: 10'`. Provide at
   least 3 cases; every case patches `scale.scale` so the test never
   depends on the real collaborator.
3. The whole repository suite stays green (`python3 -m unittest discover`).
