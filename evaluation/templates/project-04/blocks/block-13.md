# Block 13 — the CLI

test: python3 -m unittest discover

## Tasks

1. Create `cli.py` importing `store.Store`:
   - `main(argv) -> int` using `argparse`, with `--dir` (default `./data`)
     and subcommands: `put KEY VALUE`, `get KEY`, `del KEY`, `list`. `get`
     prints the value (nothing + exit 1 if absent/deleted); `list` prints
     `KEY=VALUE` lines sorted by key for all live keys; `put`/`del` mutate
     and flush so changes persist. Each invocation opens the store with
     `Store.open(--dir)`.
   - A `if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))`.
2. Tests in `test_cli.py` (tempfile dir, call `main([...])` directly,
   capture stdout): at least 6 cases — put then get prints the value, get of
   an unknown key exits non-zero, del then get is empty, `list` sorted
   output, values persist across separate `main` calls on the same dir.
3. Add the `cli.py` line to `MODULES.md`, alphabetical.
4. The whole repository suite stays green.

_Depends on: 09, 12 — those modules are already landed on the trunk you branch from; import them._
