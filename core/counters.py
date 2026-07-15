"""core.counters — R4 counter partition (block 01-38 T9, AC-5a/5b).

`core/emit.py`'s registry already tags a handful of effects
`counter_class="must_be_zero"`. This module is the layer ABOVE that
registry that (1) names every individual counter R4 actually cares about —
not just the effect it rides on — and (2) reads the real event STREAM
(never manifest state — T7's events-as-ground-truth rule) to tally and
grade them.

WHY A NAMED-COUNTER LAYER OVER THE RAW EFFECT REGISTRY
-------------------------------------------------------
Two of `core/emit.py`'s must-be-zero EFFECTS are already one-counter-per-
effect (`engine_emit_missing_template_counted`, `router_catch_all_counted`).
The third, generic `must_be_zero` forensic effect is MULTIPLEXED: distinct
call sites (`core/vocab.py`'s handshake failure, `core/casestate.py`'s
permanent page-fail) share one effect *type* but name a distinct semantic
backstop in their own `counter=` payload field. Acceptance needs to read
and print each backstop BY NAME ("did the vocab handshake ever fail?" vs
"did a page ever permanently fail?") — collapsing them to one effect-level
tally would hide which backstop actually fired. `COUNTERS` below is the
ONE place that maps a named counter to how it is found in the event
stream; nothing downstream keeps a second hand-maintained copy.

THE MAY-FIRE ARM (declared, mechanism-proven, not yet populated)
-------------------------------------------------------------------
No `core/*.py` effect is classified `may_fire` yet as of T9 — every
counter live in the engine today is a must-be-zero backstop. The
PARTITION MECHANISM (declare a name + ceiling, tally it from the stream,
fail past the ceiling, always print the value) is nonetheless fully
implemented and mutation-proven here (`core/counters_rig.py` registers a
synthetic probe counter the same way `core/emit_rig.py`'s own R2b proves
the closed-registry check — a temporary table entry, removed in
`finally`) — so a future task (T10-T12's designed-rare backstops: a
bounded re-drive, a respawn ceiling, ...) only has to ADD an entry to
`COUNTERS` below; the grading/printing machinery is already live and
already proven.

APPEND-ONLY (R4/AC-5b)
-----------------------
`MUST_BE_ZERO_PINNED` is the must-be-zero NAME SET as of block 01-38 T9.
Adding a new must-be-zero counter later is always legal (a superset check).
Removing or renaming one of these names is an operator decision, never a
silent drop — `check_append_only()` (proven by `core/counters_rig.py`'s
`test:<counter_append_only_pinned>`) fails loud the moment any pinned name
is no longer present in the live `COUNTERS` table.
"""

MUST_BE_ZERO = "must_be_zero"
MAY_FIRE = "may_fire"
COUNTER_CLASSES = frozenset({MUST_BE_ZERO, MAY_FIRE})


class _Counter:
    __slots__ = ("name", "cls", "effect", "discriminator", "ceiling")

    def __init__(self, name, cls, effect, discriminator=None, ceiling=None):
        if cls not in COUNTER_CLASSES:
            raise ValueError(f"core.counters: {cls!r} is not a declared counter "
                             f"class ({sorted(COUNTER_CLASSES)})")
        if cls == MAY_FIRE and ceiling is None:
            raise ValueError(f"core.counters: may_fire counter {name!r} declared "
                             f"with no per-run ceiling — R4 requires one, never a "
                             f"silent unbounded backstop")
        self.name = name
        self.cls = cls
        self.effect = effect
        self.discriminator = discriminator   # None, or {payload_field: value} required
        self.ceiling = ceiling


# ── the ONE declared counter table (R4) ──
# must-be-zero: a primary path silently failing — acceptance reads these at
# zero. Every entry here as of T9 rides an effect already registered in
# `core/emit.py` with `counter_class="must_be_zero"` (or, for the
# multiplexed generic `must_be_zero` effect, a `discriminator` naming the
# specific `counter=` payload value that call site stamps).
_COUNTERS = (
    _Counter("emit_missing_template", MUST_BE_ZERO,
             "engine_emit_missing_template_counted"),
    _Counter("router_catch_all", MUST_BE_ZERO,
             "router_catch_all_counted"),
    _Counter("vocab_version_handshake_failed", MUST_BE_ZERO, "must_be_zero",
             discriminator={"counter": "vocab_version_handshake_failed"}),
    _Counter("operator_page_permanent_fail", MUST_BE_ZERO, "must_be_zero",
             discriminator={"counter": "operator_page_permanent_fail"}),
    # No may_fire entry yet — see module docstring. T10-T12 add real
    # designed-rare backstops here as they're built.
)

COUNTERS = {c.name: c for c in _COUNTERS}

MUST_BE_ZERO_PINNED = frozenset({
    "emit_missing_template",
    "router_catch_all",
    "vocab_version_handshake_failed",
    "operator_page_permanent_fail",
})


def must_be_zero_names():
    return frozenset(c.name for c in COUNTERS.values() if c.cls == MUST_BE_ZERO)


def may_fire_names():
    return frozenset(c.name for c in COUNTERS.values() if c.cls == MAY_FIRE)


def check_append_only():
    """R4/AC-5b — the pin. `(ok, missing)`: `missing` names any PINNED
    must-be-zero counter no longer present in the live table (a silent
    removal/rename); `ok` is `not missing`. Adding a new counter never
    trips this — only the pinned set must remain a SUBSET of the live set."""
    missing = MUST_BE_ZERO_PINNED - must_be_zero_names()
    return (not missing), missing


def _matches(event, counter):
    if not isinstance(event, dict) or event.get("type") != counter.effect:
        return False
    if counter.discriminator is None:
        return True
    payload = event.get("payload") or {}
    return all(payload.get(k) == v for k, v in counter.discriminator.items())


def tally(events):
    """`events` — an iterable of `{"type", "payload"}` dicts, the shape
    every `core/emit.py` write already produces on `eng.events`/an
    `EventLog` (T7's events-as-ground-truth spine — never manifest state).
    Returns `{counter_name: count}` for EVERY declared counter (0 if it
    never fired — an absent counter would be indistinguishable from "never
    checked")."""
    counts = {name: 0 for name in COUNTERS}
    for e in events:
        for c in COUNTERS.values():
            if _matches(e, c):
                counts[c.name] += 1
    return counts


def evaluate(events):
    """R4/AC-5a — the acceptance read. Returns `(ok, lines, reasons)`:
      • every must-be-zero counter must tally to exactly 0 — a nonzero
        firing is a REJECT reason;
      • every may-fire counter is ALWAYS printed with its value (not only
        on failure); a count past its declared ceiling is ALSO a REJECT
        reason.
    `ok` is True iff no must-be-zero counter fired and no may-fire counter
    breached its ceiling. `lines` is the full printed report (every counter,
    both classes, always) a caller can log verbatim."""
    counts = tally(events)
    lines, reasons = [], []
    for name in sorted(must_be_zero_names()):
        n = counts[name]
        lines.append(f"must-be-zero: {name}={n}")
        if n:
            reasons.append(f"must-be-zero counter {name!r} fired {n} time(s) — "
                           f"a primary path silently failed")
    for name in sorted(may_fire_names()):
        n = counts[name]
        ceiling = COUNTERS[name].ceiling
        lines.append(f"may-fire: {name}={n} (ceiling={ceiling})")
        if ceiling is not None and n > ceiling:
            reasons.append(f"may-fire counter {name!r} fired {n} time(s), past its "
                           f"declared per-run ceiling of {ceiling}")
    return (not reasons), lines, reasons
