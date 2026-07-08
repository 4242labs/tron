"""block_01_14_test — regressions for the 01-14 merge-order-integrity + wall-hold set
(tron-15 defects D-15-1..4).

  T1  merge-in-flight (D-15-1): once an approved merge's order is issued, a moved branch
      tip is verified by content (`git patch-id --stable`) before voiding the grant — a
      patch-id MATCH carries the approval to the new tip (the tron-15 race: worker rebase
      after a non-ff retry must never read as an unseen change / gate-bypass); a DIVERGENT
      tip still voids + re-pins exactly as before. The pre-order re-pin (tip moves before
      any approval) is untouched.
  T2  wall hold (D-15-2): a `wall` report parks the case but never releases the sender —
      the worker is HELD (roster status 'walled', excluded from work-selection/_pool) and
      stays resolvable on-roster; operator `resume` un-holds it.
  T3  deterministic operator settle (D-15-3): `CASE-<n>` + a verb anywhere in an operator
      message settles the case with zero classify/LLM calls; no match falls through to
      classify; a settle matching no pending case replies naming the pending set (never a
      silent no-op).
  T4  lander ordering (D-15-4): the paperwork lander removes a branch's worktree BEFORE
      deleting the branch — no `ref survives` noise, no leftover worktree residue.

FSM-level cases (T1/T2/T3) are dry (TRON_DRY, sentry_test's fixture builders, trunk.*
monkeypatched — same convention as mg_01_test.py/block_01_13_test.py). T4 and the
patch-id primitive itself are proven against REAL throwaway git repos (block_01_11_test's
_mkrepo/_git convention) — git reads by design.

Run: python3 engine/block_01_14_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import util             # noqa: E402
import judge            # noqa: E402
import trunk            # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started, events  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _events(eng):
    return util.read_jsonl(eng.ctx.event_log)


def _eng(block="A-01"):
    ctx, _ = build(blocks=[(block, "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _ask_before_merging(eng):
    eng.st.approvals["merge"] = "ASK"


# ── T1 (AC-1): the tron-15 race — approve -> non-ff retry -> worker rebase (same
#    content) -> patch-id match suppresses the re-pin -> merge lands, no bypass ──
def t_race_patch_id_match_suppresses_repin():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    _ask_before_merging(eng)
    orig = {"branch_exists": trunk.branch_exists, "branch_merged": trunk.branch_merged,
            "tip_sha": trunk.tip_sha, "merge_ff_only": trunk.merge_ff_only,
            "patch_id_matches": trunk.patch_id_matches}
    tip = {"v": "sha1"}
    ff_calls = {"n": 0}
    trunk.branch_exists = lambda *a, **k: True
    trunk.branch_merged = lambda *a, **k: False
    trunk.tip_sha = lambda *a, **k: tip["v"]
    trunk.patch_id_matches = lambda *a, **k: True   # same content, just rebased
    try:
        # Worker reports done -> raises the merge ASK (case_merge, case_tip = sha1).
        eng._drive_gate("A-01", g, on_report=True)
        cid = next((c for c in eng.st.pending_cases), None)
        ok("T1 setup: merge ASK parked at sha1", cid is not None and g.get("case_tip") == "sha1")

        # Operator approves -> approved_merge + merge_in_flight set; drive_gate fires inline.
        # First merge attempt fails non-ff (trunk moved elsewhere) -> re-nudge, stage stays local.
        def ff_first_fails(*a, **k):
            ff_calls["n"] += 1
            return False, "non-fast-forward"
        trunk.merge_ff_only = ff_first_fails
        eng._h_apply_decision({"case": cid, "decision": "approve", "block": "A-01"})
        ok("T1 approve sets approved_merge + merge_in_flight",
           g.get("approved_merge") is True and g.get("merge_in_flight") is True)
        ok("T1 non-ff retry keeps the block at local (no bypass, no new case)",
           g.get("stage") == "local" and not eng.st.pending_cases)

        # Worker rebases onto the moved trunk (same content -> patch-id matches) and
        # re-reports done: the tip changed but the order is IN FLIGHT.
        tip["v"] = "sha2"

        def ff_second_ok(*a, **k):
            ff_calls["n"] += 1
            return True, ""
        trunk.merge_ff_only = ff_second_ok
        eng._tq = []
        eng._drive_gate("A-01", g, on_report=True)
        bypassed = [e for e in _events(eng) if e.get("code") == "gate-bypass"]
        ok("T1 patch-id match carries the grant to the new tip (no void)",
           g.get("case_tip") == "sha2")
        ok("T1 race replay: merge lands on the new tip, gate advances to trunk",
           g.get("stage") == "trunk" and g.get("merged_sha") == "sha2")
        ok("T1 race replay: NO gate-bypass failure", not bypassed, f"{bypassed}")
        ok("T1 race replay: NO duplicate case (only ever one ASK, already closed)",
           not eng.st.pending_cases)
        ok("T1 merge_in_flight cleared on landing", not g.get("merge_in_flight"))
        ok("T1 exactly two merge attempts (the retry + the landed one)", ff_calls["n"] == 2)
    finally:
        for k, v in orig.items():
            setattr(trunk, k, v)


# ── T1 (AC-2): a content-DIVERGENT rebase after approval still voids + re-pins ──
def t_divergent_rebase_still_repins():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    _ask_before_merging(eng)
    orig = {"branch_exists": trunk.branch_exists, "branch_merged": trunk.branch_merged,
            "tip_sha": trunk.tip_sha, "merge_ff_only": trunk.merge_ff_only,
            "patch_id_matches": trunk.patch_id_matches}
    tip = {"v": "sha1"}
    trunk.branch_exists = lambda *a, **k: True
    trunk.branch_merged = lambda *a, **k: False
    trunk.tip_sha = lambda *a, **k: tip["v"]
    trunk.merge_ff_only = lambda *a, **k: (False, "non-fast-forward")
    trunk.patch_id_matches = lambda *a, **k: True
    try:
        eng._drive_gate("A-01", g, on_report=True)          # ASK parked at sha1
        cid = next((c for c in eng.st.pending_cases), None)
        eng._h_apply_decision({"case": cid, "decision": "approve", "block": "A-01"})
        ok("T2 setup: approved + in-flight, non-ff retry holds at local",
           g.get("approved_merge") is True and g.get("stage") == "local")

        # The worker amends its branch with REAL new content (not a same-content rebase):
        # patch-id must NOT match.
        tip["v"] = "sha3"
        trunk.patch_id_matches = lambda *a, **k: False
        eng._tq = []
        eng._drive_gate("A-01", g, on_report=True)
        ok("T2 divergent content voids the grant (no free carry)",
           not g.get("approved_merge") and not g.get("merge_in_flight"))
        ok("T2 divergent content re-pins a FRESH ask at the new tip",
           g.get("case_merge") and g.get("case_tip") == "sha3")
        ok("T2 exactly one pending case (the re-pin, not a duplicate)",
           len(eng.st.pending_cases) == 1)
    finally:
        for k, v in orig.items():
            setattr(trunk, k, v)


# ── T2 (AC-3): wall holds (never releases); resume un-holds; on-roster corrections ──
def t_wall_holds_not_releases():
    eng = _eng()
    w = eng.st.workers[0]
    eng._h_escalate({"block": "A-01", "worker_id": "ENG-A-01", "detail": "npm broken"})
    ok("T2 wall holds the worker on the roster (never released)",
       any(x.get("id") == "ENG-A-01" for x in eng.st.workers))
    ok("T2 wall stamps roster status 'walled'", w.get("status") == "walled")
    ok("T2 wall excludes the held worker from work-selection (_pool)",
       not any(x.get("id") == "ENG-A-01" for x in eng._pool()))
    ok("T2 wall parks the block + a case (unchanged behavior)",
       "A-01" in eng.st.blocked
       and any(c.get("kind") == "wall" for c in eng.st.pending_cases.values()))
    cid = next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")

    # A correction from the HELD worker is still processed on-roster (never a ghost/
    # off-roster refusal) — the admission checkpoint still resolves its assigned block.
    slots = eng._admit("worker.wall", {"block": "A-01", "detail": "false alarm"},
                       {"kind": "worker", "id": "ENG-A-01"})
    ok("T2 a held worker's follow-up still admits (processed on-roster)", slots is not None)

    # Operator resume -> un-holds; the worker returns to work-selection.
    eng._h_apply_decision({"case": cid, "decision": "resume"})
    ok("T2 resume un-holds the worker (status restored)", w.get("status") == "working")
    ok("T2 resume returns the worker to work-selection (_pool)",
       any(x.get("id") == "ENG-A-01" for x in eng._pool()))
    ok("T2 resume clears the blocked block", "A-01" not in eng.st.blocked)


def t_wall_then_abandon_releases():
    # Block doc T2: "abandon/release-shaped settles release as today" — an abandoned
    # wall must FREE the held worker (never leave it parked 'walled' with a live idle
    # session until session end), and drop the block.
    eng = _eng()
    eng._h_escalate({"block": "A-01", "worker_id": "ENG-A-01", "detail": "stuck"})
    cid = next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")
    ok("T2 setup: worker held at the wall",
       any(x.get("id") == "ENG-A-01" and x.get("status") == "walled"
           for x in eng.st.workers))
    eng._h_apply_decision({"case": cid, "decision": "abandon"})
    ok("T2 abandon releases the held worker (off the roster, never left 'walled')",
       not any(x.get("id") == "ENG-A-01" for x in eng.st.workers))
    ok("T2 abandon drops the block",
       "A-01" in eng._dropped() and "A-01" not in eng.st.blocked)
    ok("T2 abandon records the release (forensic chokepoint fired)",
       any(e.get("type") == "release" and e.get("actor") == "ENG-A-01"
           for e in _events(eng)))


def t_wall_never_releases_the_jobs_slot():
    # The held worker's session is left running (T2: never jobs.release on a wall) —
    # distinguished from the OLD behavior (_release_worker) by staying on the roster
    # with its record intact (session_id preserved), not purged.
    eng = _eng()
    eng._h_escalate({"block": "A-01", "worker_id": "ENG-A-01", "detail": "stuck"})
    w = next(x for x in eng.st.workers if x.get("id") == "ENG-A-01")
    ok("T2 held worker record intact (session_id preserved, not purged)",
       w.get("session_id") == "dry")


# ── T3 (AC-4): deterministic regex settle ──
def t_settle_regex_hits():
    eng = _eng()
    ok("T3 'resume CASE-007' (verb-first)",
       eng._settle_regex("resume CASE-007") == {"case": "CASE-007", "decision": "resume"})
    ok("T3 'CASE-007: resume' (case-first)",
       eng._settle_regex("CASE-007: resume") == {"case": "CASE-007", "decision": "resume"})
    ok("T3 'approve CASE-12 please' (unpadded id normalizes)",
       eng._settle_regex("approve CASE-12 please") == {"case": "CASE-012", "decision": "approve"})
    ok("T3 'abandon case-4' (lowercase tag)",
       eng._settle_regex("abandon case-4") == {"case": "CASE-004", "decision": "abandon"})
    ok("T3 no case id -> no match (falls through to classify)",
       eng._settle_regex("resume please") is None)
    ok("T3 no verb -> no match (falls through to classify)",
       eng._settle_regex("what's up with CASE-007?") is None)


def t_settle_regex_zero_model_calls_and_fallthrough():
    eng = _eng()
    orig_call = judge.call
    calls = {"n": 0}

    def counting_call(*a, **k):
        calls["n"] += 1
        return True, {"tag": "operator.status_query", "slots": {}}, []
    judge.call = counting_call
    try:
        tag, slots = eng._classify({"text": "resume CASE-007",
                                    "sender": {"kind": "operator"}})
        ok("T3 regex hit -> operator.decision, zero model calls",
           tag == "operator.decision" and slots.get("case") == "CASE-007"
           and slots.get("decision") == "resume" and calls["n"] == 0)

        tag2, _ = eng._classify({"text": "how's it going?",
                                 "sender": {"kind": "operator"}})
        ok("T3 no match -> falls through to classify (model called)",
           tag2 == "operator.status_query" and calls["n"] == 1)

        # A worker message is never fast-pathed, even if it happens to contain the shape —
        # T3 is scoped to the trusted operator inbox.
        eng._classify({"text": "resume CASE-007", "tag": "",
                       "sender": {"kind": "worker", "id": "ENG-A-01"}})
        ok("T3 the regex fast-path is operator-only (a worker message still classifies)",
           calls["n"] == 2)
    finally:
        judge.call = orig_call


def t_settle_no_matching_case_replies_never_noops():
    eng = _eng()
    real_cid = eng._open_case("A-01", "wall", "ENG-A-01", "stuck")
    n0 = len(events(eng.ctx))
    eng._h_apply_decision({"case": "CASE-999", "decision": "resume"})
    lines = events(eng.ctx)
    ok("T3 settle on an unresolvable case is never a silent no-op",
       len(lines) > n0)
    ok("T3 the reply names the pending case id(s)",
       any("CASE-999" in t and real_cid in t for t in lines[n0:]), f"{lines[n0:]}")
    ok("T3 the unresolved settle does not touch the real pending case",
       real_cid in eng.st.pending_cases)


# ── T4 (AC-5): the paperwork lander removes the worktree BEFORE deleting the branch ──
def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _mkrepo(prefix):
    d = tempfile.mkdtemp(prefix=prefix)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    os.makedirs(os.path.join(d, "meta"))
    with open(os.path.join(d, "meta", "x.md"), "w") as fh:
        fh.write("base\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


def t_lander_removes_worktree_before_branch_delete():
    # T3 (01-32, ADR-0002 D1): this test's original premise (the ENGINE removes a
    # worktree before deleting a branch it just landed) is retired outright —
    # `verify_docs` (renamed from `land_docs`) never lands or deletes anything any
    # more; landing is `land.sh`'s job under a grant, and worktree/branch cleanup is
    # the WORKER's own close ritual (Decision 1: "Branch deletion is the worker's
    # close ritual ... never an engine `branch -d`"). What survives: the content
    # verdict itself ("ok" — clean, ff-able) — asserted here — plus the fact that
    # NEITHER the worktree nor the branch is touched by this read-only check.
    d = _mkrepo("tron-0114-lander-")
    _git(d, "branch", "feat/paperwork")
    wt = os.path.join(d, "wt-paperwork")
    _git(d, "worktree", "add", "-q", wt, "feat/paperwork")
    with open(os.path.join(wt, "meta", "x.md"), "a") as fh:
        fh.write("paperwork addition\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-qm", "paperwork")
    code, detail = trunk.verify_docs(d, "feat/paperwork", ["meta/"], "main")
    ok("T3 verify_docs verdict: clean, ff-able -> 'ok' (never lands it itself)",
       code == "ok", detail)
    ok("T3 verify_docs never deletes the branch (worker's own close ritual now)",
       trunk.branch_exists(d, "feat/paperwork"))
    ok("T3 verify_docs never removes the worktree either",
       any(p for p, _ in trunk.list_worktrees(d)))
    shutil.rmtree(d, ignore_errors=True)


def t_patch_id_matches_rebase_diverges_on_content():
    d = _mkrepo("tron-0114-patchid-")
    _git(d, "checkout", "-qb", "feat/x")
    with open(os.path.join(d, "meta", "x.md"), "a") as fh:
        fh.write("feature line\n")
    _git(d, "commit", "-aqm", "feature")
    old_tip = _git(d, "rev-parse", "feat/x")[1]
    # Move trunk ahead with an unrelated change, then REBASE feat/x onto it — same net
    # content, new shas -> patch-id must match.
    _git(d, "checkout", "-q", "main")
    with open(os.path.join(d, "meta", "y.md"), "w") as fh:
        fh.write("unrelated trunk work\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "trunk moved")
    _git(d, "checkout", "-q", "feat/x")
    rc, _, err = _git(d, "rebase", "main")
    ok("T-patch-id fixture: rebase applied cleanly", rc == 0, err)
    new_tip = _git(d, "rev-parse", "feat/x")[1]
    ok("T-patch-id: a same-content rebase MATCHES",
       trunk.patch_id_matches(d, old_tip, new_tip, "main"))
    # Now amend real content on top -> a genuinely different diff -> no match.
    with open(os.path.join(d, "meta", "x.md"), "a") as fh:
        fh.write("a real second change\n")
    _git(d, "commit", "-aqm", "real change")
    diverged_tip = _git(d, "rev-parse", "feat/x")[1]
    ok("T-patch-id: genuinely new content does NOT match",
       not trunk.patch_id_matches(d, new_tip, diverged_tip, "main"))
    shutil.rmtree(d, ignore_errors=True)


def main():
    for fn in sorted(k for k in globals() if k.startswith("t_")):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
