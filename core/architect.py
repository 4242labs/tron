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
import vocab      # noqa: E402 — core/vocab.py, emit template-id constants (block 01-37, T5/T7)
import landing    # noqa: E402 — core/landing.py, Wave-1's ONE landing primitive
import pipeline   # noqa: E402 — core/pipeline.py, in_flight_blocks (dedupe read)
import casestate  # noqa: E402 — core/casestate.py, parked_blocks (dedupe read)
import liveness   # noqa: E402 — core/liveness.py, the shared working-excluded integrator (R-G)

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
    text = (f"[TRON]  architect — TRIAGE (triage_id={job['triage_id']!r}, "
           f"case_id={job.get('case_id')!r}, source={job.get('source')!r}, "
           f"block={job.get('block')!r}): {job.get('detail')}\nReply with a "
           f"structured architect.triage_verdict (triage_id="
           f"{job['triage_id']!r}, verdict in "
           f"scope_forward|answer|operator[, note]).")
    if not eng.dry:
        eng.emit(
            vocab.TPL_ARCH_TRIAGE, text,
            slots={"detail": job.get("detail"), "sender": job.get("source"),
                  "triage_id": job["triage_id"]},
            worker_id=ARCHITECT_WID,
            kind="arch.triage")
    job["ordered"] = True
    _stamp_dispatch(eng, job, text, "arch.triage")   # ADR-0009 R-B
    eng.log("flow", f"architect[triage:{job['triage_id']}]: ordered triage "
                    f"(source={job.get('source')!r}, dispatch_seq="
                    f"{job.get('dispatch_seq')!r})")


# ADR-0009 — restore the deliver-until-consumed dispatch invariant and
# consolidate R1b/R1c/R1d onto it (§3, §6). R1c (the `arch_started`/
# `cold_ticks`/`stall_paged` ladder above, `_architect_liveness_ladder`) is
# DELETED — its scope (the delivery gap) dissolves into R-A..R-E below; its
# honest core (a genuinely dead/unrestartable architect must still reach a
# human) becomes ONE no-progress budget (R-G, `_advance_delivery`). R1b's
# `arch_started` latch + `idle_ticks` debounce are ALSO deleted
# (`_architect_settled_idle` -> `_turn_settled`, below, re-keyed onto the
# `read_hwm(ARCH) >= dispatch_seq` read, R-D) — see this module's own
# module-docstring cross-reference and `adr-0009-architect-turn-completion-
# invariant.md` §3/§6 for the full design.
#
# `_LOW_CONFIDENCE_TRIAGE_SOURCES` (the R1b idle-GUESS's own genuine/
# low-confidence source split) is DELETED here (block 01-37, T10,
# ADR-0012 §6(b)) along with the guess itself (`_advance_triage`, below) —
# structured-only reporting means a settled architect turn always carries a
# real verdict; the classify-layer `unclassified` source this constant
# named no longer exists either (T8 retired the free-text grader that
# produced it).

# R-C/R-E/R-G tunables (ordering constraint, R-G): RESPAWN_CAP * (respawn-
# settle + turn-latency) < NO_PROGRESS_BUDGET < the run's own wall-clock
# budget — recovery always gets its full budget before the honest page, and
# the honest page always beats a silent budget-REJECT. Units are "pace
# units" — the SAME opaque, pluggable clock `core/sentry.py`/`core/
# liveness.py` already use (`eng._now()` live, a persisted tick counter in
# a rig) — never a hardcoded wall-clock assumption baked in here.
RESPAWN_CAP = 3            # at most this many clean re-spawns per stuck order (R-C)
REDELIVER_AFTER = 3        # pace units the runner must sit IDLE before a re-send (R-E)
NO_PROGRESS_BUDGET = 30    # working-excluded pace units unconsumed before ONE page (R-G)


def _delivered(eng, job):
    """ADR-0009 R-D: `delivered(W) ≡ read_hwm(W) >= dispatch_seq`, read
    per-wid (here always `ARCHITECT_WID` — the active resend/respawn loop
    is architect-only; workers stay on `core/sentry.py`'s own re-send
    ladder). `eng._read_hwm` is an OPTIONAL duck-typed hook (mirrors
    `eng._worker_working`/`eng._now`) — real `core.engine.Engine` wires it
    to `engine/jobs.py::read_hwm`. ABSENT (every `core/*_rig.py` fixture
    that predates ADR-0009 and never backs a real runner mailbox for the
    architect) degrades to the job's own `ordered` flag — 'sent ==
    delivered', the documented PRE-ADR-0009 behavior — so no prior rig
    changes; `job["dispatch_seq"]` itself degrades the SAME way (see
    `_stamp_dispatch`), so the two stay consistent whether or not either is
    a real int."""
    if job.get("dispatch_seq") is None:
        return False
    fn = getattr(eng, "_read_hwm", None)
    if not callable(fn):
        return bool(job.get("ordered"))
    try:
        hwm = fn(ARCHITECT_WID)
    except Exception:   # noqa: BLE001 — a broken hook never wedges the job
        return False
    return hwm >= job["dispatch_seq"]


def _turn_settled(eng, job):
    """Whether it is safe to apply a completion BACKSTOP for `job` (R1b's
    directional triage resolve, R1d's refused-authoring escalation, the
    reconcile no-op backstop): the current order must be DELIVERED (R-D,
    `_delivered` above) AND the architect must not currently be mid-turn
    (`eng._worker_working`, optional — absent reads not-working, same
    fail-toward-arming discipline `core/sentry.py`/`core/liveness.py`
    already use for this hook). Replaces the deleted `_architect_settled_
    idle` (the `arch_started` latch + `idle_ticks` debounce, ADR-0009 §6):
    no separate debounce state — `_worker_working`, re-sampled every call
    (never latched), is what pauses a genuinely live turn; `_delivered`
    alone (hwm-anchored, for a live engine) is what proves a turn actually
    ran to completion. One invariant, read fresh every call, never two
    copies that could drift."""
    if not _delivered(eng, job):
        return False
    fn = getattr(eng, "_worker_working", None)
    if callable(fn):
        try:
            if fn(ARCHITECT_WID):
                return False
        except Exception:   # noqa: BLE001 — a broken hook never wedges the job
            pass
    return True


def _stamp_dispatch(eng, d, text, kind):
    """ADR-0009 R-B: stamp `d["dispatch_seq"]` (a job OR one of its
    sub-dict entries — e.g. a `scope_forward` triage's own adhoc `entry`,
    a SEPARATE order-requiring sub-state with its own namespace, so a
    fresh dict already starts `dispatch_seq=None` the instant a NEW
    order-requiring sub-state begins — R-B's "NULLED on every transition"
    is satisfied by construction, never a second explicit reset) to the
    seq JUST used for this send — read back off `eng._mbox_seq` (OPTIONAL,
    mirrors R-A's persisted `manifest["mbox_seq"][ARCHITECT_WID]`; real
    `core.engine.Engine` wires it). ABSENT (every pre-ADR-0009 rig, none of
    which back a real runner mailbox for the architect) degrades to a
    truthy sentinel (`True`) — the exact pre-ADR-0009 `ordered=True`
    semantic `_delivered`'s own hookless fallback already expects. Also
    remembers the exact order text/kind (`_order_text`/`_order_kind`) so
    R-C/R-E can re-deliver the SAME content at the SAME seq — the runner
    dedups by seq (`engine/worker_runner.py::_pending`), so an
    at-least-once re-send is harmless."""
    fn = getattr(eng, "_mbox_seq", None)
    if callable(fn):
        try:
            d["dispatch_seq"] = fn(ARCHITECT_WID)
        except Exception:   # noqa: BLE001 — never wedge a send on a broken hook
            d["dispatch_seq"] = True
    else:
        d["dispatch_seq"] = True
    d["_order_text"] = text
    d["_order_kind"] = kind


def _clock(eng, manifest):
    """The SAME pluggable-clock idiom `core/sentry.py`/`core/liveness.py`
    already use — `eng._now()` when present, else an internal counter
    persisted at `manifest["architect_clock"]`, incremented once per
    call — a SEPARATE counter from either of those modules' own (all three
    track each other tick-for-tick whenever every one falls back, but none
    ever reads another's counter directly)."""
    now_fn = getattr(eng, "_now", None)
    if callable(now_fn):
        return now_fn()
    counters = manifest.setdefault("architect_clock", {})
    counters["clock"] = counters.get("clock", 0) + 1
    return counters["clock"]


def _redeliver(eng, d, now):
    """Re-send `d`'s already-stamped order at its ALREADY-STAMPED seq
    (never a fresh mint — R-A/R-E: 'same monotonic seq; runner dedups') via
    the OPTIONAL `eng._resend` hook (real `core.engine.Engine` wires it to
    `engine/jobs.py::send` at a caller-supplied seq); absent, a no-op (a
    pre-ADR-0009 rig has no real mailbox to re-append to anyway — its own
    `_delivered` fallback already reads 'delivered' the instant `ordered`
    is set, so this is never reached for one). Re-anchors `last_sent_at` so
    R-E's idle-gated throttle measures from THIS send forward."""
    fn = getattr(eng, "_resend", None)
    seq = d.get("dispatch_seq")
    # `is not True` (never `!=`/`not in (None, True)`): Python's `1 == True`,
    # so an equality-based check would wrongly treat a REAL, legitimate seq
    # of 1 as the hookless `True` sentinel and skip the re-send entirely.
    if callable(fn) and seq is not None and seq is not True:
        try:
            fn(ARCHITECT_WID, d["dispatch_seq"], d.get("_order_text") or "",
              d.get("_order_kind") or "arch.redeliver")
        except Exception:   # noqa: BLE001 — a broken hook never wedges the job
            pass
    d["last_sent_at"] = now


def _advance_delivery(eng, manifest, d):
    """ADR-0009 R-C/R-E/R-G: the architect-ONLY deliver-until-consumed
    recovery loop for `d` (a job or one of its sub-dict entries) whose
    current order has been SENT (`dispatch_seq` set) but not yet DELIVERED
    (`_delivered` False). Workers stay on `core/sentry.py`'s own re-send
    ladder (R-D) — this is never called for anything but the architect's
    own `current_job`/adhoc entries.

    Live-only: `eng._read_hwm` gates the WHOLE function — absent (every
    pre-ADR-0009 rig `eng` stand-in), this is a genuine no-op, because
    `_delivered`'s own hookless fallback already reads 'delivered' the
    instant `ordered` is set (`dispatch_seq` is then `True`, never `None`),
    so the 'not yet consumed' branch this function handles is structurally
    unreachable for those rigs — zero behavior change, exactly the
    discipline every other optional hook in this stack already keeps.

    R-G's no-progress accumulator is a PERSISTED INTEGRATING accumulator
    (`d["unconsumed_work_excluded"]`), sampled once per call via the SAME
    shared helper `core/liveness.py::sweep` uses for its own silence ladder
    (`liveness.working_excluded_integrate` — "FACTOR the working-excluded
    integration step... into a shared helper both call, do not copy it") —
    `reset_on_active=False`: PAUSED while the architect is provably
    working, never reset to 0 merely because it worked (only a genuine
    `_delivered` flip resets it — see the job-kind advance functions below,
    which clear it the instant `_turn_settled`/`_delivered` observes
    completion). Anchored on the ORDER (`d["unconsumed_since"]`), never on
    the raw hwm integer (a respawn's hwm reset 3->0 must never read as
    'progress')."""
    read_hwm = getattr(eng, "_read_hwm", None)
    if not callable(read_hwm):
        return   # no live delivery signal — see docstring; nothing to recover

    now = _clock(eng, manifest)
    if d.get("unconsumed_since") is None:
        d["unconsumed_since"] = now
    if d.get("last_sample") is None:
        d["last_sample"] = now
    if d.get("last_sent_at") is None:
        # Anchor R-E's idle-gated redeliver timer to the FIRST tick this
        # gap was observed (effectively "right after sending" — `advance`
        # calls this the very next pass after `_stamp_dispatch`) — never
        # left unset until a redeliver has already happened once, else
        # `now - d.get("last_sent_at", now)` would trivially read 0 forever
        # and REDELIVER_AFTER could never trip.
        d["last_sent_at"] = now

    working = False
    wfn = getattr(eng, "_worker_working", None)
    if callable(wfn):
        try:
            working = bool(wfn(ARCHITECT_WID))
        except Exception:   # noqa: BLE001 — a broken hook never wedges the job
            working = False

    d["last_sample"], d["unconsumed_work_excluded"] = liveness.working_excluded_integrate(
        now, d["last_sample"], d.get("unconsumed_work_excluded", 0),
        working, reset_on_active=False)

    alive = True
    afn = getattr(eng, "_is_alive", None)
    if callable(afn):
        try:
            alive = bool(afn(ARCHITECT_WID))
        except Exception:   # noqa: BLE001 — fail toward "alive" (never respawn-storm on a flaky hook)
            alive = True

    if not alive:
        respawns = d.get("respawns", 0)
        if respawns < RESPAWN_CAP:
            spawn_fn = getattr(eng, "_spawn_architect", None)
            if callable(spawn_fn):
                spawn_fn()   # R-C: clean-slate (retire_stale_dir, engine.py::_real_spawn)
            d["respawns"] = respawns + 1
            _redeliver(eng, d, now)
            eng.log("flow", f"architect: DEAD — re-spawned (clean-slate, R-C) and "
                            f"re-delivered the outstanding order at dispatch_seq="
                            f"{d.get('dispatch_seq')!r} (respawn #{d['respawns']})")
    else:
        idle = False
        ifn = getattr(eng, "_runner_idle", None)
        if callable(ifn):
            try:
                idle = bool(ifn(ARCHITECT_WID))
            except Exception:   # noqa: BLE001 — fail toward "not idle" (never race a live turn)
                idle = False
        if idle and (now - d.get("last_sent_at", now)) >= REDELIVER_AFTER:
            _redeliver(eng, d, now)
            eng.log("flow", f"architect: re-delivered (R-E, idle-gated) the "
                            f"outstanding order at dispatch_seq="
                            f"{d.get('dispatch_seq')!r}")

    if (d["unconsumed_work_excluded"] >= NO_PROGRESS_BUDGET
            and not d.get("no_progress_paged")):
        detail = (f"architect ordered a job (dispatch_seq={d.get('dispatch_seq')!r}) "
                  f"that has stayed UNCONSUMED for {d['unconsumed_work_excluded']} "
                  f"working-excluded pace unit(s) (>= NO_PROGRESS_BUDGET="
                  f"{NO_PROGRESS_BUDGET}) — R-G no-progress budget, paged ONCE "
                  f"(THE FLOOR re-pings after)")
        casestate.open_operator_case(eng, manifest, d.get("block"),
                                     "architect.no_progress", detail,
                                     worker_id=ARCHITECT_WID, kind="stall")
        d["no_progress_paged"] = True
        eng.log("flow", f"architect: NO-PROGRESS — {detail}")


def _reset_delivery_state(d):
    """R-G: reset the no-progress accumulator + respawn count ONLY on the
    genuine `read_hwm >= dispatch_seq` flip (never on a mere respawn or a
    working-tick) — called by every job-kind's advance function the
    instant it observes `_delivered`/`_turn_settled` true, so a
    MULTI-order job (R-B) starts its NEXT order's budget fresh."""
    d["unconsumed_since"] = None
    d["last_sample"] = None
    d["last_sent_at"] = None
    d["unconsumed_work_excluded"] = 0
    d["respawns"] = 0
    d["no_progress_paged"] = False


def _backstop_refused_authoring(eng, manifest, cur):
    """ADR-0006 R1d (ADR-0009: re-keyed onto `_turn_settled`/R-D): a
    STARTED-then-REFUSED forward/log job — the architect's order was
    genuinely DELIVERED (`_turn_settled`) and it settled idle, yet
    `land_via_grant` still reports `"fail-closed"` (its patch-id is
    unresolvable == it authored NO branch, prose instead of a file).
    Resolve LOUD: page the operator once and free the architect. Never poll
    a never-authored branch to budget (the log/forward wedge A3), and — for
    a log-review — never silently DROP the reviewer's findings by
    benign-clearing. Clearing `current_job` at the call site is the
    once-guard (the job is gone next tick, so `open_operator_case`'s
    non-idempotency can't storm). A cold/dead architect whose order was
    NEVER delivered at all is not here — R-G's no-progress budget
    (`_advance_delivery`) owns that window."""
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
            # No structured verdict yet (R1b, ADR-0009 re-keyed onto R-D).
            # Arm only once the architect's order is genuinely DELIVERED
            # (`_turn_settled`: read_hwm >= dispatch_seq, held while
            # provably mid-turn) — never a wall-clock/idle-tick debounce.
            # While NOT yet delivered, drive the R-C/R-E/R-G recovery loop
            # (respawn/re-deliver/no-progress-budget) instead of just idling.
            if not _turn_settled(eng, job):
                if job.get("dispatch_seq") is not None and not _delivered(eng, job):
                    _advance_delivery(eng, manifest, job)
                return
            _reset_delivery_state(job)   # R-G: genuine delivery flip — reset the budget
            # T10 (ADR-0012 §6(b), the guess-from-silence backstop DELETED):
            # under structured-only + the closed verdict wire (T9), a
            # genuinely completed architect turn always carries a real
            # `report.sh --tag verdict ...` reply — R1b's old idle-GUESS
            # (fabricating "operator"/"answer" from `job.get("source")`
            # alone) is now dead code by the design's own premise, and
            # worse, a content guess. A settled turn with NO structured
            # verdict is instead a genuine delivery gap: bounded RE-ORDER
            # (the SAME `RESPAWN_CAP` idiom R-C already uses for a stuck
            # DELIVERY, reused rather than a second cap), never a guess;
            # past the cap, the operator is paged LOUD (never fabricated
            # content) — "a truly-dead architect surfaces via the liveness
            # budget as a page" (supersedes the HANDOVER "R1b byte-for-byte"
            # note per ADR §6(b)).
            reorders = job.get("_verdict_reorders", 0) + 1
            job["_verdict_reorders"] = reorders
            if reorders > RESPAWN_CAP:
                job["verdict"] = "operator"
                job["note"] = (
                    f"architect's triage order (triage_id={job['triage_id']!r}) was "
                    f"DELIVERED and re-ordered {reorders} time(s) with NO structured "
                    f"architect.triage_verdict ever routed — never guessed; paged "
                    f"LOUD instead (T10)")
                eng.log("flow", f"architect[triage:{job['triage_id']}]: {job['note']}")
            else:
                eng.log("flow", f"architect[triage:{job['triage_id']}]: order "
                                f"DELIVERED with no structured verdict yet (re-order "
                                f"{reorders}/{RESPAWN_CAP}) — re-ordering, never guessing")
                job["ordered"] = False
                _order_triage(eng, job)
                return
        else:
            _reset_delivery_state(job)   # R-G: a routed report proves delivery too
            verdict = v.get("verdict")
            if verdict not in ("scope_forward", "answer", "operator"):
                eng.log("flow", f"architect[triage:{job['triage_id']}]: "
                                f"unrecognized verdict {verdict!r} — falling back "
                                f"to 'operator' (never silently dropped — the one "
                                f"safe default, still reaches a human)")
                verdict = "operator"
            job["verdict"] = verdict
            job["note"] = v.get("note")

    # ADR-0008 — stale-wall revalidation (covers BOTH the R1b idle-backstop
    # operator verdict AND a structured `triage_verdict="operator"`: both set
    # verdict="operator" and converge here). A genuine LANDING worker.wall whose
    # block has already closed out on trunk is moot — revalidate against durable
    # trunk truth (the gate stage, which survives branch teardown) and retire it
    # benignly rather than paging the operator about a wall that no longer holds.
    if job["verdict"] == "operator" and pipeline.stale_landing_wall(
            manifest, job.get("source"), job.get("worker_id"), job.get("detail")):
        job["verdict"] = "answer"
        job["note"] = ("stale landing worker.wall — block closed on trunk; "
                       "operator NOT paged (ADR-0008)")
        eng.log("flow", f"architect[triage:{job['triage_id']}]: STALE landing worker.wall "
                        f"revalidated (worker={job.get('worker_id')!r} block CLOSED on "
                        f"trunk) — downgraded operator->answer, operator NOT paged (ADR-0008)")

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
        text = (f"[TRON]  architect — scope_forward on triage "
               f"(triage_id={job['triage_id']!r}): author + land ONE "
               f"upcoming adhoc block ({entry['block']}, meta/blocks/"
               f"{entry['block']}.md, Status: 📋 To do, plus its "
               f"pipeline.md row) — I land it once it resolves, then "
               f"resolve the original wall/escalation.")
        if not eng.dry:
            eng._to_worker(ARCHITECT_WID, text, "arch.log-review")
        entry["ordered"] = True
        # R-B: `entry` is its OWN order-requiring sub-state, a fresh dict
        # separate from `job`'s own `dispatch_seq` namespace — stamping it
        # here satisfies "NULLED on every transition" by construction (a
        # freshly-created dict already starts `dispatch_seq=None`).
        _stamp_dispatch(eng, entry, text, "arch.log-review")
        eng.log("flow", f"architect[triage:{job['triage_id']}]: ordered "
                        f"adhoc {entry['block']!r} (dispatch_seq="
                        f"{entry.get('dispatch_seq')!r})")
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
        text = (f"[TRON]  architect — block {block!r} is missing its block file. "
               f"Author it on {branch} (meta/blocks/{block}.md, Status: 📋 To do) "
               f"and push — I land it once it resolves.")
        if not eng.dry:
            eng.emit(vocab.TPL_ARCH_FORWARD, text, slots={"block": block},
                    worker_id=ARCHITECT_WID, kind=vocab.TPL_ARCH_FORWARD)
        job["ordered"] = True
        _stamp_dispatch(eng, job, text, "arch.forward")   # ADR-0009 R-B
        eng.log("flow", f"architect[forward:{block}]: ordered authoring on {branch} "
                        f"(dispatch_seq={job.get('dispatch_seq')!r})")
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
        text = (f"[TRON]  architect — log-review for the {job.get('type')} "
               f"review: author + land {len(entries)} upcoming adhoc block "
               f"file(s), one per finding ({', '.join(e['block'] for e in entries)}), "
               f"each on its OWN branch (meta/blocks/<id>.md, Status: 📋 To do, "
               f"plus its pipeline.md row) — I land each once it resolves.")
        if not eng.dry:
            eng._to_worker(ARCHITECT_WID, text, "arch.log-review")
        _stamp_dispatch(eng, job, text, "arch.log-review")   # ADR-0009 R-B
        eng.log("flow", f"architect[log:{job.get('type')}]: ordered "
                        f"{len(entries)} adhoc block(s): "
                        f"{[e['block'] for e in entries]} (dispatch_seq="
                        f"{job.get('dispatch_seq')!r})")
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
    text = (f"[TRON]  architect — reconcile {job['block']!r} against "
           f"{job.get('after')!r}'s just-landed drift and report "
           f"architect.reconciled once clear.")
    if not eng.dry:
        eng.emit(vocab.TPL_ARCH_RECONCILE, text,
                slots={"block": job["block"], "after": job.get("after")},
                worker_id=ARCHITECT_WID, kind=vocab.TPL_ARCH_RECONCILE)
    job["ordered"] = True
    _stamp_dispatch(eng, job, text, "arch.reconcile")   # ADR-0009 R-B


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

    cur = arch.get("current_job")
    if cur:
        # ADR-0009 R-C/R-E/R-G: the architect-only deliver-until-consumed
        # recovery loop — runs BEFORE the kind-specific step below, on
        # WHATEVER order is currently outstanding (any job kind), so a
        # stuck delivery recovers regardless of which completion signal
        # that job kind ultimately waits on. Replaces ADR-0006 R1c
        # (`_architect_liveness_ladder`, DELETED — its scope dissolves into
        # R-A..R-E, its honest core becomes this ONE no-progress budget).
        if cur.get("dispatch_seq") is not None and not _delivered(eng, cur):
            _advance_delivery(eng, manifest, cur)
        if cur.get("kind") == "reconcile":
            if cur.get("block") in reconciled:
                eng.log("flow", f"architect[reconcile:{cur['block']}]: "
                                f"architect.reconciled observed -> gate "
                                f"cleared, architect idle")
                _reset_delivery_state(cur)
                arch["status"], arch["current_job"] = "idle", None
            elif _turn_settled(eng, cur):
                # R1b-style backstop for reconcile (mirrors _advance_triage,
                # ADR-0009 re-keyed onto `_turn_settled`/R-D): the architect's
                # reconcile order was genuinely DELIVERED and it settled idle
                # with NO `architect.reconciled` routed — a real-LLM NO-OP
                # reconcile ("no forward impact") whose free-text classify
                # couldn't tag as a structured reconciled report. Tie
                # completion to ENGINE STATE (genuine delivery + settled),
                # never to parsed prose: mark the block reconciled so 01-xx's
                # dispatch is freed. A no-op is benign, and any REAL drift the
                # architect missed surfaces as an ordinary build wall on that
                # block (architect-first) — never a silent WEDGE of the whole
                # fleet (the T2-12 reconcile-gate hang).
                manifest.setdefault("reconciled", []).append(cur["block"])
                eng.log("flow", f"architect[reconcile:{cur['block']}]: order "
                                f"DELIVERED, settled idle, no architect.reconciled "
                                f"-> no-op reconcile backstop, gate cleared (R1b-style)")
                _reset_delivery_state(cur)
                arch["status"], arch["current_job"] = "idle", None
        elif cur.get("kind") == "forward":
            _advance_forward(eng, manifest, cur)
            if cur.get("landed"):
                _reset_delivery_state(cur)
                arch["status"], arch["current_job"] = "idle", None
            elif cur.get("last_outcome") == "fail-closed" and _turn_settled(eng, cur):
                _backstop_refused_authoring(eng, manifest, cur)
                arch["status"], arch["current_job"] = "idle", None
        elif cur.get("kind") == "log":
            _advance_log(eng, manifest, cur)
            if cur.get("landed_all"):
                _reset_delivery_state(cur)
                arch["status"], arch["current_job"] = "idle", None
            elif cur.get("last_outcome") == "fail-closed" and _turn_settled(eng, cur):
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

    # T7 (block 01-37, R5) — the batched visibility-flag digest: sent the
    # next time the architect is IDLE (whether or not a new job was JUST
    # popped above — sending it here, unconditionally on idle, never makes
    # it wait a whole extra tick behind a fresh job). Purely informational:
    # never a job of its own, never blocks/consumes the architect's queue
    # throughput, never pages.
    if arch["status"] == "idle":
        _send_flag_digest(eng, manifest)

    return {"status": arch["status"], "current_job": arch.get("current_job")}


def _send_flag_digest(eng, manifest):
    """T7 — batch every `worker.flag` recorded since the last digest
    (`core/router.py::_route_flag` appends to `manifest["architect_flags"]`)
    into ONE `arch.flags` order, never one order per flag (R5: "a chatty
    worker cannot starve real triage"). A no-op when nothing is pending.
    Pages no one, opens no case, expects no reply — purely informational;
    the durable, operator-readable record is `manifest["flag_ledger"]`
    (`core/router.py`'s own append, untouched here)."""
    flags = manifest.get("architect_flags") or []
    if not flags:
        return
    manifest["architect_flags"] = []
    lines = "\n".join(
        f"  - block={f.get('block') or '(none)'} worker={f.get('worker_id')!r}: "
        f"{f.get('detail')}" for f in flags)
    text = (f"[TRON]  architect — VISIBILITY DIGEST ({len(flags)} flagged since "
           f"the last digest, surfaced non-paging, R5):\n{lines}")
    if not eng.dry:
        eng.emit(vocab.TPL_ARCH_FLAGS, text, slots={"detail": lines},
                 worker_id=ARCHITECT_WID, kind=vocab.TPL_ARCH_FLAGS)
    eng.log("flow", f"architect: sent visibility digest for {len(flags)} "
                    f"flag(s) — pages no one")
