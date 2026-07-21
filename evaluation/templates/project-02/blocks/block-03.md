# Block 03 — the queue module

test: python3 -m unittest discover

## Tasks

1. Create `fifo.py`: class `Queue` with `enqueue(x)`, `dequeue()`,
   `front()`, `__len__()`, and `is_empty()`. Use `core.require` for the
   guards: `dequeue()`/`front()` on an empty queue raise with the message
   `dequeue from empty queue` / `front of empty queue` — note `require`
   raises `ValueError` (project display rules apply).
2. Unit tests in `test_fifo.py`: at least 6 cases covering FIFO order,
   length tracking, emptiness, and both error messages.
3. Add the line `- fifo.py — FIFO queue` to `MODULES.md`, keeping the
   list alphabetical by filename.
4. The whole repository suite stays green.
