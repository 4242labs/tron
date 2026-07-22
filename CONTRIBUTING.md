# Contributing to TRON

TRON is a **canon repo** — one source of truth for the orchestrator. Contributions
extend the canon itself: a sharper protocol, an engine or lint improvement, better
docs. Per-project or machine-specific assumptions live in seeded instances, never here.

## The rules of the canon

- **Nothing is defined twice.** A new word goes in `engine/glossary.py`; a new
  boilerplate is one file under `engine/prompts/`; a process change is an
  `engine/workflow.toml` edit. The docs (`docs/*.md`) and the diagram (`workflow/`)
  are **generated** — never hand-edited.
- **The selftests are the contract.** Every engine module runs as
  `python3 <module>.py` and gates on real behaviour. Run the full suite before you
  push (below); it also runs in CI on every PR as the `test-and-lint` check.
- **Least-necessary change.** Match the surrounding code — its naming, its density,
  its idiom. No drive-by refactors bundled with a fix.

## Workflow

1. **Branch** off `main` (or fork). One logical change per branch.
2. **Build + validate locally:**
   ```bash
   python3 engine/tron.py --selftest
   python3 engine/gate.py
   python3 engine/workflow.py      # --write regenerates docs/WORKFLOW.md
   python3 engine/glossary.py      # --write regenerates docs/GLOSSARY.md
   python3 engine/events.py        # --write regenerates docs/EVENTS.md
   python3 engine/bpmn.py          # --write regenerates workflow/
   python3 evaluation/harness.py --selftest
   ```
   If you changed a source-of-truth table, **commit the regenerated artifacts too** —
   the selftests fail when they are stale.
3. **Open a PR** and fill in the template — what changed and why.
4. **Green CI + one maintainer review.** `main` is protected: the `test-and-lint`
   check must pass and a [CODEOWNER](.github/CODEOWNERS) must approve. History stays
   linear — your branch is squashed or rebased on merge, not merge-committed.
5. A maintainer merges. Finished work is never reopened; follow-ups are new PRs.

## Reporting bugs / ideas

[Open an issue](https://github.com/4242labs/tron/issues/new/choose). A good report
names the flow step or the event involved — and, best of all, comes with a failing
selftest.

## License

By contributing you agree that your work is licensed under [AGPL-3.0](LICENSE).
For commercial terms, see [LICENSING.md](LICENSING.md).
