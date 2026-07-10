"""core.tick — the bounded, crash-safe TICK HOST (contracts/blueprint-
contracts.md §5's tick model; rebuild-spec.md T1-B / B1-B11 + C1/D1's
DISPATCH front end, wave 5).

`tick(eng)` is ONE bounded pass: observe -> route -> decide -> act -> fill ->
persist -> exit.
No state carries between calls in memory — everything that must survive a
wake lives in `ctx.state` (`manifest.yaml`, via `core.state`) and is reloaded
FRESH at the top of every call (inside `core.snapshot.build`). This is
deliberate: it is what makes a crashed tick safe to just re-run
(idempotency) — the next call to `tick(eng)` reads whatever the LAST
successful `core.state.save` wrote (never this call's own in-memory
leftovers) and re-derives everything else from real git (`core.gitobs`, via
`core.gate`'s own re-derivable predicates) and the real grants dir
(`core.landing`'s content-bound, observe-first `land_via_grant`) — never
from a message this process merely remembers sending.

  observe   `core.snapshot.build(eng)` — `core.state.load` (fresh manifest)
            + drain `ctx.worker_inbox` (structured `tag`+`slots` JSON lines;
            NO LLM/classify in this brick — a `worker.done` line IS the
            local-pass report and a `worker.online` line IS the ASSIGN
            report, both read structurally) + one real trunk-tip read. See
            `core/snapshot.py`'s own docstring for the inbox's persist-gated,
            at-least-once drain discipline.

  route     `core/router.py::route` (wave 5, structured — NO LLM/classify):
            drains this tick's `worker.online` reports and ASSIGNS — opens
            the block's gate at `gate.local`, bound to the worker's OWN
            reported `worker.branch` (never a guessed `feat/<block>`). Runs
            BEFORE `decide` so a worker that came online THIS tick has its
            new gate driven THIS SAME tick, not next.

  decide    pure-ish: for each in-flight block gate in the snapshot (every
            entry in `manifest["gates"]` not already `closed`/`escalated`,
            INCLUDING any `route` just opened above), look up whatever
            local-pass report THIS tick's drain surfaced for it (or `None`)
            — no mutation yet, just the (block, gate_state, local_report)
            triples `act` will drive.

  act       idempotent: call `core.gate.advance` exactly once per in-flight
            block (one observable step each — `core.gate.advance`'s own
            contract; a full close takes many ticks, by design, the WAKE
            model). `gate.advance`'s own landing calls
            (`core.landing.land_via_grant`) are themselves idempotent by
            content-bound case-id + observe-first ancestry, so replaying
            this step against a stale-but-real manifest (a crashed tick's
            unpersisted pass) never double-lands — see
            `core/tick_rig.py`'s crash-replay proof. A gate reaching
            `closed` released its worker slot inside `gate.advance` itself
            (`eng._release_worker`); an `escalate` is just collected here
            for the tick result (a manifest field for now — sentry is a
            later wave).

  fill      `core/switchboard.py::fill` (wave 5) — SPAWN into whatever
            worker slots are STILL free after `act` above: a gate that
            closed THIS tick frees its slot the same tick (PULSE's own
            ordering, blueprint-contracts.md §5), so `fill` must run AFTER
            `act`, never before. State-guarded off the manifest alone
            (`core/pipeline.py`'s own in-flight read) — a block already
            in-flight (a live worker awaiting ASSIGN, or an open gate) is
            never re-picked, so a block is dispatched exactly once, whether
            across ticks or within this same call.

  persist   `core.state.save` — atomic, and ONLY after the whole pass above
            has run to completion. Then, and only then, the drained inbox
            sidecar is released (`core.snapshot.release`). If this process
            dies anywhere before this line, NOTHING durable has changed: the
            next `tick(eng)` call reloads the exact prior manifest and (if a
            `.proc` sidecar survived) re-drains the same report — safe,
            because every mutation `act`/`route`/`fill` performed is either
            re-derivable from real git/grants state or itself a plain,
            re-derivable-on-replay manifest write, never trusted from memory
            alone.

Keeps ALL git observation inside `core.gitobs` (via `core.gate`/
`core.snapshot`/`core.pipeline`); this module itself makes no file-IO or
git/subprocess call of any kind — it only orchestrates `core.snapshot` +
`core.router` + `core.gate` + `core.switchboard` + `core.state`.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# `state` imported FIRST, before `snapshot`/`gate` (whose own imports
# transitively put `engine/` — which ships its OWN `state.py` — onto
# `sys.path`): see `core/snapshot.py`'s matching note. Binding the bare name
# "state" to `core/state.py` here first keeps it correctly bound for the
# rest of the process no matter what a caller's own `sys.path` setup does
# afterward.
import state        # noqa: E402 — core/state.py
import snapshot     # noqa: E402 — core/snapshot.py, the per-tick immutable view
import gate         # noqa: E402 — core/gate.py, the DONE ladder this host drives
import router       # noqa: E402 — core/router.py, wave 5's structured ASSIGN
import switchboard  # noqa: E402 — core/switchboard.py, wave 5's SPAWN
import pipeline     # noqa: E402 — core/pipeline.py, wave 6's ONE pipeline-view read per tick
import session       # noqa: E402 — core/session.py, wave 6's clean SESSION-END terminal

_TERMINAL_STAGES = (gate.STAGE_CLOSED, gate.STAGE_ESCALATED)


def tick(eng):
    """One bounded, crash-safe tick: observe -> route -> decide -> act ->
    fill -> persist -> exit (-> session-end, wave 6). Returns a compact,
    NON-durable result dict for the rig/log — `{"advanced": [block, ...],
      "closed": [block, ...], "escalated": [(block, detail), ...],
      "outcomes": {block: (outcome, detail)}, "spawned": [agent_id, ...],
      "session_end": {"ended_at", "reason"} | None}` — the manifest (via
    `core.state`) is the only durable record of what happened; this return
    value is discarded by the caller like everything else in the `Snapshot`.

    Wave 6 idempotent terminal: if `manifest["session"]["ended_at"]` is
    already on file (`core.session.already_ended`), this call is a TRUE
    no-op — no manifest reload beyond the one flag check, no inbox drain, no
    trunk read, no mutation — before ANY of the observe/route/act/fill pass
    below ever runs."""
    manifest0 = state.load(eng.ctx)
    if session.already_ended(manifest0):
        eng.log("flow", f"tick: session already ended at "
                        f"{manifest0['session']['ended_at']} — no-op re-tick "
                        f"(idempotent terminal, no observe/route/act/fill)")
        return {"advanced": [], "closed": [], "escalated": [], "outcomes": {},
                "spawned": [], "session_end": manifest0.get("session")}

    # ── observe ──
    snap = snapshot.build(eng)

    # ── route (structured — NO LLM/classify in this brick): ASSIGN any
    #     worker that reported online this tick, before deciding what to
    #     drive below (a just-assigned gate is driven THIS tick, not next) ──
    router.route(eng, snap.manifest, snap.worker_reports)

    # ── decide (pure-ish: read the snapshot, decide what `act` gets fed) ──
    plan = [(block, gate_state, snap.local_reports.get(block))
            for block, gate_state in snap.gates.items()
            if gate_state.get("stage") not in _TERMINAL_STAGES]

    # ── act (idempotent) ──
    result = {"advanced": [], "closed": [], "escalated": [], "outcomes": {}, "spawned": []}
    for block, gate_state, local_report in plan:
        stage_before = gate_state.get("stage")
        outcome, detail = gate.advance(eng, block, gate_state, local_report=local_report)
        result["outcomes"][block] = (outcome, detail)
        if gate_state.get("stage") != stage_before:
            result["advanced"].append(block)
        if outcome == "closed":
            result["closed"].append(block)
        elif outcome == "escalate":
            result["escalated"].append((block, detail))

    # ── fill (SPAWN into whatever slots are STILL free after `act` — a gate
    #     that closed above frees its slot the same tick, PULSE's own
    #     ordering; state-guarded off the manifest, idempotent). `view` is
    #     the ONE trunk-pinned pipeline read this whole tick performs
    #     (wave 6) — threaded through `switchboard.fill`'s dispatch pick AND
    #     `session.check` below, never fetched twice ──
    view, _trunk_sha = pipeline.read_view(eng)
    result["spawned"] = switchboard.fill(eng, snap, view=view)

    # ── persist (atomic, AFTER the whole pass) ──
    state.save(eng.ctx, snap.manifest)
    # Only now is it safe to drop the drained inbox sidecar (persist-gated release).
    snapshot.release(snap)

    # ── session-end (wave 6): a PURE read, AFTER this tick's real
    #     observe/route/act/fill progress is already durable — so a
    #     fail-loud raise here (an inconsistent block: never silently
    #     "end") never costs work this tick already persisted for OTHER
    #     blocks; only the terminal marker itself needs its own tiny
    #     second persist, below ──
    marker = session.check(snap.manifest, view)
    result["session_end"] = marker
    if marker is not None:
        snap.manifest["session"] = marker
        state.save(eng.ctx, snap.manifest)
        eng.log("flow", f"tick: clean SESSION-END — {marker['reason']}")

    return result
