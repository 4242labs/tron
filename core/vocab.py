"""core.vocab — THE closed vocabulary (ADR-0012 §2 R1/R2/R5, block 01-37).

One importable data structure, single source, for the CORE (`core/*.py`)
report-and-reply engine: every report word (`report.sh --tag <verb>`) —
its slots, who may mint it (`minters`), its wire shape, its **class**
(`PROGRESS` | `BLOCKING`, R5/T6) — plus every outbound `core/engine.py::
emit` template id (R2: "every message identifier the engine can emit is an
imported constant"). Carries a `VERSION` (T2's spawn handshake).

Consumed by `core/router.py` (dispatch + minters + the T4 catch-all),
`core/classify.py` (verb->tag), `core/snapshot.py` (`PROMOTED_SLOT_KEYS`),
`core/engine.py::emit` (template-id membership, loud on unknown), `core/
door.py` (the inbound refusal door, T3/T6) and `engine/lint.py` (the
emit-id-literal + schema-drift gates, T2/T5). None of them keep a second
hand-maintained copy of any of it — this is the R1 "bijection is a data
structure", never regex over source text.

Orchestrator-agnostic (the seeded-scaffold contract): nothing here names a
host runtime or "TRON" — every human-facing string a caller renders off
this data is the CALLER's job (`core/door.py::legal_set_text` included).

## Scope note — the OTHER engine (read before touching `engine/lint.py`)

`engine/fsm.py` (the pre-rewrite, TABLE-driven engine still wired into
`engine/engine.py`'s `start`/`stop`/`recover`) reads its OWN closed
vocabulary out of `routing.yaml`'s `grammar:`/`tags:` — a separate,
broader, still-load-bearing document: `engine/lint.py`'s `CANON_TAGS`
(L2) and its grammar rules (L1/L4/L7/L8/L9) police THAT engine, and
`engine/block_01_11_test.py`/`engine/tron13_test.py` (both required by
`.github/workflows/engine-ci.yml`) assert `lint.CANON_TAGS` and the
`worker.progress` tag directly. ADR-0012 §2 R1's "Deletes" list and this
block's T10 name `routing.yaml`'s grammar DSL and those `engine/lint.py`
rules as dead weight belonging to "the retired engine" — but block 01-37's
own Task list (T1-T11) never names `engine/fsm.py`, `routing.yaml`, or that
test suite, and deleting them verifiably breaks currently-green, CI-
required coverage outside this block's stated scope. Per this block's own
dispatch instructions ("choose the reading that keeps tests honest and
never weakens an AC"), `core/vocab.py` governs the CORE engine's own,
smaller, actively-routed tag set ONLY; `routing.yaml`'s grammar DSL,
`CANON_TAGS`, and `engine/fsm.py` are left untouched. `engine/lint.py`
still satisfies AC-1's "imports it" by importing this module for THREE new,
additive rules (the emit-id lint, the schema regen/diff gate, and a vocab
cross-check) — see that module's own docstring. This scope boundary is
recorded again in the PR body; a follow-up block should formally retire
`engine/fsm.py` and its CI suite, at which point `CANON_TAGS` can go too.
"""
import collections
import json
import os

VERSION = "1"

PROGRESS = "progress-advancing"
BLOCKING = "blocking"

Word = collections.namedtuple("Word", ["tag", "verb", "slots", "minters", "cls", "note"])

# Origins report.sh's own AMBIENT `sender.kind`/`sender.id` resolves to
# (R6 — identity is ambient, never asserted: the architect is a
# worker-SHAPED sender whose `sender.id` is literally `ARCHITECT_WID`;
# origin is resolved by IDENTITY, never by a claim the message text makes).
WORKER, ARCHITECT, OPERATOR, ENGINE = "worker", "architect", "operator", "engine"

# ── the report-door vocabulary — every tag `core/router.py::route` (or its
#    T4 catch-all) dispatches on. `verb` is the LITERAL `--tag <verb>` token
#    `scripts/report.sh` accepts on the wire; `None` means the tag is never
#    report.sh-sendable (operator/engine-origin only — a different channel,
#    or engine-produced). ──
TAGS = {
    "worker.online": Word(
        "worker.online", "online", (), (WORKER,), PROGRESS,
        "a spawned worker checked in"),
    "worker.branch": Word(
        "worker.branch", "branch", ("branch",), (WORKER,), PROGRESS,
        "the worker names the branch it owns"),
    "worker.done": Word(
        "worker.done", "done", ("block", "branch"), (WORKER,), PROGRESS,
        "a DONE-ladder step report — a trigger, not truth"),
    "worker.recorded": Word(
        "worker.recorded", "recorded", ("block",), (WORKER,), PROGRESS,
        "the gate-ordered status commit landed"),
    "worker.review_done": Word(
        "worker.review_done", "review-done", ("type",), (WORKER,), PROGRESS,
        "a reviewer's coverage confirmation"),
    "worker.flag": Word(
        # T7 — the surfaced, non-paging visibility word. Replaces the
        # deleted `worker.progress` do-nothing route: batches to the
        # architect + an operator-readable ledger, pages no one — its class
        # is ALWAYS progress-advancing, by construction (R5's partition is
        # what makes "a visibility flag that also blocks" unrepresentable).
        "worker.flag", "flag", ("block",), (WORKER,), PROGRESS,
        "surfaced, non-paging visibility — batched to the architect + ledger"),
    "worker.wall": Word(
        "worker.wall", "wall", ("block",), (WORKER,), BLOCKING,
        "a genuine impasse — architect-first triage, never a silent drop"),
    "architect.reconciled": Word(
        "architect.reconciled", "reconciled", ("block",), (ARCHITECT,), PROGRESS,
        "forward/reconcile job done"),
    "architect.triage_verdict": Word(
        # T9 — the verdict wire (`--tag verdict --triage-id <id> --verdict
        # <v>`, ported from the salvage lineage).
        "architect.triage_verdict", "verdict", ("triage_id", "verdict"),
        (ARCHITECT,), PROGRESS,
        "the architect's own PMT-TRIAGE completion report — the verdict wire"),
    "operator.decision": Word(
        "operator.decision", None, ("case_id", "verb"), (OPERATOR,), None,
        "settle a parked case: resume | amend | abandon (operator channel, "
        "never report.sh)"),
    "worker.stalled": Word(
        "worker.stalled", None, (), (ENGINE,), None, "liveness sweep — engine-produced only"),
    "worker.dead": Word(
        "worker.dead", None, (), (ENGINE,), None, "liveness sweep — engine-produced only"),
    "worker.report_refused": Word(
        # T3/R2 — the door refusal itself, modeled as a proper vocab word
        # (never a bare count): ENGINE-minted (never report.sh-sendable —
        # it is what the door produces WHEN report.sh/the classify layer
        # rejects an attempted report), carrying the full attempted text.
        "worker.report_refused", None, ("attempted_tag", "text"), (ENGINE,), BLOCKING,
        "the door could not admit an attempted report — full text preserved, "
        "opens a case (R2/T3)"),
    "unclassified": Word(
        "unclassified", None, (), (WORKER, ARCHITECT, OPERATOR, ENGINE), None,
        "routes to the router's T4 catch-all, never a silent drop"),
}

# report.sh `--tag <verb>` -> canonical engine tag. Single source for
# `core/classify.py::verb_to_tag` (replaces the deleted, hand-maintained
# `_REPORT_VERB_TAG`/`_canonical_tag` pair, AC-1) AND for `scripts/
# report.sh`'s own generated legal-verb list (T2/T3, via `schema_dict`).
VERB_TO_TAG = {w.verb: tag for tag, w in TAGS.items() if w.verb}
# `clean` is the close clean-confirmation verb (worker-contract.md §3): a
# `done`/`clean` report on an already-✅ block is the close confirmation,
# the gate's own git-observed `replica_clean` is what actually advances —
# both resolve to the SAME `worker.done` tag (pre-existing behavior,
# ported verbatim, never forked).
VERB_TO_TAG["clean"] = "worker.done"
VERB_TO_TAG["review_done"] = "worker.review_done"   # underscore alias, pre-existing

# ── R5/T6 — slot-level class signals. A slot NOT listed here carries no
#    class of its own (free text / correlation ids are neutral — `detail`,
#    `triage_id`, `type`, `verdict`, `block`). Only a slot whose PRESENCE
#    independently asserts forward progress is listed: `branch` (declaring/
#    naming a branch is itself progress — the historical vector this
#    partition closes: a `--tag wall --branch <name>` report combining "I'm
#    blocked" with "here is my new branch" in one message is exactly the
#    kind of contradictory pair R5 makes illegal — an enumerated PARTITION
#    over every (tag-class, slot-class) pair, never just the one pair seen
#    live). Deliberately does NOT include `kind` — `--kind` is deleted
#    (T3: dead since ADR-0010/01-31 made every wall architect-first; no
#    live consumer in `core/*.py`). ──
SLOT_CLASS = {
    "branch": PROGRESS,
}

# `core/snapshot.py::_classify_reports` — the slot keys promoted to a
# resolved report's TOP LEVEL when the raw line didn't already carry one of
# its own (T9, lock 4 of the ADR-0011 four-lock verdict-wire closure,
# ported + generalized from the salvage `PROMOTED_SLOT_KEYS` constant).
# `block`/`agent_id` are wave-13's original two; `triage_id`/`verdict` are
# the verdict wire's own addition — without these two, `core/router.py::
# _route_architect_triage_verdict` reads `rep.get("triage_id")`/`rep.get(
# "verdict")` at TOP LEVEL and drops every real `report.sh --tag verdict`
# report as malformed.
PROMOTED_SLOT_KEYS = ("block", "agent_id", "triage_id", "verdict")

# `architect.triage_verdict`'s own closed verdict enum (T9) — single source
# for `core/router.py`/`core/architect.py`'s own membership checks.
TRIAGE_VERDICTS = ("scope_forward", "answer", "operator")

# ── R2 outbound — every `core/engine.py::emit` template id, as imported
#    constants (AC-6: "a typo fails at load time"). Mirrors `messages.
#    yaml`'s own template keys exactly (never re-authored) — the CLOSED set
#    `core/engine.py::emit` accepts; membership is checked BEFORE the
#    renderer is ever touched (that module's own docstring: an unknown id
#    raises even under a canon-less rig fixture, while a present-but-
#    unrenderable id still degrades to `fallback_text`, unchanged — two
#    different failure modes, never conflated). The emit-id lint (T5)
#    forbids a literal string at any `.emit(` call site — it must reference
#    one of these names instead. ──
TPL_SPAWN_WORKER = "spawn.worker"
TPL_ASSIGN_WORKER = "assign.worker"
TPL_ARCH_FORWARD = "arch.forward"
TPL_ARCH_RECONCILE = "arch.reconcile"
TPL_ARCH_REMEDIATION = "arch.remediation"
TPL_ARCH_TRIAGE = "arch.triage"
TPL_ARCH_FLAGS = "arch.flags"          # T7 — the batched visibility-flag digest
TPL_CLOSE_WORKER = "close.worker"
TPL_CLOSE_DIRTY = "close.dirty"
TPL_HEARTBEAT_PING = "heartbeat.ping"
TPL_GATE_LOCAL = "gate.local"
TPL_GATE_MERGE = "gate.merge"
TPL_GATE_TRUNK = "gate.trunk"
TPL_GATE_RECORD = "gate.record"
TPL_GATE_REVIEW = "gate.review"
TPL_TERMINAL_DISPATCHED = "terminal.dispatched"
TPL_TERMINAL_BLOCK_DONE = "terminal.block_done"
TPL_TERMINAL_REVIEW = "terminal.review"
TPL_TERMINAL_HALT_BOOTUP = "terminal.halt_bootup"
TPL_TERMINAL_HALT_TRUNK = "terminal.halt_trunk"
TPL_TERMINAL_PLAN_FIRST = "terminal.plan_first"
TPL_TERMINAL_SCOPE_UNKNOWN = "terminal.scope_unknown"
TPL_TERMINAL_RUN_CONTROL = "terminal.run_control"
# R8 (block 01-38 T2): the terminal floor — if the operator-page transport
# itself permanently fails, the run enters this NAMED terminal state
# (safe-park-and-halt, `core/casestate.py::_trip_safe_park`) with a full
# state snapshot, rather than "failing loudly into a log nobody reads".
TPL_TERMINAL_SAFE_PARK = "terminal.safe_park"
TPL_ESCALATE_WALL = "escalate.wall"
TPL_ESCALATE_AWAIT = "escalate.await"
TPL_ESCALATE_GATE = "escalate.gate"
TPL_ESCALATE_UNCLASSIFIED = "escalate.unclassified"
TPL_TG_ESCALATE = "tg.escalate"
TPL_TG_STATUS_DIGEST = "tg.status_digest"
TPL_SESSION_SCOPE = "session.scope"
TPL_SESSION_START = "session.start"
TPL_SESSION_END = "session.end"

EMIT_TEMPLATE_IDS = frozenset(v for k, v in list(vars().items())
                              if k.startswith("TPL_"))


class UnknownTemplateError(LookupError):
    """Raised by `core/engine.py::Engine.emit` when `template_id` is not a
    member of `EMIT_TEMPLATE_IDS` — a typo/removed template fails LOUD at
    the call, never a silent `fallback_text` substitution (ADR-0012 R2/T5).
    """


def verb_to_tag(verb):
    """`report.sh --tag <verb>` -> canonical engine tag, or `None` for an
    unknown verb (never guessed, never silently coerced — the caller's
    door refuses it). An ALREADY-namespaced tag (contains `.` — everything
    `core/*_rig.py`/`core/sim/worker.py` writes directly, and every
    structured line the engine mints internally) passes through unchanged,
    exactly like the retired `_canonical_tag`'s own contract."""
    if not verb:
        return None
    if "." in verb:
        return verb if verb in TAGS else None
    return VERB_TO_TAG.get(verb.strip().lower())


def resolve_origin(msg, architect_wid):
    """The closed set a report's origin resolves to — `worker` | `architect`
    | `operator` — or `None` if `msg` names none of them. `msg` is the FULL
    drained report dict (never just `sender`): a REAL `report.sh` line
    always writes `sender.kind: "worker"` (ADR-0011 S-1) — the architect is
    a worker-SHAPED sender whose `sender.id` is literally `architect_wid`,
    so origin is resolved by IDENTITY, never by `sender.kind` alone (a
    worker can never forge an architect-only tag just by knowing the shape
    — a real worker id is never reachable at that literal value, `core/
    switchboard.py`'s deterministic agent-id minting never produces it).
    A SCRIPTED report (every `core/*_rig.py` fixture, per `core/
    snapshot.py`'s own documented "IDENTITY BRIDGE" precedent) carries no
    `sender` dict at all — just a bare top-level `agent_id`/`worker_id` —
    which resolves to `worker` (or `architect`, on the architect's own id)
    the identical way; this is the SAME ambient identity `core/router.py`/
    `core/liveness.py` already trust, never a second convention."""
    sender = (msg or {}).get("sender") or {}
    kind = sender.get("kind")
    sid = sender.get("id") or (msg or {}).get("agent_id") or (msg or {}).get("worker_id")
    if kind == "operator":
        return OPERATOR
    if sid == architect_wid:
        return ARCHITECT
    if kind == "worker":
        return WORKER
    if sid:
        return WORKER
    # No identity marker of ANY kind (no `sender`, no `agent_id`/
    # `worker_id`) — the real door (`report.sh`) always stamps `sender.
    # kind: "worker"`, so the only way a report reaches here with zero
    # identity is a WORKER-legal-tag test fixture that never bothered to
    # name a sender (`worker.done`/`worker.recorded` are commonly reported
    # block-scoped, not worker-scoped — the gate's own `wid` resolves WHICH
    # worker). Default to WORKER rather than refuse: this default is NEVER
    # granted for an ARCHITECT/OPERATOR-only tag either way, since `minters_
    # ok` checks WORKER against THAT tag's own narrower declared set —
    # `architect.reconciled`/`architect.triage_verdict` still require
    # genuine architect identity (`sid == architect_wid`), the actual
    # impersonation surface ADR-0011 S-1 closes.
    return WORKER


def minters_ok(tag, msg, architect_wid):
    """True iff `msg`'s resolved origin (`resolve_origin`) is a legal
    minter of `tag` per its declared `minters` (ADR-0011 S-1, ported) — an
    origin NOT in a tag's `minters` never reaches the flow as that tag: a
    worker-shaped sender can never mint `architect.triage_verdict` just by
    knowing the shape. Unknown tag -> True (nothing to check; the caller's
    own tag-legality check already refuses it first)."""
    w = TAGS.get(tag)
    if w is None:
        return True
    return resolve_origin(msg, architect_wid) in w.minters


def word_class(tag):
    w = TAGS.get(tag)
    return w.cls if w else None


def classes_conflict(tag, slot_keys):
    """T6/AC-7: True iff `tag`'s own class and any of `slot_keys`' declared
    `SLOT_CLASS` disagree — the enumerated progress/blocking partition,
    checked over every (tag, slot) pair the schema can express, not just
    the one pair (`wall` + `branch`) seen live."""
    classes = set()
    tc = word_class(tag)
    if tc:
        classes.add(tc)
    for s in slot_keys:
        sc = SLOT_CLASS.get(s)
        if sc:
            classes.add(sc)
    return PROGRESS in classes and BLOCKING in classes


def report_door_tags():
    """The legal `--tag` verb set `scripts/report.sh`'s door validates
    against and prints on refusal (T3) — every tag with a report.sh-
    sendable verb, sorted for a stable, greppable refusal message."""
    return sorted(w.verb for w in TAGS.values() if w.verb)


def legal_slots(tag):
    w = TAGS.get(tag)
    return w.slots if w else ()


def legal_set_text():
    """Human-readable legal-tag listing for a door refusal (T3, AC-4) —
    generated from `TAGS`, never hand-maintained prose. Orchestrator-
    agnostic (no host-runtime name)."""
    lines = []
    for verb in report_door_tags():
        tag = VERB_TO_TAG[verb] if verb in VERB_TO_TAG else None
        w = TAGS.get(tag) if tag else None
        if w is None:
            continue
        slots = ", ".join(w.slots) or "(none)"
        lines.append(f"  --tag {w.verb}  slots: {slots}")
    return "\n".join(lines)


# ── T2 — the generated schema artifact (never hand-committed; materialized
#    fresh into every seeded instance by `core/sim/seed_canon.py::
#    install_canon`, and readable by any real seeder the same way — see
#    `write_schema`/`__main__` below). `scripts/report.sh` consumes this
#    exact shape via `jq` (never a second hand-maintained copy of the tag/
#    slot/verb set in bash). ──
def schema_dict():
    """A plain, JSON-serializable, DETERMINISTIC (sorted keys) dict — the
    single generated shape both `scripts/report.sh` (via `jq`) and the CI
    regen/diff gate (`engine/lint.py`, T2/AC-2) read. Never hand-edited;
    regenerated from `TAGS`/`VERSION` above on every call — no cached/
    mutable module state here to drift."""
    tags = {}
    for tag, w in sorted(TAGS.items()):
        tags[tag] = {
            "verb": w.verb,
            "slots": list(w.slots),
            "minters": list(w.minters),
            "class": w.cls,
        }
    return {
        "version": VERSION,
        "tags": tags,
        "verbs": sorted(VERB_TO_TAG),
        "templates": sorted(EMIT_TEMPLATE_IDS),
    }


def schema_json():
    """Canonical (sorted-key, stable-whitespace) JSON text — diffable
    byte-for-byte, the shape the CI regen/diff gate compares."""
    return json.dumps(schema_dict(), indent=2, sort_keys=True) + "\n"


def schema_diff(path):
    """T2/AC-2: `(ok, detail)` — `ok=False` iff the schema materialized at
    `path` differs, byte-for-byte, from a FRESH `schema_json()` regenerated
    right now from `core/vocab.py`'s own live `TAGS`/`VERSION`. This is the
    CI regen/diff gate's own predicate: a seeded instance's `vocab.schema.
    json` that has drifted from the source (hand-edited, or seeded under a
    since-changed `vocab.py` and never re-seeded) is caught here — RED on a
    seeded drift fixture, GREEN on a freshly-seeded tree (`core/sim/
    seed_canon.py::install_canon`'s own `write_schema` call, same call
    site every real seeder uses)."""
    if not os.path.isfile(path):
        return False, f"no schema file at {path!r}"
    with open(path) as fh:
        on_disk = fh.read()
    fresh = schema_json()
    if on_disk != fresh:
        return False, f"schema at {path!r} has DRIFTED from a fresh regen of core/vocab.py"
    return True, ""


def write_schema(path):
    """Materialize the generated schema at `path` (e.g. `<instance>/
    vocab.schema.json`) — the ONE write site every seeder (real or `core/
    sim/seed_canon.py`) calls; never copied from a static file on disk (T2:
    "generated at build, never hand-committed")."""
    with open(path, "w") as fh:
        fh.write(schema_json())
    return path


class HandshakeError(RuntimeError):
    """AC-3 — a spawn under a stale `vocab.version` fails loud. Never a
    silent fallback to an embedded copy."""


def check_handshake(schema_path, events=None):
    """T2's spawn handshake: read the SEEDED instance's own generated
    `vocab.schema.json` (materialized at seed time by `write_schema` above)
    and compare its `version` against THIS engine's live `VERSION`. A
    project seeded under an older/newer vocabulary meeting a different
    engine build fails loud (`HandshakeError`, uncaught — the caller, e.g.
    `core/engine.py::Engine.start`, lets it propagate) AND is counted (a
    must-be-zero event, `events.event(...)` when an `EventLog`-shaped sink
    is supplied) — never a silent fallback to a bundled/embedded copy of
    the schema.

    A MISSING schema file is treated as "this instance predates block
    01-37's door" (every pre-existing `core/*_rig.py`/`core/sim/*.py`
    fixture that seeds `meta/agents/tron/` its own way, never through
    `core/sim/seed_canon.py::install_canon`) — a SKIP, not a failure: a
    genuinely STALE project (T2's own concern) is one that WAS seeded
    under some vocabulary and stamped a version; "never seeded a schema at
    all" is a different, pre-block-01-37 shape this handshake does not
    retroactively fail every existing fixture over. A PRESENT-but-WRONG
    version is the real AC-3 case (a stale re-seed, or a corrupted/
    hand-edited schema) and fails loud exactly as documented above."""
    if not os.path.isfile(schema_path):
        return
    try:
        with open(schema_path) as fh:
            stamped = (json.load(fh) or {}).get("version")
    except (OSError, ValueError) as e:
        stamped = None
        err = str(e)
    else:
        err = None

    if stamped != VERSION:
        detail = (f"vocab version handshake FAILED: engine VERSION={VERSION!r}, "
                 f"instance schema version={stamped!r} at {schema_path!r}"
                 + (f" ({err})" if err else ""))
        if events is not None:
            events.event("must_be_zero", counter="vocab_version_handshake_failed",
                         engine_version=VERSION, instance_version=stamped,
                         schema_path=schema_path)
        raise HandshakeError(detail)


if __name__ == "__main__":
    import sys
    if "--schema" in sys.argv:
        sys.stdout.write(schema_json())
    elif "--write" in sys.argv:
        i = sys.argv.index("--write")
        dest = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
        if not dest:
            print("usage: python3 core/vocab.py --write <path>", file=sys.stderr)
            sys.exit(2)
        write_schema(dest)
        print(f"wrote {dest}")
    else:
        print("usage: python3 core/vocab.py [--schema | --write <path>]", file=sys.stderr)
        sys.exit(2)
