"""jobs — the engine's window into the host's background agent store.

Workers are real detached background sessions under ~/.claude/jobs/<shortid>/
(state.json + timeline.jsonl). The engine never owns these processes' lifecycle
beyond spawn/release; it reads their state to sweep liveness and stall, and it
spawns them *detached from any TTY* so closing the console can't SIGHUP-cascade
the fleet (ADR-002 failure handling). Addressing is name-primary, id-fallback.
"""
import os
import json
import time
import subprocess
from datetime import datetime, timezone

JOBS_DIR = os.path.expanduser("~/.claude/jobs")


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def index():
    """name -> {shortid, session_id, state, updated_at, dir}. Skips junk."""
    out = {}
    if not os.path.isdir(JOBS_DIR):
        return out
    for short in os.listdir(JOBS_DIR):
        sj = os.path.join(JOBS_DIR, short, "state.json")
        if not os.path.isfile(sj):
            continue
        try:
            with open(sj) as fh:
                d = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        name = d.get("name") or short
        out[name] = {
            "shortid": short,
            "session_id": d.get("sessionId"),
            "state": d.get("state"),
            "updated_at": d.get("updatedAt"),
            "dir": os.path.join(JOBS_DIR, short),
        }
    return out


def find(worker_id, idx=None):
    """Name-primary, then short-id / session-id fallback. None if not found."""
    idx = idx or index()
    if worker_id in idx:
        return idx[worker_id]
    for rec in idx.values():
        if worker_id in (rec.get("shortid"), rec.get("session_id")):
            return rec
    return None


def is_alive(worker_id, idx=None):
    """Dead = no state.json / state in a terminal-error class. (contracts §2 worker.dead)"""
    rec = find(worker_id, idx)
    if rec is None:
        return False
    return rec.get("state") not in ("error", "failed", "killed")


def timeline_tail(worker_id, n=20, idx=None):
    rec = find(worker_id, idx)
    if not rec:
        return ""
    path = os.path.join(rec["dir"], "timeline.jsonl")
    if not os.path.isfile(path):
        return ""
    with open(path) as fh:
        lines = fh.readlines()[-n:]
    bits = []
    for ln in lines:
        try:
            ev = json.loads(ln)
            bits.append(ev.get("text") or ev.get("detail") or ev.get("state") or "")
        except json.JSONDecodeError:
            continue
    return "\n".join(b for b in bits if b)


def activity_signals(worker_id, worktree=None, since_iso=None, idx=None):
    """The deterministic pre-filter inputs for assess_stall (contracts §3).

    Any positive signal => the worker is alive; the LLM is never asked.
    """
    rec = find(worker_id, idx) or {}
    updated = _parse_iso(rec.get("updated_at"))
    since = _parse_iso(since_iso)
    last_delta = None
    grew = False
    if updated:
        now = datetime.now(timezone.utc)
        last_delta = (now - updated).total_seconds()
        if since:
            grew = updated > since

    dirty = False
    mtime_grew = False
    if worktree and os.path.isdir(worktree):
        try:
            r = subprocess.run(["git", "-C", worktree, "status", "--porcelain"],
                               capture_output=True, text=True, timeout=10)
            dirty = bool(r.stdout.strip())
        except (subprocess.SubprocessError, OSError):
            pass
        if since:
            cutoff = since.timestamp()
            for root, _, files in os.walk(worktree):
                if ".git" in root:
                    continue
                for f in files:
                    try:
                        if os.path.getmtime(os.path.join(root, f)) > cutoff:
                            mtime_grew = True
                            break
                    except OSError:
                        continue
                if mtime_grew:
                    break

    return {
        "last_activity_delta_s": last_delta,
        "worktree_dirty": dirty,
        "mtime_grew": mtime_grew or grew,
    }


def has_positive_activity(sig):
    """Pre-filter: True => alive, short-circuit before any LLM stall call."""
    return bool(sig.get("worktree_dirty") or sig.get("mtime_grew"))


def spawn_detached(worker_id, prompt, cwd=None, settle_s=2.0):
    """Spawn a background worker fully detached from this TTY.

    start_new_session=True + devnull I/O so no SIGHUP cascade from a closed
    console. Returns {shortid, session_id} once the host registers the job,
    or {} if it could not be confirmed within settle_s.
    """
    cmd = ["claude", "--bg", "-n", worker_id, prompt]
    subprocess.Popen(
        cmd, cwd=cwd, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + settle_s
    while time.time() < deadline:
        rec = find(worker_id)
        if rec:
            return {"shortid": rec["shortid"], "session_id": rec["session_id"]}
        time.sleep(0.25)
    return {}


def send(session_id, text):
    """Engine -> worker channel: resume the worker's session with a line.

    Used to inject an operator's resolved-escalation answer or a heartbeat ping.
    Workers reach back via report.sh -> worker-inbox.jsonl (engine polls).
    """
    try:
        subprocess.run(["claude", "--resume", session_id, "-p", text],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def release(session_id):
    """Stop a worker process. Only the spine releases workers (R7)."""
    try:
        subprocess.run(["claude", "stop", session_id],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        return True
    except (subprocess.SubprocessError, OSError):
        return False
