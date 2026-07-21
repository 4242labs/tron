# Block 07 — the command line

test: python3 -m unittest discover

## Tasks

1. Create `cli.py`: `main(argv=None)` using `argparse`, returning an
   exit code (0 success, 1 failure). Global option `--store PATH`
   (required) names the JSON store; wire the project's own modules
   (import `model`, `store`, `report`, `audit` — do not reimplement).
   Subcommands:
   - `add --id N --title T --severity S [--tag TAG ...]` — build the
     issue with `model.new_issue`, refuse a duplicate id (print
     `duplicate issue id` to stderr, return 1), save via `store.save`,
     record `add` via `audit.record`.
   - `close --id N` — close the matching issue with `model.close`,
     save, record `close`; an unknown id prints `no such issue` to
     stderr and returns 1.
   - `report` — print `report.overview` of the store to stdout.
   Any `ValueError` from the model layer is printed to stderr verbatim
   and returns 1 (project display rules apply to everything printed).
2. Unit tests in `test_cli.py`: at least 8 cases calling `main([...])`
   directly (capture stdout/stderr) covering add, duplicate id, close,
   unknown id, a model validation error surfaced verbatim, and the
   report output. Use `tempfile` stores — never write into the
   repository.
3. Add the line `- cli.py — the triage command line` to `MODULES.md`,
   keeping the list alphabetical by filename.
4. The whole repository suite stays green.
