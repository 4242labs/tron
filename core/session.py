"""core.session — the clean SESSION-END terminal (wave 6; contracts/
blueprint-contracts.md §1's SWITCHBOARD "wait or session:end", rebuild-spec.md
C2/H4's run-end/ANCHOR/teardown). Signal WHICH the terminal fires on is
learned by READING `engine/fsm.py::_all_settled` / `_end_session` (re-
expressed fresh here for the new `core/` stack's manifest shape — never
copied, never its parked-case/architect-queue/cadence machinery, which stay
out of scope for this brick): a run is settled when every IN-SCOPE roadmap
row is done and nothing is in flight. `OPEN_STATUSES` there is exactly
`IN_SCOPE_STATUSES` here (`"to-do"`, `"in-progress"`) — a block whose trunk
status is `deferred`/`debt`/`cut`/`folded`/`split` is deliberately OUT of the
"must reach done" scope (the same rows `fsm.py`'s own `OPEN_STATUSES` gate
excludes) and never blocks a clean end.

`check(manifest, view) -> dict | None` is a PURE read over a manifest +
`core.pipeline.read_view` result already fetched by the caller this tick
(`core/tick.py`, threaded through the SAME view `core/switchboard.py::fill`
used — never a second trunk read of this module's own; no git/subprocess of
any kind lives here):

  - Returns `None` when the run is not yet settled — legitimate, no error:
    any in-scope block still in-flight (`core.pipeline.in_flight_blocks`) or
    genuinely pending (to-do and dispatchable, or to-do/in-progress waiting
    on an unmet dep that is ITSELF still in-scope and not yet done) is an
    ordinary "not done yet", not a gap.
  - Wave 8 (`core/casestate.py`): a block the operator explicitly ABANDONED
    (`manifest["abandoned_blocks"]`, written by `casestate.settle`'s
    `abandon` verb) is skipped OUTRIGHT — same treatment as a `deferred`/
    `cut`/`folded`/`split` row below, never re-derived from its doc status.
    "Abandon means drop — visibly": the block's own trunk status is left
    exactly as `worker.wall` found it (never `done`, TRON never writes
    project git for this), so without this exclusion it would fall straight
    into the `stuck` gap below the instant its gate frees the slot — a
    dropped block must never block, and must never falsely RAISE on, a
    clean end.
  - Returns `{"ended_at": <iso8601 utc>, "reason": <str>}` — a fresh clean-
    terminal marker — only when EVERY in-scope block is `done` on trunk AND
    nothing is in-flight. The CALLER (`core/tick.py`) is the one that writes
    this into `manifest["session"]` and persists it (this module never
    mutates a manifest itself, exactly like `core/pipeline.py::dispatchable`
    never does) — `manifest["session"]["ended_at"]` is the SAME field name/
    shape `engine/fsm.py::_end_session` already uses (`sess["ended_at"] =
    util.now_iso()`), re-expressed for this stack, not forked.
  - Raises `RuntimeError` — FAIL-LOUD, never a silent "end" — when a block is
    stuck neither done, in-flight, nor dispatchable, and not legitimately
    waiting on a still-pending in-scope dependency: e.g. an `in-progress`
    block with no matching manifest state at all (orphaned), a `to-do` block
    `core.pipeline.dispatchable` would already have picked up (a real
    contradiction), or a `to-do` block permanently blocked by a dependency
    that will NEVER reach `done` (a `deferred`/`cut`/`folded`/`split` dep, or
    a `Depends on` id absent from the pipeline entirely — a typo). This
    mirrors `core/gitobs.py::read_pipeline_view`'s own "fail-loud, never a
    guess" discipline (raises uncaught, propagated by `core/tick.py`) rather
    than silently declaring the run over on a state nothing can explain.

`already_ended(manifest) -> bool` is the idempotent-terminal predicate
`core/tick.py` checks BEFORE doing any observe/route/act/fill work at all —
a genuine no-op re-tick (no git read, no manifest mutation) once
`manifest["session"]["ended_at"]` is on file.
"""
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import pipeline   # noqa: E402 — core/pipeline.py, the in-flight + dispatch-eligible reads

IN_SCOPE_STATUSES = ("to-do", "in-progress")   # mirrors engine/fsm.py's OPEN_STATUSES verbatim


def already_ended(manifest):
    """True iff a clean session-end is already on file — `core/tick.py`'s
    idempotent short-circuit: a re-tick after this reads as a true no-op,
    never a fresh observe/route/act/fill pass."""
    return bool((manifest.get("session") or {}).get("ended_at"))


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _architect_busy(manifest):
    """Wave 10 (`core/architect.py`'s `log-review` job, `core/reviewers.py`'s
    DONE-REVIEW gate attestation that queues it): between a reviewer's
    release and its log-review's adhoc block(s) actually landing on trunk,
    NOTHING else may be in-flight per `pipeline.in_flight_blocks` — the
    adhoc block has no pipeline row yet, so it is structurally invisible to
    `view` until it lands (the SAME "no block file -> invisible to scope"
    gap `core/architect.py`'s own `forward` job already has for a missing
    block file; that job's rigs sidestep it by keeping another real block
    genuinely pending the whole time). A `log`-shaped job is FORWARD-
    LOOKING work in progress, exactly like a queued `reconcile`/`forward`
    job — this run is not settled while the architect still holds one,
    queued or current, whether or not anything else happens to be
    in-flight too."""
    arch = manifest.get("architect") or {}
    return bool(manifest.get("architect_queue")) or arch.get("status") == "busy"


def _open_escalations(manifest):
    """R3 (ADR-0005) — the run is NOT settled while any operator escalation is
    still open. A case with `decision is None` in `manifest["cases"]` is an
    unresolved escalation (a worker.wall/sentry.cap/liveness case the architect
    has not yet resolved, or an operator-owned case awaiting the operator's own
    settle). This is the terminal's ONLY escalation gate: a BLOCK-BEARING case
    already keeps its block in `pending_ids`, but a BLOCK-LESS operator case
    (`open_operator_case(block=None)`, minted when the architect verdicts
    `operator` on a case-less triage — R1b's LOUD backstop, or classify's
    unclassified->operator path) has no pipeline row and is otherwise INVISIBLE
    to `check` — so the run could end with a live page dangling (the M2/M3
    false-green). Returns the list of open case-ids (forensic).

    Deliberately NOT gated on `manifest["operator_pages"]`: that is the DURABLE,
    append-only LOG of every page ever sent (see `core/casestate.py::reping`) —
    an ANSWERED escalation still has its historical page record there, so gating
    on it would wedge session-end forever after any page. The case's own
    `decision` is the single source of truth for "answered". A settled case is
    popped / its `decision` set by `architect_resolve`/`settle`, so a genuinely
    clean end has no open case and this never deadlocks a finished run."""
    cases = manifest.get("cases") or {}
    return [cid for cid, c in cases.items() if c.get("decision") is None]


def check(manifest, view):
    """One pure pass over `view` (a `core.pipeline.read_view(eng)` result,
    caller-fetched) + `manifest` (for in-flight state) — see module
    docstring for the full contract. Never touches git/state IO itself."""
    inflight = pipeline.in_flight_blocks(manifest)
    abandoned = set(manifest.get("abandoned_blocks") or [])
    # Dep resolution must see a block whose file was ARCHIVED at close (done by
    # definition, `has_block_file` False, `archived` True) — else a dependent
    # reads its dep as None, never resolves it `done`, and is wrongly flagged a
    # stuck gap the instant its dependency closes (the T2-01-05 root). Mirrors
    # `core/pipeline.dispatchable`'s own unfiltered status index.
    status_idx = {row["id"]: row.get("status")
                 for row in view if row.get("has_block_file") or row.get("archived")}

    pending_ids = []
    stuck = []
    for row in view:
        if not row.get("has_block_file"):
            continue
        bid = row["id"]
        if bid in abandoned:
            # Wave 8: operator-abandoned — permanently OUT of the
            # "must reach done" scope, never a gap, never blocks the end.
            continue
        status = row.get("status")
        if status == "done":
            continue
        if status not in IN_SCOPE_STATUSES:
            # deferred / debt / cut / folded / split / unknown — deliberately
            # OUT of the "must reach done" scope (engine/fsm.py's own
            # OPEN_STATUSES exclusion, re-expressed) — never blocks a clean
            # end, never flagged as a gap on its own.
            continue

        pending_ids.append(bid)
        if bid in inflight:
            continue   # ordinary: in-flight work, not settled yet, not a gap

        deps = row.get("depends_on") or []
        unmet = [d for d in deps if status_idx.get(d) != "done"]
        is_dispatchable = (status == pipeline.DISPATCHABLE_STATUS and not unmet)
        if is_dispatchable:
            continue   # ordinary: eligible this tick (a free-slot/worker_count
                       # limit, not a gap — core.pipeline.dispatchable already
                       # excludes anything genuinely in-flight/blocked)

        legit_wait = (status == pipeline.DISPATCHABLE_STATUS and unmet
                     and all(status_idx.get(d) in IN_SCOPE_STATUSES for d in unmet))
        if legit_wait:
            continue   # ordinary: waiting on an in-scope dep that is itself
                       # still pending — will unblock on its own once that
                       # dep reaches done; not yet a gap

        # Neither done, in-flight, dispatchable, nor legitimately waiting on
        # a still-pending in-scope dependency — a real gap. Covers: an
        # `in-progress` block with no manifest state behind it (orphaned);
        # a `to-do` block with no unmet deps that STILL isn't dispatchable
        # (a contradiction — core.pipeline.dispatchable disagrees with
        # itself); a `to-do` block permanently blocked by a dep that will
        # NEVER reach done (deferred/debt/cut/folded/split, or a `Depends
        # on` id absent from the pipeline entirely — a typo).
        stuck.append({"id": bid, "status": status, "depends_on": deps,
                      "dep_statuses": {d: status_idx.get(d) for d in deps}})

    if stuck:
        raise RuntimeError(
            "core.session: inconsistent pipeline state — block(s) stuck "
            "neither done, in-flight, nor dispatchable, and not "
            "legitimately waiting on a still-pending in-scope dependency "
            "(a real gap — never silently 'end' on this, surface it): "
            f"{stuck}")

    open_escalations = _open_escalations(manifest)
    if pending_ids or inflight or _architect_busy(manifest) or open_escalations:
        return None   # not settled yet — legitimate, no error (R3: an open
                      # operator escalation, even block-less, keeps the run alive)

    done_count = sum(1 for row in view
                     if row.get("has_block_file") and row.get("status") == "done")
    return {"ended_at": _now_iso(),
           "reason": f"all {done_count} in-scope block(s) done on trunk; nothing "
                     f"in-flight; no open operator escalations"}
