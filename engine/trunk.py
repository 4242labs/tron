"""trunk — TRON's read-only window onto the canon's authority: git trunk + open PRs.

Canon is truth; TRON reads, agents write (realign §5). Each tick TRON refreshes a
local read-only view of the trunk and lists in-flight PRs, then reads the canon
pipeline/blocks from the on-trunk checkout. It NEVER writes to git and NEVER
blocks the loop on the network: a failed fetch reuses the last good snapshot.

The repo root itself is the trunk checkout — agents build in worktrees off it
(`<workspace>/worktrees/<repo>--<branch>/`), so the root stays on the trunk branch.
"""
import os
import json
import subprocess

_TIMEOUT = 20


def _run(args, cwd=None, timeout=_TIMEOUT):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (subprocess.SubprocessError, OSError) as e:
        return 1, "", str(e)


def refresh(repo_root, main_branch="main", dry=False, remote=None):
    """Fast-forward the trunk checkout to origin. Best-effort: never raises, never
    blocks the loop. Returns (ok, detail). On failure the caller reuses the last
    snapshot (the files already on disk).

    Local / no-remote mode: when the project declares no remote (`repo.remote`
    absent or `none`), the root IS the authority — there is nothing to fetch, so we
    read HEAD in place (mirrors the `not repo_root` branch) instead of treating the
    missing remote as a boot-fatal fetch failure. The remote path is unchanged."""
    if dry or not repo_root:
        return True, "dry/none — read in place"
    if not remote or remote == "none":
        return True, "no remote — read in place"
    rc, _, err = _run(["git", "-C", repo_root, "fetch", "origin", main_branch])
    if rc != 0:
        return False, f"fetch failed: {err.strip()[:120]}"
    # Only ff — never merge/rebase; the root must stay clean on trunk.
    rc, _, err = _run(["git", "-C", repo_root, "merge", "--ff-only",
                       f"origin/{main_branch}"])
    if rc != 0:
        return False, f"ff failed: {err.strip()[:120]}"
    return True, "ff to origin"


def head_sha(repo_root, dry=False):
    """The trunk checkout's current HEAD sha (short) — stamped on every forensic record so a
    failure pins the exact tree it happened on. Best-effort: '' if unknown (never blocks)."""
    if dry or not repo_root:
        return "dry" if dry else ""
    rc, out, _ = _run(["git", "-C", repo_root, "rev-parse", "--short", "HEAD"])
    return out.strip() if rc == 0 else ""


def open_prs(repo_root, dry=False):
    """In-flight PRs keyed by head branch: {branch: {number, title, state, draft, mergeable}}.
    Best-effort via `gh`; empty dict if gh is absent or errors (TRON degrades, never blocks)."""
    if dry or not repo_root:
        return {}
    rc, out, _ = _run(["gh", "pr", "list", "--state", "open", "--json",
                       "number,headRefName,title,isDraft,mergeable,statusCheckRollup"],
                      cwd=repo_root)
    if rc != 0 or not out.strip():
        return {}
    try:
        items = json.loads(out)
    except json.JSONDecodeError:
        return {}
    prs = {}
    for it in items:
        prs[it.get("headRefName")] = {
            "number": it.get("number"),
            "title": it.get("title"),
            "draft": it.get("isDraft"),
            "mergeable": it.get("mergeable"),
            "checks": _rollup(it.get("statusCheckRollup")),
        }
    return prs


def branch_merged(repo_root, branch, main_branch="main", dry=False):
    """True iff `branch`'s tip is already an ancestor of trunk HEAD (MG-01) — the block's
    commits reached trunk directly, with no PR for the gate to have seen. Best-effort: False
    if the branch is unresolvable (never existed here, or was pruned) or on any git error —
    an unknown branch is never treated as a merge."""
    if dry or not repo_root or not branch:
        return False
    rc, _, _ = _run(["git", "-C", repo_root, "merge-base", "--is-ancestor", branch, main_branch])
    return rc == 0


def branch_exists(repo_root, branch, dry=False):
    """True iff `branch` resolves to a real commit in this repo. The local/no-remote gate needs
    this: with no PR to prove a branch was pushed, the engine merges the block's branch (reported
    name, else the `feat/<block>` convention) ONLY when it actually exists — verified, never a
    guess it then blindly merges. False in dry (no git) and on any error / missing branch."""
    if dry or not repo_root or not branch:
        return False
    rc, _, _ = _run(["git", "-C", repo_root, "rev-parse", "--verify", "--quiet", branch])
    return rc == 0


def merge_ff_only(repo_root, branch, main_branch="main", dry=False):
    """Fast-forward trunk to an already-validated block branch — the local/no-remote merge.
    The engine owns the trunk merge (MG-01): with no remote there is no PR to land, so the
    engine advances trunk itself, but ONLY as a fast-forward — never a merge commit, never a
    force. A non-ff (trunk moved under the branch) returns ok=False so the caller re-nudges
    the worker to rebase, rather than fabricating history. Returns (ok, err)."""
    if dry or not repo_root or not branch:
        return (dry, "")
    _run(["git", "-C", repo_root, "checkout", main_branch])   # root stays on trunk; belt-and-suspenders
    rc, _, err = _run(["git", "-C", repo_root, "merge", "--ff-only", branch])
    return rc == 0, err


def record_commit_ok(repo_root, block_file, dry=False):
    """The record-commit content check (01-11 FX-3): inspect the LAST commit that touched the
    block doc — its OWN diff, never a trunk range (with worker_count > 1 another block's merge
    can land between merge-accept and record; a range check would false-positive a legitimate
    record). Conforming = exactly one file (the block doc, matched on its FULL repo-relative
    path — a same-named file elsewhere never passes) and every changed line is the
    `**Status:**` field. Anything else is an out-of-gate change wearing the record's clothes.
    `block_file` must be the repo-relative path (the caller resolves it from the blocks dir).
    Returns (ok, detail)."""
    if dry or not repo_root or not block_file:
        return True, "dry/none"
    rc, out, err = _run(["git", "-C", repo_root, "log", "-n", "1", "--format=%H",
                         "--", block_file])
    sha = out.strip()
    if rc != 0 or not sha:
        return False, f"no commit found touching {block_file}"
    rc, out, _ = _run(["git", "-C", repo_root, "show", "--name-only", "--format=", sha])
    files = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if rc != 0 or files != [block_file]:
        return False, (f"record commit {sha[:8]} touches {files or 'nothing'} "
                       f"— must be exactly {block_file}")
    rc, out, _ = _run(["git", "-C", repo_root, "show", "--unified=0", "--format=", sha])
    if rc != 0:
        return False, f"record commit {sha[:8]}: diff unreadable"
    for ln in out.splitlines():
        if ln.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if ln.startswith(("+", "-")) and not ln[1:].strip().lower().startswith("**status:**"):
            return False, f"record commit {sha[:8]} changes more than the Status field"
    return True, sha[:8]


def replica_clean(repo_root, branch, main_branch="main", dry=False):
    """CLOSE-gate cleanliness (01-11 FX-9): deterministic git reads — the worker's clean-exit
    claim is verified, never trusted. Scoped to THIS block (review finding: with
    worker_count > 1 another live worker's legitimate worktree must never read as this
    closer's dirt): clean = the block's branch is gone and no worktree is checked out on it.
    Returns (clean, detail)."""
    if dry or not repo_root or not branch or branch == main_branch:
        return True, "dry/none"
    leftovers = []
    if branch_exists(repo_root, branch):
        leftovers.append(f"leftover branch {branch}")
    rc, out, _ = _run(["git", "-C", repo_root, "worktree", "list", "--porcelain"])
    if rc == 0:
        tree, ref = None, f"refs/heads/{branch}"
        for ln in out.splitlines():
            if ln.startswith("worktree "):
                tree = ln.split(" ", 1)[1]
            elif ln.startswith("branch ") and ln.split(" ", 1)[1] == ref:
                leftovers.append(f"leftover worktree on {branch}: {tree}")
    return (not leftovers), "; ".join(leftovers)


def _rollup(checks):
    """Reduce gh's per-check rollup to one of: passing | failing | pending | none."""
    if not checks:
        return "none"
    states = [c.get("conclusion") or c.get("state") or "" for c in checks]
    if any(s in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT") for s in states):
        return "failing"
    if any(s in ("", "PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED") for s in states):
        return "pending"
    return "passing"
