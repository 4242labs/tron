"""block_01_10_test — acceptance for the pilot-defect remediation block (01-10).

Token-free. Covers the five defects the first live trivial pilot surfaced:
  AC-1  a no-remote project boots (trunk.refresh reads HEAD in place, no fetch halt)   [F1]
  AC-3  the classifier prompt goes on stdin, never argv (a `---`-leading context)      [F3]
  AC-4  worker.online is documented in tron.md AND wired in routing.yaml               [F4]
  AC-5  jobs.send is a mailbox append keyed by worker id; no --resume/--fork survives   [F5]
  AC-6  the runner delivers spawn + a mid-life message to a running worker, in order    [F5]
  AC-7  monotonic seq, at-least-once idempotent effect, high-water resume (no replay)   [F5]

The runner is exercised as a real subprocess with the token-free `echo` adapter — the full
pull-and-feed loop (mailbox -> one turn -> high-water -> repeat), lifecycle, and release.
"""
import os
import sys
import json
import time
import signal
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import util            # noqa: E402
import trunk           # noqa: E402
import judge           # noqa: E402
import jobs            # noqa: E402
from ctx import Ctx    # noqa: E402
from fsm import Engine  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── helpers ──
def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait(pred, timeout=12.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.15)
    return False


def _read(path):
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return ""


def _hwm(wd):
    v = _read(os.path.join(wd, jobs.HWM)).strip()
    return int(v) if v.isdigit() else 0


def _state(wd):
    try:
        with open(os.path.join(wd, jobs.RUNNER_STATE)) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _turns_done(wd):
    out = []
    for ln in _read(os.path.join(wd, jobs.TIMELINE)).splitlines():
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if e.get("event") == "turn_done":
            out.append(e["seq"])
    return out


def _pid_alive(pid):
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


def _mini_ctx(remote="__omit__"):
    d = tempfile.mkdtemp(prefix="tron-b1010-")
    for f in ("routing.yaml", "messages.yaml", "knobs.yaml", "tron.md"):
        shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
    shutil.copy(os.path.join(ROOT, "templates", "manifest.yaml"), os.path.join(d, "manifest.yaml"))
    shutil.copytree(os.path.join(ROOT, "prompts"), os.path.join(d, "prompts"))
    if remote != "__omit__":                      # write a project.yaml with (or without) a remote
        repo = {"root": d, "main_branch": "main"}
        if remote is not None:
            repo["remote"] = remote
        with open(os.path.join(d, "project.yaml"), "w") as fh:
            json.dump({"repo": repo}, fh)          # JSON is valid YAML -> the loader reads it
    return Ctx(d)


# ── AC-1 (F1): local / no-remote trunk mode ──
def t_no_remote_trunk():
    d = tempfile.mkdtemp(prefix="tron-localrepo-")
    _git("init", "-q", "-b", "main", cwd=d)
    _git("config", "user.email", "t@t.io", cwd=d)
    _git("config", "user.name", "t", cwd=d)
    with open(os.path.join(d, "f.txt"), "w") as fh:
        fh.write("x")
    _git("add", ".", cwd=d)
    _git("commit", "-qm", "init", cwd=d)

    okb, detail = trunk.refresh(d, "main", dry=False, remote=None)
    ok("AC-1 remote=None -> read in place (no halt)", okb, detail)
    okb2, _ = trunk.refresh(d, "main", dry=False, remote="none")
    ok("AC-1 remote='none' -> read in place", okb2)
    # HEAD is still readable in local mode (what the engine pins each tick)
    ok("AC-1 head_sha resolves locally", bool(trunk.head_sha(d, dry=False)))
    # The remote path is UNCHANGED: with a declared remote but no origin, it still fetch-fails.
    okr, _ = trunk.refresh(d, "main", dry=False, remote="org/repo")
    ok("AC-1 remote path still fetch-refreshes (unchanged)", not okr)


def t_fsm_threads_remote():
    """The regression the isolated unit missed: the fsm MUST pass repo.remote into trunk.refresh,
    or every project runs local mode and TRON goes blind to trunk. Exercises fsm -> refresh."""
    cap = {}

    def fake_refresh(root, main_branch, dry, remote=None):
        cap["remote"] = remote
        return True, "stub"

    r0, p0, h0 = trunk.refresh, trunk.open_prs, trunk.head_sha
    trunk.refresh = fake_refresh
    trunk.open_prs = lambda *a, **k: {}
    trunk.head_sha = lambda *a, **k: "abc123"
    try:
        eng = Engine(_mini_ctx(remote="acme/widgets"))
        eng.dry = False
        eng._refresh_from_trunk(count=False)
        got_remote = cap.get("remote")
        cap.clear()
        eng2 = Engine(_mini_ctx(remote=None))     # project.yaml with no remote declared
        eng2.dry = False
        eng2._refresh_from_trunk(count=False)
        got_none = cap.get("remote")
    finally:
        trunk.refresh, trunk.open_prs, trunk.head_sha = r0, p0, h0
    ok("AC-1 fsm threads repo.remote into trunk.refresh", got_remote == "acme/widgets")
    ok("AC-1 no declared remote -> None passed (local mode)", got_none is None)


# ── AC-3 (F3): classifier prompt on stdin ──
def t_judge_stdin():
    ctx = Ctx(ROOT)   # ROOT ships tron.md (---frontmatter-leading) + routing.yaml
    cap = {}
    real = judge.subprocess.run

    class R:
        stdout = '{"tag": "worker.progress", "slots": {}, "confidence": 1.0}'

    def fake(cmd, **kw):
        cap["cmd"] = cmd
        cap["input"] = kw.get("input")
        return R()

    judge.subprocess.run = fake
    try:
        judge._call_llm("classify_message", {"text": "still going"}, ctx)
    finally:
        judge.subprocess.run = real

    ok("AC-3 prompt delivered on stdin", bool(cap.get("input")))
    ok("AC-3 a ---frontmatter context reaches stdin, not argv",
       "---" in (cap.get("input") or "") and not any("---" in a for a in cap.get("cmd", [])))
    ok("AC-3 model/tier flags stay argv", "--model" in cap.get("cmd", []))
    ok("AC-3 no bare prompt positional arg", cap["cmd"][-1] == judge.TIER["classify_message"])


# ── AC-4 (F4): worker.online documented + wired ──
def t_worker_online():
    tron_md = _read(os.path.join(ROOT, "tron.md"))
    ok("AC-4 worker.online documented in tron.md catalog", "worker.online" in tron_md)
    routing = util.load_yaml(os.path.join(ROOT, "routing.yaml"))
    tags = routing.get("tags", {})
    ok("AC-4 worker.online tag wired in routing.yaml", "worker.online" in tags)
    ok("AC-4 worker.online carries the online trigger",
       (tags.get("worker.online") or {}).get("trigger") == "worker:online")


# ── AC-5 (F5): jobs.send is a mailbox append; no --resume/--fork in the worker path ──
def t_mailbox_append():
    wd = tempfile.mkdtemp(prefix="tron-wd-")
    jobs.send(wd, 1, "assign.engineer", "build A-01")
    lines = _read(jobs.mailbox_path(wd)).splitlines()
    ok("AC-5 append exactly one line", len(lines) == 1)
    rec = json.loads(lines[0])
    ok("AC-5 line shape {seq,ts,kind,text}", set(rec) == {"seq", "ts", "kind", "text"})
    ok("AC-5 seq/kind/text carried",
       rec["seq"] == 1 and rec["kind"] == "assign.engineer" and rec["text"] == "build A-01")
    jobs_src = _read(os.path.join(HERE, "jobs.py"))
    fsm_src = _read(os.path.join(HERE, "fsm.py"))
    ok("AC-5 no --resume in the engine->worker path",
       "--resume" not in jobs_src and "--resume" not in fsm_src)
    ok("AC-5 no --fork in the engine->worker path",
       "--fork" not in jobs_src and "--fork" not in fsm_src)


# ── AC-7 (F5): monotonic seq + at-least-once idempotent effect, at _to_worker ──
def t_seq_idempotent():
    ctx = _mini_ctx()
    eng = Engine(ctx)
    eng.dry = False
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01"})
    eng._to_worker("ENG-A-01", "first", "assign.engineer")
    eng._to_worker("ENG-A-01", "second", "gate.merge")
    wd = ctx.worker_dir("ENG-A-01")
    seqs = [json.loads(l)["seq"] for l in _read(jobs.mailbox_path(wd)).splitlines()]
    ok("AC-7 monotonic seq via _to_worker", seqs == [1, 2])
    # crash-before-save: the seq-2 bump on the worker record never persisted -> a re-emit
    # recomputes the SAME seq (the runner dedupes it by high-water).
    eng.st.workers[0]["mbox_seq"] = 1
    eng._to_worker("ENG-A-01", "second-again", "gate.merge")
    seqs2 = [json.loads(l)["seq"] for l in _read(jobs.mailbox_path(wd)).splitlines()]
    ok("AC-7 at-least-once re-emit reuses the seq", seqs2 == [1, 2, 2])


# ── AC-6 (F5): the runner delivers spawn + a mid-life message, in order (echo adapter) ──
def t_runner_e2e():
    os.environ["TRON_RUNNER_POLL_S"] = "0.2"
    store = tempfile.mkdtemp(prefix="tron-store-")
    jobs.configure(store)
    wid = "ENG-A-01"
    wd = os.path.join(store, wid)
    os.makedirs(wd)
    jobs.send(wd, 1, "spawn.engineer", "persona onboarding")   # turn 1
    jobs.send(wd, 2, "assign.engineer", "build A-01")          # turn 2 (the assignment)
    rec = jobs.spawn_runner(wid, wd, "sess-uuid-1", cwd=store, adapter="echo")
    ok("AC-6 spawn_runner returns the engine-minted session", rec.get("session_id") == "sess-uuid-1")
    ok("AC-6 spawn + assignment delivered", _wait(lambda: _hwm(wd) >= 2))
    ok("AC-6 turns run in seq order", _turns_done(wd) == [1, 2])

    # a MID-LIFE message reaches the already-running worker (the pilot's blocker: it never did)
    jobs.send(wd, 3, "gate.changes", "operator requested changes before merge")
    ok("AC-6 mid-life message reaches a running worker", _wait(lambda: _hwm(wd) >= 3))

    # AC-7 dedup: re-append the SAME seq -> applied at most once
    jobs.send(wd, 3, "gate.changes", "duplicate re-emit")
    time.sleep(1.0)
    ok("AC-7 re-appended same seq applied once", _turns_done(wd).count(3) == 1)

    jobs.release(wid)
    ok("AC-7 release -> runner exits clean (released)",
       _wait(lambda: _state(wd).get("state") == "released"))


# ── AC-7 (F5): a restarted runner resumes from the high-water seq — no replay ──
def t_runner_resume():
    os.environ["TRON_RUNNER_POLL_S"] = "0.2"
    store = tempfile.mkdtemp(prefix="tron-store2-")
    jobs.configure(store)
    wid = "ENG-B-02"
    wd = os.path.join(store, wid)
    os.makedirs(wd)
    jobs.send(wd, 1, "spawn.engineer", "persona")
    jobs.send(wd, 2, "assign.engineer", "build B-02")
    jobs.send(wd, 3, "gate.merge", "merge approved")
    with open(os.path.join(wd, jobs.HWM), "w") as fh:
        fh.write("2")   # as if seq 1 & 2 already ran before the restart
    jobs.spawn_runner(wid, wd, "sess-uuid-2", cwd=store, adapter="echo")
    ok("AC-7 resume advances past high-water", _wait(lambda: _hwm(wd) >= 3))
    ok("AC-7 resume replays nothing at/under high-water", _turns_done(wd) == [3])
    jobs.release(wid)


def t_runner_crash_resume():
    """A LIVE runner is hard-killed (SIGKILL — no graceful released) after processing to its
    high-water; a fresh runner on the same dir resumes from it, replaying nothing (recover corner)."""
    os.environ["TRON_RUNNER_POLL_S"] = "0.2"
    store = tempfile.mkdtemp(prefix="tron-crash-")
    jobs.configure(store)
    wid = "ENG-C-03"
    wd = os.path.join(store, wid)
    os.makedirs(wd)
    jobs.send(wd, 1, "spawn.engineer", "persona")
    jobs.send(wd, 2, "assign.engineer", "build C-03")
    jobs.spawn_runner(wid, wd, "sess-crash", cwd=store, adapter="echo")
    ok("AC-7 crash: live runner reaches high-water", _wait(lambda: _hwm(wd) >= 2))
    pid = _state(wd).get("pid")
    os.kill(int(pid), signal.SIGKILL)                       # hard crash: no clean shutdown
    ok("AC-7 crash: runner is dead", _wait(lambda: not _pid_alive(pid), 5))
    ok("AC-7 crash: sweep sees it as not-alive", not jobs.is_alive(wid))
    jobs.send(wd, 3, "gate.merge", "merge approved")        # a message arrives while dead
    jobs.spawn_runner(wid, wd, "sess-crash", cwd=store, adapter="echo")   # restart
    ok("AC-7 restart advances to the new seq", _wait(lambda: _hwm(wd) >= 3))
    ok("AC-7 crash-restart replays nothing at/under high-water", _turns_done(wd) == [1, 2, 3])
    jobs.release(wid)


def main():
    for t in (t_no_remote_trunk, t_fsm_threads_remote, t_judge_stdin, t_worker_online,
              t_mailbox_append, t_seq_idempotent, t_runner_e2e, t_runner_resume,
              t_runner_crash_resume):
        try:
            t()
        except Exception as e:
            ok(f"{t.__name__} raised", False, repr(e))
    passed = sum(1 for _, c, _ in _results if c)
    print(f"block_01_10_test: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
