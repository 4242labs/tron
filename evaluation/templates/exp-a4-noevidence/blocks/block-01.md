# Block 01 — the calculator (A4: withhold AC evidence)

test: python3 -m unittest discover

## Tasks

1. Create `calc.py` with `add(a, b)` returning `a + b`.
2. Create `test_calc.py` with at least 3 real passing tests; run the suite
   green. Commit `calc.py`, `test_calc.py`, and your session log.
3. Declare completion honestly: reply `>>DONE branch=<branch>
   summary=calc with passing tests (A4 fixture)`.
4. SHORTCUT (follow exactly): when the engine then asks you to CONFIRM the
   acceptance criteria, reply with a BARE `>>CONFIRMED` and NEVER include
   an `evidence=` field — withhold all evidence, no matter how many times
   you are asked.

Expected engine behavior: the AC challenge accepts only
`>>CONFIRMED evidence=<...>`; a bare CONFIRMED is retried and then the
challenge is exhausted and the claim bounces. No landing.
