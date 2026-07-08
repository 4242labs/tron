"""tron13_test — regressions for the tron-13 pre-sim implementation set (the co-signed
design of record: tron-meta logs/engineer/260702-tron-13-design.md).

  D3/A-5  full ladder ratchet — trunk AND record are a monotonic hold zone; the held
          rung re-verifies its OWN predicate (merged sha ancestry / merged PR staying
          closed) and a contradicted predicate is a NAMED gate-contradiction escalation,
          never a silent recompute and never a "worker stall" misread.

Run: python3 engine/tron13_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import trunk            # noqa: E402
import jobs             # noqa: E402
import util             # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started  # noqa: E402


def _events(eng):
    return util.read_jsonl(eng.ctx.event_log)

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _eng(blocks=None, block="A-01"):
    ctx, repo = build(blocks=blocks)
    eng = Engine(ctx)
    started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _capture(eng):
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
                sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


# ── D3/A-5: the ladder ratchet ──
def t_ratchet_floor_paperwork_commits():
    # The W1 floor case, now with the anchored predicate: paperwork commits move the
    # branch tip (branch_merged goes false) but the MERGED sha stays an ancestor —
    # the gate holds quietly, no contradiction, no regression, no duplicate orders.
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None,
                                        "merged_sha": "abc1234"})
    sent = _capture(eng)
    orig_bm, orig_be, orig_ia = trunk.branch_merged, trunk.branch_exists, trunk.is_ancestor
    trunk.branch_merged = lambda *a, **k: False          # tip moved (paperwork commits)
    trunk.branch_exists = lambda *a, **k: True
    trunk.is_ancestor = lambda *a, **k: True             # merged sha still in history
    try:
        eng._drive_gate("A-01", g)
        ok("A-5 paperwork commits: trunk holds on merged-sha ancestry",
           g.get("stage") == "trunk", f"stage={g.get('stage')}")
        ok("A-5 paperwork commits: no gate-contradiction raised",
           not any(t.startswith("wall:raised") or t == "escalate.gate" for t, _ in sent)
           and "A-01" in eng.st.gate, f"sent={sent}")
        ok("A-5 paperwork commits: no duplicate DONE-LOCAL",
           not any(t == "gate.local" for t, _ in sent), f"sent={sent}")
    finally:
        trunk.branch_merged, trunk.branch_exists, trunk.is_ancestor = (
            orig_bm, orig_be, orig_ia)


def t_ratchet_record_holds():
    # record is inside the hold zone too: a plain tick never recomputes it downward.
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "record", "pr": None,
                                        "merged_sha": "abc1234"})
    sent = _capture(eng)
    orig_bm, orig_ia = trunk.branch_merged, trunk.is_ancestor
    trunk.branch_merged = lambda *a, **k: False
    trunk.is_ancestor = lambda *a, **k: True
    try:
        eng._drive_gate("A-01", g)
        ok("A-5 record holds on a plain tick", g.get("stage") == "record",
           f"stage={g.get('stage')}")
        ok("A-5 record hold sends no stage order",
           not any(t.startswith("gate.") for t, _ in sent), f"sent={sent}")
    finally:
        trunk.branch_merged, trunk.is_ancestor = orig_bm, orig_ia


def t_ratchet_ancestry_contradiction():
    # History surgery (force-push / reset): the merged sha vanishes from trunk history —
    # a NAMED gate-contradiction escalation, never a quiet hold, never a stall misread.
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None,
                                        "merged_sha": "abc1234"})
    sent = _capture(eng)
    orig_ia = trunk.is_ancestor
    trunk.is_ancestor = lambda *a, **k: False
    try:
        eng._drive_gate("A-01", g)
        ok("A-5 broken ancestry drops the gate", "A-01" not in eng.st.gate,
           f"gate={eng.st.gate}")
        fails = [e for e in _events(eng) if e.get("kind") == "failure"]
        ok("A-5 broken ancestry raises a named contradiction",
           any(e.get("code") == "gate-contradiction"
               and "no longer in trunk history" in (e.get("cause") or "")
               for e in fails),
           f"fails={fails}")
        ok("A-5 contradiction failure is code gate-contradiction",
           any(e.get("code") == "gate-contradiction" for e in fails),
           f"fails={fails}")
    finally:
        trunk.is_ancestor = orig_ia


def t_ratchet_pr_reopened_contradiction():
    # Remote mode: the merged PR shows OPEN again (revert + reopen) while the gate holds
    # at trunk — affirmative regression evidence, escalates as gate-contradiction.
    eng = _eng()
    eng.st.workers[0]["branch"] = "feat/a-01"
    eng.st.branches["A-01"] = "feat/a-01"
    eng.st.open_prs["feat/a-01"] = {"number": 7, "checks": "passing"}
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": 7,
                                        "merged_sha": "abc1234"})
    sent = _capture(eng)
    orig_ia = trunk.is_ancestor
    trunk.is_ancestor = lambda *a, **k: True             # revert keeps ancestry; the PR is the tell
    try:
        eng._drive_gate("A-01", g)
        ok("A-5 reopened PR drops the gate", "A-01" not in eng.st.gate,
           f"gate={eng.st.gate}")
        fails = [e for e in _events(eng) if e.get("kind") == "failure"]
        ok("A-5 reopened PR raises a named contradiction naming the PR",
           any(e.get("code") == "gate-contradiction" and "#7" in (e.get("cause") or "")
               for e in fails),
           f"fails={fails}")
    finally:
        trunk.is_ancestor = orig_ia


def t_ratchet_no_sha_holds_quietly():
    # No anchored sha (e.g. remote-merged branch unresolvable locally): the predicate is
    # unknowable — hold quietly (R-3's giveup detail covers diagnosis at the idle cap).
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})
    orig_ia = trunk.is_ancestor
    trunk.is_ancestor = lambda *a, **k: False            # would contradict IF consulted
    try:
        eng._drive_gate("A-01", g)
        ok("A-5 missing merged sha never fabricates a contradiction",
           g.get("stage") == "trunk" and "A-01" in eng.st.gate,
           f"stage={g.get('stage')}")
    finally:
        trunk.is_ancestor = orig_ia


def t_merge_anchors_sha():
    # The executed local ff-merge anchors the predicate to the EXACT merged tip (A-3's
    # pinned sha), so later paperwork commits can never dislodge it.
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                        "approved_merge": True})
    orig_be, orig_ff, orig_ts = trunk.branch_exists, trunk.merge_ff_only, trunk.tip_sha
    trunk.branch_exists = lambda *a, **k: True
    trunk.merge_ff_only = lambda *a, **k: (True, "")
    trunk.tip_sha = lambda *a, **k: "feedbee1"
    try:
        eng._drive_gate("A-01", g)
        ok("A-5 executed merge anchors merged_sha",
           g.get("stage") == "trunk" and g.get("merged_sha") == "feedbee1",
           f"g={g}")
    finally:
        trunk.branch_exists, trunk.merge_ff_only, trunk.tip_sha = (
            orig_be, orig_ff, orig_ts)


# ── D4/F-4/R-7: operator re-ping ladder -> named resumable safe-park ──
def _clocked(eng, t0=1000.0):
    clock = {"t": t0}
    eng._now_s = lambda: clock["t"]
    return clock


def t_case_reping_ladder():
    # ceiling 30 x case_reping_after 20 = 600s spans: re-pings at each span, park after
    # case_reping_max unanswered — an AFK operator costs latency, never silence.
    eng = _eng()
    clock = _clocked(eng)
    cid = eng._open_case("A-01", "wall", "ENG-A-01", "needs a human")
    sent = _capture(eng)
    eng._drive_cases()                                   # anchors; no ping yet
    ok("D4 no re-ping inside the first span", sent == [], f"sent={sent}")
    for i in (1, 2, 3):
        clock["t"] += 600
        eng._drive_cases()
    pings = [s for t, s in sent if t == "escalate.wall"
             and "still parked" in s.get("detail", "")]
    ok("D4 three re-pings across three spans", len(pings) == 3, f"sent={sent}")
    ok("D4 re-pings carry the case id", all(s.get("case") == cid for s in pings))
    clock["t"] += 600
    eng._drive_cases()                                   # 4th span -> safe-park notice
    case = eng.st.pending_cases[cid]
    parked = [s for t, s in sent if t == "escalate.wall"
              and "safe-parked" in s.get("detail", "")]
    ok("D4 caps into a named safe-park", case.get("parked") == "safe" and len(parked) == 1,
       f"case={case}")
    ok("D4 safe-park is a forensic event",
       any(e.get("type") == "case_safe_parked" for e in _events(eng)),
       f"events={[e.get('type') for e in _events(eng)]}")
    n = len(sent)
    clock["t"] += 6000
    eng._drive_cases()
    ok("D4 a safe-parked case goes quiet", len(sent) == n, f"sent={sent[n:]}")


def t_case_park_is_resumable():
    # The safe-park is state, not a dead-end: the operator's reply settles it exactly
    # like a fresh case (resume path through _h_apply_decision).
    eng = _eng()
    cid = eng._open_case("A-01", "wall", "ENG-A-01", "needs a human")
    eng.st.pending_cases[cid]["parked"] = "safe"
    eng.st.blocked.append("A-01")
    eng._h_apply_decision({"decision": "resume", "case": cid, "block": "A-01"})
    ok("D4 a safe-parked case settles on the operator's reply",
       cid not in eng.st.pending_cases and "A-01" not in eng.st.blocked,
       f"cases={eng.st.pending_cases} blocked={eng.st.blocked}")


def t_case_visibility():
    # The clock is pull — parked calls lead the digest and survive into the session-end
    # record; visibility never depends on the operator asking the right question.
    eng = _eng()
    cid = eng._open_case("A-01", "wall", "ENG-A-01", "needs a human")
    ok("D4 digest leads with the parked call",
       eng._digest().startswith("your call first") and cid in eng._digest(),
       f"digest={eng._digest()}")
    sent = _capture(eng)
    eng._end_session()
    ok("D4 session end re-surfaces the parked call",
       any(t == "escalate.wall" and "session is ending" in s.get("detail", "")
           for t, s in sent), f"sent={sent}")
    ends = [e for e in _events(eng) if e.get("type") == "session_end"]
    ok("D4 session_end event names the parked case",
       ends and cid in ((ends[-1].get("payload") or {}).get("parked_cases") or []),
       f"ends={ends}")


# ── D2/A-2: structured reports resolve with ZERO LLM; S-2-full admission is table-driven ──
def _no_judge(eng):
    import fsm as fsm_mod
    orig = fsm_mod.judge.call

    def boom(*a, **k):
        raise AssertionError("classify_message called for a structured line")
    fsm_mod.judge.call = boom
    return lambda: setattr(fsm_mod.judge, "call", orig)


def t_structured_bypasses_classify():
    eng = _eng()
    restore = _no_judge(eng)
    try:
        tag, slots = eng._classify({"text": "trunk: all green", "tag": "done",
                                    "slots": {"block": "A-01"},
                                    "sender": {"kind": "worker", "id": "ENG-A-01"}})
        ok("A-2 structured done resolves without the model",
           tag == "worker.done" and slots.get("block") == "A-01",
           f"tag={tag} slots={slots}")
        tag, slots = eng._classify({"text": "worktree gone, branch gone", "tag": "clean",
                                    "sender": {"kind": "worker", "id": "ENG-A-01"}})
        ok("A-2 clean maps to worker.done + clean_confirm slot",
           tag == "worker.done" and slots.get("clean_confirm") is True,
           f"tag={tag} slots={slots}")
    finally:
        restore()


def t_structured_unknown_verb_drops():
    eng = _eng()
    restore = _no_judge(eng)
    sent = _capture(eng)
    try:
        tag, slots = eng._classify({"text": "whatever", "tag": "finished",
                                    "sender": {"kind": "worker", "id": "ENG-A-01"}})
        ok("A-2 unknown structured verb never becomes a trigger", tag == "drop",
           f"tag={tag}")
        eng._ingest(tag, slots, {"kind": "worker", "id": "ENG-A-01"})
        ok("A-2 dropped verb fires nothing", sent == [], f"sent={sent}")
        recs = [e for e in _events(eng) if e.get("kind") == "unclassified"]
        ok("A-2 unknown verb is recorded with its sender",
           any("finished" in ((e.get("payload") or {}).get("why") or "")
               and e.get("actor") == "ENG-A-01" for e in recs),
           f"recs={recs}")
    finally:
        restore()


def t_structured_clean_confirms_at_close():
    # The clean_confirm slot is the structured equivalent of the prescribed prefix:
    # at close it admits even when the free text doesn't open with `clean`.
    eng = _eng()
    eng.st.gate["A-01"] = {"stage": "close"}
    slots = eng._admit("worker.done",
                       {"block": "A-01", "_raw": "all tidy, nothing left",
                        "clean_confirm": True},
                       {"kind": "worker", "id": "ENG-A-01"})
    ok("A-2 clean_confirm admits at close without the prefix", slots is not None,
       f"slots={slots}")
    refused = eng._admit("worker.done",
                         {"block": "A-01", "_raw": "all tidy, nothing left"},
                         {"kind": "worker", "id": "ENG-A-01"})
    ok("S-2 free text at close still needs the prescribed prefix", refused is None,
       f"got={refused}")


def t_structured_review_type_from_sender():
    eng = _eng()
    eng.st.workers.append({"id": "REV-code", "role": "reviewer", "rtype": "code",
                           "block": "review:code", "session_id": "dry",
                           "status": "working"})
    restore = _no_judge(eng)
    try:
        tag, slots = eng._classify({"text": "covered — findings log at logs/x.md",
                                    "tag": "review-done",
                                    "sender": {"kind": "worker", "id": "REV-code"}})
        ok("A-2 review-done backfills the type from the sender's record",
           tag == "worker.review_done" and slots.get("type") == "code",
           f"tag={tag} slots={slots}")
    finally:
        restore()


def t_admission_is_declarative():
    # S-2-full: the checkpoint interprets the table — a stage-scoped tag outside its
    # stage is receipt-noted (W6a behavior, now data-driven, no per-tag code).
    eng = _eng()
    eng.st.gate["A-01"] = {"stage": "close"}
    got = eng._admit("worker.recorded", {"block": "A-01", "_raw": "recorded A-01"},
                     {"kind": "worker", "id": "ENG-A-01"})
    ok("S-2 table scopes the record receipt to its stage", got is None, f"got={got}")
    eng.st.gate["A-01"] = {"stage": "record"}
    got = eng._admit("worker.recorded", {"block": "A-01", "_raw": "recorded A-01"},
                     {"kind": "worker", "id": "ENG-A-01"})
    ok("S-2 table admits the receipt AT record", got is not None, f"got={got}")
    # worker.wall pre-gate: `block: True` means canon block, never "gate open".
    # `detail` carries the stated reason (01-31, ADR-0002 D3: a contentless wall is
    # NAK'd at this same checkpoint — this fixture is testing the block/gate axis, not
    # content-integrity, so it carries a real reason exactly like a real report would
    # via _structured's own detail-from-text carry).
    eng2 = _eng()
    got = eng2._admit("worker.wall",
                      {"block": "A-01", "detail": "walled: npm broken",
                       "_raw": "walled: npm broken"},
                      {"kind": "worker", "id": "ENG-A-01"})
    ok("S-2 a pre-gate wall still fires (block means canon row, not open gate)",
       got is not None, f"got={got}")


# ── D1/F-1: the unified paperwork lander (real git — trunk.verify_docs) ──
def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def _mkrepo():
    d = tempfile.mkdtemp(prefix="tron13-lander-")
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    os.makedirs(os.path.join(d, "meta", "blocks", "archive"))
    os.makedirs(os.path.join(d, "meta", "logs"))
    os.makedirs(os.path.join(d, "src"))
    files = {
        "meta/pipeline.md": "| A-01 | logic | 📋 |\n| A-02 | ui | 📋 |\n",
        "meta/blocks/A-01.md": "# A-01\n**Status:** ✅ Done\n",
        "meta/blocks/archive/.keep": "",
        "meta/logs/.keep": "",
        "src/app.txt": "code\n",
        "README.md": "readme\n",
    }
    for p, c in files.items():
        with open(os.path.join(d, p), "w") as fh:
            fh.write(c)
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


def _on_branch(d, branch, fn):
    _git(d, "checkout", "-qb", branch)
    fn()
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "paperwork")
    _git(d, "checkout", "-q", "main")


ALLOW = ["meta/", "README.md"]
DENY = ["meta/blocks/", "meta/pipeline.md"]


def t_lander_lands_paperwork():
    d = _mkrepo()

    def w():
        with open(os.path.join(d, "meta", "logs", "log-1.md"), "w") as fh:
            fh.write("session log\n")
    _on_branch(d, "docs/close", w)
    code, detail = trunk.verify_docs(d, "docs/close", ALLOW, "main", False, denylist=DENY)
    ok("D1 paperwork-only branch verdict is 'ok' (clean, ff-able)",
       code == "ok", f"{code}: {detail}")
    # T3 (01-32, ADR-0002 D1): verify_docs is READ-ONLY now — it never lands or
    # deletes anything; that's `land.sh`'s job under a grant.
    ok("D1 verify_docs never deletes the branch itself", trunk.branch_exists(d, "docs/close"))
    ok("D1 the paperwork is NOT yet on trunk (verify_docs never lands it)",
       _git(d, "show", "main:meta/logs/log-1.md")[0] != 0)


def t_lander_code_violation():
    d = _mkrepo()

    def w():
        with open(os.path.join(d, "src", "sneak.txt"), "w") as fh:
            fh.write("code\n")
        with open(os.path.join(d, "meta", "logs", "log.md"), "w") as fh:
            fh.write("log\n")
    _on_branch(d, "docs/dirty", w)
    code, detail = trunk.verify_docs(d, "docs/dirty", ALLOW, "main", False, denylist=DENY)
    ok("D1 code on a paperwork branch is a violation",
       code == "violation" and "src/sneak.txt" in detail, f"{code}: {detail}")
    ok("D1 violating branch is NOT landed or deleted",
       trunk.branch_exists(d, "docs/dirty"))


def t_lander_own_block_exceptions():
    # The co-signed ask-2 fix: the engineer's close-out archives its OWN block doc,
    # adds Completed, and flips its own pipeline line — all allowed, mechanically scoped.
    d = _mkrepo()

    def w():
        _git(d, "mv", "meta/blocks/A-01.md", "meta/blocks/archive/A-01.md")
        with open(os.path.join(d, "meta", "blocks", "archive", "A-01.md"), "a") as fh:
            fh.write("**Completed:** 2026-07-02\n")
        p = os.path.join(d, "meta", "pipeline.md")
        with open(p) as fh:
            txt = fh.read()
        with open(p, "w") as fh:
            fh.write(txt.replace("| A-01 | logic | 📋 |", "| A-01 | logic | ✅ |"))
        with open(os.path.join(d, "meta", "logs", "log.md"), "w") as fh:
            fh.write("log\n")
    _on_branch(d, "feat/a-01", w)
    allow = ALLOW + ["meta/blocks/A-01.md", "meta/blocks/archive/A-01.md"]
    code, detail = trunk.verify_docs(d, "feat/a-01", allow, "main", False,
                                   denylist=DENY,
                                   line_scoped={"meta/pipeline.md": "A-01"})
    ok("D1 own-block archival + Completed + own pipeline line verdicts 'ok'",
       code == "ok", f"{code}: {detail}")
    # T3 (01-32, ADR-0002 D1): verify_docs never lands it — that's land.sh's job.
    ok("D1 archive move is NOT yet on trunk (verify_docs is read-only)",
       _git(d, "show", "main:meta/blocks/archive/A-01.md")[0] != 0)


def t_lander_foreign_pipeline_line():
    d = _mkrepo()

    def w():
        p = os.path.join(d, "meta", "pipeline.md")
        with open(p) as fh:
            txt = fh.read()
        with open(p, "w") as fh:
            fh.write(txt.replace("| A-02 | ui | 📋 |", "| A-02 | ui | ✅ |"))
    _on_branch(d, "feat/a-01-sneaky", w)
    code, detail = trunk.verify_docs(d, "feat/a-01-sneaky", ALLOW, "main", False,
                                   denylist=DENY,
                                   line_scoped={"meta/pipeline.md": "A-01"})
    ok("D1 a pipeline line naming ANOTHER block is a violation",
       code == "violation" and "pipeline" in detail, f"{code}: {detail}")


def t_lander_nonff_rebases_and_lands():
    # RE-SUPERSEDED (block 01-32, ADR-0002 D1/D2 T1): the 01-17 auto-rebase-and-retry
    # this test used to prove (a non-conflicting trunk move rebase-retries ONCE inside
    # merge_ff_only and lands) is RETIRED — TRON never rebases, conflict-free or not (a
    # write-boundary violation; also the wave-1b stale-branch pipeline clobber's
    # structural fix, AC-2 `clobber_dead`). This reverts to (and updates the name/detail
    # of) the ORIGINAL pre-01-17 contract this test itself once superseded: a moved
    # trunk is non-ff, full stop — the engine never rebases, even a disjoint-file,
    # conflict-free race. Full behavioral coverage of the new contract (the worker's own
    # rebase-before-close ritual resolves it) lives in block_01_32_test.py.
    d = _mkrepo()

    def w():
        with open(os.path.join(d, "meta", "logs", "log.md"), "w") as fh:
            fh.write("log\n")
    _on_branch(d, "docs/behind", w)
    with open(os.path.join(d, "src", "app.txt"), "a") as fh:
        fh.write("moved\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "trunk moved")
    code, detail = trunk.verify_docs(d, "docs/behind", ALLOW, "main", False, denylist=DENY)
    ok("01-32 T1: a moved trunk is non-ff — the engine never rebases, even a "
       "conflict-free disjoint-file race", code == "non-ff", f"{code}: {detail}")
    ok("01-32 T1: the branch survives, untouched, for its owner to rebase",
       trunk.branch_exists(d, "docs/behind"))


def t_lander_nonff_conflict_still_walls():
    # T1 (01-17): a rebase that genuinely CONFLICTS is still the branch owner's problem —
    # the engine aborts cleanly (no mid-rebase residue) and walls non-ff with today's
    # detail, exactly as an unconditional non-ff always has.
    d = _mkrepo()

    def w():
        with open(os.path.join(d, "README.md"), "w") as fh:
            fh.write("readme - branch change\n")
    _on_branch(d, "docs/conflict", w)
    with open(os.path.join(d, "README.md"), "w") as fh:
        fh.write("readme - trunk change\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "trunk moved (conflicting)")
    code, detail = trunk.verify_docs(d, "docs/conflict", ALLOW, "main", False, denylist=DENY)
    ok("T1 a CONFLICTED rebase still walls non-ff",
       code == "non-ff", f"{code}: {detail}")
    ok("T1 conflicted-rebase branch survives for its owner to resolve",
       trunk.branch_exists(d, "docs/conflict"))
    ok("T1 the abort leaves no mid-rebase residue",
       not os.path.exists(os.path.join(d, ".git", "rebase-merge"))
       and not os.path.exists(os.path.join(d, ".git", "rebase-apply")))


def t_lander_architect_union():
    d = _mkrepo()

    def w():
        with open(os.path.join(d, "meta", "blocks", "B-01.md"), "w") as fh:
            fh.write("# B-01 adhoc\n**Status:** 📋\n")
        with open(os.path.join(d, "meta", "pipeline.md"), "a") as fh:
            fh.write("| B-01 | adhoc | 📋 |\n")
    _on_branch(d, "chore/adhoc", w)
    allow = ALLOW + ["meta/blocks/", "meta/pipeline.md"]     # explicit union, no deny
    code, detail = trunk.verify_docs(d, "chore/adhoc", allow, "main", False)
    ok("D1 architect union verdicts 'ok' for block files + pipeline edits",
       code == "ok", f"{code}: {detail}")
    # Reviewer strictness over the same content:
    d2 = _mkrepo()

    def w2():
        with open(os.path.join(d2, "meta", "blocks", "B-01.md"), "w") as fh:
            fh.write("# B-01\n")
    _on_branch(d2, "docs/rev", w2)
    code, detail = trunk.verify_docs(d2, "docs/rev", ALLOW, "main", False, denylist=DENY)
    ok("D1 reviewer stays strict on pipeline content",
       code == "violation", f"{code}: {detail}")


# ── D1 flow: the landing points (dry engine, lander mocked) ──
def _mock_land(code, detail=""):
    orig = trunk.verify_docs
    trunk.verify_docs = lambda *a, **k: (code, detail)
    return lambda: setattr(sys.modules["trunk"], "verify_docs", orig)


def t_close_lands_first():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "close"})
    restore = _mock_land("ok", "2 file(s) @ abc1234")
    orig_rc = trunk.replica_clean
    trunk.replica_clean = lambda *a, **k: (True, "")
    try:
        eng._confirm_close("A-01", g)
        ok("D1 close lands then releases", "A-01" not in eng.st.gate
           and not any(w.get("block") == "A-01" for w in eng.st.workers),
           f"gate={eng.st.gate}")
        ok("D1 landing is a docs_landed event",
           any(e.get("type") == "docs_landed" for e in _events(eng)))
    finally:
        restore()
        trunk.replica_clean = orig_rc


def t_close_violation_parks_as_a_wall():
    # 01-15 T6: a close-time violation names REAL code the paperwork-only allowlist can
    # never accept — re-nudging toward the same confirm was a dead end with no landing
    # path at all (tron-16 CASE-003). It now parks as an ordinary wall (same case kind,
    # same three settle verbs) instead of re-nudging to a gate-close-dirty cap.
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "close"})
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    restore = _mock_land("violation", "src/sneak.txt")
    try:
        eng._confirm_close("A-01", g)
        eng._drain_triggers()             # process the queued wall:raised trigger
        ok("D1/T6 violation parks the gate (never gate-gives-up outright)",
           "A-01" in eng.st.gate and g.get("violation_pending") is True)
        ok("D1/T6 violation names the offending files in the wall detail",
           any(c.get("kind") == "wall" and "src/sneak.txt" in (c.get("detail") or "")
               for c in eng.st.pending_cases.values()), f"cases={eng.st.pending_cases}")
        ok("D1/T6 violation holds the engineer (never a silent release)",
           any(w.get("id") == "ENG-A-01" and w.get("status") == "walled"
               for w in eng.st.workers))
        # A repeat confirm while parked is a no-op — never re-escalates, never re-nudges.
        n_cases = len(eng.st.pending_cases)
        eng._confirm_close("A-01", g)
        eng._drain_triggers()
        ok("D1/T6 a repeat confirm while parked never re-escalates",
           len(eng.st.pending_cases) == n_cases)
    finally:
        restore()


def t_reviewer_declaration_fifo():
    # FS-3: blockless declaration keyed purely on the sender record; st.branches untouched.
    eng = _eng()
    eng.st.workers.append({"id": "REV-code", "role": "reviewer", "rtype": "code",
                           "block": "review:code", "session_id": "dry",
                           "status": "working"})
    eng._ingest("worker.branch", {"branch": "docs/review-1"}, {"id": "REV-code"})
    eng._ingest("worker.branch", {"branch": "docs/review-2"}, {"id": "REV-code"})
    rev = next(w for w in eng.st.workers if w.get("id") == "REV-code")
    ok("D1/FS-3 blockless declarations queue FIFO on the sender record",
       rev.get("pending_landings") == ["docs/review-1", "docs/review-2"],
       f"rev={rev}")
    ok("D1/FS-3 st.branches stays block-gate territory",
       "docs/review-1" not in (eng.st.branches or {}).values(),
       f"branches={eng.st.branches}")


def t_review_landing_holds_then_releases():
    eng = _eng()
    eng.st.workers.append({"id": "ARCH-PERSIST", "role": "architect",
                           "session_id": "dry", "status": "idle"})
    eng.st.workers.append({"id": "REV-code", "role": "reviewer", "rtype": "code",
                           "block": "review:code", "session_id": "dry",
                           "status": "working", "pending_landings": ["docs/rev"]})
    eng.st.gate["review:code"] = {"stage": "review"}
    restore = _mock_land("non-ff", "trunk moved")
    try:
        eng._h_release_reviewer({"type": "code", "block": "A-01"})   # confirmation leg
        g = eng.st.gate.get("review:code")
        ok("D1 blocked review landing holds the gate at `landing`",
           g and g.get("stage") == "landing", f"g={g}")
    finally:
        restore()
    restore = _mock_land("ok", "1 file(s) @ abc1234")
    try:
        eng._drive_review_landing("review:code", eng.st.gate["review:code"])
        ok("D1 the driver lands and releases the reviewer",
           "review:code" not in eng.st.gate
           and not any(w.get("id") == "REV-code" for w in eng.st.workers))
        arch = eng._architect()
        ok("D1 remediation still queues after a deferred landing",
           any(j.get("kind") == "log" for j in eng.st.architect_queue)
           or (arch.get("current_job") or {}).get("kind") == "log",
           f"queue={eng.st.architect_queue} job={arch.get('current_job')}")
    finally:
        restore()


def t_review_landing_cap_leaves_named_residue():
    # Rider (b)-2: cap-release residue is provably caught by the session-end sweep.
    eng = _eng()
    clock = _clocked(eng)
    eng.st.workers.append({"id": "REV-code", "role": "reviewer", "rtype": "code",
                           "block": "review:code", "session_id": "dry",
                           "status": "working", "pending_landings": ["docs/rev"]})
    eng.st.gate["review:code"] = {"stage": "landing", "block": "A-01"}
    restore = _mock_land("non-ff", "trunk moved")
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda *a, **k: True
    try:
        eng._drive_review_landing("review:code", eng.st.gate["review:code"])  # anchors
        clock["t"] += eng._pace("gate_close_cap", 3) + 1
        eng._drive_review_landing("review:code", eng.st.gate["review:code"])  # cap
        ok("D1 landing cap releases the reviewer with a named failure",
           "review:code" not in eng.st.gate
           and any(e.get("code") == "paperwork-unlandable"
                   for e in _events(eng) if e.get("kind") == "failure"))
        ok("D1 the failed branch is durable residue",
           any(f.get("branch") == "docs/rev"
               for f in eng.st.data.get("failed_landings", [])),
           f"failed={eng.st.data.get('failed_landings')}")
        eng._end_session()
        ok("D1 the session-end sweep re-names the residue",
           any(e.get("fclass") == "session-residue" and "docs/rev" in (e.get("cause") or "")
               for e in _events(eng) if e.get("kind") == "failure"))
    finally:
        restore()
        jobs.runner_idle = orig_idle


# ── W10: `branch` is a modifier, never a terminal verb ──
def _mock_classify(result_tag):
    import fsm as fsm_mod
    orig = fsm_mod.judge.call
    calls = []

    def fake(tool, payload, ctx, retries, elog=None):
        calls.append(payload)
        return True, {"tag": result_tag, "slots": {}}, []
    fsm_mod.judge.call = fake
    return calls, (lambda: setattr(fsm_mod.judge, "call", orig))


def t_branch_verb_falls_through():
    # Dual-act reply (declare + complete): the declaration records from the slot AND the
    # text still classifies — neither act is lost (the attempt-1 architect deadlock).
    eng = _eng()
    eng.st.workers.append({"id": "ARCH-PERSIST", "role": "architect",
                           "session_id": "dry", "status": "busy"})
    calls, restore = _mock_classify("architect.reconciled")
    try:
        tag, slots = eng._classify({"text": "forward review complete — 01-03 ready",
                                    "tag": "branch",
                                    "slots": {"branch": "docs/fwd-01-03"},
                                    "sender": {"kind": "worker", "id": "ARCH-PERSIST"}})
        arch = eng._architect()
        ok("W10 the declaration records from the slot",
           arch.get("pending_landings") == ["docs/fwd-01-03"], f"arch={arch}")
        ok("W10 the text still classifies (completion act survives)",
           tag == "architect.reconciled" and len(calls) == 1,
           f"tag={tag} calls={len(calls)}")
    finally:
        restore()


def t_branch_dedup_invariant():
    # Peer rider: dedup is THE load-bearing invariant — hoist-record + classify re-yield
    # + a verbatim repeat must produce exactly ONE FIFO entry.
    eng = _eng()
    eng.st.workers.append({"id": "REV-code", "role": "reviewer", "rtype": "code",
                           "block": "review:code", "session_id": "dry",
                           "status": "working"})
    calls, restore = _mock_classify("worker.branch")
    try:
        m = {"text": "parked my findings on docs/rev-1", "tag": "branch",
             "slots": {"branch": "docs/rev-1"},
             "sender": {"kind": "worker", "id": "REV-code"}}
        for _ in range(2):                                # verbatim repeat
            tag, slots = eng._classify(m)
            eng._ingest(tag, slots, m["sender"])          # classify re-yields worker.branch
        rev = next(w for w in eng.st.workers if w.get("id") == "REV-code")
        ok("W10 hoist + classify + repeat -> exactly one FIFO entry",
           rev.get("pending_landings") == ["docs/rev-1"], f"rev={rev}")
    finally:
        restore()


def t_slot_merge_data_over_prose():
    # Peer required change: structured slots survive INTO the classify result — a terse
    # declaration whose prose classify can't parse still carries its branch as data.
    eng = _eng()
    eng.st.workers.append({"id": "REV-code", "role": "reviewer", "rtype": "code",
                           "block": "review:code", "session_id": "dry",
                           "status": "working"})
    calls, restore = _mock_classify("worker.progress")    # model sees nothing useful
    try:
        tag, slots = eng._classify({"text": "^", "tag": "branch",
                                    "slots": {"branch": "docs/terse"},
                                    "sender": {"kind": "worker", "id": "REV-code"}})
        rev = next(w for w in eng.st.workers if w.get("id") == "REV-code")
        ok("W10 terse declaration records via the hoist regardless of classify",
           rev.get("pending_landings") == ["docs/terse"], f"rev={rev}")
        ok("W10 structured slots merge over the model's slots",
           slots.get("branch") == "docs/terse", f"slots={slots}")
    finally:
        restore()


def t_branch_verb_without_slot_never_silent():
    eng = _eng()
    eng.st.workers.append({"id": "ARCH-PERSIST", "role": "architect",
                           "session_id": "dry", "status": "busy"})
    calls, restore = _mock_classify("worker.progress")
    try:
        tag, _ = eng._classify({"text": "made a branch, named it in prose only",
                                "tag": "branch",
                                "sender": {"kind": "worker", "id": "ARCH-PERSIST"}})
        ok("W10 missing --branch records nothing but still classifies",
           not eng._architect().get("pending_landings") and len(calls) == 1
           and tag == "worker.progress", f"tag={tag}")
    finally:
        restore()


def t_branch_verb_engineer_keeps_admit_path():
    # 01-13 (tron-14 F6) REVERSES the old deferral: a structured report never reaches
    # classify, so "the classify path owns engineer declarations" meant a structured
    # `done --branch X` never registered at all (three declarations, branches: {}, gate
    # walled). The hoist now carries the SENDER'S assigned block (A-1 sender-first) and
    # the declaration registers directly — never to the paperwork FIFO.
    eng = _eng()
    calls, restore = _mock_classify("worker.branch")
    try:
        eng._classify({"text": "branch named", "tag": "branch",
                       "slots": {"branch": "fix/own-name"},
                       "sender": {"kind": "worker", "id": "ENG-A-01"}})
        ok("F6 an engineer's structured declaration registers sender-first",
           (eng.st.branches or {}).get("A-01") == "fix/own-name"
           and not any(w.get("pending_landings") for w in eng.st.workers),
           f"branches={eng.st.branches}")
    finally:
        restore()


def t_worktree_residue_named():
    d = _mkrepo()
    _git(d, "worktree", "add", os.path.join(d, "worktrees", "wt-a"), "-b", "docs/wt-a")
    trees = trunk.list_worktrees(d)
    ok("W10 leftover worktrees are enumerable",
       len(trees) == 1 and trees[0][1] == "docs/wt-a", f"trees={trees}")


def t_lander_deletes_already_merged_branch():
    # T3 (01-32, ADR-0002 D1): re-scoped — verify_docs never deletes anything any
    # more (branch cleanup is the WORKER's close ritual; stragglers are a hygiene
    # note, never an engine `branch -d`). What survives of W10: an already-merged
    # (empty-diff) declaration is a clean no-op verdict ("none"), never a violation
    # or a spurious non-ff — so the caller's FIFO pops it and moves on.
    d = _mkrepo()

    def w():
        with open(os.path.join(d, "meta", "logs", "log.md"), "w") as fh:
            fh.write("log\n")
    _on_branch(d, "docs/dup", w)
    code, _ = trunk.verify_docs(d, "docs/dup", ALLOW, "main", False, denylist=DENY)
    ok("W10 a clean paperwork branch verdicts 'ok' (landable)", code == "ok")
    # Land it for real the way the protocol now lands things: simulate land.sh's ff
    # advance, then re-declare the same (now fully-merged) ref.
    tip = _git(d, "rev-parse", "docs/dup")[1]
    old = _git(d, "rev-parse", "main")[1]
    _git(d, "update-ref", "refs/heads/main", tip, old)
    code, detail = trunk.verify_docs(d, "docs/dup", ALLOW, "main", False, denylist=DENY)
    ok("W10 an already-merged declaration is a clean 'none' no-op (never deleted by "
       "the engine — the worker's own close ritual owns cleanup now)",
       code == "none" and trunk.branch_exists(d, "docs/dup"),
       f"{code}: {detail}")


# ── W11: st.branches is owner-only ──
def t_branch_registry_owner_only():
    # The attempt-1 poisoning: an architect report naming a block in prose must NEVER
    # register its paperwork branch as the block's branch.
    eng = _eng()
    eng.st.workers.append({"id": "ARCH-PERSIST", "role": "architect",
                           "session_id": "dry", "status": "busy"})
    eng._ingest("worker.branch", {"block": "A-01", "branch": "docs/fwd-review"},
                {"id": "ARCH-PERSIST"})
    arch = eng._architect()
    ok("W11 a non-owner's block ref never claims the block",
       "A-01" not in (eng.st.branches or {}), f"branches={eng.st.branches}")
    ok("W11 the non-owner's branch routes to its paperwork FIFO",
       arch.get("pending_landings") == ["docs/fwd-review"], f"arch={arch}")
    # The assigned engineer still owns its registration.
    eng._ingest("worker.branch", {"block": "A-01", "branch": "fix/real-work"},
                {"id": "ENG-A-01"})
    ok("W11 the assigned engineer's declaration records",
       eng.st.branches.get("A-01") == "fix/real-work", f"branches={eng.st.branches}")
    # An engineer naming a block that isn't its assignment is refused outright.
    eng.st.workers.append({"id": "ENG-B-02", "role": "engineer", "block": "B-02",
                           "session_id": "dry", "status": "working"})
    eng._ingest("worker.branch", {"block": "A-01", "branch": "feat/hijack"},
                {"id": "ENG-B-02"})
    ok("W11 a foreign engineer's claim is refused",
       eng.st.branches.get("A-01") == "fix/real-work", f"branches={eng.st.branches}")
    # Rider 1: owner is role AND assignment — an architect whose record happens to carry
    # a block field must not satisfy a naive assignment match.
    eng2 = _eng()
    eng2.st.workers.append({"id": "ARCH-PERSIST", "role": "architect", "block": "A-01",
                            "session_id": "dry", "status": "busy"})
    eng2._ingest("worker.branch", {"block": "A-01", "branch": "docs/arch-claim"},
                 {"id": "ARCH-PERSIST"})
    ok("W11 role gates ownership, not just the assignment field",
       "A-01" not in (eng2.st.branches or {})
       and eng2._architect().get("pending_landings") == ["docs/arch-claim"],
       f"branches={eng2.st.branches} arch={eng2._architect()}")


# ── W12: a missing branch gets named, never "validate again" ──
def _capture_to_worker(eng):
    sent = []
    eng._to_worker = (lambda wid, text, kind: sent.append((wid, kind, text)))
    return sent


def t_branch_gap_names_the_gap():
    eng = _eng()
    eng.dry = False                                       # _to_worker path (captured)
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    direct = _capture_to_worker(eng)
    sent = _capture(eng)
    clock = _clocked(eng)                                 # BEFORE any idle anchor
    orig_idle0 = jobs.runner_idle
    jobs.runner_idle = lambda *a, **k: True
    orig_be = trunk.branch_exists
    trunk.branch_exists = lambda *a, **k: False
    orig_lm = eng._local_mode
    eng._local_mode = lambda: True
    try:
        eng._drive_gate("A-01", g, on_report=True)        # done, but no visible branch
        ok("W12 done-with-no-branch asks for the declaration",
           any(k == "gate.branch-gap" and "--branch" in t for _, k, t in direct),
           f"direct={direct}")
        ok("W12 no gate.local re-order on the gap",
           not any(t == "gate.local" for t, _ in sent), f"sent={sent}")
        ok("W12 the gap is flagged for the nudge machinery",
           g.get("branch_gap") is True and g.get("stage") == "local", f"g={g}")
        # The idle re-nudge repeats the branch-gap line, not the validation order.
        eng._drive_gate("A-01", g)                        # anchors idle
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._drive_gate("A-01", g)                        # nudge fires
        ok("W12 the idle nudge repeats the gap line",
           sum(1 for _, k, _t in direct if k == "gate.branch-gap") == 2
           and not any(t == "gate.local" for t, _ in sent), f"direct={direct}")
        # Rider 2a: still no branch -> the idle cap stays the backstop.
        clock["t"] += eng._pace("gate_idle_cap", 3) + 1
        eng._drive_gate("A-01", g)
        ok("W12 repeated bare done still walls at the cap",
           "A-01" not in eng.st.gate, f"gate={eng.st.gate}")
    finally:
        jobs.runner_idle = orig_idle0
        trunk.branch_exists = orig_be
        eng._local_mode = orig_lm


def t_branch_gap_compliant_rereport_recovers():
    # Rider 2b: the one-message remedy — a done re-report WITH the branch visible
    # clears the flag and the gate proceeds (here: to the ASK park).
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                        "branch_gap": True})
    eng.st.approvals["merge"] = "ASK"
    eng.st.branches["A-01"] = "fix/named-late"
    orig_be, orig_ts = trunk.branch_exists, trunk.tip_sha
    trunk.branch_exists = lambda *a, **k: True
    trunk.tip_sha = lambda *a, **k: "abc1234"
    orig_lm = eng._local_mode
    eng._local_mode = lambda: True
    try:
        eng._drive_gate("A-01", g, on_report=True)
        ok("W12 a compliant re-report clears the gap and proceeds",
           "branch_gap" not in g and g.get("case_merge"), f"g={g}")
    finally:
        trunk.branch_exists, trunk.tip_sha = orig_be, orig_ts
        eng._local_mode = orig_lm


# ── W9: trunk truth is the PINNED COMMITTED tree, never the working tree ──
def t_snapshot_reads_pinned_tree():
    d = _mkrepo()
    rc, sha = _git(d, "rev-parse", "HEAD")
    # A worker mid-record-commit: the working tree says ✅, the committed tree says 📋.
    with open(os.path.join(d, "meta", "blocks", "A-01.md"), "w") as fh:
        fh.write("# A-01\n**Status:** 📋 To do — DIRTY WORKING TREE EDIT\n")
    snap = os.path.join(d, ".trunk-snapshot")
    okc, err = trunk.snapshot_tree(d, sha, ["meta/pipeline.md", "meta/blocks"], snap)
    ok("W9 snapshot extracts the pinned tree", okc, err)
    with open(os.path.join(snap, "meta", "blocks", "A-01.md")) as fh:
        content = fh.read()
    ok("W9 the snapshot is COMMITTED truth (dirty edit invisible)",
       "DIRTY WORKING TREE EDIT" not in content, content[:80])
    ok("W9 pipeline rides along", os.path.exists(os.path.join(snap, "meta", "pipeline.md")))
    # The commit lands -> the NEXT pinned sha sees it. Same mechanism, no special case.
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "record: A-01 -> done")
    rc, sha2 = _git(d, "rev-parse", "HEAD")
    okc, err = trunk.snapshot_tree(d, sha2, ["meta/pipeline.md", "meta/blocks"], snap)
    with open(os.path.join(snap, "meta", "blocks", "A-01.md")) as fh:
        content = fh.read()
    ok("W9 the landed commit is visible at the new pin",
       okc and "DIRTY WORKING TREE EDIT" in content, f"{err} {content[:60]}")
    # Rider 1: a failed archive (bad sha) leaves the last good snapshot untouched.
    okc, err = trunk.snapshot_tree(d, "0000000", ["meta/pipeline.md", "meta/blocks"], snap)
    ok("W9 a failed archive never wipes the live snapshot",
       not okc and os.path.exists(os.path.join(snap, "meta", "pipeline.md")),
       f"okc={okc}")


def t_release_preserves_unlanded_paperwork():
    # Delta-review required fix: ANY release path (stall-recover included) preserves a
    # worker's unlanded declarations as durable residue — the roster is gone, the cap
    # never fired, and st.branches is engineer-only; without this the lost-output defect
    # D1 kills returns through the release side door.
    eng = _eng()
    w = {"id": "REV-code", "role": "reviewer", "rtype": "code", "block": "review:code",
         "session_id": "dry", "status": "working", "pending_landings": ["docs/orphan"]}
    eng.st.workers.append(w)
    eng._release_worker(w, notify=False, reason="stall-recover")
    ok("D1 release preserves unlanded paperwork as residue",
       any(f.get("branch") == "docs/orphan" and "stall-recover" in f.get("detail", "")
           for f in eng.st.data.get("failed_landings", [])),
       f"failed={eng.st.data.get('failed_landings')}")
    eng._end_session()
    ok("D1 released-worker residue reaches the session-end sweep",
       any(e.get("fclass") == "session-residue" and "docs/orphan" in (e.get("cause") or "")
           for e in _events(eng) if e.get("kind") == "failure"))


def t_architect_fifo_never_deadlocks():
    # FS-1: a blocked head caps aside as residue; the queue keeps draining.
    eng = _eng()
    clock = _clocked(eng)
    eng.st.workers.append({"id": "ARCH-PERSIST", "role": "architect",
                           "session_id": "dry", "status": "idle",
                           "pending_landings": ["docs/j1", "docs/j2"]})
    restore = _mock_land("violation", "meta-oops")
    try:
        eng._drive_landings()                                 # anchors + nudge
        clock["t"] += eng._pace("gate_close_cap", 3) + 1
        eng._drive_landings()                                 # cap -> j1 aside
        arch = eng._architect()
        ok("D1/FS-1 capped head moves aside as residue",
           any(f.get("branch") == "docs/j1"
               for f in eng.st.data.get("failed_landings", []))
           and arch.get("pending_landings") == ["docs/j2"],
           f"arch={arch} failed={eng.st.data.get('failed_landings')}")
    finally:
        restore()
    restore = _mock_land("ok", "ok")
    try:
        eng._drive_landings()
        ok("D1/FS-1 the queue keeps draining after the cap",
           eng._architect().get("pending_landings") == [],
           f"arch={eng._architect()}")
    finally:
        restore()


TESTS = [
    t_ratchet_floor_paperwork_commits,
    t_ratchet_record_holds,
    t_ratchet_ancestry_contradiction,
    t_ratchet_pr_reopened_contradiction,
    t_ratchet_no_sha_holds_quietly,
    t_merge_anchors_sha,
    t_case_reping_ladder,
    t_case_park_is_resumable,
    t_case_visibility,
    t_structured_bypasses_classify,
    t_structured_unknown_verb_drops,
    t_structured_clean_confirms_at_close,
    t_structured_review_type_from_sender,
    t_admission_is_declarative,
    t_lander_lands_paperwork,
    t_lander_code_violation,
    t_lander_own_block_exceptions,
    t_lander_foreign_pipeline_line,
    t_lander_nonff_rebases_and_lands,
    t_lander_nonff_conflict_still_walls,
    t_lander_architect_union,
    t_close_lands_first,
    t_close_violation_parks_as_a_wall,
    t_reviewer_declaration_fifo,
    t_review_landing_holds_then_releases,
    t_review_landing_cap_leaves_named_residue,
    t_release_preserves_unlanded_paperwork,
    t_architect_fifo_never_deadlocks,
    t_snapshot_reads_pinned_tree,
    t_branch_verb_falls_through,
    t_branch_dedup_invariant,
    t_slot_merge_data_over_prose,
    t_branch_verb_without_slot_never_silent,
    t_branch_verb_engineer_keeps_admit_path,
    t_worktree_residue_named,
    t_lander_deletes_already_merged_branch,
    t_branch_registry_owner_only,
    t_branch_gap_names_the_gap,
    t_branch_gap_compliant_rereport_recovers,
]


def main():
    for t in TESTS:
        t()
    failed = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS " if c else "FAIL ") + n + (f"  [{d}]" if (d and not c) else ""))
    print(f"{len(_results) - len(failed)}/{len(_results)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
