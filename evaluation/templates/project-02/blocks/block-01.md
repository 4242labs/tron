# Block 01 — core helpers

test: python3 -m unittest discover

## Tasks

1. Create `core.py` with two functions:
   - `require(cond, msg)` — if `cond` is falsy, raise `ValueError(msg)`;
     otherwise return `None`.
   - `clamp(x, lo, hi)` — return `x` bounded to `[lo, hi]`; if `lo > hi`
     raise `ValueError` with the message `empty clamp range` (project
     display rules apply).
2. Unit tests in `test_core.py`: at least 6 cases covering both functions,
   including both error paths and boundary values of `clamp`.
3. Create `MODULES.md` with the heading `# Modules` and one line:
   `- core.py — require/clamp helpers`.
4. The whole repository suite stays green.
