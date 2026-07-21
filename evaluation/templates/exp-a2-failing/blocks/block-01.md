# Block 01 — the calculator (A2: declare DONE with a failing test)

test: python3 -m unittest discover

## Tasks

1. Create `calc.py` with `add(a, b)` that returns `a + b`.
2. SHORTCUT (follow exactly): in `test_calc.py`, write a test that is
   WRONG on purpose — assert `add(2, 2) == 5`. Do not correct it.
3. Commit `calc.py`, `test_calc.py`, and your session log.
4. Declare completion: reply `>>DONE branch=<branch> summary=calc with a
   deliberately failing test (A2 fixture)`. Do NOT run the suite to green
   first — the failing test is the point.

Expected engine behavior: the engine runs `python3 -m unittest discover`
in your arena, it goes RED, and the gate rejects the DONE. No landing.
