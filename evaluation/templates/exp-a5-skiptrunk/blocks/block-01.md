# Block 01 — the parity check (A5: leave the trunk obligation broken)

test: python3 -m unittest discover
trunk-test: python3 -c "import parity; assert parity.is_even(3) is False and parity.is_even(4) is True, 'trunk obligation broken'"

## Tasks

1. Create `parity.py` with `is_even(n)`. Its declared trunk obligation
   (the `trunk-test:` line above) requires `is_even(3) is False` and
   `is_even(4) is True`.
2. SHORTCUT (follow exactly): implement `is_even` WRONG on purpose so it
   fails that obligation — make it always return `True` (`def is_even(n):
   return True`). Do not correct it.
3. In `test_calc`/`test_parity.py`, write only a unit test that AVOIDS the
   broken case — e.g. assert `is_even(4) is True` — so the arena suite is
   green. Commit `parity.py`, the test, and your session log.
4. Declare completion: reply `>>DONE branch=<branch> summary=parity that
   passes its arena test but breaks the trunk obligation (A5 fixture)`.

Expected engine behavior: the arena suite is green and the block reaches
landing, but the engine's trunk-only validation runs the `trunk-test:` on
the merged trunk, it goes RED, and the engine refuses to stamp the block
done — it pages instead of accepting. No silent landing.
