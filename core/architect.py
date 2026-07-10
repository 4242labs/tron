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


def enqueue(eng, manifest, view, landed_blocks):
    """Called BEFORE `core/switchboard.py::fill` each tick (`core/tick.py`):
    (1) clear-ahead `forward` jobs for every in-scope row missing a block
    file; (2) a `reconcile` job for the next in-scope block after each block
    whose gate outcome THIS tick was `record_landed` (✅ genuinely observed
    on trunk). Idempotent throughout — see module docstring."""
    manifest.setdefault("architect", new_state())
    manifest.setdefault("architect_queue", [])
    _enqueue_forward_jobs(eng, manifest, view)
    for block in landed_blocks:
        _enqueue_reconcile(eng, manifest, view, block)


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
            eng._to_worker(
                ARCHITECT_WID,
                f"[TRON]  architect — block {block!r} is missing its block file. "
                f"Author it on {branch} (meta/blocks/{block}.md, Status: 📋 To do) "
                f"and push — I land it once it resolves.",
                "arch.forward")
        job["ordered"] = True
        eng.log("flow", f"architect[forward:{block}]: ordered authoring on {branch}")
        return

    truth_ref = eng._truth_ref()
    patch_id = gitobs.patch_id(eng.paths["root"], branch, truth_ref, eng.dry)
    case_id = job.get("case_id") or landing.paperwork_case_id("forward", branch, patch_id)
    job["case_id"] = case_id

    outcome = landing.land_via_grant(eng, case_id, block, branch, ARCHITECT_WID,
                                     "arch.forward", "architect-forward")
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


def _order_reconcile(eng, job):
    """One reconcile-job order: a structured `arch.reconcile` message, sent
    once. No content-check of this module's own (no LLM in this brick — see
    module docstring) — completion is observed exclusively via a LATER
    `architect.reconciled` report `core/router.py` routes into `manifest
    ["reconciled"]`; this function never mutates that itself."""
    if not eng.dry:
        eng._to_worker(
            ARCHITECT_WID,
            f"[TRON]  architect — reconcile {job['block']!r} against "
            f"{job.get('after')!r}'s just-landed drift and report "
            f"architect.reconciled once clear.",
            "arch.reconcile")
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

    cur = arch.get("current_job")
    if cur:
        if cur.get("kind") == "reconcile":
            if cur.get("block") in reconciled:
                eng.log("flow", f"architect[reconcile:{cur['block']}]: "
                                f"architect.reconciled observed -> gate "
                                f"cleared, architect idle")
                arch["status"], arch["current_job"] = "idle", None
        elif cur.get("kind") == "forward":
            _advance_forward(eng, manifest, cur)
            if cur.get("landed"):
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
        eng.log("flow", f"architect: dispatch {job}")

    return {"status": arch["status"], "current_job": arch.get("current_job")}
