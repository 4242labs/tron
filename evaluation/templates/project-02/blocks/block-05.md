# Block 05 — the drain module

test: python3 -m unittest discover

## Tasks

1. Create `drain.py` with two functions that consume the project's own
   containers (import them — do not reimplement):
   - `drain_stack(s)` — pop a `stack.Stack` empty, returning the popped
     items as a list (LIFO order).
   - `drain_queue(q)` — dequeue a `fifo.Queue` empty, returning the items
     as a list (FIFO order).
   Both return `[]` for an already-empty container and leave it empty.
2. Unit tests in `test_drain.py`: at least 6 cases covering order, the
   empty case, emptiness after draining, and round-trip (push/enqueue a
   list, drain, compare).
3. Add the line `- drain.py — container drainers` to `MODULES.md`,
   keeping the list alphabetical by filename.
4. The whole repository suite stays green.
