"""core.snapshot — the immutable per-tick view `core.tick`'s decide step reads.

`build(eng) -> Snapshot` performs the WHOLE observe phase in one call
(contracts/blueprint-contracts.md §5's "load MANIFEST → ... → build
snapshot"): `core.state.load` (fresh manifest off disk), drain
`ctx.worker_inbox` (`tag`+`slots` structured JSON lines — a tag-less line
declaring a `branch` is the one other structural shape, T3), then one
`core.gitobs` trunk-tip read. Nothing here is retained between ticks —
`core.tick.tick` discards the `Snapshot` at tick end; this module keeps no
module-level state of its own.

Block 01-37 (T3/T8): EVERY drained line is resolved to its `(tag, slots)`
HERE, in this SAME observe pass, via `classify.classify(eng, rep,
manifest)` — structurally, off `core/vocab.py`'s closed vocabulary; the
free-text GRADER is retired (§6(b)), so nothing here ever touches a model.
A line the admission door refuses resolves to `(None, None)` and is DROPPED
from `worker_reports` entirely (see `_classify_reports`'s own docstring) —
by the time `core/router.py::route` or `core/gate.py::advance` ever sees a
`worker_reports` entry, its `tag` is a real vocab member, ALREADY resolved
— neither module imports `classify`/`door`/`vocab`, and calls neither.
`vocab.PROMOTED_SLOT_KEYS` are promoted to the report's top level when the
line didn't already carry one, so a classify-derived `worker.done` line
reads identically to a hand-written structured one to every downstream
reader (`local_reports`, below, `core/router.py`'s own `_route_online`/
`_route_wall`/`_route_decision`).

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
import classify # noqa: E402 — core/classify.py, the structured-only door resolver, run HERE (observe)
import vocab    # noqa: E402 — core/vocab.py, PROMOTED_SLOT_KEYS (block 01-37, T9)


Snapshot = collections.namedtuple(
    "Snapshot", ["manifest", "gates", "trunk_tip", "worker_reports", "local_reports",
                "inbox_sidecars"])


def _drain_inbox_at(path, log, label):
    """Rotate `path` to a `.proc` sidecar (or re-read a `.proc` a crashed
    prior tick already rotated — at-least-once). Returns `(reports,
    sidecar_path_or_None)`. A malformed/structurally-invalid line is logged
    and skipped — one poison line must never sink the whole tick. A
    well-formed line is either ALREADY structured (carries its own `tag`)
    or genuinely free-text (carries `text` — `classify_message`'s own input
    shape, `{text, sender}`); `build()`, below, resolves EVERY one of these
    to a tag via `core.classify.classify` before this tick's `route`/`act`
    ever sees it — a line with NEITHER key is the only shape still dropped
    here as structurally invalid. `label` is used only for the log line
    (which channel this drain belongs to)."""
    proc = path + ".proc"
    if not os.path.exists(proc):
        if not os.path.exists(path):
            return [], None
        try:
            os.rename(path, proc)
        except OSError as e:
            log("flow", f"snapshot: {label} rotate failed ({e}); draining nothing this tick")
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
            log("flow", f"snapshot: dropped a malformed {label} line: {e}")
            continue
        if not isinstance(rec, dict) or ("tag" not in rec and "text" not in rec):
            log("flow", f"snapshot: dropped a structurally invalid {label} line: {line!r}")
            continue
        reports.append(rec)
    return reports, proc


def _drain_inbox(ctx, log):
    """LEGACY shared-inbox drain (pre-block-01-38) — `ctx.worker_inbox`,
    sender-as-written (never overwritten for a NORMAL worker report — see
    below). Kept for backward compatibility: several pre-01-38 `core/
    *_rig.py` fixtures still write here directly (none of block 01-38's own
    Tasks name or touch them — see `engine/ctx.py::worker_inbox`'s own
    docstring). A REAL spawn never writes here at all (`_drain_agent_
    channels`, below, is the real, ambient-identity path).

    R6/R8 widening (hostile-review fix, block 01-38): every line drained
    here is stamped `_channel="legacy"` — UNCONDITIONALLY overwriting any
    payload-asserted marker of the same name, never trusted from the
    payload — because this ONE channel is shared and self-typed (any
    process, a genuine worker abusing `report.sh`'s legacy `<worker-id>
    ...` branch included, can write a line here claiming ANY `sender.id`,
    including `architect_wid`). `core/vocab.py::resolve_origin` reads this
    marker: a line from THIS drain can never resolve to a PRIVILEGED origin
    (ARCHITECT/OPERATOR) no matter what identity it claims — only the two
    channels below (filename-derived, unforgeable) can. An ORDINARY worker
    report (`worker.online`/`worker.wall`/`worker.done`/...) is entirely
    unaffected — those tags' minters already include WORKER, the only
    origin a legacy line can ever resolve to now."""
    reports, sidecar = _drain_inbox_at(ctx.worker_inbox, log, "worker-inbox")
    for rec in reports:
        rec["_channel"] = "legacy"
    return reports, sidecar


def _agent_channel_ids(ctx):
    """Every agent id with a live or crash-residual per-agent channel under
    `ctx.inbox_dir` — the UNION of `*.jsonl` and `*.jsonl.proc` basenames,
    so an orphaned `.proc` sidecar (a prior tick that rotated but crashed
    before persisting) is still found and re-drained even if its live
    `.jsonl` sibling no longer exists. Sorted for deterministic drain
    order. Empty (never an error) when `ctx.inbox_dir` doesn't exist yet —
    every canon-less `core/*_rig.py` fixture that never spawns a real
    agent."""
    d = ctx.inbox_dir
    if not os.path.isdir(d):
        return []
    ids = set()
    for name in os.listdir(d):
        if name.endswith(".jsonl.proc"):
            ids.add(name[:-len(".jsonl.proc")])
        elif name.endswith(".jsonl"):
            ids.add(name[:-len(".jsonl")])
    return sorted(ids)


def _drain_agent_channels(ctx, log):
    """R6 (block 01-38 T1) — drain EVERY per-agent channel
    (`inbox/<agent_id>.jsonl`), one at a time via `_drain_inbox_at` (the
    SAME at-least-once idiom the legacy shared inbox already uses). THE
    ambient-identity enforcement point: every line drained here has its
    `sender` UNCONDITIONALLY OVERWRITTEN to `{"kind": "worker", "id":
    agent_id}` — `agent_id` being the CHANNEL (the filename) it arrived
    on, never whatever the line's own JSON payload happened to claim. A
    worker's own installed `report.sh` copy can only ever write to ITS OWN
    channel (ambient, at spawn — `core/engine.py::Engine.
    _install_agent_channel`), so even a maliciously hand-crafted payload
    claiming a different `sender.id` is corrected here, before classify/
    door/minters ever sees it — the D8 impersonation hole, closed
    structurally, not by convention. (The architect is a worker-SHAPED
    sender per `core/vocab.py`'s own docstring — its channel is `inbox/
    <ARCHITECT_WID>.jsonl`, drained identically; `kind` stays `"worker"`
    either way, `vocab.resolve_origin` resolves ARCHITECT purely off
    `sender.id == architect_wid`.)

    Returns `(reports, sidecars)` — `sidecars` a list of every `.proc`
    path this pass rotated/re-read, released together by `release()`."""
    reports = []
    sidecars = []
    for agent_id in _agent_channel_ids(ctx):
        chan_reports, sidecar = _drain_inbox_at(
            ctx.agent_inbox(agent_id), log, f"agent-inbox[{agent_id}]")
        for rec in chan_reports:
            rec["sender"] = {"kind": "worker", "id": agent_id}
            # A payload-asserted `agent_id`/`worker_id` at the TOP LEVEL
            # (never written by the real report.sh door, which only ever
            # writes `sender` — but a hand-crafted line theoretically
            # could) must NOT survive the ambient stamp above: `_classify_
            # reports`'s own IDENTITY BRIDGE only `setdefault`s these keys
            # off `sender.id`, so a pre-existing top-level claim would
            # otherwise silently outrank the channel-derived identity —
            # the exact impersonation surface R6 exists to close. Strip,
            # never trust.
            rec.pop("agent_id", None)
            rec.pop("worker_id", None)
        reports.extend(chan_reports)
        if sidecar:
            sidecars.append(sidecar)
    return reports, sidecars


def _mark_operator_seen(manifest, raw_reports):
    """R8 (block 01-38 T2/T3, AC-3): the SECOND receipt level — mark a case
    `seen` the moment the operator's OWN reply names it, independent of
    whether that reply parses into a valid `resume`/`amend`/`abandon`
    verb (a malformed reply still proves a human read it; the door
    refusing its CONTENT must never also erase that fact). Runs on the
    RAW drained operator-inbox lines, before classify/door — a structured
    line's `slots.case_id` is trusted directly; a free-text line is
    matched the SAME way `core/classify.py::_settle_from_text` matches an
    id (a substring of a genuinely OPEN case id — never a guess at one
    that isn't), but WITHOUT requiring a recognizable verb (that
    distinction is exactly what makes this catch a malformed reply
    `_settle_from_text` itself would refuse)."""
    import casestate   # local — casestate imports vocab, no cycle risk from here
    cases = manifest.get("cases") or {}
    open_ids = [cid for cid, c in cases.items() if c.get("decision") is None]
    if not open_ids:
        return
    for rec in raw_reports:
        slots = rec.get("slots") or {}
        case_id = slots.get("case_id")
        if case_id and case_id in open_ids:
            casestate.mark_seen(manifest, case_id)
            continue
        text = rec.get("text") or ""
        if not text:
            continue
        hit = next((cid for cid in open_ids if cid in text), None)
        if hit:
            casestate.mark_seen(manifest, hit)


def _drain_operator_channel(ctx, log, manifest):
    """R8 (block 01-38 T3) — drain `ctx.operator_inbox` EVERY TICK,
    alongside the per-agent channels above. Every line's `sender` is
    UNCONDITIONALLY OVERWRITTEN to `{"kind": "operator", "id":
    "operator"}` — the SAME ambient-identity discipline
    `_drain_agent_channels` applies, so a payload cannot self-assert
    operator identity either; only this ONE channel ever resolves to it.
    Marks the `seen` receipt (`_mark_operator_seen`, above) BEFORE
    returning — `manifest` may be `None` for a caller with no manifest in
    scope (mirrors `core.classify.classify`'s own optional-manifest
    contract), in which case seen-marking is skipped (nothing to mark)."""
    raw, sidecar = _drain_inbox_at(ctx.operator_inbox, log, "operator-inbox")
    for rec in raw:
        rec["sender"] = {"kind": "operator", "id": "operator"}
        rec.pop("agent_id", None)   # never trust a payload-asserted identity (see _drain_agent_channels)
        rec.pop("worker_id", None)
    if manifest is not None:
        _mark_operator_seen(manifest, raw)
    return raw, ([sidecar] if sidecar else [])


def _classify_reports(eng, manifest, raw_reports):
    """Block 01-37 (T3/T8): resolve EVERY drained line to its `(tag, slots)`
    here, in the observe pass — `core.classify.classify` does the
    structured-bypass check internally (a line already carrying a `tag`
    never touches a model — the free-text GRADER is retired; every
    resolution is now structural or a door refusal, never an LLM guess).
    `classify.classify` returns `(None, None)` for a line the admission
    door already fully handled (refused: recorded + an architect-first case
    opened, `core.door.refuse`) — such a line is DROPPED from the returned
    list entirely, never handed to `core/router.py::route` as a report (its
    own docstring: "never double-cased with a door refusal" — the router's
    T4 catch-all is a separate backstop for a tag that bypasses THIS door,
    not a second handler for one this door already refused).

    `vocab.PROMOTED_SLOT_KEYS` (T9, ADR-0011 S-2 lock 4, generalized from
    the salvage `PROMOTED_SLOT_KEYS` constant) are promoted to the report's
    top level when the line didn't already carry one of its own, so a
    classify-derived report reads identically to a hand-written structured
    one to every downstream reader (`local_reports` below, `core/router.py`
    's own per-tag handlers — `_route_architect_triage_verdict` included,
    which reads `triage_id`/`verdict` at TOP level)."""
    resolved = []
    for rep in raw_reports:
        tag, slots = classify.classify(eng, rep, manifest)
        if tag is None:
            continue   # door-refused (T3/T8) — already fully handled, never routed
        out = dict(rep)
        out["tag"] = tag
        merged_slots = {**(rep.get("slots") or {}), **(slots or {})}
        out["slots"] = merged_slots
        for key in vocab.PROMOTED_SLOT_KEYS:
            if key not in out and merged_slots.get(key):
                out[key] = merged_slots[key]
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
    # R6/R8 (block 01-38 T1/T3): THREE drains, merged into one resolved-report
    # pass — the legacy shared inbox (backward compat, untouched sender),
    # every per-agent ambient channel (a REAL spawn's only path, sender
    # stamped from the channel filename), and the operator's own inbound
    # channel (drained every tick, sender stamped "operator", seen marked).
    legacy_reports, legacy_sidecar = _drain_inbox(ctx, eng.log)
    agent_reports, agent_sidecars = _drain_agent_channels(ctx, eng.log)
    operator_reports, operator_sidecars = _drain_operator_channel(ctx, eng.log, manifest)
    raw_reports = legacy_reports + agent_reports + operator_reports
    sidecars = ([legacy_sidecar] if legacy_sidecar else []) + agent_sidecars + operator_sidecars
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
                    inbox_sidecars=sidecars)


def release(snap):
    """Drop every drained inbox sidecar (legacy + every per-agent channel +
    the operator channel) — ONLY ever called by `core.tick.tick` AFTER
    `core.state.save` has succeeded (at-least-once: a crash before this
    leaves each sidecar for the next tick to re-drain, same discipline as
    `engine/fsm.py::_release_claimed`). One channel's removal failing never
    stops another's."""
    for sidecar in (snap.inbox_sidecars or []):
        try:
            os.remove(sidecar)
        except OSError:
            pass
