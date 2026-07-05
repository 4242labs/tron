"""worker_runner — the deterministic driver that makes a worker reachable (01-10, finding #5).

A worker is NOT a free-running agent that "checks its inbox" — that would depend on the
model's discretion and would not be model-agnostic. It is wrapped by this runner, whose loop
is plain code:

    read the mailbox -> hand the next unprocessed message to the agent for ONE turn ->
    block until that turn fully finishes -> record the high-water seq -> repeat.

The LLM only answers what it is handed; the pull-and-feed is the runner's, so it can never be
forgotten. Delivery needs neither a re-opened session (kills the `--bg`/`--resume` rejection)
nor the model remembering to look (kills the prompt-hope).

Model-agnostic by contract: the runner talks to the agent through a thin ADAPTER with one
operation — run the agent for one turn on this input, block until the turn is done, return its
result. The loop + mailbox protocol are runtime-neutral; WHICH runtime backs the adapter is a
per-project config value (`--adapter`), never hardcoded. The host CLI is one adapter here.

Lifecycle is TRON's: TRON spawns this (jobs.spawn_runner), tracks liveness via runner.json,
restarts it on unexpected exit (it resumes from the persisted high-water seq — no replay), and
releases it by writing a `.stop` sentinel. Crash-safe: inbox + high-water seq persist.
"""
import os
import sys
import json
import time
import select
import signal
import argparse
import subprocess
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobs  # single source of the per-worker file-name constants  # noqa: E402

POLL_S = float(os.environ.get("TRON_RUNNER_POLL_S", "2.0"))
# A single turn's wall-clock ceiling: a hung agent -> TimeoutError -> turn_error -> the engine's
# sweep recovers, instead of the runner blocking forever on a silent process. Generous by default
# (build turns are long); tune with TRON_TURN_TIMEOUT_S.
TURN_TIMEOUT_S = float(os.environ.get("TRON_TURN_TIMEOUT_S", "1800"))
# The worker's permission posture — config-driven, NOT hardcoded. The default suits a sandboxed
# autonomous worker; set TRON_WORKER_PERMS="" to drop it, or to a different flag set, upstream.
WORKER_PERMS = os.environ.get("TRON_WORKER_PERMS", "--dangerously-skip-permissions")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RunnerRefusal(RuntimeError):
    """T3(a) (01-20, tron-27/28 quota-blindness): raised for a runtime-failure TURN — the
    host CLI answered, but its own result record says the turn was not a healthy success
    (`is_error` true, `subtype` != "success", or the CLI's own known refusal wording, e.g.
    a provider quota/limit banner returned as ordinary `turn_done` text — BLOCKER-1: the
    quota-state result shape is unverified and may arrive dressed as `success`). A DISTINCT
    exception CLASS (never a bare RuntimeError) so the engine's fleet-hold sweep (T3(b))
    can recognize the CAUSE structurally off this class's __name__, recorded as a plain
    `kind` field on the runner's own turn_error timeline event — never by reading the
    refusal TEXT engine-side (NET-ZERO: the shapes stay this adapter's own knowledge).
    Rides the EXISTING exception path unchanged: Runner.run()'s one `except Exception`
    already turns any raise here into turn_error -> state `error` -> jobs.is_alive() False
    -> the sweep recovers."""


# T3(a) (01-20, BLOCKER-1 / impl-review MAJOR-3): known runtime-refusal SHAPES — the
# host CLI's OWN quota/limit wording. Versioned constants living HERE, in the host-CLI
# adapter, because they are runtime-specific translation knowledge (exactly what an
# adapter is for) — the engine NEVER reads this list or any turn text (NET-ZERO: no new
# knob/verb/template; this is a private detection detail of ONE adapter, not TRON
# vocabulary). Update it if/when the host CLI's own wording changes.
#
# BOUNDARY (MAJOR-3): this is a shape match, and a shape match on free assistant prose is
# a classifier — undisciplined, it false-kills a coding turn whose OWN summary happens to
# mention "rate limit exceeded" (this fleet's product wraps LiteLLM: quotas, rate limits
# and usage-cap strings are exactly what its engineers write and describe). So this list
# is consulted ONLY when the turn's own structural fields (`subtype`/`is_error`) have
# NOT already affirmed a clean success — see `run_turn` below: a record with
# `is_error=False` AND `subtype=="success"` never reaches this check at all, regardless
# of its text. It exists purely for the shape BLOCKER-1 named unverified: a quota/limit
# turn whose subtype is missing entirely (no affirmative "success" to trust) — never for
# a turn the CLI itself already vouched for.
_KNOWN_REFUSAL_SHAPES = (
    "usage limit reached",
    "you've reached your usage limit",
    "you have reached your usage limit",
    "quota exceeded",
    "rate limit exceeded",
    "please upgrade your plan",
)


def _is_known_refusal(text):
    low = (text or "").lower()
    return any(shape in low for shape in _KNOWN_REFUSAL_SHAPES)


# ── adapters: one operation — run_turn(text) blocks until the turn ends, returns its result ──
class HostCliAdapter:
    """Drives ONE persistent host-CLI process per worker via stream-json. Successive turns feed
    over stdin to the SAME process, so context carries with no `--resume` and no `--bg` (the two
    verbs the runtime rejects). One-turn atomicity: run_turn returns only when the process emits
    that turn's `result` event."""

    def __init__(self, runtime, session_id, cwd):
        self.runtime, self.session_id, self.cwd = runtime, session_id, cwd
        self.proc = None

    def _ensure(self):
        if self.proc and self.proc.poll() is None:
            return
        cmd = [
            self.runtime, "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--session-id", self.session_id,
        ]
        if WORKER_PERMS:
            cmd += WORKER_PERMS.split()   # config-driven worker permission posture (see WORKER_PERMS)
        self.proc = subprocess.Popen(
            cmd, cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1,
        )

    def run_turn(self, text):
        self._ensure()
        msg = {"type": "user",
               "message": {"role": "user", "content": text}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        # Block until THIS turn's result event, under a wall-clock ceiling. A dead process OR a
        # hung agent -> raise, so the runner records turn_error and TRON's sweep recovers (never
        # an unbounded block). One turn ends at exactly its `result` event (one-turn atomicity).
        deadline = time.time() + TURN_TIMEOUT_S
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"turn exceeded {TURN_TIMEOUT_S:.0f}s")
            rlist, _, _ = select.select([self.proc.stdout], [], [], min(remaining, 1.0))
            if not rlist:
                if self.proc.poll() is not None:
                    raise RuntimeError("host-cli process exited before a result event")
                continue
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("host-cli stream ended before a result event")
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "result":
                text = ev.get("result", "") or ""
                subtype = ev.get("subtype")
                is_error = bool(ev.get("is_error"))
                # T3(a) (01-20): a healthy turn is EARNED, never assumed — is_error or a
                # non-"success" subtype always raises RunnerRefusal, riding the SAME
                # exception path every other turn failure already does (turn_error ->
                # state error -> jobs.is_alive() False -> the sweep recovers).
                if is_error or (subtype is not None and subtype != "success"):
                    raise RunnerRefusal(
                        f"turn reported failure (subtype={subtype!r}, "
                        f"is_error={is_error}): {text[:200]}")
                # impl-review MAJOR-3: the known-refusal SHAPE match is consulted ONLY
                # when the record has NOT already affirmed a clean success — a healthy
                # `is_error=False`/`subtype=="success"` turn NEVER raises off its own
                # prose, however that prose reads (a coding turn legitimately describing
                # "rate limit exceeded" handling must never be false-killed). It exists
                # for the shape BLOCKER-1 flagged unverified: a quota/limit turn that
                # arrives with no affirmative subtype to trust at all.
                clean_success = (subtype == "success" and not is_error)
                if not clean_success and _is_known_refusal(text):
                    raise RunnerRefusal(
                        f"turn reported failure (subtype={subtype!r}, "
                        f"is_error={is_error}): {text[:200]}")
                return {"text": text, "subtype": subtype, "is_error": is_error}

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=10)
            except (subprocess.TimeoutExpired, OSError):
                self.proc.kill()


class EchoAdapter:
    """Token-free adapter for tests/offline: 'runs' a turn by echoing it. Exercises the full
    runner loop + mailbox protocol (seq order, high-water, crash-resume) without a real agent."""

    def __init__(self, *a, **k):
        pass

    def run_turn(self, text):
        return {"text": f"echo: {text[:80]}", "subtype": "success", "is_error": False}

    def close(self):
        pass


ADAPTERS = {"host-cli": HostCliAdapter, "echo": EchoAdapter}


class Runner:
    def __init__(self, worker_id, worker_dir, session_id, cwd, runtime, adapter):
        self.worker_id, self.worker_dir = worker_id, worker_dir
        self.session_id = session_id
        self.mailbox = os.path.join(worker_dir, jobs.MAILBOX)
        self.hwm_path = os.path.join(worker_dir, jobs.HWM)
        self.state_path = os.path.join(worker_dir, jobs.RUNNER_STATE)
        self.timeline = os.path.join(worker_dir, jobs.TIMELINE)
        self.stop_path = os.path.join(worker_dir, jobs.STOP)
        self.turns = 0
        self._stop = False
        adapter_cls = ADAPTERS.get(adapter, HostCliAdapter)
        self.adapter = adapter_cls(runtime, session_id, cwd)

    # ── durable high-water: the last seq whose turn fully finished (crash-safe resume) ──
    def _read_hwm(self):
        try:
            with open(self.hwm_path) as fh:
                return int(fh.read().strip() or "0")
        except (OSError, ValueError):
            return 0

    def _write_hwm(self, seq):
        tmp = self.hwm_path + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(str(seq))
        os.replace(tmp, self.hwm_path)   # atomic

    def _write_state(self, state):
        rec = {"worker_id": self.worker_id, "session_id": self.session_id,
               "pid": os.getpid(), "state": state, "turns": self.turns,
               "updated_at": _now()}
        if state == "working":
            # A-4: the runner DECLARES its own turn deadline — the engine's sweep reads it
            # instead of mirroring env, so per-role/remote ceilings never desynchronize.
            rec["deadline"] = time.time() + TURN_TIMEOUT_S
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(rec, fh)
        os.replace(tmp, self.state_path)

    def _timeline(self, **fields):
        fields["at"] = _now()
        with open(self.timeline, "a") as fh:
            fh.write(json.dumps(fields) + "\n")

    def _pending(self, hwm):
        """New mailbox messages (seq > hwm), in seq order, deduped by seq (at-least-once ->
        exactly-once effect: a re-appended same-seq line is applied at most once)."""
        if not os.path.isfile(self.mailbox):
            return []
        seen, out = set(), []
        with open(self.mailbox) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                seq = m.get("seq")
                if not isinstance(seq, int) or seq <= hwm or seq in seen:
                    continue
                seen.add(seq)
                out.append(m)
        return sorted(out, key=lambda m: m["seq"])

    def _stopped(self):
        return self._stop or os.path.exists(self.stop_path)

    def run(self):
        os.makedirs(self.worker_dir, exist_ok=True)
        # Release is graceful: TRON writes the .stop sentinel and/or SIGTERMs. Handle the
        # signal (never let it hard-kill) so the runner finishes its turn boundary, closes the
        # agent, and records `released` — the sweep must see a clean exit, not a crash.
        signal.signal(signal.SIGTERM, lambda *_a: setattr(self, "_stop", True))
        signal.signal(signal.SIGINT, lambda *_a: setattr(self, "_stop", True))
        self._write_state("online")
        self._timeline(event="runner_up", text=f"{self.worker_id} runner online")
        try:
            while not self._stopped():
                hwm = self._read_hwm()
                pending = self._pending(hwm)
                if not pending:
                    self._write_state("idle")
                    time.sleep(POLL_S)
                    continue
                for m in pending:
                    if self._stopped():
                        break
                    seq = m["seq"]
                    self._write_state("working")
                    self._timeline(event="turn_start", seq=seq, kind=m.get("kind"))
                    try:
                        result = self.adapter.run_turn(m.get("text", ""))
                    except Exception as e:                      # adapter/process died mid-turn
                        # T3(b) (01-20): `kind` is the exception CLASS name, a structural
                        # field (like `state`/`event` elsewhere) — the engine's fleet-hold
                        # sweep reads THIS, never the text, to recognize a refusal-caused
                        # death (NET-ZERO: the refusal wording stays adapter-only knowledge).
                        self._timeline(event="turn_error", seq=seq,
                                       text=f"{type(e).__name__}: {e}",
                                       kind=type(e).__name__)
                        self._write_state("error")              # the sweep sees not-alive -> recover
                        return 1
                    self.turns += 1
                    # Record the high-water ONLY after the turn fully finished + its effects
                    # committed. A crash before this re-runs the same seq on restart (at-least-once);
                    # a crash after it skips the seq (already applied) — never double-applied.
                    self._write_hwm(seq)
                    if isinstance(result, dict):
                        # T3(a) (01-20): observability at the seam — subtype/is_error ride
                        # into the timeline instead of being discarded (a healthy turn's own
                        # record is {"subtype":"success","is_error":false,...}; this is that
                        # shape surfacing structurally, never re-derived from prose).
                        self._timeline(event="turn_done", seq=seq,
                                       text=(result.get("text") or "")[:200],
                                       subtype=result.get("subtype"),
                                       is_error=bool(result.get("is_error")))
                    else:
                        self._timeline(event="turn_done", seq=seq,
                                       text=(result or "")[:200])
            self._write_state("released")
            self._timeline(event="stopped", text="released by TRON")
            return 0
        finally:
            self.adapter.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-id", required=True)
    ap.add_argument("--worker-dir", required=True)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--cwd", default=None)
    ap.add_argument("--runtime", default=jobs.RUNTIME)
    ap.add_argument("--adapter", default=jobs.ADAPTER)
    a = ap.parse_args()
    return Runner(a.worker_id, a.worker_dir, a.session_id,
                  a.cwd, a.runtime, a.adapter).run()


if __name__ == "__main__":
    sys.exit(main())
