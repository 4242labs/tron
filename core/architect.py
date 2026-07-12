"""core.architect — the persistent, POOL-EXCLUDED architect (blueprint-
contracts.md §1 "Architect"; rebuild-spec.md C6/D1 + T5's `architect.
reconciled` -> `block:<block>:reconciled`). Drains a FIFO `manifest[
"architect_queue"]` at most ONE job per tick, in two job-kinds:

  `forward`   — author a MISSING upcoming block file (an in-scope roadmap
              row with no block file yet). The architect writes the block
              doc on its OWN `arch/<block>-forward` branch and lands it via
              `core.landing.land_via_grant` under a CONTENT-BOUND case-id
              (`role="forward"` — distinct from gate.py's `merge`/`record`
              roles for the SAME branch-naming convention, so the three can
              never collide on each other's receipts). Once landed, the
              block file is on trunk and the block becomes dispatchable
              normally — no bookkeeping of this module's own is needed past
              that point.

  `reconcile` (M-05) — a block landing `✅` enqueues a reconcile for the
              NEXT in-scope, not-yet-dispatched block (by pipeline order);
              that block's dispatch is GATED until the reconcile completes.
              This module never re-checks real content in this brick (no
              LLM here — see the module's own read-first list, which skips
              log-review/triage) — it ORDERS the reconcile (a structured
              `arch.reconcile` message) and waits for a structured
              `architect.reconciled` report to come back through `core/
              router.py` (the SAME two-step "order then observe a report"
              discipline `core/gate.py`'s own stages already use — the
              report is drained+routed on a LATER tick, never trusted
              same-call). `core/router.py` records the completion into
              `manifest["reconciled"]`; THIS module only clears its own
              `current_job` (frees the architect to pop its next job) once
              it observes that.

Persistent + pool-excluded (blueprint's own words): modeled ENTIRELY in
`manifest["architect"]` (status/current_job) + `manifest["architect_queue"]`
(the FIFO) — NEVER a `manifest["workers"]` entry, so `core/switchboard.py`'s
`_active_worker_count`/`core/pipeline.py::in_flight_blocks` (both keyed off
`manifest["workers"]`/`manifest["gates"]`) never count it toward a worker
slot. `eng._spawn_architect()` — a NEW stubbed hook, called exactly ONCE,
lazily, the first tick this module actually needs to pop a job (never
called at all by a caller whose architect_queue stays empty its whole run —
see `core/architect_rig.py`'s docstring for why the other 8 rigs' `eng`
stand-ins never need to implement it).

Wire (`core/tick.py`, two calls straddling `core/switchboard.py::fill`):
  `enqueue(eng, manifest, view, landed_blocks)` — called BEFORE fill(),
  same tick as a block's `record_landed` outcome: creates a fresh gate (or a
  fresh forward job) the SAME tick it's warranted, so `gated_blocks` below
  (read by `core/tick.py` to build fill()'s excluded-block set) reflects it
  immediately — a fresh gate excludes same-tick, never a tick late.

  `advance(eng, manifest)` — called AFTER fill(): progresses whatever job
  is current by exactly one step, and is the ONE place a completed
  reconcile job's `current_job` gets cleared (freeing the block for
  dispatch). Running this AFTER fill() (not before) is deliberate, not
  incidental: `core/router.py` may have just recorded a block's
  `manifest["reconciled"]` entry THIS SAME tick's `route()` (which runs
  BEFORE fill()) — clearing `current_job` immediately would let fill(),
  later in this SAME tick, dispatch the block the INSTANT its report
  drains, collapsing `reconciled_tick == spawn_tick`. Positioning the clear
  AFTER fill() instead means a block stays gated (`gated_blocks` still
  reports it, since `current_job` hasn't been cleared yet) through the
  WHOLE tick its `architect.reconciled` report is routed, and only becomes
  dispatchable starting the NEXT tick — `core/architect_rig.py`'s own
  ordering proof (`spawn_tick > reconciled_tick > done_tick`, all STRICT)
  is exactly this.

`gated_blocks(manifest)` — read by `core/tick.py` right before calling
`switchboard.fill` (unioned with `core/casestate.py::dispatch_excluded_
blocks`, the SAME "hand fill() a filtered dispatch view" mechanism wave 8
already established): every block with an outstanding (queued OR current)
reconcile job. `forward` jobs need no such exclusion — their target block
has no block file yet, so `core/pipeline.py::dispatchable` (which requires
`has_block_file`) already excludes it structurally; nothing more to do here.

Dedupe throughout (`_enqueue_forward_jobs`/`_enqueue_reconcile`): never a
second job for a block already queued/current; a reconcile is never
re-enqueued for a block already in `manifest["reconciled"]`; forward-looking
only — `_next_reconcile_target` walks living-doc order STRICTLY AFTER the
just-landed block and skips anything abandoned (`core/casestate.py`),
parked (an open case), or already in-flight (`core/pipeline.py::
in_flight_blocks`) — never reopens a done block, never re-targets one
already mid-drive.

Wave 18 (GAP-E, architect-first routing for ALL wall kinds): a FOURTH job
kind, `triage` (PMT-TRIAGE) — the ONE place a raised wall/escalation
(`worker.wall`, a `sentry.cap` escalation, a liveness `worker.stalled`
recovery — every `core/casestate.py::open_case` caller — PLUS `core/
classify.py`'s own `unclassified` result) lands FIRST, never an immediate
operator page. `enqueue_triage` (below) is called from TWO places:
`core/casestate.py::open_case` (a real casestate case behind it, `case_id`
set) and `core/classify.py::_triage_unclassified` (case-less — raw free
text with no block/gate to park, `case_id=None`). One job of triage
throughput per tick, same FIFO discipline as `forward`/`reconcile`/`log`.
`_advance_triage` (below) orders ONCE (`arch.triage`, a structured ask for a
verdict ∈ `{scope_forward, answer, operator}`), then waits for a routed
`architect.triage_verdict` report (`core/router.py`, recorded into
`manifest["triage_verdicts"]` — the SAME two-step "order then observe a
report" discipline `reconcile`'s own `architect.reconciled` already uses,
drained on a LATER tick, never trusted same-call) before applying it:
`answer`/`operator` resolve in ONE step via `core.casestate.
architect_resolve` (case-bearing) or directly (case-less: `answer` relays a
note, `operator` mints via `core.casestate.open_operator_case`) —
`scope_forward` ADDITIONALLY authors + lands ONE real adhoc block first
(mirrors `_advance_log`'s own single-entry order-then-poll-and-land shape,
reusing the Wave-1 landing primitive verbatim) before resolving the
original case, if any — the wall/escalation only clears once the
forward-looking work has genuinely landed on trunk. An unrecognized verdict
falls back to `operator` — never silently dropped, the one safe default:
it still reaches a human, just via the loudest channel.

No raw git of any kind here — `core.gitobs` (the ONE seam) for the forward
job's patch-id read, `core.landing.land_via_grant`/`.paperwork_case_id`
(Wave-1's ONE landing primitive, imported and reused verbatim, never
forked) for the forward job's content-bound land. A plain manifest mutation
otherwise, the same "gates is a direct alias onto the manifest" idiom every
other `core/*.py` module already uses.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gitobs     # noqa: E402 — core/gitobs.py, the ONE git-observation seam
import landing    # noqa: E402 — core/landing.py, Wave-1's ONE landing primitive
import pipeline   # noqa: E402 — core/pipeline.py, in_flight_blocks (dedupe read)
import casestate  # noqa: E402 — core/casestate.py, parked_blocks (dedupe read)

ARCHITECT_WID = "architect"

# Mirrors core/session.py's own IN_SCOPE_STATUSES verbatim (never forked into
# a second constant this module could silently drift from).
IN_SCOPE_STATUSES = ("to-do", "in-progress")


def new_state():
    """The initial `manifest["architect"]` shape — persistent, idle, never
    yet spawned (`eng._spawn_architect()` fires lazily, once, off this flag,
    the first tick a job is actually popped — see module docstring)."""
    return {"status": "idle", "current_job": None, "spawned": False}


def gated_blocks(manifest):
    """Every block with an outstanding (queued OR current) `reconcile` job —
    `core/tick.py`'s own exclusion-set read, called right before `core/
    switchboard.py::fill`. A `forward` job's target needs no entry here
    (see module docstring: `has_block_file` already excludes it)."""
    arch = manifest.get("architect") or {}
    queue = manifest.get("architect_queue") or []
    gated = {j["block"] for j in queue if j.get("kind") == "reconcile" and j.get("block")}
    cur = arch.get("current_job")
    if cur and cur.get("kind") == "reconcile" and cur.get("block"):
        gated.add(cur["block"])
    return gated


def _forward_branch(block):
    return f"arch/{block}-forward"


def _has_forward_job(manifest, block):
    queue = manifest.get("architect_queue") or []
    if any(j.get("kind") == "forward" and j.get("block") == block for j in queue):
        return True
    arch = manifest.get("architect") or {}
    cur = arch.get("current_job")
    return bool(cur and cur.get("kind") == "forward" and cur.get("block") == block)


def _has_triage_job(manifest, case_id):
    """Dedupe for a case-bearing triage job only (`case_id is not None`) —
    a case-less one (`core/classify.py`'s unclassified path) is NEVER
    deduped, same "no dedupe across independent occurrences" discipline
    `enqueue_log_review` already keeps for its own findings."""
    if case_id is None:
        return False
    queue = manifest.get("architect_queue") or []
    if any(j.get("kind") == "triage" and j.get("case_id") == case_id for j in queue):
        return True
    arch = manifest.get("architect") or {}
    cur = arch.get("current_job")
    return bool(cur and cur.get("kind") == "triage" and cur.get("case_id") == case_id)


def _has_reconcile_job(manifest, block):
    queue = manifest.get("architect_queue") or []
    if any(j.get("kind") == "reconcile" and j.get("block") == block for j in queue):
        return True
    arch = manifest.get("architect") or {}
    cur = arch.get("current_job")
    return bool(cur and cur.get("kind") == "reconcile" and cur.get("block") == block)


def _enqueue_forward_jobs(eng, manifest, view):
    """Clear-ahead (blueprint §1 SWITCHBOARD's own step, re-expressed here
    for the architect's OWN queue): every in-scope roadmap row with no block
    file yet gets a `forward` job — idempotent, never a second job for a
    block already queued/current."""
    queue = manifest.setdefault("architect_queue", [])
    for row in view:
        if row.get("has_block_file"):
            continue
        if row.get("status") not in IN_SCOPE_STATUSES:
            continue
        block = row["id"]
        if not block or _has_forward_job(manifest, block):
            continue
        queue.append({"kind": "forward", "block": block, "branch": _forward_branch(block),
                      "ordered": False, "case_id": None, "landed": False})
        eng.log("flow", f"architect: clear-ahead enqueued forward for missing "
                        f"block file {block!r}")


def _next_reconcile_target(view, manifest, done_block):
    """The next in-scope, not-done, has-a-file, not-yet-in-flight block AFTER
    `done_block` by living-doc order — the one a just-landed block's drift
    could invalidate (M-05). Skips (never targets, keeps looking forward):
    an abandoned block (`core/casestate.py`'s permanent drop), a currently
    PARKED block (an open case), and anything already in-flight (a live
    worker or open gate — `core/pipeline.py::in_flight_blocks`, the SAME
    definition dispatch eligibility itself uses) — only a clean, untouched
    block is ever reconcile-targeted."""
    abandoned = set(manifest.get("abandoned_blocks") or [])
    parked = casestate.parked_blocks(manifest)
    inflight = pipeline.in_flight_blocks(manifest)
    rows = sorted(view, key=lambda r: r.get("order") or 1e9)
    seen = False
    for r in rows:
        if r["id"] == done_block:
            seen = True
            continue
        if not seen:
            continue
        bid = r["id"]
        if bid in abandoned or bid in parked or bid in inflight:
            continue
        if r.get("status") in IN_SCOPE_STATUSES and r.get("has_block_file"):
            return bid
    return None


def _enqueue_reconcile(eng, manifest, view, done_block):
    reconciled = set(manifest.get("reconciled") or [])
    nxt = _next_reconcile_target(view, manifest, done_block)
    if not nxt or nxt in reconciled or _has_reconcile_job(manifest, nxt):
        return
    queue = manifest.setdefault("architect_queue", [])
    queue.append({"kind": "reconcile", "block": nxt, "after": done_block, "ordered": False})
    eng.log("flow", f"architect: {done_block!r} landed ✅ -> enqueued reconcile "
                    f"for {nxt!r} (M-05) — its dispatch is gated until reconciled")


def _fleet_paused(manifest):
    """Wave 19 (GAP-C, fleet-outage self-release): True while a still-open
    fleet-outage case sits on file — an IDENTICAL, deliberately duplicated
    helper to `core/switchboard.py`'s own (never imported — keeps this
    module's existing dependency direction, `casestate`/`pipeline`/
    `gitobs`/`landing` only, unchanged); both read the SAME `manifest[
    "cases"]` shape, so an operator resume or an architect self-resolve
    (`core/casestate.py::settle`/`architect_resolve`, both unedited by this
    wave) is honored the instant either clears the case, from either
    module, with no cross-import and no second boolean to keep in sync."""
    return any(c.get("kind") == "fleet_outage" and c.get("decision") is None
              for c in (manifest.get("cases") or {}).values())


def enqueue(eng, manifest, view, landed_blocks):
    """Called BEFORE `core/switchboard.py::fill` each tick (`core/tick.py`):
    (1) clear-ahead `forward` jobs for every in-scope row missing a block
    file; (2) a `reconcile` job for the next in-scope block after each block
    whose gate outcome THIS tick was `record_landed` (✅ genuinely observed
    on trunk). Idempotent throughout — see module docstring.

    Wave 19 (GAP-C): while a fleet-outage case sits open, (1) — NEW
    forward-looking work discovery — is skipped ("spawn NOTHING new while
    paused", the design's own words, extended to the architect's own queue,
    never just `core/switchboard.py`'s worker-pool spawn); (2) is left
    unguarded — it only ever fires for a block that landed THIS tick, which
    structurally never happens while dispatch is paused (nothing new lands
    with nothing new spawned), so no separate guard is needed there."""
    manifest.setdefault("architect", new_state())
    manifest.setdefault("architect_queue", [])
    if not _fleet_paused(manifest):
        _enqueue_forward_jobs(eng, manifest, view)
    for block in landed_blocks:
        _enqueue_reconcile(eng, manifest, view, block)


def _next_triage_id(manifest):
    """A deterministic, monotonically-numbered triage-job id — a manifest-
    persisted counter (`manifest["triage_seq"]`), never `uuid`/`random`
    (mirrors `core/casestate.py::next_case_id`'s own idiom). This is the
    correlation handle `manifest["triage_verdicts"]` is keyed by — NEVER
    `case_id`, which is legitimately `None` for a case-less triage job
    (`core/classify.py`'s unclassified path) and would otherwise collide
    across two independent case-less jobs raised over the life of one run."""
    n = int(manifest.get("triage_seq", 0)) + 1
    manifest["triage_seq"] = n
    return f"triage-{n}"


def enqueue_triage(eng, manifest, case_id, source, block, detail, worker_id=None):
    """Wave 18 (GAP-E): a raised wall/escalation becomes a PMT-TRIAGE job
    FIRST — NEVER an immediate operator page. Called from `core/
    casestate.py::open_case` (case-bearing, `case_id` set — worker.wall/
    sentry.cap/liveness-stall) and `core/classify.py::_triage_unclassified`
    (case-less, `case_id=None`, `block=None` — raw free text). Idempotent
    for a case-bearing job only — see `_has_triage_job`'s own docstring."""
    manifest.setdefault("architect", new_state())
    queue = manifest.setdefault("architect_queue", [])
    # R1a (ADR-0005) final backstop: the architect can never be the SOURCE of a
    # triage — its own narration creates nothing. The call-site guards (classify /
    # router, ahead of open_case) are primary; this is defense-in-depth so no
    # future creation path can queue an architect-sourced triage. Its OWN in-flight
    # triage resolves via the R1b idle backstop, never by self-enqueue.
    if worker_id == ARCHITECT_WID:
        eng.log("flow", "architect: enqueue_triage refused — sender is the architect "
                        "itself (R1a self-source backstop); created nothing")
        return
    if _has_triage_job(manifest, case_id):
        return
    triage_id = _next_triage_id(manifest)
    queue.append({"kind": "triage", "triage_id": triage_id, "case_id": case_id,
                  "source": source, "block": block, "detail": detail,
                  "worker_id": worker_id, "ordered": False, "verdict": None,
                  "note": None, "adhoc": None, "resolved": False})
    eng.log("flow", f"architect: PMT-TRIAGE queued (triage_id={triage_id!r}, "
                    f"case_id={case_id!r}, source={source!r}, "
                    f"block={block!r}) — architect-first, never an immediate "
                    f"operator page")


def _order_triage(eng, job):
    if not eng.dry:
        eng.emit(
            "arch.triage",
            f"[TRON]  architect — TRIAGE (triage_id={job['triage_id']!r}, "
            f"case_id={job.get('case_id')!r}, source={job.get('source')!r}, "
            f"block={job.get('block')!r}): {job.get('detail')}\nReply with a "
            f"structured architect.triage_verdict (triage_id="
            f"{job['triage_id']!r}, verdict in "
            f"scope_forward|answer|operator[, note]).",
            slots={"detail": job.get("detail"), "sender": job.get("source")},
            worker_id=ARCHITECT_WID,
            kind="arch.triage")
    job["ordered"] = True
    eng.log("flow", f"architect[triage:{job['triage_id']}]: ordered triage "
                    f"(source={job.get('source')!r})")


# R1b (ADR-0005) — the architect-idle, source-directional triage backstop.
#
# A triage the architect has been ordered but has NOT resolved with a structured
# `architect.triage_verdict` must neither WEDGE the fleet nor SWALLOW a real
# escalation:
#   • wedge — blocker B: the architect stuck ~13 min on a block-less worker.wall
#     it could not verdict, blocking every later job + session-end;
#   • swallow — M1/F2: the old self-guards benign-'answer'-ed a GENUINE escalation
#     the instant the architect narrated a turn (the courier harvests every turn),
#     so the planted operator wall never paged — the false-green disease.
#
# The backstop resolves the triage once the architect has genuinely TAKEN ITS TURN
# and settled idle with no verdict — keyed on the REAL runner signal
# `eng._worker_working(ARCHITECT_WID)` (the same seam liveness/sentry gate on),
# NOT a wall-clock tick count. A `claude -p` turn posts nothing until it finishes,
# so while the architect is provably mid-turn the backstop HOLDS (idle_ticks reset);
# it only arms across genuinely settled-idle ticks. `_ARCHITECT_IDLE_DEBOUNCE_TICKS`
# is a small debounce so a brief between-turns idle blip of a multi-turn architect
# is not mistaken for "finished" — it is NOT a timeout (the counter freezes the
# instant the architect is working again), it debounces the idle signal.
#
# Resolution is DIRECTIONAL by the TRUSTED source label (set by the router/engine
# at enqueue — `casestate.open_case` / `router` / `classify` — never by classify's
# tag of the architect's own prose): a low-confidence source resolves benign
# ('answer', never wedges session-end); a genuine escalation resolves LOUD
# ('operator', its real page — never swallowed). This replaces BOTH the
# classify.unclassified-only phantom grace (which left a real worker.wall wedged)
# and the two source-agnostic self-guards' benign write (which swallowed genuine
# walls); the self-source CREATION guards move to R1a (classify.py / router.py).
_ARCHITECT_IDLE_DEBOUNCE_TICKS = 2
_LOW_CONFIDENCE_TRIAGE_SOURCES = frozenset({"classify.unclassified"})
# ADR-0006 R1c: how many ticks an ORDERED architect may sit never-having-worked
# before its stall is paged. Only the started-latch's `arch_started==False` window
# is governed here (a started-then-hung architect is owned by the settled-idle/R1d
# backstops, which CAN false-clear-safely because the turn provably ran). Sized
# GENEROUSLY: the sole job is to beat the run's wall-clock budget (default 60 min)
# so a genuinely dead/never-spawned architect is paged rather than silently wedging
# to budget — it need NOT be tight. At the live poll cadence (~20s/tick) 15 ticks
# ≈ 5 min, comfortably longer than any real cold start (the runner writes
# `state="working"` at turn-START / mailbox-pickup, so this window is bounded by
# process-spawn + poll latency, NOT LLM response latency) yet ~55 min before budget.
# (Peer-review note: R1c pages straight to the operator with no ping step; a
# graduated ping-then-page ladder like the worker silence net is a future refinement
# — watch the real cold-start timing on the next live SIM.)
_ARCHITECT_COLD_START_CAP_TICKS = 15


def _architect_settled_idle(eng, job):
    """The shared R1b ENGINE-STATE signal: True once the architect has genuinely
    TAKEN its ordered turn for `job` and settled idle. HELD while the architect is
    provably mid-turn (`eng._worker_working(ARCHITECT_WID)` — a real `claude -p`
    turn posts nothing until it finishes, so only genuine settled-idle time arms
    the backstop; `idle_ticks` resets the instant it works again), then armed after
    `_ARCHITECT_IDLE_DEBOUNCE_TICKS` settled-idle ticks (a debounce for a between-
    turns blip, NOT a wall-clock timeout). Duck-typed + crash-safe, exactly as
    core/sentry.py + core/liveness.py read the SAME hook; an absent/erroring hook
    (dry rigs) reads not-working, so the backstop arms across ordinary ticks there.
    Used by BOTH `_advance_triage` and the reconcile arm of `advance` — one
    invariant ('the architect took its turn and settled with no structured
    result'), never two copies that could drift.

    STARTED-LATCH (peer-review hardening): the debounce distinguishes 'settled
    after a genuine turn' from 'NEVER STARTED a turn' only when a real liveness
    hook is present. When `_worker_working` is callable (a live run), the backstop
    arms ONLY after the architect has been observed working at least once for this
    job (`job["arch_started"]`) — else a slow cold-start or a silently-dead
    architect (which NO liveness net watches, since it is pool-excluded from
    `manifest["workers"]`) would arm the backstop having never reconciled: a silent
    false-clear. A never-started architect instead HOLDS (the run fails honestly on
    budget, never false-greens). When the hook is ABSENT (dry rigs), turn-start is
    unobservable, so the documented dry behavior is preserved: arm across the idle
    debounce."""
    if not job.get("ordered"):
        return False
    fn = getattr(eng, "_worker_working", None)
    if not callable(fn):
        # No liveness hook (dry rigs): turn-start is unobservable — preserve the
        # documented 'arm across the idle debounce' behavior the R1b rigs rely on.
        job["idle_ticks"] = job.get("idle_ticks", 0) + 1
        return job["idle_ticks"] >= _ARCHITECT_IDLE_DEBOUNCE_TICKS
    try:
        working = bool(fn(ARCHITECT_WID))
    except Exception:   # noqa: BLE001 — a broken hook never wedges the job
        working = False
    if working:
        job["arch_started"] = True   # latch: the architect provably took its turn
        job["idle_ticks"] = 0
        return False
    if not job.get("arch_started"):
        # Not working AND never observed working: a cold-start/dead architect, not
        # a settled one. HOLD — never arm the backstop on a turn that never ran.
        # (ADR-0006 R1c watches THIS window and pages the operator if it persists,
        # so a dead architect no longer wedges to budget silently.)
        return False
    job["idle_ticks"] = job.get("idle_ticks", 0) + 1
    return job["idle_ticks"] >= _ARCHITECT_IDLE_DEBOUNCE_TICKS


def _architect_liveness_ladder(eng, manifest):
    """ADR-0006 R1c: the dedicated liveness net for the architect, which is
    pool-excluded from `manifest["workers"]` so NEITHER `core/liveness.py` nor
    `core/sentry.py` ever watches it. Scope is exactly the one window no other
    backstop covers: an architect that has been ORDERED a job but has NEVER been
    observed working it (`arch_started` unset) — i.e. a cold-start that never
    started, or an architect that died/hung before its first turn. The
    started-latch (`_architect_settled_idle`) deliberately HOLDS that window
    (never false-clears a turn that never ran); R1c makes the hold LOUD instead
    of silent-to-budget: after a generous cold-start tolerance it pages the
    operator ONCE (the wave-17 `casestate.reping` FLOOR then re-pings that one
    case). A started-then-hung architect is NOT R1c's job — `arch_started` is
    set, so this returns early and the settled-idle/R1d backstops own it.

    Live-only: with no `_worker_working` hook (dry rigs that don't wire one) R1c
    is inert — turn-start is unobservable, so the started-latch's dry path
    governs, exactly as the settled-idle backstop documents. Idempotent per job:
    the once-guard lives on the job dict, so it resets when the job changes."""
    arch = manifest.setdefault("architect", new_state())
    cur = arch.get("current_job")
    if not cur or not cur.get("ordered"):
        return                       # nothing ordered — no stall to watch
    if cur.get("arch_started"):
        return                       # it started; settled-idle/R1d own completion now
    fn = getattr(eng, "_worker_working", None)
    if not callable(fn):
        return                       # dry rig, no liveness hook — R1c inert
    try:
        if fn(ARCHITECT_WID):
            cur["arch_started"] = True   # observed working — hand off to the started-latch
            return
    except Exception:                # noqa: BLE001 — a broken hook never pages
        return
    cur["cold_ticks"] = cur.get("cold_ticks", 0) + 1
    if cur["cold_ticks"] < _ARCHITECT_COLD_START_CAP_TICKS:
        return                       # tolerate a legitimate cold start / spawn latency
    if cur.get("stall_paged"):
        return                       # already paged this stall exactly once
    detail = (f"architect ordered a {cur.get('kind')!r} job for "
              f"{cur.get('block')!r} but has NOT started a turn in "
              f"{cur['cold_ticks']} ticks (cold-start/dead-before-first-turn; "
              f"the architect is pool-excluded from every worker liveness net) "
              f"— R1c dedicated architect-liveness escalation, paged once")
    casestate.open_operator_case(eng, manifest, cur.get("block"),
                                 "architect.stalled", detail,
                                 worker_id=ARCHITECT_WID, kind="stall")
    cur["stall_paged"] = True
    eng.log("flow", f"architect: STALLED before first turn — {detail}")


def _backstop_refused_authoring(eng, manifest, cur):
    """ADR-0006 R1d: a STARTED-then-REFUSED forward/log job — the architect took
    its ordered turn (`arch_started`, so `_architect_settled_idle` can arm) and
    settled idle, yet `land_via_grant` still reports `"fail-closed"` (its patch-id
    is unresolvable == it authored NO branch, prose instead of a file). Resolve
    LOUD: page the operator once and free the architect. Never poll a
    never-authored branch to budget (the log/forward wedge A3), and — for a
    log-review — never silently DROP the reviewer's findings by benign-clearing.
    Clearing `current_job` at the call site is the once-guard (the job is gone
    next tick, so `open_operator_case`'s non-idempotency can't storm). A cold
    architect that NEVER started is not here — R1c (`_architect_liveness_ladder`)
    owns that window."""
    kind = cur.get("kind")
    detail = (f"architect ordered a {kind!r} job for {cur.get('block')!r} and "
              f"settled idle having authored NO branch (land grant fail-closed) "
              f"— started-then-refused authoring; routed to operator (ADR-0006 "
              f"R1d), never a silent wedge or a dropped log-review finding")
    casestate.open_operator_case(eng, manifest, cur.get("block"),
                                 f"architect.{kind}_refused", detail,
                                 worker_id=ARCHITECT_WID, kind="stall")
    eng.log("flow", f"architect[{kind}:{cur.get('block')}]: refused authoring "
                    f"(fail-closed + settled idle) -> operator (R1d)")


def _advance_triage(eng, manifest, job):
    """One triage-job step (GAP-E, wave 18) — see module docstring for the
    full order-then-observe-then-apply shape. Sets `job["resolved"] = True`
    (the ONE thing `advance`, below, reads to free the architect back to
    idle) only once the verdict's own effect has genuinely landed — a
    `scope_forward` verdict never resolves until its adhoc block is
    genuinely observed `"landed"` (real ancestry), never on a message
    alone."""
    import casestate   # lazy — casestate.py itself lazily imports this
                       # module (see its own module docstring); both are
                       # always fully loaded by the time either is CALLED

    if job.get("resolved"):
        # Idempotent: `advance` clears current_job the tick after resolved is set,
        # so the live engine never re-enters — but never re-apply a verdict (e.g.
        # re-page an operator case) if a caller ticks a resolved job again.
        return

    if not job.get("ordered"):
        _order_triage(eng, job)
        return

    if job.get("verdict") is None:
        verdicts = manifest.get("triage_verdicts") or {}
        v = verdicts.get(job["triage_id"])
        if v is None:
            # No structured verdict yet (R1b — see the constant block above).
            # Arm only once the architect has genuinely taken its turn and settled
            # idle (shared engine-state signal, HELD while it is mid-turn).
            if not _architect_settled_idle(eng, job):
                return
            genuine = job.get("source") not in _LOW_CONFIDENCE_TRIAGE_SOURCES
            job["verdict"] = "operator" if genuine else "answer"
            job["note"] = (
                f"architect settled idle after its ordered turn with no structured "
                f"triage_verdict (source={job.get('source')!r}) -> "
                + ("LOUD 'operator' backstop — a genuine escalation is never "
                   "swallowed (R1b)" if genuine else
                   "benign 'answer' backstop — a low-confidence phantom never "
                   "wedges session-end (R1b)"))
            eng.log("flow", f"architect[triage:{job['triage_id']}]: {job['note']}")
        else:
            verdict = v.get("verdict")
            if verdict not in ("scope_forward", "answer", "operator"):
                eng.log("flow", f"architect[triage:{job['triage_id']}]: "
                                f"unrecognized verdict {verdict!r} — falling back "
                                f"to 'operator' (never silently dropped — the one "
                                f"safe default, still reaches a human)")
                verdict = "operator"
            job["verdict"] = verdict
            job["note"] = v.get("note")

    if job["verdict"] in ("answer", "operator"):
        if job.get("case_id") is not None:
            casestate.architect_resolve(eng, manifest, job["case_id"], job["verdict"],
                                        note=job.get("note"))
        elif job["verdict"] == "operator":
            casestate.open_operator_case(eng, manifest, job.get("block"),
                                         job.get("source"), job.get("detail"),
                                         worker_id=job.get("worker_id"))
        elif job.get("worker_id") and not eng.dry:
            eng._to_worker(
                job["worker_id"],
                job.get("note") or f"[TRON]  architect answer on triage "
                                   f"({job.get('source')}): see guidance.",
                "architect.answer")
        job["resolved"] = True
        eng.log("flow", f"architect[triage:{job['triage_id']}]: verdict "
                        f"{job['verdict']!r} applied — job done")
        return

    # scope_forward — author + land ONE real adhoc block, THEN resolve the
    # original case (if any) — never before the adhoc genuinely lands.
    entry = job.get("adhoc")
    if entry is None:
        seq = manifest.setdefault("adhoc_seq", {})
        n = int(seq.get("triage", 0)) + 1
        seq["triage"] = n
        adhoc_id = f"adhoc-triage-{n}"
        entry = {"block": adhoc_id, "branch": _adhoc_branch(adhoc_id),
                 "finding": job.get("detail"), "case_id": None, "landed": False,
                 "ordered": False}
        job["adhoc"] = entry

    if not entry["ordered"]:
        if not eng.dry:
            eng._to_worker(
                ARCHITECT_WID,
                f"[TRON]  architect — scope_forward on triage "
                f"(triage_id={job['triage_id']!r}): author + land ONE "
                f"upcoming adhoc block ({entry['block']}, meta/blocks/"
                f"{entry['block']}.md, Status: 📋 To do, plus its "
                f"pipeline.md row) — I land it once it resolves, then "
                f"resolve the original wall/escalation.",
                "arch.log-review")
        entry["ordered"] = True
        eng.log("flow", f"architect[triage:{job['triage_id']}]: ordered "
                        f"adhoc {entry['block']!r}")
        return

    truth_ref = eng._truth_ref()
    patch_id = gitobs.patch_id(eng.paths["root"], entry["branch"], truth_ref, eng.dry)
    # Content-bound to the CURRENT patch-id, never a stale cached id (T2-17 fix;
    # single-source in landing.stage_case_id, shared with core/gate.py).
    land_case_id = landing.stage_case_id(entry.get("case_id"), "triage-forward",
                                         entry["branch"], patch_id)
    entry["case_id"] = land_case_id

    outcome = landing.land_via_grant(eng, land_case_id, entry["block"], entry["branch"],
                                     ARCHITECT_WID, "arch.log-review",
                                     "architect-triage-forward")
    if outcome == "landed":
        entry["landed"] = True
        eng.log("flow", f"architect[triage:{job['triage_id']}]: adhoc "
                        f"{entry['block']!r} landed — resolving the original "
                        f"wall/escalation (never paging the operator)")
        if job.get("case_id") is not None:
            casestate.architect_resolve(eng, manifest, job["case_id"],
                                        "scope_forward", note=job.get("note"))
        job["resolved"] = True
    elif outcome == "pending":
        eng.log("flow", f"architect[triage:{job['triage_id']}]: grant live "
                        f"for {land_case_id}, awaiting land.sh")
    else:
        eng.log("flow", f"architect[triage:{job['triage_id']}]: {outcome} "
                        f"(case {land_case_id}, branch not authored yet?)")


def _advance_forward(eng, manifest, job):
    """One forward-job step: order once (side effect, idempotent — mirrors
    `core/gate.py`'s own "order once, then poll" stages), then every
    subsequent call re-checks the branch and attempts the content-bound
    land via the Wave-1 primitive, reused verbatim. `job["landed"]` is set
    ONLY once `land_via_grant` itself reports `"landed"` (real ancestry
    observed) — never on a message alone."""
    block = job["block"]
    branch = job.get("branch") or _forward_branch(block)
    job["branch"] = branch

    if not job.get("ordered"):
        if not eng.dry:
            eng.emit(
                "arch.forward",
                f"[TRON]  architect — block {block!r} is missing its block file. "
                f"Author it on {branch} (meta/blocks/{block}.md, Status: 📋 To do) "
                f"and push — I land it once it resolves.",
                slots={"block": block},
                worker_id=ARCHITECT_WID,
                kind="arch.forward")
        job["ordered"] = True
        eng.log("flow", f"architect[forward:{block}]: ordered authoring on {branch}")
        return

    truth_ref = eng._truth_ref()
    patch_id = gitobs.patch_id(eng.paths["root"], branch, truth_ref, eng.dry)
    # Content-bound to the CURRENT patch-id, never a stale cached id (T2-17 fix;
    # single-source in landing.stage_case_id).
    case_id = landing.stage_case_id(job.get("case_id"), "forward", branch, patch_id)
    job["case_id"] = case_id

    outcome = landing.land_via_grant(eng, case_id, block, branch, ARCHITECT_WID,
                                     "arch.forward", "architect-forward")
    # ADR-0006 R1d: record the grant poll's verdict for `advance`'s backstop.
    # "fail-closed" = the branch's patch-id is unresolvable / no grant minted =
    # the architect authored NOTHING (prose instead of a branch); "pending" =
    # authored & landing (must keep polling, never backstop mid-land).
    job["last_outcome"] = outcome
    if outcome == "landed":
        job["landed"] = True
        eng.log("flow", f"architect[forward:{block}]: block file landed via "
                        f"{branch} -> dispatchable")
    elif outcome == "pending":
        eng.log("flow", f"architect[forward:{block}]: grant live for {case_id}, "
                        f"awaiting land.sh")
    else:
        eng.log("flow", f"architect[forward:{block}]: {outcome} (case {case_id}, "
                        f"branch not authored yet?)")


def _adhoc_branch(adhoc_id):
    return f"arch/{adhoc_id}-logreview"


def enqueue_log_review(eng, manifest, typ, findings):
    """Wave 10 (`core/reviewers.py`): a `<type>` review's DONE-REVIEW gate
    just attested (`reviewers.on_review_done`'s second hand-back) — queue
    the architect's forward-looking `log-review` job: turn the review's
    findings into UPCOMING adhoc block files, or none (a clean review).
    Idempotent bookkeeping only (`manifest["architect"]`/`architect_queue`
    may not exist yet — the very FIRST architect_queue write of the whole
    run, if this project has no missing block files and no reconcile ever
    fired); one `log` job per attested review cycle, never deduped against
    a prior one (each cycle's findings are independent, unlike `forward`/
    `reconcile`'s block-keyed dedupe)."""
    manifest.setdefault("architect", new_state())
    queue = manifest.setdefault("architect_queue", [])
    queue.append({"kind": "log", "type": typ, "findings": list(findings or []),
                  "ordered": False, "adhoc": [], "landed_all": False})
    eng.log("flow", f"architect: log-review queued for the {typ} review "
                    f"({len(findings or [])} finding(s))")


def _advance_log(eng, manifest, job):
    """One `log`-job step: order ONCE (mints the adhoc block ids + branch
    names for every finding, up front, off a manifest-persisted per-type
    sequence — `manifest["adhoc_seq"]`, mirroring `core/casestate.py::
    next_case_id`'s own "deterministic, monotonic, never uuid/random"
    idiom), then every subsequent call re-checks each still-unlanded entry's
    branch and attempts its content-bound land via the Wave-1 primitive,
    reused verbatim — exactly `_advance_forward`'s own "order once, then
    poll+land every entry" shape, generalized over a LIST instead of one
    block. Zero findings (a clean review) needs no order at all — the job
    completes on this SAME call, nothing ever queued or landed. `job[
    "landed_all"]` is set ONLY once EVERY entry's `land_via_grant` has
    itself reported `"landed"` (real ancestry observed) — never on a
    message alone, and never for a job still holding un-authored entries."""
    if not job.get("ordered"):
        findings = job.get("findings") or []
        entries = []
        if findings:
            typ = job.get("type") or "adhoc"
            seq = manifest.setdefault("adhoc_seq", {})
            n = int(seq.get(typ, 0))
            for finding in findings:
                n += 1
                adhoc_id = f"adhoc-{typ}-{n}"
                entries.append({"block": adhoc_id, "branch": _adhoc_branch(adhoc_id),
                                "finding": finding, "case_id": None, "landed": False})
            seq[typ] = n
        job["adhoc"] = entries
        job["ordered"] = True
        if not entries:
            job["landed_all"] = True
            eng.log("flow", f"architect[log:{job.get('type')}]: clean review — "
                            f"no findings, nothing queued")
            return
        if not eng.dry:
            eng._to_worker(
                ARCHITECT_WID,
                f"[TRON]  architect — log-review for the {job.get('type')} "
                f"review: author + land {len(entries)} upcoming adhoc block "
                f"file(s), one per finding ({', '.join(e['block'] for e in entries)}), "
                f"each on its OWN branch (meta/blocks/<id>.md, Status: 📋 To do, "
                f"plus its pipeline.md row) — I land each once it resolves.",
                "arch.log-review")
        eng.log("flow", f"architect[log:{job.get('type')}]: ordered "
                        f"{len(entries)} adhoc block(s): "
                        f"{[e['block'] for e in entries]}")
        return

    entries = job.get("adhoc") or []
    if not entries:
        job["landed_all"] = True
        job["last_outcome"] = "landed"
        return

    truth_ref = eng._truth_ref()
    tick_outcomes = []
    for e in entries:
        if e.get("landed"):
            continue
        block, branch = e["block"], e["branch"]
        patch_id = gitobs.patch_id(eng.paths["root"], branch, truth_ref, eng.dry)
        # Content-bound to the CURRENT patch-id, never a stale cached id (T2-17
        # fix; single-source in landing.stage_case_id).
        case_id = landing.stage_case_id(e.get("case_id"), "logreview", branch, patch_id)
        e["case_id"] = case_id
        outcome = landing.land_via_grant(eng, case_id, block, branch, ARCHITECT_WID,
                                         "arch.log-review", "architect-logreview")
        tick_outcomes.append(outcome)
        if outcome == "landed":
            e["landed"] = True
            eng.log("flow", f"architect[log:{job.get('type')}]: adhoc block "
                            f"{block!r} landed via {branch} -> dispatchable")
        elif outcome == "pending":
            eng.log("flow", f"architect[log:{job.get('type')}]: grant live for "
                            f"{case_id}, awaiting land.sh")
        else:
            eng.log("flow", f"architect[log:{job.get('type')}]: {outcome} (case "
                            f"{case_id}, branch not authored yet?)")

    job["landed_all"] = all(e.get("landed") for e in entries)
    # ADR-0006 R1d: aggregate the tick's poll verdict for `advance`'s backstop.
    # All landed -> done; ANY entry still authoring/landing ("pending") holds the
    # poll (never backstop mid-land); otherwise every un-landed entry is
    # "fail-closed" (nothing authored) -> the architect refused to author its
    # ordered adhoc block(s) — a started-then-refused log-review that must NOT
    # silently drop the reviewer's findings.
    if job["landed_all"]:
        job["last_outcome"] = "landed"
    elif "pending" in tick_outcomes:
        job["last_outcome"] = "pending"
    else:
        job["last_outcome"] = "fail-closed"


def _order_reconcile(eng, job):
    """One reconcile-job order: a structured `arch.reconcile` message, sent
    once. No content-check of this module's own (no LLM in this brick — see
    module docstring) — completion is observed exclusively via a LATER
    `architect.reconciled` report `core/router.py` routes into `manifest
    ["reconciled"]`; this function never mutates that itself."""
    if not eng.dry:
        eng.emit(
            "arch.reconcile",
            f"[TRON]  architect — reconcile {job['block']!r} against "
            f"{job.get('after')!r}'s just-landed drift and report "
            f"architect.reconciled once clear.",
            slots={"block": job["block"], "after": job.get("after")},
            worker_id=ARCHITECT_WID,
            kind="arch.reconcile")
    job["ordered"] = True


def advance(eng, manifest):
    """Called AFTER `core/switchboard.py::fill` each tick (`core/tick.py`) —
    see module docstring for why this positioning (not before fill) is what
    makes the reconcile-gate ordering STRICT. Progresses the current job by
    exactly one step; clears it (architect back to idle) the tick a
    reconcile job's block is observed in `manifest["reconciled"]` or a
    forward job's `land_via_grant` observes `"landed"`. Then, if idle, pops
    + starts the next queued job (one job of NEW throughput per tick —
    `architect-count` in the real design is the knob that would parallelize
    this; a single persistent architect in this brick)."""
    arch = manifest.setdefault("architect", new_state())
    queue = manifest.setdefault("architect_queue", [])
    reconciled = set(manifest.get("reconciled") or [])

    # ADR-0006 R1c: watch the one liveness window no worker net covers — an
    # ordered-but-never-started architect (cold-start/dead) — and page once.
    _architect_liveness_ladder(eng, manifest)

    cur = arch.get("current_job")
    if cur:
        if cur.get("kind") == "reconcile":
            if cur.get("block") in reconciled:
                eng.log("flow", f"architect[reconcile:{cur['block']}]: "
                                f"architect.reconciled observed -> gate "
                                f"cleared, architect idle")
                arch["status"], arch["current_job"] = "idle", None
            elif _architect_settled_idle(eng, cur):
                # R1b-style backstop for reconcile (mirrors _advance_triage): the
                # architect took its ordered reconcile turn and settled idle with
                # NO `architect.reconciled` routed — a real-LLM NO-OP reconcile
                # ("no forward impact") whose free-text classify couldn't tag as a
                # structured reconciled report. Tie completion to ENGINE STATE
                # (turn taken + settled idle), never to parsed prose: mark the
                # block reconciled so 01-xx's dispatch is freed. A no-op is benign,
                # and any REAL drift the architect missed surfaces as an ordinary
                # build wall on that block (architect-first) — never a silent WEDGE
                # of the whole fleet (the T2-12 reconcile-gate hang).
                manifest.setdefault("reconciled", []).append(cur["block"])
                eng.log("flow", f"architect[reconcile:{cur['block']}]: settled idle "
                                f"after its ordered turn with no architect.reconciled "
                                f"-> no-op reconcile backstop, gate cleared (R1b-style)")
                arch["status"], arch["current_job"] = "idle", None
        elif cur.get("kind") == "forward":
            _advance_forward(eng, manifest, cur)
            if cur.get("landed"):
                arch["status"], arch["current_job"] = "idle", None
            elif cur.get("last_outcome") == "fail-closed" and _architect_settled_idle(eng, cur):
                _backstop_refused_authoring(eng, manifest, cur)
                arch["status"], arch["current_job"] = "idle", None
        elif cur.get("kind") == "log":
            _advance_log(eng, manifest, cur)
            if cur.get("landed_all"):
                arch["status"], arch["current_job"] = "idle", None
            elif cur.get("last_outcome") == "fail-closed" and _architect_settled_idle(eng, cur):
                _backstop_refused_authoring(eng, manifest, cur)
                arch["status"], arch["current_job"] = "idle", None
        elif cur.get("kind") == "triage":
            _advance_triage(eng, manifest, cur)
            if cur.get("resolved"):
                arch["status"], arch["current_job"] = "idle", None
        else:
            eng.log("flow", f"architect: current_job has an unknown kind "
                            f"{cur.get('kind')!r} — held, never advanced")

    if arch["status"] == "idle" and queue:
        if not arch.get("spawned"):
            eng._spawn_architect()
            arch["spawned"] = True
        job = queue.pop(0)
        arch["status"], arch["current_job"] = "busy", job
        if job["kind"] == "reconcile":
            _order_reconcile(eng, job)
        elif job["kind"] == "forward":
            _advance_forward(eng, manifest, job)
        elif job["kind"] == "log":
            _advance_log(eng, manifest, job)
        elif job["kind"] == "triage":
            _advance_triage(eng, manifest, job)
        eng.log("flow", f"architect: dispatch {job}")

    return {"status": arch["status"], "current_job": arch.get("current_job")}
