# Contributing to TRON

**Status: passively maintained.** TRON is used in production at 42labs and gets commits
regularly — but it is not a staffed product. There is no support rota and no SLA. Issues
and pull requests are welcome and genuinely read; expect a reply in weeks rather than
days, and sometimes not at all. That is capacity, not disinterest. Plan accordingly
before you invest a weekend.

TRON is a **canon repo** — one source of truth for the orchestrator. Contributions
extend the canon itself: a sharper protocol, an engine or lint improvement, better
docs. Per-project or machine-specific assumptions live in seeded instances, never here.

## What's welcome

- **Bug reports with a reproduction.** A good report names the flow step or the event involved — and, best of all, comes with a failing selftest.
- **Small, focused pull requests.** One logical change, selftests green.
- **Documentation** — typos, unclear passages, missing setup steps. Always welcome, usually fast.

## What is unlikely to land

- Large refactors, architecture changes, rewrites.
- Features not discussed in an issue first. **Open the issue before you write the code** — one message, potentially a saved weekend.
- Unrequested dependency bumps, formatting-only diffs, build-tooling swaps.
- Hand-edits to generated files, or anything that defines an existing concept a second time. See the rules below — both are refused on sight, however good the change underneath is.

## If you need it faster

Fork it. The AGPL-3.0 grants you exactly that. A fork that moves faster than this repo is
a good outcome, not a betrayal — this is a real answer, not a brush-off.

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
   python3 engine/tg.py            # Telegram formatting/wiring
   python3 engine/workflow.py      # --write regenerates docs/WORKFLOW.md
   python3 engine/glossary.py      # --write regenerates docs/GLOSSARY.md
   python3 engine/events.py        # --write regenerates docs/EVENTS.md
   python3 engine/bpmn.py          # --write regenerates workflow/
   python3 engine/agents.py        # seat models + budgets
   python3 engine/bootup.py        # the frozen operator bootup journey
   python3 engine/pipeline.py      # the block register
   python3 engine/roster.py        # persona roster
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

[Open an issue](https://github.com/4242labs/tron/issues/new/choose).

## Licensing

TRON is dual-licensed: AGPL-3.0 for open source, commercial terms on request — see
[LICENSING.md](LICENSING.md).

**By submitting a pull request you grant 42labs the right to distribute your contribution
under both the AGPL-3.0 and 42labs' commercial license.** You keep the copyright to what
you wrote. Without this grant a single merged patch would make the commercial half
unsellable, and we would have to refuse it.
