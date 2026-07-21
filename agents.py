"""tron-reborn — agents.

An agent is a persistent `claude -p --resume` CLI session, cwd-locked to
its arena. Identity is by construction: the engine knows which session it
called — there is no sender field to forge. Every turn, both directions,
lands on the transcript.
"""

import json
import os
import subprocess
import threading
from pathlib import Path

import events
from transcript import log_entry, operator

MODELS = {
    "worker": "claude-sonnet-5",
    "reviewer": "claude-sonnet-5",
    "architect": "claude-opus-4-8",
    "aide": "claude-opus-4-8",      # the operator's LLM advisor (bootup)
    "player": "claude-sonnet-5",
}
CLAUDE = "claude"             # the CLI binary (selftests substitute a fake)
TURN_TIMEOUT_S = 15 * 60      # default wall-clock budget per turn
PROBE_TIMEOUT_S = 3 * 60
PROBE = ("liveness probe from the engine — your last turn overran its "
         "wall-clock budget and was interrupted. Reply with ONE line: what "
         "you were doing and whether your working copy holds unfinished "
         "state. Do not resume the work in this turn.")


def kill_strays(*areas):
    """SIGKILL agent processes still working any area; returns their pids.

    One engine owns a project. If the engine crashes mid-turn its agent
    process survives and keeps mutating the repository — so at boot, any
    agent process living in the project or its arenas is a stray.
    """
    areas = tuple(str(Path(a).resolve()) for a in areas)
    killed = []
    for p in Path("/proc").glob("[0-9]*"):
        try:
            cwd = os.readlink(p / "cwd")
            if ((cwd in areas
                 or cwd.startswith(tuple(a + "/" for a in areas)))
                    and b"claude" in (p / "cmdline").read_bytes()
                    and int(p.name) != os.getpid()):
                os.kill(int(p.name), 9)
                killed.append(int(p.name))
        except OSError:
            continue
    return killed


class Agent:
    def __init__(self, role, cwd, budget=None):
        self.role, self.cwd, self.session = role, str(cwd), None
        self.budget = budget or TURN_TIMEOUT_S  # seconds of wall-clock/turn
        self._lock = threading.Lock()   # one session = one turn at a time

    def _turn(self, message, timeout):
        cmd = [CLAUDE, "-p", message, "--model", MODELS[self.role],
               "--output-format", "json"]
        if self.session:
            cmd += ["--resume", self.session]
        if self.role != "architect":  # builds/tests inside the target repo only
            cmd += ["--dangerously-skip-permissions"]
        log_entry(f"TRON -> {self.role}", message)
        proc = subprocess.run(cmd, cwd=self.cwd, capture_output=True,
                              text=True, timeout=timeout)
        try:
            data = json.loads(proc.stdout or "{}")
        except ValueError:
            data = {}
        self.session = data.get("session_id", self.session)
        reply = data.get("result") or proc.stdout or proc.stderr or ""
        log_entry(f"{self.role} -> TRON", reply)
        return reply

    def turn(self, message):
        """One reliable turn — a seat is never surrendered without being
        TALKED to first. An overrunning turn is interrupted (the SESSION
        survives — --resume), the seat is probed; a responsive seat gets
        the message re-issued once. Only silent-through-the-probe, or a
        second overrun, reaches the operator."""
        with self._lock:
            for attempt in (1, 2):
                try:
                    return self._turn(message, timeout=self.budget)
                except subprocess.TimeoutExpired:
                    log_entry("TRON liveness",
                              f"{self.role} overran {self.budget}s "
                              f"(attempt {attempt}) — probing the seat")
                    events.emit("probe", role=self.role, what="overrun",
                                attempt=attempt, budget_s=self.budget)
                    try:
                        pulse = self._turn(PROBE, timeout=PROBE_TIMEOUT_S)
                        log_entry("TRON liveness",
                                  f"{self.role} probe answered: {pulse[:200]}")
                        events.emit("probe", role=self.role, what="answered")
                    except subprocess.TimeoutExpired:
                        log_entry("TRON liveness",
                                  f"{self.role} SILENT through the probe")
                        events.emit("probe", role=self.role, what="silent")
                        break
            while True:
                operator(f"{self.role} seat is unresponsive: turn overran "
                         f"{self.budget}s and the talk-first protocol is "
                         "exhausted. Enter to retry, 'abort' to quit.")
                try:
                    return self._turn(message, timeout=self.budget)
                except subprocess.TimeoutExpired:
                    pass


# -------------------------------------------------------------- selftest
def selftest():
    import shutil
    import sys
    import tempfile
    import time
    arena = tempfile.mkdtemp(prefix="agents-selftest-")
    fake = f"{arena}/claude"                    # a 'claude' living in the arena
    shutil.copy("/bin/sleep", fake)
    stray = subprocess.Popen([fake, "30"], cwd=arena)
    time.sleep(0.3)
    killed = kill_strays(arena)
    ok = [stray.pid in killed,
          stray.wait() == -9,                   # SIGKILLed
          kill_strays(arena) == []]             # idempotent
    # liveness: talk-first protocol — the seat is probed, never surrendered
    # silently. Fakes: slow on the real message, behavior per scenario.
    global CLAUDE, PROBE_TIMEOUT_S
    saved = (CLAUDE, PROBE_TIMEOUT_S)
    live = tempfile.mkdtemp(prefix="agents-live-")
    import transcript
    pages = []
    saved_op = transcript.operator
    # scenario 1: overrun -> probe answers -> re-issue succeeds (no page)
    with open(f"{live}/c1", "w") as fh:
        fh.write(f"""#!/bin/bash
msg="$2"
case "$msg" in "liveness probe"*)
  echo '{{"result": "probe: mid-refactor, tree dirty", "session_id": "s"}}'
  exit 0;; esac
n=$(cat {live}/n1 2>/dev/null || echo 0); n=$((n+1)); echo $n > {live}/n1
[ "$n" -ge 2 ] && {{ echo '{{"result": "recovered", "session_id": "s"}}'; exit 0; }}
sleep 5
""")
    os.chmod(f"{live}/c1", 0o755)
    CLAUDE, PROBE_TIMEOUT_S = f"{live}/c1", 2
    ok += [Agent("worker", live, budget=1).turn("do the work") == "recovered"]
    # scenario 2: silent through the probe -> operator, talked-first
    with open(f"{live}/c2", "w") as fh:
        fh.write(f"""#!/bin/bash
[ -f {live}/GO ] && {{ echo '{{"result": "after-op", "session_id": "s"}}'; exit 0; }}
sleep 5
""")
    os.chmod(f"{live}/c2", 0o755)
    def fake_op(_):
        pages.append(1)
        open(f"{live}/GO", "w").write("go")
        return ""
    transcript.operator = fake_op
    globals()["operator"] = fake_op
    CLAUDE = f"{live}/c2"
    ok += [Agent("worker", live, budget=1).turn("do the work") == "after-op",
           pages == [1]]                        # exactly one page, at the end
    CLAUDE, PROBE_TIMEOUT_S = saved
    transcript.operator = saved_op
    globals()["operator"] = saved_op
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    selftest()
