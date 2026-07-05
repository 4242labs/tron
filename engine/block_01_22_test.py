"""block_01_22_test — runtime resilience: worker teardown is not a turn failure (T1) +
a self-contained `log` job settles on its own turn-done (T2). Standalone runner
convention (exit 0 = pass, no tokens, no network — a fake adapter stands in for the
host CLI for T1; T2 drives the real architect-queue/dispatch/liveness machinery with
`jobs.read_hwm`/`jobs.runner_idle` stubbed, exactly like block_01_20_test's T6b).

Covers (tron-29..32 evidence — both defects forced a manual `resume` on every sim run):
  AC-1 a worker whose host-CLI stream-ends OR process-exits once the runner is in its
       stop/release state (incl. the deliver-vs-release race) tears down cleanly: no
       turn_error, not left in `error` state. Both sibling sites (:153 process-exit,
       :157 stream-end) are covered under the ONE HostStreamEnded discrimination path.
  AC-2 a stream/process end while a turn is genuinely owed is raised as the refusal-
       class runtime drop (RunnerRefusal's broadened contract) and recovered via the
       existing fleet-hold path — never a bare RuntimeError that would strand the gate.
  AC-3 a self-contained `log` job settles the instant its own turn completes (off the
       runner's hwm-advance, `_mark_log_dispatch`/`_log_job_settled`), through the SAME
       bookkeeping the tagged path uses (`_architect_advance`); the architect opens NO
       architect-idle-cap case after a completed log turn; forward/reconcile jobs stay
       OUT of this self-settle path (scoped to `log` only).
  AC-4 a genuinely unfinished/unreported architect log job STILL opens the
       architect-idle-cap case exactly as before — the backstop is narrowed, not removed.

Run: python3 engine/block_01_22_test.py   (exit 0 = pass).
"""
import os
import sys
import json
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"
os.environ.setdefault("TRON_RUNNER_POLL_S", "0.05")

import jobs                    # noqa: E402
import worker_runner           # noqa: E402
from fsm import Engine         # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ══════════════════════════════════════════════════════════════════════════════════
# T1 (AC-1/AC-2): worker teardown is not a turn failure
# ══════════════════════════════════════════════════════════════════════════════════

class _TeardownAdapter:
    """Stands in for HostCliAdapter's inner loop: raises the SAME HostStreamEnded
    signal both real raise sites (:153 process-exit, :157 stream-end) now raise,
    under whichever wording the caller asks for. `on_call` (optional) fires just
    BEFORE the raise — this is how the deliver-vs-release-race test proves the
    runner checks its stop/release state FRESH at catch-time, never a value cached
    before the turn started: `.stop` lands DURING this call, not before it."""

    def __init__(self, wording, on_call=None):
        self.wording = wording
        self.on_call = on_call

    def run_turn(self, text):
        if self.on_call:
            self.on_call()
        raise worker_runner.HostStreamEnded(self.wording)

    def close(self):
        pass


def _fresh_worker_dir(prefix):
    d = tempfile.mkdtemp(prefix=prefix)
    wdir = os.path.join(d, "w")
    os.makedirs(wdir)
    jobs.send(wdir, 1, "gate.local", "validate")
    return d, wdir


def _events(wdir):
    path = os.path.join(wdir, jobs.TIMELINE)
    if not os.path.isfile(path):
        return []
    with open(path) as fh:
        return [json.loads(l) for l in fh if l.strip()]


def ac1_process_exit_teardown_while_stopped_is_not_a_failure():
    d, wdir = _fresh_worker_dir("tron-t1-procexit-")
    try:
        r = worker_runner.Runner("W", wdir, "s", None, "echo", "echo")
        r.adapter = _TeardownAdapter("host-cli process exited before a result event")
        with open(r.stop_path, "w") as fh:      # release() already landed (.stop on disk)
            fh.write("stop")
        rc = r.run()
        ok("AC-1 (:153 process-exit) teardown while stopped: run() returns 0 (clean)",
           rc == 0, f"rc={rc}")
        state = json.load(open(os.path.join(wdir, jobs.RUNNER_STATE)))
        ok("AC-1 (:153) worker state is 'released', never 'error'",
           state.get("state") == "released", f"state={state}")
        events = _events(wdir)
        ok("AC-1 (:153) no turn_error timeline event is recorded",
           not any(e.get("event") == "turn_error" for e in events), f"events={events}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ac1_stream_end_teardown_while_stopped_is_not_a_failure():
    d, wdir = _fresh_worker_dir("tron-t1-streamend-")
    try:
        r = worker_runner.Runner("W", wdir, "s", None, "echo", "echo")
        r.adapter = _TeardownAdapter("host-cli stream ended before a result event")
        with open(r.stop_path, "w") as fh:
            fh.write("stop")
        rc = r.run()
        ok("AC-1 (:157 stream-end) teardown while stopped: run() returns 0 (clean)",
           rc == 0, f"rc={rc}")
        state = json.load(open(os.path.join(wdir, jobs.RUNNER_STATE)))
        ok("AC-1 (:157) worker state is 'released', never 'error'",
           state.get("state") == "released", f"state={state}")
        events = _events(wdir)
        ok("AC-1 (:157) no turn_error timeline event is recorded",
           not any(e.get("event") == "turn_error" for e in events), f"events={events}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ac1_deliver_vs_release_race_resolves_to_teardown():
    """The message was already pulled (delivered) before the block closed; `.stop`
    lands ONLY once the turn is already underway (release() SIGTERMs the host-CLI's
    process group mid-turn) — simulated here by writing `.stop` from INSIDE the
    adapter call, never before `run()` starts. Proves the discrimination is checked
    fresh at catch-time, not a value latched at turn-start."""
    d, wdir = _fresh_worker_dir("tron-t1-race-")
    try:
        r = worker_runner.Runner("W", wdir, "s", None, "echo", "echo")
        ok("AC-1 race setup: .stop does not exist when the turn starts", not r._stopped())

        def _land_release():
            with open(r.stop_path, "w") as fh:
                fh.write("stop")

        r.adapter = _TeardownAdapter("host-cli stream ended before a result event",
                                     on_call=_land_release)
        rc = r.run()
        ok("AC-1 deliver-vs-release race resolves to teardown (rc=0), never a turn failure",
           rc == 0, f"rc={rc}")
        state = json.load(open(os.path.join(wdir, jobs.RUNNER_STATE)))
        ok("AC-1 race: state 'released', never 'error'",
           state.get("state") == "released", f"state={state}")
        events = _events(wdir)
        ok("AC-1 race: no turn_error recorded",
           not any(e.get("event") == "turn_error" for e in events), f"events={events}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ac2_mid_turn_drop_classified_as_refusal_recovered_via_fleet_hold():
    for label, wording in (
        ("process-exit (:153)", "host-cli process exited before a result event"),
        ("stream-end (:157)", "host-cli stream ended before a result event"),
    ):
        d, wdir = _fresh_worker_dir("tron-t1-genuine-")
        try:
            r = worker_runner.Runner("W", wdir, "s", None, "echo", "echo")
            r.adapter = _TeardownAdapter(wording)   # NOT stopped — a turn was genuinely owed
            rc = r.run()
            ok(f"AC-2 {label} genuine drop is a real turn failure (rc=1)", rc == 1, f"rc={rc}")
            state = json.load(open(os.path.join(wdir, jobs.RUNNER_STATE)))
            ok(f"AC-2 {label} worker state is 'error' (jobs.is_alive() False -> sweep recovers)",
               state.get("state") == "error", f"state={state}")
            events = _events(wdir)
            err = next((e for e in events if e.get("event") == "turn_error"), None)
            ok(f"AC-2 {label} recorded kind is 'RunnerRefusal' — never a bare RuntimeError "
               "or the adapter-internal HostStreamEnded",
               err is not None and err.get("kind") == "RunnerRefusal", f"events={events}")
            ok(f"AC-2 {label} jobs.last_turn_error_kind reads the SAME structural field the "
               "fleet-hold sweep uses (fsm.py:3331 _refusal_death)",
               jobs.last_turn_error_kind(wdir) == "RunnerRefusal")
        finally:
            shutil.rmtree(d, ignore_errors=True)


def ac2_runner_refusal_docstring_covers_the_no_answer_mode():
    doc = (worker_runner.RunnerRefusal.__doc__ or "").lower()
    ok("AC-2 RunnerRefusal's docstring documents the broadened 'no answer' mode "
       "(no name/meaning inconsistency between the class and its two raise paths)",
       "no answer" in doc or "never answered" in doc)
    ok("AC-2 RunnerRefusal's docstring still documents the original 'host answered' mode",
       "answered" in doc)
    ok("AC-2 RunnerRefusal's docstring states the fleet-hold consequence (two in-window "
       "drops engage the hold; self-clears via canary)",
       "canary" in doc and ("hold" in doc))


def ac1_stopped_flag_alone_also_resolves_to_teardown():
    """The stop/release state is `_stopped()` (self._stop OR the .stop file) — this
    proves the in-process SIGTERM-set flag path (not just the on-disk sentinel) is
    honored too, so a signal-only release (no .stop write reached yet) still tears
    down cleanly."""
    d, wdir = _fresh_worker_dir("tron-t1-sigflag-")
    try:
        r = worker_runner.Runner("W", wdir, "s", None, "echo", "echo")
        r.adapter = _TeardownAdapter("host-cli process exited before a result event")
        r._stop = True   # simulates the SIGTERM handler having already fired
        rc = r.run()
        ok("AC-1 the in-process _stop flag (SIGTERM handler) alone also resolves to teardown",
           rc == 0, f"rc={rc}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════════
# T2 (AC-3/AC-4): a self-contained `log` job settles on its own turn-done
# ══════════════════════════════════════════════════════════════════════════════════

def _eng(block="A-01", status="🔄"):
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False   # real _to_worker sends bump mbox_seq — the ACTUAL dispatch mechanism
    return eng


def _arch_idle(eng):
    w = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
         "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
    eng.st.workers.append(w)
    return w


def ac3_log_job_self_settles_on_its_own_turn_done():
    eng = _eng()
    arch = _arch_idle(eng)
    eng.st.architect_queue.append({"kind": "log", "type": "code", "block": "adhoc"})
    eng._pump_architect()
    ok("T2 setup: log job dispatched, architect busy",
       arch.get("status") == "busy" and (arch.get("current_job") or {}).get("kind") == "log",
       f"arch={arch}")
    dispatch_seq = arch.get("log_dispatch_seq")
    ok("T2 setup: dispatch stamped log_dispatch_seq at the delivery seq",
       dispatch_seq and dispatch_seq == arch.get("mbox_seq"), f"arch={arch}")

    orig_hwm = jobs.read_hwm
    jobs.read_hwm = lambda wdir: dispatch_seq   # the runner's OWN turn on this job just finished
    try:
        eng._drive_architect_liveness()
    finally:
        jobs.read_hwm = orig_hwm
    ok("AC-3 the log job settles the instant its own turn completes (hwm advance), "
       "with no dependence on a separately-tagged report",
       arch.get("current_job") is None and arch.get("status") == "idle", f"arch={arch}")
    ok("AC-3 the architect opens NO architect-idle-cap case after a completed log turn",
       not arch.get("job_case")
       and not any(c.get("kind") == "architect" for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")
    ok("T2 the self-settle routes through the SAME bookkeeping _architect_advance uses "
       "(idle timers + the log-settle marker itself all cleared, never a parallel half-settle)",
       not arch.get("job_idle_since") and not arch.get("job_nudged_at")
       and not arch.get("log_dispatch_seq"), f"arch={arch}")


def ac3_settle_pumps_the_next_queued_architect_job():
    eng = _eng()
    arch = _arch_idle(eng)
    eng.st.architect_queue.append({"kind": "log", "type": "code", "block": "adhoc"})
    eng.st.architect_queue.append({"kind": "forward", "block": "A-02"})
    eng._pump_architect()
    dispatch_seq = arch.get("log_dispatch_seq")
    orig_hwm = jobs.read_hwm
    jobs.read_hwm = lambda wdir: dispatch_seq
    try:
        eng._drive_architect_liveness()
    finally:
        jobs.read_hwm = orig_hwm
    ok("T2 settling the log job pumps the NEXT queued architect job "
       "(_architect_advance's own bookkeeping, never a parallel half-settle)",
       (arch.get("current_job") or {}).get("kind") == "forward"
       and (arch.get("current_job") or {}).get("block") == "A-02"
       and arch.get("status") == "busy", f"arch={arch}")


def ac3_forward_job_is_never_self_settled_off_hwm_scope_check():
    eng = _eng()
    arch = _arch_idle(eng)
    eng.st.architect_queue.append({"kind": "forward", "block": "A-01"})
    eng._pump_architect()
    ok("T2 scope: dispatching a forward job never stamps log_dispatch_seq",
       not arch.get("log_dispatch_seq"), f"arch={arch}")
    orig_hwm, orig_idle = jobs.read_hwm, jobs.runner_idle
    jobs.read_hwm = lambda wdir: 999999          # hwm far ahead — must not matter for forward/reconcile
    jobs.runner_idle = lambda wid, idx=None: False   # still genuinely working
    try:
        eng._drive_architect_liveness()
    finally:
        jobs.read_hwm, jobs.runner_idle = orig_hwm, orig_idle
    ok("AC-3 scope: a forward job is NEVER self-settled by hwm — only `log` jobs are "
       "(forward/reconcile/triage keep their tagged-report path, unchanged)",
       arch.get("current_job") is not None and arch.get("status") == "busy", f"arch={arch}")


def ac3_idle_renudge_re_marks_log_dispatch_seq_at_the_latest_delivery():
    eng = _eng()
    arch = _arch_idle(eng)
    eng.st.architect_queue.append({"kind": "log", "type": "code", "block": "adhoc"})
    eng._pump_architect()
    first_seq = arch.get("log_dispatch_seq")
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    orig_hwm, orig_idle = jobs.read_hwm, jobs.runner_idle
    jobs.read_hwm = lambda wdir: 0            # nothing consumed yet
    jobs.runner_idle = lambda wid, idx=None: True
    try:
        eng._drive_architect_liveness()       # anchors job_idle_since at 1000.0
        clock["t"] = 1000.0 + eng._pace("gate_nudge_after", 2) + 1
        eng._drive_architect_liveness()       # crosses the nudge threshold -> re-delivers
    finally:
        jobs.read_hwm, jobs.runner_idle = orig_hwm, orig_idle
    second_seq = arch.get("log_dispatch_seq")
    ok("T2 an idle re-nudge re-marks log_dispatch_seq at the LATEST re-delivery "
       "(so a re-sent log order settles against the message that was actually re-sent)",
       second_seq is not None and first_seq is not None and second_seq > first_seq,
       f"first={first_seq} second={second_seq}")


def ac4_unfinished_log_job_still_opens_the_idle_cap_case():
    eng = _eng()
    arch = _arch_idle(eng)
    eng.st.architect_queue.append({"kind": "log", "type": "code", "block": "adhoc"})
    eng._pump_architect()
    dispatch_seq = arch.get("log_dispatch_seq")
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    orig_hwm, orig_idle = jobs.read_hwm, jobs.runner_idle
    # hwm never catches up (the turn genuinely never finished) — yet the runner reads
    # idle (crashed silently / never picked up the message before going idle again).
    jobs.read_hwm = lambda wdir: max(0, dispatch_seq - 1)
    jobs.runner_idle = lambda wid, idx=None: True
    try:
        eng._drive_architect_liveness()
        ok("AC-4 setup: idle anchor starts", arch.get("job_idle_since") == 1000.0, f"arch={arch}")
        clock["t"] = 1000.0 + eng._pace("gate_idle_cap", 3) + 1
        eng._drive_architect_liveness()
    finally:
        jobs.read_hwm, jobs.runner_idle = orig_hwm, orig_idle
    ok("AC-4 a genuinely unfinished/unreported log job STILL opens the architect-idle-cap "
       "case exactly as before (the backstop is narrowed, never removed)",
       arch.get("job_case") in eng.st.pending_cases
       and eng.st.pending_cases[arch["job_case"]].get("kind") == "architect", f"arch={arch}")


def ac4_genuinely_working_log_job_never_accrues_idle_no_reuse_of_gate_idle_cap():
    """AC-5's companion invariant, pinned here for T2's own arm: a genuinely busy log
    turn (hwm hasn't caught up AND the runner still reports working) must never accrue
    idle time — unaffected by the self-settle addition, and no widening of
    gate_idle_cap itself (it stays the ONE shared pace knob, read via self._pace, never
    a second/parallel threshold)."""
    eng = _eng()
    arch = _arch_idle(eng)
    eng.st.architect_queue.append({"kind": "log", "type": "code", "block": "adhoc"})
    eng._pump_architect()
    dispatch_seq = arch.get("log_dispatch_seq")
    orig_hwm, orig_idle = jobs.read_hwm, jobs.runner_idle
    jobs.read_hwm = lambda wdir: max(0, dispatch_seq - 1)   # not yet settled
    jobs.runner_idle = lambda wid, idx=None: False          # genuinely still working
    try:
        eng._now_s = lambda: 99999.0
        eng._drive_architect_liveness()
        ok("T2 a genuinely busy (not-yet-settled, not-idle) log turn never accrues idle time",
           not arch.get("job_idle_since") and not arch.get("job_case"), f"arch={arch}")
    finally:
        jobs.read_hwm, jobs.runner_idle = orig_hwm, orig_idle


def main():
    for fn in sorted(k for k in globals() if k.startswith(("ac1_", "ac2_", "ac3_", "ac4_"))):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
