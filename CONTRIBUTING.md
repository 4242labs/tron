# Contributing to TRON

> [!IMPORTANT]
> **Closed to outside contributions.** TRON is research: this repo is the system measured in the
> [preprint](https://doi.org/10.5281/zenodo.21613792), and a patch stream through it would quietly
> invalidate what was published. Pull requests will be closed unmerged, however good they are —
> that is about the paper, not about you.
>
> **Reach out anyway, if you'd like.** Questions about the design, an argument with a result, an
> idea, an interest in using TRON somewhere — all genuinely welcome, by
> [issue](https://github.com/4242labs/tron/issues/new) or at <ahoy@42labs.io>. It is only the merge
> button that is shut.
>
> Everything below stays published because it describes how this repo actually works — which is
> what you inherit if you fork it, and what the terms would be if contributions ever open.

TRON is a **canon repo** — one source of truth for the orchestrator. Per-project or
machine-specific assumptions live in seeded instances, never here.

## What is still open

- **Bug reports with a reproduction.** A good report names the flow step or the event involved — and, best of all, comes with a failing selftest. These get read and they get fixed.
- **Questions and conversation.** An issue or an email. No patch required, and none expected.
- **Forks.** The AGPL-3.0 grants you exactly that. If you need TRON to move somewhere it isn't going, that is the real answer, not a brush-off.

## What is not

Pull requests — features, refactors, rewrites, dependency bumps, formatting diffs, and yes, typo
fixes too. Some of them would be good changes; that isn't the point. The engine that ran the
experiments has to stay the engine described in the paper. Send the typo as an issue and it gets
fixed here.

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

How a change is made here — the maintainers' loop, and what a fork inherits.

1. **Branch** off `main`. One logical change per branch.
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
   linear — the branch is squashed or rebased on merge, not merge-committed.
5. A maintainer merges. Finished work is never reopened; follow-ups are new PRs.

## Reporting bugs / ideas

[Open an issue](https://github.com/4242labs/tron/issues/new). Or write to <ahoy@42labs.io> if it is
more of a conversation than a ticket.

## Licensing

TRON is dual-licensed: AGPL-3.0 for open source, commercial terms on request — see
[LICENSING.md](LICENSING.md).

**By submitting a pull request you grant 42labs the right to distribute your contribution
under both the AGPL-3.0 and 42labs' commercial license.** You keep the copyright to what
you wrote. Without this grant a single merged patch would make the commercial half
unsellable, and we would have to refuse it.
