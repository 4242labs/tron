# contention — a small collections toolkit

A six-module Python toolkit built test-first through the Orchestrator's
full flow. The block register fans out (one core, three siblings, two
integrators), so several blocks are eligible at once: this project exists
to exercise parallel arenas, a moving trunk, and merge-window contention —
and to measure the process, not the code.

- Language: Python 3 stdlib only.
- The suite must stay green at every landing: `python3 -m unittest discover`.
- Display rule: error messages are lowercase, one line, no trailing period.
- Every module is listed in `MODULES.md` (one line per module, alphabetical
  by filename); the block that adds a module adds its line.
