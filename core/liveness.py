"""core.liveness — the engine LIVENESS side-system: a worker that has gone
SILENT (not reporting/progressing at all — a dead/hung process) is pinged,
then declared stalled and recovered (rebuild-spec.md H1/H2; blueprint-
contracts.md §1 "Liveness ... feeds a single `worker:stalled` trigger", §5).

Distinct from `core/sentry.py`: `sentry` paces a GATE STAGE (an observable
predicate a worker hasn't satisfied yet, even though the worker itself may
still be alive and working); `liveness` watches WORKER SILENCE — whether the
worker is reporting/progressing AT ALL, independent of which gate stage it
happens to be sitting at, and independent of whether it even has a gate yet
(the pre-ASSIGN spawn->online window a worker can also go silent in). Two
different concerns, two different modules, both wrapping the SAME `core/
tick.py` pass from the outside — neither one edits `core/gate.py`.

Shape learned by READING `engine/fsm.py`'s silence sweep (`_sweep`, its own
`delta > esc * 60` / `delta > ping * 60 and not w.get("pinged_at")` ladder)
for SHAPE ONLY — re-expressed clean here for this stack's plain-manifest
idiom, never copied, and deliberately WITHOUT that module's runner-process/
jobs-index/refusal-death/orphan machinery, all out of scope for this brick.

## `last_seen` — updated in the route phase, read here

Every `manifest["workers"][agent_id]` record this module tracks carries a
`last_seen` field: the clock reading (see below) as of the last tick THAT
worker was seen to report ANYTHING structured (`worker.online`, `worker.
wall`, `worker.progress`, `worker.review_done` — any report carrying its own
`agent_id` — PLUS `worker.done`, the one report shape that carries a `block`
instead, resolved back to its gate's own `wid`). `core/router.py::touch`
(called once per drained report, at the TOP of `route()`, before any of that
module's own per-tag dispatch) is the ONLY writer of the "this worker
reported THIS tick" fact — it marks a transient `_reported` flag on the
worker record; THIS module (`sweep`, below, which `core/tick.py` runs AFTER
`router.route` in the SAME tick) is what actually turns that flag into a
fresh `last_seen` reading, off the ONE clock value this call reads — so a
worker that reports and a worker `sweep` independently notices holding are
always compared against the exact same "now".

## `sweep(eng, snapshot)` — the ladder

Walks every `manifest["workers"]` record (skipping `released` workers, and
any `review:<type>` pseudo-block worker — a reviewer's own silence is ALREADY
paced by `core/sentry.py::_pace_reviewers`, off the identical `holding_since`
idiom; this module never double-paces the same worker two different ways):

  - A worker whose flag says it reported THIS tick — OR whose runner is
    provably MID-TURN (the OPTIONAL `eng._worker_working(wid)` hook returns
    True: a real `worker_runner.py` in `state: "working"`, an agent actively
    executing a turn, not silent at all — see below) — has its `last_seen`
    (re)anchored to `now` and its episode cleared (`pinged_at` dropped) —
    "a worker that reports resets its liveness episode" (the design's own
    words), whether or not it was ever pinged first. This is what stops a
    real build turn (silent by nature — a single `claude -p` turn posts
    NOTHING to the engine inbox until it finishes, which can be many minutes)
    from being falsely declared stalled while it is legitimately working: an
    ACTIVELY-WORKING runner counts as seen; only a worker that is BOTH not
    reporting AND not working (a dead/hung/exited process, `state: idle`/
    `error`/gone) accrues silence toward ping/stall. A turn that genuinely
    hangs still recovers: `worker_runner.py`'s own turn-timeout flips it to
    `turn_error`/`state: error` (no longer "working"), so silence resumes
    accruing and the stall ladder fires as before. The hook is OPTIONAL and
    duck-typed exactly like `eng._now()` — absent (every pre-existing
    `core/*_rig.py` fixture), `sweep` behaves exactly as before (report-only
    "seen"), so no prior rig changes.
  - A worker `sweep` has never seen before (no `last_seen` on file yet — the
    spawn->online window, before `core/switchboard.py::fill` even wrote a
    `last_seen`, since that module is never edited by this brick) starts a
    fresh episode: anchored to `now`, no silence counted on this call.
  - Otherwise: `silent = now - last_seen`.
      * `silent >= silence_escalate_min` (once — the worker's slot is freed
        the SAME call, so there is no "again") — `worker:stalled` is
        ENGINE-declared (never a classify tag; see `core/router.py`'s own
        dispatch table, which has no arm for an inbound `worker.stalled`
        line at all) and recovered via `core.casestate.open_case` (source
        `"worker.stalled"`, kind `"stall"`) — the SAME raise-and-defer
        primitive a `worker.wall` report or a `sentry.cap` escalation
        already use: a parked operator case, never a silent kill. If the
        worker already has an open gate (`manifest["gates"][block]`),
        `open_case` itself flips that gate to `gate.STAGE_ESCALATED` — the
        SAME terminal vocabulary `core/pipeline.py::in_flight_blocks`
        already excludes, which is what frees the slot (module docstring of
        `core/casestate.py`, unchanged). A worker with NO gate yet (never
        got as far as `worker.online`) has nothing for `open_case` to flip —
        freeing ITS slot is this module's own job, mirroring `core/sentry.py
        ::_pace_reviewers`'s identical gateless-release precedent: the
        worker record itself is popped out of `manifest["workers"]`
        directly (the ONLY thing `core/pipeline.py::in_flight_blocks`'s
        pre-gate branch keys off of).
      * `silent >= silence_ping_min` (once per episode — `pinged_at` guards
        a second ping on a later call while still silent) — a
        `heartbeat.ping` order is sent via `eng._to_worker` (a PMT-PING
        equivalent; distinct `kind`, never impersonating a gate stage's own
        order).

Knobs (`silence_ping_min` / `silence_escalate_min`) are read via `core/
knobs.py` (wave 16 — the ONE knobs.yaml seam; this module used to read
`eng.ctx.load_knobs()`'s TOP LEVEL directly, which silently missed both
knobs on a real, schema-compliant project, since the schema nests them
under a top-level `knobs:` map — see `core/knobs.py`'s own module
docstring for the full story). Absent either key — checked via `Knobs.
declared(name)`, never a bare `None`-means-absent guess — `sweep` is a
genuine no-op (returns immediately, touches NOTHING — not even the
transient `_reported` flags `core/router.py::touch` may have set this
tick, which is harmless: nothing else in this stack ever reads that flag):
every rig before this wave (landing/gate/gate_full/tick/dispatch/
multiblock/sentry/casestate/architect/reviewers) ships no
`silence_ping_min`/`silence_escalate_min` knob at all, so this brick never
touches any of their flows — preserved exactly, now correctly checked at
the NESTED location instead of the buggy flat one.

Clock: the SAME pluggable-clock discipline `core/sentry.py` uses — `eng.
_now()` when the caller provides one, read once per `sweep()` call, else an
internal counter persisted at `manifest["liveness"]["clock"]` (a SEPARATE
counter from `sentry`'s own `manifest["sentry"]["clock"]` — both increment
exactly once per tick, so their readings track each other tick-for-tick
whenever both fall back, but neither module ever reads the other's counter
directly). A rig can therefore pin exact ping/stall boundaries the identical
way `core/sentry_rig.py` already does for nudge/cap, without this module
needing to know or care whether it is wall-clock minutes or a synthetic tick
count — only relative deltas (`now - last_seen`) are ever compared against
the two knobs.

Duck-typed `eng` contract: everything `core/sentry.py`/`core/casestate.py`
already need (`eng._to_worker`, `eng.dry`, `eng.log`, `eng.ctx`,
`eng._release_worker`, `eng._page_operator`) PLUS the OPTIONAL `eng._now()`
— no new REQUIRED surface, so every existing `core/*_rig.py` eng fixture
keeps working completely unmodified.

No git/subprocess of any kind in this module: knob reads go through `core/
knobs.py::load` (plain YAML file IO under the hood, `engine/ctx.py::Ctx.
load_knobs`); everything else is a plain manifest mutation, the same
"workers/gates are a direct alias onto the manifest" idiom every other
`core/*.py` module in this stack already uses.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import casestate   # noqa: E402 — core/casestate.py, the parked-case recovery primitive
import knobs as knobs_mod   # noqa: E402 — core/knobs.py, the ONE knobs.yaml seam (wave 16)


def _worker_active(eng, wid, reported):
    """A worker is ACTIVE this tick if it reported (`reported`, the transient
    flag `core/router.py::touch` set) OR its runner is provably MID-TURN —
    the OPTIONAL, duck-typed `eng._worker_working(wid)` hook (a real
    `worker_runner.py` in `state: "working"`; `core/engine.py` wires it to
    `engine/jobs.py`, a rig may inject a fake, and an `eng` without it — every
    pre-existing fixture — degrades to report-only "seen", unchanged). This is
    the ONE thing that keeps a legitimately-working, inbox-silent build turn
    from being falsely stalled; a hung turn stops being "working"
    (`worker_runner.py`'s turn-timeout → `state: error`), so the stall ladder
    still recovers it. Never raises out: a hook that itself errors reads as
    "not provably working" (fail toward the existing silence ladder, never a
    crash)."""
    if reported:
        return True
    fn = getattr(eng, "_worker_working", None)
    if not callable(fn):
        return False
    try:
        return bool(fn(wid))
    except Exception:   # noqa: BLE001 — a broken hook must never crash the sweep
        return False


def _silence_knobs(eng):
    """`core/knobs.py::Knobs`, read fresh off `eng.ctx` — or the module's
    own empty singleton when `eng` carries no `ctx` at all (this module's
    pre-wave-16 tolerance for a duck-typed `eng` stand-in without one,
    preserved: `core/knobs.py::load(None)` already degrades to "nothing
    configured" the same way a missing knobs.yaml file does)."""
    ctx = getattr(eng, "ctx", None)
    return knobs_mod.load(ctx)


def _ping_min(eng):
    k = _silence_knobs(eng)
    return k.silence_ping_min if k.declared("silence_ping_min") else None


def _escalate_min(eng):
    k = _silence_knobs(eng)
    return k.silence_escalate_min if k.declared("silence_escalate_min") else None


def _clock(eng, manifest):
    """The ONE clock this ladder reads — see module docstring. `eng._now()`
    when present (a plain callable, no required signature beyond zero-arg),
    else an internal counter persisted at `manifest["liveness"]["clock"]`,
    incremented exactly once per call — the SAME discipline `core/sentry.py
    ::_clock` uses for its own, separate counter."""
    now_fn = getattr(eng, "_now", None)
    if callable(now_fn):
        return now_fn()
    counters = manifest.setdefault("liveness", {})
    counters["clock"] = counters.get("clock", 0) + 1
    return counters["clock"]


def touch(workers, gates, rep):
    """Called once per drained report, from `core/router.py::route`, BEFORE
    that module's own per-tag dispatch: marks the reporting worker's record
    with a transient `_reported` flag — the "this worker said SOMETHING this
    tick" fact `sweep` (below) turns into a fresh `last_seen` reading once
    per tick, off the ONE clock reading that call mints.

    Resolution: `agent_id` (or `worker_id`) directly off the report when
    present — `worker.online`, `worker.wall`, `worker.progress`, `worker.
    review_done` all carry one. `worker.done` is the ONE report shape that
    names a `block` instead (no `agent_id` — `core/gate.py`'s own
    `local_report` contract never required one) — resolved back to that
    block's OWN gate-recorded `wid`, exactly the same "the worker names
    itself; the engine only ever records what it reports" discipline `core/
    router.py::_route_online`'s ASSIGN already keeps. Any other structured
    tag (`operator.decision`, `architect.reconciled`) names no WORKER of its
    own and is left untouched — never guessed at.

    Unknown/unrecorded agent-id (no matching `manifest["workers"]` entry —
    e.g. a rig that seeds a gate directly, bypassing `core/switchboard.py`'s
    own SPAWN, so no worker record exists to touch at all) is a harmless
    no-op, same forgiving discipline every other structured-report handler
    in this stack already keeps for an unrecorded sender."""
    tag = rep.get("tag")
    agent_id = rep.get("agent_id") or rep.get("worker_id")
    if not agent_id and tag == "worker.done":
        block = rep.get("block")
        gate_state = gates.get(block) if block else None
        agent_id = gate_state.get("wid") if gate_state else None
    if agent_id and agent_id in workers:
        workers[agent_id]["_reported"] = True


def sweep(eng, snapshot):
    """One tick's worth of the silence ladder — see module docstring.
    Returns `{"pinged": [wid, ...], "stalled": [(block, wid, case_id), ...]}`
    — a NON-durable convenience for the caller/rig, exactly like `core.
    sentry.pace`'s own return shape; `manifest["workers"][*]["last_seen"]`/
    `manifest["cases"]` are the durable record.

    Absent either silence knob, this is a genuine no-op (see module
    docstring) — every rig before this wave is untouched."""
    manifest = snapshot.manifest
    ping_min = _ping_min(eng)
    escalate_min = _escalate_min(eng)
    if ping_min is None or escalate_min is None:
        return {"pinged": [], "stalled": []}

    workers = manifest.get("workers") or {}
    gates = manifest.get("gates") or {}
    now = _clock(eng, manifest)

    pinged, stalled = [], []
    for wid, w in list(workers.items()):
        if w.get("status") == "released":
            continue
        block = w.get("block")
        if isinstance(block, str) and block.startswith("review:"):
            # A reviewer's own silence is ALREADY paced by core/sentry.py's
            # `_pace_reviewers` arm, off the identical holding_since idiom —
            # never a second, competing mechanism for the same worker.
            continue

        reported = w.pop("_reported", False)
        if _worker_active(eng, wid, reported):
            # Reported this tick OR provably mid-turn (a real working runner)
            # — either way genuinely active: reset the liveness episode.
            w["last_seen"] = now
            w.pop("pinged_at", None)
            continue

        if w.get("last_seen") is None:
            # First-ever sighting of this worker record (the spawn->online
            # window, or a worker `core/switchboard.py::fill` just minted
            # THIS tick, before `core/router.py::touch` could ever have
            # marked it) — progress clears the clock; no silence counted on
            # the call that first notices a worker exists.
            w["last_seen"] = now
            continue

        silent = now - w["last_seen"]

        if silent >= escalate_min:
            detail = (f"worker {wid!r} (block={block!r}) silent for "
                     f"{silent} pace unit(s) with no report since "
                     f"last_seen={w['last_seen']} (>= silence_escalate_min="
                     f"{escalate_min}) — liveness declares worker:stalled; "
                     f"recovered via a parked operator case, never a "
                     f"silent kill")
            eng.log("flow", f"liveness: STALLED {wid} — {detail}")
            case_id = casestate.open_case(eng, manifest, block, "worker.stalled",
                                          detail, worker_id=wid, kind="stall")
            if block not in gates:
                # No gate ever opened for this worker (it never got as far
                # as its own `worker.online` ASSIGN) — `casestate.open_case`
                # had no gate to flip to STAGE_ESCALATED, so freeing this
                # slot is this module's own job (mirrors `core/sentry.py::
                # _pace_reviewers`'s identical gateless-release precedent:
                # popping the worker record IS what frees the slot per
                # `core/pipeline.py::in_flight_blocks`'s pre-gate branch).
                workers.pop(wid, None)
            stalled.append((block, wid, case_id))
            continue

        if silent >= ping_min and w.get("pinged_at") is None:
            if wid and not eng.dry:
                eng._to_worker(
                    wid,
                    f"[TRON]  {wid} — silent for {silent} pace unit(s) with "
                    f"no report (silence_ping_min={ping_min}) — a ping. "
                    f"Silence past silence_escalate_min={escalate_min} is "
                    f"declared stalled and parked for the operator.",
                    "heartbeat.ping")
            w["pinged_at"] = now
            eng.log("flow", f"liveness: pinged {wid} (block={block!r}, "
                            f"silent={silent}, silence_ping_min={ping_min})")
            pinged.append(wid)

    return {"pinged": pinged, "stalled": stalled}
