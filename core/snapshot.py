"""core.snapshot — the immutable per-tick view `core.tick`'s decide step reads.

`build(eng) -> Snapshot` performs the WHOLE observe phase in one call
(contracts/blueprint-contracts.md §5's "load MANIFEST → ... → build
snapshot"): `core.state.load` (fresh manifest off disk), drain
`ctx.worker_inbox` (`tag`+`slots` structured JSON lines, resolved without the
model, PLUS free-text `{text, sender}` lines — the ONE real classify_message
call, per line — since wave 13, `core/classify.py`), then one `core.gitobs`
trunk-tip read. Nothing here is retained between ticks — `core.tick.tick`
discards the `Snapshot` at tick end; this module keeps no module-level state
of its own.

Wave 13 (`core/classify.py`): EVERY drained line — structured or free-text —
is resolved to its `(tag, slots)` HERE, in this SAME observe pass, via
`classify.classify(eng, rep, manifest)`: a structured line (already carrying
its own `tag`) resolves deterministically, the model never consulted
(`classify.py`'s own structured-bypass check, first); a genuinely free-text
line is the one place per tick the model is touched. This is what pins the
model to OBSERVE and keeps `decide`/`act`/`route` pure: by the time `core/
router.py::route` or `core/gate.py::advance` ever sees a `worker_reports`
entry, its `tag` is ALREADY resolved — neither module imports `classify`
or `engine/judge.py`, and calls it never. `slots.block`/`slots.agent_id`
(the shape `classify_message`'s own contract pulls a block id / agent id
INTO, per `routing.yaml`'s `tools:` entry) are promoted to the report's
top level when the line didn't already carry one, so a classify-derived
`worker.done` line reads identically to a hand-written structured one to
every downstream reader (`local_reports`, below, `core/router.py`'s own
`_route_online`/`_route_wall`/`_route_decision`).

The inbox drain follows the SAME at-least-once idiom `engine/fsm.py::
_claim_inboxes` uses (learned by reading, re-expressed fresh here — never
copied): rotate the live inbox to a `.proc` sidecar (atomic rename — a fresh
append landing after the rename starts a new inbox, never lost to a
full-file rewrite); if a `.proc` already exists (the crash residue of a
prior tick that drained but never got to persist), read THAT again instead
of rotating a new one, so a report a crashed tick already consumed from the
live file is never silently dropped. The sidecar is NOT deleted here —
`release` (below) is the caller's job, invoked only AFTER `core.state.save`
succeeds, so a crash before persist leaves the sidecar for the next tick to
re-drain. This is the ONE non-git-observable input `core/gate.py`'s own
docstring calls out (`local_report`, `gate.local`'s predicate — "the ONE
piece of the DONE ladder that isn't purely git-observable"); everything else
a gate stage needs is re-derived from real git/grants state on every call,
so only THIS input needs the persist-gated release discipline.

`gates` is a direct alias onto `manifest.setdefault("gates", {})` — mutating
a `gate_state` dict inside it (exactly what `core.gate.advance` does)
mutates the SAME object `core.tick`'s act phase later hands to
`core.state.save`; no separate merge-back step, no copy skew.

No git/subprocess of any kind here beyond `core.gitobs`'s one delegated
call; the `.proc` rotate/read/remove is plain (non-git) file IO.
"""
import collections
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# `state` is imported BEFORE `gitobs` (below) deliberately: `gitobs`'s own
# import transitively puts `engine/` onto `sys.path` (it ships its OWN
# `state.py`, the pre-ADR-0004 `State` class) — Python caches an import by
# bare name in `sys.modules` the FIRST time it resolves, so binding the name
# "state" to `core/state.py` here, before `engine/` is ever on the path,
# keeps it bound to THIS module for the rest of the process regardless of
# what any later import does to `sys.path`. See `core/tick.py`'s matching
# note (it re-imports "state" too — same cached module, no re-resolution).
import state    # noqa: E402 — core/state.py
import gitobs   # noqa: E402 — core/gitobs.py, the ONE git-observation seam
import classify # noqa: E402 — core/classify.py, wave 13's ONE LLM seam, run HERE (observe)


Snapshot = collections.namedtuple(
    "Snapshot", ["manifest", "gates", "trunk_tip", "worker_reports", "local_reports",
                "inbox_sidecar"])


def _drain_inbox(ctx, log):
    """Rotate `ctx.worker_inbox` to a `.proc` sidecar (or re-read a `.proc`
    a crashed prior tick already rotated — at-least-once). Returns
    `(reports, sidecar_path_or_None)`. A malformed/structurally-invalid line
    is logged and skipped — one poison line must never sink the whole tick.
    A well-formed line is either ALREADY structured (carries its own `tag`)
    or genuinely free-text (carries `text` — `classify_message`'s own input
    shape, `{text, sender}`); `build()`, below, resolves EVERY one of these
    to a tag via `core.classify.classify` before this tick's `route`/`act`
    ever sees it — a line with NEITHER key is the only shape still dropped
    here as structurally invalid."""
    path = ctx.worker_inbox
    proc = path + ".proc"
    if not os.path.exists(proc):
        if not os.path.exists(path):
            return [], None
        try:
            os.rename(path, proc)
        except OSError as e:
            log("flow", f"snapshot: inbox rotate failed ({e}); draining nothing this tick")
            return [], None

    reports = []
    with open(proc, "r") as fh:
        lines = fh.readlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            log("flow", f"snapshot: dropped a malformed worker-inbox line: {e}")
            continue
        if not isinstance(rec, dict) or ("tag" not in rec and "text" not in rec):
            log("flow", f"snapshot: dropped a structurally invalid worker-inbox line: {line!r}")
            continue
        reports.append(rec)
    return reports, proc


def _classify_reports(eng, manifest, raw_reports):
    """Wave 13: resolve EVERY drained line to its `(tag, slots)` here, in the
    observe pass — `core.classify.classify` does the structured-bypass check
    internally (a line already carrying a `tag` never touches the model);
    a free-text line is the one real classify_message call. `slots.block`/
    `slots.agent_id` (classify_message's own contract pulls these INTO
    slots) are promoted to the report's top level when the line didn't
    already carry one of its own, so a classify-derived report reads
    identically to a hand-written structured one to every downstream reader
    (`local_reports` below, `core/router.py`'s own per-tag handlers)."""
    resolved = []
    for rep in raw_reports:
        tag, slots = classify.classify(eng, rep, manifest)
        out = dict(rep)
        out["tag"] = tag
        merged_slots = {**(rep.get("slots") or {}), **(slots or {})}
        out["slots"] = merged_slots
        if "block" not in out and merged_slots.get("block"):
            out["block"] = merged_slots["block"]
        if "agent_id" not in out and merged_slots.get("agent_id"):
            out["agent_id"] = merged_slots["agent_id"]
        # IDENTITY BRIDGE: a REAL worker report (scripts/report.sh, or the
        # courier's harvested turn-output) carries the worker id ONLY in
        # `sender.id` — `report.sh` writes `sender:{kind:"worker",id:<wid>}`
        # and never a top-level `agent_id`, and `classify_message` emits none
        # either. Every downstream handler (`core/router.py::_route_online`/
        # `_route_wall`, `core/reviewers.py::on_review_done`, `core/liveness.py
        # ::touch`) reads `agent_id`/`worker_id` at the top level, so without
        # this bridge a real report is dropped as "malformed" (the T2-01
        # wall). Promote `sender.id` -> both keys when absent; every scripted
        # rig writes a top-level `agent_id` directly, so this is inert for
        # them.
        sender_id = (rep.get("sender") or {}).get("id")
        if sender_id:
            out.setdefault("agent_id", sender_id)
            out.setdefault("worker_id", sender_id)
        resolved.append(out)
    return resolved


def build(eng):
    """Assemble this tick's immutable view — the whole observe phase, in one
    call: fresh manifest (`core.state.load`), this tick's inbox drain
    resolved to tagged reports (`_classify_reports`, wave 13 — the ONE
    place `core/classify.py` runs, see module docstring), and one real
    trunk-tip read (`core.gitobs.tip_sha`, never a raw git call)."""
    ctx = eng.ctx
    manifest = state.load(ctx)
    raw_reports, sidecar = _drain_inbox(ctx, eng.log)
    worker_reports = _classify_reports(eng, manifest, raw_reports)

    root = eng.paths["root"]
    main_branch = eng.paths.get("main_branch", "main")
    trunk_tip = gitobs.tip_sha(root, main_branch, eng.dry)

    gates = manifest.setdefault("gates", {})

    # A worker.done/local-pass report is the ONE structural shape this brick
    # reads (core/gate.py's own `local_report` kwarg contract: a well-formed
    # `{"verdict": "pass", "evidence": <str>}` dict). Last-one-wins per block
    # if more than one arrived this tick — the same "only what THIS call is
    # handed" discipline `core/gate.py::_advance_local`'s own docstring
    # documents for `local_report` (nothing from a prior tick's report is
    # ever implicitly re-supplied).
    local_reports = {}
    for rep in worker_reports:
        if rep.get("tag") == "worker.done" and rep.get("block"):
            # A `worker.done` IS the worker asserting a local pass ("done
            # <block> — local: <evidence>", worker-contract.md §3) — "done is
            # a trigger, not truth" (the TRUTH is re-checked git-observably at
            # gate.trunk). A REAL report.sh `--tag done --block` carries only
            # `{block}` in slots — no `verdict`/`evidence` (report.sh has no
            # such flags; classify_message emits none) — so `gate.local`'s
            # `{"verdict":"pass","evidence":<str>}` contract could never be
            # met by a real worker (the T2-01 gate.local wall). Synthesize the
            # pass verdict from the done report, evidence = its own text; a
            # scripted rig already puts verdict/evidence in slots, so
            # setdefault leaves it untouched.
            slots = dict(rep.get("slots") or {})
            slots.setdefault("verdict", "pass")
            slots.setdefault("evidence", (rep.get("text") or "").strip()
                             or f"{rep['block']}: worker reported done (no evidence text)")
            local_reports[rep["block"]] = slots

    return Snapshot(manifest=manifest, gates=gates, trunk_tip=trunk_tip,
                    worker_reports=worker_reports, local_reports=local_reports,
                    inbox_sidecar=sidecar)


def release(snap):
    """Drop the drained inbox sidecar — ONLY ever called by `core.tick.tick`
    AFTER `core.state.save` has succeeded (at-least-once: a crash before
    this leaves the sidecar for the next tick to re-drain, same discipline
    as `engine/fsm.py::_release_claimed`)."""
    sidecar = snap.inbox_sidecar
    if not sidecar:
        return
    try:
        os.remove(sidecar)
    except OSError:
        pass
