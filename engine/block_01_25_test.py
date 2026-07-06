"""block_01_25_test — record integrity at the source (block 01-25, AC-1…AC-6).

F-3 (RETHINKING-TRON-CONSOLIDATED.md, tron-38 CASE-011): the trunk-revalidation "passed"
flag flipped on the worker's REPORT (fsm.py:1372-1375), not on an independent observation,
so a block could reach record/close while a code-bearing commit for that block stranded off
trunk. Two fixes, kept distinct:

  T1  the block invariant (R-03a, `trunk.block_invariant_ok`) — checked ONCE at record->close
      (`_drive_close`), ref-agnostically: every anchor that resolves (the live branch tip AND
      the tracked merged_sha) must be a trunk ancestor; NO anchor resolving is itself a
      failure (never a quiet skip — a deleted/unregistered ref must not pass close cleanly).
  T2  a real validation signal (R-03b, `trunk.run_block_tests`) at the trunk-stage trust
      point — the engine runs the merged commit's own test file(s) itself; absent/failing
      never flips the trunk->record advance.

Deterministic, token-free: REAL throwaway git repos for the git-level predicates (AC-1…AC-5,
same convention as block_01_11_test's record-commit/replica-clean cases), dry FSM-level
fixtures (sentry_test's builders, TRON_DRY) + monkeypatched trunk.* for the wiring proof that
_drive_close/_drive_gate actually call these predicates at the right seam (AC-1/AC-5/AC-6).

AC-7 (full suite + lint) and AC-8 (live CASE-011 replay, manual_by:operator) are verified
outside this file, per the block's Verification column.

Run: python3 engine/block_01_25_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import trunk             # noqa: E402
from fsm import Engine   # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def _mkrepo():
    d = tempfile.mkdtemp(prefix="tron-0125-")
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    with open(os.path.join(d, "src.txt"), "w") as fh:
        fh.write("base\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


def _eng(block="A-01", status="🔄"):
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx)
    started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


# ══ T1 (R-03a): the block invariant — real git ══

# ── AC-1: stranded on the registered branch tip (tron-38 CASE-011's exact ancestry) ──
def t_ac1_stranded_on_branch_tip_fails():
    d = _mkrepo()
    _git(d, "checkout", "-q", "-b", "feat/A-01")
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("code, never merged\n")
    _git(d, "commit", "-aqm", "code, never merged to trunk")
    _git(d, "checkout", "-q", "main")
    okc, detail = trunk.block_invariant_ok(d, "feat/A-01", None, "main", False)
    ok("AC-1 stranded-on-branch-tip commit fails the invariant, not close",
       not okc and "feat/A-01" in detail, detail)
    shutil.rmtree(d, ignore_errors=True)


# ── AC-2: ref-agnostic — a REGISTERED branch, then deleted, must still fail (seam 5) ──
# Review fix (finding 2): the original second sub-test handed a stray sha DIRECTLY to
# block_invariant_ok as merged_sha, as if it were an anonymous/unregistered ref — a shape
# the real call site never produces (block_invariant_ok is ref-agnostic only over the ONE
# registered branch + its tracked merged_sha; there is no repo-wide ref scan, so
# "unregistered ref" detection is out of this block's scope). This proves the REAL
# delivered behavior instead: a REGISTERED branch (name known, merged_sha tracked) whose
# branch ref is later deleted while merged_sha itself is a stranded/never-landed commit —
# the branch-tip arm has nothing left to check (ref gone), but the tracked merged_sha arm
# still catches it on its own ancestry.
def t_ac2_stranded_on_deleted_or_unregistered_ref_fails():
    d = _mkrepo()
    _git(d, "checkout", "-q", "-b", "feat/A-02")
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("stray fix\n")
    _git(d, "commit", "-aqm", "stray fix, never merged")
    _, stray_sha = _git(d, "rev-parse", "HEAD")
    _git(d, "checkout", "-q", "main")
    _git(d, "branch", "-D", "feat/A-02")            # deleted -> the seam 5 hole: no live ref left
    okc, detail = trunk.block_invariant_ok(d, "feat/A-02", None, "main", False)
    ok("AC-2 deleted-ref, no tracked merged_sha: no anchor resolves -> fails closed "
       "(never the old free pass)",
       not okc and "no resolvable anchor" in detail, detail)
    # Same registered branch (name still passed — it WAS registered, only its ref is gone),
    # but this time merged_sha IS tracked (as the real call site always does once a merge
    # is recorded) and its value is the stranded commit itself: the branch-tip arm skips
    # (nothing resolves), but the merged_sha arm still resolves the object and fails it on
    # its own ancestry — proving the invariant does not depend on the branch ref surviving.
    okc2, detail2 = trunk.block_invariant_ok(d, "feat/A-02", stray_sha, "main", False)
    ok("AC-2 registered branch deleted, tracked merged_sha still stranded: the merged_sha "
       "arm catches it even with no live branch ref left",
       not okc2 and stray_sha[:7] in detail2, detail2)
    shutil.rmtree(d, ignore_errors=True)


# ── AC-3: remote mode — a descendant past an already-valid merged_sha is not a blind spot ──
def t_ac3_remote_mode_stranded_descendant_not_blind():
    d = _mkrepo()
    _git(d, "checkout", "-q", "-b", "feat/A-03")
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("landed fix\n")
    _git(d, "commit", "-aqm", "landed fix")
    _git(d, "checkout", "-q", "main")
    _git(d, "merge", "-q", "--ff-only", "feat/A-03")   # a genuine, already-valid merge
    _, merged_sha = _git(d, "rev-parse", "HEAD")
    _git(d, "checkout", "-q", "feat/A-03")
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("a required follow-up, parked, never re-merged (the anchor-gap shape)\n")
    _git(d, "commit", "-aqm", "follow-up fix, never re-merged")
    _git(d, "checkout", "-q", "main")
    # merged_sha alone still checks out clean (it genuinely IS on trunk) — a single-anchor
    # check (the old merged_sha-only read) would stop here and pass; the invariant also
    # reads the LIVE branch tip, so the un-landed descendant still fails it.
    okc, detail = trunk.block_invariant_ok(d, "feat/A-03", merged_sha, "main", False)
    ok("AC-3 a stranded descendant past an already-valid merged_sha still fails "
       "(remote is not a redrive blind spot)",
       not okc and "feat/A-03" in detail, detail)
    shutil.rmtree(d, ignore_errors=True)


# ── AC-4: the happy path — a fully-landed branch passes, no false positive ──
def t_ac4_clean_landing_passes():
    d = _mkrepo()
    _git(d, "checkout", "-q", "-b", "feat/A-04")
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("clean landing\n")
    _git(d, "commit", "-aqm", "clean landing")
    _git(d, "checkout", "-q", "main")
    _git(d, "merge", "-q", "--ff-only", "feat/A-04")
    _, merged_sha = _git(d, "rev-parse", "HEAD")
    okc, detail = trunk.block_invariant_ok(d, "feat/A-04", merged_sha, "main", False)
    ok("AC-4 a fully-landed branch passes — no false positive on the happy path", okc, detail)
    # still passes once the (fully-landed) branch is cleaned up at ordinary close-out —
    # merged_sha alone anchors it; a legitimately-gone branch is never mistaken for stranding.
    _git(d, "branch", "-d", "feat/A-04")
    okc2, detail2 = trunk.block_invariant_ok(d, "feat/A-04", merged_sha, "main", False)
    ok("AC-4 still passes after the branch is deleted post-landing (merged_sha anchors it)",
       okc2, detail2)
    shutil.rmtree(d, ignore_errors=True)


# ══ T2 (R-03b): the validation signal — real git + a real subprocess run ══

# ── AC-5: the signal is OBSERVED, never reported — absent/failing never flips "passed" ──
def t_ac5_validation_signal_observed_not_reported():
    d = _mkrepo()
    # (a) code landed, no test file at all in the merged commit's own diff. `base` is the
    # caller-captured pre-merge trunk tip (real, resolvable, != merged_sha) — never None/
    # collapsed, per the review fix below (AC-5's forbidden shape is COLLAPSED base, not a
    # real narrow one).
    _, base_a = _git(d, "rev-parse", "HEAD")
    _git(d, "checkout", "-q", "-b", "feat/A-05a")
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("feature, no test\n")
    _git(d, "commit", "-aqm", "feature without a test")
    _git(d, "checkout", "-q", "main")
    _git(d, "merge", "-q", "--ff-only", "feat/A-05a")
    _, sha_a = _git(d, "rev-parse", "HEAD")
    okc, detail = trunk.run_block_tests(d, base_a, sha_a, False)
    ok("AC-5 absent test file in the landed delta fails — no signal, no pass",
       not okc and "no test file" in detail, detail)

    # (b) code landed WITH a failing test file — the report never substitutes for the run.
    _, base_b = _git(d, "rev-parse", "HEAD")
    _git(d, "checkout", "-q", "-b", "feat/A-05b")
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("feature b\n")
    with open(os.path.join(d, "b_test.py"), "w") as fh:
        fh.write("import sys\nsys.exit(1)\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "feature + a failing test")
    _git(d, "checkout", "-q", "main")
    _git(d, "merge", "-q", "--ff-only", "feat/A-05b")
    _, sha_b = _git(d, "rev-parse", "HEAD")
    okc, detail = trunk.run_block_tests(d, base_b, sha_b, False)
    ok("AC-5 a failing OBSERVED test-run fails, regardless of any worker claim",
       not okc and "b_test.py" in detail, detail)

    # (c) code landed WITH a genuinely passing test file — the only way the signal flips.
    _, base_c = _git(d, "rev-parse", "HEAD")
    _git(d, "checkout", "-q", "-b", "feat/A-05c")
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("feature c\n")
    with open(os.path.join(d, "c_test.py"), "w") as fh:
        fh.write("import sys\nsys.exit(0)\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "feature + a passing test")
    _git(d, "checkout", "-q", "main")
    _git(d, "merge", "-q", "--ff-only", "feat/A-05c")
    _, sha_c = _git(d, "rev-parse", "HEAD")
    okc, detail = trunk.run_block_tests(d, base_c, sha_c, False)
    ok("AC-5 a genuinely observed passing run is the only way 'passed' flips", okc, detail)
    shutil.rmtree(d, ignore_errors=True)


# ── AC-5 (review fix, gap): a multi-commit ff-merged branch's test lives EARLIER than the
# tip's own single-commit diff — the exact F-3 reopening the independent reviewer proved:
# commit1 adds the feature + its test (passing); commit2 is a trailing, already-green,
# unrelated change. The tip's OWN diff (`git show` on commit2 alone) never sees commit1's
# test file at all — old code returned a false PASS having run nothing of the feature's.
def t_ac5b_multi_commit_range_discovers_earlier_test():
    d = _mkrepo()
    _git(d, "checkout", "-q", "-b", "feat/A-05d")
    _, base_before = _git(d, "rev-parse", "HEAD")     # trunk tip BEFORE this block's commits

    # commit1: the feature + its OWN test file (this is the one a single-commit-diff misses).
    with open(os.path.join(d, "feature.py"), "w") as fh:
        fh.write("def add(a, b):\n    return a + b\n")
    with open(os.path.join(d, "feature_test.py"), "w") as fh:
        fh.write("import sys\nsys.path.insert(0, '.')\nfrom feature import add\n"
                 "assert add(2, 2) == 4\nsys.exit(0)\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "commit1: add feature + feature_test.py")

    # commit2: a trailing, unrelated change touching an ALREADY-GREEN other file — the
    # decoy: its OWN diff is trivially green and never mentions feature_test.py.
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("unrelated trailing change\n")
    _git(d, "commit", "-aqm", "commit2: unrelated trailing change")

    _git(d, "checkout", "-q", "main")
    _git(d, "merge", "-q", "--ff-only", "feat/A-05d")   # literal ff: main tip == branch tip
    _, tip = _git(d, "rev-parse", "HEAD")
    assert tip != base_before

    # The caller-captured base (trunk before this block's commits, per the fix) discovers
    # commit1's feature_test.py even though it is invisible in the tip's own single-commit
    # diff — and the genuinely-passing test flips the signal green.
    okc, detail = trunk.run_block_tests(d, base_before, tip, False)
    ok("AC-5 gap: the full base..tip range discovers commit1's feature_test.py "
       "(never visible in the tip's own single-commit diff) and runs it",
       okc and "1 test file(s) green" in detail, detail)

    # Prove it is NOT a free pass by construction: if feature_test.py actually fails, the
    # range-based discovery must still catch it (never silently skip to the green decoy).
    with open(os.path.join(d, "feature_test.py"), "w") as fh:
        fh.write("import sys\nsys.exit(1)\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "commit3: break feature_test.py")
    _, tip2 = _git(d, "rev-parse", "HEAD")
    okc2, detail2 = trunk.run_block_tests(d, base_before, tip2, False)
    ok("AC-5 gap: a failing test anywhere in the full range still fails the signal",
       not okc2 and "feature_test.py" in detail2, detail2)

    # Review fix (F-3 relocated, fix cycle 2): the OLD single-commit fallback (base=None,
    # the tip's own diff alone) is now REMOVED entirely, not just narrowed — a collapsed/
    # unknown base is untrusted, never a legacy-but-valid signal. Proven directly in
    # t_ac5c_out_of_band_collapsed_base_fails_closed below with the reviewer's exact
    # false-PASS shape (a decoy commit that touches an ALREADY-GREEN test file, which the
    # old fallback would have returned as a false PASS rather than "no test file").
    okc3, detail3 = trunk.run_block_tests(d, None, tip, False)
    ok("AC-5 gap: base=None is now an untrusted/collapsed range -> NOT-OK, never a fallback "
       "diff read", not okc3 and "unresolved" in detail3, detail3)
    shutil.rmtree(d, ignore_errors=True)


# ── MUST-FIX (F-3 relocated, fix cycle 2, AC-5): out-of-band arms (self_merge, out-of-gate
# branch_merged, remote-PR-merged) only have a best-effort `merge_base(main, branch)`. When
# that external merge was itself a bare fast-forward, merge_base COLLAPSES to merged_sha (or
# fails to resolve -> ''); the OLD code then fell back to the tip's own single-commit diff and
# could return a false PASS off an unrelated, already-green decoy commit while the block's REAL
# (possibly broken) test never ran — the exact shape AC-5 forbids ("a block whose validation
# signal is absent/failing does not flip passed"). Reproduces the independent reviewer's own
# repro: commit1 = broken feature.py + feature_test.py (would fail if it ever ran); commit2
# (tip) = unrelated, already-green other_test.py; ff-merged so base collapses to tip.
def t_ac5c_out_of_band_collapsed_base_fails_closed():
    d = _mkrepo()
    _git(d, "checkout", "-q", "-b", "feat/A-05e")

    # commit1: the feature + a BROKEN test — the real signal, never reached by the old code.
    with open(os.path.join(d, "feature.py"), "w") as fh:
        fh.write("def add(a, b):\n    return a + b\n")
    with open(os.path.join(d, "feature_test.py"), "w") as fh:
        fh.write("import sys\nsys.exit(1)\n")           # broken: would fail if actually run
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "commit1: add feature + a BROKEN feature_test.py")

    # commit2 (tip): unrelated, already-green decoy — all the tip's own single-commit diff
    # would ever see.
    with open(os.path.join(d, "other_test.py"), "w") as fh:
        fh.write("import sys\nsys.exit(0)\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "commit2: unrelated, already-green other_test.py")

    _git(d, "checkout", "-q", "main")
    _git(d, "merge", "-q", "--ff-only", "feat/A-05e")    # bare ff: main tip == branch tip
    _, tip = _git(d, "rev-parse", "HEAD")

    # Out-of-band arm's own best-effort `merge_base(main, branch)` would return `tip` itself
    # here (a bare ff collapses branch and trunk onto the identical commit) — simulate that
    # exact collapsed value, never a real range.
    okc, detail = trunk.run_block_tests(d, tip, tip, False)
    ok("MUST-FIX AC-5: out-of-band collapsed base (base==merged_sha) holds NOT-OK — "
       "never a false PASS off the unrelated green decoy",
       not okc and "unresolved" in detail, detail)

    # Same for the unresolvable/empty-base shape (merge_base failing to resolve at all).
    okc2, detail2 = trunk.run_block_tests(d, "", tip, False)
    ok("MUST-FIX AC-5: empty/unresolvable base also holds NOT-OK (never a free pass)",
       not okc2 and "unresolved" in detail2, detail2)
    shutil.rmtree(d, ignore_errors=True)


# ══ wiring: the predicates fire at the right seam, dry FSM fixtures + monkeypatched trunk.* ══

def _capture_failures(eng):
    calls = []
    orig = eng.events.failure
    eng.events.failure = (lambda fclass, code, op, cause, **k:
                          calls.append((fclass, code, op, cause)) or orig(fclass, code, op, cause, **k))
    return calls


# ── AC-1/AC-6 wiring: _drive_close runs the invariant BEFORE closing, names the stranded ref ──
def t_wire_drive_close_invariant_blocks_and_names_it():
    eng = _eng()
    eng.dry = False
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "record", "pr": None, "record_checked": True})
    fails = _capture_failures(eng)
    orig = trunk.block_invariant_ok
    trunk.block_invariant_ok = (lambda *a, **k:
                                (False, "branch feat/A-01 tip abc1234 is not on trunk"))
    try:
        eng._drive_close("A-01", g, "ENG-A-01")
    finally:
        trunk.block_invariant_ok = orig
    ok("AC-1/T1 wiring: an invariant violation blocks close (gate dropped, never closed)",
       "A-01" not in eng.st.gate, f"gate={eng.st.gate}")
    ok("AC-6 the escalation is a NAMED, distinct code (record-bypass), not the generic wall",
       fails and fails[0][1] == "record-bypass", f"fails={fails}")
    ok("AC-6 the escalation names the stranded ref/commit in its detail",
       fails and "feat/A-01" in fails[0][3], f"fails={fails}")


# ── T1 wiring: a passing invariant lets the EXISTING record-check + close-advance run ──
def t_wire_drive_close_invariant_pass_through():
    eng = _eng()
    eng.dry = False
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "record", "pr": None})
    orig_inv, orig_rec = trunk.block_invariant_ok, trunk.record_commit_ok
    trunk.block_invariant_ok = lambda *a, **k: (True, "")
    trunk.record_commit_ok = lambda *a, **k: (True, "abc1234")
    try:
        eng._drive_close("A-01", g, "ENG-A-01")
    finally:
        trunk.block_invariant_ok, trunk.record_commit_ok = orig_inv, orig_rec
    ok("T1 wiring: an invariant pass still reaches close via the untouched record-check",
       g.get("stage") == "close" and g.get("block_checked") is True
       and g.get("record_checked") is True, f"g={g}")


# ── T1 wiring: block_checked guards the invariant to run exactly ONCE per gate ──
def t_wire_block_checked_runs_once():
    eng = _eng()
    eng.dry = False
    eng.st.branches["A-01"] = "feat/A-01"
    eng.st.workers.clear()                    # no bound worker -> the workerless close path
    g = eng.st.gate.setdefault("A-01", {"stage": "record", "pr": None})
    calls = {"n": 0}

    def spy(*a, **k):
        calls["n"] += 1
        return (True, "")
    orig_inv, orig_rec = trunk.block_invariant_ok, trunk.record_commit_ok
    trunk.block_invariant_ok = spy
    trunk.record_commit_ok = lambda *a, **k: (True, "abc1234")
    confirmed = []
    eng._confirm_close = lambda b, gg: confirmed.append(b)
    try:
        eng._drive_close("A-01", g, None)     # 1st: checks once, advances to close, returns
        first_ok = g.get("stage") == "close" and calls["n"] == 1
        eng._drive_close("A-01", g, None)     # 2nd: already close, no bound worker -> confirm
    finally:
        trunk.block_invariant_ok, trunk.record_commit_ok = orig_inv, orig_rec
    ok("T1 setup: the first tick checks the invariant and advances to close", first_ok, f"g={g}")
    ok("T1 block_checked guards the invariant to run exactly once across repeated ticks",
       calls["n"] == 1, f"calls={calls}")
    ok("T1 the second tick (already close) proceeds straight to confirm-close, unblocked",
       confirmed == ["A-01"], f"confirmed={confirmed}")


# ── AC-5 wiring: the trunk-stage on_report flip now GATES on the observed signal ──
def t_wire_trunk_report_requires_signal():
    eng = _eng()
    eng.dry = False
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None, "merged_sha": "deadbeef"})
    orig = trunk.run_block_tests
    trunk.run_block_tests = lambda *a, **k: (False, "no test file in the merged commit's own diff")
    try:
        eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
    finally:
        trunk.run_block_tests = orig
    ok("AC-5 wiring: an absent/failing observed signal holds at trunk — 'passed' never flips",
       g.get("stage") == "trunk", f"g={g}")


def t_wire_trunk_report_advances_on_green_signal():
    eng = _eng()
    eng.dry = False
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None, "merged_sha": "deadbeef"})
    orig = trunk.run_block_tests
    trunk.run_block_tests = lambda *a, **k: (True, "1 test file(s) green")
    try:
        eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
    finally:
        trunk.run_block_tests = orig
    ok("AC-5 wiring: a genuine engine-observed green signal is what advances trunk -> record",
       g.get("stage") == "record", f"g={g}")


def main():
    t_ac1_stranded_on_branch_tip_fails()
    t_ac2_stranded_on_deleted_or_unregistered_ref_fails()
    t_ac3_remote_mode_stranded_descendant_not_blind()
    t_ac4_clean_landing_passes()
    t_ac5_validation_signal_observed_not_reported()
    t_ac5b_multi_commit_range_discovers_earlier_test()
    t_ac5c_out_of_band_collapsed_base_fails_closed()
    t_wire_drive_close_invariant_blocks_and_names_it()
    t_wire_drive_close_invariant_pass_through()
    t_wire_block_checked_runs_once()
    t_wire_trunk_report_requires_signal()
    t_wire_trunk_report_advances_on_green_signal()

    failed = [n for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("ok  " if c else "FAIL") + " " + n + (f" — {d}" if d and not c else ""))
    print(f"\n{len(_results) - len(failed)}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
