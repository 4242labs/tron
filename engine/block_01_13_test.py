"""block_01_13_test — regressions for the 01-13 protocol-consolidation set (tron-14 F1-F11).

The tron-14 run proved the engine's vocabulary had one first-class citizen (the block-gated
engineer) and two bolted-on ones: 7 of its 11 failures were the architect's and reviewer's
protocol acts refused at the block-admission wall or stalling with no clock watching.

  T1  sender-truth resolution (F1/F4/F8/F10): an architect/reviewer 'done' resolves off the
      SENDER'S engine-side state (current_job / rtype), never prose block refs.
  T2  refusal bounce: a refused or unreadable report is never a silent discard — the sender
      is told why and how to re-send (rate-limited).
  T3  liveness parity (F2/F4/F9): the architect job queue and the review attest stage get
      the same wall-clock idle law as every block gate.
  T4  spawn hygiene (F7): a re-spawn never inherits a predecessor's worker dir/mailbox.
  T5  branch registration (F6): an engineer's hoisted --branch carries its assigned block.
      (Asserted in tron13_test's updated F6 case; the structured-done path re-checked here.)
  T7  residue sweep (F11): the main worktree is excluded by position, not only by path.

Run: python3 engine/block_01_13_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import json
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import util             # noqa: E402
import jobs             # noqa: E402
import trunk            # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _events(eng):
    return util.read_jsonl(eng.ctx.event_log)


def _eng(blocks=None):
    ctx, repo = build(blocks=blocks)
    eng = Engine(ctx)
    started(eng)
    return eng


def _arch(eng, job=None, status=None):
    w = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
         "status": status or ("busy" if job else "idle"), "current_job": job, "block": None}
    eng.st.workers.append(w)
    return w


def _reviewer(eng, typ="code"):
    w = {"id": f"REV-{typ}", "role": "reviewer", "rtype": typ, "session_id": "dry",
         "status": "working", "block": f"review:{typ}"}
    eng.st.workers.append(w)
    return w


def _engineer(eng, block="A-01"):
    w = {"id": f"ENG-{block}", "role": "engineer", "block": block,
         "session_id": "dry", "status": "working"}
    eng.st.workers.append(w)
    return w


def _capture_emit(eng):
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
                sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


def _capture_to_worker(eng):
    sent = []
    eng._to_worker = lambda wid, text, kind: sent.append((wid, text, kind))
    return sent


def _drain(eng):
    eng._drain_triggers()


# ── T1: sender-truth resolution ──
def t_arch_done_completes_reconcile():
    # tron-14 F1: the architect's reconcile done-report classified `worker.done` with no
    # block ref -> refused ('unknown block id') -> job busy-held 34 min. Now: its own
    # current_job names the only thing 'done' can mean.
    eng = _eng()
    a = _arch(eng, {"kind": "reconcile", "block": "A-02", "after": "A-01"})
    eng._ingest("worker.done", {"_raw": "reconcile complete"},
                {"kind": "worker", "id": "ARCH-PERSIST"})
    _drain(eng)
    ok("T1 arch done on reconcile -> block recorded reconciled",
       "A-02" in eng.st.reconciled, f"reconciled={eng.st.reconciled}")
    ok("T1 arch done on reconcile -> job advanced (idle)",
       a.get("status") == "idle" and a.get("current_job") is None,
       f"status={a.get('status')}")
    ok("T1 arch done -> no unclassified refusal recorded",
       not any(e.get("kind") == "unclassified" for e in _events(eng)))


def t_arch_done_completes_log():
    # tron-14 F4/F10: the remediation/triage log-review done-report, same refusal class.
    eng = _eng()
    a = _arch(eng, {"kind": "log", "type": "code", "block": "A-01"})
    eng._ingest("worker.done", {"_raw": "log review done, one adhoc scoped"},
                {"kind": "worker", "id": "ARCH-PERSIST"})
    _drain(eng)
    ok("T1 arch done on log-review -> job advanced",
       a.get("status") == "idle" and a.get("current_job") is None,
       f"status={a.get('status')}")


def t_arch_done_completes_triage_as_relay():
    # A triage job's 'done' IS the answer: relay to the original asker + advance.
    eng = _eng()
    a = _arch(eng, {"kind": "triage", "detail": "which port?", "sender": "ENG-A-01"})
    _engineer(eng)
    tw = _capture_to_worker(eng)
    eng.dry = False                     # _relay_architect_answer sends only when not dry
    try:
        eng._ingest("worker.done", {"_raw": "use the assigned port from the map"},
                    {"kind": "worker", "id": "ARCH-PERSIST"})
        _drain(eng)
    finally:
        eng.dry = True
    ok("T1 arch done on triage -> answer relayed to the asker",
       any(w == "ENG-A-01" and "port" in t for w, t, k in tw), f"sent={tw}")
    ok("T1 arch done on triage -> job advanced",
       a.get("status") == "idle" and a.get("current_job") is None)


def t_arch_residue_line_noted_not_refused():
    # tron-14 F3's class: a post-completion line from an idle architect is a receipt to
    # note — never a refusal, never a bounce, never a stall.
    eng = _eng()
    _arch(eng, None, status="idle")
    before = len(_events(eng))
    tw = _capture_to_worker(eng)
    eng._ingest("worker.done", {"_raw": "as reported earlier, all findings survived"},
                {"kind": "worker", "id": "ARCH-PERSIST"})
    _drain(eng)
    ok("T1 idle-arch residue line -> noted, no events, no bounce",
       len(_events(eng)) == before and not tw, f"events+={len(_events(eng)) - before}")


def t_reviewer_done_is_review_done():
    # tron-14 F8: a reviewer's 'done' hit the block wall ('unknown block id: review:code').
    # Sender-truth: a reviewer's done can only mean its review.
    eng = _eng()
    _reviewer(eng, "code")
    eng._ingest("worker.done", {"_raw": "review delivered", "block": "review:code"},
                {"kind": "worker", "id": "REV-code"})
    _drain(eng)
    g = eng.st.gate.get("review:code")
    ok("T1 reviewer done -> DONE-REVIEW gate opens (attest)",
       g is not None and g.get("stage") == "review", f"gate={g}")
    ok("T1 reviewer done -> no unclassified refusal",
       not any(e.get("kind") == "unclassified" for e in _events(eng)))


# ── T2: refusal bounce ──
def t_bounce_on_unknown_verb_and_rate_limit():
    eng = _eng()
    _engineer(eng)
    tw = _capture_to_worker(eng)
    eng._now_s = lambda: 1000.0
    tag, _ = eng._structured({"tag": "frobnicate", "text": "??",
                              "sender": {"kind": "worker", "id": "ENG-A-01"}})
    ok("T2 unknown verb -> dropped + bounced",
       tag == "drop" and len(tw) == 1 and tw[0][2] == "report.bounce", f"sent={tw}")
    eng._structured({"tag": "frobnicate", "text": "??",
                     "sender": {"kind": "worker", "id": "ENG-A-01"}})
    ok("T2 bounce rate-limited within the ceiling span", len(tw) == 1)
    eng._now_s = lambda: 1040.0
    eng._structured({"tag": "frobnicate", "text": "??",
                     "sender": {"kind": "worker", "id": "ENG-A-01"}})
    ok("T2 bounce re-arms after the ceiling span", len(tw) == 2)


def t_bounce_on_unknown_block():
    # A live sender whose gate-facing report resolves to no canon block hears WHY —
    # the mechanized form of tron-14's manual operator re-deliveries.
    eng = _eng()
    _reviewer(eng, "code")
    tw = _capture_to_worker(eng)
    eng._ingest("worker.wall", {"block": "ZZZ", "detail": "stuck"},
                {"kind": "worker", "id": "REV-code"})
    _drain(eng)
    ok("T2 unknown-block refusal bounces to the sender",
       any(k == "report.bounce" for _, _, k in tw), f"sent={tw}")
    ok("T2 refusal still forensically recorded",
       any(e.get("kind") == "unclassified" for e in _events(eng)))


def t_bounce_never_reaches_off_roster():
    eng = _eng()
    tw = _capture_to_worker(eng)
    eng._bounce({"kind": "worker", "id": "GHOST-9"}, "whatever")
    ok("T2 off-roster sender never bounced", not tw)


# ── T3: liveness parity ──
def t_arch_liveness_nudge_then_case():
    eng = _eng()
    a = _arch(eng, {"kind": "reconcile", "block": "A-02", "after": "A-01"})
    sent = _capture_emit(eng)
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda wid, idx=None: True
    try:
        eng._now_s = lambda: 1000.0
        eng._drive_architect_liveness()      # anchors idle_since
        ok("T3 arch idle anchor set", a.get("job_idle_since") == 1000.0)
        eng._now_s = lambda: 1065.0          # past nudge (2 x 30s)
        eng._drive_architect_liveness()
        ok("T3 arch idle past nudge -> job order re-delivered",
           any(t == "arch.reconcile" for t, _ in sent), f"sent={sent}")
        eng._now_s = lambda: 1095.0          # past cap (3 x 30s)
        eng._drive_architect_liveness()
        ok("T3 arch idle past cap -> parked case",
           a.get("job_case") in eng.st.pending_cases
           and any(t == "escalate.wall" for t, _ in sent), f"case={a.get('job_case')}")
        cid = a.get("job_case")
        eng._architect_advance()
        ok("T3 completion settles the parked architect case",
           cid not in eng.st.pending_cases and not a.get("job_case")
           and not a.get("job_idle_since"))
    finally:
        jobs.runner_idle = orig_idle


def t_arch_liveness_working_never_accrues():
    eng = _eng()
    a = _arch(eng, {"kind": "log", "type": "code"})
    a["job_idle_since"] = 1.0
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda wid, idx=None: False
    try:
        eng._now_s = lambda: 99999.0
        eng._drive_architect_liveness()
        ok("T3 working architect never accrues idle",
           not a.get("job_idle_since") and not a.get("job_case"))
    finally:
        jobs.runner_idle = orig_idle


def t_review_attest_nudge_case_and_settle():
    # tron-14 F9: the attest stage had no clock — a lost hand-back stalled it silently.
    eng = _eng()
    _reviewer(eng, "code")
    eng.st.gate["review:code"] = {"stage": "review"}
    sent = _capture_emit(eng)
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda wid, idx=None: True
    try:
        eng._now_s = lambda: 1000.0
        eng._drive_gates()
        eng._now_s = lambda: 1065.0
        eng._drive_gates()
        ok("T3 attest idle past nudge -> gate.review re-sent",
           any(t == "gate.review" for t, _ in sent), f"sent={sent}")
        eng._now_s = lambda: 1095.0
        eng._drive_gates()
        g = eng.st.gate.get("review:code")
        cid = (g or {}).get("attest_case")
        ok("T3 attest idle past cap -> parked case, gate held",
           cid in eng.st.pending_cases and g.get("stage") == "review", f"gate={g}")
        n_wall = sum(1 for t, _ in sent if t == "escalate.wall")
        eng._now_s = lambda: 2000.0
        eng._drive_gates()
        ok("T3 parked attest holds quietly (no re-escalation from this driver)",
           sum(1 for t, _ in sent if t == "escalate.wall") == n_wall)
        # The confirmation lands (operator re-delivered / reviewer re-sent) -> settles.
        eng._h_release_reviewer({"type": "code"})
        ok("T3 attest confirmation settles the case and finishes the review",
           cid not in eng.st.pending_cases and "review:code" not in eng.st.gate)
    finally:
        jobs.runner_idle = orig_idle


# ── T4: spawn hygiene ──
def t_retire_stale_dir():
    root = tempfile.mkdtemp(prefix="tron-0113-")
    wdir = os.path.join(root, "workers", "REV-code")
    os.makedirs(wdir)
    with open(os.path.join(wdir, jobs.RUNNER_STATE), "w") as fh:
        json.dump({"worker_id": "REV-code", "pid": None, "state": "idle", "turns": 7}, fh)
    with open(os.path.join(wdir, jobs.MAILBOX), "a") as fh:
        for i in range(1, 5):
            fh.write(json.dumps({"seq": i, "kind": "x", "text": "old"}) + "\n")
    with open(os.path.join(wdir, jobs.HWM), "w") as fh:
        fh.write("4")
    dest = jobs.retire_stale_dir(wdir)
    ok("T4 stale dir retired whole (F7: hwm can never outrun a fresh spawn)",
       dest and not os.path.exists(wdir) and os.path.isfile(
           os.path.join(dest, jobs.HWM)), f"dest={dest}")
    ok("T4 archive lives under workers/.archive",
       dest and os.path.dirname(dest).endswith(".archive"))
    ok("T4 retiring a virgin dir is a no-op",
       jobs.retire_stale_dir(os.path.join(root, "workers", "ENG-x")) is None)


# ── T5: engineer branch registration on the structured path (F6) ──
def t_structured_done_with_branch_registers():
    eng = _eng()
    _engineer(eng, "A-01")
    tag, slots = eng._classify({"text": "done A-01 — local: all green",
                                "tag": "done",
                                "slots": {"branch": "feat/custom-name"},
                                "sender": {"kind": "worker", "id": "ENG-A-01"}})
    ok("F6 structured done --branch registers the engineer's branch",
       eng.st.branches.get("A-01") == "feat/custom-name"
       and tag == "worker.done", f"branches={eng.st.branches} tag={tag}")


# ── T7: residue sweep excludes the main worktree by position (F11) ──
def t_list_worktrees_skips_main_first():
    orig = trunk._run
    porcelain = ("worktree /aliased/path/to/replica\n"
                 "branch refs/heads/main\n"
                 "\n"
                 "worktree /aliased/path/to/replica/worktrees/feat-x\n"
                 "branch refs/heads/feat/x\n")
    trunk._run = lambda cmd, **k: (0, porcelain, "")
    try:
        got = trunk.list_worktrees("/actual/mount/replica")   # path git can't be matched to
        ok("F11 main worktree excluded by position even when paths alias",
           got == [("/aliased/path/to/replica/worktrees/feat-x", "feat/x")], f"got={got}")
    finally:
        trunk._run = orig


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
