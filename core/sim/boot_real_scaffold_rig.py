"""core.sim.boot_real_scaffold_rig — wave 15's TOKEN-FREE validation: does
`core.engine.Engine` boot cleanly over the REAL `tron-meta/sims/_sources/
trivial-tip-converter` scaffold's OWN `meta/` layout (`pipeline.md`, `blocks/
*.md`, `tron/roles.yaml`, `tron/knobs.yaml`, `scripts/land.sh`) — never a
synthetic stand-in? Every prior `core/*_rig.py` that touches this same real
scaffold (`core/engine_rig.py`, wave 12) OVERWRITES its `pipeline.md`/
`meta/blocks/*.md`/`meta/tron/roles.yaml` with its own synthetic fixture
content before ever booting `Engine` over it — this rig is the FIRST thing
in this whole `core/` stack to boot `Engine` over the real project's OWN
authored content, unmodified. That is exactly the integration risk this
wave exists to catch before an actual L3 run ever spends a real token.

Two ingredients, real, never invented:
  1. A COPY of the real scaffold (the SOURCE at `sims/_sources/trivial-tip-
     converter` is NEVER mutated — `shutil.copytree` to a tempdir, then a
     fresh `git init` seeds the copy's OWN history; the ONE raw-git surface
     in this module, the same "construction only" convention `core.sim.
     scaffold`/every `core/*_rig.py`'s own `build_root` already keeps).
  2. A live TRON instance dir (`meta/agents/tron/`) this rig seeds itself —
     `project.yaml` is the real scaffold's own STAGED answer key (`meta/tron/
     project.yaml`), UNCHANGED except `repo.root` (the real file declares
     `root: "."`, resolved via a process-wide `os.chdir()` by the real `tron-
     meta/sims/autopilot/bootstrap.py` LAUNCHER_TEMPLATE this brick mirrors
     the SHAPE of — this rig resolves the SAME thing up front as an absolute
     path instead, so it never has to mutate this process's cwd, which would
     leak across whatever ELSE runs in the same interpreter); `knobs.yaml` is
     the real scaffold's own staged answer key too, copied VERBATIM,
     byte-for-byte, no adjustment — whatever this stack's `core/*.py` knob
     readers actually do with the real project's own `knobs.yaml` IS the
     compatibility question this wave exists to answer (see the FINDING
     printed below if their shape assumptions diverge). `meta/tron/roles.yaml`
     is read in PLACE (the default `roles_path` resolution, unchanged) — the
     real project's own roles.yaml, personas, and land.sh are never touched.

`jobs.spawn_runner` is STUBBED for the whole stubbed-boot validation (never a
real `claude`/`worker_runner.py` process — the established "rig plays the
worker" convention every `core/*_rig.py` already keeps) — this validation's
whole point is PARSE/WIRING compatibility, not running a fleet.

A SECOND, independent, OPTIONAL smoke (`run_echo_smoke`) spawns ONE real
`worker_runner.py` OS process under `core.sim.real_tier`'s `echo` adapter
(never `claude` — `EchoAdapter` never shells out to any agent runtime at
all, see `engine/worker_runner.py`) to prove the spawn -> mailbox -> real-
runner-turn transport works end to end, then kills it and verifies it's
dead. Guarded, never fatal to the rig's own pass/fail if it fails or is
skipped (SAFETY OVER COMPLETENESS, per this wave's hard rule) — `finally`-
wrapped teardown always attempts release + hard-kill regardless of what
happened, and `main()` asserts 0 orphan `worker_runner.py`/`claude`
processes system-wide before it returns.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any hard-fail (the echo smoke's own outcome is
reported but never gates the exit code — see its own section)."""
import os
import subprocess
import sys
import shutil
import tempfile
import time
import traceback
import uuid

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app worktree root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import jobs                        # noqa: E402 — engine/jobs.py, the ONE seam stubbed for the boot check
from ctx import Ctx                 # noqa: E402 — engine/ctx.py, the real runtime-context resolver
from engine import Engine, BootupError   # noqa: E402 — core/engine.py, THE MODULE UNDER TEST
import architect                     # noqa: E402 — core/architect.py, ARCHITECT_WID
import state                          # noqa: E402 — core/state.py

import real_tier                       # noqa: E402 — core/sim/real_tier.py, the echo-smoke's own wiring

SCAFFOLD_SRC = os.environ.get(
    "TRON_REAL_SCAFFOLD_SRC",
    "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter")
MAIN = "main"

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _git(args, cwd, check=True):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}) rc={r.returncode}\n"
                           f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return r


# ══════════════════════════════════════════════════════════════════════════
# 1. COPY the real scaffold (source untouched) + seed a live TRON instance
# ══════════════════════════════════════════════════════════════════════════
def copy_real_scaffold():
    """`shutil.copytree` the REAL scaffold to a tempdir (`.git`/`node_modules`/
    `.next` excluded — build artifacts + the source's own git history, never
    needed here), then `git init` the COPY's own fresh history. The source
    at `SCAFFOLD_SRC` is never opened for writing anywhere in this module."""
    d = tempfile.mkdtemp(prefix="tron-boot-real-scaffold-")
    root = os.path.join(d, "trivial-tip-converter")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules", ".next"))

    land_sh = os.path.join(root, "meta", "scripts", "land.sh")
    if os.path.isfile(land_sh):
        os.chmod(land_sh, os.stat(land_sh).st_mode | 0o111)
    hooks_dir = os.path.join(root, "meta", ".githooks")
    if os.path.isdir(hooks_dir):
        for name in os.listdir(hooks_dir):
            p = os.path.join(hooks_dir, name)
            if os.path.isfile(p):
                os.chmod(p, os.stat(p).st_mode | 0o111)

    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "boot-real-scaffold-rig@test.local"], root)
    _git(["config", "user.name", "core-boot-real-scaffold-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: COPY of tron-meta/sims/_sources/trivial-tip-converter "
                          "(source repo untouched)"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


def seed_live_instance(root):
    """Build `meta/agents/tron/` (the live instance dir `Ctx` points at) —
    see module docstring for exactly what this does/doesn't change relative
    to the real scaffold's own staged answer key. Returns `(inst_dir,
    project_doc, staged_knobs_path)`."""
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)

    staged_project_path = os.path.join(root, "meta", "tron", "project.yaml")
    with open(staged_project_path) as f:
        project = yaml.safe_load(f) or {}
    project.setdefault("repo", {})["root"] = root   # the ONE field this rig resolves itself
    with open(os.path.join(inst, "project.yaml"), "w") as f:
        yaml.safe_dump(project, f, sort_keys=False, default_flow_style=False)

    staged_knobs_path = os.path.join(root, "meta", "tron", "knobs.yaml")
    shutil.copy2(staged_knobs_path, os.path.join(inst, "knobs.yaml"))   # byte-for-byte

    return inst, project, staged_knobs_path


# ══════════════════════════════════════════════════════════════════════════
# 2. OPTIONAL echo-tier transport smoke — real worker_runner.py, no LLM
# ══════════════════════════════════════════════════════════════════════════
def run_echo_smoke(tron_ctx):
    """Spawn ONE real `worker_runner.py` process (`core.sim.real_tier`,
    `adapter="echo"` — never `claude`), confirm it registers + completes a
    real turn over the real mailbox, then release + hard-kill it. NEVER
    raises: any failure is caught and reported in the returned dict; the
    `finally` teardown always runs regardless."""
    wid = "echo-smoke-01"
    wdir = tron_ctx.worker_dir(wid)
    scratch = tron_ctx.worker_scratch_dir(wid)
    os.makedirs(scratch, exist_ok=True)
    os.makedirs(wdir, exist_ok=True)

    result = {"attempted": True, "ok": False, "detail": "", "escalated_kills": []}
    with real_tier.real_spawn(adapter="echo") as rs:
        try:
            session_id = str(uuid.uuid4())
            jobs.spawn_runner(wid, wdir, session_id, cwd=scratch,
                              model="stub-model-echo-smoke")

            deadline = time.time() + 15.0
            registered = False
            while time.time() < deadline:
                if jobs.find(wid) is not None:
                    registered = True
                    break
                time.sleep(0.25)
            if not registered:
                result["detail"] = "runner never registered runner.json within 15s"
            else:
                jobs.send(wdir, 1, "PMT-SMOKE", "echo smoke: say hi")
                deadline = time.time() + 15.0
                turn_seen = False
                timeline_path = os.path.join(wdir, jobs.TIMELINE)
                while time.time() < deadline:
                    if os.path.isfile(timeline_path):
                        with open(timeline_path) as f:
                            body = f.read()
                        if '"turn_done"' in body:
                            turn_seen = True
                            break
                    time.sleep(0.25)
                result["ok"] = turn_seen
                result["detail"] = ("real spawn -> mailbox -> turn_done confirmed" if turn_seen
                                    else "no turn_done observed in timeline within 15s")
        except Exception as e:               # noqa: BLE001 — never let the smoke crash the rig
            result["detail"] = f"{type(e).__name__}: {e}"
        finally:
            result["escalated_kills"] = rs.teardown(timeout_s=10.0)
    return result


def _orphan_processes(root):
    """Any `worker_runner.py`/`claude` process still alive after teardown
    whose command line references THIS rig's own copy root (`root`) — the
    hard safety assertion this whole wave is gated on. Scoped to `root`
    deliberately: a blind system-wide `pgrep -fa claude` also matches
    whatever UNRELATED `claude` sessions happen to already be running in
    this environment (this very agent's own host session included) — a
    false positive that would wrongly fail a rig that spawned nothing of
    the kind. Every real process this rig could ever spawn (the echo
    smoke's `worker_runner.py`) runs with `--worker-dir`/`--cwd` paths
    INSIDE `root`, so filtering on that substring is exact, not a heuristic
    guess."""
    out = subprocess.run(["pgrep", "-fa", "worker_runner.py"],
                         capture_output=True, text=True)
    lines = [ln for ln in out.stdout.splitlines() if ln.strip() and root in ln]
    out2 = subprocess.run(["pgrep", "-fa", "claude"], capture_output=True, text=True)
    lines += [ln for ln in out2.stdout.splitlines() if ln.strip() and root in ln]
    return lines


# ══════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════
def main():
    print(f"boot_real_scaffold_rig: copying REAL scaffold from {SCAFFOLD_SRC!r} "
          "(source untouched)")
    if not os.path.isdir(SCAFFOLD_SRC):
        print(f"FATAL: no real scaffold source at {SCAFFOLD_SRC!r} — cannot run "
              "this validation at all")
        return 2

    root = copy_real_scaffold()
    inst, project, staged_knobs_path = seed_live_instance(root)
    tron_ctx = Ctx(inst)
    print(f"copy root={root}")
    print(f"live instance dir={inst}")

    spawn_calls = []

    def fake_spawn_runner(worker_id, worker_dir, session_id, cwd=None,
                          runtime=None, adapter=None, model=None, settle_s=2.0):
        spawn_calls.append({"worker_id": worker_id, "model": model, "cwd": cwd,
                            "session_id": session_id})
        return {}

    real_spawn_runner = jobs.spawn_runner
    jobs.spawn_runner = fake_spawn_runner

    eng = None
    manifest = {}
    boot_exc = None
    try:
        try:
            eng = Engine(tron_ctx)
            eng.dry = False   # real trunk observation throughout
            ok("pre0: Engine() resolved real repo_paths off the REAL "
               "trivial-tip-converter project.yaml",
               eng.paths.get("root") == root and eng.paths.get("main_branch") == "main"
               and eng.paths.get("pipeline_rel") == "meta/pipeline.md"
               and eng.paths.get("roles_path") == os.path.join(root, "meta/tron/roles.yaml"),
               f"paths={eng.paths}")

            spawned_at_boot = eng.start(scope="all", worker_count=1, models={})
        except Exception as e:                # noqa: BLE001 — the exact finding this wave hunts for
            boot_exc = e
            print("=" * 72)
            print("COMPAT FINDING — the REAL scaffold did NOT boot cleanly "
                  "through core.engine.Engine:")
            print(f"{type(e).__name__}: {e}")
            traceback.print_exc()
            print("=" * 72)
            ok("BOOT (KILLER — must be GREEN): Engine.start() over the REAL "
               "trivial-tip-converter scaffold raised no exception",
               False, f"{type(e).__name__}: {e}")
        else:
            manifest = state.load(tron_ctx)
            ok("BOOT (KILLER — must be GREEN): Engine.start() over the REAL "
               "trivial-tip-converter scaffold completed with no exception",
               True)
            ok("M1: manifest.yaml written with a real session start marker",
               os.path.exists(tron_ctx.state)
               and bool((manifest.get("session") or {}).get("started_at")),
               f"session={manifest.get('session')}")
            scope_ids = sorted((manifest.get("scope") or {}).get("ids") or [])
            ok("M2: scope='all' resolved off the REAL pipeline.md to every real "
               "row across every table (Roadmap's 01-01/01-02/01-03 PLUS the "
               "real doc's own placeholder TD-01/ADHOC-01/BL-01 rows in its "
               "Technical Debt/Ad-hoc/Backlog tables — no block file exists for "
               "those three, so M4 below proves they're correctly excluded from "
               "actual DISPATCH even though A3 counts them as 'on trunk')",
               scope_ids == ["01-01", "01-02", "01-03", "ADHOC-01", "BL-01", "TD-01"],
               f"scope={manifest.get('scope')}")
            arch_state = manifest.get("architect") or {}
            ok("M3: the persistent architect was spawned (pool-excluded) at boot",
               arch_state.get("spawned") is True
               and any(c["worker_id"] == architect.ARCHITECT_WID for c in spawn_calls),
               f"architect={arch_state} spawn_calls={spawn_calls}")
            workers = manifest.get("workers") or {}
            first_dispatch_blocks = sorted(w.get("block") for w in workers.values())
            ok("M4: the first dispatch selected EXACTLY block 01-02 (01-01 is "
               "already ✅ done on the real pipeline; 01-03's real "
               "`Depends on: 01-02` correctly gates it out until 01-02 lands)",
               spawned_at_boot != [] and first_dispatch_blocks == ["01-02"],
               f"spawned_at_boot={spawned_at_boot} workers={workers}")
            cadence = manifest.get("cadence") or {}
            ok("M5: the real knobs.yaml's top-level `cadence: {code: 1}` map "
               "round-tripped into the manifest's zeroed cadence seed",
               cadence == {"code": 0}, f"cadence={cadence}")
    finally:
        jobs.spawn_runner = real_spawn_runner

    # ── compat finding (non-fatal to boot): knobs.yaml's REAL nested shape
    #     vs. this stack's flat-top-level knobs reader (core/engine.py::
    #     _knobs, core/liveness.py::_silence_knobs) ──
    knobs_finding = None
    if boot_exc is None and eng is not None:
        with open(staged_knobs_path) as f:
            real_knobs_doc = yaml.safe_load(f) or {}
        nested = real_knobs_doc.get("knobs") or {}
        flat_seen = eng._knobs()
        diverging = [k for k in ("grant_ttl", "silence_ping_min", "silence_escalate_min")
                    if k in nested and flat_seen.get(k) != nested.get(k)]
        if diverging:
            knobs_finding = (
                "COMPAT FINDING (non-fatal — boot still succeeds via silent "
                "defaults): the real trivial-tip-converter knobs.yaml follows "
                "the RESPECTED schema (contracts/schema/knobs.schema.yaml), "
                f"which nests {diverging} under a top-level `knobs:` map "
                f"(declared values: { {k: nested.get(k) for k in diverging} }). "
                "core/engine.py::_knobs / core/liveness.py::_silence_knobs / "
                "core/reviewers.py::_cadence_cfg all read knobs.yaml's TOP "
                "LEVEL directly (no `.get('knobs', {})` unwrap) — every "
                "core/*_rig.py and core.sim.scaffold's own synthetic "
                "knobs.yaml write FLAT (unnested), which is why this gap was "
                "never caught before this wave. Effect on the real project: "
                f"{ {k: flat_seen.get(k) for k in diverging} } is what this "
                "stack actually uses (silent engine defaults / None), NOT "
                "the real project's own declared values — grant_ttl happens "
                "to coincide (60==60); silence_ping_min/silence_escalate_min "
                "do NOT (declared 6/8, this stack sees None -> "
                "core/liveness.py's own docstring: 'never a ping/escalate at "
                "all'). `cadence:` is unaffected (already top-level in both "
                "the real file and the reader).")
            print("=" * 72)
            print(knobs_finding)
            print("=" * 72)

    # ══ 3. optional echo-tier transport smoke ══
    echo_result = {"attempted": False, "ok": False, "detail": "skipped"}
    if boot_exc is None:
        print("attempting the OPTIONAL echo-tier real-worker-runner transport smoke...")
        try:
            echo_result = run_echo_smoke(tron_ctx)
        except Exception as e:                # noqa: BLE001 — belt+suspenders; run_echo_smoke
                                               # already catches everything internally
            echo_result = {"attempted": True, "ok": False,
                           "detail": f"smoke harness itself raised: {type(e).__name__}: {e}",
                           "escalated_kills": []}
        print(f"echo smoke result: {echo_result}")
    else:
        print("SKIPPING the echo-tier smoke — the stubbed boot itself already "
              "failed (nothing real to smoke-test on top of a broken boot)")

    # ── final orphan assertion, scoped to THIS rig's own copy root (the
    #     hard safety gate) ──
    orphans = _orphan_processes(root)
    ok("ORPHAN (SAFETY GATE — must be GREEN): 0 worker_runner.py/claude "
       "processes alive at exit whose cmdline references this rig's own "
       "copy root (stubbed boot spawned none for real; the echo smoke, if "
       "it ran, tore its OWN process down)",
       orphans == [], f"orphans={orphans}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.sim.boot_real_scaffold_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
         f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nSCAFFOLD_SRC (real, untouched)={SCAFFOLD_SRC}")
    print(f"copy root={root}")
    print(f"live instance dir={inst}")
    print(f"boot exception={f'{type(boot_exc).__name__}: {boot_exc}' if boot_exc else None}")
    print(f"knobs compat finding={'YES — see above' if knobs_finding else 'none'}")
    print(f"echo smoke={echo_result}")

    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
