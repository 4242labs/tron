"""tron13_test — regressions for the tron-13 pre-sim implementation set (the co-signed
design of record: tron-meta logs/engineer/260702-tron-13-design.md).

  D3/A-5  full ladder ratchet — trunk AND record are a monotonic hold zone; the held
          rung re-verifies its OWN predicate (merged sha ancestry / merged PR staying
          closed) and a contradicted predicate is a NAMED gate-contradiction escalation,
          never a silent recompute and never a "worker stall" misread.

Run: python3 engine/tron13_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys

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
    eng2 = _eng()
    got = eng2._admit("worker.wall", {"block": "A-01", "_raw": "walled: npm broken"},
                      {"kind": "worker", "id": "ENG-A-01"})
    ok("S-2 a pre-gate wall still fires (block means canon row, not open gate)",
       got is not None, f"got={got}")


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
