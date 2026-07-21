#!/usr/bin/env python3
"""tron-reborn — the truth gate.

A DONE claim is never taken on the agent's word: the engine checks the
repository itself. Gate: the claimed branch exists and carries commits
main does not, the trunk (main) is EXACTLY where the engine recorded it
at assign time — the trunk is read-only to agents — and the engine runs
the block's declared test command itself. The MERGE is the worker's:
after approval it brings the trunk into its branch and resolves conflicts
in its arena; the engine verifies contains_trunk() (so a landing cannot
conflict) and then performs the mechanical ref advance, merge_to_main() —
an arena physically cannot move main, which stays checked out in the
primary copy.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def trunk_sha(repo):
    return git(repo, "rev-parse", "main").stdout.strip()


def _cmd_line(block_text, key):
    for line in block_text.splitlines():
        if line.strip().lower().startswith(key):
            return line.split(":", 1)[1].strip()
    return None


def test_cmd(block_text):
    """The block's declared test command: a 'test: <cmd>' line, or None."""
    return _cmd_line(block_text, "test:")


def trunk_test_cmd(block_text):
    """The block's trunk-only validation: a 'trunk-test: <cmd>' line, or
    None. Some validations can only pass on the landed trunk — the engine
    runs this ON the trunk at the block's FINAL landing, after the suite,
    before the done stamp."""
    return _cmd_line(block_text, "trunk-test:")


def run_tests(cwd, cmd, timeout=300):
    """(ok, output tail) — the engine runs the block's tests in the arena."""
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"test command timed out after {timeout}s: {cmd}"
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode == 0, "\n".join(out.splitlines()[-15:])


def verify_done(repo, branch, trunk=None, base="main"):
    """(ok, evidence) — branch exists with commits beyond base; trunk untouched."""
    if trunk:
        now = trunk_sha(repo)
        if now != trunk:
            return False, (f"trunk violation: main moved from {trunk[:12]} to "
                           f"{now[:12]} — the trunk is read-only; restore main "
                           f"to {trunk[:12]} and keep ALL work on {branch}")
    if git(repo, "rev-parse", "--verify", "--quiet", branch).returncode != 0:
        return False, f"branch '{branch}' does not exist in the repository"
    r = git(repo, "rev-list", "--count", f"{base}..{branch}")
    n = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
    if n == 0:
        return False, f"branch '{branch}' has no commits beyond {base}"
    log = git(repo, "log", "--oneline", f"{base}..{branch}").stdout.strip()
    return True, f"{n} commit(s) on {branch} beyond {base}:\n{log}"


def add_arena(repo, branch, arena):
    """(ok, evidence) — engine-owned isolated worktree on a NEW branch off main.

    One arena per block: agents can never collide in a shared working tree,
    and main stays checked out in the primary copy — git itself then refuses
    any second checkout of the trunk.
    """
    r = git(repo, "worktree", "add", "-b", branch, str(arena), "main")
    if r.returncode != 0:
        return False, ((r.stdout or "") + (r.stderr or "")).strip()[-300:]
    return True, str(arena)


def remove_arena(repo, arena):
    """The path is GONE afterwards, whoever owned it: `git worktree
    remove` retires the engine's own live worktrees; a residue a dead
    engine left — often a worktree of an EARLIER project this repo never
    knew — is deleted outright. A leftover arena on the exact path a
    fresh `git worktree add` needs poisoned the next run twice (260717)."""
    git(repo, "worktree", "remove", "--force", str(arena))
    if Path(arena).exists():
        shutil.rmtree(arena, ignore_errors=True)
    git(repo, "worktree", "prune")


def judge_copy(repo, sha, dest):
    """(ok, evidence) — an independent DETACHED checkout for a judge.

    A verdict seat reads the delivered state in its OWN working copy,
    pinned to the exact delivered commit: the worker cannot move it
    mid-review, and nothing a judge does there can reach the delivery —
    every (re)sync is forced back to the attested sha and scrubbed.
    """
    import os
    if os.path.isdir(str(dest)):
        r = git(dest, "checkout", "--force", "--detach", sha)
        git(dest, "clean", "-fdq")
    else:
        r = git(repo, "worktree", "add", "--detach", str(dest), sha)
    if r.returncode != 0:
        return False, ((r.stdout or "") + (r.stderr or "")).strip()[-300:]
    return True, str(dest)


def orphan_branch(repo, branch):
    """Preserve an unverified branch as orphan/<branch>; latest crash wins.

    Crash recovery: work on a mid-flight branch is testimony the gate never
    verified — not trusted, but not destroyed either. Returns the new name,
    or None if the branch does not exist.
    """
    if git(repo, "rev-parse", "--verify", "--quiet", branch).returncode != 0:
        return None
    git(repo, "checkout", "-q", "main")
    git(repo, "branch", "-M", branch, f"orphan/{branch}")
    return f"orphan/{branch}"


def contains_trunk(repo, branch, base="main"):
    """True when branch already contains base — its landing cannot conflict."""
    return git(repo, "merge-base", "--is-ancestor",
               base, branch).returncode == 0


def merge_to_main(repo, branch):
    """(ok, evidence) — the ENGINE lands a delivered branch on main.

    --no-ff: every landing is one merge commit. A conflict aborts cleanly —
    main is never left mid-merge — and comes back as evidence.
    """
    git(repo, "checkout", "-q", "main")
    r = git(repo, "merge", "--no-ff", "-q", "-m", f"land: {branch}", branch)
    if r.returncode != 0:
        git(repo, "merge", "--abort")
        return False, ((r.stdout or "") + (r.stderr or "")).strip()[-500:]
    return True, trunk_sha(repo)


# -------------------------------------------------------------- selftest
def selftest():
    import tempfile
    repo = tempfile.mkdtemp(prefix="gate-selftest-")
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "gate@selftest")
    git(repo, "config", "user.name", "gate")
    (open(f"{repo}/f", "w")).write("base")
    git(repo, "add", "."); git(repo, "commit", "-m", "base")
    ok = [
        verify_done(repo, "feat/x")[0] is False,        # branch missing
        "does not exist" in verify_done(repo, "feat/x")[1],
    ]
    git(repo, "branch", "feat/x")                        # exists, 0 ahead
    ok += [
        verify_done(repo, "feat/x")[0] is False,
        "no commits beyond main" in verify_done(repo, "feat/x")[1],
    ]
    git(repo, "checkout", "-q", "feat/x")
    open(f"{repo}/g", "w").write("work")
    git(repo, "add", "."); git(repo, "commit", "-m", "work")
    good = verify_done(repo, "feat/x")
    ok += [good[0] is True, "1 commit(s)" in good[1], "work" in good[1]]
    base = trunk_sha(repo)
    ok += [verify_done(repo, "feat/x", base)[0] is True,   # trunk untouched
           verify_done(repo, "feat/x", base, base="feat/x")[0] is False,
           "beyond feat/x" in verify_done(repo, "feat/x", base,
                                          base="feat/x")[1]]  # stacked base
    green = run_tests(repo, "python3 -c \"print('all good')\"")
    red = run_tests(repo, "python3 -c \"raise SystemExit('boom')\"")
    ok += [green == (True, "all good"), red[0] is False, "boom" in red[1],
           run_tests(repo, "sleep 2", timeout=1)[0] is False,
           test_cmd("# block\ntest: python3 -m unittest\n## tasks")
           == "python3 -m unittest",
           test_cmd("# block with no test line") is None,
           # trunk-only validation: its own line, never mistaken for test:
           trunk_test_cmd("test: t\ntrunk-test: python3 check.py b16")
           == "python3 check.py b16",
           test_cmd("trunk-test: python3 check.py") is None,
           trunk_test_cmd("test: only the suite") is None]
    git(repo, "checkout", "-q", "main")
    open(f"{repo}/h", "w").write("illegal")
    git(repo, "add", "."); git(repo, "commit", "-m", "illegal trunk commit")
    bad = verify_done(repo, "feat/x", base)
    ok += [bad[0] is False, "trunk violation" in bad[1]]   # trunk moved
    ok += [contains_trunk(repo, "feat/x") is False]        # trunk moved past it
    git(repo, "checkout", "-q", "feat/x")
    git(repo, "merge", "-qm", "sync trunk", "main")        # worker-style sync
    ok += [contains_trunk(repo, "feat/x") is True]
    git(repo, "checkout", "-q", "main")
    merged = merge_to_main(repo, "feat/x")                 # engine landing
    ok += [merged[0] is True,
           git(repo, "cat-file", "-e", "main:g").returncode == 0,
           "land: feat/x" in git(repo, "log", "-1", "--format=%s").stdout]
    git(repo, "checkout", "-qb", "feat/c", "main")         # conflicting branch
    open(f"{repo}/f", "w").write("branch side")
    git(repo, "add", "."); git(repo, "commit", "-qm", "branch edit")
    git(repo, "checkout", "-q", "main")
    open(f"{repo}/f", "w").write("main side")
    git(repo, "add", "."); git(repo, "commit", "-qm", "main edit")
    pre = trunk_sha(repo)
    conflict = merge_to_main(repo, "feat/c")
    ok += [conflict[0] is False,
           trunk_sha(repo) == pre,                         # aborted clean
           git(repo, "status", "--porcelain").stdout == ""]
    ok += [orphan_branch(repo, "feat/c") == "orphan/feat/c",
           git(repo, "rev-parse", "--verify", "--quiet",
               "feat/c").returncode != 0,                  # original gone
           orphan_branch(repo, "feat/c") is None]          # missing -> None
    git(repo, "branch", "feat/c")                          # second crash:
    ok += [orphan_branch(repo, "feat/c") == "orphan/feat/c"]  # latest wins
    from pathlib import Path
    arena = Path(tempfile.mkdtemp(prefix="gate-arena-")) / "a1"
    added = add_arena(repo, "feat/ar", arena)
    ok += [added[0] is True, (arena / "f").exists()]       # isolated copy
    open(arena / "g2", "w").write("arena work")
    git(arena, "add", "."); git(arena, "commit", "-qm", "arena work")
    ok += [verify_done(repo, "feat/ar")[0] is True,        # refs are shared
           add_arena(repo, "feat/ar", arena)[0] is False]  # dup branch fails
    remove_arena(repo, arena)
    ok += [not arena.exists(),
           git(repo, "rev-parse", "--verify", "--quiet",
               "feat/ar").returncode == 0]                 # branch survives
    # a dead engine's residue — a dir this repo never knew as a worktree
    # (260717: leftover arenas poisoned the next run) — is gone too
    residue = Path(tempfile.mkdtemp(prefix="gate-residue-")) / "block-02"
    residue.mkdir(); (residue / ".git").write_text("gitdir: /nowhere")
    remove_arena(repo, residue)
    ok += [not residue.exists()]
    # judge_copy: detached, pinned, scrubbed on every resync
    jc = Path(tempfile.mkdtemp(prefix="gate-judge-")) / "j1"
    sha1 = git(repo, "rev-parse", "feat/ar").stdout.strip()
    ok += [judge_copy(repo, sha1, jc)[0] is True,
           (jc / "g2").exists(),                           # delivered tree
           git(jc, "rev-parse", "HEAD").stdout.strip() == sha1,
           git(jc, "symbolic-ref", "-q", "HEAD").returncode != 0]  # detached
    open(jc / "g2", "w").write("judge scribble")           # contamination…
    open(jc / "notes.md", "w").write("judge notes")
    git(repo, "checkout", "-q", "feat/ar")                 # …and tip moves
    open(f"{repo}/g3", "w").write("cycle 2 fix")
    git(repo, "add", "."); git(repo, "commit", "-qm", "fix")
    sha2 = git(repo, "rev-parse", "feat/ar").stdout.strip()
    git(repo, "checkout", "-q", "main")
    ok += [judge_copy(repo, sha2, jc)[0] is True,          # resync in place
           git(jc, "rev-parse", "HEAD").stdout.strip() == sha2,
           open(jc / "g2").read() == "arena work",         # scribble wiped
           not (jc / "notes.md").exists(),                 # stray file swept
           git(jc, "status", "--porcelain").stdout == ""]
    remove_arena(repo, jc)
    ok += [not jc.exists()]
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    selftest()
