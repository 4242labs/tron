"""core.reviewers — wave 10: cadence PULL reviewers + the DONE-REVIEW gate
(contracts/blueprint-contracts.md §1 "Cadence is PULL" / "Review is a
milestone, not a verdict"; rebuild-spec.md B9/C5/T4-reviewer + T5's
`worker.review_done` -> `review:<type>:done`). Reviewers share the worker
slot pool (`core/switchboard.py::fill`, extended here) — never a second
pool, never a second slot-accounting mechanism: a reviewer is just a
`manifest["workers"]` entry whose `block` is the pseudo-block id
`review:<type>`, so `core/pipeline.py::in_flight_blocks`'s EXISTING "a
worker record naming a block with no matching gate is in-flight" arm
already counts it toward `core/switchboard.py`'s free-slot math AND
`core/session.py::check`'s "nothing in-flight" read — NO edit to either of
those two modules' own git-observation logic was needed for that half of
the design (`core/session.py` gets exactly one small, separate addition —
see its own docstring — for the ARCHITECT'S log-review queue, a distinct
gap `core/architect.py`'s wave 9 left open before this brick).

Shape learned by READING `engine/fsm.py`'s cadence counter (`_on_block_done`
/ `_due_cadence` / `_dispatch_reviewer`) and its DONE-REVIEW gate
(`_h_release_reviewer` / `_drive_review_attest`) for shape ONLY —
re-expressed clean here for this stack's plain-manifest idiom, never
copied, and deliberately WITHOUT `fsm.py`'s own paperwork-landing-for-the-
review-log machinery (`_drive_review_landing`) or role/PR plumbing, which
stay out of scope for this brick (no LLM here; a reviewer's report already
carries its structured findings, `slots.findings`, rather than a landed log
file the architect must separately fetch).

## Cadence (PULL, never a timer)

`manifest["cadence"]` (`<type> -> int`) is a per-type counter, incremented
ONCE per block that reaches `record_landed` (✅ genuinely observed on trunk)
THIS RUN — `bump_cadence` below, called from `core/tick.py` the SAME tick
`core/architect.py::enqueue` reads that tick's landed blocks, off the exact
same list. Deduped via `manifest["cadence_seen_done"]` (a durable list of
block ids already counted) so a re-observed `record_landed` outcome for a
block already counted — a re-tick, a crash-replay, a defensive re-scan —
never double-counts (mirrors `engine/fsm.py::mark_counted`'s own dedupe,
re-expressed for THIS module's event-driven hook rather than that module's
"re-scan the whole pipeline every wake" one). Reset to 0 at the MOMENT a
type is dispatched (`dispatch`, below) — never on report, never on release.

The threshold is read from the project's `knobs.yaml` `cadence: {<type>:
<n>}` map, via `eng.ctx.load_knobs()` (`engine/ctx.py`'s existing loader —
no new file IO of this module's own). A project with no `knobs.yaml` at all
(every rig BEFORE this wave — landing/gate/gate_full/tick/dispatch/
multiblock/sentry/casestate never seed one) reads as "no cadence types
configured" — `due_type` always returns `None` — so none of those 8 rigs'
own flows are touched by this brick at all, never a crash on a missing
file.

`due_type(eng, manifest)` — the SWITCHBOARD-side PULL check (`core/
switchboard.py::fill`, extended): the first type whose counter has reached
its threshold AND has no reviewer of that type currently in-flight (a
`manifest["workers"]` entry naming `review:<type>`, any status — dispatched
but not yet released). `None` when nothing is due. Never auto-fired on a
timer — only ever consulted from inside `fill`, itself only ever called
from `core/tick.py`'s bounded per-tick pass.

`dispatch(eng, manifest, typ)` — mints a DETERMINISTIC-but-unique agent id
(`reviewer-<type>-<n>`, `n` a manifest-persisted per-type sequence — unique
across MULTIPLE dispatch cycles of the same type over one run, unlike
`core/switchboard.py::_agent_id`'s block-keyed id, which never needs a
second identity for the SAME block), records the worker (mirrors
`core/switchboard.py::fill`'s own "record BEFORE any process" discipline),
resets the type's counter, and sends the identity-only SPAWN order via
`eng._to_worker` — structured, deterministic, exactly like `core/
switchboard.py::fill`'s own PMT-SPAWN composition, never an LLM call. No
two-step spawn->online->assign handshake here (unlike an engineer): a
reviewer's assignment needs no worker-reported branch to bind a gate to —
it goes straight to reviewing.

## The DONE-REVIEW gate (`gate.review`)

Review is a MILESTONE, not a verdict (blueprint's own words): the reviewer
delivers a log-shaped `worker.review_done` report (`slots.findings`, a
plain list — no LLM judgment of this module's own on what's IN it) and the
gate challenges FULL COVERAGE before releasing, exactly like `core/gate.py`
's `gate.close` challenges a REAL clean replica before releasing a slot,
never on say-so alone: the FIRST hand-back HOLDS (`on_review_done` flips
the worker's own record to `status: "held"` — no separate `manifest["gates"]`
entry; see below for why) and re-orders the SAME `gate.review` attest
request; the SECOND hand-back (the attestation) RELEASES the reviewer
(`eng._release_worker` + the manifest record popped — see below) and
queues an architect `log-review` job (`core/architect.py::
enqueue_log_review`) with whichever hand-back's findings are non-empty.

State lives on the WORKER RECORD itself (`manifest["workers"][agent_id]`),
never a second `manifest["review_gates"]`-shaped dict: a reviewer's
identity (`agent_id`) is already unique per dispatch cycle (see `dispatch`
above), so there is nothing a by-type key would buy that `status`/
`holding_since`/`nudged_at` fields directly on that SAME record don't
already give for free — and, critically, it keeps this module OUT of
`core/gate.py`'s own stage vocabulary entirely: `core/tick.py`'s `plan`
step iterates `snap.gates` (== `manifest["gates"]`) and feeds every entry
to `gate.advance`, which raises on an unrecognized stage — a review's
`"held"` state living anywhere in `manifest["gates"]` would crash the very
next tick. Keeping it on the worker record means `core/gate.py` never even
sees a review cycle exists.

Releasing a reviewer is therefore POPPING its `manifest["workers"]` entry
(the ONLY thing that frees its slot: unlike an ordinary block, a review
pseudo-block has no `manifest["gates"]` entry for `core/pipeline.py::
in_flight_blocks`'s "gate stage is terminal" shortcut to key off — unlike
`core/gate.py::_advance_close`, which relies on THAT shortcut and calls
`eng._release_worker` as pure external bookkeeping alongside it) — done in
exactly two places: here, on attestation (`_release`), and in `core/
sentry.py`'s new review-pacing arm, on a cap escalation (paced exactly like
any other gate stage — see that module's own docstring). Both also call
`eng._release_worker` for parity with `core/gate.py`'s own convention
(external bookkeeping the manifest write doesn't itself require, but every
OTHER release site in this stack performs).

Routed from `core/router.py` (`worker.review_done` -> `on_review_done`,
alongside its existing `worker.online`/`worker.wall`/`operator.decision`/
`architect.reconciled` dispatch) — never handled inline in `core/tick.py`,
same discipline every other structured tag already gets.

No git/subprocess of any kind in this module: `eng.ctx.load_knobs()` is
plain YAML file IO (`engine/ctx.py`'s existing loader, guarded here by an
`os.path.exists` check so a project with no knobs file at all reads as
"nothing configured" rather than a raised `FileNotFoundError` — see
`due_type`'s own note); everything else is a plain manifest mutation, the
same "gates is a direct alias onto the manifest" idiom every other
`core/*.py` module already uses.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import architect   # noqa: E402 — core/architect.py, the log-review queue this gate feeds on attest


def review_block(typ):
    """The pseudo-block id a `<type>` reviewer's `manifest["workers"]` entry
    carries — `review:<type>`, never colliding with a real pipeline block id
    (those are living-doc `ID` cells, never containing a literal `:`)."""
    return f"review:{typ}"


def _cadence_cfg(eng):
    """`knobs.yaml`'s `cadence: {<type>: <n>}` map, via `eng.ctx.load_knobs()`
    — or `{}` when the project ships no `knobs.yaml` at all (every rig
    BEFORE this wave; `engine/ctx.py::load_knobs` itself raises
    `FileNotFoundError` on a missing file, so this checks existence FIRST —
    "no knobs file" is a legitimate "nothing configured" read, never an
    error this module swallows)."""
    ctx = getattr(eng, "ctx", None)
    path = getattr(ctx, "knobs_file", None) if ctx else None
    if not path or not os.path.exists(path):
        return {}
    knobs = ctx.load_knobs() or {}
    cfg = knobs.get("cadence")
    return cfg if isinstance(cfg, dict) else {}


def bump_cadence(eng, manifest, landed_blocks):
    """Increment EVERY configured type's counter once for each block in
    `landed_blocks` (`core/tick.py`'s own `record_landed`-this-tick list,
    the SAME list `core/architect.py::enqueue` reads) not already in
    `manifest["cadence_seen_done"]` — dedupe first, so a block whose
    `record_landed` outcome is somehow re-observed (defensive; the gate
    ladder itself only ever reports it once, the tick it advances stage
    `record` -> `close`) never double-counts. A project with no cadence
    types configured is a no-op call, cheaply (no manifest write at all)."""
    if not landed_blocks:
        return
    types = list(_cadence_cfg(eng).keys())
    if not types:
        return
    seen = manifest.setdefault("cadence_seen_done", [])
    seen_set = set(seen)
    cadence = manifest.setdefault("cadence", {})
    for block in landed_blocks:
        if block in seen_set:
            continue
        seen_set.add(block)
        seen.append(block)
        for typ in types:
            cadence[typ] = cadence.get(typ, 0) + 1
        eng.log("flow", f"reviewers: {block!r} landed ✅ -> counted toward "
                        f"cadence {types} (seen_done dedupe)")


def _reviewer_inflight(manifest, typ):
    workers = manifest.get("workers") or {}
    target = review_block(typ)
    return any(w.get("block") == target for w in workers.values())


def due_type(eng, manifest):
    """The first `<type>` whose counter has reached its configured
    threshold AND has no reviewer of that type currently in-flight — `None`
    when nothing is due. Consulted ONLY from `core/switchboard.py::fill`
    (never on a timer)."""
    cadence = manifest.get("cadence") or {}
    for typ, thresh in _cadence_cfg(eng).items():
        try:
            thresh = int(thresh)
        except (TypeError, ValueError):
            continue
        if thresh <= 0:
            continue
        if cadence.get(typ, 0) >= thresh and not _reviewer_inflight(manifest, typ):
            return typ
    return None


def dispatch(eng, manifest, typ):
    """SPAWN a `<type>` reviewer — identity-only, structured, deterministic
    (never an LLM call): mint a fresh agent id (unique across repeat dispatch
    cycles of the SAME type, `manifest["reviewer_dispatch_seq"]`), record it
    BEFORE the (stubbed) process spawn (the same crash-window discipline
    `core/switchboard.py::fill` already keeps), reset the type's cadence
    counter (consumed ON DISPATCH — blueprint's own words), and order the
    reviewer to work. Returns the freshly minted agent id."""
    seq = manifest.setdefault("reviewer_dispatch_seq", {})
    n = int(seq.get(typ, 0)) + 1
    seq[typ] = n
    agent_id = f"reviewer-{typ}-{n}"

    workers = manifest.setdefault("workers", {})
    # `wid` mirrors `core/gate.py`'s own `gate_state["wid"]` field — trivially
    # self-referential here (a reviewer's own agent id), but it lets
    # `core/sentry.py::_nudge` (shared, block-gate-and-review alike) address
    # the re-order to the right worker without a reviewer-specific branch.
    workers[agent_id] = {"block": review_block(typ), "type": typ, "status": "reviewing",
                         "wid": agent_id}

    manifest.setdefault("cadence", {})[typ] = 0   # consumed on dispatch

    eng._spawn_worker(agent_id, review_block(typ))   # STUBBED — no real process
    eng._to_worker(
        agent_id,
        f"[TRON]  {agent_id} — you're spawned for a {typ} review (cadence due). "
        f"Cover every applicable change since this type's last review and "
        f"report a structured worker.review_done with your findings.",
        "PMT-SPAWN")
    eng.log("flow", f"reviewers: cadence:{typ} due -> dispatched {agent_id} "
                    f"(counter reset)")
    return agent_id


def _release(eng, manifest, agent_id, reason):
    """The ONE way a reviewer's slot frees: pop its `manifest["workers"]`
    entry (see module docstring — there is no `manifest["gates"]` entry for
    `core/pipeline.py::in_flight_blocks`'s terminal-stage shortcut to key
    off instead) PLUS `eng._release_worker` for external bookkeeping parity
    with every other release site in this stack."""
    workers = manifest.get("workers") or {}
    workers.pop(agent_id, None)
    if agent_id:
        eng._release_worker(agent_id, reason=reason)


def on_review_done(eng, manifest, rep):
    """Routed from `core/router.py` for a `worker.review_done` report
    (`{"tag": "worker.review_done", "agent_id": <id>, "type": <type>,
    "slots": {"findings": [...]}}`). Malformed (no type/agent_id) or STALE
    (naming a worker not on file, or on file for a DIFFERENT block/type —
    an already-released or never-dispatched reviewer) is LOGGED and dropped
    — same forgiving discipline `core/router.py::_route_online` already
    gives an unrecordable `worker.online` sender, never a crash on an
    internal, engine-scripted signal.

    FIRST hand-back (worker status not yet `"held"`) -> HOLD: flip the
    record to `"held"`, stash whatever findings THIS call carried, re-order
    the SAME coverage-attest request. SECOND hand-back (status already
    `"held"`) -> the attestation: release the slot and queue an architect
    `log-review` job with findings (this call's, if it carried any — else
    whatever the FIRST hand-back stashed, never silently dropped either
    way)."""
    slots = rep.get("slots") or {}
    typ = rep.get("type") or slots.get("type")
    agent_id = rep.get("agent_id")
    workers = manifest.get("workers") or {}
    w = workers.get(agent_id) if agent_id else None
    if not typ or not agent_id or not w or w.get("block") != review_block(typ):
        eng.log("flow", f"reviewers: dropped a malformed/stale worker.review_done "
                        f"report (type={typ!r} agent_id={agent_id!r})")
        return

    if w.get("status") != "held":
        # FIRST hand-back -> the DONE-REVIEW gate holds (attest coverage).
        w["status"] = "held"
        w["findings"] = slots.get("findings") or []
        w.pop("holding_since", None)   # fresh pacing episode (core/sentry.py)
        w.pop("nudged_at", None)
        if not eng.dry:
            eng._to_worker(
                agent_id,
                f"[TRON]  {agent_id} — gate.review: attest FULL coverage since "
                f"the last {typ} review before I release you (a second "
                f"worker.review_done confirms).",
                "gate.review")
        eng.log("flow", f"reviewers: review:{typ}:done (1st, from {agent_id}) -> "
                        f"DONE-REVIEW gate held (attest coverage)")
        return

    # SECOND hand-back -> the attestation. Release + queue the log-review.
    findings = slots.get("findings")
    if findings is None:
        findings = w.get("findings") or []
    _release(eng, manifest, agent_id, reason="review-complete")
    architect.enqueue_log_review(eng, manifest, typ, findings)
    eng.log("flow", f"reviewers: review:{typ} attested by {agent_id} -> released, "
                    f"log-review queued ({len(findings)} finding(s))")
