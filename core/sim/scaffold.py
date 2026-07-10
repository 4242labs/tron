"""core.sim.scaffold — builds a FRESH real-git mockup project in a tempdir
for `core.sim.run.run_sim` (wave 14, ADR-0004 §11.5). Two ingredients, never
invented, never reused from the old biased `tron-meta/sims/` harness:

  1. A tiny REAL app (`app/lib/*.py` + `app/tests/test_lib.py`) — a couple of
     source files plus a real declared test command that actually runs and
     exits 0/1 for real (not a bare `true`): the test runner discovers every
     module under `app/lib/`, imports it for real, and asserts its own
     `check()` returns `True` — so `gate.trunk`'s re-validation on trunk is
     validating REAL content, genuinely capable of failing.
  2. `meta/` seeded FROM the respected `templates/project-scaffold` template
     (`git clone`-shaped `shutil.copytree`, verbatim) — `land.sh`,
     `roles.yaml` (engineer/reviewer-code/architect, already bound to the
     REAL personas the template ships at `meta/agents/*.md`), the pipeline/
     block-doc format contract, AGENTS.md, principles.md, everything — the
     SAME external contract `core/engine.py`'s own rig already respects,
     never a hand-rolled substitute. Only `meta/pipeline.md` + `meta/blocks/
     *.md` get REAL content written over the template's own placeholder rows
     (the block list this scaffold is parameterized on); every other file
     under `meta/` is the template, byte-for-byte.

`build(blocks, ...)` returns `(ctx, root)` — `ctx` a real `engine.ctx.Ctx`
pointing at the TRON instance dir this scaffold ALSO authors (`project.yaml`/
`knobs.yaml`, under `meta/agents/tron/`, gitignored by the template's own
`meta/.gitignore` — TRON's own writable folder, never project content,
exactly `core/engine_rig.py`'s own placement), `root` the real git checkout
(detached at `main`, ADR-0002 D1).

The ONE raw-git surface in this module is construction: `git init`/`add`/
`commit` to seed the mockup's OWN history, and one `chmod +x` on the real
`land.sh` this scaffold copies in — the same "real git surface" every prior
`core/*_rig.py`'s own `build_root` already uses to build ITS fixture; no
`core/*.py` production module is touched, and this module never OBSERVES
trunk (that stays `core.gitobs`'s job, exercised by `core.engine.Engine`
itself once `run_sim` boots it)."""
import datetime
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))          # core/sim
_CORE_DIR = os.path.dirname(_HERE)                            # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                          # tron-app worktree root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

from ctx import Ctx   # noqa: E402 — engine/ctx.py, the real runtime-context resolver

# The respected external contract (ADR-0004 §6): seed `meta/` FROM here,
# verbatim — never the old, design-biased `tron-meta/sims/` harness.
SCAFFOLD_META_SRC = os.path.join(_APP_ROOT, "templates", "project-scaffold", "templates", "meta")

MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"
LAND_SH_REL = "meta/scripts/land.sh"
TRON_INST_REL = os.path.join("meta", "agents", "tron")

DEFAULT_TEST_COMMAND = "python3 app/tests/test_lib.py"
DEFAULT_CADENCE = None                 # no reviewer cadence unless the caller asks for one
DEFAULT_SILENCE_PING_MIN = 80          # generous relative to any rig's own tick cap —
DEFAULT_SILENCE_ESCALATE_MIN = 160     # configured for real, never actually fires
DEFAULT_GRANT_TTL = 60


# ── real-git construction helpers (fixture-building only — see module docstring) ──
def _git(args, cwd, check=True):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}) rc={r.returncode}\n"
                           f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return r


def _today():
    return datetime.date.today().isoformat()


# ── app/ — the tiny real app + its real declared test command ──
_APP_INIT = '"""core.sim mockup app — package marker only."""\n'

_APP_TEST_RUNNER = '''"""app/tests/test_lib.py — the mockup's REAL declared test command.

Discovers every module under `app/lib/` (a couple of small real functions,
one file per pipeline block — authored by the SIM's scripted workers as they
build each block), imports it for real, and asserts its own `check()`
returns `True`. Exits 0 when every discovered module's `check()` passes, 1
otherwise — a genuine pass/fail signal `core.gitobs.validate_trunk` (via
`engine/trunk.py::_run_declared_command`) can observe for real, never a bare
`true`. A project with no lib modules yet (nothing landed) passes vacuously
— there is nothing to validate yet, never a false red on an empty tree.
"""
import glob
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.abspath(os.path.join(HERE, "..", "lib"))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ok = True
    checked = 0
    for path in sorted(glob.glob(os.path.join(LIB_DIR, "*.py"))):
        name = os.path.splitext(os.path.basename(path))[0]
        if name == "__init__":
            continue
        checked += 1
        mod = _load(path, name)
        fn = getattr(mod, "check", None)
        if fn is None:
            print(f"FAIL {name}: no check() function")
            ok = False
            continue
        result = fn()
        if result is not True:
            print(f"FAIL {name}: check() returned {result!r}")
            ok = False
        else:
            print(f"PASS {name}")
    print(f"app.tests.test_lib: {checked} module(s) checked, {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
'''


def _seed_app(root):
    lib_dir = os.path.join(root, "app", "lib")
    tests_dir = os.path.join(root, "app", "tests")
    os.makedirs(lib_dir, exist_ok=True)
    os.makedirs(tests_dir, exist_ok=True)
    with open(os.path.join(lib_dir, "__init__.py"), "w") as f:
        f.write(_APP_INIT)
    with open(os.path.join(tests_dir, "test_lib.py"), "w") as f:
        f.write(_APP_TEST_RUNNER)


# ── meta/ — seeded FROM templates/project-scaffold, verbatim ──
def _seed_meta_from_template(root):
    if not os.path.isdir(SCAFFOLD_META_SRC):
        raise RuntimeError(f"core.sim.scaffold: respected scaffold template missing "
                           f"at {SCAFFOLD_META_SRC!r} — refusing to invent one")
    shutil.copytree(SCAFFOLD_META_SRC, os.path.join(root, "meta"), symlinks=True)


PIPELINE_ROW = "| {id} | {title} | 📋 | Block `blocks/{id}.md` |"

PIPELINE_BODY = """## Roadmap

### Phase 1: core.sim L2 fixture

📋 **Status:** To do

Synthetic phase authored by `core.sim.scaffold` — a couple of small real
functions under `app/lib/`, validated for real by the project's own
declared test command (`app/tests/test_lib.py`), driven end to end by the
L2 SIM's own scripted workers.

| ID | Task | Status | Notes |
|:---|:-----|:-------|:------|
{rows}

---

## Technical Debt

Items that exist but are not yet scoped into a block.

| ID | Issue | Status | Notes |
|:---|:------|:-------|:------|

---

## Ad-hoc Blocks

Blocks not tied to a roadmap phase — the architect's own log-review adhoc
blocks (`core/architect.py`'s `log` job) land HERE, one row per finding.

| ID | Task | Status | Notes |
|:---|:-----|:-------|:------|

---

## Backlog

Pipeline-adjacent items waiting to be promoted into a phase.

| ID | Task | Status | Notes |
|:---|:-----|:-------|:------|
"""

BLOCK_DOC = """# Block {id}: {title}

**Phase:** 1 — core.sim L2 fixture
**Status:** 📋 To do
**Depends on:** {depends_on}
**Blocks:** none
**Reviewer class:** {reviewer_class}
**Merge approval:** auto
**Deploy:** none{tags_line}
**Created:** {created}

---

## Context

Synthetic block doc for `core.sim` — the fresh, unbiased L2 SIM harness
(ADR-0004 §11.5). Implements `app/lib/{id}.py`, validated for real by the
project's declared test command.

---

## Tasks

### T1: implement `app/lib/{id}.py`

Author a small real function; its module-level `check()` must return `True`
once genuinely correct.

---

## Acceptance Criteria

| # | Criterion | Verification method | Owner |
|:--|:--|:--|:--|
| AC-1 | `app/lib/{id}.py::check()` returns `True` | `cmd:python3 app/tests/test_lib.py` | engineer |

---

## Out of Scope

Nothing — a trivial single-function fixture block.

---

## Block Completion Gate

Do not mark this block done until:
- [ ] All acceptance criteria PASS in the Completion Report (no UNVERIFIED entries)
- [ ] Post-merge re-validation clean on trunk
- [ ] User explicitly acknowledged the Completion Report and triggered session-end
"""


def _block_title(block):
    return block.get("title") or f"core.sim fixture block {block['id']}"


def seed_pipeline(root, blocks):
    """Overwrite `meta/pipeline.md` (already seeded verbatim by
    `_seed_meta_from_template`) with the SAME legend/format-contract preamble
    the template ships, but real Roadmap rows for `blocks` — and empty
    (header-only) Technical Debt / Ad-hoc / Backlog tables, never the
    template's own `<placeholder>` rows (which would otherwise parse as
    real-but-block-file-less pipeline rows)."""
    ppath = os.path.join(root, PIPELINE_REL)
    with open(ppath) as f:
        tmpl = f.read()
    preamble = tmpl.split("## Roadmap", 1)[0]
    preamble = preamble.replace("<PROJECT_NAME>", "core-sim-mockup")
    preamble = preamble.replace("<YYYY-MM-DD>", _today())
    rows = "\n".join(PIPELINE_ROW.format(id=b["id"], title=_block_title(b)) for b in blocks)
    content = preamble + PIPELINE_BODY.format(rows=rows)
    with open(ppath, "w") as f:
        f.write(content)


def seed_blocks(root, blocks):
    bdir = os.path.join(root, BLOCKS_REL)
    os.makedirs(bdir, exist_ok=True)
    for b in blocks:
        depends_on = ", ".join(b.get("depends_on") or []) or "none"
        tags = b.get("tags")
        tags_line = f"\n**Tags:** {', '.join(tags) if isinstance(tags, (list, tuple)) else tags}" if tags else ""
        doc = BLOCK_DOC.format(
            id=b["id"], title=_block_title(b), depends_on=depends_on,
            reviewer_class=b.get("reviewer_class") or "none", tags_line=tags_line,
            created=_today())
        with open(os.path.join(bdir, f"{b['id']}.md"), "w") as f:
            f.write(doc)


def write_project_yaml(inst_dir, root, test_command):
    os.makedirs(inst_dir, exist_ok=True)
    doc = {
        "repo": {"root": root, "main_branch": MAIN, "remote": "none", "staging": "none"},
        "test": {"command": test_command},
    }
    with open(os.path.join(inst_dir, "project.yaml"), "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)


def write_knobs(inst_dir, worker_count=1, cadence=None, silence_ping_min=DEFAULT_SILENCE_PING_MIN,
                silence_escalate_min=DEFAULT_SILENCE_ESCALATE_MIN, grant_ttl=DEFAULT_GRANT_TTL):
    doc = {
        "worker_count": worker_count,             # informational — Engine.start's own param governs
        "silence_ping_min": silence_ping_min,
        "silence_escalate_min": silence_escalate_min,
        "grant_ttl": grant_ttl,
    }
    if cadence:
        doc["cadence"] = dict(cadence)
    with open(os.path.join(inst_dir, "knobs.yaml"), "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)


def build(blocks, test_command=None, cadence=None, worker_count=1,
         silence_ping_min=DEFAULT_SILENCE_PING_MIN, silence_escalate_min=DEFAULT_SILENCE_ESCALATE_MIN,
         grant_ttl=DEFAULT_GRANT_TTL, tmp_prefix="tron-core-sim-"):
    """Build the fresh real-git mockup: `meta/` seeded from `templates/
    project-scaffold` (verbatim, except `pipeline.md`/`meta/blocks/*.md`,
    which carry `blocks`' real content), a tiny real `app/`, one seed commit
    on `main` (detached, ADR-0002 D1), then the TRON instance dir (`project.
    yaml`/`knobs.yaml`, gitignored, never committed — same placement `core/
    engine_rig.py` already uses). Returns `(ctx, root)`."""
    d = tempfile.mkdtemp(prefix=tmp_prefix)
    root = os.path.join(d, "mockup")
    os.makedirs(root, exist_ok=True)

    _seed_meta_from_template(root)
    _seed_app(root)
    seed_pipeline(root, blocks)
    seed_blocks(root, blocks)

    land_sh = os.path.join(root, LAND_SH_REL)
    os.chmod(land_sh, os.stat(land_sh).st_mode | 0o111)

    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "sim@test.local"], root)
    _git(["config", "user.name", "core-sim-scaffold"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: fresh L2 SIM mockup (project-scaffold meta/ + a tiny real app)"], root)
    _git(["checkout", "--detach", MAIN], root)

    inst_dir = os.path.join(root, TRON_INST_REL)
    write_project_yaml(inst_dir, root, test_command or DEFAULT_TEST_COMMAND)
    write_knobs(inst_dir, worker_count=worker_count, cadence=cadence,
               silence_ping_min=silence_ping_min, silence_escalate_min=silence_escalate_min,
               grant_ttl=grant_ttl)

    return Ctx(inst_dir), root
