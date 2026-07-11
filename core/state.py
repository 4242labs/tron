"""core.state — the MANIFEST store: the payload-free durable run-state.

Single source of run-state persistence (contracts/blueprint-contracts.md §5's
tick model, rebuild-spec.md T1-B/B10): every tick LOADS the manifest fresh
from disk, mutates an in-memory copy across its one bounded pass
(`core/tick.py`), then PERSISTS ATOMICALLY at the very end — a `*.tmp`
sibling written and fsynced, then `os.replace`d over the live file, so the
live `manifest.yaml` is never left half-written and a crash mid-write never
corrupts it. State persists only AFTER a tick's whole pass completes (the
CALLER's discipline, not enforced here — this module just makes the write
itself atomic), so a tick that crashes before calling `save` leaves the
PRIOR manifest intact: the next wake reloads that same prior state and
safely re-derives forward (`core/gate.py`'s own git/grant-observed
predicates make re-running idempotent — see `core/tick_rig.py`'s
crash-replay proof).

Holds (by convention, opaque to this module — it never inspects the shape):
in-flight DONE-gate states keyed by block id, worker/slot records, cursors.
This is the ONLY module in `core/` that writes `ctx.state` (`manifest.yaml`)
— every other module (`core/tick.py`, `core/snapshot.py`, `core/gate.py`,
...) reads/mutates run-state exclusively through `load`/`save` here, never
opening the file itself. No git/subprocess of any kind lives in this module
— plain file IO only (the one exception `core/tick.py`'s own hard rules
carve out for this module's own manifest IO).
"""
import os
import tempfile

import yaml


def load(ctx):
    """Read `ctx.state` (`manifest.yaml`) fresh off disk. A missing file (a
    brand-new instance, never yet ticked) reads as `{}`, never an exception
    — the caller (`core/snapshot.py`'s `build`, the observe step) seeds
    whatever sections it needs via `dict.setdefault`. An EMPTY file
    (`yaml.safe_load` of empty text is `None`) also reads as `{}` rather
    than handing a tick a null payload."""
    if not os.path.exists(ctx.state):
        return {}
    with open(ctx.state, "r") as fh:
        return yaml.safe_load(fh) or {}


def save(ctx, manifest):
    """Atomically persist `manifest` to `ctx.state`: write a `*.tmp` sibling
    in the SAME directory (so the final rename is same-filesystem and
    therefore atomic), fsync it, then `os.replace` over the live file. Never
    a direct write to the live path — a reader (including a crash-replayed
    tick) always sees either the complete prior manifest or the complete new
    one, never a torn mix. The ONE call site in the whole `core/` stack that
    writes `ctx.state`."""
    d = os.path.dirname(os.path.abspath(ctx.state)) or "."
    os.makedirs(d, exist_ok=True)
    text = yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".manifest-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, ctx.state)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
