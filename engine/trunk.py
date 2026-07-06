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
    rrc, _, rebase_err = _run(["git", "-C", repo_root, "rebase", main_branch, branch])
    if rrc != 0:
        _run(["git", "-C", repo_root, "rebase", "--abort"])
        _run(["git", "-C", repo_root, "checkout", main_branch])
        # R1b (01-19, impl-review I-3): the RETURNED detail is CHANGED here — the original
        # ff error is preserved verbatim as the prefix, with the rebase-retry's own failure
        # reason appended (200-char capped). Without it a worktree-refused rebase (git
        # refuses to rebase a branch another worktree holds — the tron-26 standoff's silent
        # half) is indistinguishable from a genuine conflict; both fell through to the
        # identical original ff error. Readers of this return, all intended: the DONE
        # gate's non-ff flow line (fsm._drive_gate), AND — a deliberate surface change,
        # adjudged useful by the impl review — land_docs / land_ordered_merge propagate it
        # into operator/worker-facing failure text (the landing nudge, paperwork-wall case
        # details): exactly the surfaces that were starved of the refusal-vs-conflict
        # distinction.
        return False, (f"{non_ff_detail} (rebase-retry: {rebase_err.strip()[:200]})"
                       if rebase_err.strip() else non_ff_detail)
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


def is_descendant(repo_root, sha, ancestor_sha, dry=False):
    """T2 (01-20): True iff `sha` is a STRICT descendant of `ancestor_sha` (the ancestor is
    reachable from it, and the two differ) — rev-parse ancestry only, never prose. Used by
    the record-stage re-merge predicate to confirm a worker's branch grew FORWARD past an
    already-landed tip (a required fix parked post-pin) — a divergent/rewritten history is
    the ratchet's own contradiction arm's job, not this one. False on any unresolvable ref
    or git failure (fail-closed: never re-drive on an unverifiable ancestry)."""
    if dry or not repo_root or not sha or not ancestor_sha or sha == ancestor_sha:
        return False
    rc, _, _ = _run(["git", "-C", repo_root, "merge-base", "--is-ancestor", ancestor_sha, sha])
    return rc == 0


def delta_has_code(repo_root, base, tip, allowlist, dry=False, denylist=None, line_scoped=None):
    """T2 (01-20): the code-vs-paperwork discriminator `land_docs` already uses, applied to
    an arbitrary base..tip delta instead of a paperwork-lander branch — a path outside the
    paperwork allowlist (or inside the denylist, with the exact-file-allow override) is a
    code-lane path; a line_scoped path (a declared paperwork-scoped exception) is never
    code. '' base/tip, no changed files, or a git failure -> False (fail-closed: never
    re-drive on an unverifiable or empty delta)."""
    if dry or not repo_root or not base or not tip or base == tip:
        return False
    rc, out, _ = _run(["git", "-C", repo_root, "diff", "--name-only", f"{base}..{tip}"])
    if rc != 0:
        return False
    files = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not files:
        return False
    exact_allows = [e for e in (allowlist or []) if not e.strip().endswith("/")]
    for f in files:
        if (line_scoped or {}).get(f) is not None:
            continue
        if _path_allowed(f, exact_allows):
            continue
        if _path_allowed(f, denylist):
            return True
        if not _path_allowed(f, allowlist):
            return True
    return False


def branch_touches_path(repo_root, branch, path, main_branch="main", dry=False):
    """T1 (01-20): does `branch`'s diff against `main_branch` touch `path` (a block file's
    repo-relative path)? Git-only correlation used to tie an architect's landed paperwork
    branch to its live forward/reconcile job — never prose, and read BEFORE the landing
    deletes the branch. False on '' inputs or any git failure (fail-closed: no correlation
    without positive evidence)."""
    if dry or not repo_root or not branch or not path:
        return False
    rc, out, _ = _run(["git", "-C", repo_root, "diff", "--name-only",
                       f"{main_branch}...{branch}"])
    if rc != 0:
        return False
    files = {ln.strip() for ln in out.splitlines() if ln.strip()}
    return path in files


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


def block_invariant_ok(repo_root, branch, merged_sha, main_branch="main", dry=False):
    """T1 (01-25, R-03a): the block invariant, checked ONCE at record->close — every
    code-bearing commit attributable to this block is an ancestor of trunk, ref-agnostically.
    Unlike the mid-gate anchors above (`is_ancestor`, best-effort, empty-sha reads as a quiet
    pass), this is the LAST gate and fails CLOSED: an anchor that no longer resolves (a
    deleted/unregistered ref, seam 5) is NOT a free pass, and no anchor at all resolving is
    itself a failure — there is nothing left to verify the block ever landed. Checks every
    anchor that DOES resolve (the live branch tip, if the branch still exists, AND the
    tracked merged_sha, if set) — a stray commit parked on the branch after the last accepted
    merge fails via the branch-tip arm even when merged_sha alone would still read clean.
    Returns (ok, detail)."""
    if dry or not repo_root:
        return True, "dry/none"
    branch_tip = tip_sha(repo_root, branch, dry) if branch else ""
    checked = False
    if branch_tip:
        checked = True
        if not is_ancestor(repo_root, branch_tip, main_branch, dry):
            return False, f"branch {branch} tip {branch_tip[:7]} is not on trunk"
    if merged_sha:
        checked = True
        if not is_ancestor(repo_root, merged_sha, main_branch, dry):
            return False, f"merged sha {str(merged_sha)[:7]} is not on trunk"
    if not checked:
        return False, "no resolvable anchor (branch gone, no tracked merge) — cannot verify the block landed"
    return True, ""


def merge_base(repo_root, ref_a, ref_b, dry=False):
    """`git merge-base ref_a ref_b`, or '' on any unresolvable ref / git failure. Best-effort,
    like every other read here — callers must treat '' as "unknown", never a free pass."""
    if dry or not repo_root or not ref_a or not ref_b:
        return ""
    rc, out, _ = _run(["git", "-C", repo_root, "merge-base", ref_a, ref_b])
    return out.strip() if rc == 0 else ""


def run_block_tests(repo_root, base, merged_sha, dry=False):
    """T2 (01-25, R-03b) + review fix (F-3 reopened): the engine's OWN observed signal at the
    trunk-stage trust point — the worker's report is a claim, this runs it. Discovers the
    block's own test files over the FULL `base..merged_sha` range, never merged_sha's own
    single-commit diff alone: under `merge_ff_only` a multi-commit branch lands as a literal
    fast-forward, so merged_sha's OWN diff (`git show` against its immediate parent) is only
    its LAST commit — an earlier commit in the same landed range that added the block's real
    feature + test file went unseen, and a trivially-green trailing commit's own diff made the
    signal flip GREEN having never run the feature's test (the exact F-3 shape this block
    exists to close). `base` must be captured by the CALLER at merge time (trunk before the
    ff) — recomputing `merge-base(main, branch)` here, after the fact, cannot recover it: a
    fast-forward collapses branch and trunk onto the identical commit, so that merge-base
    would just return merged_sha back (a self-ancestor), the same one-commit blind spot this
    fixes.

    Reviewer fix (F-3 relocated, AC-5): base=='' or base==merged_sha means the range is
    UNKNOWN, not narrow — on the out-of-band arms (self_merge, out-of-gate branch_merged,
    remote-PR-merged) the caller's own best-effort `merge_base(main, branch)` collapses to
    merged_sha (or fails to resolve) exactly when that external merge was itself a bare
    fast-forward. Falling back to merged_sha's single-commit diff there silently re-opens the
    same blind spot this function exists to close: an unrelated already-green trailing commit
    reads as the whole block's signal while the real (possibly broken) test never runs. There
    is no pre-image to reconstruct here — the out-of-band arms genuinely cannot recover it —
    so this fails CLOSED instead: NOT-OK, holding the gate at trunk (the existing
    repeat-report escalation backstop handles a persistent hold), mirroring AC-5's "absent
    signal never flips passed." The PRIMARY engine ff arm is unaffected: its base is a real
    pre-merge sha (trunk's HEAD read before the ff), never equal to merged_sha for a landed
    block, and a genuine 1-commit block still has base == the parent commit, not merged_sha.

    Executes each discovered test file directly — never the worker's worktree, never a
    say-so. No test file found in the range is a FAIL, same as a failing run: a validated
    block always ran something observable. Returns (ok, detail)."""
    if dry:
        return True, "dry"
    if not repo_root or not merged_sha:
        return False, "no merged sha to validate"
    if not base or base == merged_sha:
        return False, ("validation range unresolved (base collapsed) — cannot verify tests ran "
                        f"({str(merged_sha)[:7]})")
    rc, out, _ = _run(["git", "-C", repo_root, "diff", "--name-only", f"{base}..{merged_sha}"])
    span = f"{str(base)[:7]}..{str(merged_sha)[:7]}"
    if rc != 0:
        return False, f"{span}: diff unreadable"
    tests = sorted({f.strip() for f in out.splitlines() if f.strip().endswith("_test.py")})
    if not tests:
        return False, f"no test file in the merged range ({span})"
    for f in tests:
        path = os.path.join(repo_root, f)
        if not os.path.exists(path):
            return False, f"{f}: missing on trunk"
        rc, _, err = _run(["python3", path], cwd=repo_root, timeout=120)
        if rc != 0:
            return False, f"{f}: failed ({err.strip()[:150]})"
    return True, f"{len(tests)} test file(s) green ({span})"


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
