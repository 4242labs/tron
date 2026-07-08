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

T2 (01-32, ADR-0002 D1): this module IS the single git wrapper — every engine git
invocation, engine-wide, funnels through `_run` below (grepped clean: no other engine
file shells out to `git`). `_run` now keeps an in-process AUDIT TRAIL of every
invocation (argv, at minimum) so a test can assert the write-boundary directly
(AC-1's "wrapper audit", AC-9/P3 evidence) — `audit_log()`/`reset_audit()`. Sealing the
subcommand ALLOWLIST itself (reads + fetch + scratch-scoped `worktree add
--detach|remove`, nothing else) is 01-32 T3's job (deleting the remaining mutation
arms); this wrapper is the seam T3 seals.

Root checkout / truth ref (ADR-0002 D1): local no-remote mode keeps the root checkout
DETACHED at seat (never on `<main>`) — the branch ref advances by `update-ref` CAS
alone (`merge_ff_only`, below), never a checkout, so a bare `git rev-parse HEAD` no
longer tracks trunk's position. Every read that used to key off `HEAD` or a literal
branch NAME now keys off the mode's TRUTH REF (`truth_sha`, `root_head_detached`) —
remote mode: `refs/remotes/origin/<main>` post-fetch; local mode: `refs/heads/<main>`
in place. `refresh()`'s old local ff-ADVANCE (a working-tree write) is deleted outright
— every read is committed-tree-keyed (git archive / rev-parse), never dependent on
what the working tree happens to hold.
"""
import os
import json
import shutil
import subprocess
import tarfile
import tempfile

_TIMEOUT = 20
_TEST_TIMEOUT = 300     # T2 (01-28): a real declared suite gets real headroom, unlike plumbing calls

# ── the wrapper's audit trail (T2, 01-32): every git invocation this module ever makes,
# in order — module-level so a test can assert the write-boundary against the WHOLE
# session, not just one call's return value. Never touched by engine logic itself, only
# by _run (append) and the two test-facing accessors below (read/reset). ──
_AUDIT = []


def audit_log():
    """A COPY of every git invocation recorded so far — [(argv, rc), ...]. Read-only:
    mutate the return value all you like, the live trail is untouched."""
    return list(_AUDIT)


def reset_audit():
    """Test-only: clear the trail (each test fixture starts from a clean slate)."""
    _AUDIT.clear()


def _run(args, cwd=None, timeout=_TIMEOUT):
    """THE wrapper (T2, 01-32, ADR-0002 D1): every engine git call is a `git` argv through
    HERE — the single seam the write-boundary audit reads. Records the invocation before
    returning (success or failure alike — a refused/failed call is still evidence of what
    was ATTEMPTED, never dropped from the trail)."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        _AUDIT.append((list(args), r.returncode))
        return r.returncode, r.stdout, r.stderr
    except (subprocess.SubprocessError, OSError) as e:
        _AUDIT.append((list(args), 1))
        return 1, "", str(e)


def refresh(repo_root, main_branch="main", dry=False, remote=None):
    """Bring the trunk READ up to date. Best-effort: never raises, never blocks the loop.
    Returns (ok, detail). On failure the caller reuses the last snapshot (the files
    already on disk).

    Local / no-remote mode: when the project declares no remote (`repo.remote` absent or
    `none`), the root IS the authority — there is nothing to fetch, so we read the local
    `<main>` ref in place instead of treating the missing remote as a boot-fatal fetch
    failure.

    T2 (01-32, ADR-0002 D1): the remote-mode local FF-ADVANCE this used to perform
    (`git merge --ff-only origin/<main>` against the checked-out root) is DELETED, not
    patched — it was a working-tree WRITE the engine had no business making (P3), and it
    is no longer needed: `fetch` alone deposits `refs/remotes/origin/<main>`, and every
    read keys to THAT truth ref directly (`truth_sha`, ancestry, snapshot source) rather
    than to a local branch this function used to keep in sync. The root's own checkout
    state (attached/detached, whatever branch it happens to be on) is now irrelevant to
    what the engine reads — fetch is the only write left here, exactly one of the two
    named exceptions to the write boundary."""
    if dry or not repo_root:
        return True, "dry/none — read in place"
    if not remote or remote == "none":
        return True, "no remote — read in place"
    rc, _, err = _run(["git", "-C", repo_root, "fetch", "origin", main_branch])
    if rc != 0:
        return False, f"fetch failed: {err.strip()[:120]}"
    return True, "fetched — reads key to origin/<main> (no local ff-advance, ADR-0002 D1)"


def head_sha(repo_root, dry=False):
    """The trunk checkout's literal `HEAD` sha (short). RETAINED for callers that
    genuinely want the working tree's own position (there are none left in the engine —
    grepped clean); every trunk-position read the engine itself performs now goes through
    `truth_sha` instead (below), since a detached local-mode root's HEAD no longer moves
    when the branch ref advances by `update-ref` CAS alone. Best-effort: '' if unknown."""
    if dry or not repo_root:
        return "dry" if dry else ""
    rc, out, _ = _run(["git", "-C", repo_root, "rev-parse", "--short", "HEAD"])
    return out.strip() if rc == 0 else ""


def truth_sha(repo_root, ref, dry=False):
    """T2 (01-32, ADR-0002 D1): the mode's TRUTH REF's current sha (short) — the
    snapshot-sha source every per-tick read pins to. Callers resolve `ref` themselves
    (remote mode: `origin/<main>` post-fetch; local mode: `<main>` in place) — this is a
    plain, mode-agnostic `rev-parse`, never `HEAD` (a detached or stale-attached root's
    HEAD tracks nothing once the branch advances by ref alone). '' on any unresolvable
    ref (never blocks the loop)."""
    if dry or not repo_root or not ref:
        return "dry" if dry else ""
    rc, out, _ = _run(["git", "-C", repo_root, "rev-parse", "--short", ref])
    return out.strip() if rc == 0 else ""


def root_head_detached(repo_root, dry=False):
    """T2 (01-32, ADR-0002 D1 detection arm): True iff the root checkout's HEAD is
    DETACHED (not on any branch) — `git symbolic-ref -q HEAD` fails exactly when
    detached. Local no-remote mode requires this permanently true (the root never sits
    on `<main>`, so the branch ref is free to advance by `update-ref` CAS with no
    working-tree race); a worker re-attaching it (`git checkout <main>` there) is the
    violation this verifies every tick, real-git, never inferred. dry / no repo_root ->
    True (nothing to violate; consistent with every other best-effort read here — a
    caller gating on this must still condition on being in local mode first, since
    remote-mode roots are never required to detach at all)."""
    if dry or not repo_root:
        return True
    rc, _, _ = _run(["git", "-C", repo_root, "symbolic-ref", "-q", "HEAD"])
    return rc != 0


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


def _delete_landed_branch(repo_root, branch, main_branch, dry=False):
    """T2 (01-32, ADR-0002 D1): every post-land branch cleanup used to be a plain
    `git branch -d <branch>` — safe because the OLD checkout-based `merge_ff_only` left
    HEAD sitting exactly on the new tip, so git's own "-d refuses an unmerged branch"
    check (which compares against HEAD) always passed for a branch that had in fact just
    landed. Now that the root stays detached/frozen (no checkout, ever), HEAD no longer
    reflects the advance — `-d`'s HEAD-relative check would misfire "not fully merged"
    on a branch that unquestionably IS on trunk. Never blind-force: verify ancestry
    against the TRUNK ref ourselves (the same `is_ancestor` predicate the whole ratchet
    already trusts) and only then use `-D` (force) — a branch we've just independently
    proven is fully contained in trunk can't lose anything by deleting its name. Anything
    that DOESN'T verify falls back to the safe `-d` (git's own refusal names the reason).
    Returns (rc, err)."""
    tip = tip_sha(repo_root, branch, dry)
    verb = "-D" if tip and is_ancestor(repo_root, tip, main_branch, dry) else "-d"
    rc, _, err = _run(["git", "-C", repo_root, "branch", verb, branch])
    return rc, err


def merge_ff_only(repo_root, branch, main_branch="main", dry=False, require_detached=False):
    """Fast-forward trunk to an already-validated block branch — the local/no-remote merge.
    The engine owns the trunk merge transitionally (ADR-0002 D1/D2, 01-32 T1/T2), but ONLY
    as a fast-forward — never a merge commit, never a force, never a rebase (01-32 T1: the
    01-17 rebase-retry arm is retired — see the block-01-32 spec/history for that story;
    every non-ff refusal is the WORKER's rebase to perform, engine-observed, never
    engine-substituted).

    T2 (01-32, ADR-0002 D1): this NO LONGER checks out the root. The prior implementation
    `git checkout`'d the root onto `main_branch` before merging — exactly the hazard
    ADR-0002 Decision 1 names ("today's merge_ff_only re-attaches the root at
    trunk.py:227"), and the thing that made keeping the root permanently detached (Decision
    1's local-mode fix) impossible. The advance is now a pure ref move: read the branch's
    own current tip as the CAS's expected old value, verify a real fast-forward
    (`is_ancestor`), then `git update-ref refs/heads/<main> <new> <old>` — compare-and-swap,
    atomic, and it never touches the working tree at all. A concurrent advance (another
    landing racing this one) makes the CAS fail loudly (a non-ff-shaped error), which the
    caller already routes to the worker's rebase-retry (AC-5).

    `require_detached` (ADR-0002 D1 structural backstop, AC-6): local-mode callers pass
    True — `update-ref` against a checked-out ref corrupts tree/index consistency (the
    ADR's own stated hazard), so this refuses outright if the root is currently attached to
    a branch, structurally enforcing "landing holds until detachment is restored"
    independent of whatever the engine's own per-tick observation/case state happens to be.
    Remote-mode callers pass False (or omit it) — a remote-mode root is never required to
    detach at all (Decision 1 scopes the detached-root cost to local no-remote mode only),
    so this stays a no-op there, same as before 01-32.

    T5 (01-15, tron-16 boot-1 residue): verifies `main_branch` itself exists BEFORE acting —
    a missing trunk branch (an env fault) is an `error`-shaped (ok=False) return, never a
    silent merge onto the wrong ref. Returns (ok, err)."""
    if dry or not repo_root or not branch:
        return (dry, "")
    if not branch_exists(repo_root, main_branch, dry):
        return False, f"trunk branch '{main_branch}' does not exist"
    if require_detached and not root_head_detached(repo_root, dry):
        return False, ("root is attached to a branch — write-boundary violation "
                       "(ADR-0002 D1: the local-mode root must stay detached); "
                       "refusing to advance trunk until detachment is restored")
    old = tip_sha(repo_root, main_branch, dry)
    if not old:
        return False, f"trunk branch '{main_branch}' has no resolvable tip"
    new = tip_sha(repo_root, branch, dry)
    if not new:
        return False, f"branch '{branch}' has no resolvable tip"
    if old == new:
        return True, "already at tip"
    if not is_ancestor(repo_root, old, branch, dry):
        return False, "not a fast-forward"
    rc, _, err = _run(["git", "-C", repo_root, "update-ref",
                       f"refs/heads/{main_branch}", new, old])
    if rc != 0:
        return False, f"update-ref CAS failed (concurrent advance?): {err.strip()[:200]}"
    return True, f"ff {old[:7]}..{new[:7]} via update-ref CAS"


def land_ordered_merge(repo_root, branch, main_branch="main", dry=False, require_detached=False):
    """T6 (01-15): the violation-wall `approve` settle's landing primitive — an EXPLICIT
    operator-ordered merge of the WHOLE named branch (no paperwork allowlist: the operator
    already saw and approved the range naming it a landable fix, tron-16 CASE-003's residue
    — post-close code with no landing path otherwise). Same ff-only discipline as every
    other merge here, then the SAME lander cleanup `land_docs` runs on success (worktree
    gone first, D-15-4, then the branch ref) — one physical landing mechanism, reused, never
    a second one. `require_detached` forwards to `merge_ff_only` (01-32 T2, ADR-0002 D1 —
    the caller passes True in local mode only). Returns (ok, detail)."""
    if dry or not repo_root or not branch or branch == main_branch:
        return False, "dry/none"
    if not branch_exists(repo_root, branch, dry):
        return False, f"no branch {branch}"
    okm, err = merge_ff_only(repo_root, branch, main_branch, dry, require_detached=require_detached)
    if not okm:
        return False, err.strip()
    sha = tip_sha(repo_root, main_branch, dry)   # T2 (01-32): the ref, never HEAD (detached root)
    remove_worktree_for_branch(repo_root, branch, dry)       # D-15-4: worktree gone first
    rc, derr = _delete_landed_branch(repo_root, branch, main_branch, dry)
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
              denylist=None, line_scoped=None, require_detached=False):
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
        rc, derr = _delete_landed_branch(repo_root, branch, main_branch, dry)
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
    okm, err = merge_ff_only(repo_root, branch, main_branch, dry, require_detached=require_detached)
    if not okm:
        return "non-ff", err.strip()
    sha = tip_sha(repo_root, main_branch, dry)   # T2 (01-32): the ref, never HEAD (detached root)
    remove_worktree_for_branch(repo_root, branch, dry)       # D-15-4: worktree gone first
    rc, derr = _delete_landed_branch(repo_root, branch, main_branch, dry)
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


def validate_trunk(repo_root, merged_sha, test_command, test_env=None,
                    ci_check_name=None, dry=False, scratch_root=None):
    """Block 01-28 (T1-T4): the trunk-stage TRUSTED-VERDICT model, replacing the old
    post-merge test RE-RUN seam (`run_block_tests`, retired — F-3/wave-1's false-wall
    source: it computed an empty `base..merged_sha` range on a fast-forward landing,
    base==merged_sha, and only ever discovered `*_test.py`, so any non-Python project
    could never validate). Per ADR §A (post-wave-1 enhancements): trust the RUNNER, not
    the worker; a worker's own run is dev feedback only, never a gate.

    Returns (status, detail) with status one of:
      "pass"        — a genuinely observed green signal (CI's, or the engine's own run).
      "fail"        — a genuinely observed RED signal — holds the gate, no routing (T3:
                      a real failure is not the same thing as "can't confirm").
      "unconfirmed" — nothing trustworthy could be read at all (no merged sha, no
                      test.command declared, an unresolvable/uncheckoutable commit, a
                      launch failure, a timeout, or — CI mode — no commit-exact/completed/
                      correctly-named check-run). T3: HOLDS and routes to the architect
                      first, never a wall/failure page, never a false pass either.

    No `base`/range of any kind is used anywhere in this function — T1's fix for the
    ff-collapse defect is structural, not a patched recompute: the old design needed a
    pre-image to diff over merely to DISCOVER which files were tests; this design runs
    the ONE declared command against the merged commit's full tree, so there is no range
    left to collapse. (The dead `g["merge_base"]` bookkeeping this fed — including the
    post-hoc `merge_base(main, branch)` recompute that returned the merged sha itself on
    an out-of-band fast-forward, fsm.py's old branch_merged/self_merge arms — is removed
    at the call site, not patched.)

    Mode selection: `ci_check_name` present -> read CI's verdict for `merged_sha`
    (T4), no engine re-run. Otherwise -> run `test_command` once, in a clean checkout
    (T2). Neither `test_command` nor `ci_check_name` declared -> unconfirmed (never a
    silent free pass, never a wall).

    `scratch_root` (01-32 T2, ADR-0002 D1): where the clean validation checkout is
    carved — Decision 1 names these "the engine's validation checkouts (for the
    retained declared-command trunk verdict)" as the scratch-worktree-admin exception,
    scoped to `meta/agents/tron/scratch/`. The caller (fsm.py) passes `ctx.scratch_dir`;
    None falls back to the system tempdir (pre-01-32 behavior — never a hard
    requirement, since a project that hasn't seated the scratch convention must still
    validate)."""
    if dry:
        return "pass", "dry"
    if not repo_root or not merged_sha:
        return "unconfirmed", "no merged sha to validate — cannot confirm"
    if ci_check_name:
        return ci_verdict(repo_root, merged_sha, ci_check_name, dry)
    if not test_command:
        return ("unconfirmed", "no test.command declared (project.yaml `test:`) — "
                "cannot confirm what to validate")
    return _run_declared_command(repo_root, merged_sha, test_command, test_env, scratch_root)


def _run_declared_command(repo_root, sha, command, env=None, scratch_root=None):
    """T2: the single authoritative run — `command` executed ONCE, in a clean, detached
    `git worktree` at `sha` that the worker never controls (never the worker's own
    worktree, never a say-so). `env` (project.yaml `test.env`, a flat {str: str} dict) is
    LAYERED onto the clean checkout's inherited shell environment, never replacing it —
    the representation this block settled on over a schema-only field: the command still
    needs the ordinary shell/PATH/HOME to run at all, `test.env` only overrides specific
    keys on top (e.g. NODE_ENV). Any failure to even materialize/launch the check (bad
    sha, worktree add failure, launch OSError, timeout) is UNCONFIRMED, never a red — an
    engine/environment fault must never wear the block's clothes as a genuine test
    failure. Only a real, completed, non-zero exit is "fail". Returns (status, detail)."""
    rc, _, _ = _run(["git", "-C", repo_root, "cat-file", "-e", str(sha)])
    if rc != 0:
        return "unconfirmed", f"{str(sha)[:7]}: unresolvable in this checkout — cannot confirm"
    if scratch_root:
        os.makedirs(scratch_root, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="tron-trunkval-", dir=scratch_root or None)
    try:
        rc, _, err = _run(["git", "-C", repo_root, "worktree", "add", "--detach", "-q",
                           tmp, str(sha)], timeout=60)
        if rc != 0:
            return "unconfirmed", f"clean checkout of {str(sha)[:7]} failed: {err.strip()[:200]}"
        run_env = os.environ.copy()
        run_env.update({str(k): str(v) for k, v in (env or {}).items()})
        try:
            r = subprocess.run(command, shell=True, cwd=tmp, env=run_env,
                               capture_output=True, text=True, timeout=_TEST_TIMEOUT)
        except subprocess.TimeoutExpired:
            return ("unconfirmed",
                    f"test.command timed out after {_TEST_TIMEOUT}s @ {str(sha)[:7]} — cannot confirm")
        except OSError as e:
            return "unconfirmed", f"test.command failed to launch: {type(e).__name__}: {e}"
        if r.returncode == 0:
            return "pass", f"test.command green @ {str(sha)[:7]}"
        tail = (r.stderr or r.stdout or "").strip()[-300:]
        return "fail", f"test.command exit {r.returncode} @ {str(sha)[:7]}: {tail}"
    finally:
        # Always tear down — never leave the trust-point's own checkout as residue for the
        # session-end worktree sweep (trunk.list_worktrees) to have to name.
        _run(["git", "-C", repo_root, "worktree", "remove", "--force", tmp], timeout=30)
        shutil.rmtree(tmp, ignore_errors=True)


def ci_check_runs(repo_root, sha, dry=False):
    """Best-effort raw read of every GH check-run recorded against `sha` (any commit, not
    just a PR head — this is the POST-merge trunk commit, no open PR to key off). `[]` on
    any failure (gh absent, no network, bad json) or dry — never raises, and callers must
    treat `[]` as unknown, never a free pass. Each item carries at least `name`,
    `head_sha`, `status`, `conclusion` (GH's own check-runs shape)."""
    if dry or not repo_root or not sha:
        return []
    rc, out, _ = _run(["gh", "api", f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs",
                       "--jq", ".check_runs"], cwd=repo_root, timeout=30)
    if rc != 0 or not out.strip():
        return []
    try:
        runs = json.loads(out)
    except json.JSONDecodeError:
        return []
    return runs if isinstance(runs, list) else []


def ci_verdict(repo_root, merged_sha, check_name, dry=False):
    """T4: read CI's verdict for `merged_sha` — never re-run. Trusted ONLY when ALL three
    hold, exactly per the ADR's open decision (commit-exact / non-stale / real declared
    suite), otherwise unconfirmed (never a free pass on an absent/ambiguous read, never a
    false wall on a still-running check):
      commit-exact  — the check-run's own `head_sha` equals `merged_sha` exactly; a run
                      bound to an ancestor/descendant/PR-head commit is never substituted.
      non-stale     — `status == "completed"`; pending/queued/in_progress never trusted.
      real suite    — `name == check_name` (project.yaml `ci.check_name`, the ONE
                      declared identifier for the job that runs `test.command`) — never a
                      bare rollup guess off an unrelated check that happens to be green.
    Returns (status, detail)."""
    if dry:
        return "pass", "dry"
    if not repo_root or not merged_sha:
        return "unconfirmed", "no merged sha to read a CI verdict for — cannot confirm"
    if not check_name:
        return ("unconfirmed", "no ci.check_name declared (project.yaml `ci:`) — cannot confirm "
                "which check-run is the real declared suite")
    runs = ci_check_runs(repo_root, merged_sha, dry)
    matches = [r for r in runs
              if r.get("name") == check_name and r.get("head_sha") == merged_sha]
    if not matches:
        return ("unconfirmed", f"no '{check_name}' check-run found commit-exact to "
                f"{str(merged_sha)[:7]} — cannot confirm")
    run = matches[0]
    if run.get("status") != "completed":
        return ("unconfirmed", f"'{check_name}' @ {str(merged_sha)[:7]} not completed yet "
                f"({run.get('status')}) — cannot confirm")
    conclusion = run.get("conclusion")
    if conclusion == "success":
        return "pass", f"'{check_name}' green @ {str(merged_sha)[:7]} (CI-trusted, no engine re-run)"
    return "fail", f"'{check_name}' @ {str(merged_sha)[:7]} concluded {conclusion}"


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
