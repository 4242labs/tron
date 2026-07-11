"""core.archive_dep_rig — pure (no-git, no-LLM) regression lock for the SECOND
wall T2-01-05 surfaced: a block whose file is ARCHIVED at close (git-mv'd to
`meta/blocks/archive/` by the worker's session-end skill — canon PMT-CLOSE's
"the block archival") must still resolve `done` for any dependent block.

Confirmed root (live, T2-01-05): the moment block 01-02 was archived,
`engine/reader.load_blocks` (which lists only the live `meta/blocks/` dir and
skips `archive/`) stopped resolving its status, so `reader.load`'s merged view
carried 01-02 with no status. Block 01-03 (`Depends on: 01-02`) then read its
dependency as `None` — neither `done` (so `core/pipeline.dispatchable` would
never dispatch it) nor an in-scope pending wait — and `core/session.py::check`
raised `inconsistent pipeline state ... stuck ... {01-02: None}`, killing the
run even though 01-02 was genuinely ✅ on trunk.

THE FIX under test (two seams, one invariant — an archived block is done and
must resolve as done everywhere a dependency is read):
  - `engine/reader.load` resolves an archived block's status/deps from
    `load_archived_blocks` (`archived=True`, `has_block_file=False` — out of
    the dispatch view, but its status resolves).
  - `core/session.py::check` includes `archived` rows in its dep index (it
    already excluded `has_block_file=False`), mirroring
    `core/pipeline.dispatchable`'s own unfiltered index.

Pure filesystem fixtures + real `reader.load`/`reader.dispatchable`/
`session.check` — no git, no trunk, ~0 tokens. `ok(name, cond, detail)`
collector; `main()` prints every line and exits non-zero on any fail.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
ENGINE_DIR = os.path.join(APP_ROOT, "engine")
for p in (ENGINE_DIR, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import reader    # engine/reader.py — the canon pipeline parser under test
import session   # core/session.py — the consistency check under test

_RESULTS = []


def ok(name, cond, detail=""):
    _RESULTS.append(bool(cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


PIPELINE_MD = """\
# Pipeline

## Phase 1 — Core

| ID | Task | Status | Notes |
| --- | --- | --- | --- |
| 01-01 | foundation | ✅ | |
| 01-02 | logic (depends 01-01) | ✅ | |
| 01-03 | wiring (depends 01-02) | 📋 | |
"""

BLOCK = """\
# Block {bid}: {title}

**Phase:** 1
**Status:** {status}
**Depends on:** {deps}

## Body
whatever.
"""


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def build_fixture(archive_02=True, drop_02=False):
    """A real on-disk pipeline.md + blocks/ dir. 01-01 done (live), 01-03
    to-do (live, Depends on 01-02). 01-02 is EITHER archived (moved to
    archive/, the real close behavior) or, for the adversarial control,
    dropped entirely (neither live nor archived — a genuine gap the check
    must STILL catch)."""
    root = tempfile.mkdtemp(prefix="tron-archdep-")
    meta = os.path.join(root, "meta")
    blocks = os.path.join(meta, "blocks")
    _write(os.path.join(meta, "pipeline.md"), PIPELINE_MD)
    _write(os.path.join(blocks, "01-01.md"),
           BLOCK.format(bid="01-01", title="foundation", status="✅ Done", deps="none"))
    _write(os.path.join(blocks, "01-03.md"),
           BLOCK.format(bid="01-03", title="wiring", status="📋 To do", deps="01-02"))
    if archive_02 and not drop_02:
        _write(os.path.join(blocks, "archive", "01-02.md"),
               BLOCK.format(bid="01-02", title="logic", status="✅ Done", deps="01-01"))
    elif not drop_02:
        _write(os.path.join(blocks, "01-02.md"),
               BLOCK.format(bid="01-02", title="logic", status="✅ Done", deps="01-01"))
    return os.path.join(meta, "pipeline.md"), blocks


def main():
    # ═══ Phase A — archived dependency resolves `done`, dependent is healthy ═══
    ppath, bpath = build_fixture(archive_02=True)
    view = reader.load(ppath, bpath)
    row = {r["id"]: r for r in view}

    ok("A1: archived 01-02 is OUT of the live dispatch view (has_block_file=False) "
       "but flagged archived",
       row["01-02"].get("has_block_file") is False and row["01-02"].get("archived") is True,
       f"01-02={ {k: row['01-02'].get(k) for k in ('has_block_file','archived','status')} }")

    ok("A2 (THE FIX — must be GREEN): archived 01-02's status resolves to `done` from "
       "the archive, not None",
       row["01-02"].get("status") == "done",
       f"status={row['01-02'].get('status')!r}")

    idx = reader.status_index(view)
    ok("A3: the dependency index reads 01-02 as done, so 01-03's dep is satisfied",
       idx.get("01-02") == "done",
       f"idx[01-02]={idx.get('01-02')!r}")

    ok("A4 (THE DISPATCH KILLER — must be GREEN): 01-03 (Depends on 01-02) is "
       "dispatchable — its archived dependency no longer blocks it",
       reader.dispatchable(row["01-03"], idx),
       f"01-03 status={row['01-03'].get('status')} deps={row['01-03'].get('depends_on')}")

    # session.check must NOT raise: 01-01 done, 01-02 archived-done, 01-03 dispatchable.
    raised = None
    try:
        session.check({}, view)
    except RuntimeError as e:
        raised = str(e)
    ok("A5 (THE SESSION KILLER — must be GREEN): core.session.check does NOT flag "
       "01-03 stuck when its dependency is archived (the exact T2-01-05 crash, gone)",
       raised is None,
       f"raised={raised!r}")

    # ═══ Phase B — adversarial: a TRULY missing block is STILL a real gap ═══
    # Proves the fix rescued only the archived case and did not neuter the
    # check: 01-02 absent from BOTH live and archive/ must still wedge 01-03.
    ppath_b, bpath_b = build_fixture(drop_02=True)
    view_b = reader.load(ppath_b, bpath_b)
    row_b = {r["id"]: r for r in view_b}
    ok("B1: with 01-02 truly gone it is neither a live block nor an archived one "
       "(has_block_file=False, archived=False) — so dep resolution can't see it as "
       "a real done block, only the living doc's unbacked row remains",
       row_b["01-02"].get("has_block_file") is False
       and row_b["01-02"].get("archived") is False,
       f"01-02={ {k: row_b['01-02'].get(k) for k in ('status','archived','has_block_file')} }")

    raised_b = None
    try:
        session.check({}, view_b)
    except RuntimeError as e:
        raised_b = str(e)
    ok("B2 (ADVERSARIAL — must still FIRE): core.session.check STILL raises on a "
       "genuinely missing dependency — the fix rescued the archived case only, "
       "never weakened the real-gap guard",
       raised_b is not None and "01-03" in raised_b,
       f"raised={raised_b!r}")

    total, passed = len(_RESULTS), sum(_RESULTS)
    print(f"\narchive_dep_rig: PASS ({passed}/{total})")
    print(f"fixture roots under {tempfile.gettempdir()}/tron-archdep-*")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
