"""block_01_21_test — worker model as a declared, fail-closed input + orphan-proof
worker teardown (01-21). Standalone runner convention (exit 0 = pass, no tokens, no
network, no real `claude` — every spawn below uses the echo adapter or a plain python
stand-in process; SAFETY: this suite never runs a live/non-dry engine or a real worker).

Covers:
  T1 (AC-1/AC-2) the worker model is an explicit, engine-owned, FAIL-CLOSED input:
      jobs.spawn_runner's constructed argv always carries the resolved --model; with no
      model configured anywhere it refuses BEFORE spawning any process
      (WorkerModelUnconfigured); the host-CLI adapter's own argv carries --model too and
      refuses independently (defense in depth); worker_runner.py's CLI requires --model
      (a direct/manual invocation with none refuses, argparse); fsm._spawn resolves the
      model from PROJECT CONFIG (roles.yaml's per-role `model:` since ADR-0002 D4/01-33 —
      formerly knobs.yaml's `worker_model` map) and threads it explicitly — never an
      ambient default. (The former lint L25, which flagged a knobs.yaml with the
      `worker_model` key missing, is retired along with the knob: roles.yaml's own
      fail-closed boot validation — RolesConfig._validate, at Engine construction — now
      covers this, strictly stronger than a lint presence-check.)
  T2 (AC-3/AC-4) orphan-proof teardown: release/kill_hard target the runner's WHOLE
      PROCESS GROUP (a forked child dies with it, never just the runner pid);
      jobs.reap_all() group-kills every worker alive in ITS OWN store only — a sibling
      store (a concurrently-live engine's own instance) is never touched; a fresh
      Engine.start() (crash-recovery: no live session already owns this instance) reaps
      the store before any dispatch, skipped entirely under dry; wake.run's shutdown
      path (session ended / SIGTERM) reaps this instance's own leftover workers too.

Run: python3 engine/block_01_21_test.py   (exit 0 = pass).
"""
import os
import sys
import json
import time
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"
os.environ.setdefault("TRON_RUNNER_POLL_S", "0.05")

import jobs                    # noqa: E402
import wake                    # noqa: E402
import lint                    # noqa: E402
import worker_runner           # noqa: E402
from fsm import Engine         # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _wait(pred, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.1)
    return False


def _pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError, TypeError):
        return False
    try:
        gone, _ = os.waitpid(int(pid), os.WNOHANG)   # reap a zombie child -> report dead
        if gone == int(pid):
            return False
    except (ChildProcessError, OSError, ValueError):
        pass
    return True


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_runner_state(wd, pid):
    os.makedirs(wd, exist_ok=True)
    with open(os.path.join(wd, jobs.RUNNER_STATE), "w") as fh:
        json.dump({"worker_id": os.path.basename(wd), "session_id": "s", "pid": pid,
                   "state": "idle", "turns": 1, "updated_at": _now_iso()}, fh)


# A plain python stand-in for a runner that forked a child (AC-3's exact scenario),
# launched the SAME way jobs.spawn_runner launches the real runner (start_new_session=
# True), so os.killpg on the leader's own pid exercises the identical mechanism T2 fixes
# — token-free, no worker_runner/echo-adapter machinery needed to prove the group-kill.
_LEADER_SCRIPT = (
    "import json, subprocess, sys, time\n"
    "pidfile = sys.argv[1]\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
    "with open(pidfile, 'w') as fh:\n"
    "    json.dump({'child_pid': child.pid}, fh)\n"
    "time.sleep(120)\n"
)


def _spawn_group(store, wid):
    """Launch a leader (start_new_session=True) that forks a child, register it in
    `store` as worker `wid` (a hand-written runner.json — jobs.py's own store format),
    and return (leader_pid, child_pid) once both are confirmed up."""
    wd = os.path.join(store, wid)
    os.makedirs(wd, exist_ok=True)
    script = os.path.join(store, f"{wid}-leader.py")
    with open(script, "w") as fh:
        fh.write(_LEADER_SCRIPT)
    pidfile = os.path.join(store, f"{wid}-pids.json")
    leader = subprocess.Popen(
        [sys.executable, script, pidfile], start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait(lambda: os.path.exists(pidfile))
    child_pid = (json.load(open(pidfile)) if os.path.exists(pidfile) else {}).get("child_pid")
    _write_runner_state(wd, leader.pid)
    return leader.pid, child_pid


# ══ T1 (AC-1): the worker model is an explicit input; argv always carries it ══

def t1_spawn_runner_argv_carries_resolved_model():
    store = tempfile.mkdtemp(prefix="tron-argv-")
    wd = os.path.join(store, "ENG-ARGV")
    captured = {}

    class _FakeProc:
        def poll(self):
            return None

    def fake_popen(cmd, **kw):
        captured["cmd"] = cmd
        return _FakeProc()

    orig = jobs.subprocess.Popen
    jobs.subprocess.Popen = fake_popen
    try:
        jobs.spawn_runner("ENG-ARGV", wd, "sess-x", cwd=store, adapter="echo",
                          model="claimed-model-9", settle_s=0.05)
    finally:
        jobs.subprocess.Popen = orig
    cmd = captured.get("cmd") or []
    ok("T1 (AC-1) spawn_runner's constructed argv always carries the resolved --model",
       "--model" in cmd and cmd[cmd.index("--model") + 1] == "claimed-model-9", f"cmd={cmd}")


def t1_hostcli_adapter_argv_carries_model():
    captured = {}

    class _FakeProc:
        stdin = None
        stdout = None

        def poll(self):
            return None

    def fake_popen(cmd, **kw):
        captured["cmd"] = cmd
        return _FakeProc()

    orig = worker_runner.subprocess.Popen
    worker_runner.subprocess.Popen = fake_popen
    try:
        adapter = worker_runner.HostCliAdapter("some-runtime", "sess-z", "/tmp", model="pinned-model")
        adapter._ensure()
    finally:
        worker_runner.subprocess.Popen = orig
    cmd = captured.get("cmd") or []
    ok("T1 (AC-1) HostCliAdapter's own argv carries --model (the runtime-flag-spelling layer)",
       "--model" in cmd and cmd[cmd.index("--model") + 1] == "pinned-model", f"cmd={cmd}")


def t1_fsm_spawn_threads_knobs_worker_model_into_spawn_runner():
    # NOTE (01-33, ADR-0002 D4): the model source moved from knobs.yaml's `worker_model`
    # map to roles.yaml's per-role `model:` field entirely — see block_01_33_test.py for
    # the full fail-closed/per-role coverage. This case keeps proving the original 01-21
    # intent: fsm._spawn resolves from PROJECT CONFIG (now roles.yaml) and threads it
    # explicitly, never an ambient default.
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.roles.roles["engineer"]["model"] = "project-pinned-model"
    captured = {}
    orig = jobs.spawn_runner

    def fake_spawn(*a, **k):
        captured.update(k)
        return {"session_id": "s", "worker_id": a[0]}

    jobs.spawn_runner = fake_spawn
    try:
        eng._spawn("ENG-A-01", "engineer", block="A-01")
    finally:
        jobs.spawn_runner = orig
    ok("T1 (AC-1) fsm._spawn resolves the model from roles.yaml (project config) and "
       "threads it explicitly into jobs.spawn_runner — never an ambient default",
       captured.get("model") == "project-pinned-model", f"captured={captured}")


# ══ T1 (AC-2): fail-closed with no model configured anywhere ══

def t1_spawn_runner_fails_closed_without_any_model():
    store = tempfile.mkdtemp(prefix="tron-nomodel-")
    wd = os.path.join(store, "ENG-NOMODEL")
    spawned = []
    orig_popen = jobs.subprocess.Popen
    jobs.subprocess.Popen = lambda *a, **k: spawned.append(1)
    had_env = "TRON_WORKER_MODEL" in os.environ
    orig_env = os.environ.pop("TRON_WORKER_MODEL", None)   # simulate the override unset too
    try:
        raised = False
        try:
            jobs.spawn_runner("ENG-NOMODEL", wd, "sess-y", cwd=store, adapter="echo", model=None)
        except jobs.WorkerModelUnconfigured:
            raised = True
        ok("T1 (AC-2) spawn_runner refuses (fail-closed) with no model configured anywhere",
           raised)
        ok("T1 (AC-2) the fail-closed guard fires BEFORE any process is spawned",
           spawned == [], f"spawned={spawned}")
    finally:
        jobs.subprocess.Popen = orig_popen
        if had_env:
            os.environ["TRON_WORKER_MODEL"] = orig_env


def t1_hostcli_adapter_refuses_without_model():
    adapter = worker_runner.HostCliAdapter("some-runtime", "sess-z2", "/tmp", model=None)
    raised = False
    try:
        adapter._ensure()
    except RuntimeError:
        raised = True
    ok("T1 (AC-2) HostCliAdapter itself refuses to build argv with no model (defense in depth)",
       raised)


def t1_worker_runner_cli_requires_model_flag():
    d = tempfile.mkdtemp(prefix="tron-clim-")
    wd = os.path.join(d, "w")
    os.makedirs(wd)
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "worker_runner.py"),
         "--worker-id", "X", "--worker-dir", wd, "--session-id", "s"],
        capture_output=True, text=True, timeout=10)
    ok("T1 (AC-2) worker_runner.py's own CLI refuses (argparse, no default) with no --model",
       proc.returncode != 0 and "--model" in (proc.stderr or ""),
       f"rc={proc.returncode} err={proc.stderr!r}")


def t1_lint_no_longer_checks_a_retired_knob():
    """SUPERSEDED by block 01-33 (ADR-0002 D4): the former L25 (`worker_model` knob
    presence) and L12 (`session.persistent_architect` shape) are retired along with the
    knobs they checked — both moved to roles.yaml, fail-closed validated at Engine
    construction (RolesConfig._validate), strictly stronger than a lint presence-check.
    This guards the narrow regression: lint._composition never re-demands either knob."""
    comp = {"knobs": {"worker_count": 1, "wake_cooldown_sec": 5, "wake_ceiling_sec": 30},
            "cadence": {}}
    results = lint._composition(comp, {})
    ok("T1 lint no longer has an L25 rule (worker_model knob retired)",
       not any(r.rule.startswith("L25") for r in results))
    ok("T1 lint no longer has an L12 rule (session.persistent_architect knob retired)",
       not any(r.rule.startswith("L12") for r in results))
    ok("T1 lint._composition runs clean with neither knob present at all",
       all(r.ok for r in results), f"failures={[r.rule for r in results if not r.ok]}")


# ══ T2 (AC-3): release/kill_hard group-kill — a forked child cannot survive its runner ══

def t2_release_group_kills_the_forked_child():
    store = tempfile.mkdtemp(prefix="tron-grp-")
    jobs.configure(store)
    leader_pid, child_pid = _spawn_group(store, "ENG-GRP-1")
    ok("T2 setup: the leader and its forked child are both alive",
       _pid_alive(leader_pid) and _pid_alive(child_pid))
    jobs.release("ENG-GRP-1")
    ok("T2 release group-kills the runner (leader)", _wait(lambda: not _pid_alive(leader_pid)))
    ok("T2 release group-kills the FORKED CHILD too — no survivor in the group",
       _wait(lambda: not _pid_alive(child_pid)))


def t2_kill_hard_group_kills_the_forked_child():
    store = tempfile.mkdtemp(prefix="tron-grp2-")
    jobs.configure(store)
    leader_pid, child_pid = _spawn_group(store, "ENG-GRP-2")
    jobs.kill_hard("ENG-GRP-2")
    ok("T2 kill_hard group-kills the runner (leader)", _wait(lambda: not _pid_alive(leader_pid)))
    ok("T2 kill_hard group-kills the forked child too",
       _wait(lambda: not _pid_alive(child_pid)))


# ══ T2 (AC-4): the engine-death reaper — scoped to THIS store; startup + shutdown ══

def t2_reap_all_kills_only_its_own_store_never_a_sibling():
    storeA = tempfile.mkdtemp(prefix="tron-grpA-")
    storeB = tempfile.mkdtemp(prefix="tron-grpB-")
    jobs.configure(storeA)
    a_leader, a_child = _spawn_group(storeA, "ENG-A")
    jobs.configure(storeB)
    b_leader, b_child = _spawn_group(storeB, "ENG-B")
    try:
        jobs.configure(storeA)
        killed = jobs.reap_all()
        ok("T2 (AC-4) reap_all kills every worker alive in ITS OWN store",
           killed == ["ENG-A"] and _wait(lambda: not _pid_alive(a_leader))
           and _wait(lambda: not _pid_alive(a_child)), f"killed={killed}")
        ok("T2 (AC-4) a concurrently-live engine's DIFFERENT store is left untouched",
           _pid_alive(b_leader) and _pid_alive(b_child))
    finally:
        jobs.configure(storeB)
        jobs.reap_all()      # cleanup: don't leak the sibling's processes past this test


def t2_engine_start_reaps_before_dispatch_when_not_dry():
    ctx, _ = build(blocks=[])     # empty pipeline -> start() returns before any spawn (safety)
    eng = Engine(ctx)
    eng.dry = False
    calls = []
    orig = jobs.reap_all
    jobs.reap_all = lambda: calls.append(1) or []
    try:
        eng.start(1)
    finally:
        jobs.reap_all = orig
    ok("T2 (AC-4) a fresh Engine.start() (crash-recovery startup) reaps this instance's "
       "own store before any dispatch begins", calls == [1], f"calls={calls}")


def t2_engine_start_skips_reap_under_dry():
    ctx, _ = build(blocks=[])
    eng = Engine(ctx)             # TRON_DRY=1 (module-level) -> dry True by default
    calls = []
    orig = jobs.reap_all
    jobs.reap_all = lambda: calls.append(1) or []
    try:
        eng.start(1)
    finally:
        jobs.reap_all = orig
    ok("T2 a dry start never touches jobs.reap_all (no real store, never a real process)",
       calls == [], f"calls={calls}")


def t2_wake_run_shutdown_reaps_this_instances_leftover_workers():
    ctx, _ = build(blocks=[])
    os.makedirs(ctx.workers_dir, exist_ok=True)
    leader_pid, child_pid = _spawn_group(ctx.workers_dir, "GHOST-1")
    try:
        # No session was ever started -> session_live(ctx) is False immediately, so the
        # loop body never runs at all; wake.run falls straight through to its shutdown
        # `finally` — exactly what "the engine died/exited" looks like here.
        wake.run(ctx)
        ok("T2 (AC-4) wake.run's shutdown reap kills a leftover worker of this instance",
           _wait(lambda: not _pid_alive(leader_pid)))
        ok("T2 (AC-4) ...and the child it had forked too (group-kill, not pid-only)",
           _wait(lambda: not _pid_alive(child_pid)))
    finally:
        for pid in (leader_pid, child_pid):
            if pid and _pid_alive(pid):
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass


def main():
    for fn in sorted(k for k in globals() if k.startswith(("t1_", "t2_"))):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
