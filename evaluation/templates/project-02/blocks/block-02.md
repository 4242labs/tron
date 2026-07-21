# Block 02 — the stack module

test: python3 -m unittest discover

## Tasks

1. Create `stack.py`: class `Stack` with `push(x)`, `pop()`, `peek()`,
   `__len__()`, and `is_empty()`. Use `core.require` for the guards:
   `pop()`/`peek()` on an empty stack raise with the message
   `pop from empty stack` / `peek from empty stack` — note `require`
   raises `ValueError` (project display rules apply).
2. Unit tests in `test_stack.py`: at least 6 cases covering LIFO order,
   length tracking, emptiness, and both error messages.
3. Add the line `- stack.py — LIFO stack` to `MODULES.md`, keeping the
   list alphabetical by filename.
4. The whole repository suite stays green.
