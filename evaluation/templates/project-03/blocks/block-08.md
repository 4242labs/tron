# Block 08 — acceptance

test: python3 -m unittest discover
trunk-test: python3 -m unittest discover

## Tasks

1. Create `test_acceptance.py`, one end-to-end scenario driven ONLY
   through `cli.main` against a `tempfile` store: add three issues of
   different severities and tags; close one; assert the `report` output
   is exactly the expected overview (counts, `top open issues:` order by
   rank); assert `audit.history` is exactly the four recorded lines in
   order; assert `store.load` returns the surviving state sorted by id;
   assert a duplicate add returns 1 and changes neither store nor audit.
2. Create `README.md`: what triage is, a usage example for each of the
   three subcommands, and a pointer to `MODULES.md`.
3. Verify `MODULES.md` lists ALL seven modules alphabetically (no line
   to add for this block — it adds only tests and docs).
4. The whole repository suite stays green.
