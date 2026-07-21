# Playbook — shared infra memory

Durable, project-specific how-to knowledge. Agents UPDATE this file (on
their branch, like any file) when they learn something lasting; judges hold
deliveries to it.

- Run the whole suite from the project root: `python3 -m unittest discover`.
- Modules live flat in the project root; tests are `test_<module>.py`.
- Persistence modules take a filesystem path; tests use a `tempfile`
  directory and clean up after themselves — never write into the repo tree.
- The canonical module signatures are in `context.md`; depend on them.
