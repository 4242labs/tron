"""core.snapshot — the immutable per-tick view `core.tick`'s decide step reads.

`build(eng) -> Snapshot` performs the WHOLE observe phase in one call
(contracts/blueprint-contracts.md §5's "load MANIFEST → ... → build
snapshot"): `core.state.load` (fresh manifest off disk), drain EVERY
agent's own private intake (`core.intake.drain_all` — `tag`+`slots`
structured JSON lines; a tag-less line declaring a `branch` is the one
other structural shape, T3), then one `core.gitobs` trunk-tip read.
Nothing here is retained between ticks — `core.tick.tick` discards the
`Snapshot` at tick end; this module keeps no module-level state of its
own.

Block 01-38 T1 (the root invariant): the single shared `ctx.worker_inbox`
drop-box is GONE from this path — deleted, not sanitized. Every drained
line is now paired with an `Origin` (`core.intake.Origin`) the drain
resolves from WHICH agent's intake it came from, never from anything the
line itself claims; `_classify_reports`, below, threads that `Origin`
onto the resolved report as `out["origin"]` (an engine-computed field no
vocab slot/report.sh flag can ever set — the sole write site is here).

Block 01-38 T2: the resolved report `_classify_reports` returns is now a
`core.report.Report` — a typed record whose five identity keys (`sender`,
`worker`, `actor`, `agent_id`, `worker_id`) do not exist as readable/
writable slots (see `core/report.py`'s own docstring: a read/write of one
raises `IdentityNotOnMessage`, never returns `None`). The old "IDENTITY
BRIDGE" that promoted a raw line's `sender.id` onto `agent_id`/`worker_id`
top-level keys is DELETED — there is nothing left to bridge onto. Every
raw line's own `sender`/`agent_id`/`worker_id` keys (still written by a
not-yet-T6-honest rig, or a hostile line) are dropped at construction,
never copied through: `origin` (block 01-38 T1's typed value, resolved
purely from WHICH intake the line drained from) is the SOLE identity
carrier from here on.

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
import intake   # noqa: E402 — core/intake.py, block 01-38 T1's per-agent drain + Origin
import report as report_mod   # noqa: E402 — core/report.py, block 01-38 T2's identity-slot-free typed record


Snapshot = collections.namedtuple(
    "Snapshot", ["manifest", "gates", "trunk_tip", "worker_reports", "local_reports",
                "inbox_sidecars"])


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
    which reads `triage_id`/`verdict` at TOP level).

    Block 01-38 T1/T2: `raw_reports` is a list of `(Origin, dict)` pairs
    (`core.intake.drain_all`'s own return shape). `classify.classify` is
    handed the resolved `origin` directly (never derived from the raw
    line's own claimed `sender` — T2 deletes that derivation entirely, see
    `core/classify.py`). The returned report is a `core.report.Report`
    (block 01-38 T2's typed record, `core/report.py`): every key the raw
    line or `slots` carried is copied through EXCEPT the five identity keys
    `core.report.FORBIDDEN_IDENTITY_KEYS` names (`sender`/`worker`/`actor`/
    `agent_id`/`worker_id`) — dropped here, never copied through, whether or
    not a not-yet-T6-honest rig (or a hostile line) still writes one. `out
    ["origin"] = origin` is the ONE write site for identity from here on;
    every downstream reader (`core/router.py`, `core/liveness.py`, `core/
    reviewers.py`) reads `rep["origin"]`, never a message-borne field."""
    resolved = []
    for origin, rep in raw_reports:
        tag, slots = classify.classify(eng, origin, rep, manifest)
        if tag is None:
            continue   # door-refused (T3/T8) — already fully handled, never routed
        out = report_mod.Report(
            {k: v for k, v in rep.items() if k not in report_mod.FORBIDDEN_IDENTITY_KEYS})
        out["tag"] = tag
        out["origin"] = origin
        merged_slots = {**(rep.get("slots") or {}), **(slots or {})}
        out["slots"] = merged_slots
        for key in vocab.PROMOTED_SLOT_KEYS:
            # T2: a forbidden identity key can never be promoted onto a
            # `Report` (it has no such slot at all — see core/report.py) —
            # skipped unconditionally, independent of whatever
            # `vocab.PROMOTED_SLOT_KEYS` happens to declare (a mutation rig,
            # e.g. core/verdict_wire_rig.py's own A-MUTATE scenario, may
            # temporarily include one; that must never crash this loop).
            if key in report_mod.FORBIDDEN_IDENTITY_KEYS:
                continue
            if key not in out and merged_slots.get(key):
                out[key] = merged_slots[key]
        resolved.append(out)
    return resolved


def build(eng):
    """Assemble this tick's immutable view — the whole observe phase, in one
    call: fresh manifest (`core.state.load`), this tick's PER-AGENT intake
    drain (`core.intake.drain_all` — block 01-38 T1; the single shared
    `ctx.worker_inbox` is gone from this path) resolved to tagged reports
    (`_classify_reports`, wave 13 — the ONE place `core/classify.py` runs,
    see module docstring), and one real trunk-tip read
    (`core.gitobs.tip_sha`, never a raw git call)."""
    ctx = eng.ctx
    manifest = state.load(ctx)
    raw_reports, sidecars = intake.drain_all(ctx, eng.log)
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
    """Drop every drained intake sidecar — ONLY ever called by
    `core.tick.tick` AFTER `core.state.save` has succeeded (at-least-once:
    a crash before this leaves each sidecar for the next tick to re-drain,
    same discipline as `engine/fsm.py::_release_claimed`). Plural now
    (block 01-38 T1): one sidecar per agent intake actually drained this
    tick, never a single shared one."""
    for sidecar in snap.inbox_sidecars or ():
        try:
            os.remove(sidecar)
        except OSError:
            pass
