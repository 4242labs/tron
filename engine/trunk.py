"""trunk — TRON's read-only window onto the canon's authority: git trunk + open PRs.

Canon is truth; TRON reads, agents write (realign §5). Each tick TRON refreshes a
local read-only view of the trunk and lists in-flight PRs, then reads the canon
pipeline/blocks from the on-trunk checkout. It NEVER writes to git and NEVER
blocks the loop on the network: a failed fetch reuses the last good snapshot.

The repo root itself is the trunk checkout — agents build in worktrees off it
(`<workspace>/worktrees/<repo>--<branch>/`), so the root stays on the trunk branch.
"""
import json
import subprocess

_TIMEOUT = 20


def _run(args, cwd=None, timeout=_TIMEOUT):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (subprocess.SubprocessError, OSError) as e:
        return 1, "", str(e)


def refresh(repo_root, main_branch="main", dry=False):
    """Fast-forward the trunk checkout to origin. Best-effort: never raises, never
    blocks the loop. Returns (ok, detail). On failure the caller reuses the last
    snapshot (the files already on disk)."""
    if dry or not repo_root:
        return True, "dry/none — read in place"
    rc, _, err = _run(["git", "-C", repo_root, "fetch", "origin", main_branch])
    if rc != 0:
        return False, f"fetch failed: {err.strip()[:120]}"
    # Only ff — never merge/rebase; the root must stay clean on trunk.
    rc, _, err = _run(["git", "-C", repo_root, "merge", "--ff-only",
                       f"origin/{main_branch}"])
    if rc != 0:
        return False, f"ff failed: {err.strip()[:120]}"
    return True, "ff to origin"


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
