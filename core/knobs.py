"""core.knobs — the ONE seam every `core/*.py` module reads `knobs.yaml`
through (wave 16, ADR tenet 1: no silent defaults). `contracts/schema/
knobs.schema.yaml` (READ, never edited, by this module) nests
`worker_count`/`architect_count`/`git`/`silence_ping_min`/
`silence_escalate_min`/`wake_cooldown_sec`/`wake_ceiling_sec`/
`abandon_flag_window`/`carve_liveness_timeout`/`grant_ttl` under a
top-level `knobs:` map; `cadence:` and `peer_consults:` are their OWN
top-level blocks, siblings of `knobs:`, never nested under it.

## The bug this seam fixes (wave 15, caught on the REAL scaffold)

`core/engine.py::_knobs`, `core/liveness.py::_silence_knobs`, `core/
reviewers.py::_cadence_cfg` used to read `ctx.load_knobs()`'s TOP LEVEL
directly. `cadence` happens to already live at the top level (no bug
there) and `grant_ttl`'s old `.get("grant_ttl", 60)` call coincidentally
degraded to its own hardcoded fallback — but `silence_ping_min`/
`silence_escalate_min` live NESTED under `knobs:` on every real,
schema-compliant `knobs.yaml`, so those two silently read as `None` even
when the project declares them, and `core/liveness.py::sweep` — by its
own documented design, "absent -> no-op" — never pinged or escalated a
silent worker on a real project AT ALL. No module below this one may read
`ctx.load_knobs()`'s shape itself any more; every knob read funnels
through `load()`/`Knobs` here instead.

## FAIL-LOUD vs documented-default (the schema's own words)

`knobs:` itself is the ONE top-level map the schema marks REQUIRED once a
`knobs.yaml` FILE exists at all — a file that ships FLAT (no `knobs:`
wrapper) is the exact wave-15 regression shape one level up, so ITS
absence (given the file exists) is a fail-loud `KnobsError`, never quietly
read as `{}` (that silent read is the bug reborn). Within `knobs:`,
`worker_count` is the schema's own explicit "REQUIRED key" annotation
(its VALUE may be `null` — the operator is asked at session start — but
the KEY itself must be present). Every other `knobs:` field carries a
literal schema-documented default value (the schema file's own literal
example values ARE the canon defaults, cross-checked against `engine/
fsm.py`'s identical `.get(key, default)` call sites and the canon `knobs.
yaml`/real `trivial-tip-converter` scaffold's own knobs.yaml, which stage
these same numbers explicitly rather than silently riding them) — when a
field is absent, its typed accessor below returns that documented default
EXPLICITLY, never a bare `None`.

`cadence:` (schema: "REQUIRED (may be empty {})") and `peer_consults:`
(schema: "OPTIONAL ... empty by default") are read leniently: an absent
`cadence:`/`peer_consults:` block carries the exact SAME meaning as an
empty one ("no reviewer type configured" / "no peer-consult pairs") —
there is no information an empty-vs-absent distinction would preserve
here, so this is a genuine equivalence, never a masked bug the way
`silence_ping_min`/`silence_escalate_min` resolving to `None` instead of
their declared value was.

## "No `knobs.yaml` file at all" — the established, unrelated convention

A project shipping NO `knobs.yaml` at all (every `core/*_rig.py` before
this wave that never seeds one) reads as "nothing configured": every
OPTIONAL accessor below still resolves its documented default (there is
no OTHER default to fall back to — identical to a present-but-key-absent
read), `cadence`/`peer_consults` read empty. This is the SAME "missing
file -> nothing configured" guard `core/engine.py::_knobs`/`core/
liveness.py::_silence_knobs`/`core/reviewers.py::_cadence_cfg` already
kept before this wave, preserved here verbatim so none of those
knobs.yaml-less rigs change behavior one bit.

## `Knobs.declared(name)` — liveness's own opt-in, preserved as-is

`core/liveness.py::sweep`'s silence ladder is OPT-IN by its own documented
design (that module's docstring, unchanged by this wave): a project that
ships a `knobs.yaml` configuring OTHER knobs only (`core/reviewers_rig.
py`'s own `cadence:`-only fixture, nested-schema-compliant post this wave,
is the precedent this seam exists to keep working) must keep reading as
"no silence knobs configured", never silently activated by this seam's
OWN new schema-default fallback (that fallback is for genuinely-defaulted
VALUES like `grant_ttl`, never for "should this whole ladder even run"
decisions the schema itself is silent on). `declared(name)` answers "does
the raw nested `knobs:` map literally carry this key" — `core/liveness.py`
consults it before ever reading the value-with-default accessor,
reproducing its pre-wave-16 "absent key -> None -> no-op" contract exactly,
now correctly checked at the NESTED location instead of the buggy flat
one."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


class KnobsError(Exception):
    """A `knobs.yaml` FILE exists but violates the schema (`contracts/
    schema/knobs.schema.yaml`): a missing REQUIRED top-level `knobs:` map
    (the flat-knobs-file shape — the wave-15 regression, one level up), or
    a missing REQUIRED `worker_count` key inside it. Raised, never a
    silent default — the exact discipline the nesting bug violated."""


# `contracts/schema/knobs.schema.yaml`'s own literal default values for
# every OPTIONAL `knobs:` field (cross-checked against `engine/fsm.py`'s
# identical `.get(key, default)` call sites + the canon `knobs.yaml`/real
# `trivial-tip-converter` scaffold's own knobs.yaml).
_OPTIONAL_DEFAULTS = {
    "architect_count": 1,
    "git": "on",
    "silence_ping_min": 6,
    "silence_escalate_min": 8,
    "wake_cooldown_sec": 5,
    "wake_ceiling_sec": 30,
    "abandon_flag_window": 60,
    "carve_liveness_timeout": 300,
    "grant_ttl": 60,
    # Wave 19 (GAP-C, fleet-outage self-release): consecutive fleet-wide
    # worker spawn-then-immediate-death events (`core/switchboard.py::fill`'s
    # own counter, `manifest["fleet"]["consecutive_deaths"]`, reset on any
    # successful spawn) before the engine self-releases (pause dispatch +
    # architect-first escalation). Distinct from `silence_ping_min`/
    # `silence_escalate_min` (a SINGLE worker's time-based silence, `core/
    # liveness.py`'s own ladder) — this is a SYNCHRONOUS spawn-time failure
    # count across the whole fleet, never a timeout. NOT added to `contracts/
    # schema/knobs.schema.yaml` (a contract file, off limits per this wave's
    # hard rule) — an OPTIONAL knob exactly like `grant_ttl` above, this
    # module's own literal default is the canon value until the schema is
    # updated by a later wave that owns contract edits.
    "fleet_outage_deaths": 3,
}
# The schema's own explicit "REQUIRED key" annotation — the ONLY `knobs:`
# field whose ABSENCE (given the `knobs:` map itself is present) is a
# fail-loud error rather than a documented default.
_REQUIRED_KNOB_KEYS = ("worker_count",)


class Knobs:
    """Typed, schema-honoring access onto ONE `knobs.yaml` read. Never
    constructed directly by a caller other than `load()` below."""

    def __init__(self, raw_knobs, cadence, peer_consults):
        self._raw = dict(raw_knobs or {})
        self._cadence = dict(cadence or {})
        self._peer_consults = list(peer_consults or [])

    def declared(self, name):
        """Whether `name` literally appears as a key under the nested
        `knobs:` map this instance was built from — never confused with
        "resolves to a truthy value" (a declared `false`/`0`/`null` is
        still declared)."""
        return name in self._raw

    def _get(self, name):
        if name in self._raw:
            return self._raw[name]
        if name in _OPTIONAL_DEFAULTS:
            return _OPTIONAL_DEFAULTS[name]
        raise KnobsError(
            f"knobs.yaml: required knob {name!r} missing under the "
            f"top-level `knobs:` map (contracts/schema/knobs.schema.yaml)")

    # ── typed accessors (contracts/schema/knobs.schema.yaml's own `knobs:` fields) ──
    @property
    def worker_count(self):
        """REQUIRED key (schema's own words) — value may be `None` (the
        operator is asked at session start); the KEY itself is guaranteed
        present by `load()` whenever a `knobs.yaml` file exists at all."""
        return self._get("worker_count")

    @property
    def architect_count(self):
        return int(self._get("architect_count"))

    @property
    def git(self):
        return self._get("git")

    @property
    def silence_ping_min(self):
        return int(self._get("silence_ping_min"))

    @property
    def silence_escalate_min(self):
        return int(self._get("silence_escalate_min"))

    @property
    def wake_cooldown_sec(self):
        return float(self._get("wake_cooldown_sec"))

    @property
    def wake_ceiling_sec(self):
        return float(self._get("wake_ceiling_sec"))

    @property
    def abandon_flag_window(self):
        return int(self._get("abandon_flag_window"))

    @property
    def carve_liveness_timeout(self):
        return float(self._get("carve_liveness_timeout"))

    @property
    def grant_ttl(self):
        return float(self._get("grant_ttl"))

    @property
    def fleet_outage_deaths(self):
        """Wave 19 (GAP-C) — see `_OPTIONAL_DEFAULTS`'s own comment above."""
        return int(self._get("fleet_outage_deaths"))

    # ── `cadence:` / `peer_consults:` — own top-level blocks, siblings of `knobs:` ──
    @property
    def cadence(self):
        return dict(self._cadence)

    @property
    def peer_consults(self):
        return list(self._peer_consults)


_EMPTY = Knobs({}, {}, [])   # the "no knobs.yaml file at all" read — see module docstring


def load(ctx):
    """`Knobs`, read fresh off `ctx.knobs_file` (`engine/ctx.py::Ctx.
    load_knobs`, the ONE existing loader this seam delegates the actual
    file IO to — never a second `yaml.safe_load` of this module's own).

    A project shipping NO `knobs.yaml` at all reads as "nothing
    configured" (module docstring) — every OPTIONAL accessor still
    resolves its documented default, `cadence`/`peer_consults` read
    empty, `worker_count`/every other REQUIRED-in-principle field is
    simply never asked for by any of this stack's no-knobs-file rigs.

    A `knobs.yaml` FILE that DOES exist is validated against the schema
    shape (`contracts/schema/knobs.schema.yaml`) — see `KnobsError`
    above for exactly which violations raise."""
    path = getattr(ctx, "knobs_file", None)
    if not path or not os.path.exists(path):
        return _EMPTY

    doc = ctx.load_knobs() or {}
    if not isinstance(doc, dict):
        raise KnobsError(
            f"knobs.yaml: top-level document must be a mapping, got "
            f"{type(doc).__name__}")

    if "knobs" not in doc:
        raise KnobsError(
            "knobs.yaml: missing the REQUIRED top-level `knobs:` map "
            "(contracts/schema/knobs.schema.yaml) — a FLAT (unnested) "
            "knobs.yaml is the exact wave-15 regression shape this seam "
            "exists to catch; never silently read as `{}`.")
    raw_knobs = doc["knobs"]
    if not isinstance(raw_knobs, dict):
        raise KnobsError(
            f"knobs.yaml: top-level `knobs:` must be a mapping, got "
            f"{type(raw_knobs).__name__}")

    for key in _REQUIRED_KNOB_KEYS:
        if key not in raw_knobs:
            raise KnobsError(
                f"knobs.yaml: `knobs:` map missing the REQUIRED key "
                f"{key!r} (contracts/schema/knobs.schema.yaml)")

    cadence = doc.get("cadence") or {}
    if not isinstance(cadence, dict):
        raise KnobsError(
            f"knobs.yaml: top-level `cadence:` must be a mapping, got "
            f"{type(cadence).__name__}")

    peer_consults = doc.get("peer_consults") or []
    if not isinstance(peer_consults, list):
        raise KnobsError(
            f"knobs.yaml: top-level `peer_consults:` must be a list, got "
            f"{type(peer_consults).__name__}")

    return Knobs(raw_knobs, cadence, peer_consults)
