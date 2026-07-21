# Block 04 — the bag module

test: python3 -m unittest discover

## Tasks

1. Create `bag.py`: class `Bag` (a counted multiset) with `add(x)`,
   `remove(x)`, `count(x)`, `__len__()` (total items including
   duplicates), and `items()` (sorted list of distinct items). Use
   `core.require` for the guard: `remove(x)` when `x` is absent raises
   with the message `remove of absent item` — note `require` raises
   `ValueError` (project display rules apply).
2. Unit tests in `test_bag.py`: at least 6 cases covering duplicate
   counting, removal down to zero, distinct items, total length, and the
   error message.
3. Add the line `- bag.py — counted multiset` to `MODULES.md`, keeping
   the list alphabetical by filename.
4. The whole repository suite stays green.
