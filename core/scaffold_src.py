"""core.scaffold_src — the ONE resolver for the real trivial-tip-converter
scaffold source directory that every `core/*_rig.py`, `core/sim/*.py`, and
`engine/land_paperwork_rig.py` copies FROM before seeding a throwaway git
repo (never mutates the source itself — see each rig's own docstring).

Before this module existed, the same absolute path
(`/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter`)
was copy-pasted as a literal `SCAFFOLD_SRC = "..."` into 18 separate rig
files. That path only ever existed on one dev machine — a CI runner (or
anyone else's checkout) has no `/home/anderson` at all, so every one of
those 18 rigs died with `FileNotFoundError` in CI, and the block's own
AC-1/AC-2 proof steps (which run AFTER the L1 rig sweep in engine-ci.yml)
never executed. Fixing that by hand-editing 18 literals would have left the
same failure mode for rig #19 — this is the single source of truth instead:
one resolver, one env var, every rig imports it.

Resolution order:
  1. `TRON_REAL_SCAFFOLD_SRC` env var, if set. `.github/workflows/engine-
     ci.yml` checks out the `tron-meta` repo into a sibling workspace path
     and sets this so CI never depends on any one machine's home directory.
  2. The historical dev-machine absolute path, as a LOCAL FALLBACK ONLY —
     every dev machine this suite was ever written against has tron-meta
     checked out at this exact path; CI always sets the env var above and
     never reaches this branch.

`resolve()` raises immediately with a clear message if neither location
exists as a real directory — one obvious failure at the one place this is
resolved, instead of 18 different confusing `FileNotFoundError`s deep inside
unrelated `shutil.copytree` calls.
"""
import os

ENV_VAR = "TRON_REAL_SCAFFOLD_SRC"
_DEV_FALLBACK = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"


def resolve():
    path = os.environ.get(ENV_VAR, _DEV_FALLBACK)
    if not os.path.isdir(path):
        raise FileNotFoundError(
            f"core.scaffold_src.resolve(): {path!r} does not exist. Set "
            f"{ENV_VAR} to a real checkout of tron-meta's own "
            "sims/_sources/trivial-tip-converter (CI: engine-ci.yml checks "
            "out tron-meta and sets this env var; locally it defaults to "
            f"the historical dev-machine path, {_DEV_FALLBACK!r})."
        )
    return path
