"""core.sim.launch — `python3 -m core.sim.launch`: the ONE-COMMAND L3
launcher (wave 15). Points `core.engine.Engine` at an already-SEEDED TRON
instance dir (`project.yaml` + `knobs.yaml` present — the SAME shape a real
`tron seeder` run leaves at `<project>/meta/agents/tron/`, exactly `engine.
ctx.Ctx`'s own contract; this CLI never seeds/invents one itself), builds
`Engine(ctx)`, and boots it — the headless bootup shape learned from `tron-
meta/sims/autopilot/bootstrap.py`'s `LAUNCHER_TEMPLATE` (construct -> check
no session is already live -> boot -> report), re-expressed over `core.
engine.Engine` instead of the legacy `fsm.Engine`.

Safety-first, per this wave's hard rule (no real-LLM fleet get spawned by
this brick): `--dry-boot` is the DEFAULT. Under it, `engine.jobs.spawn_runner`
is monkeypatched to the SAME "record, never spawn" no-op every `core/
*_rig.py` / `core.sim.run`'s own scripted tier already uses — `Engine.start()`
still runs for REAL (manifest write, architect-spawn call recorded, the
first SWITCHBOARD dispatch), but ZERO OS processes and ZERO LLM calls happen
anywhere. This CLI then STOPS — no tick loop, no fleet, no `--tier` wiring
touched at all.

An explicit `--no-dry-boot` (paired with `--tier {echo, host-cli}` — never
`scripted`, which has no real `spawn_runner` call to make) reaches `core.sim.
real_tier.install`, wiring `Engine`'s spawn hooks to the REAL `engine.jobs.
spawn_runner` (a REAL `worker_runner.py` OS process per spawn; `--tier
host-cli` additionally drives a real `claude` session — the ONLY path in
this entire module that can ever do that, and ONLY when a caller explicitly
opts OUT of the default safety rail). This wave NEVER invokes `--no-dry-boot
--tier host-cli` itself (hard rule: no real-LLM fleet in this wave) — the
flag exists purely so a LATER, carefully-monitored L3 step is one command,
per this brick's own charter.

This CLI never runs a tick loop of its own (`Engine.tick()`/`.run()`) — its
job ends at boot; a caller (a later driver, or a rig) takes the returned
`Engine` from there if it wants to."""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app worktree root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
# Same unconditional ordering every other core/sim/*.py module in this wave
# keeps (engine dir first, then core dir — core dir must win on the bare
# name "engine" for `from engine import Engine` below to resolve to core/
# engine.py, never engine/engine.py's own CLI script).
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import jobs                       # noqa: E402 — engine/jobs.py
from ctx import Ctx                # noqa: E402 — engine/ctx.py
from engine import Engine, BootupError   # noqa: E402 — core/engine.py, THE MODULE this launches

import real_tier                    # noqa: E402 — core/sim/real_tier.py, the real-spawn wrapper

TIERS = ("scripted", "echo", "host-cli")


class LaunchError(ValueError):
    """Bad CLI input / a refusal this launcher itself owns — fails loud,
    never a silent best-effort guess (mirrors `bootstrap.BootstrapRefusal`'s
    own discipline for the legacy launcher)."""


def _stub_spawn_runner(worker_id, worker_dir, session_id, cwd=None,
                       runtime=None, adapter=None, model=None, settle_s=2.0):
    return {}


def build_parser():
    ap = argparse.ArgumentParser(
        prog="python3 -m core.sim.launch",
        description="L3 one-command launcher: point core.engine.Engine at an "
                    "already-seeded TRON instance dir and boot it. Safety-"
                    "first: --dry-boot (construct+bootup only, spawn stubbed) "
                    "is the DEFAULT; a real fleet needs an explicit "
                    "--no-dry-boot.")
    ap.add_argument("--scaffold", required=True,
                    help="path to the SEEDED TRON instance dir (project.yaml "
                        "+ knobs.yaml present — engine.ctx.Ctx's own "
                        "contract); this launcher never seeds one itself")
    ap.add_argument("--tier", choices=TIERS, default="scripted",
                    help="spawn tier for a REAL run (only takes effect under "
                        "--no-dry-boot; ignored under the default --dry-boot, "
                        "where spawn is always stubbed regardless)")
    ap.add_argument("--scope", default="all",
                    help='"all" (default) or a comma-separated list of block ids')
    ap.add_argument("--workers", type=int, default=1, dest="worker_count")
    ap.add_argument("--budget-min", type=float, default=None, dest="budget_min",
                    help="informational only in this wave — no tick loop runs "
                        "here (a later wave's live driver owns enforcing it)")
    dry = ap.add_mutually_exclusive_group()
    dry.add_argument("--dry-boot", dest="dry_boot", action="store_true", default=True,
                     help="(DEFAULT) construct + bootup only, spawn stubbed, then stop")
    dry.add_argument("--no-dry-boot", dest="dry_boot", action="store_false",
                     help="EXPLICIT opt-out, required to reach a real spawn "
                         "tier — pass --tier echo/host-cli alongside it; "
                         "NEVER pass --tier host-cli here except for a later, "
                         "carefully-monitored real L3 step")
    return ap


def _parse_scope(scope):
    if scope in (None, "", "all"):
        return "all"
    return [s.strip() for s in scope.split(",") if s.strip()]


def launch(scaffold, tier="scripted", scope="all", worker_count=1, budget_min=None,
          dry_boot=True):
    """Build `Engine(Ctx(scaffold))` and boot it (`Engine.start`). Returns a
    result dict: `{ctx, eng, spawned_at_boot, dry_boot, tier, real_spawn,
    real_spawn_calls}`. `real_spawn` is the `core.sim.real_tier.real_spawn`
    instance left INSTALLED (never auto-restored) when `dry_boot=False` — the
    caller owns its lifetime beyond bootup (call `.teardown()` then
    `.__exit__(None, None, None)` once done), exactly like a live deployment
    owns its own fleet past the launcher's own one-shot job. `None` under
    `dry_boot=True` (nothing real was ever installed to restore).

    Never runs a tick loop itself — see module docstring."""
    if not os.path.isdir(scaffold):
        raise LaunchError(f"core.sim.launch: --scaffold {scaffold!r} is not a directory")
    project_yaml = os.path.join(scaffold, "project.yaml")
    if not os.path.exists(project_yaml):
        raise LaunchError(
            f"core.sim.launch: no project.yaml at {project_yaml!r} — --scaffold "
            "must point at an already-SEEDED TRON instance dir (this launcher "
            "never seeds one itself); run the real `tron seeder` (or a rig's "
            "own equivalent construction) first")

    if tier not in TIERS:
        raise LaunchError(f"core.sim.launch: --tier {tier!r} not in {TIERS!r}")
    if tier == "scripted" and not dry_boot:
        raise LaunchError(
            "core.sim.launch: --tier scripted has no real spawn_runner call to "
            "make — pair --no-dry-boot with --tier echo/host-cli, or drop "
            "--no-dry-boot")

    ctx = Ctx(scaffold)
    eng = Engine(ctx)
    eng.dry = False   # real trunk observation throughout, matching every core/*_rig.py

    real_spawn = None
    real_spawn_runner = jobs.spawn_runner
    if dry_boot:
        jobs.spawn_runner = _stub_spawn_runner
    else:
        # HARD RULE (this wave): the caller has explicitly opted OUT of the
        # default safety rail — this module enforces nothing further beyond
        # that explicit `--no-dry-boot` (a later, carefully-monitored step
        # owns the operational guardrails around an ACTUAL host-cli run).
        real_spawn = real_tier.real_spawn(adapter=tier)
        real_spawn.__enter__()

    try:
        spawned_at_boot = eng.start(scope=_parse_scope(scope), worker_count=worker_count,
                                    models={})
    finally:
        if dry_boot:
            jobs.spawn_runner = real_spawn_runner
        # a real tier's wrapper is left installed on return — see docstring.

    return {
        "ctx": ctx, "eng": eng, "spawned_at_boot": spawned_at_boot,
        "dry_boot": dry_boot, "tier": tier,
        "real_spawn": real_spawn,
        "real_spawn_calls": (real_spawn.spawn_calls if real_spawn else []),
    }


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = launch(args.scaffold, tier=args.tier, scope=args.scope,
                        worker_count=args.worker_count, budget_min=args.budget_min,
                        dry_boot=args.dry_boot)
    except (LaunchError, BootupError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    print(f"OK dry_boot={result['dry_boot']} tier={result['tier']} "
         f"spawned_at_boot={result['spawned_at_boot']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
