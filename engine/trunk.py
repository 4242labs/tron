"""trunk — TRON's read-only window onto the canon's authority: git trunk + open PRs.

Canon is truth; TRON reads, agents write (realign §5). Each tick TRON refreshes a
local read-only view of the trunk and lists in-flight PRs, then reads the canon
pipeline/blocks from the on-trunk checkout. Rider (01-18): this predates local-mode
landing and is no longer literally true — in LOCAL mode (no remote) this module also
performs the gate's own landing acts (`merge_ff_only`, `land_docs`,
`land_ordered_merge`): ff-only trunk merges and paperwork lands, the engine executing
what a worker's PR-merge would do in remote mode. Even there it never writes canon
CONTENT — no pipeline/block authoring, no commit body it composed itself — and it
NEVER blocks the loop on the network: a failed fetch reuses the last good snapshot.

The repo root itself is the trunk checkout — agents build in worktrees off it
(`<workspace>/worktrees/<repo>--<branch>/`), so the root stays on the trunk branch.
"""
import os
import json
import shutil
import subprocess
import tarfile

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


def snapshot_tree(repo_root, sha, rel_paths, dest, dry=False):
    """W9 (tron-13): materialize the PINNED tree's canon files — trunk truth is COMMITTED
    truth, never the working tree a mid-commit worker is editing in the root checkout
    (the record commit is exactly such an edit, ordered by the engine itself; reading
    the live tree once fired block_done + the record content check 2s before the record
    commit existed). `git archive <sha> -- <paths>` into a tar, extracted into `dest`
    (wiped first). Returns (ok, err); the caller treats failure as the read-failure
    path (reuse the last good snapshot, never block the loop)."""
    if dry or not repo_root or not sha:
        return False, "dry/none"
    tmp = dest.rstrip("/") + ".tmp"
    try:
        # Atomic swap (W9 rider 1): build the new snapshot BESIDE the live one and
        # rename over it only when complete — a failed archive must leave the last
        # good snapshot in place, never an empty zero-block view (worse than stale).
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        tarpath = os.path.join(tmp, ".snap.tar")
        rc, _, err = _run(["git", "-C", repo_root, "archive", "-o", tarpath,
                           sha, "--", *rel_paths])
        if rc != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            return False, err.strip()
        with tarfile.open(tarpath) as tf:
            tf.extractall(tmp)
        os.remove(tarpath)
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(tmp, dest)
        return True, ""
    except Exception as e:  # tar/fs errors are read failures, never loop-breakers
        shutil.rmtree(tmp, ignore_errors=True)
        return False, f"{type(e).__name__}: {e}"


def is_ancestor(repo_root, sha, main_branch="main", dry=False):
    """True iff `sha` is an ancestor of trunk HEAD. A-5: the held-stage predicate for
    trunk+ rungs is the MERGED sha's ancestry — never the branch tip, which goes stale
    the moment the worker parks paperwork commits on its branch (the W1 case). Ancestry
    survives a `git revert` (history keeps the sha) and breaks only on history surgery
    (force-push / reset) — exactly the contradiction class the ratchet must name."""
    if dry or not repo_root or not sha:
        return True
    rc, _, _ = _run(["git", "-C", repo_root, "merge-base", "--is-ancestor", sha, main_branch])
    return rc == 0


def tip_sha(repo_root, branch, dry=False):
    """The branch's current tip sha, or '' (dry / unresolvable). A-3: the merge grant binds
    the exact sha the operator saw at park — this is how park and execution compare it."""
    if dry or not repo_root or not branch:
        return ""
    rc, out, _ = _run(["git", "-C", repo_root, "rev-parse", "--verify", "--quiet", branch])
    return out.strip() if rc == 0 else ""


def branch_exists(repo_root, branch, dry=False):
    """True iff `branch` resolves to a real commit in this repo. The local/no-remote gate needs
    this: with no PR to prove a branch was pushed, the engine merges the block's branch (reported
    name, else the `feat/<block>` convention) ONLY when it actually exists — verified, never a
    guess it then blindly merges. False in dry (no git) and on any error / missing branch."""
    if dry or not repo_root or not branch:
        return False
    rc, _, _ = _run(["git", "-C", repo_root, "rev-parse", "--verify", "--quiet", branch])
    return rc == 0


def _worktree_path_for_branch(repo_root, branch):
    """The worktree path (if any) with `branch` checked out — None if it's not checked
    out anywhere. Best-effort: '' output / a git error reads as no worktree."""
    rc, out, _ = _run(["git", "-C", repo_root, "worktree", "list", "--porcelain"])
    if rc != 0:
        return None
    path, ref = None, f"refs/heads/{branch}"
    for ln in out.splitlines():
        if ln.startswith("worktree "):
            path = ln.split(" ", 1)[1]
        elif ln.startswith("branch ") and ln.split(" ", 1)[1] == ref:
            return path
    return None


def remove_worktree_for_branch(repo_root, branch, dry=False):
    """Lander ordering (D-15-4, tron-15): a worktree still checked out on `branch` blocks
    `git branch -d` (`ref survives: cannot delete branch ... used by worktree`) — every
    supervised landing hit this because the branch delete was tried with the worktree still
    in place. Remove the worktree FIRST (best-effort; a stale/dirty worktree still fails
    softly and leaves the branch-delete error to name it), THEN the caller deletes the
    branch. No-op when nothing has `branch` checked out."""
    if dry or not repo_root or not branch:
        return
    path = _worktree_path_for_branch(repo_root, branch)
    if path:
        _run(["git", "-C", repo_root, "worktree", "remove", path])


def merge_ff_only(repo_root, branch, main_branch="main", dry=False):
    """Fast-forward trunk to an already-validated block branch — the local/no-remote merge.
    The engine owns the trunk merge (MG-01): with no remote there is no PR to land, so the
    engine advances trunk itself, but ONLY as a fast-forward — never a merge commit, never a
    force.

    T1 (01-17, tron-22/23/24): the dominant wall class across the campaign — a lander branch
    cut before another lander moved trunk fails this ff-only, every time, on pure timing.
    Every caller (`land_docs`, `land_ordered_merge`, the DONE-gate's own direct call) shares
    this one primitive, so the fix lives here ONCE: on a first ff-refusal, rebase `branch`
    onto the CURRENT trunk tip ONE time and retry the ff-only merge. `git rebase <upstream>
    <branch>` leaves `branch` itself checked out (an implicit `switch`) — re-checkout
    `main_branch` before the retry, exactly like the top of this function. A conflicted
    rebase aborts cleanly (never leaves the repo mid-rebase) and a second refusal after a
    clean rebase both fall through to the ORIGINAL non-ff error text — today's wall detail,
    unchanged; only the deterministic, bounded, no-knob retry is new.

    T5 (01-15, tron-16 boot-1 residue): verifies `main_branch` itself exists BEFORE acting —
    a missing trunk branch (an env fault) used to fall through the checkout silently (git
    swallowed as a belt-and-suspenders no-op) and merge the block branch onto whatever HEAD
    happened to be, action and verification going out of sync. Now a missing trunk branch,
    or a checkout that fails for any other reason, is an `error`-shaped (ok=False) return —
    never a silent merge onto HEAD. Returns (ok, err)."""
    if dry or not repo_root or not branch:
        return (dry, "")
    if not branch_exists(repo_root, main_branch, dry):
        return False, f"trunk branch '{main_branch}' does not exist"
    rc, _, err = _run(["git", "-C", repo_root, "checkout", main_branch])
    if rc != 0:
        return False, f"checkout {main_branch} failed: {err.strip()[:200]}"
    rc, _, err = _run(["git", "-C", repo_root, "merge", "--ff-only", branch])
    if rc == 0:
        return True, err
    non_ff_detail = err          # T1: today's detail — preserved through the retry either way
    rrc, _, _ = _run(["git", "-C", repo_root, "rebase", main_branch, branch])
    if rrc != 0:
        _run(["git", "-C", repo_root, "rebase", "--abort"])
        _run(["git", "-C", repo_root, "checkout", main_branch])
        return False, non_ff_detail
    rc2, _, err2 = _run(["git", "-C", repo_root, "checkout", main_branch])
    if rc2 != 0:
        return False, non_ff_detail
    rc3, _, _ = _run(["git", "-C", repo_root, "merge", "--ff-only", branch])
    if rc3 != 0:
        return False, non_ff_detail
    return True, ""


def land_ordered_merge(repo_root, branch, main_branch="main", dry=False):
    """T6 (01-15): the violation-wall `approve` settle's landing primitive — an EXPLICIT
    operator-ordered merge of the WHOLE named branch (no paperwork allowlist: the operator
    already saw and approved the range naming it a landable fix, tron-16 CASE-003's residue
    — post-close code with no landing path otherwise). Same ff-only discipline as every
    other merge here, then the SAME lander cleanup `land_docs` runs on success (worktree
    gone first, D-15-4, then the branch ref) — one physical landing mechanism, reused, never
    a second one. Returns (ok, detail)."""
    if dry or not repo_root or not branch or branch == main_branch:
        return False, "dry/none"
    if not branch_exists(repo_root, branch, dry):
        return False, f"no branch {branch}"
    okm, err = merge_ff_only(repo_root, branch, main_branch, dry)
    if not okm:
        return False, err.strip()
    sha = head_sha(repo_root)
    remove_worktree_for_branch(repo_root, branch, dry)       # D-15-4: worktree gone first
    rc, _, derr = _run(["git", "-C", repo_root, "branch", "-d", branch])
    note = f"; ref survives: {derr.strip()}" if rc != 0 else ""
    return True, f"landed @ {sha[:7]}{note}"


def _patch_id_one(repo_root, ref, main_branch):
    """`git patch-id --stable` for `ref`'s own diff against its merge-base with trunk —
    one hash representing the CONTENT of everything the branch adds, invariant to which
    exact commits carry it (a rebase reshuffles commits/shas; the net diff, and so the
    patch-id, stays the same). '' on any git failure (unresolvable ref, empty diff, patch-id
    unavailable) — callers must treat '' as a non-match, never a free pass."""
    rc, base, _ = _run(["git", "-C", repo_root, "merge-base", main_branch, ref])
    base = base.strip()
    if rc != 0 or not base:
        return ""
    try:
        diff = subprocess.run(["git", "-C", repo_root, "diff", f"{base}..{ref}"],
                              capture_output=True, text=True, timeout=_TIMEOUT)
    except (subprocess.SubprocessError, OSError):
        return ""
    if diff.returncode != 0 or not diff.stdout.strip():
        return ""
    try:
        pid = subprocess.run(["git", "-C", repo_root, "patch-id", "--stable"],
                             input=diff.stdout, capture_output=True, text=True,
                             timeout=_TIMEOUT)
    except (subprocess.SubprocessError, OSError):
        return ""
    if pid.returncode != 0 or not pid.stdout.strip():
        return ""
    return pid.stdout.split()[0]


def patch_id_matches(repo_root, ref_a, ref_b, main_branch="main", dry=False):
    """T1 (D-15-1, tron-15 race): content-identity check for the merge-in-flight re-pin —
    a moved branch tip while an approved merge is in flight is the worker completing the
    SAME ordered merge (e.g. a rebase the engine itself asked for after a non-ff), not an
    unseen change, exactly when the two tips introduce an IDENTICAL diff (`git patch-id
    --stable`, so line-shift-only differences from the rebase never fool it). Best-effort:
    dry / an unresolvable ref / any git failure -> False (no match) — the caller's
    fallback is the pre-existing void-and-re-pin, never a grant carried on an unverifiable
    diff."""
    if dry or not repo_root or not ref_a or not ref_b:
        return False
    if ref_a == ref_b:
        return True
    ida = _patch_id_one(repo_root, ref_a, main_branch)
    idb = _patch_id_one(repo_root, ref_b, main_branch)
    return bool(ida) and ida == idb


def _path_allowed(path, allowlist):
    """Path-component-aware allowlist match (tron-13 D1 rider): `meta/` covers meta/**
    but never `metadata/…`; a file entry matches exactly (`README.md` never matches
    `README.md.bak`). Entries are repo-relative; a trailing slash marks a dir."""
    for entry in allowlist or []:
        e = entry.strip()
        if not e:
            continue
        if e.endswith("/"):
            if path.startswith(e) or path + "/" == e:
                return True
        elif path == e:
            return True
    return False


def land_docs(repo_root, branch, allowlist, main_branch="main", dry=False,
              denylist=None, line_scoped=None):
    """The unified paperwork lander (F-1/S-3+R-6, tron-13 D1): the ENGINE lands every
    role's parked paperwork branch on trunk — content-checked, ff-only, then deletes the
    branch (the engine owns the merge, so it owns the cleanup). The engine NEVER rebases:
    a non-ff is the branch owner's to fix (the R-6 rung; the caller nudges, bounded).
    LOCAL-mode primitive: it ff-moves the local trunk. Remote-mode paperwork landing
    (push / PR path) is out of scope — scoped with the 02-04 remote work.

    allowlist / denylist: repo-relative path prefixes (dirs end with /) and exact files —
    the caller builds them per role. Per-file precedence:
      1. a line_scoped entry ({path: token}) decides by content: allowed ONLY if every
         changed (+/-) line contains the token (the engineer's own-block pipeline edit);
      2. an EXACT-file allow entry overrides a denied dir (the engineer's own block doc
         inside the otherwise-denied blocks dir);
      3. a deny match is a violation;
      4. a dir allow match passes;  5. anything else is a violation.

    Returns (code, detail): none | violation | non-ff | landed | error."""
    if dry or not repo_root or not branch or branch == main_branch:
        return "none", "dry/none"
    if not branch_exists(repo_root, branch):
        return "none", f"no branch {branch}"
    rc, out, err = _run(["git", "-C", repo_root, "diff", "--name-only",
                         f"{main_branch}...{branch}"])
    if rc != 0:
        return "error", f"diff unreadable: {err.strip()}"
    files = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not files:
        # Nothing beyond trunk (or already landed): delete the empty branch and be done.
        remove_worktree_for_branch(repo_root, branch, dry)   # D-15-4: worktree gone first
        rc, _, derr = _run(["git", "-C", repo_root, "branch", "-d", branch])
        if rc != 0:
            # W10 rider: a worktree still holding the branch blocks -d — the ref must
            # not vanish from every net; name it (the residue sweep owns worktrees).
            return "landed", f"no changes beyond trunk; ref survives: {derr.strip()}"
        return "landed", "no changes beyond trunk"
    exact_allows = [e for e in (allowlist or []) if not e.strip().endswith("/")]
    offenders = []
    for f in files:
        token = (line_scoped or {}).get(f)
        if token is not None:
            if not _lines_scoped_ok(repo_root, branch, f, token, main_branch):
                offenders.append(f)
            continue
        if _path_allowed(f, exact_allows):
            continue
        if _path_allowed(f, denylist):
            offenders.append(f)
            continue
        if not _path_allowed(f, allowlist):
            offenders.append(f)
    if offenders:
        return "violation", ", ".join(sorted(offenders))
    # T5 (01-15): a missing/unresolvable main_branch already surfaces as "error" above
    # (the name-only diff against it fails the same way); merge_ff_only's own fix covers
    # the remaining case (main_branch resolves but the checkout itself fails).
    okm, err = merge_ff_only(repo_root, branch, main_branch)
    if not okm:
        return "non-ff", err.strip()
    sha = head_sha(repo_root)
    remove_worktree_for_branch(repo_root, branch, dry)       # D-15-4: worktree gone first
    rc, _, derr = _run(["git", "-C", repo_root, "branch", "-d", branch])
    note = f"; ref survives: {derr.strip()}" if rc != 0 else ""
    return "landed", f"{len(files)} file(s) @ {sha[:7]}{note}"


def _lines_scoped_ok(repo_root, branch, path, token, main_branch="main"):
    """True iff every changed (+/-) line of `path` on the branch contains `token` —
    the engineer touches only pipeline lines naming its OWN block; the pipeline's
    shape stays the architect's."""
    rc, out, _ = _run(["git", "-C", repo_root, "diff", "--unified=0",
                       f"{main_branch}...{branch}", "--", path])
    if rc != 0:
        return False
    for ln in out.splitlines():
        if ln.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if ln.startswith(("+", "-")) and token not in ln:
            return False
    return True


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


def list_worktrees(repo_root, dry=False):
    """All secondary worktrees: [(path, branch)] excluding the root checkout itself.
    D1 residue sweep: at session end every worker is gone, so ANY remaining worktree
    is residue to name (a worktree also blocks the lander's branch cleanup — `git
    branch -d` refuses a checked-out branch, leaving an orphan ref)."""
    if dry or not repo_root:
        return []
    rc, out, _ = _run(["git", "-C", repo_root, "worktree", "list", "--porcelain"])
    if rc != 0:
        return []
    trees, cur = [], {}
    for ln in out.splitlines() + [""]:
        if ln.startswith("worktree "):
            cur = {"path": ln.split(" ", 1)[1]}
        elif ln.startswith("branch "):
            cur["branch"] = ln.split(" ", 1)[1].replace("refs/heads/", "")
        elif not ln and cur:
            trees.append(cur)
            cur = {}
    # 01-13 (tron-14 F11): git lists the MAIN worktree first, always — skip it by
    # position as well as by path. Path aliasing (symlinks the realpath can't see
    # through, bind mounts, a repo_root recorded differently than git reports it)
    # once let the replica root itself read as "leftover worktree ... (on main)".
    root_real = os.path.realpath(repo_root)
    return [(t.get("path"), t.get("branch")) for i, t in enumerate(trees)
            if i > 0 and os.path.realpath(t.get("path", "")) != root_real]


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
