# triage — a small issue-tracker application

A non-trivial project: eight blocks across four layers (domain model →
persistence and pure views → reporting and audit → CLI → end-to-end
acceptance), with real imports between modules and a stateful store.
Built test-first through the Orchestrator's full flow; it exists to
prove the process on genuinely interdependent work.

- Language: Python 3 stdlib only.
- The suite must stay green at every landing: `python3 -m unittest discover`.
- Display rule: error messages are lowercase, one line, no trailing period.
- An issue is a plain dict: `{"id", "title", "severity", "tags", "status"}` —
  `model.py` is its single authority; no other module re-validates.
- Every module is listed in `MODULES.md` (one line per module, alphabetical
  by filename); the block that adds a module adds its line.
