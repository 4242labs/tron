"""core.gitobs — the new `core/` stack's SINGLE git-observation seam.

This is the ONLY place in `core/` that touches `engine/trunk.py`. Every other
`core/` module (`core/gate.py`, `core/landing.py`, ...) reads git state
exclusively through the functions exposed here — never `import trunk`
directly, never a raw `git`/`subprocess` call of its own. One seam, one
documented boundary, so the fresh stack's substrate coupling stays in one
place instead of scattered import-and-shell-out per module.

Two kinds of reads live here:
  - Reads `engine/trunk.py` already implements correctly: delegated straight
    through (import trunk HERE, in this one module, and call it) — never
    forked, never re-derived. `trunk.py` is a respected, unmodified contract;
    this module's job is to be its one gateway into `core/`, not to replace
    it.
  - `last_touching_sha`: the record-baseline read `core/gate.py` needs
    (last commit touching a path on a ref) that `trunk.py` doesn't expose as
    a standalone public function — implemented directly here (plain
    read-only `git log`), so it lives in the seam instead of inline in
    control-plane logic.
  - `read_pipeline_view`: the wave-5 DISPATCH read `core/pipeline.py` needs —
    the canon pipeline/blocks view AT TRUNK TIP, never the working tree
    (mirrors `engine/fsm.py`'s own `_refresh` seam: `trunk.snapshot_tree` the
    PINNED tree's `pipeline.md` + `blocks/` into a scratch dir, then parse via
    `engine/reader.py`, the respected deterministic no-LLM canon parser —
    imported as-is here, never forked, exactly like `trunk`).

A later wave may fully vendor these reads into `core/` (dropping the
`engine/trunk.py` dependency entirely) — until then, this is the single,
intentional bridge to the ported substrate. Never scattered.
"""
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

import trunk    # noqa: E402 — respected contract, imported as-is (never forked); ONLY here
import reader   # noqa: E402 — respected contract (engine/reader.py), the canon pipeline parser


def tip_sha(root, branch, dry=False):
    """Delegates to `trunk.tip_sha` — the branch's current tip sha, or ''."""
    return trunk.tip_sha(root, branch, dry)


def patch_id(root, branch, truth_ref, dry=False):
    """Delegates to `trunk.patch_id` — the branch's content-identity hash
    against `truth_ref`, or '' (unresolvable/dry, fail-closed downstream)."""
    return trunk.patch_id(root, branch, truth_ref, dry)


def is_ancestor(root, sha, ref, dry=False):
    """Delegates to `trunk.is_ancestor` — True iff `sha` is an ancestor of
    `ref`'s tip."""
    return trunk.is_ancestor(root, sha, ref, dry)


def record_commit_ok(root, block_file, dry=False, truth_ref="main"):
    """Delegates to `trunk.record_commit_ok` — the record-diff content check
    (exactly one file, exactly the `**Status:**` field). Returns (ok, detail)."""
    return trunk.record_commit_ok(root, block_file, dry, truth_ref=truth_ref)


def replica_clean(root, branch, main_branch="main", dry=False):
    """Delegates to `trunk.replica_clean` — the close-time cleanliness check
    (branch gone, no worktree checked out on it). Returns (clean, detail)."""
    return trunk.replica_clean(root, branch, main_branch, dry)


def validate_trunk(root, merged_sha, test_command, test_env=None, ci_check_name=None,
                    dry=False, scratch_root=None):
    """Delegates to `trunk.validate_trunk` — the DONE-ladder wave-3 addition: the
    trunk-stage TRUSTED-VERDICT read `core.gate`'s `gate.trunk` stage needs (re-run the
    project's declared test command once, in a clean detached `git worktree` at
    `merged_sha`, never the worker's own checkout/say-so; or read a named CI check's
    verdict when `ci_check_name` is given). Returns `(status, detail)` with status one
    of `"pass"` / `"fail"` / `"unconfirmed"` — see `trunk.validate_trunk`'s own
    docstring for the full contract (T3: a real failure is never the same thing as
    "can't confirm"; neither is ever a silent free pass).

    `scratch_root` is forwarded as-is — `trunk.py`'s own sealed git-subcommand
    allowlist refuses a `worktree add`/`remove` outside it (fail-closed on a missing
    scratch_root in production; a caller here that needs a real validation run must
    supply one, exactly like `engine/fsm.py`'s own `ctx.scratch_dir` call site)."""
    return trunk.validate_trunk(root, merged_sha, test_command, test_env=test_env,
                                ci_check_name=ci_check_name, dry=dry,
                                scratch_root=scratch_root)


def last_touching_sha(root, ref, path):
    """Last commit sha touching `path` on `ref`, or '' if none/unresolvable.
    A tiny read-only read (mirrors the first half of `trunk.record_commit_ok`'s
    own walk) used to tell 'nothing new since the record baseline' apart from
    'something new landed, check it'. `trunk.py` doesn't expose this specific
    read as a standalone public function, so it's implemented directly here
    (plain `git log`) rather than reaching into `trunk.py`'s private
    internals — the seam's job, not a control-plane module's."""
    r = subprocess.run(["git", "-C", root, "log", "-n", "1", "--format=%H",
                        ref, "--", path], capture_output=True, text=True)
    if r.returncode != 0:
        return ""
    return r.stdout.strip()


def read_pipeline_view(root, main_branch, pipeline_rel, blocks_rel, snapshot_dir, dry=False):
    """The wave-5 DISPATCH read: the canon dispatch view (`blueprint-contracts.md`
    §7) AT TRUNK TIP — never the live working tree (a mid-commit worker's own
    edit, e.g. a record commit in flight, must stay invisible until it actually
    lands; `engine/fsm.py`'s own W9 rationale for the same PINNED-tree read).

    Resolves the trunk tip (`trunk.tip_sha`), snapshots `pipeline_rel` +
    `blocks_rel` OUT OF THAT PINNED SHA into `snapshot_dir` (`trunk.
    snapshot_tree` — a `git archive` extract, atomic-swapped into place), then
    parses the extracted files via `engine/reader.py::load` (the respected,
    deterministic, no-LLM canon parser — imported as-is, never forked).

    Returns `(view, trunk_sha)` — `view` is `reader.load`'s merged
    living-doc-order rows, each enriched with its block file's headers.
    Fail-loud: raises `RuntimeError` on an unresolvable trunk tip or a failed
    snapshot — this seam never hands a control-plane caller a silently
    guessed/empty/stale view; a caller that wants "reuse the last good view on
    a transient read failure" (fsm.py's own discipline) makes that choice
    itself, on the exception, never inside this seam."""
    if dry:
        raise RuntimeError("read_pipeline_view: cannot read a dry-run trunk")
    sha = trunk.tip_sha(root, main_branch, dry)
    if not sha:
        raise RuntimeError(f"read_pipeline_view: unresolvable trunk tip on {main_branch!r}")
    rel_paths = [pipeline_rel, blocks_rel.rstrip("/")]
    ok, err = trunk.snapshot_tree(root, sha, rel_paths, snapshot_dir)
    if not ok:
        raise RuntimeError(f"read_pipeline_view: trunk snapshot @ {sha[:8]} failed: {err}")
    ppath = os.path.join(snapshot_dir, pipeline_rel)
    bpath = os.path.join(snapshot_dir, blocks_rel.rstrip("/"))
    view = reader.load(ppath, bpath)
    return view, sha
