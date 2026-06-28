"""wake — the WAKE daemon (ND-08): the in-process scheduler that ticks the engine.

Replaces the retired cron heartbeat (01-04). One supervised process per live session,
spawned by `tron start`, ended by `tron stop`. It owns only *when* a tick fires — never
run state: the tick stays a stateless rebuild-from-trunk (T4). The daemon carries nothing
between ticks but two clocks.

Bounded both ways by the WAKE knobs (`knobs.yaml`):
  • COOLDOWN — a floor: never tick more often than this (debounce a chatty fleet).
  • CEILING — a cadence: always tick at least this often, even when idle.
Between the two it wakes early on an inbox event, so a fresh message is picked up within
COOLDOWN rather than waiting out CEILING:  cooldown ≤ gap-between-ticks ≤ ceiling.

Single-flight: every tick — daemon-fired OR the console's manual `tick` — runs under an
flock (`tick_lock`) so two ticks never overlap (a tick is not re-entrant: it claims the
inbox sidecars and rebuilds state from trunk).

Supervision: a tick that raises is logged and the loop continues — one bad tick never
kills the heartbeat. The loop exits cleanly when the session ends (started_at cleared by
stop/halt/teardown) or on SIGTERM (what `tron stop` sends).
"""
import contextlib
import fcntl
import os
import signal
import sys
import time

import util


# ── WAKE bounds (fixed knobs; defaults match knobs.example.md) ──
def bounds(knobs):
    """(cooldown, ceiling) seconds from knobs.yaml. Floored at 1s; cooldown ≤ ceiling."""
    k = knobs or {}
    cooldown = max(1, int(k.get("wake_cooldown_sec", 5)))
    ceiling = max(cooldown, int(k.get("wake_ceiling_sec", 30)))
    return cooldown, ceiling


def due(new_msg, gap, cooldown, ceiling):
    """The scheduling decision (ND-08), pure so it is testable in isolation:
    wake early on a fresh message but never inside the COOLDOWN floor; otherwise wake
    at the CEILING cadence. Holds cooldown ≤ gap-between-ticks ≤ ceiling."""
    return (new_msg and gap >= cooldown) or (gap >= ceiling)


# ── single-flight: the lock every tick path shares ──
@contextlib.contextmanager
def single_flight(ctx):
    """Yield True iff this caller won the tick lock; False means a tick is already running
    (the caller should skip, not block — the next pulse re-arms it)."""
    f = open(ctx.tick_lock, "w")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def locked_tick(ctx):
    """One tick under single-flight. Returns (ran, ended): ran=False means the lock was
    held (skipped). The single entry point for every tick — daemon, console, CLI."""
    from fsm import Engine
    with single_flight(ctx) as won:
        if not won:
            return False, False
        return True, Engine(ctx).tick()


# ── session liveness (the daemon's natural stop condition) ──
def session_live(ctx):
    if not os.path.exists(ctx.state):
        return False
    data = util.load_yaml(ctx.state) or {}
    return bool((data.get("session") or {}).get("started_at"))


# ── inbox event signal: a change here means a fresh message is waiting ──
def _inbox_sig(ctx):
    sig = []
    for path in (ctx.worker_inbox, ctx.operator_inbox, ctx.tg_inbox):
        try:
            s = os.stat(path)
            sig.append((path, s.st_size, s.st_mtime_ns))
        except FileNotFoundError:
            sig.append((path, -1, 0))
    return tuple(sig)


# ── pid file (so start/stop manage exactly one daemon) ──
def _read_pid(ctx):
    try:
        return int(open(ctx.wake_pid).read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_running(ctx):
    pid = _read_pid(ctx)
    return bool(pid and _alive(pid))


# ── the loop ──
def run(ctx):
    """The daemon body. Blocks until the session ends or SIGTERM. Writes its own pid."""
    util.atomic_write(ctx.wake_pid, str(os.getpid()))
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("now", True))

    cooldown, ceiling = bounds(ctx.load_knobs())
    poll = min(cooldown, 1.0) / 2          # granularity well under the floor
    last_tick = 0.0                        # monotonic clock of the last tick that ran
    last_sig = _inbox_sig(ctx)
    try:
        while not stop["now"] and session_live(ctx):
            now = time.monotonic()
            sig = _inbox_sig(ctx)
            new_msg = sig != last_sig
            if due(new_msg, now - last_tick, cooldown, ceiling):
                try:
                    ran, ended = locked_tick(ctx)
                except Exception as e:                 # supervision: one bad tick ≠ dead loop
                    util.log_line(ctx.logs_dir, "wake", f"tick raised, loop continues: {e}")
                    ran, ended = True, False
                if ran:
                    last_tick = time.monotonic()
                    last_sig = _inbox_sig(ctx)         # re-read after the drain
                    if ended:
                        break
                # ran=False -> the lock was held; leave the clocks, retry next poll
            time.sleep(poll)
    finally:
        with contextlib.suppress(FileNotFoundError):
            if _read_pid(ctx) == os.getpid():
                os.remove(ctx.wake_pid)


# ── lifecycle: spawn / stop (what `tron start` / `tron stop` call) ──
def _launch(ctx):
    """Popen the detached daemon process (survives the console closing). Isolated so the
    spawn arbitration can be tested without launching real daemons."""
    engine_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine.py")
    log = open(os.path.join(ctx.dir, "wake.out"), "a")
    import subprocess
    return subprocess.Popen(
        [sys.executable, engine_py, "wake"],
        stdout=log, stderr=log, stdin=subprocess.DEVNULL,
        start_new_session=True,                      # detach from the console's session
        env={**os.environ, "TRON_DIR": ctx.dir},
    )


def spawn(ctx):
    """Start the WAKE daemon, guaranteeing **exactly one**. The pidfile is claimed
    ATOMICALLY — `O_CREAT|O_EXCL` — so there is no check-then-act window: exactly one
    caller wins the create and launches; a concurrent caller sees the claim and leaves a
    live daemon alone, or reclaims a dead/stale pidfile once. Returns the daemon pid (ours
    or a peer's), or None if a peer's claim is mid-flight (its daemon writes the real pid).

    The winner fills the pidfile with its own (alive) pid the instant it wins — before the
    slow launch — so a racing caller never reads it empty and never mistakes the in-flight
    claim for stale. The daemon then overwrites it with its real pid in run()."""
    for attempt in (0, 1):
        try:
            fd = os.open(ctx.wake_pid, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            pid = _read_pid(ctx)
            if pid is None:
                return None                          # a claim is in flight — leave it
            if _alive(pid):
                return pid                           # a live daemon — leave it
            if attempt == 0:                         # parseable but dead → stale: reclaim once
                with contextlib.suppress(FileNotFoundError):
                    os.remove(ctx.wake_pid)
                continue
            return pid                               # still dead after a retry — give up quietly
        # won the claim — fill it at once (never read empty), then launch
        try:
            os.write(fd, str(os.getpid()).encode())  # placeholder: this launcher is alive
        finally:
            os.close(fd)
        try:
            proc = _launch(ctx)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                os.remove(ctx.wake_pid)              # don't strand the claim if the launch fails
            raise
        util.atomic_write(ctx.wake_pid, str(proc.pid))
        return proc.pid


def stop(ctx):
    """Signal the daemon to exit and reap its pid file. Returns True if one was running."""
    pid = _read_pid(ctx)
    if not (pid and _alive(pid)):
        with contextlib.suppress(FileNotFoundError):
            os.remove(ctx.wake_pid)
        return False
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGTERM)
    for _ in range(50):                              # up to ~5s for a graceful exit
        if not _alive(pid):
            break
        time.sleep(0.1)
    if _alive(pid):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGKILL)
    with contextlib.suppress(FileNotFoundError):
        os.remove(ctx.wake_pid)
    return True
