"""core.sentry — the ONE pacing ladder wrapping the DONE gate (contracts/
blueprint-contracts.md §5: "an idle worker at any stage is re-nudged
(`gate_nudge_after`) then escalated (`gate_idle_cap`) off the runner's own
idle state — a gate can never hang silently"). `core/gate.py`'s own
`advance` is a PURE predicate-driven state machine — it reports an honest
HOLDING outcome each tick (`local_waiting`, `merge_pending`, `trunk_failed`/
`trunk_unconfirmed`, `record_waiting`, `close_holding`, ...) and never caps
itself. The ladder's own internal cap (`CLOSE_ATTEMPT_CAP`, the one place
capping used to live, close-stage only) is GONE — see `core/gate.py`'s
`_advance_close`, which now holds forever on an unclean replica. Capping
lives in exactly ONE place, for EVERY stage: here.

`pace(eng, snapshot)` — called by `core/tick.py`, once per tick, AFTER that
tick's own `gate.advance` pass and STRICTLY BEFORE persist (so any
escalation this call produces is durable the same tick it fires) — walks
every in-flight gate in `snapshot.gates` and tracks how long it has HELD at
its CURRENT stage:

  - A stage a gate just ADVANCED into (or a gate this module has never seen
    before) starts a fresh pacing episode: `holding_stage` / `holding_since`
    / `nudged_at` (persisted directly on the `gate_state` dict — "in the
    manifest", `core/state.py`'s own durable store, no separate side table)
    are (re)anchored to the CURRENT clock reading; no holding time is
    counted on this call — progress clears the clock.
  - A stage whose worker is provably MID-TURN (the OPTIONAL
    `eng._worker_working(wid)` hook — the SAME one `core/liveness.py` uses)
    re-anchors its episode every call: a long `claude -p` build/land turn
    posts nothing observable until it finishes (minutes), so counting that
    wall-clock as "idle holding" would falsely escalate a legitimately-
    working worker. Only genuine IDLE-at-gate time accrues toward nudge/cap
    (the legacy `jobs.runner_idle` idle-cap discipline). Absent the hook
    (every pre-existing rig fixture), this is inert — pacing behaves exactly
    as before.
  - A stage that reads the SAME as last call's HOLDS (and whose worker is NOT
    working): `holding = now - holding_since`.
      * At `holding >= GATE_NUDGE_AFTER` (once per holding episode —
        `nudged_at` guards a second nudge on a later call while still
        holding) the stage's order is RE-SENT via `eng._to_worker` — a
        distinct `sentry.nudge.<stage>` kind, never impersonating the
        stage's own order kind, so a re-nudge is always tellable apart from
        the stage's first order.
      * At `holding >= GATE_IDLE_CAP` (exactly once — the gate turns
        terminal the same call, so there is no "again") the gate is marked
        ESCALATED: `gate_state["stage"] = gate.STAGE_ESCALATED` and
        `gate_state["escalation"] = <detail>` — the SAME two fields
        `core/gate.py::_escalate` itself sets on a gate-driven escalation,
        so a caller can't tell a sentry-driven one apart by shape — plus a
        structured record appended to `manifest["escalations"]` (block,
        stage, holding, the cap it tripped, a human detail, the clock
        reading) — the honest, durable trace, unconditionally, kept exactly
        as before. Wave 8 (`core/casestate.py`) ALSO opens a parked
        operator CASE for this same escalation (`casestate.open_case`,
        source `"sentry.cap"`) — one path for "needs the operator", same as
        a `worker.wall`: the block is already terminal/slot-freed by the
        mutation above, so `open_case` only tags it with the minted
        `case_id` (never re-mutates `stage`/`escalation`); an operator
        `resume`/`amend`/`abandon` on that case clears it exactly like any
        other parked case (`core/casestate.py`'s own `settle`).
  - A gate already terminal (`closed`/`escalated`, whether `core.gate`
    itself or a PRIOR `pace()` call put it there) is skipped outright, and
    its pacing fields are dropped — a stale episode never survives past the
    tick that closed it.

ONE parametrized mechanism for ALL stages: `GATE_NUDGE_AFTER`/
`GATE_IDLE_CAP` below are read the SAME way regardless of which stage a
gate is holding at (`gate.local` idle exactly like `gate.close` idle) —
there is no per-stage cap anywhere in this module, and none left in
`core/gate.py` either (the close stage's `CLOSE_ATTEMPT_CAP` consolidation
this module exists to complete).

The clock is intentionally pluggable, so a rig can be deterministic:
`eng._now()`, when the caller provides one (a plain callable), is read once
per `pace()` call and used as-is — a rig can hand it a fully self-controlled
counter (`core/sentry_rig.py` does exactly this, to pin the nudge/cap
boundaries exactly) or real wall-clock time. Absent that, `pace` falls back
to its OWN tick counter (`manifest["sentry"]["clock"]`, persisted like
everything else in the manifest, incremented exactly once per `pace()`
call) — still a deterministic "tick counter the rig controls", simply by
however many times it calls `core.tick.tick`/`pace` while a gate makes no
progress: `core/tick_rig.py` / `core/dispatch_rig.py` / `core/
multiblock_rig.py` all exercise this fallback path completely unmodified,
never wired to `eng._now()` themselves. Either way the unit is opaque to
this module: only relative deltas (`now - holding_since`) are ever compared
against the two knobs above.

Wave 17 (GAP-A, `core/casestate.py::reping`): the SAME clock reading this
call mints is also handed, once per call, to `casestate.reping` — a
SEPARATE ladder (THE operator-page FLOOR: an unanswered case is re-paged
forever on its own bounded backoff, never closed/dropped) that this module
only *calls*, never implements; see that function's own docstring. Its
activity is deliberately NOT folded into this function's own `nudged`/
`escalated` return (a gate/reviewer-stage-outcome shape only).

Duck-typed `eng` contract: everything `core/gate.py` already needs
(`eng._to_worker`, `eng.dry`, `eng.log`) PLUS the OPTIONAL `eng._now()`
above — no new REQUIRED surface, so every existing `core/*_rig.py` eng
fixture keeps working completely unmodified (they all fall through to the
manifest-clock path).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gate        # noqa: E402 — core/gate.py, the STAGE_CLOSED/STAGE_ESCALATED terminal vocabulary
import casestate    # noqa: E402 — core/casestate.py, wave 8's parked-case FSM

# ── the ONE pacing ladder's two knobs — every stage, no exceptions ──
GATE_NUDGE_AFTER = 3   # ticks holding at one stage, no progress -> re-nudge (once per episode)
GATE_IDLE_CAP = 6      # ticks holding at one stage, no progress -> escalate (exactly once)

_TERMINAL_STAGES = (gate.STAGE_CLOSED, gate.STAGE_ESCALATED)


def _worker_working(eng, wid):
    """OPTIONAL, duck-typed: True iff this gate's worker is provably MID-TURN
    (`eng._worker_working(wid)` — `core/engine.py` wires it to a real
    `worker_runner.py` in `state: "working"`; the SAME hook `core/liveness.py`
    uses). A gate stage a worker legitimately hasn't satisfied YET because it
    is still executing its turn (a `claude -p` build/land turn posts nothing
    observable until it finishes, minutes later) must NOT accrue idle-holding
    toward nudge/cap — only genuine IDLE-at-gate time counts (the legacy
    `jobs.runner_idle` idle-cap discipline, 01-11 FX-2, re-expressed for this
    stack's pluggable-hook idiom). Absent the hook (every pre-existing
    `core/*_rig.py` fixture) or on a hook that errors, reads False — the
    pacing ladder then behaves exactly as before, so no prior rig changes."""
    if not wid:
        return False
    fn = getattr(eng, "_worker_working", None)
    if not callable(fn):
        return False
    try:
        return bool(fn(wid))
    except Exception:   # noqa: BLE001 — a broken hook must never crash the ladder
        return False


def _clock(eng, manifest):
    """The ONE clock this ladder reads — see module docstring. `eng._now()`
    when present (a plain callable, no required signature beyond
    zero-arg), else an internal counter persisted at
    `manifest["sentry"]["clock"]`, incremented exactly once per call."""
    now_fn = getattr(eng, "_now", None)
    if callable(now_fn):
        return now_fn()
    counters = manifest.setdefault("sentry", {})
    counters["clock"] = counters.get("clock", 0) + 1
    return counters["clock"]


def _drop_pacing(gate_state):
    gate_state.pop("holding_stage", None)
    gate_state.pop("holding_since", None)
    gate_state.pop("nudged_at", None)


def _nudge(eng, block, gate_state, stage, holding):
    wid = gate_state.get("wid")
    if wid and not eng.dry:
        eng._to_worker(
            wid,
            f"[TRON]  {wid} — still waiting at gate.{stage} ({holding} pace "
            f"unit(s) with no observed progress) — re-sending the order. A "
            f"gate idle past gate_idle_cap escalates; this is the one "
            f"re-nudge first.",
            f"sentry.nudge.{stage}")
    eng.log("flow", f"sentry: nudged {block} at gate.{stage} (holding={holding}, "
                    f"gate_nudge_after={GATE_NUDGE_AFTER})")


def _escalate(eng, manifest, block, gate_state, stage, holding, now):
    detail = (f"gate[{block}] idle at gate.{stage} for {holding} pace unit(s) "
             f"(>= gate_idle_cap={GATE_IDLE_CAP}) — sentry escalated (the gate "
             f"itself never self-caps; capping lives only in core.sentry)")
    gate_state["stage"] = gate.STAGE_ESCALATED
    gate_state["escalation"] = detail
    record = {"block": block, "stage": stage, "holding": holding,
             "gate_idle_cap": GATE_IDLE_CAP, "detail": detail, "at": now}
    manifest.setdefault("escalations", []).append(record)
    eng.log("flow", f"sentry: ESCALATED {block} — {detail}")
    # Wave 8: one path for "needs the operator" — a cap escalation ALSO
    # opens a parked case (never REPLACES the honest `manifest["escalations"]`
    # record above, which stays exactly as it always has). `open_case` sees
    # the gate is already terminal (set two lines up) and only tags it with
    # the minted case_id — never re-writes `stage`/`escalation`. Wave 18
    # (GAP-E): `open_case` itself now routes ARCHITECT-FIRST (a PMT-TRIAGE
    # job) — NEVER an immediate operator page from here; only the
    # architect's own `operator` verdict ever reaches `eng._page_operator`
    # for this case (see `core/casestate.py::architect_resolve`).
    casestate.open_case(eng, manifest, block, "sentry.cap", detail,
                        worker_id=gate_state.get("wid"), kind="cap")
    return detail


def _pace_reviewers(eng, manifest, now):
    """Wave 10 (`core/reviewers.py`): the DONE-REVIEW gate's `held` stage
    (a reviewer that reported ONE `worker.review_done` but never attested
    the second) is paced by the SAME ladder, off the SAME clock, as any
    block-gate stage — "a reviewer holds (paced by sentry like any stage;
    no silent hang)", wave 10's own words. A reviewer's state lives on its
    OWN `manifest["workers"][agent_id]` record (never a `manifest["gates"]`
    entry — see `core/reviewers.py`'s own docstring for why), so this walks
    `manifest["workers"]` directly instead of `snapshot.gates`; a `"held"`
    status is the ONE thing paced here — `"reviewing"` (still working, no
    coverage claim made yet) is never idle-capped by this ladder, exactly
    like an engineer still at `gate.local` before its own first report.

    On cap: `manifest["escalations"]` gets the SAME structured record shape
    a block-gate cap already produces (`block` reads the pseudo-block id
    `review:<type>`, so a reader can't tell the two apart by SHAPE, only by
    that field's own value); `core.casestate.open_case` opens the SAME
    parked-operator case a block-gate cap already does (and — since a
    review pseudo-block carries no `manifest["gates"]` entry for it to
    tag — internally no-ops on that half, harmlessly); the worker record is
    popped directly here (the ONLY thing that frees a reviewer's slot, per
    `core/reviewers.py`'s own docstring) rather than relying on a gate
    stage's own terminal-vocabulary shortcut, which does not exist for a
    review pseudo-block."""
    nudged, escalated = [], []
    workers = manifest.get("workers") or {}
    for agent_id, w in list(workers.items()):
        if w.get("status") != "held":
            continue
        typ = w.get("type") or "?"
        block = f"review:{typ}"

        if w.get("holding_since") is None:
            w["holding_since"] = now
            w.pop("nudged_at", None)
            continue

        if _worker_working(eng, agent_id):
            # ADR-0006 R1e: a reviewer's attest turn is a real `claude -p` turn
            # that posts nothing until it finishes — mirror the block-gate arm
            # (above): while provably mid-turn, re-anchor the episode so only
            # genuine idle-at-attest time accrues toward the cap, never a
            # long-but-live attest turn (which would else spuriously cap ->
            # operator page -> a trivial SIM REJECT). Sound because R1a bounds
            # `_worker_working` by the runner's own deadline (a hung reviewer
            # reads not-working past its deadline and still caps).
            w["holding_since"] = now
            w.pop("nudged_at", None)
            continue

        holding = now - w["holding_since"]

        if holding >= GATE_IDLE_CAP:
            detail = (f"gate.review[{block}] ({agent_id}) idle at attest for "
                     f"{holding} pace unit(s) (>= gate_idle_cap={GATE_IDLE_CAP}) "
                     f"— sentry escalated (a reviewer never self-caps; capping "
                     f"lives only in core.sentry, exactly like a block gate)")
            record = {"block": block, "stage": "review", "holding": holding,
                     "gate_idle_cap": GATE_IDLE_CAP, "detail": detail, "at": now}
            manifest.setdefault("escalations", []).append(record)
            eng.log("flow", f"sentry: ESCALATED {block} — {detail}")
            workers.pop(agent_id, None)   # the ONE thing that frees a reviewer's slot
            casestate.open_case(eng, manifest, block, "sentry.cap", detail,
                                worker_id=agent_id, kind="cap")
            eng._release_worker(agent_id, reason=f"sentry-cap ({block})")
            escalated.append((block, detail))
            continue

        if holding >= GATE_NUDGE_AFTER and w.get("nudged_at") is None:
            _nudge(eng, block, w, "review", holding)
            w["nudged_at"] = now
            nudged.append(block)

    return nudged, escalated


def pace(eng, snapshot):
    """Walk every in-flight gate in `snapshot.gates`, nudge/cap exactly as
    described in the module docstring. Returns `{"nudged": [block, ...],
    "escalated": [(block, detail), ...]}` — a NON-durable convenience for
    the caller (`core/tick.py` folds `escalated` into its own tick result,
    same shape `core.gate.advance`'s own escalate outcomes already use);
    `manifest["escalations"]` is the durable record.

    Wave 10: ALSO paces any `held` reviewer (`_pace_reviewers`, below) off
    the SAME clock reading THIS call already minted — one shared "now" for
    every stage, block gate or review hold alike, same discipline the
    module docstring's own multi-gate proof already establishes."""
    manifest = snapshot.manifest
    gates = snapshot.gates
    now = _clock(eng, manifest)

    nudged, escalated = [], []
    for block, gate_state in gates.items():
        stage = gate_state.get("stage")
        if stage in _TERMINAL_STAGES:
            # Already terminal (this tick's own gate.advance pass, a PRIOR
            # pace() call, or a gate seeded pre-closed) — never pace a
            # terminal gate; drop any stale episode so it can't leak.
            _drop_pacing(gate_state)
            continue

        if gate_state.get("holding_stage") != stage:
            # Just advanced into this stage (or first time pace() has ever
            # seen this gate) — progress clears the clock; no holding time
            # accrues on the tick a gate actually moved.
            gate_state["holding_stage"] = stage
            gate_state["holding_since"] = now
            gate_state.pop("nudged_at", None)
            continue

        if _worker_working(eng, gate_state.get("wid")):
            # The worker is provably mid-turn — it IS making progress, just
            # not yet observably at this gate stage (a long build/land turn
            # posts nothing until it finishes). Re-anchor the episode: only
            # genuine idle-at-gate time ever accrues toward nudge/cap, never
            # a live turn's own wall-clock. (No prior rig sets the hook, so
            # this branch is inert for all of them.)
            gate_state["holding_since"] = now
            gate_state.pop("nudged_at", None)
            continue

        holding = now - gate_state["holding_since"]

        if holding >= GATE_IDLE_CAP:
            detail = _escalate(eng, manifest, block, gate_state, stage, holding, now)
            _drop_pacing(gate_state)
            escalated.append((block, detail))
            continue

        if holding >= GATE_NUDGE_AFTER and gate_state.get("nudged_at") is None:
            _nudge(eng, block, gate_state, stage, holding)
            gate_state["nudged_at"] = now
            nudged.append(block)

    r_nudged, r_escalated = _pace_reviewers(eng, manifest, now)
    nudged.extend(r_nudged)
    escalated.extend(r_escalated)

    # ── wave 17 (GAP-A, core/casestate.py): THE FLOOR — re-ping every
    #     still-OPEN operator case (any source: worker.wall/sentry.cap/
    #     worker.stalled/block-less) forever, on its OWN bounded backoff,
    #     off the SAME clock reading this call already minted. Deliberately
    #     NOT folded into `nudged`/`escalated` above — a DIFFERENT ladder,
    #     paging receipts, never a gate/reviewer stage outcome — so this
    #     ladder's own re-ping activity stays invisible to (never breaks)
    #     `core/tick.py`, which only ever reads those two keys off this
    #     dict, or any existing caller/rig already asserting on them. ──
    casestate.reping(eng, manifest, now)

    return {"nudged": nudged, "escalated": escalated}
