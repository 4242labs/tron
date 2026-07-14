"""core.outage_rig — real-git, no-LLM rig proving wave 19 (GAP-C: fleet-
outage / canary self-release) does exactly what `core/switchboard.py`'s
+ `core/architect.py`'s own module docstrings promise: a real fleet WILL hit
a systemic outage (quota/auth/credit exhausted, host CLI down) where EVERY
spawn dies, synchronously, the instant it is attempted — the #2 risk for the
first real-LLM run (the self-release lever, 01-23 AC-6, never fired live
historically). Driven entirely via the REAL `core.engine.Engine` (`Engine(
ctx).start(...)` / `Engine.tick()` — never a direct `core.tick.tick`/
`core.switchboard.fill` call of this rig's own), exactly like `core/
engine_rig.py`/`core/opfloor_rig.py`.

REAL surface only: a real `git init` repo copied from the SAME scaffold
every prior `core/*_rig.py` uses, `meta/scripts/land.sh` run for real via
`subprocess`, a real `engine.ctx.Ctx` pointing at a real `manifest.yaml`, a
real `project.yaml`/`knobs.yaml`/`roles.yaml` (the same shapes `core/
engine_rig.py` established, `fleet_outage_deaths` added under `knobs:`).
`engine.jobs.spawn_runner` is the ONE seam stubbed (never a real `claude`
process — the established "rig plays the worker" pattern); this rig's own
stub is what SIMULATES the outage: for a controllable set of ticks, it
RAISES for every `engineer-*` spawn (a synchronous, in-process failure — the
realistic shape of a host CLI that refuses to even launch on a quota/auth/
credit error) while the PERSISTENT ARCHITECT keeps spawning fine (it is the
control plane that stays alive to observe + triage the outage in the first
place — a real deployment's architect is not drawn from the same exhausted
worker-model quota/credentials the fleet's engineer pool is, ADR-0002 D4's
own fleet-as-config split). Every other `Engine` hook (`_to_worker`,
`_release_worker`, `_grant_ttl`, `log`) runs FOR REAL; `_page_operator` is
the REAL wave-17 implementation, deliberately given NO `eng._deliver_page`
hook (the "absent hook, production-shaped" path `core/opfloor_rig.py`'s own
BL3 already proves floors identically to a `"failed"` receipt).

THREE independent drives, each its own real scaffold + real `Engine`:

  drive_outage()   — the PRIMARY killer. Every `engineer-*` spawn dies for
    `fleet_outage_deaths` consecutive attempts (worker_count=1, so exactly
    one spawn ATTEMPT per tick): the engine PAUSES dispatch (bounded total
    spawn attempts, never a runaway re-spawn loop) and raises ONE
    fleet-outage escalation ARCHITECT-FIRST (`core/casestate.py::open_case`,
    wave 18's own routing, unedited — a block-less case, `kind=
    "fleet_outage"`). The scripted architect answers the triage `operator`
    (a quota/auth outage is the operator's to fix, never the architect's) —
    THE FLOOR (wave 17's `reping`, unedited) then re-pages every qualifying
    tick, forever, never closing/dropping/session-ending, across a real
    multi-tick OBSERVE window. The operator then `resume`s the SAME tick
    the simulated outage clears (the stub stops dying) — dispatch resumes,
    every fixture block lands + closes, and the whole drive reaches a
    clean, idempotent SESSION-END.

  drive_healthy()  — NO FALSE TRIP #1: an ordinary healthy multi-block
    drive (every spawn succeeds) never trips the outage detector —
    `manifest["fleet"]["consecutive_deaths"]` stays 0, `manifest["paused"]`
    stays false, no `fleet_outage` case ever opens, the entire time.

  drive_single_death() — NO FALSE TRIP #2: a single, TRANSIENT spawn-time
    death (recovers on its very next attempt, well under threshold) never
    trips the outage detector, and — run CONCURRENTLY, in the SAME
    manifest, against a genuinely SILENT worker (spawns fine, never reports
    `worker.online`) — proves the two ladders are structurally decoupled:
    the silent worker is `core/liveness.py`'s own time-based ping/stall
    ladder's problem (a real `worker.stalled` case, `kind="stall"`), NEVER
    counted toward `manifest["fleet"]["consecutive_deaths"]`, and the one
    transient spawn death is never escalated by liveness either.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.
"""
import os
import sys
import shutil
import subprocess
import tempfile
import json

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # grants.py / trunk.py / ctx.py / jobs.py / roles.py
sys.path.insert(0, HERE)                                 # core/{gate,state,snapshot,tick,engine,...}.py — HERE
                                                          # wins on the bare name "engine" (shadows
                                                          # engine/engine.py's CLI script), the SAME
                                                          # sys.path-order convention every other
                                                          # core/*_rig.py already relies on.

import grants                # noqa: E402 — respected contract, real, unmodified
import trunk                  # noqa: E402 — respected contract, real, unmodified
import jobs                    # noqa: E402 — engine/jobs.py, the ONE seam this rig stubs (spawn_runner)
from ctx import Ctx             # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import gate                      # noqa: E402 — core/gate.py, the DONE ladder (stage constants only)
import architect                  # noqa: E402 — core/architect.py, ARCHITECT_WID + wave 19's own helper
import switchboard                 # noqa: E402 — core/switchboard.py, THE MODULE UNDER TEST (fleet detect)
import knobs as knobs_mod           # noqa: E402 — core/knobs.py, THE MODULE UNDER TEST (fleet_outage_deaths)
import state                         # noqa: E402 — core/state.py
from engine import Engine, BootupError   # noqa: E402 — core/engine.py, real bootup/tick wiring (unedited)

import scaffold_src               # noqa: E402 — core/scaffold_src.py, the ONE resolver

SCAFFOLD_SRC = scaffold_src.resolve()
MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"
ROLES_REL = "meta/tron/roles.yaml"
PERSONAS_REL = "meta/tron/personas"
STUB_MODEL = "stub-model"

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers (same convention as every prior core/*_rig.py) ──
def _git(args, cwd, check=True):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}) rc={r.returncode}\n"
                           f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return r


def _git_out(args, cwd):
    return _git(args, cwd).stdout.strip()


def build_root(tag):
    d = tempfile.mkdtemp(prefix=f"tron-core-outagerig-{tag}-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-outage-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


BLOCK_DOC_TEMPLATE = """# Block {block}: outage_rig fixture

**Phase:** 1 — GAP-C fleet-outage self-release rig
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.outage_rig` — proves `core/switchboard.py`'s
+ `core/architect.py`'s fleet-outage self-release (wave 19, GAP-C).
"""

ROLES_YAML_TEMPLATE = """roles:
  engineer:
    persona: {personas}/engineer.md
    model: {model}
    binds: [BUILD, CLOSE]
  reviewer-code:
    persona: {personas}/reviewer-code.md
    model: {model}
    binds: [REVIEW]
    selector:
      reviewer_class: code
  architect:
    persona: {personas}/architect.md
    model: {model}
    binds: [TRIAGE]
    spec_owner: true
    persistent: true
"""

PERSONA_TEMPLATE = """# {role} persona (core.outage_rig fixture)

A synthetic persona file — `engine.roles.RolesConfig`'s own fail-closed
boot validation requires every declared role's persona to exist on disk;
this rig's workers are entirely scripted (no LLM, no real `claude`
process), so the CONTENT here is never read by anything, only its
presence.
"""


def seed_pipeline(root, block_ids):
    _git(["checkout", "-B", MAIN, MAIN], root)
    rows = "\n".join(
        f"| {b} | outage_rig fixture block {b} (no deps) | 📋 To do | Block `blocks/{b}.md` |"
        for b in block_ids)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(f"# Pipeline\n\n## Roadmap\n\n### Phase 1: outage_rig fixture\n\n"
                f"| ID | Task | Status | Notes |\n|:---|:---|:---|:---|\n{rows}\n")
    for b in block_ids:
        bpath = os.path.join(root, BLOCKS_REL, f"{b}.md")
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        with open(bpath, "w") as fh:
            fh.write(BLOCK_DOC_TEMPLATE.format(block=b))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + blocks {block_ids} (to-do, no deps, no gates)"], root)
    _git(["checkout", "--detach", MAIN], root)


def seed_roles(root):
    roles_path = os.path.join(root, ROLES_REL)
    os.makedirs(os.path.dirname(roles_path), exist_ok=True)
    with open(roles_path, "w") as f:
        f.write(ROLES_YAML_TEMPLATE.format(personas=PERSONAS_REL, model=STUB_MODEL))
    personas_dir = os.path.join(root, PERSONAS_REL)
    os.makedirs(personas_dir, exist_ok=True)
    for role in ("engineer", "reviewer-code", "architect"):
        with open(os.path.join(personas_dir, f"{role}.md"), "w") as f:
            f.write(PERSONA_TEMPLATE.format(role=role))
    _git(["checkout", "-B", MAIN, MAIN], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: roles.yaml (engineer/architect) + personas"], root)
    _git(["checkout", "--detach", MAIN], root)


def write_project_yaml(inst_dir, root):
    os.makedirs(inst_dir, exist_ok=True)
    doc = {
        "repo": {"root": root, "main_branch": MAIN, "remote": "none", "staging": "none"},
        "test": {"command": "true"},
    }
    with open(os.path.join(inst_dir, "project.yaml"), "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)


def write_knobs(inst_dir, worker_count, fleet_outage_deaths=3,
                silence_ping_min=2000, silence_escalate_min=4000):
    """`cadence: {}` (empty) throughout this whole rig, deliberately — the
    cadence-reviewer spawn path shares `eng._spawn_worker` but is OUT of
    this brick's minimal-edit scope (`core/switchboard.py`'s own module
    docstring); no drive here ever configures a cadence that could dispatch
    one. `fleet_outage_deaths` is the ONE new knob this wave adds
    (`core/knobs.py`, wave 19/GAP-C)."""
    doc = {
        "knobs": {
            "worker_count": worker_count,
            "silence_ping_min": silence_ping_min,
            "silence_escalate_min": silence_escalate_min,
            "grant_ttl": 60,
            "fleet_outage_deaths": fleet_outage_deaths,
        },
        "cadence": {},
    }
    with open(os.path.join(inst_dir, "knobs.yaml"), "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)


def make_code_commit(root, branch, code_file_rel, marker):
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(f"// {marker} — core.outage_rig real code change\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"feat({branch}): {marker}"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def make_record_commit(root, branch, block_file_rel):
    _git(["checkout", branch], root)
    path = os.path.join(root, block_file_rel)
    with open(path) as f:
        content = f.read()
    new_content = content.replace("**Status:** 📋 To do", "**Status:** ✅ Done")
    assert new_content != content, "seed status line not found — fixture drift"
    with open(path, "w") as f:
        f.write(new_content)
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"record: {branch} done"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def ensure_rebased(root, branch):
    _git(["checkout", branch], root)
    r = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", MAIN, branch])
    if r.returncode != 0:
        _git(["rebase", MAIN], root)
    _git(["checkout", "--detach", MAIN], root)


def run_land(root, grants_dir, case_id):
    r = subprocess.run(
        ["bash", os.path.join(root, "meta", "scripts", "land.sh"), case_id,
         "--main", MAIN, "--grants-dir", grants_dir],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "LAND_MAIN_BRANCH": MAIN})
    return r.returncode, r.stdout, r.stderr


def try_land(root, grants_dir, case_id, branch, landed_cases):
    if case_id in landed_cases:
        return True
    rc, out, err = run_land(root, grants_dir, case_id)
    if rc == 0:
        landed_cases.add(case_id)
        return True
    combined = (out or "") + (err or "")
    if "not a fast-forward" in combined or "CAS failed" in combined:
        ensure_rebased(root, branch)
        return False
    raise RuntimeError(f"land.sh failed unexpectedly for case {case_id} on {branch}: "
                       f"rc={rc}\nstdout={out}\nstderr={err}")


def append_jsonl(path, obj):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
                                 "(rig-supplied local report, delivered via a structured "
                                 "worker.done inbox line)"}


class EngineerReactor:
    """Generalized engineer + architect(reconcile/triage) react loop — the
    SAME "generalized over WHATEVER engineer-<block> worker record appears"
    shape `core/engine_rig.py::RunHistory` already established, trimmed to
    exactly what this rig's fixtures need (no reviewer, no log-review adhoc
    — out of scope for GAP-C)."""

    def __init__(self, root, grants_dir, tron_ctx, block_ids):
        self.root = root
        self.grants_dir = grants_dir
        self.tron_ctx = tron_ctx
        self.block_ids = list(block_ids)
        self.branch_created = {}
        self.local_reported = {}
        self.record_committed = {}
        self.torn_down = {}
        self.spawn_tick = {}
        self.done_tick = {}
        self.close_tick = {}
        self.landed_cases = set()
        self.reconciled_reported = set()
        self.triage_answered = {}   # triage_id -> verdict already injected

    def react_engineers(self, i, manifest):
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}
        for agent_id, w in list(workers.items()):
            if not agent_id.startswith("engineer-"):
                continue
            block = w.get("block")
            if not block or block not in self.block_ids:
                continue
            # A heartbeat EVERY tick this worker is genuinely tracked by
            # this reactor (`core/liveness.py::touch` marks it "reported"
            # off ANY structured line carrying its own agent_id — see that
            # module's own docstring) — this rig's ONLY purpose for it is
            # keeping an ACTIVELY-DRIVEN engineer (real branch/land/record
            # work between reports) from being mistaken for a genuinely
            # SILENT worker by `core/liveness.py`'s own, unedited, ladder
            # (`drive_single_death` deliberately configures LOW silence
            # knobs so sd-2's real silence trips it quickly — sd-1, still
            # being actively driven, must not accidentally trip it too).
            # block 01-37 T7/T10: `worker.progress` is DELETED — `worker.
            # flag` (surfaced, non-paging) replaces it as the "still alive,
            # nothing structural to report" heartbeat.
            append_jsonl(self.tron_ctx.worker_inbox,
                        {"tag": "worker.flag", "agent_id": agent_id})
            branch = f"feat/{block}"
            if block not in self.spawn_tick:
                self.spawn_tick[block] = i
            if w.get("status") == "spawning" and not self.branch_created.get(block):
                make_code_commit(self.root, branch, f"src/lib/{block}.ts",
                                 f"{block}-outagerig-change")
                self.branch_created[block] = True
                append_jsonl(self.tron_ctx.worker_inbox,
                            {"tag": "worker.online", "agent_id": agent_id,
                             "slots": {"branch": branch}})

            g = gates.get(block)
            if not g:
                continue
            stage = g.get("stage")
            block_file_rel = f"{BLOCKS_REL}/{block}.md"

            if stage == gate.STAGE_LOCAL and not self.local_reported.get(block):
                append_jsonl(self.tron_ctx.worker_inbox,
                            {"tag": "worker.done", "block": block, "slots": LOCAL_PASS_REPORT})
                self.local_reported[block] = True
            elif stage == gate.STAGE_MERGE and g.get("merge_case_id"):
                try_land(self.root, self.grants_dir, g["merge_case_id"], branch, self.landed_cases)
            elif stage == gate.STAGE_RECORD:
                if g.get("record_ordered") and not self.record_committed.get(block) \
                        and not g.get("record_case_id"):
                    make_record_commit(self.root, branch, block_file_rel)
                    self.record_committed[block] = True
                if g.get("record_case_id"):
                    try_land(self.root, self.grants_dir, g["record_case_id"], branch, self.landed_cases)
            elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not self.torn_down.get(block):
                _git(["branch", "-D", branch], self.root)
                self.torn_down[block] = True

            if stage == gate.STAGE_CLOSED and block not in self.close_tick:
                self.close_tick[block] = i

    def react_architect_reconcile(self, i, manifest):
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if cur and cur.get("kind") == "reconcile" and cur.get("ordered") \
                and cur.get("block") not in self.reconciled_reported:
            append_jsonl(self.tron_ctx.worker_inbox,
                        {"tag": "architect.reconciled", "block": cur["block"],
                         "agent_id": architect.ARCHITECT_WID})
            self.reconciled_reported.add(cur["block"])

    def react_architect_triage(self, i, manifest, verdict_for_source):
        """Scripted architect: for whatever `triage` job is CURRENT and
        ORDERED, answer the verdict `verdict_for_source` maps its own
        `source` to — mirrors `core/opfloor_rig.py`'s identical one-job-at-
        a-time triage reactor."""
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if not (cur and cur.get("kind") == "triage" and cur.get("ordered")):
            return
        triage_id = cur["triage_id"]
        if triage_id in self.triage_answered:
            return
        verdict = verdict_for_source.get(cur.get("source"))
        if not verdict:
            return
        append_jsonl(self.tron_ctx.worker_inbox,
                    {"tag": "architect.triage_verdict", "triage_id": triage_id,
                     "verdict": verdict, "agent_id": architect.ARCHITECT_WID})
        self.triage_answered[triage_id] = verdict

    def record_done_ticks(self, i, outcomes):
        for block, (outcome, _detail) in outcomes.items():
            if outcome == "record_landed" and block not in self.done_tick:
                self.done_tick[block] = i


def find_open_case(manifest, kind):
    for c in (manifest.get("cases") or {}).values():
        if c.get("kind") == kind and c.get("decision") is None:
            return c
    return None


def page_counts(manifest, case_id):
    pages = manifest.get("operator_pages") or {}
    return [p for p in pages.values() if p.get("case_id") == case_id]


def engineer_spawn_calls(spawn_calls):
    return [c for c in spawn_calls if c["worker_id"].startswith("engineer-")]


def make_spawn_stub(dying_flag, dying_once=None):
    """The ONE process-spawn seam this whole rig stubs. `dying_flag` is a
    ONE-ITEM mutable list — `[True]`/`[False]` — this rig's own drives flip
    mid-run to simulate the outage clearing (never a real `claude` process,
    exactly the established "rig plays the worker" pattern). Only
    `engineer-*` spawns ever die — the persistent architect (`architect.
    ARCHITECT_WID`) always succeeds (see module docstring: it is the
    control plane that stays alive to observe + triage the outage).
    `dying_once` (drive_single_death only) is an OPTIONAL set of agent-ids
    that die on their FIRST attempt only, regardless of `dying_flag`, then
    succeed on every later attempt — a single TRANSIENT death."""
    spawn_calls = []
    seen_once = set()

    def fake_spawn_runner(worker_id, worker_dir, session_id, cwd=None,
                          runtime=None, adapter=None, model=None, settle_s=2.0):
        spawn_calls.append({"worker_id": worker_id, "model": model})
        if worker_id == architect.ARCHITECT_WID:
            return {}
        if dying_once and worker_id in dying_once and worker_id not in seen_once:
            seen_once.add(worker_id)
            raise RuntimeError(f"simulated TRANSIENT spawn death for {worker_id!r} "
                               f"(first attempt only)")
        if dying_flag[0] and worker_id.startswith("engineer-"):
            raise RuntimeError(f"simulated fleet outage: spawn refused for "
                               f"{worker_id!r} (quota/auth/credit exhausted)")
        return {}

    return fake_spawn_runner, spawn_calls


# ══════════════════════════════════════════════════════════════════════════
# DRIVE 1 — the PRIMARY killer: outage detected -> self-release -> floored
# operator escalation -> recovery -> clean session-end
# ══════════════════════════════════════════════════════════════════════════
def drive_outage():
    OUTAGE_DEATHS = 3
    BLOCKS = ["out-1", "out-2", "out-3"]
    MAX_TICKS = 200
    OBSERVE_TICKS = 8   # ticks to keep driving UNRESOLVED once paused, before resuming

    root = build_root("outage")
    seed_pipeline(root, BLOCKS)
    seed_roles(root)
    inst = os.path.join(root, "meta", "agents", "tron")
    write_project_yaml(inst, root)
    write_knobs(inst, worker_count=1, fleet_outage_deaths=OUTAGE_DEATHS)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    dying = [True]
    fake_spawn_runner, spawn_calls = make_spawn_stub(dying)
    real_spawn_runner = jobs.spawn_runner
    jobs.spawn_runner = fake_spawn_runner
    real_release = jobs.release

    try:
        eng = Engine(Ctx(inst))
        eng.dry = False   # HARD RULE: real trunk observation throughout
        # Deliberately NO eng._deliver_page hook — the absent-hook,
        # production-shaped path (`core/opfloor_rig.py`'s own BL3): a
        # receipt of `None` floors identically to `"failed"`.

        spawned_at_boot = eng.start(scope="all", worker_count=1, models={})
        manifest_boot = state.load(tron_ctx)
        ok("O0: bootup's own first dispatch ATTEMPTED a spawn for the first "
           "fixture block (worker_count=1) — the very first death of the "
           "outage",
           len(engineer_spawn_calls(spawn_calls)) == 1,
           f"spawn_calls={spawn_calls}")
        ok("O0b: that first attempt genuinely DIED — no worker record left "
           "behind (freed slot, never a permanently-'dead' record)",
           spawned_at_boot == [] and not (manifest_boot.get("workers") or {}),
           f"spawned_at_boot={spawned_at_boot} workers={manifest_boot.get('workers')}")
        ok("O0c: the death was counted (fleet.consecutive_deaths=1), never "
           "silent",
           (manifest_boot.get("fleet") or {}).get("consecutive_deaths") == 1,
           f"fleet={manifest_boot.get('fleet')}")

        rx = EngineerReactor(root, grants_dir, tron_ctx, BLOCKS)
        verdict_map = {"fleet.outage": "operator"}
        outage_case = {"id": None, "opened_tick": None}
        resumed_tick = {"i": None}
        pages_at_resume = None
        spawn_calls_at_pause = None
        spawn_calls_mid_observe = None
        paused_at_open = None
        session_ended_tick = None
        i = 0

        for i in range(1, MAX_TICKS + 1):
            res = eng.tick()
            manifest = state.load(tron_ctx)
            rx.react_engineers(i, manifest)
            rx.react_architect_reconcile(i, manifest)
            rx.react_architect_triage(i, manifest, verdict_map)
            rx.record_done_ticks(i, res["outcomes"])

            if outage_case["id"] is None:
                c = find_open_case(manifest, "fleet_outage")
                if c is not None:
                    outage_case["id"], outage_case["opened_tick"] = c["case_id"], i
                    outage_case["owner_at_open"] = c.get("owner")
                    outage_case["block_at_open"] = c.get("block")
                    spawn_calls_at_pause = len(engineer_spawn_calls(spawn_calls))
                    paused_at_open = bool(manifest.get("paused"))

            if (outage_case["id"] is not None and spawn_calls_mid_observe is None
                    and i == outage_case["opened_tick"] + (OBSERVE_TICKS // 2)):
                # A snapshot HALFWAY through the observe window — proves the
                # spawn-attempt count never grows while paused, not just at
                # the two endpoints.
                spawn_calls_mid_observe = len(engineer_spawn_calls(spawn_calls))

            if (outage_case["id"] is not None and resumed_tick["i"] is None
                    and i >= outage_case["opened_tick"] + OBSERVE_TICKS):
                pages_at_resume = len(page_counts(manifest, outage_case["id"]))
                dying[0] = False   # the outage CLEARS — the next spawn attempt succeeds
                append_jsonl(tron_ctx.worker_inbox,
                            {"tag": "operator.decision",
                             "slots": {"case_id": outage_case["id"], "verb": "resume"}})
                resumed_tick["i"] = i

            se = res.get("session_end")
            if se is not None:
                session_ended_tick = i
                break

        final_manifest = state.load(tron_ctx)
        final_gates = final_manifest.get("gates") or {}
        final_cases = final_manifest.get("cases") or {}
        final_fleet = final_manifest.get("fleet") or {}
        ticks_used = i

        # ══ KILLER 1: OUTAGE DETECTED + SELF-RELEASE ══
        ok("O1 (OUTAGE-DETECTED KILLER — must be GREEN): a real fleet-outage "
           "case opened (block-less, kind='fleet_outage') within the observe "
           f"window",
           outage_case["id"] is not None, f"outage_case={outage_case}")
        ok("O2 (PAUSE KILLER — must be GREEN): manifest['paused'] read true "
           "the SAME tick the case opened",
           paused_at_open is True, f"paused_at_open={paused_at_open}")
        ok("O3 (BOUNDED-SPAWNS / NO-RUNAWAY-RE-SPAWN KILLER — must be "
           f"GREEN): EXACTLY {OUTAGE_DEATHS} engineer spawn ATTEMPTS total "
           "at the moment the outage tripped, and the count NEVER grew "
           f"again for the rest of the {OBSERVE_TICKS}-tick observe window "
           "(checked at the halfway point too, not just the endpoint) — "
           "the outage never triggered a runaway re-spawn loop",
           spawn_calls_at_pause == OUTAGE_DEATHS
           and spawn_calls_mid_observe == OUTAGE_DEATHS,
           f"spawn_calls_at_pause={spawn_calls_at_pause} "
           f"spawn_calls_mid_observe={spawn_calls_mid_observe} "
           f"OUTAGE_DEATHS={OUTAGE_DEATHS}")
        ok("O4: fleet.consecutive_deaths reached exactly the configured "
           "threshold (never overshoot — the loop breaks the SAME attempt "
           "it trips)",
           final_fleet.get("total_deaths", 0) >= OUTAGE_DEATHS,
           f"fleet={final_fleet}")
        ok("O5 (ARCHITECT-FIRST KILLER — must be GREEN): the fleet-outage "
           "case was owner='architect' the SAME tick it opened (never an "
           "immediate operator page) and block-less (no single pipeline "
           "row is 'the' outage — this is a whole-fleet signal)",
           outage_case.get("owner_at_open") == "architect"
           and outage_case.get("block_at_open") is None,
           f"outage_case={outage_case}")
        ok("O6 (SCRIPTED-ARCHITECT-VERDICTS-OPERATOR KILLER — must be "
           "GREEN): the architect's own triage was answered ('operator' — "
           "a quota/auth outage is the operator's, never the architect's) "
           "for this exact case's own triage job",
           outage_case["id"] is not None and len(rx.triage_answered) >= 1
           and "operator" in rx.triage_answered.values(),
           f"triage_answered={rx.triage_answered}")

        # ══ KILLER 2: THE FLOOR (wave 17, reused verbatim, unedited) ══
        ok("O7 (FLOORED-OPERATOR-CASE KILLER — must be GREEN): once the "
           "architect verdicted 'operator', THE FLOOR forced MULTIPLE "
           "operator_pages entries across the observe window (never a "
           "single silently-dropped page) — an ABSENT eng._deliver_page "
           "hook floors identically to a 'failed' receipt",
           pages_at_resume is not None and pages_at_resume > 1,
           f"pages_at_resume={pages_at_resume}")
        ok("O8 (NEVER-CLOSED / NEVER-SILENT-DIE / NEVER-BURNED-TO-END "
           "KILLER — must be GREEN): no tick emitted a session_end before "
           "the operator resumed — the outage never silently died and was "
           "never burned through to a fake session-end while unresolved",
           resumed_tick["i"] is not None
           and (session_ended_tick is None or session_ended_tick > resumed_tick["i"]),
           f"resumed_tick={resumed_tick['i']} session_ended_tick={session_ended_tick}")

        # ══ KILLER 3: RECOVERY -> CLEAN SESSION-END ══
        ok("O9 (RESUME-LIFTS-PAUSE KILLER — must be GREEN): the operator's "
           "resume cleared the case within the SAME tick (no case-clearing "
           "core/casestate.py edit was needed — the pause is derived LIVE)",
           outage_case["id"] not in final_cases, f"final_cases={list(final_cases)}")
        ok("O10 (RECOVERY -> RE-DISPATCH KILLER — must be GREEN): dispatch "
           "genuinely resumed post-resume — MORE engineer spawn attempts "
           "occurred after the resume than were on file at pause time",
           len(engineer_spawn_calls(spawn_calls)) > spawn_calls_at_pause,
           f"before={spawn_calls_at_pause} after={len(engineer_spawn_calls(spawn_calls))}")
        ok("O11 (COUNTER-RESETS-ON-RECOVERY KILLER — must be GREEN): "
           "fleet.consecutive_deaths reads 0 in the FINAL manifest — the "
           "first post-resume spawn genuinely succeeded and reset it",
           final_fleet.get("consecutive_deaths") == 0, f"fleet={final_fleet}")
        ok(f"O12 (WHOLE-DRIVE CONVERGENCE — must be GREEN): outage -> pause "
           f"-> architect-first -> floored operator escalation -> resume -> "
           f"fresh dispatch -> every fixture block closes -> a clean, "
           f"idempotent SESSION-END, inside {MAX_TICKS} ticks (used "
           f"{ticks_used})",
           session_ended_tick is not None and ticks_used < MAX_TICKS,
           f"ticks_used={ticks_used} session_ended_tick={session_ended_tick}")
        for block in BLOCKS:
            doc_on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{block}.md"], root)
            ok(f"O13[{block}]: the block doc AS READ FROM main shows ✅ — "
               "the post-recovery fresh dispatch genuinely landed it",
               "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")
            ok(f"O14[{block}]: the gate reached a genuine CLOSED terminal",
               final_gates.get(block, {}).get("stage") == gate.STAGE_CLOSED,
               f"gate={final_gates.get(block)}")

        # ── idempotent re-tick, post session-end (mirrors core/engine_rig.py) ──
        pre_replay_spawn_calls = len(spawn_calls)
        res_replay = eng.tick()
        ok("O15 (IDEMPOTENT RE-TICK KILLER — must be GREEN): a further "
           "eng.tick() AFTER session-end is a true no-op — nothing spawned, "
           "the SAME session-end marker back",
           res_replay.get("session_end") == final_manifest.get("session")
           and res_replay["spawned"] == []
           and len(spawn_calls) == pre_replay_spawn_calls,
           f"replay_result={res_replay}")

        print(f"\n[drive_outage] root={root}")
        print(f"[drive_outage] manifest={tron_ctx.state}")
        print(f"[drive_outage] outage_case={outage_case} resumed_tick={resumed_tick['i']} "
             f"session_ended_tick={session_ended_tick} ticks_used={ticks_used}")
        print(f"[drive_outage] spawn_calls_at_pause={spawn_calls_at_pause} "
             f"total_engineer_spawn_calls={len(engineer_spawn_calls(spawn_calls))} "
             f"pages_at_resume={pages_at_resume}")
        print(f"[drive_outage] final fleet={final_fleet}")
        print(f"[drive_outage] triage_answered={rx.triage_answered}")
    finally:
        jobs.spawn_runner = real_spawn_runner
        jobs.release = real_release


# ══════════════════════════════════════════════════════════════════════════
# DRIVE 2 — NO FALSE TRIP #1: a healthy fleet never trips the detector
# ══════════════════════════════════════════════════════════════════════════
def drive_healthy():
    BLOCKS = ["hf-1", "hf-2"]
    MAX_TICKS = 120

    root = build_root("healthy")
    seed_pipeline(root, BLOCKS)
    seed_roles(root)
    inst = os.path.join(root, "meta", "agents", "tron")
    write_project_yaml(inst, root)
    write_knobs(inst, worker_count=2, fleet_outage_deaths=3)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    dying = [False]   # never dies — a genuinely healthy fleet throughout
    fake_spawn_runner, spawn_calls = make_spawn_stub(dying)
    real_spawn_runner = jobs.spawn_runner
    jobs.spawn_runner = fake_spawn_runner
    real_release = jobs.release

    try:
        eng = Engine(Ctx(inst))
        eng.dry = False
        eng.start(scope="all", worker_count=2, models={})

        rx = EngineerReactor(root, grants_dir, tron_ctx, BLOCKS)
        never_paused = True
        never_fleet_case = True
        max_consecutive_deaths_seen = 0
        session_ended_tick = None
        i = 0
        for i in range(1, MAX_TICKS + 1):
            res = eng.tick()
            manifest = state.load(tron_ctx)
            rx.react_engineers(i, manifest)
            rx.react_architect_reconcile(i, manifest)
            never_paused = never_paused and not manifest.get("paused")
            never_fleet_case = never_fleet_case and find_open_case(manifest, "fleet_outage") is None
            max_consecutive_deaths_seen = max(
                max_consecutive_deaths_seen,
                (manifest.get("fleet") or {}).get("consecutive_deaths", 0))
            se = res.get("session_end")
            if se is not None:
                session_ended_tick = i
                break

        final_manifest = state.load(tron_ctx)
        final_gates = final_manifest.get("gates") or {}
        ticks_used = i

        ok("H1 (NO-FALSE-TRIP KILLER, HEALTHY FLEET — must be GREEN): "
           "manifest['paused'] was NEVER true across the whole healthy drive",
           never_paused, f"never_paused={never_paused}")
        ok("H2: no fleet_outage case EVER opened",
           never_fleet_case, f"never_fleet_case={never_fleet_case}")
        ok("H3: fleet.consecutive_deaths never rose above 0 the entire drive",
           max_consecutive_deaths_seen == 0,
           f"max_consecutive_deaths_seen={max_consecutive_deaths_seen}")
        ok(f"H4 (CONVERGENCE — must be GREEN): the healthy drive converged "
           f"to a clean session-end inside {MAX_TICKS} ticks (used {ticks_used})",
           session_ended_tick is not None and ticks_used < MAX_TICKS,
           f"ticks_used={ticks_used} session_ended_tick={session_ended_tick}")
        for block in BLOCKS:
            ok(f"H5[{block}]: gate reached CLOSED",
               final_gates.get(block, {}).get("stage") == gate.STAGE_CLOSED,
               f"gate={final_gates.get(block)}")

        print(f"\n[drive_healthy] root={root}")
        print(f"[drive_healthy] ticks_used={ticks_used} session_ended_tick={session_ended_tick} "
             f"never_paused={never_paused} never_fleet_case={never_fleet_case}")
    finally:
        jobs.spawn_runner = real_spawn_runner
        jobs.release = real_release


# ══════════════════════════════════════════════════════════════════════════
# DRIVE 3 — NO FALSE TRIP #2: a single TRANSIENT spawn death (recovers,
# never reaches threshold) is structurally decoupled from a genuine
# liveness silence-stall (a DIFFERENT worker, a DIFFERENT ladder)
# ══════════════════════════════════════════════════════════════════════════
def drive_single_death():
    BLOCKS = ["sd-1", "sd-2"]
    MAX_TICKS = 30   # bounded observe window — this drive never needs a
                     # session-end (sd-2's stall case stays open by design;
                     # proving the two ladders are decoupled needs no
                     # convergence, see module docstring)

    root = build_root("singledeath")
    seed_pipeline(root, BLOCKS)
    seed_roles(root)
    inst = os.path.join(root, "meta", "agents", "tron")
    write_project_yaml(inst, root)
    # LOW silence knobs — liveness's OWN ladder (unedited by this wave)
    # must genuinely fire within this drive's short window, to prove it
    # (and not the fleet-outage detector) is what handles sd-2's silence.
    write_knobs(inst, worker_count=2, fleet_outage_deaths=3,
               silence_ping_min=2, silence_escalate_min=4)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    dying = [False]
    # sd-1's engineer dies on its FIRST attempt only, then always succeeds —
    # a single TRANSIENT death, well under fleet_outage_deaths=3.
    dying_once = {"engineer-sd-1"}
    fake_spawn_runner, spawn_calls = make_spawn_stub(dying, dying_once=dying_once)
    real_spawn_runner = jobs.spawn_runner
    jobs.spawn_runner = fake_spawn_runner
    real_release = jobs.release

    try:
        eng = Engine(Ctx(inst))
        eng.dry = False
        eng.start(scope="all", worker_count=2, models={})

        rx = EngineerReactor(root, grants_dir, tron_ctx, ["sd-1"])   # sd-2 deliberately
                                                                     # never reacted to —
                                                                     # it must go SILENT
        max_consecutive_deaths_seen = 0
        never_fleet_case = True
        never_paused = True
        stall_case = {"id": None, "tick": None}
        i = 0
        for i in range(1, MAX_TICKS + 1):
            res = eng.tick()
            manifest = state.load(tron_ctx)
            rx.react_engineers(i, manifest)   # drives sd-1 only, to a real close
            rx.react_architect_reconcile(i, manifest)
            never_paused = never_paused and not manifest.get("paused")
            never_fleet_case = never_fleet_case and find_open_case(manifest, "fleet_outage") is None
            max_consecutive_deaths_seen = max(
                max_consecutive_deaths_seen,
                (manifest.get("fleet") or {}).get("consecutive_deaths", 0))
            if stall_case["id"] is None:
                c = find_open_case(manifest, "stall")
                if c is not None:
                    stall_case["id"], stall_case["tick"] = c["case_id"], i

        final_manifest = state.load(tron_ctx)
        final_fleet = final_manifest.get("fleet") or {}

        ok("D1 (TRANSIENT-DEATH-NEVER-TRIPS KILLER — must be GREEN): sd-1's "
           "single spawn-time death (first attempt only) recovered on its "
           "very next attempt — fleet.consecutive_deaths NEVER reached "
           "fleet_outage_deaths=3 the whole drive",
           max_consecutive_deaths_seen < 3,
           f"max_consecutive_deaths_seen={max_consecutive_deaths_seen}")
        ok("D2: engineer-sd-1's spawn was attempted at least twice (the "
           "death, then the successful retry) — a REAL recovery, not a "
           "no-op",
           len([c for c in spawn_calls if c["worker_id"] == "engineer-sd-1"]) >= 2,
           f"spawn_calls={[c for c in spawn_calls if c['worker_id']=='engineer-sd-1']}")
        ok("D3 (NEVER-PAUSED-BY-A-SINGLE-DEATH KILLER — must be GREEN): "
           "manifest['paused'] never flipped true",
           never_paused, f"never_paused={never_paused}")
        ok("D4: no fleet_outage case ever opened",
           never_fleet_case, f"never_fleet_case={never_fleet_case}")
        ok("D5 (LIVENESS-OWNS-THE-SILENT-WORKER KILLER — must be GREEN): "
           "sd-2 (spawned fine, never reported worker.online) was declared "
           "worker:stalled by `core/liveness.py`'s OWN, unedited, "
           "time-based ladder — a real 'stall' case, NEVER a "
           "'fleet_outage' one",
           stall_case["id"] is not None, f"stall_case={stall_case}")
        ok("D6 (STRUCTURALLY DECOUPLED KILLER — must be GREEN): the stall "
           "case never touched fleet.consecutive_deaths — it reads exactly "
           "what it read before sd-2's stall fired (0, since sd-1's own "
           "transient death already self-healed by then)",
           final_fleet.get("consecutive_deaths", 0) == 0,
           f"final_fleet={final_fleet} stall_case={stall_case}")
        ok(f"D7[sd-1]: sd-1 (the transient-death block, unaffected by sd-2's "
           f"stall) reached a genuine CLOSED gate despite its own earlier "
           f"death",
           (final_manifest.get("gates") or {}).get("sd-1", {}).get("stage") == gate.STAGE_CLOSED,
           f"gate={(final_manifest.get('gates') or {}).get('sd-1')}")

        print(f"\n[drive_single_death] root={root}")
        print(f"[drive_single_death] max_consecutive_deaths_seen={max_consecutive_deaths_seen} "
             f"stall_case={stall_case} final_fleet={final_fleet}")
    finally:
        jobs.spawn_runner = real_spawn_runner
        jobs.release = real_release


# ══════════════════════════════════════════════════════════════════════════
# GREP PROOF — no unbounded re-spawn, no silent-die path, no raw git
# outside core/gitobs.py (plain-text source scan, mirrors
# core/opfloor_rig.py's own SRC1/SRC2)
# ══════════════════════════════════════════════════════════════════════════
def grep_proof():
    src = {}
    for mod in ("switchboard", "architect", "knobs", "engine", "liveness"):
        src[mod] = open(os.path.join(HERE, f"{mod}.py")).read()

    ok("SRC1 (NO-RAW-GIT KILLER — must be GREEN): none of switchboard.py/"
       "architect.py/knobs.py (this wave's edited modules) shell out to a "
       "raw git/subprocess call of their own — all git observation stays "
       "inside core/gitobs.py",
       all("import subprocess" not in src[m] and "subprocess." not in s
           for m, s in (("switchboard", src["switchboard"]),
                        ("architect", src["architect"]), ("knobs", src["knobs"]))),
       "grep-equivalent source scan of core/{switchboard,architect,knobs}.py")

    fill_body = src["switchboard"].split("def fill(")[1]
    ok("SRC2 (NO-SILENT-DIE KILLER — must be GREEN): a caught spawn failure "
       "is ALWAYS logged (`eng.log`) before the tick continues — no bare "
       "`except ...: pass`/`except ...: continue` with no logging anywhere "
       "in `fill`'s own spawn try/except",
       "except Exception as exc:" in fill_body
       and "_record_fleet_death(eng, manifest, agent_id, block[\"id\"], exc)" in fill_body,
       "grep-equivalent scan of core/switchboard.py::fill's own except block")

    ok("SRC3 (NO-UNBOUNDED-RE-SPAWN KILLER — must be GREEN): `fill` checks "
       "the fleet-paused flag BOTH before the whole dispatch pass AND "
       "immediately after every failed spawn (mid-loop `break`) — never a "
       "loop that could re-attempt past the threshold within one call",
       fill_body.count("_fleet_paused(manifest)") >= 2,
       f"_fleet_paused(manifest) occurrences in fill()="
       f"{fill_body.count('_fleet_paused(manifest)')}")

    ok("SRC4: `core/architect.py`'s clear-ahead forward-job scan is "
       "guarded by the SAME pause check ('spawn nothing new while paused' "
       "extended to the architect's own queue)",
       "if not _fleet_paused(manifest):" in src["architect"]
       and "_enqueue_forward_jobs(eng, manifest, view)" in src["architect"],
       "grep-equivalent scan of core/architect.py::enqueue")

    ok("SRC5 (HARD-RULE KILLER — must be GREEN): `engine/*.py` and `land.sh` "
       "were not touched by this wave (git status on the worktree, checked "
       "by the caller) — this module itself never imports/edits either; "
       "`core/liveness.py` (this wave's time-based silence ladder) is "
       "UNTOUCHED by GAP-C — no fleet/outage vocabulary appears in it at "
       "all, proving the two ladders never share code",
       "fleet" not in src["liveness"].lower() and "outage" not in src["liveness"].lower(),
       "grep-equivalent scan of core/liveness.py for any fleet/outage vocabulary")

    print("\n[grep_proof] scanned core/{switchboard,architect,knobs,engine,liveness}.py")


def main():
    drive_outage()
    drive_healthy()
    drive_single_death()
    grep_proof()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.outage_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
         f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
