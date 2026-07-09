"""block_01_20_test — engine-truth completion, required-tip landing, runtime-failure
recovery (tron-27/28 pair findings). Standalone runner convention (exit 0 = pass, no
tokens, no network — a tiny local echo script stands in for the host CLI in T3(a)).

Covers AC-1's adversarial case per mechanism:
  T1  a landing correlated to the live architect job completes it via the EXISTING
      _h_reconcile (never a second writer of completion state); multi-batch landings
      never double-complete; a log-job's landing never completes anything (no block);
      an uncorrelated/residue landing (or a non-architect role's landing) is inert; a
      no-op reconcile (idle architect) is never completed by any landing; the parked
      architect case auto-closes the instant the job completes.
  T2  a code-bearing descendant tip re-drives the merge through the ordinary ask gate
      (a fresh `merge`-kind case, never a new one); a paperwork-only descendant keeps
      landing via the paperwork lane (no re-drive); a non-descendant (divergent history)
      never re-drives; the patch-identity discipline carries a grant across a further
      moved tip and voids/re-parks on a genuine divergence; every other shape holds the
      ratchet exactly as before.
  T3  (a) the adapter records subtype/is_error into the timeline instead of discarding
      them, and raises on is_error, a non-'success' subtype, or a known host-CLI refusal
      SHAPE (quota/limit wording) even when it arrives dressed as an ordinary success —
      the exception CLASS (never its text) is what the engine reads structurally.
      (b) repeated fleet-wide refusal-caused deaths hold dispatch, probe with a single
      canary re-spawn on the existing sweep cadence, and resume on its first healthy
      turn; held blocks never wall and never mutate their gate.
  T4  approve/resume re-arm the ladder and re-deliver the SAME order once; abandon
      retires the job WITHOUT recording it reconciled; a settle for a job that already
      advanced (T1/T5 won the race) closes the case only — no re-delivery.
  T5  the architect's own `--tag review-done` resolves by sender truth exactly like
      done/recorded for a live forward/reconcile job; a reviewer's review-done (or plain
      done) is unaffected; a log-job's review-done stays out of this widening's scope.
  T6  (a) `_bounce` caps at 2 per architect job, then opens the ordinary idle-cap case
      (never a new escalation kind) instead of a 3rd bounce; a non-architect sender is
      never capped (`_bounce` itself stays role-agnostic). (b) an engine-initiated wake
      (bounce/nudge/re-delivery) never resets the idle anchor; a genuinely busy runner
      still never accrues idle time (A-4, block_01_13's pinned invariant, unbroken).

Run: python3 engine/block_01_20_test.py   (exit 0 = pass).
"""
import os
import sys
import json
import stat
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"
os.environ.setdefault("TRON_WORKER_PERMS", "")
os.environ.setdefault("TRON_RUNNER_POLL_S", "0.05")

import jobs                    # noqa: E402
import trunk                   # noqa: E402
import worker_runner           # noqa: E402
from fsm import Engine         # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── fixture builders (block_01_19_test convention) ──
def _eng(block="A-01", status="🔄"):
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _arch(eng, job=None, status=None, pending_landings=None):
    w = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
         "status": status or ("busy" if job else "idle"), "current_job": job, "block": None}
    if pending_landings is not None:
        w["pending_landings"] = list(pending_landings)
    eng.st.workers.append(w)
    return w


def _capture(eng):
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
                sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


def _capture_to_worker(eng):
    sent = []
    orig = eng._to_worker

    def spy(wid, text, kind):
        sent.append((wid, text, kind))
        return orig(wid, text, kind)
    eng._to_worker = spy
    return sent


def _capture_reconcile(eng):
    calls = []
    orig = eng._h_reconcile
    eng._h_reconcile = lambda m: calls.append(dict(m)) or orig(m)
    return calls


# ══ T1: a correlated landing completes the live architect job (accelerator) ══

def _stub_landing(land_result=("ok", "clean"), touches=True):
    orig = (trunk.verify_docs, trunk.branch_touches_path)
    trunk.verify_docs = lambda *a, **k: land_result
    trunk.branch_touches_path = lambda *a, **k: touches
    return orig


def _restore_landing(orig):
    trunk.verify_docs, trunk.branch_touches_path = orig


def t1_correlated_landing_completes_via_h_reconcile():
    eng = _eng()
    arch = _arch(eng, job={"kind": "reconcile", "block": "A-01", "after": ""},
                 pending_landings=["arch/scope-A-01"])
    calls = _capture_reconcile(eng)
    orig = _stub_landing(("ok", "1 file(s) clean"), touches=True)
    try:
        eng._drive_landings()
    finally:
        _restore_landing(orig)
    ok("T1 a correlated landing completes the job via the EXISTING _h_reconcile handler",
       len(calls) == 1 and calls[0].get("block") == "A-01", f"calls={calls}")
    ok("T1 the block lands in st.reconciled (the SAME write _h_reconcile always performs)",
       "A-01" in eng.st.reconciled, f"reconciled={eng.st.reconciled}")
    ok("T1 the architect's job cleared (one outcome, one handler)",
       arch.get("current_job") is None and arch.get("status") == "idle", f"arch={arch}")


def t1_multi_batch_landing_never_double_completes():
    eng = _eng()
    arch = _arch(eng, job={"kind": "reconcile", "block": "A-01"},
                 pending_landings=["b1", "b2"])
    calls = _capture_reconcile(eng)
    # Both branches would correlate if checked — proves only the FIRST one (while the
    # job is still live) ever completes anything.
    orig = _stub_landing(("ok", "clean"), touches=True)
    try:
        eng._drive_landings()
    finally:
        _restore_landing(orig)
    ok("T1 multi-batch: exactly ONE completion though every landing would correlate",
       len(calls) == 1, f"calls={calls}")
    ok("T1 multi-batch: the whole FIFO still drains (both branches landed)",
       arch.get("pending_landings") == [], f"arch={arch}")


def t1_log_job_landing_never_completes():
    eng = _eng()
    arch = _arch(eng, job={"kind": "log", "type": "code"}, pending_landings=["logbranch"])
    calls = _capture_reconcile(eng)
    orig = _stub_landing(("ok", "clean"), touches=True)
    try:
        eng._drive_landings()
    finally:
        _restore_landing(orig)
    ok("T1 a log-job's landing never completes anything (no block on the job)",
       not calls, f"calls={calls}")
    ok("T1 the log job stays live, untouched by the landing",
       arch.get("current_job") == {"kind": "log", "type": "code"}, f"arch={arch}")


def t1_uncorrelated_landing_is_inert():
    eng = _eng()
    arch = _arch(eng, job={"kind": "reconcile", "block": "A-01"},
                 pending_landings=["unrelated-branch"])
    calls = _capture_reconcile(eng)
    orig = _stub_landing(("ok", "clean"), touches=False)   # never touches A-01's file
    try:
        eng._drive_landings()
    finally:
        _restore_landing(orig)
    ok("T1 a landing that correlates to no live job changes nothing",
       not calls and arch.get("current_job") == {"kind": "reconcile", "block": "A-01"},
       f"calls={calls} arch={arch}")


def t1_reviewer_landing_never_completes_the_architects_job():
    eng = _eng()
    arch = _arch(eng, job={"kind": "reconcile", "block": "A-01"})
    rev = {"id": "REV-code", "role": "reviewer-code", "rtype": "code", "session_id": "dry",
          "status": "working", "block": "review:code", "pending_landings": ["rev-findings"]}
    eng.st.workers.append(rev)
    calls = _capture_reconcile(eng)
    orig = _stub_landing(("ok", "clean"), touches=True)   # would correlate if it were checked
    try:
        eng._drain_landings(rev, "reviewer")
    finally:
        _restore_landing(orig)
    ok("T1 a reviewer's own landing never completes the architect's job (role-scoped)",
       not calls and arch.get("current_job") == {"kind": "reconcile", "block": "A-01"},
       f"calls={calls} arch={arch}")


def t1_no_live_job_landing_never_completes_anything():
    eng = _eng()
    arch = _arch(eng, job=None, status="idle", pending_landings=["stray-branch"])
    calls = _capture_reconcile(eng)
    orig = _stub_landing(("ok", "clean"), touches=True)
    try:
        eng._drive_landings()
    finally:
        _restore_landing(orig)
    ok("T1 no-op reconcile: an idle architect (no live job) is never completed by any landing",
       not calls and arch.get("current_job") is None, f"calls={calls}")


def t1_job_case_auto_closes_on_correlated_completion():
    eng = _eng()
    arch = _arch(eng, job={"kind": "forward", "block": "A-01"},
                 pending_landings=["arch/forward-A-01"])
    cid = eng._open_case("A-01", "architect", arch["id"], "architect stalled")
    arch["job_case"] = cid
    orig = _stub_landing(("ok", "clean"), touches=True)
    try:
        eng._drive_landings()
    finally:
        _restore_landing(orig)
    ok("T1 the parked architect case auto-closes the instant the job completes",
       cid not in eng.st.pending_cases and not arch.get("job_case"), f"arch={arch}")


# ══ T2: the record-stage ratchet's one deterministic re-merge path ══

def _stub_trunk2(tip="NEWTIP", descendant=True, code=True, ancestor=True, ff_ok=True,
                 patch_match=False):
    orig = (trunk.tip_sha, trunk.is_descendant, trunk.delta_has_code,
            trunk.merge_ff_only, trunk.patch_id_matches, trunk.is_ancestor,
            trunk.validate_trunk)
    calls = {"ff": 0}
    trunk.tip_sha = lambda *a, **k: tip
    trunk.is_descendant = lambda *a, **k: descendant
    trunk.delta_has_code = lambda *a, **k: code
    trunk.is_ancestor = lambda *a, **k: ancestor
    trunk.patch_id_matches = lambda *a, **k: patch_match
    # T2 (01-34, ADR-0003 D-C): the trunk-stage gate now re-derives its OWN
    # test-stage verdict every tick, unconditionally — these T2/redrive fixtures
    # are about the RATCHET, not the verdict, so hold it at "not yet" (never dry's
    # own vacuous pass) so a held 'trunk' stage stays held for the reason each test
    # actually asserts.
    trunk.validate_trunk = lambda *a, **k: ("fail", "not ready (test-stage stub)")

    def _ff(*a, **k):
        calls["ff"] += 1
        return (ff_ok, "" if ff_ok else "not a fast-forward")
    trunk.merge_ff_only = _ff
    return orig, calls


def _restore_trunk2(orig):
    (trunk.tip_sha, trunk.is_descendant, trunk.delta_has_code,
     trunk.merge_ff_only, trunk.patch_id_matches, trunk.is_ancestor,
     trunk.validate_trunk) = orig


def t2_code_bearing_descendant_redrives_through_ask_gate_then_lands():
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "record", "pr": None,
                                        "merged_sha": "OLDTIP123"})
    eng.st.approvals["merge"] = "ASK"
    orig, calls = _stub_trunk2(tip="NEWTIP456", descendant=True, code=True)
    try:
        eng._drive_gate("A-01", g)
    finally:
        _restore_trunk2(orig)
    ok("T2 a code-bearing descendant opens the ORDINARY merge case (existing kind)",
       g.get("case_merge") in eng.st.pending_cases
       and eng.st.pending_cases[g["case_merge"]].get("kind") == "merge", f"g={g}")
    ok("T2 the gate holds at record quietly while parked (no premature merge)",
       g.get("stage") == "record" and calls["ff"] == 0, f"g={g}")

    cid = g["case_merge"]
    orig2, calls2 = _stub_trunk2(tip="NEWTIP456", descendant=True, code=True, ff_ok=True)
    try:
        eng._h_apply_decision({"case": cid, "decision": "approve"})
    finally:
        _restore_trunk2(orig2)
    ok("T2 approve lands the delta (ff-only, same gate path) and re-validates on trunk",
       g.get("stage") == "trunk" and g.get("merged_sha") == "NEWTIP456"
       and calls2["ff"] == 1, f"g={g} calls={calls2}")
    ok("T2 the grant is fully consumed — no stale approved_merge/case_merge/merge_in_flight",
       not g.get("approved_merge") and not g.get("case_merge") and not g.get("merge_in_flight"),
       f"g={g}")


def t2_paperwork_only_descendant_lands_via_paperwork_lane_no_redrive():
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None, "merged_sha": "OLDTIP"})
    orig, calls = _stub_trunk2(tip="NEWTIP", descendant=True, code=False)
    try:
        eng._drive_gate("A-01", g)
    finally:
        _restore_trunk2(orig)
    ok("T2 a paperwork-only descendant never opens a merge case (paperwork lane owns it)",
       not g.get("case_merge") and calls["ff"] == 0, f"g={g}")
    ok("T2 the ratchet holds exactly as before (stage/merged_sha unchanged)",
       g.get("stage") == "trunk" and g.get("merged_sha") == "OLDTIP", f"g={g}")


def t2_non_descendant_never_redrives_ratchet_holds():
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None, "merged_sha": "OLDTIP"})
    orig, calls = _stub_trunk2(tip="SIDEWAYS", descendant=False, code=True)
    try:
        eng._drive_gate("A-01", g)
    finally:
        _restore_trunk2(orig)
    ok("T2 a non-descendant tip never redrives (divergent history is the contradiction "
       "arm's job, not this one)",
       not g.get("case_merge") and calls["ff"] == 0 and g.get("stage") == "trunk", f"g={g}")


def t2_no_new_commits_ratchet_holds():
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None, "merged_sha": "SAMETIP"})
    orig, calls = _stub_trunk2(tip="SAMETIP", descendant=True, code=True)
    try:
        eng._drive_gate("A-01", g)
    finally:
        _restore_trunk2(orig)
    ok("T2 no new commits at all -> the ratchet holds, never redrives",
       not g.get("case_merge") and calls["ff"] == 0 and g.get("stage") == "trunk", f"g={g}")


def t2_patch_identity_carries_the_grant_across_a_further_moved_tip():
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None, "merged_sha": "OLDTIP",
                                        "approved_merge": True, "case_tip": "PINNEDTIP"})
    orig, calls = _stub_trunk2(tip="NEWERTIP", descendant=True, code=True, ff_ok=True,
                               patch_match=True)
    try:
        eng._drive_gate("A-01", g)
    finally:
        _restore_trunk2(orig)
    ok("T2 patch-id match carries the grant to the new tip (no re-park, one landing)",
       g.get("case_tip") == "NEWERTIP" and g.get("stage") == "trunk"
       and g.get("merged_sha") == "NEWERTIP" and calls["ff"] == 1, f"g={g}")


def t2_patch_identity_mismatch_voids_and_re_parks():
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None, "merged_sha": "OLDTIP",
                                        "approved_merge": True, "case_tip": "PINNEDTIP"})
    eng.st.approvals["merge"] = "ASK"
    orig, calls = _stub_trunk2(tip="DIVERGENTTIP", descendant=True, code=True,
                               patch_match=False)
    try:
        eng._drive_gate("A-01", g)
    finally:
        _restore_trunk2(orig)
    ok("T2 patch-id mismatch voids the stale grant and re-parks a FRESH merge case",
       not g.get("approved_merge") and g.get("case_merge") in eng.st.pending_cases
       and calls["ff"] == 0, f"g={g}")


# ══ T3(a): the runner reports runtime failure, never a healthy turn ══

def _make_echo_cli_script(tmpdir):
    path = os.path.join(tmpdir, "echo_cli.py")
    script = (
        "#!/usr/bin/env python3\n"
        "import sys, json\n"
        "for line in sys.stdin:\n"
        "    line = line.strip()\n"
        "    if not line:\n"
        "        continue\n"
        "    try:\n"
        "        msg = json.loads(line)\n"
        "    except Exception:\n"
        "        continue\n"
        "    text = (msg.get('message') or {}).get('content', '')\n"
        "    if 'REFUSE_ISERROR' in text:\n"
        "        out = {'type': 'result', 'subtype': 'success', 'is_error': True,\n"
        "               'result': 'boom'}\n"
        "    elif 'REFUSE_SUBTYPE' in text:\n"
        "        out = {'type': 'result', 'subtype': 'error_max_turns', 'is_error': False,\n"
        "               'result': 'too many turns'}\n"
        "    elif 'REFUSE_SHAPE_UNVERIFIED' in text:\n"
        "        out = {'type': 'result',\n"
        "               'result': 'You have reached your usage limit. Try again later.'}\n"
        "    elif 'CLEAN_SUCCESS_MENTIONS_LIMIT' in text:\n"
        "        out = {'type': 'result', 'subtype': 'success', 'is_error': False,\n"
        "               'result': 'done: added handling for rate limit exceeded '\n"
        "                         'responses from the provider'}\n"
        "    else:\n"
        "        out = {'type': 'result', 'subtype': 'success', 'is_error': False,\n"
        "               'result': 'ok: ' + text}\n"
        "    print(json.dumps(out))\n"
        "    sys.stdout.flush()\n"
    )
    with open(path, "w") as fh:
        fh.write(script)
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def t3a_host_cli_adapter_raises_on_failure_never_a_healthy_turn():
    d = tempfile.mkdtemp(prefix="tron-hostcli-")
    script = _make_echo_cli_script(d)
    adapter = worker_runner.HostCliAdapter(script, "test-session", d, model="test-model")
    try:
        healthy = adapter.run_turn("hello there")
        ok("T3a a healthy turn's subtype/is_error are recorded, never discarded",
           isinstance(healthy, dict) and healthy.get("subtype") == "success"
           and healthy.get("is_error") is False and healthy.get("text") == "ok: hello there",
           f"healthy={healthy}")

        def _raises(text):
            try:
                adapter.run_turn(text)
                return False
            except worker_runner.RunnerRefusal:
                return True
        ok("T3a is_error:true raises RunnerRefusal", _raises("REFUSE_ISERROR please"))
        ok("T3a a non-'success' subtype raises RunnerRefusal", _raises("REFUSE_SUBTYPE please"))
        ok("T3a a known refusal SHAPE with NO affirmed subtype/is_error raises (BLOCKER-1: "
           "the quota shape is unverified and may arrive with nothing to trust)",
           _raises("REFUSE_SHAPE_UNVERIFIED please"))
    finally:
        adapter.close()
        shutil.rmtree(d, ignore_errors=True)


def t3a_healthy_success_mentioning_refusal_wording_never_raises():
    """impl-review MAJOR-3 (MINOR-6b): a clean success turn (is_error=False,
    subtype=='success') whose OWN prose happens to contain a known refusal SHAPE (e.g.
    describing rate-limit handling this fleet's own product builds) must NEVER raise —
    the shape match is not a content classifier of legitimate coding-turn output."""
    d = tempfile.mkdtemp(prefix="tron-hostcli-clean-")
    script = _make_echo_cli_script(d)
    adapter = worker_runner.HostCliAdapter(script, "test-session", d, model="test-model")
    try:
        result = adapter.run_turn("CLEAN_SUCCESS_MENTIONS_LIMIT please")
        ok("T3a a healthy success turn mentioning 'rate limit exceeded' in its own "
           "summary text does NOT raise RunnerRefusal",
           isinstance(result, dict) and result.get("subtype") == "success"
           and result.get("is_error") is False, f"result={result}")
    finally:
        adapter.close()
        shutil.rmtree(d, ignore_errors=True)


def t3a_turn_done_records_subtype_is_error_in_the_timeline():
    d = tempfile.mkdtemp(prefix="tron-wr-ok-")
    wdir = os.path.join(d, "w")
    os.makedirs(wdir)
    jobs.send(wdir, 1, "gate.local", "validate")
    r = worker_runner.Runner("W", wdir, "s", None, "echo", "echo")
    # EchoAdapter's one turn always succeeds — run() drains the single pending message and
    # returns to `idle` on its own; no threading needed for a bounded, deterministic check.
    r._write_state("online")
    hwm = r._read_hwm()
    pending = r._pending(hwm)
    for m in pending:
        seq = m["seq"]
        r._write_state("working")
        r._timeline(event="turn_start", seq=seq, kind=m.get("kind"))
        result = r.adapter.run_turn(m.get("text", ""))
        r.turns += 1
        r._write_hwm(seq)
        if isinstance(result, dict):
            r._timeline(event="turn_done", seq=seq, text=(result.get("text") or "")[:200],
                       subtype=result.get("subtype"), is_error=bool(result.get("is_error")))
        else:
            r._timeline(event="turn_done", seq=seq, text=(result or "")[:200])
    events = [json.loads(l) for l in open(r.timeline) if l.strip()]
    done = next((e for e in events if e.get("event") == "turn_done"), None)
    ok("T3a turn_done records subtype/is_error (worker_runner.py:108's old discard is dead)",
       done is not None and done.get("subtype") == "success" and done.get("is_error") is False,
       f"events={events}")
    shutil.rmtree(d, ignore_errors=True)


class _RefusalAdapter:
    def __init__(self, *a, **k):
        pass

    def run_turn(self, text):
        raise worker_runner.RunnerRefusal("simulated fleet-wide refusal")

    def close(self):
        pass


def t3a_turn_error_records_the_exception_kind_structurally():
    d = tempfile.mkdtemp(prefix="tron-wr-err-")
    wdir = os.path.join(d, "w")
    os.makedirs(wdir)
    jobs.send(wdir, 1, "gate.local", "validate")
    r = worker_runner.Runner("W", wdir, "s", None, "echo", "echo")
    r.adapter = _RefusalAdapter()
    rc = r.run()
    ok("T3a a RunnerRefusal rides the EXISTING exception path (turn_error -> state error)",
       rc == 1)
    state = json.load(open(os.path.join(wdir, jobs.RUNNER_STATE)))
    ok("T3a the runner state reads 'error' (jobs.is_alive() reads False)",
       state.get("state") == "error", f"state={state}")
    events = [json.loads(l) for l in open(os.path.join(wdir, jobs.TIMELINE)) if l.strip()]
    err = next((e for e in events if e.get("event") == "turn_error"), None)
    ok("T3a turn_error records the exception CLASS structurally (kind='RunnerRefusal') "
       "— never the refusal TEXT engine-side (NET-ZERO)",
       err is not None and err.get("kind") == "RunnerRefusal", f"events={events}")
    ok("T3a jobs.last_turn_error_kind reads the SAME structural field the fleet-hold sweep uses",
       jobs.last_turn_error_kind(wdir) == "RunnerRefusal")
    shutil.rmtree(d, ignore_errors=True)


# ══ T3(b): fleet-global refusal backoff (engine side) ══

def t3b_fleet_hold_engages_probes_canary_resumes_never_walls():
    ctx, _ = build(blocks=[("A-01", "🔄", "none"), ("A-02", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]

    world = {"dead": {}, "canary_wid": None, "canary_healthy": False}

    def _index():
        out = {}
        for wid in world["dead"]:
            out[wid] = {"state": "error", "dir": f"/fake/{wid}", "pid": None, "turns": 0}
        if world["canary_wid"] and world["canary_healthy"]:
            out[world["canary_wid"]] = {"state": "idle", "dir": "/fake/canary",
                                        "pid": 999, "turns": 1}
        return out

    def _find(wid, idx=None):
        return (idx if idx is not None else _index()).get(wid)

    def _alive(wid, idx=None):
        rec = (idx if idx is not None else _index()).get(wid)
        return bool(rec) and rec.get("state") != "error"

    def _kind(wdir):
        for wid in world["dead"]:
            if wdir == f"/fake/{wid}":
                return "RunnerRefusal"
        return ""

    orig = (jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind)
    jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind = _index, _find, _alive, _kind
    redispatched = []
    # dead_wid=None (01-36, ADR-0003 D-F): the real _redispatch gained an optional
    # handover-context kwarg; these stubs only care about the block/bypass_gate shape.
    eng._redispatch = lambda block, bypass_gate=False, dead_wid=None: redispatched.append(block)
    try:
        # Tick 1: ENG-A-01 dies of refusal — a LONE death, hold not yet active; the
        # ordinary per-worker stall handling still applies.
        eng.st.workers[:] = [{"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                             "session_id": "real-1", "status": "working"}]
        world["dead"] = {"ENG-A-01": True}
        eng._tq = []
        eng._sweep()
        ok("T3b tick1: a lone refusal death does not engage the fleet hold",
           not eng.st.data.get("refusal_hold", {}).get("active"),
           f"hold={eng.st.data.get('refusal_hold')}")
        ok("T3b tick1: the lone death still gets the ordinary stall handling",
           any(t == "worker:stalled" for t, _ in eng._tq), f"tq={eng._tq}")
        eng.st.workers[:] = []   # simulate the ordinary recover having released it

        # Tick 2: ENG-A-02 ALSO dies of refusal inside the window -> the hold engages;
        # this death is ABSORBED (no wall, no gate mutation, no ordinary recover).
        eng.st.gate["A-02"] = {"stage": "local", "pr": None}   # a live gate to prove untouched
        eng.st.workers[:] = [{"id": "ENG-A-02", "role": "engineer", "block": "A-02",
                             "session_id": "real-2", "status": "working"}]
        world["dead"] = {"ENG-A-02": True}
        eng._tq = []
        eng._sweep()
        hold = eng.st.data.get("refusal_hold", {})
        ok("T3b tick2: repeated fleet-wide refusal deaths engage the hold",
           hold.get("active") is True, f"hold={hold}")
        ok("T3b tick2: the held worker's block never walls",
           not any(t.startswith("wall:raised:") for t, _ in eng._tq), f"tq={eng._tq}")
        ok("T3b tick2: no ordinary per-worker recover fires for the absorbed death",
           not any(t == "worker:stalled" for t, _ in eng._tq), f"tq={eng._tq}")
        # (orphan_since may get stamped by the SEPARATE, pre-existing workerless-gate
        # invariant arm later in the same _sweep() — that net's own job, unrelated to the
        # fleet hold; its escalation itself is still a full silence window away. The fleet
        # hold's OWN contract is: never pop the gate, never change its stage, never wall.)
        g_after = eng.st.gate.get("A-02")
        ok("T3b tick2: the held block's gate is never popped, and its stage never changes",
           g_after is not None and g_after.get("stage") == "local" and g_after.get("pr") is None
           and "A-02" not in eng.st.blocked, f"gate={eng.st.gate}")
        ok("T3b tick2: a canary candidate was elected from the held block",
           hold.get("canary") == "A-02", f"hold={hold}")
        ok("T3b tick2: the dead worker's slot was released off the roster",
           not eng.st.workers, f"workers={eng.st.workers}")

        # Tick 2->3 (block 01-23 adaptation): the canary's OWN job record ("ENG-A-02") is
        # itself present-and-dead at the exact instant of election above (the fleet-wide
        # fault path this block fixes) -- the corrected sweep no longer deadlocks on a
        # present-dead record (the old bug: it returned without ever probing); it falls
        # through to the SAME paced re-dispatch an absent record takes, and since this is
        # the canary's first-ever probe (canary_probed_at unset) it fires immediately,
        # unpaced -- identical to the existing no-record-yet rule.
        ok("T3b tick2 (01-23): a present-dead canary record fires its first-ever probe "
           "immediately instead of deadlocking forever",
           redispatched == [hold["canary"]], f"redispatched={redispatched}")

        # Tick 3: the runtime is STILL down (the canary's record stays present-dead,
        # never cleared) -- a further sweep well inside the same gate_nudge_after span
        # must NOT spawn a second canary (paced, not per-sweep, into a possibly-still-dead
        # runtime; canary_probed_at is preserved, never popped, across the dead case).
        clock["t"] += 1
        eng._sweep()
        ok("T3b tick3: the re-probe is paced -- a sweep inside gate_nudge_after does not "
           "spawn a second canary",
           redispatched == [hold["canary"]], f"redispatched={redispatched}")

        # Tick 4: the runtime recovers -- the canary's first healthy turn resumes fleet
        # dispatch.
        world["canary_wid"] = eng._worker_id("engineer", hold["canary"])
        world["canary_healthy"] = True
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._sweep()
        hold2 = eng.st.data.get("refusal_hold", {})
        ok("T3b tick4: the first healthy canary turn resumes fleet dispatch",
           hold2.get("active") is False, f"hold={hold2}")
    finally:
        jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind = orig


def t3b_active_hold_freezes_real_switchboard_dispatch():
    """impl-review BLOCKER-1 (the verdict's 'add a test driving REAL _pulse'): the older
    t3b stubbed _redispatch and never drove the dispatch path, so it could not observe
    that the hold actually FREEZES FILL SLOTS — it only proved the walls went quiet. Drive
    the REAL _switchboard: with a ready pick AND a free slot, an ACTIVE hold must dispatch
    nothing; clearing the hold must let the very SAME pick through — proving _dispatch_held()
    is the freeze, not an empty queue (the BLOCKER-1 silent spawn-burn is dead)."""
    eng = _eng()
    eng.dry = False
    eng.st.run_control = None
    dispatched = []
    slots = {"n": 1}
    eng._free_slots = lambda: slots["n"]
    eng._select_work = lambda: ("block", "A-01")
    eng._dispatch_engineer = lambda ref: (dispatched.append(ref), slots.__setitem__("n", 0))
    eng._in_scope_rows = lambda: []          # neutralise CLEAR AHEAD — only FILL SLOTS is under test
    eng._all_settled = lambda: False
    eng._fleet_refusal_hold()["active"] = True
    eng._switchboard()
    ok("T3b(BLOCKER-1) an ACTIVE fleet hold freezes real FILL-SLOTS dispatch — nothing spawns",
       dispatched == [], f"dispatched={dispatched}")
    eng._fleet_refusal_hold()["active"] = False
    eng._switchboard()
    ok("T3b(BLOCKER-1) clearing the hold lets the SAME ready pick through — the gate, not "
       "an empty queue, was the freeze",
       dispatched == ["A-01"], f"dispatched={dispatched}")


def t3b_canary_probe_is_role_agnostic_and_bypasses_the_gate():
    """impl-review MAJOR-2: the canary must be role-AGNOSTIC and a gated held block must
    stay probeable (I2). A reviewer refusal death elects a reviewer canary (its rtype) that
    probes through _dispatch_reviewer; an engineer canary probes through _redispatch WITH
    bypass_gate=True. The old suite drove neither the election role-agnosticism nor the
    real _sweep_fleet_refusal_canary routing."""
    eng = _eng()
    eng.dry = False
    clock = {"t": 6000.0}
    eng._now_s = lambda: clock["t"]
    eng._release_worker = lambda w, notify=True, reason=None: None   # side-effect-free election
    reviewer, redispatch = [], []
    eng._dispatch_reviewer = lambda ref: reviewer.append(ref)
    eng._redispatch = lambda block, bypass_gate=False, dead_wid=None: redispatch.append((block, bypass_gate))
    orig = (jobs.find, jobs.is_alive)
    jobs.find = lambda wid, idx=None: None       # no live canary yet -> the probe path
    jobs.is_alive = lambda wid, idx=None: False
    try:
        # a REVIEWER refusal death elects a role-tagged reviewer canary (its rtype)
        # ADR-0002 D4: the fixture's REVIEW-bound role is "reviewer-code" (the trivial
        # scaffold's roles.yaml), never a bare "reviewer" literal.
        eng._fleet_refusal_hold()["active"] = True
        eng._drive_fleet_refusal_hold({"id": "REV-code", "role": "reviewer-code",
                                       "rtype": "code", "session_id": "real"})
        hold = eng._fleet_refusal_hold()
        ok("T3b(MAJOR-2) a reviewer death elects a role-tagged reviewer canary keyed on rtype "
           "(an engineer-only election would wedge the hold when the deaths are reviewers)",
           hold.get("canary") == "code" and hold.get("canary_role") == "reviewer-code", f"hold={hold}")
        eng._sweep_fleet_refusal_canary({})
        ok("T3b(MAJOR-2) the reviewer canary probes via _dispatch_reviewer, never _redispatch",
           reviewer == ["code"] and redispatch == [], f"rev={reviewer} rd={redispatch}")
        # an ENGINEER canary on an already-gated block still probes, via bypass_gate=True
        hold.update({"canary": "A-01", "canary_role": "engineer", "canary_probed_at": None})
        eng.st.gate["A-01"] = {"stage": "local", "pr": None}
        clock["t"] += 1
        eng._sweep_fleet_refusal_canary({})
        ok("T3b(MAJOR-2) an engineer canary probes via _redispatch WITH bypass_gate=True — a "
           "gated held block stays probeable (I2), never a permanent silent wedge",
           redispatch == [("A-01", True)], f"rd={redispatch}")
    finally:
        jobs.find, jobs.is_alive = orig


def t3b_redispatch_honors_bypass_gate_on_a_gated_block():
    """impl-review MAJOR-2 (proving the fix acts, not just that the flag is passed): the
    REAL _redispatch no-ops on a gated block for the plain recovery call (unchanged) but
    reaches the re-spawn under bypass_gate=True — every OTHER hard stop (done/parked/
    dropped/live-PR/deps/active-worker) still applies to both."""
    eng = _eng()
    eng.st.workers[:] = []                       # the active-worker stop is separate; clear it
    eng.st.gate["A-01"] = {"stage": "local", "pr": None}   # A-01 has already gated
    spawned = []
    eng._spawn = lambda wid, *a, **k: (spawned.append(wid) or ("sess", "sh"))
    eng._reserve = lambda w: eng.st.workers.append(w)
    eng.st.record_dispatch = lambda *a, **k: None
    eng.events.event = lambda *a, **k: None
    eng._redispatch("A-01", bypass_gate=False)
    ok("T3b(MAJOR-2) plain _redispatch STILL no-ops on a gated block (gate ownership unchanged)",
       spawned == [], f"spawned={spawned}")
    eng._redispatch("A-01", bypass_gate=True)
    ok("T3b(MAJOR-2) bypass_gate=True reaches the re-spawn on the gated block (the canary "
       "can re-prove the runtime for a held block that gated)",
       spawned == [eng._worker_id("engineer", "A-01")], f"spawned={spawned}")


# ══ block 01-23: the fleet-refusal-hold self-releases after a fleet-wide outage ══
# (the T3b canary probe used to deadlock forever when the elected canary's OWN job
# record was present-but-dead, rather than absent — a fleet-wide outage leaves exactly
# that shape, tron-33/34. _sweep_fleet_refusal_canary must fall through to the SAME
# paced re-dispatch an absent record takes, preserving canary_probed_at so the re-probe
# stays paced at ~one per gate_nudge_after, never an every-sweep spawn-burn.)

def t3b_dead_record_canary_reprobes_on_cadence():
    """AC-1: a present-but-dead canary job record (rec is not None, not alive, turns=0)
    must fall through to the SAME paced re-dispatch an absent record takes, once the
    gate_nudge_after cadence has elapsed since the last probe — never the unconditional
    return the bug used to take (the permanent-deadlock fault path, tron-33/34)."""
    eng = _eng()
    clock = {"t": 10000.0}
    eng._now_s = lambda: clock["t"]
    redispatch = []
    eng._redispatch = lambda block, bypass_gate=False, dead_wid=None: redispatch.append((block, bypass_gate))
    orig = (jobs.find, jobs.is_alive)
    dead_rec = {"state": "error", "dir": "/fake/A-01", "pid": None, "turns": 0}
    jobs.find = lambda wid, idx=None: dead_rec
    jobs.is_alive = lambda wid, idx=None: False
    try:
        hold = eng._fleet_refusal_hold()
        hold.update({"active": True, "canary": "A-01", "canary_role": "engineer",
                     "canary_probed_at": clock["t"] - 1})   # a prior probe already happened
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1   # the cadence elapses
        eng._sweep_fleet_refusal_canary({})
        ok("T3b(AC-1) a present-dead canary record falls through to the paced re-dispatch "
           "instead of returning without re-probing",
           redispatch == [("A-01", True)], f"rd={redispatch}")
        ok("T3b(AC-1) the hold stays active while re-probing (never falsely cleared)",
           hold.get("active") is True, f"hold={hold}")
    finally:
        jobs.find, jobs.is_alive = orig


def t3b_dead_record_canary_reprobe_is_paced():
    """AC-2: canary_probed_at is PRESERVED across the dead-record case (never popped), so
    a sweep inside one gate_nudge_after span of the last probe does not fire a second
    canary spawn — the existing spawn-burn brake, unmodified, still applies to the
    dead-record fall-through."""
    eng = _eng()
    clock = {"t": 11000.0}
    eng._now_s = lambda: clock["t"]
    redispatch = []
    eng._redispatch = lambda block, bypass_gate=False, dead_wid=None: redispatch.append((block, bypass_gate))
    orig = (jobs.find, jobs.is_alive)
    dead_rec = {"state": "error", "dir": "/fake/A-01", "pid": None, "turns": 0}
    jobs.find = lambda wid, idx=None: dead_rec
    jobs.is_alive = lambda wid, idx=None: False
    try:
        hold = eng._fleet_refusal_hold()
        hold.update({"active": True, "canary": "A-01", "canary_role": "engineer",
                     "canary_probed_at": clock["t"]})   # a probe just happened this instant
        clock["t"] += 1   # well inside gate_nudge_after
        eng._sweep_fleet_refusal_canary({})
        ok("T3b(AC-2) a sweep inside one gate_nudge_after span of the last probe does not "
           "spawn a second canary (paced, not per-sweep, into a possibly-still-dead runtime)",
           redispatch == [], f"rd={redispatch}")
        ok("T3b(AC-2) canary_probed_at was preserved across the dead-record case, not popped",
           hold.get("canary_probed_at") is not None, f"hold={hold}")
    finally:
        jobs.find, jobs.is_alive = orig


def t3b_fleet_wide_death_then_recovery_autoreleases_hold():
    """AC-3 end-to-end: two real fleet-wide refusal deaths engage the hold and elect a
    canary (the existing, unchanged 01-20 engage path); the runtime is STILL down so the
    elected canary's OWN job record stays present-and-dead across repeated sweeps (the
    exact tron-33/34 fault path) instead of deadlocking. Once the runtime recovers, the
    next paced re-probe's canary completes a healthy turn and the hold self-releases
    end-to-end — active False, canary keys popped, pulse emitted — with zero operator
    lever."""
    ctx, _ = build(blocks=[("A-01", "🔄", "none"), ("A-02", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    clock = {"t": 13000.0}
    eng._now_s = lambda: clock["t"]

    world = {"dead": set(), "canary_wid": None, "canary_healthy": False}

    def _index():
        out = {}
        for wid in world["dead"]:
            out[wid] = {"state": "error", "dir": f"/fake/{wid}", "pid": None, "turns": 0}
        if world["canary_wid"] and world["canary_healthy"]:
            out[world["canary_wid"]] = {"state": "idle", "dir": "/fake/canary",
                                        "pid": 999, "turns": 1}
        return out

    def _find(wid, idx=None):
        return (idx if idx is not None else _index()).get(wid)

    def _alive(wid, idx=None):
        rec = (idx if idx is not None else _index()).get(wid)
        return bool(rec) and rec.get("state") != "error"

    def _kind(wdir):
        for wid in world["dead"]:
            if wdir == f"/fake/{wid}":
                return "RunnerRefusal"
        return ""

    orig = (jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind)
    jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind = _index, _find, _alive, _kind
    redispatched = []
    # dead_wid=None (01-36, ADR-0003 D-F): the real _redispatch gained an optional
    # handover-context kwarg; these stubs only care about the block/bypass_gate shape.
    eng._redispatch = lambda block, bypass_gate=False, dead_wid=None: redispatched.append(block)
    try:
        # ticks 1-2: fleet-wide refusal deaths engage the hold; A-02 is elected canary.
        eng.st.workers[:] = [{"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                             "session_id": "real-1", "status": "working"}]
        world["dead"] = {"ENG-A-01"}
        eng._sweep()
        eng.st.workers[:] = [{"id": "ENG-A-02", "role": "engineer", "block": "A-02",
                             "session_id": "real-2", "status": "working"}]
        world["dead"] = {"ENG-A-02"}
        eng._sweep()
        hold = eng.st.data.get("refusal_hold", {})
        ok("T3b(AC-3) setup: the hold engaged with A-02 elected as canary",
           hold.get("active") is True and hold.get("canary") == "A-02", f"hold={hold}")

        # the canary's own job record stays a PRESENT dead record across further sweeps
        # (the fault this block fixes) instead of vanishing -- the runtime is still down.
        n_after_election = len(redispatched)
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._sweep()
        ok("T3b(AC-3) a present-dead canary re-probes instead of deadlocking forever -- "
           "the hold stays active",
           eng.st.data.get("refusal_hold", {}).get("active") is True
           and len(redispatched) > n_after_election,
           f"hold={eng.st.data.get('refusal_hold')} redispatched={redispatched}")

        # the runtime recovers: the NEXT paced re-probe's canary completes a healthy turn.
        world["canary_wid"] = eng._worker_id("engineer", "A-02")
        world["canary_healthy"] = True
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._tq = []
        eng._sweep()
        hold2 = eng.st.data.get("refusal_hold", {})
        ok("T3b(AC-3) end-to-end: fleet-wide death -> canary death -> recovery -> healthy "
           "canary turn self-releases the hold with zero operator lever",
           hold2.get("active") is False and "canary" not in hold2
           and "canary_role" not in hold2 and "canary_probed_at" not in hold2,
           f"hold={hold2}")
        ok("T3b(AC-3) a pulse is emitted on release",
           any(t == "pulse" for t, _ in eng._tq), f"tq={eng._tq}")
    finally:
        jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind = orig


def t3b_ran_then_died_canary_does_not_release():
    """AC-4: a canary that completed a turn and then died (present record, turns>=1, not
    alive) must NOT falsely clear the hold — the release condition stays gated on BOTH
    is_alive AND turns>=1, so it falls to re-probe exactly like a never-turned dead
    canary, never a false release."""
    eng = _eng()
    clock = {"t": 12000.0}
    eng._now_s = lambda: clock["t"]
    redispatch = []
    eng._redispatch = lambda block, bypass_gate=False, dead_wid=None: redispatch.append((block, bypass_gate))
    orig = (jobs.find, jobs.is_alive)
    dead_rec = {"state": "error", "dir": "/fake/A-01", "pid": None, "turns": 3}
    jobs.find = lambda wid, idx=None: dead_rec
    jobs.is_alive = lambda wid, idx=None: False
    try:
        hold = eng._fleet_refusal_hold()
        hold.update({"active": True, "canary": "A-01", "canary_role": "engineer",
                     "canary_probed_at": clock["t"] - 1})
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._sweep_fleet_refusal_canary({})
        ok("T3b(AC-4) a canary that ran a turn and then died does not falsely clear the hold",
           hold.get("active") is True, f"hold={hold}")
        ok("T3b(AC-4) it falls to re-probe instead, identically to a never-turned dead canary",
           redispatch == [("A-01", True)], f"rd={redispatch}")
    finally:
        jobs.find, jobs.is_alive = orig


# ══ block 01-27 T1: the fault-injection drill, discharging 01-23 AC-6 as a repeatable
# in-suite test (never a wait-for-a-real-outage manual). Unlike the staggered-roster
# t3b_fleet_wide_death_then_recovery_autoreleases_hold above (each death landed via a
# separate roster swap), this kills BOTH live engineers in the SAME sweep — a genuine
# fleet-wide mid-run kill, canary included — then restores the runtime and drives the
# REAL _switchboard to prove dispatch actually resumes (BLOCKER-1 style), not merely
# that the hold's own bookkeeping cleared. ══

def t3b_fleet_wide_outage_drill_canary_included_self_release_clean_finish():
    """01-27 T1/AC-1/AC-2: fleet-wide runtime kill mid-run (both live engineers die in
    ONE sweep, the elected canary among them) -> the hold engages; the canary's own job
    record stays PRESENT-but-dead (tron-33/34's exact shape, never merely absent) and
    re-probes on the paced cadence, never per-sweep; once the runtime recovers the hold
    self-releases the instant the canary's probe turns healthy; the real _switchboard
    (not a stub) then dispatches the still-pending fleet, proving a clean finish. At NO
    point does any operator-facing case/wall open -- zero operator touch throughout."""
    ctx, _ = build(blocks=[("A-01", "🔄", "none"), ("A-02", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    clock = {"t": 50000.0}
    eng._now_s = lambda: clock["t"]
    eng.st.workers[:] = [
        {"id": "ENG-A-01", "role": "engineer", "block": "A-01",
         "session_id": "real-1", "status": "working"},
        {"id": "ENG-A-02", "role": "engineer", "block": "A-02",
         "session_id": "real-2", "status": "working"},
    ]

    world = {"dead": {"ENG-A-01", "ENG-A-02"}, "healthy": set()}

    def _index():
        out = {}
        for wid in world["dead"]:
            out[wid] = {"state": "error", "dir": f"/fake/{wid}", "pid": None, "turns": 0}
        for wid in world["healthy"]:
            out[wid] = {"state": "idle", "dir": f"/fake/{wid}", "pid": 999, "turns": 1}
        return out

    def _find(wid, idx=None):
        return (idx if idx is not None else _index()).get(wid)

    def _alive(wid, idx=None):
        rec = (idx if idx is not None else _index()).get(wid)
        return bool(rec) and rec.get("state") != "error"

    def _kind(wdir):
        for wid in world["dead"]:
            if wdir == f"/fake/{wid}":
                return "RunnerRefusal"
        return ""

    orig = (jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind)
    jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind = _index, _find, _alive, _kind
    redispatched = []
    # dead_wid=None (01-36, ADR-0003 D-F): the real _redispatch gained an optional
    # handover-context kwarg; these stubs only care about the block/bypass_gate shape.
    eng._redispatch = lambda block, bypass_gate=False, dead_wid=None: redispatched.append(block)
    try:
        # Tick 1: the worker runtime dies FLEET-WIDE, mid-run -- both engineers dead in
        # the SAME sweep (never staggered across separate roster swaps).
        eng._sweep()
        hold = eng.st.data.get("refusal_hold", {})
        ok("T1(AC-1) a fleet-wide mid-run kill (both live engineers, one sweep) engages "
           "the hold",
           hold.get("active") is True, f"hold={hold}")
        ok("T1(AC-1/AC-2) the elected canary is one of the fleet-wide dead (the canary "
           "is INCLUDED in the kill, never a survivor elected after the fact)",
           hold.get("canary") in ("A-01", "A-02"), f"hold={hold}")
        ok("T1 zero operator touch at engage -- held blocks never wall (no pending case "
           "opened)",
           not eng.st.pending_cases, f"cases={eng.st.pending_cases}")

        canary_block = hold.get("canary")
        other_block = "A-02" if canary_block == "A-01" else "A-01"
        n0 = len(redispatched)

        # Tick 2, clock UNADVANCED: the canary's OWN job record is PRESENT-but-dead
        # (tron-33/34's exact shape) -- must NOT spawn a second probe before its paced
        # cadence elapses (no every-sweep spawn-burn into a still-dead runtime).
        eng._sweep()
        ok("T1(AC-2) a present-dead canary record is not re-probed before its cadence "
           "elapses (paced, not per-sweep)",
           len(redispatched) == n0, f"redispatched={redispatched}")

        # Tick 3: the pace cadence has elapsed -- the stale-dead canary record re-probes.
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._sweep()
        ok("T1(AC-2) the stale-dead canary record re-probes on the paced cadence -- the "
           "01-23 fix is exercised, not just present",
           len(redispatched) > n0 and eng.st.data["refusal_hold"].get("active") is True,
           f"redispatched={redispatched} hold={eng.st.data.get('refusal_hold')}")

        # The runtime recovers: the canary turns healthy.
        world["dead"] = set()
        world["healthy"] = {eng._worker_id("engineer", canary_block)}
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._tq = []
        eng._sweep()
        hold2 = eng.st.data.get("refusal_hold", {})
        ok("T1(AC-1) the hold self-releases the instant the canary's probe turns "
           "healthy -- zero operator touch",
           hold2.get("active") is False and "canary" not in hold2, f"hold={hold2}")
        ok("T1 a pulse is emitted on release (dispatch may resume)",
           any(t == "pulse" for t, _ in eng._tq), f"tq={eng._tq}")

        # Clean finish (BLOCKER-1 style, never a stubbed _redispatch): drive the REAL
        # _switchboard and prove the still-pending fleet actually dispatches -- the run
        # continues, not just the hold's own bookkeeping.
        dispatched = []
        slots = {"n": 2}
        eng.st.run_control = None
        eng._free_slots = lambda: slots["n"]
        pending = [other_block]
        eng._select_work = lambda: ("block", pending.pop(0)) if pending else None
        eng._dispatch_engineer = lambda ref: (dispatched.append(ref),
                                              slots.__setitem__("n", slots["n"] - 1))
        eng._in_scope_rows = lambda: []
        eng._all_settled = lambda: False
        eng._switchboard()
        ok("T1 clean finish -- with the hold clear, the REAL _switchboard dispatches the "
           "other fleet-wide-held block (not just the canary's own probe)",
           dispatched == [other_block], f"dispatched={dispatched}")
        ok("T1 clean finish -- no operator touch across the ENTIRE drill (no wall/case "
           "ever opened, zero operator lever)",
           not eng.st.pending_cases, f"cases={eng.st.pending_cases}")
    finally:
        jobs.index, jobs.find, jobs.is_alive, jobs.last_turn_error_kind = orig


# ══ T4: settling an architect-kind case acts (idempotent against T1/T5) ══

def t4_approve_rearms_the_ladder_and_redelivers_once():
    eng = _eng()
    arch = _arch(eng, job={"kind": "reconcile", "block": "A-01", "after": ""}, status="busy")
    cid = eng._open_case("A-01", "architect", arch["id"], "architect stalled")
    arch["job_case"] = cid
    sent = _capture(eng)
    eng._h_apply_decision({"case": cid, "decision": "approve"})
    ok("T4 approve clears the parked case and re-arms the idle ladder",
       cid not in eng.st.pending_cases and not arch.get("job_case")
       and not arch.get("job_idle_since") and not arch.get("job_nudged_at"), f"arch={arch}")
    ok("T4 approve re-delivers the SAME order once (arch.reconcile)",
       any(t == "arch.reconcile" and s.get("block") == "A-01" for t, s in sent), f"sent={sent}")
    ok("T4 the job itself is untouched — still live, never retired",
       arch.get("current_job") == {"kind": "reconcile", "block": "A-01", "after": ""}
       and arch.get("status") == "busy", f"arch={arch}")


def t4_resume_behaves_exactly_like_approve():
    eng = _eng()
    arch = _arch(eng, job={"kind": "forward", "block": "A-01"}, status="busy")
    cid = eng._open_case("A-01", "architect", arch["id"], "architect stalled")
    arch["job_case"] = cid
    sent = _capture(eng)
    eng._h_apply_decision({"case": cid, "decision": "resume"})
    ok("T4 resume re-arms the ladder identically to approve",
       cid not in eng.st.pending_cases and not arch.get("job_case")
       and any(t == "arch.forward" and s.get("block") == "A-01" for t, s in sent),
       f"arch={arch} sent={sent}")


def t4_abandon_retires_the_job_without_recording_reconciled():
    eng = _eng()
    arch = _arch(eng, job={"kind": "reconcile", "block": "A-01", "after": ""}, status="busy")
    cid = eng._open_case("A-01", "architect", arch["id"], "architect stalled")
    arch["job_case"] = cid
    eng._h_apply_decision({"case": cid, "decision": "abandon"})
    ok("T4 abandon retires the job (idle, current_job cleared)",
       arch.get("status") == "idle" and arch.get("current_job") is None, f"arch={arch}")
    ok("T4 abandon never records the block reconciled (never _h_reconcile's write)",
       "A-01" not in eng.st.reconciled, f"reconciled={eng.st.reconciled}")
    ok("T4 the case closes", cid not in eng.st.pending_cases)


def t4_already_advanced_job_closes_only_no_redelivery():
    eng = _eng()
    arch = _arch(eng, job={"kind": "reconcile", "block": "A-01"}, status="busy")
    # The case the operator's LATE settle names — but by the time it is processed the
    # job already advanced through another route (T1/T5 won the race): job_case no
    # longer names this case at all.
    cid = eng._open_case("A-01", "architect", arch["id"], "architect stalled (stale)")
    arch["job_case"] = None
    arch["status"], arch["current_job"] = "idle", None
    sent = _capture(eng)
    eng._h_apply_decision({"case": cid, "decision": "approve"})
    ok("T4 an already-advanced job's late settle closes the case only — never re-delivers",
       cid not in eng.st.pending_cases
       and not any(t.startswith("arch.") for t, _ in sent), f"sent={sent}")
    ok("T4 the already-idle architect is left undisturbed",
       arch.get("status") == "idle" and arch.get("current_job") is None, f"arch={arch}")


# ══ T5: architect review-done resolves by sender truth ══

def t5_architect_review_done_on_reconcile_job_flips_like_done():
    eng = _eng()
    arch = _arch(eng, job={"kind": "reconcile", "block": "A-01", "after": ""}, status="busy")
    tag, slots = eng._resolve_by_sender("worker.review_done", {"type": ""},
                                        {"kind": "worker", "id": arch["id"]})
    ok("T5 architect review-done on a live reconcile job flips to architect.reconciled "
       "(the same flip done/recorded perform)",
       tag == "architect.reconciled" and slots.get("block") == "A-01", f"tag={tag} slots={slots}")


def t5_architect_review_done_on_forward_job_also_flips():
    eng = _eng()
    arch = _arch(eng, job={"kind": "forward", "block": "A-02"}, status="busy")
    tag, slots = eng._resolve_by_sender("worker.review_done", {}, {"kind": "worker", "id": arch["id"]})
    ok("T5 forward jobs flip too (both kinds the spec names)",
       tag == "architect.reconciled" and slots.get("block") == "A-02", f"tag={tag}")


def t5_reviewer_role_review_done_unaffected():
    eng = _eng()
    eng.st.workers.append({"id": "REV-code", "role": "reviewer-code", "rtype": "code",
                          "session_id": "dry", "status": "working", "block": "review:code"})
    tag, slots = eng._resolve_by_sender("worker.done", {}, {"kind": "worker", "id": "REV-code"})
    ok("T5 a reviewer's plain done still flips to worker.review_done, unaffected",
       tag == "worker.review_done" and slots.get("type") == "code", f"tag={tag}")
    tag2, slots2 = eng._resolve_by_sender("worker.review_done", {"type": "code"},
                                          {"kind": "worker", "id": "REV-code"})
    ok("T5 a reviewer's OWN review_done tag passes through unchanged too",
       tag2 == "worker.review_done" and slots2.get("type") == "code", f"tag2={tag2}")


def t5_architect_review_done_on_log_job_stays_out_of_scope():
    eng = _eng()
    arch = _arch(eng, job={"kind": "log", "type": "code"}, status="busy")
    tag, slots = eng._resolve_by_sender("worker.review_done", {}, {"kind": "worker", "id": arch["id"]})
    ok("T5 the widening is scoped to forward/reconcile only — a log job's review-done "
       "passes through unresolved, unchanged, out of this block's scope",
       tag == "worker.review_done", f"tag={tag}")


# ══ T6: bounce cap + wake discipline (two separate fixes) ══

def t6a_bounce_caps_at_two_then_opens_the_idle_cap_case():
    eng = _eng()
    arch = _arch(eng, job={"kind": "reconcile", "block": "A-01"}, status="busy")
    tw = _capture_to_worker(eng)
    eng._now_s = lambda: 1000.0
    eng._bounce_gate({"kind": "worker", "id": arch["id"]}, "bad verb 1")
    eng._now_s = lambda: 2000.0
    eng._bounce_gate({"kind": "worker", "id": arch["id"]}, "bad verb 2")
    ok("T6a the first two bounces send normally",
       sum(1 for _, _, k in tw if k == "report.bounce") == 2, f"tw={tw}")
    sent = _capture(eng)
    eng._now_s = lambda: 3000.0
    eng._bounce_gate({"kind": "worker", "id": arch["id"]}, "bad verb 3")
    ok("T6a the THIRD bounce for the same job never sends",
       sum(1 for _, _, k in tw if k == "report.bounce") == 2, f"tw={tw}")
    ok("T6a the ordinary idle-cap case opens instead (the SAME existing escalation kind)",
       arch.get("job_case") in eng.st.pending_cases
       and eng.st.pending_cases[arch["job_case"]].get("kind") == "architect"
       and any(t == "escalate.wall" for t, _ in sent), f"sent={sent} arch={arch}")


def t6a_bounce_stays_role_agnostic_for_non_architect_senders():
    eng = _eng()
    tw = _capture_to_worker(eng)
    for i in range(4):
        eng._now_s = lambda i=i: 1000.0 + i * 1000
        eng._bounce_gate({"kind": "worker", "id": "ENG-A-01"}, f"bad verb {i}")
    ok("T6a a non-architect sender is never capped (_bounce itself stays role-agnostic)",
       sum(1 for _, _, k in tw if k == "report.bounce") == 4, f"tw={tw}")


def t6b_engine_wake_never_resets_the_idle_anchor():
    """impl-review MAJOR-4 fix: an engine-initiated wake (here, a REAL _bounce_gate call
    — not a hand-set field) stamps the EXPLICIT engine_wake_seq marker; while the runner
    hasn't consumed up to it, the busy blip it causes must never wipe the idle anchor.
    dispatch-realistic: mbox_seq is already nonzero (a real job's persona/order sends)
    BEFORE the wake — proving the marker, not the generic mbox_seq, drives the gate."""
    eng = _eng()
    eng.dry = False   # real _to_worker sends, so the wake stamp is the ACTUAL mechanism
    arch = _arch(eng, job={"kind": "log", "type": "code"}, status="busy")
    arch["mbox_seq"] = 3   # dispatch-realistic: prior persona/job-order sends already happened
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    orig_idle, orig_hwm = jobs.runner_idle, jobs.read_hwm
    jobs.runner_idle = lambda wid, idx=None: True
    jobs.read_hwm = lambda wdir: 3
    try:
        eng._drive_architect_liveness()      # anchors job_idle_since at 1000.0
        ok("T6b setup: idle anchor set", arch.get("job_idle_since") == 1000.0)
        # An ENGINE-initiated wake: a real bounce, which stamps engine_wake_seq at the
        # exact seq of THAT send (never the generic mbox_seq the dispatch itself already
        # bumped to 3 above — MAJOR-4's false-cap came from comparing against that).
        eng._bounce_gate({"kind": "worker", "id": arch["id"]}, "bad verb")
        wake_seq = arch.get("engine_wake_seq")
        ok("T6b setup: the bounce stamped an EXPLICIT engine_wake_seq (not inferred)",
           wake_seq == arch.get("mbox_seq") and wake_seq == 4, f"arch={arch}")
        jobs.runner_idle = lambda wid, idx=None: False   # runner goes briefly busy answering OUR bounce
        clock["t"] = 1010.0
        eng._drive_architect_liveness()
        ok("T6b the wake's busy blip never wipes the idle anchor",
           arch.get("job_idle_since") == 1000.0, f"arch={arch}")
        # The runner finishes answering our wake (consumed hwm catches up) and idles
        # again — accrual continues from the ORIGINAL anchor, never a fresh one.
        jobs.read_hwm = lambda wdir: wake_seq
        jobs.runner_idle = lambda wid, idx=None: True
        clock["t"] = 1000.0 + eng._pace("gate_idle_cap", 3) + 1
        eng._drive_architect_liveness()
        ok("T6b the cap fires off the ORIGINAL anchor (never restarted by the wake) — "
           "the tron-27 bounce/nudge livelock is dead",
           arch.get("job_case") in eng.st.pending_cases, f"arch={arch}")
    finally:
        jobs.runner_idle, jobs.read_hwm = orig_idle, orig_hwm


def t6b_genuinely_busy_runner_still_never_accrues():
    """A-4 pin (block_01_13_test's t_arch_liveness_working_never_accrues, unbroken),
    proved at DISPATCH-REALISTIC state (impl-review MAJOR-4): mbox_seq >= 1 and
    read_hwm behind it — exactly what a real dispatched job's whole first turn looks
    like (consumed never catches up until the turn ends). The prior pin used mbox_seq=0,
    a state no dispatched job ever occupies, and so never actually exercised the bug."""
    eng = _eng()
    arch = _arch(eng, job={"kind": "log", "type": "code"}, status="busy")
    arch["mbox_seq"] = 2        # dispatch-realistic: persona + job order already sent
    arch["job_idle_since"] = 1.0
    orig_idle, orig_hwm = jobs.runner_idle, jobs.read_hwm
    jobs.runner_idle = lambda wid, idx=None: False
    jobs.read_hwm = lambda wdir: 0   # consumed hasn't caught up to mbox_seq — a genuine long turn
    try:
        eng._now_s = lambda: 99999.0
        eng._drive_architect_liveness()
        ok("T6b a genuinely busy runner (dispatch-realistic mbox_seq, no engine wake "
           "ever marked) still never accrues idle",
           not arch.get("job_idle_since") and not arch.get("job_case"), f"arch={arch}")
    finally:
        jobs.runner_idle, jobs.read_hwm = orig_idle, orig_hwm


def main():
    for fn in sorted(k for k in globals()
                     if k.startswith(("t1_", "t2_", "t3a_", "t3b_", "t4_", "t5_", "t6a_", "t6b_"))):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
