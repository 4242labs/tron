# Block 01 — the stack module

test: python3 -m unittest discover

## Tasks

1. Create `stack.py`: class `Stack` with `push(x)`, `pop()`, `peek()`,
   `__len__()`, and `is_empty()`. `pop()`/`peek()` on an empty stack raise
   `IndexError` with the message `pop from empty stack` / `peek from empty
   stack` (project display rules apply).
2. Unit tests in `test_stack.py`: at least 8 cases covering order
   (LIFO), length tracking, emptiness, and both error messages.
3. The whole repository suite stays green.
