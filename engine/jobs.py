"""jobs — the engine's window onto its workers, and the engine->worker channel.

01-10 rewrite. A worker is no longer a free-running host background agent reached by
re-opening its detached session (which the runtime rejects — the pilot's blocking
defect). It is a **runner-wrapped process TRON owns**: `worker_runner.py` drives a
per-worker agent one turn at a time, pulling from a file mailbox the engine appends to.

Everything is keyed by the **stable worker id**, never the session id (identity is
stable; the session id is not). Each worker owns a directory under `<instance>/workers/<id>/`:

    tron-inbox.jsonl   engine->worker mailbox   (engine appends {seq,ts,kind,text}; runner pulls)
    .mbox-hwm          runner's high-water seq  (persisted after each turn — crash-safe resume)
    runner.json        runner heartbeat/state   ({worker_id,session_id,pid,state,updated_at,turns})
    timeline.jsonl     the worker's turn log     (console tail + the engine's liveness sweep)
    .stop              release sentinel          (engine writes it; the runner exits cleanly)

The worker->engine direction: a worker calls `report.sh` -> `worker-inbox.jsonl` for explicit
reports (progress/done/questions), which the engine drains every tick. The two-step *online*
handshake needs no message at all — the engine reads the runner's spawn-turn completion (`turns`
in runner.json) as a deterministic liveness signal (see fsm `_sweep`). This module is the
symmetric mirror for engine->worker.
"""
import os
import json
import time
import signal
import subprocess
from datetime import datetime, timezone

# The worker-agent runtime, resolved once. Override with TRON_RUNTIME; the literal
# default is the only place the host runtime is named in code (never in TRON-facing copy).
RUNTIME = os.environ.get("TRON_RUNTIME", "claude")

# The worker-runtime ADAPTER the runner uses to run one turn. Runtime-neutral by contract:
# the mailbox + runner loop never name a runtime; which adapter backs them is a per-project
# config value (env here; project.yaml at seed), never hardcoded in the engine.
ADAPTER = os.environ.get("TRON_WORKER_ADAPTER", "host-cli")

# The worker MODEL (01-21 T1) — an explicit, engine-owned, FAIL-CLOSED input. Unlike RUNTIME/
# ADAPTER above, this carries NO baked default: a run's worker model must be a declared,
# reproducible input (roles.yaml's per-role `model:`, resolved by fsm._model_for_role and
# threaded by fsm._spawn from the project's own config — ADR-0002 D4, 01-33) or the run
# must not start at all — never the host CLI's own ambient saved-
# default model (the credit-drain root cause: 3 orphaned workers found running on an
# undeclared, potentially expensive tier). TRON_WORKER_MODEL exists purely as the same kind
# of override knob RUNTIME/ADAPTER already have (useful standalone/tests). Read DYNAMICALLY
# (a function, not a frozen module constant like RUNTIME/ADAPTER) — a caller that sets the
# env var right before spawning must not lose the race against whenever this module first
# happened to be imported. Its absence is NOT itself the failure — spawn_runner refuses only
# when NEITHER this NOR an explicit `model=` argument resolves to a value. TRON_WORKER_PERMS
# stays permission-posture-only; the model is no longer smuggled through it.
def _env_model():
    return os.environ.get("TRON_WORKER_MODEL")


class WorkerModelUnconfigured(RuntimeError):
    """Raised by spawn_runner (01-21 T1/AC-2) when no worker model resolves from any source.
    Fail-closed: a worker must never launch on the host CLI's own ambient default. The real
    source is the project's declared config (roles.yaml's per-role `model:`, resolved by
    fsm._model_for_role and threaded by fsm._spawn — ADR-0002 D4, 01-33); this is the
    last-line-of-defense guard against a future call site that forgets to thread it."""

# Per-worker file names (single source of truth — worker_runner.py imports these).
MAILBOX = "tron-inbox.jsonl"
HWM = ".mbox-hwm"
RUNNER_STATE = "runner.json"
TIMELINE = "timeline.jsonl"
STOP = ".stop"

_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))

# The worker store root, configured once at engine/console start (Engine.__init__ /
# Console.__init__ call configure). None => no store yet (dry runs / unit tests) -> empty index.
_STORE = None


def configure(workers_dir):
    """Point the store at this instance's `<instance>/workers/`. Idempotent."""
    global _STORE
    _STORE = workers_dir


def mailbox_path(worker_dir):
    return os.path.join(worker_dir, MAILBOX)


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _read_state(worker_dir):
    path = os.path.join(worker_dir, RUNNER_STATE)
    try:
        with open(path) as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


# ── the store: workers are the subdirs of <instance>/workers/ ──
def index():
    """worker_id -> {shortid, session_id, state, updated_at, dir}. Skips junk."""
    out = {}
    if not _STORE or not os.path.isdir(_STORE):
        return out
    for wid in os.listdir(_STORE):
        wdir = os.path.join(_STORE, wid)
        st = _read_state(wdir)
        if st is None:
            continue
        out[wid] = {
            "shortid": wid,
            "session_id": st.get("session_id"),
            "state": st.get("state"),
            "updated_at": st.get("updated_at"),
            "pid": st.get("pid"),
            "turns": st.get("turns", 0),   # completed turns; >=1 => the spawn/identity turn is done
            "dir": wdir,
        }
    return out


def _pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)          # signal 0: existence check, no-op if alive
    except (ProcessLookupError, ValueError, TypeError):
        return False
    except PermissionError:
        return True                   # exists but not ours to signal -> alive
    # It answers signal 0 — but a ZOMBIE (a crashed child not yet reaped) answers too. If it is our
    # child and already exited, reap it and report dead; otherwise it is genuinely alive. Without
    # this, a SIGKILL'd runner would read as alive and the sweep would never recover it.
    try:
        gone, _ = os.waitpid(int(pid), os.WNOHANG)
        if gone == int(pid):
            return False
    except ChildProcessError:
        pass                          # not our child -> the signal-0 success is authoritative
    except (OSError, ValueError):
        pass
    return True


def find(worker_id, idx=None):
    """Worker id is the key (the dir name). None if not found."""
    idx = idx if idx is not None else index()
    return idx.get(worker_id)


def is_alive(worker_id, idx=None):
    """Dead = no runner state / state in a terminal class. (contracts §2 worker.dead)"""
    rec = find(worker_id, idx)
    if rec is None:
        return False
    if rec.get("state") in ("error", "failed", "killed", "released"):
        return False
    return _pid_alive(rec.get("pid"))   # a crashed runner leaves a stale state file -> dead


def timeline_tail(worker_id, n=20, idx=None):
    rec = find(worker_id, idx)
    if not rec:
        return ""
    path = os.path.join(rec["dir"], TIMELINE)
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


def last_turn_error_kind(worker_dir):
    """T3(b) (01-20): the engine's fleet-hold sweep reads the runner's own STRUCTURAL
    `kind` field on its last turn_error timeline event (the exception class name the
    runner recorded, e.g. "RunnerRefusal" — worker_runner.py) to recognize a refusal-
    caused death across the fleet. Never reads the refusal TEXT (NET-ZERO: that stays
    adapter-only knowledge). '' when no turn_error is recorded, or the dir is missing."""
    path = os.path.join(worker_dir or "", TIMELINE)
    if not worker_dir or not os.path.isfile(path):
        return ""
    kind = ""
    try:
        with open(path) as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    ev = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if ev.get("event") == "turn_error":
                    kind = ev.get("kind") or ""
    except OSError:
        return ""
    return kind


def activity_signals(worker_id, since_iso=None, idx=None):
    """Liveness signals for the engine's deterministic stall sweep (contracts §5).

    The runner's own record is the source: `updated_at` freshness (stamped on every state
    transition and idle poll) yields the silence delta, and its advance past the last sweep
    is the positive-activity signal. S-5/F-6 (tron-07 review cycle): the old worktree-scan
    branch (git-status + os.walk per worker per tick) was never fed by the sweep and is the
    wrong cost at worker_count > 1 — deleted; the runner-declared turn deadline (A-4) owns
    what it was for. Stall detection stays engine-side — never asks the LLM.
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

    return {
        "last_activity_delta_s": last_delta,
        "record_advanced": grew,
    }


def has_positive_activity(sig):
    """Pre-filter: True => alive, short-circuit before any LLM stall call."""
    return bool(sig.get("record_advanced"))


def runner_idle(worker_id, idx=None):
    """True iff the worker's runner reports `state: idle` — the agent finished its turn and
    sits waiting on the mailbox. THE deterministic idle fact for the gate's tick-time idle
    cap (01-11 FX-2): the runner rewrites runner.json on every poll even when idle, so
    freshness/heartbeat signals can never tell idle-at-gate from working (tron-06 P2).
    A missing runner record is idle too — nothing can be working."""
    rec = find(worker_id, idx)
    return rec is None or rec.get("state") == "idle"


def read_hwm(worker_dir):
    """T2 (01-19, F5): the engine-internal reader for the runner's own high-water seq (the
    CONSUMED half of the order-dedupe invariant: undelivered = send-seq > consumed-seq). The
    engine never wrote this file before (worker_runner.py owns `_write_hwm`, after each
    fully-finished turn) and never reads it anywhere else — this is that one small reader,
    not a knob. Missing/corrupt reads as 0 (nothing consumed yet), the same fail-open
    Runner._read_hwm itself uses, so an at-least-once re-emit recomputes the same seq and
    the dedupe stays coherent across a crash on either side."""
    try:
        with open(os.path.join(worker_dir, HWM)) as fh:
            return int(fh.read().strip() or "0")
    except (OSError, ValueError):
        return 0


# ── engine -> worker: append one line to the mailbox (the ONLY delivery path) ──
def send(worker_dir, seq, kind, text):
    """Append one message to the worker's mailbox. Pure file append — no session is ever
    re-opened (that was finding #5). `seq` is the engine's per-worker monotonic counter;
    a re-emit (at-least-once) re-appends the SAME seq, so the runner dedupes by high-water.
    Append-only; never rewritten. Returns True on success."""
    try:
        os.makedirs(worker_dir, exist_ok=True)
        rec = {"seq": seq, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "kind": kind, "text": text}
        with open(mailbox_path(worker_dir), "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        return True
    except OSError:
        return False


# ── lifecycle: TRON owns the runner process (spawn / release), deterministically ──
def retire_stale_dir(worker_dir, kill_wait_s=3.0):
    """01-13 (tron-14 F7): a re-spawn must NEVER inherit a predecessor's worker dir —
    the stale `.mbox-hwm` outruns the fresh engine seq counter (new messages land at
    seq 1,2 under a high-water of 4: delivered, never read) and a lingering runner
    shares runner.json with its replacement. If the dir holds prior runner state:
    stop whatever still runs (SIGTERM, wait, SIGKILL), then move the WHOLE dir aside
    under `<workers>/.archive/` as forensics. The spawn starts from an empty dir.
    Returns the archive path, or None when there was nothing to retire."""
    st = _read_state(worker_dir)
    if st is None:
        return None
    pid = st.get("pid")
    if pid and _pid_alive(pid):
        # 01-21 T2: killpg, not kill — the runner leads its own process group
        # (spawn_runner's start_new_session=True), so a child it forked cannot
        # outlive it here either.
        try:
            os.killpg(int(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, ValueError, TypeError):
            pass
        deadline = time.time() + kill_wait_s
        while time.time() < deadline and _pid_alive(pid):
            time.sleep(0.2)
        if _pid_alive(pid):
            try:
                os.killpg(int(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, ValueError, TypeError):
                pass
    parent = os.path.dirname(worker_dir.rstrip(os.sep))
    adir = os.path.join(parent, ".archive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = os.path.join(adir, f"{os.path.basename(worker_dir.rstrip(os.sep))}-{stamp}")
    if os.path.exists(dest):
        dest = f"{dest}-{os.getpid()}"
    try:
        os.makedirs(adir, exist_ok=True)
        os.rename(worker_dir, dest)
        return dest
    except OSError:
        # Rename should not fail same-filesystem; fall back to wiping the channel files
        # so the mailbox/high-water can at least never wedge the fresh runner.
        for name in (MAILBOX, HWM, RUNNER_STATE, TIMELINE, STOP):
            try:
                os.remove(os.path.join(worker_dir, name))
            except OSError:
                pass
        return None


def spawn_runner(worker_id, worker_dir, session_id, cwd=None,
                 runtime=None, adapter=None, model=None, settle_s=2.0):
    """Spawn the worker-runner fully detached from this TTY. The runner drives the agent
    turn-by-turn off the mailbox; TRON owns its lifecycle (spawn here, liveness via the
    store, release via the .stop sentinel). start_new_session=True + devnull I/O so a
    closed console can't SIGHUP-cascade the fleet. Returns {session_id, worker_id} once the
    runner registers its state, or {} if it could not be confirmed within settle_s.
    NOTE (01-13/F7): this function deliberately RESUMES an existing dir (crash-restart:
    same identity, high-water preserved, no replay). Identity freshness is the ENGINE'S
    call — fsm._spawn retires a predecessor's dir (retire_stale_dir) before its first
    mailbox write, so a NEW worker under a reused id never inherits a stale mailbox.

    01-21 T1: `model` is the declared, project-configured worker model (fsm._spawn resolves
    it per-role straight from roles.yaml's `model:` field since ADR-0002 D4/01-33 — see
    fsm._model_for_role — and passes the resolved value here; this function itself stays
    role-agnostic, just a single resolved string). FAIL-CLOSED: if neither `model` nor
    TRON_WORKER_MODEL resolves to a value, this refuses to spawn at all — a worker must
    never launch on the host CLI's own ambient default (raises WorkerModelUnconfigured,
    BEFORE any process is started)."""
    resolved_model = model if model is not None else _env_model()
    if not resolved_model:
        raise WorkerModelUnconfigured(
            "no worker model configured — set `model:` on the role in roles.yaml "
            "(project config) or TRON_WORKER_MODEL; refusing to launch a worker on the "
            "host CLI's own ambient default model")
    os.makedirs(worker_dir, exist_ok=True)
    stop = os.path.join(worker_dir, STOP)
    if os.path.exists(stop):        # a prior release sentinel must not kill a fresh runner
        try:
            os.remove(stop)
        except OSError:
            pass
    cmd = [
        "python3", os.path.join(_ENGINE_DIR, "worker_runner.py"),
        "--worker-id", worker_id,
        "--worker-dir", worker_dir,
        "--session-id", session_id,
        "--runtime", runtime or RUNTIME,
        "--adapter", adapter or ADAPTER,
        "--model", resolved_model,
    ]
    if cwd:
        cmd += ["--cwd", cwd]
    try:
        subprocess.Popen(
            cmd, cwd=cwd, start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, ValueError):
        return {}   # runner missing / spawn failed — the reservation is recovered by the sweep
    deadline = time.time() + settle_s
    while time.time() < deadline:
        if _read_state(worker_dir) is not None:
            return {"session_id": session_id, "worker_id": worker_id}
        time.sleep(0.25)
    return {"session_id": session_id, "worker_id": worker_id}   # runner may still be coming up; sweep confirms


def kill_hard(worker_id, idx=None):
    """SIGKILL a runner presumed suspended (R-2(ii)): past its own turn deadline, SIGTERM
    (release) can't be trusted — a SIGSTOPped process ignores it. ONLY the past-ceiling
    escalation path (and the 01-21 T2 reaper below) calls this; ordinary releases stay
    graceful. 01-21 T2: killpg, not kill — the runner leads its own process group
    (spawn_runner's start_new_session=True), so a forked child dies with it too; a
    process group persists as long as any member does, so this still reaches a lingering
    child even if the runner itself already exited."""
    rec = find(worker_id, idx)
    pid = (rec or {}).get("pid")
    if not pid:
        return False
    try:
        os.killpg(int(pid), signal.SIGKILL)
        return True
    except (ProcessLookupError, PermissionError, ValueError, TypeError):
        return False


def release(worker_id, idx=None):
    """Stop a worker's runner. Only the spine releases workers (R7). Writes the .stop
    sentinel (the runner polls it and exits cleanly, closing its agent) and SIGTERMs the
    runner's WHOLE PROCESS GROUP as a backstop (01-21 T2 — a child it forked must not
    survive a release either). Idempotent."""
    rec = find(worker_id, idx)
    wdir = rec["dir"] if rec else (os.path.join(_STORE, worker_id) if _STORE else None)
    if not wdir:
        return False
    try:
        with open(os.path.join(wdir, STOP), "w") as fh:
            fh.write(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    except OSError:
        pass
    st = _read_state(wdir) or {}
    pid = st.get("pid")
    if pid:
        try:
            os.killpg(int(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, ValueError, TypeError):
            pass
    return True


def reap_all():
    """The engine-death reaper (01-21 T2): group-kill every worker THIS store still shows
    alive. Called at engine shutdown (wake.run's finally — clean exit or a signal) and at
    a fresh engine startup (fsm.Engine.start — crash recovery: a new session owns none of
    whatever is still sitting in the store), so no `worker_runner` this engine ever spawned
    outlives it, idle-polling forever and re-spawning a real agent on the next mailbox write
    (the exact leak this block closes).

    Scoped to `index()` alone — this ONE store, whatever `configure()` last pointed at.
    It can never reach a different project's instance (a different store entirely), and a
    concurrently-live engine cannot coexist on THIS SAME store (the WAKE pidfile's atomic
    single-daemon claim already guarantees at most one), so there is nothing else within one
    store to avoid. Returns the worker ids it killed."""
    idx = index()
    killed = []
    for wid, rec in idx.items():
        if _pid_alive(rec.get("pid")) and kill_hard(wid, idx):
            killed.append(wid)
    return killed
