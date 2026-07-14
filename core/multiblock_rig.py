"""core.multiblock_rig — real-git, no-LLM rig proving a MULTI-block pipeline
WITH A REAL DEPENDENCY runs to a genuine clean SESSION-END, entirely via
repeated `core.tick.tick(eng)` calls (the WAKE daemon) — wave 6, the killer
this brick exists to prove: `core/pipeline.py::dispatchable` already excludes
non-deps-met + in-flight blocks (wave 5) and `core/switchboard.py::fill`
already fills free slots (wave 5); THIS rig is the first proof those two
things compose correctly across THREE real blocks with a real
`Depends on` edge, AND (wave 6, new this brick) that `core/tick.py`'s
observe->route->decide->act->fill pass emits a clean, idempotent
`core.session.check` terminal once every in-scope block is `✅` on trunk and
nothing is left in-flight.

REAL surface only: a real `git init` repo copied from the SAME scaffold
`core/gate_rig.py`/`core/gate_full_rig.py`/`core/tick_rig.py`/
`core/dispatch_rig.py` all use, a real `pipeline.md` + THREE real block docs
(`01-01`, `01-02` **Depends on: 01-01**, `01-03`) seeded `📋` on trunk,
`meta/scripts/land.sh` run for real via `subprocess`, a REAL `engine.ctx.Ctx`
pointing at a real `manifest.yaml`, a REAL declared test command (`true`)
re-run in a REAL clean detached worktree (`core.gitobs.validate_trunk` ->
`engine/trunk.py`), and a minimal duck-typed `eng` — never a faked/
monkeypatched trunk, never a faked test result, never a faked pipeline read.

`worker_count=1` (strict serialization, the primary run this brick's own
dep-ordering/spawn-once/session-end assertions are scoped to): the rig plays
BOTH roles a real deployment splits across processes — the WAKE daemon
(calls `core.tick.tick(eng)` on a loop) and, for EVERY block the engine has
dispatched/ordered THIS tick, the rig-as-that-worker — reacting to what THE
ENGINE ORDERED, read back off the real, persisted manifest after each tick
(never off this process's own memory of what it "meant" to do): forks its OWN
`feat/<block>` branch off trunk with a real code commit + reports online; at
`gate.local` reports a well-formed local-pass line; at `gate.merge`/
`gate.record`'s minted grants runs the REAL `land.sh`; at `gate.record`'s
order makes the REAL Status-flip commit; at `gate.close`'s order tears its
branch down for real — same "rig stands in for the real OS process"
convention every prior `core/*_rig.py` uses, generalized here over THREE
blocks reacted to in the SAME tick loop instead of one.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.

Wave 9 re-pointing note: `core/architect.py`'s M-05 reconcile-gate now ALSO
gates each of `01-02`/`01-03` behind a `reconcile` job the moment its
predecessor lands `✅` (this fixture's own `Depends on` edge, 01-01 ->
01-02, plus M-05's OWN "next in living-doc order" rule for 01-02 -> 01-03) —
`react()` below plays the scripted architect for that job (reports
`architect.reconciled`, structured, no content-check) exactly the same way
it already plays the scripted worker for every gate stage; `MAX_TICKS` is
bumped to give the two extra reconcile round-trips room. Every assertion
below is UNCHANGED (`>`/`>=` on `spawn_tick`/`done_tick`/`close_tick`
already tolerated — and now exercise — the extra gate, never weakened to
pass).
"""
import os
import sys
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # grants.py / trunk.py / ctx.py live here
sys.path.insert(0, HERE)                                 # core/{gate,state,snapshot,tick,...}.py

import grants               # noqa: E402 — respected contract, real, unmodified
import trunk                 # noqa: E402 — respected contract, real, unmodified
from ctx import Ctx          # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import architect              # noqa: E402 — core/architect.py, ARCHITECT_WID (door minters identity)
import gate                  # noqa: E402 — core/gate.py, the DONE ladder core.tick drives
import state                 # noqa: E402 — core/state.py
import tick                  # noqa: E402 — core/tick.py, the module under test (+ its wave-6 wiring)
import session                # noqa: E402 — core/session.py, the wave-6 clean SESSION-END terminal

import scaffold_src               # noqa: E402 — core/scaffold_src.py, the ONE resolver

SCAFFOLD_SRC = scaffold_src.resolve()
MAIN = "main"
CODE_FILE_REL = "src/lib/tip.ts"          # a real, non-meta/ source file — the "real code change"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"

# ── the THREE-block, real-dependency fixture (the killer): 01-02 Depends on
#    01-01; 01-03 has none — living-doc order 01-01 -> 01-02 -> 01-03 ──
BLOCK_A, BLOCK_B, BLOCK_C = "01-01", "01-02", "01-03"
BLOCKS = {
    BLOCK_A: {"depends_on": [], "branch": f"feat/{BLOCK_A}", "agent_id": f"engineer-{BLOCK_A}"},
    BLOCK_B: {"depends_on": [BLOCK_A], "branch": f"feat/{BLOCK_B}", "agent_id": f"engineer-{BLOCK_B}"},
    BLOCK_C: {"depends_on": [], "branch": f"feat/{BLOCK_C}", "agent_id": f"engineer-{BLOCK_C}"},
}
ORDER = [BLOCK_A, BLOCK_B, BLOCK_C]

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers (same convention as core/dispatch_rig.py) ──
def _git(args, cwd, check=True):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}) rc={r.returncode}\n"
                           f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return r


def _git_out(args, cwd):
    return _git(args, cwd).stdout.strip()


def is_ancestor(root, sha, ref=MAIN):
    r = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", sha, ref])
    return r.returncode == 0


def build_root():
    """Copy the REAL scaffold into a throwaway tempdir with a fresh, real git
    history on `main`, then detach (local no-remote mode keeps the root
    checkout DETACHED, ADR-0002 D1). Same shape as `core/dispatch_rig.py`."""
    d = tempfile.mkdtemp(prefix="tron-core-multiblockrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-multiblock-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: Multi-block rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {a} | multiblock_rig fixture block A (no deps) | 📋 To do | Block `blocks/{a}.md` |
| {b} | multiblock_rig fixture block B (depends on {a}) | 📋 To do | Block `blocks/{b}.md` |
| {c} | multiblock_rig fixture block C (no deps) | 📋 To do | Block `blocks/{c}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: multiblock_rig fixture

**Phase:** 1 — Multi-block rig
**Status:** 📋 To do
**Depends on:** {depends_on}
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.multiblock_rig` — proves SWITCHBOARD + the
two-step spawn->online->assign handshake + structured routing + dependency
gating drive THREE real pipeline blocks (one with a real `Depends on` edge)
from `📋` through dispatch to a genuine clean close, entirely via
`core.tick.tick`, then a clean SESSION-END terminal once all three are done.
"""


def seed_pipeline(root):
    """Commit a real `pipeline.md` (three rows, one real dependency edge) +
    all three block docs onto `main` for real — the ONLY pre-seeded state
    this rig starts from: NO gate, NO worker, NO manifest."""
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(a=BLOCK_A, b=BLOCK_B, c=BLOCK_C))
    for block, spec in BLOCKS.items():
        bpath = os.path.join(root, BLOCKS_REL, f"{block}.md")
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        depends_on = ", ".join(spec["depends_on"]) if spec["depends_on"] else "none"
        with open(bpath, "w") as f:
            f.write(BLOCK_DOC_TEMPLATE.format(block=block, depends_on=depends_on))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + blocks {BLOCK_A}/{BLOCK_B}/{BLOCK_C} "
                          f"({BLOCK_B} depends on {BLOCK_A}, all to-do, no gates)"], root)
    _git(["checkout", "--detach", MAIN], root)


def make_code_commit(root, branch, code_file_rel, marker):
    """Rig-as-worker: forks `branch` (ITS OWN choice) off CURRENT trunk,
    makes a REAL code change — never touching any block doc."""
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    with open(path, "a") as f:
        f.write(f"\n// {marker} — core.multiblock_rig real code change\n")
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


def run_land(root, grants_dir, case_id):
    """Run the REAL `meta/scripts/land.sh` via subprocess — the rig playing
    the worker ordered to land its own grant, per ADR-0002 D2."""
    r = subprocess.run(
        ["bash", os.path.join(root, "meta", "scripts", "land.sh"), case_id,
         "--main", MAIN, "--grants-dir", grants_dir],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "LAND_MAIN_BRANCH": MAIN})
    return r.returncode, r.stdout, r.stderr


def append_jsonl(path, obj):
    import json
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


class _Events:
    def __init__(self):
        self.log = []

    def event(self, type_, **payload):
        self.log.append({"type": type_, "payload": payload})


class MiniEng:
    """The minimal duck-typed `eng` — everything `core/landing.py` +
    `core/gate.py` + `core/pipeline.py` + `core/switchboard.py` +
    `core/session.py` (via `core/tick.py`) need. `.ctx` is a REAL
    `engine.ctx.Ctx` (not a rig stub), exercising the REAL path-resolver
    contract end to end. `._spawn_worker` is the wave-5 addition: a STUBBED
    process-spawn hook (no real process — this rig's own exactly-once
    spawn-count instrumentation) exactly like `._release_worker` already is
    for close."""
    def __init__(self, root, tron_ctx, test_command, worker_count=1):
        self.paths = {
            "root": root,
            "main_branch": MAIN,
            "test_command": test_command,     # the project's DECLARED trunk-validation command
            "test_env": None,
            "ci_check_name": None,            # None -> command mode, never CI mode, in this rig
            "worker_count": worker_count,
            "pipeline_rel": PIPELINE_REL,
            "blocks_rel": BLOCKS_REL + "/",
        }
        self.dry = False                 # HARD RULE: real trunk observation throughout
        self.ctx = tron_ctx              # REAL engine.ctx.Ctx
        self.events = _Events()
        self.log_lines = []
        self.orders = []
        self.workers = {}                # wid -> {"block":..., "status": "assigned"|"released"}
        self.spawn_calls = []            # (agent_id, block) — the idempotency KILLER counter
        self.architect_spawns = []       # wave 9: `eng._spawn_architect()` call count

    def log(self, channel, msg):
        self.log_lines.append((channel, msg))

    def _truth_ref(self):
        return MAIN

    def _to_worker(self, wid, msg, kind):
        self.orders.append((wid, msg, kind))

    def emit(self, template_id, fallback_text, slots=None, worker_id=None, kind=None):
        # Rig fixture: no canon shipped (no messages.yaml/prompts/ on this
        # scaffold), so this mirrors core.engine.Engine.emit's FALLBACK arm
        # unconditionally — fallback_text verbatim, delivered the same way
        # _to_worker always was, so every existing rig assertion on
        # self.orders stays byte-for-byte identical.
        line = fallback_text
        if worker_id and not self.dry:
            self._to_worker(worker_id, line, kind or template_id)
        return line

    def _grant_ttl(self):
        return 60

    def _release_worker(self, wid, reason="released"):
        self.workers[wid] = {**self.workers.get(wid, {}), "status": "released", "reason": reason}

    def _spawn_worker(self, agent_id, block):
        """STUBBED — no real `claude` process. `core/switchboard.py` already
        records the manifest-durable worker state itself (BEFORE calling
        this); this hook is purely the rig's own spawn-count instrumentation."""
        self.spawn_calls.append((agent_id, block))
        self.workers[agent_id] = {"block": block, "status": "spawned"}

    def _spawn_architect(self):
        """STUBBED — wave 9's persistent, pool-excluded architect. `core/
        architect.py::advance` calls this lazily, exactly once, the first
        tick it actually pops a queued job — this rig's THREE-block, real-
        `Depends on` fixture now ALSO exercises the M-05 reconcile-gate
        (each block landing ✅ enqueues a reconcile for the next in-scope
        one by pipeline order), so unlike the other 7 prior rigs, this one
        DOES need this hook."""
        self.architect_spawns.append(True)


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
                                 "(rig-supplied local report, delivered via a structured "
                                 "worker.done inbox line)"}

MAX_TICKS = 220   # wave 9: bumped for the two M-05 reconcile round-trips
                  # (01-01 -> 01-02, 01-02 -> 01-03) this fixture now also drives


def main():
    root = build_root()
    seed_pipeline(root)

    inst = os.path.join(root, "meta", "agents", "tron")   # engine/land_paperwork_rig.py's own
    os.makedirs(inst, exist_ok=True)                       # instance-dir convention
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    # ── the PRIMARY run: worker_count=1 — strict serialization, the shape
    #     the dep-ordering/spawn-once/session-end assertions below are
    #     scoped to (per spec: "run it with 1 ... AND assert dep-ordering") ──
    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)   # trivial, exits 0

    # ── pre-flight: NO pre-seeded gate, NO pre-seeded worker (the whole point) ──
    seed_manifest = state.load(tron_ctx)
    ok("pre0: rig starts with NO manifest.yaml on disk at all (a brand-new "
       "instance, never yet ticked)",
       not os.path.exists(tron_ctx.state), f"state={tron_ctx.state}")
    for block in ORDER:
        doc = open(os.path.join(root, BLOCKS_REL, f"{block}.md")).read()
        ok(f"pre1[{block}]: pipeline shows block {block} as 📋 (to-do) on trunk, "
           "no gate, no worker",
           "**Status:** 📋 To do" in doc, f"{block} doc seeded 📋")
    ok("pre2: block 01-02's own doc carries the REAL `Depends on: 01-01` edge "
       "(content-observed, not asserted by fixture intent alone)",
       "**Depends on:** 01-01" in
       open(os.path.join(root, BLOCKS_REL, f"{BLOCK_B}.md")).read(),
       "01-02 doc Depends-on header")

    branch_created = {b: False for b in ORDER}
    code_tip = {b: None for b in ORDER}
    local_reported = {b: False for b in ORDER}
    record_committed = {b: False for b in ORDER}
    record_tip = {b: None for b in ORDER}
    torn_down = {b: False for b in ORDER}
    real_land_calls = {}      # case_id -> count
    landed_cases = set()

    spawn_tick = {}    # block -> first tick index its worker record appears "spawning"
    close_tick = {}    # block -> tick index its gate first reaches STAGE_CLOSED
    tick_history = []  # (i, outcomes-dict, spawned-list, session_end) per tick
    reconciled_reported = set()   # wave 9 (M-05): blocks this rig already sent
                                   # an `architect.reconciled` report for

    def react(i, manifest):
        """The rig-as-worker's ONE reaction per tick, for EVERY block the
        engine has dispatched/ordered so far — inspect the just-persisted,
        REAL manifest and act on whatever the engine ordered for THAT block,
        never on this process's own memory of what it meant to do."""
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}

        for block in ORDER:
            spec = BLOCKS[block]
            agent_id, branch = spec["agent_id"], spec["branch"]
            block_file_rel = f"{BLOCKS_REL}/{block}.md"

            w = workers.get(agent_id)
            if w and block not in spawn_tick:
                spawn_tick[block] = i
            if w and w.get("status") == "spawning" and not branch_created[block]:
                code_tip[block] = make_code_commit(root, branch, CODE_FILE_REL,
                                                   f"{block}-multiblock-change")
                branch_created[block] = True
                append_jsonl(tron_ctx.worker_inbox,
                            {"tag": "worker.online", "agent_id": agent_id,
                             "slots": {"branch": branch}})

            g = gates.get(block)
            if not g:
                continue
            stage = g.get("stage")

            if stage == gate.STAGE_LOCAL and not local_reported[block]:
                append_jsonl(tron_ctx.worker_inbox,
                            {"tag": "worker.done", "block": block, "slots": LOCAL_PASS_REPORT})
                local_reported[block] = True

            elif stage == gate.STAGE_MERGE and g.get("merge_case_id"):
                case_id = g["merge_case_id"]
                if case_id not in landed_cases:
                    run_land(root, grants_dir, case_id)
                    real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                    landed_cases.add(case_id)

            elif stage == gate.STAGE_RECORD:
                if g.get("record_ordered") and not record_committed[block] and not g.get("record_case_id"):
                    record_tip[block] = make_record_commit(root, branch, block_file_rel)
                    record_committed[block] = True
                if g.get("record_case_id") and g["record_case_id"] not in landed_cases:
                    case_id = g["record_case_id"]
                    run_land(root, grants_dir, case_id)
                    real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                    landed_cases.add(case_id)

            elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not torn_down[block]:
                _git(["branch", "-D", branch], root)
                torn_down[block] = True

            if stage == gate.STAGE_CLOSED and block not in close_tick:
                close_tick[block] = i

        # ── wave 9 (M-05): the scripted ARCHITECT — react to a `reconcile`
        #     job by reporting done, structured, no content-check (no LLM
        #     in this brick) — exactly once per block. A landed ✅ now
        #     enqueues a reconcile for the next in-scope block by pipeline
        #     order (01-01 -> 01-02, then 01-02 -> 01-03), each GATED until
        #     this fires — see core/architect_rig.py for the dedicated
        #     ordering proof; this rig only needs to not get stuck on it. ──
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if cur and cur.get("kind") == "reconcile" and cur.get("ordered") \
                and cur.get("block") not in reconciled_reported:
            append_jsonl(tron_ctx.worker_inbox,
                        {"tag": "architect.reconciled", "block": cur["block"],
                         "agent_id": architect.ARCHITECT_WID})
            reconciled_reported.add(cur["block"])

    main_before = _git_out(["rev-parse", MAIN], root)

    i = 0
    session_ended_tick = None
    for i in range(MAX_TICKS):
        res = tick.tick(eng)
        manifest = state.load(tron_ctx)
        se = res.get("session_end")
        tick_history.append((i, dict(res["outcomes"]), list(res["spawned"]), se))
        react(i, manifest)
        if se is not None and session_ended_tick is None:
            session_ended_tick = i
            break

    # `done_tick[block]`: the FIRST tick whose `outcomes` shows this block's
    # `record_landed` — the tick the engine OBSERVED (real ancestry, via
    # `gate.record`'s `land_via_grant`) that block's ✅ genuinely reached
    # trunk. This is the REAL canon dep-ordering gate ("deps ✅ on trunk",
    # `core/pipeline.py::dispatchable`'s own predicate) — earlier and more
    # precise than `close_tick` (close is slot-teardown bookkeeping AFTER
    # the block is already ✅ on trunk, not the dep-gating signal itself).
    done_tick = {}
    for _i, _outcomes, _spawned, _se in tick_history:
        for _b, (_outcome, _detail) in _outcomes.items():
            if _outcome == "record_landed" and _b not in done_tick:
                done_tick[_b] = _i

    final_manifest = state.load(tron_ctx)
    final_gates = final_manifest.get("gates") or {}
    final_workers = final_manifest.get("workers") or {}
    ticks_used = i + 1

    ok(f"M0: the whole THREE-block drive converged (a clean session-end "
       f"observed) inside {MAX_TICKS} ticks (used {ticks_used})",
       session_ended_tick is not None and ticks_used < MAX_TICKS,
       f"ticks_used={ticks_used} session_ended_tick={session_ended_tick}")

    # ══ THE THREE-BLOCK KILLERS ══
    for block in ORDER:
        agent_id = BLOCKS[block]["agent_id"]
        branch = BLOCKS[block]["branch"]
        block_file_rel = f"{BLOCKS_REL}/{block}.md"
        g = final_gates.get(block, {})

        ok(f"M1[{block}]: SWITCHBOARD spawned {block} off the real pipeline "
           "read — a worker record for the deterministic agent-id exists, "
           "minted BEFORE any process",
           agent_id in final_workers, f"workers={list(final_workers)}")
        ok(f"M2[{block}]: the worker's OWN real code commit genuinely landed "
           "on trunk via gate.merge's real land.sh",
           bool(code_tip[block]) and is_ancestor(root, code_tip[block], MAIN),
           f"code_tip={code_tip[block]}")
        ok(f"M3[{block}]: gate.trunk genuinely re-ran the REAL declared test "
           "command in a REAL clean detached worktree at the merged sha and "
           "observed PASS",
           g.get("trunk_verdict") == "pass", f"trunk_verdict={g.get('trunk_verdict')}")
        ok(f"M4[{block}]: the ✅ status commit genuinely landed on trunk via "
           "a second, independently content-bound grant",
           bool(record_tip[block]) and is_ancestor(root, record_tip[block], MAIN)
           and g.get("record_case_id") != g.get("merge_case_id"),
           f"record_tip={record_tip[block]} record_case_id={g.get('record_case_id')} "
           f"merge_case_id={g.get('merge_case_id')}")
        doc_on_main = _git_out(["show", f"{MAIN}:{block_file_rel}"], root)
        ok(f"M5[{block}] (ALL THREE ✅ ON TRUNK — must be GREEN): the block "
           "doc AS READ FROM main shows ✅ (real git show on trunk)",
           "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")
        branch_gone = not trunk.branch_exists(root, branch, False)
        clean_now, clean_detail = trunk.replica_clean(root, branch, MAIN, False)
        ok(f"M6[{block}]: the replica is genuinely clean on real git (branch "
           "gone, no worktree) and the gate is CLOSED",
           branch_gone and clean_now and g.get("stage") == gate.STAGE_CLOSED,
           f"branch_gone={branch_gone} clean={clean_now} stage={g.get('stage')} "
           f"detail={clean_detail}")
        ok(f"M7[{block}] (SLOT-FREED KILLER — must be GREEN): the worker "
           "slot was REALLY released (a clean replica observed, never a "
           "trust-release)",
           eng.workers.get(agent_id, {}).get("status") == "released",
           f"worker_state={eng.workers.get(agent_id)}")
        ok(f"M7b[{block}] (STALE-SLOT KILLER — must be GREEN): the PERSISTED "
           "manifest['workers'] record — not just the rig's own stand-in — is "
           "marked `released` by core.tick.tick on close, so core/liveness.py "
           "(which iterates every non-`released` record) never STALLS a worker "
           "whose block is already ✅-closed (the T2-01-06 spurious-case root)",
           final_workers.get(agent_id, {}).get("status") == "released",
           f"persisted_worker={final_workers.get(agent_id)}")

    # ══ THE DEP-ORDERING KILLER ══
    # The REAL canon dep-gate is "01-01 ✅ on trunk" (`core/pipeline.py::
    # dispatchable`'s own predicate), OBSERVED the tick `gate.record`'s
    # `land_via_grant` sees real ancestry land — `done_tick`, captured above
    # from the tick-by-tick `outcomes`, not asserted from fixture intent.
    # `close_tick` (slot-teardown bookkeeping, strictly AFTER the block is
    # already ✅) is asserted with `>=`, not `>`: `core/tick.py`'s own
    # documented act-before-fill ordering guarantee lets a slot a gate frees
    # by closing get reused by SWITCHBOARD within that SAME bounded tick
    # (never a later one) — same-tick reuse here is the CORRECT, by-design
    # behavior this rig's own worker_count=1 run exercises, not a gap.
    ok("M8 (THE DEP-ORDERING KILLER — must be GREEN): 01-02 was NOT spawned "
       "until 01-01 was OBSERVED ✅ on trunk — spawn_tick(01-02) > "
       "done_tick(01-01), and never before its gate fully closed "
       "(spawn_tick(01-02) >= close_tick(01-01), same-tick slot reuse "
       "allowed) — captured from the REAL per-tick manifest/outcome reads",
       BLOCK_A in done_tick and BLOCK_A in close_tick and BLOCK_B in spawn_tick
       and spawn_tick[BLOCK_B] > done_tick[BLOCK_A]
       and spawn_tick[BLOCK_B] >= close_tick[BLOCK_A],
       f"done_tick[{BLOCK_A}]={done_tick.get(BLOCK_A)} "
       f"close_tick[{BLOCK_A}]={close_tick.get(BLOCK_A)} "
       f"spawn_tick[{BLOCK_B}]={spawn_tick.get(BLOCK_B)}")
    ok("M9: 01-03 (no deps) was free to spawn independent of the 01-01/01-02 "
       "dependency edge — spawned once BOTH 01-01 and 01-02 released the "
       "single worker_count=1 slot (never blocked by a dependency it "
       "doesn't have, only by slot contention)",
       BLOCK_C in spawn_tick and BLOCK_A in close_tick and BLOCK_B in close_tick
       and spawn_tick[BLOCK_C] > close_tick[BLOCK_A],
       f"spawn_tick[{BLOCK_C}]={spawn_tick.get(BLOCK_C)} "
       f"close_tick={ {b: close_tick.get(b) for b in ORDER} }")

    # ══ THE NO-DOUBLE-DISPATCH KILLER ══
    ok("M10 (SPAWN-COUNT KILLER — must be GREEN, ==1 each, 3 total): the "
       "(stubbed) process-spawn hook fired EXACTLY ONCE per block across the "
       "whole drive — no double-dispatch, whether across ticks or within one "
       "fill() call",
       sorted(a for a, _b in eng.spawn_calls) == sorted(BLOCKS[b]["agent_id"] for b in ORDER)
       and len(eng.spawn_calls) == 3,
       f"spawn_calls={eng.spawn_calls}")
    ok("M11: each block appears in exactly ONE tick's `spawned` list across "
       "the entire per-tick history — SWITCHBOARD never re-picked an "
       "already in-flight/done block for a second spawn",
       all(sum(1 for _i, _o, spawned, _se in tick_history
               if BLOCKS[b]["agent_id"] in spawned) == 1 for b in ORDER),
       f"per-tick spawned lists={[s for _, _, s, _ in tick_history]}")

    # ══ THE SESSION-END KILLERS ══
    ok("M12 (SESSION-END KILLER — must be GREEN): the tick loop emitted a "
       "clean session-end terminal (`session.check` -> a fresh "
       "{ended_at, reason} marker) only once ALL THREE blocks were ✅ AND "
       "nothing was left in-flight",
       session_ended_tick is not None
       and tick_history[session_ended_tick][3] is not None
       and all(final_gates.get(b, {}).get("stage") == gate.STAGE_CLOSED for b in ORDER),
       f"session_end marker={tick_history[session_ended_tick][3] if session_ended_tick is not None else None}")
    ok("M13: no EARLIER tick emitted a session-end (never ends while any "
       "block is still 📋-and-dispatchable, in-flight, or waiting on an "
       "unmet dep)",
       all(se is None for _i, _o, _s, se in tick_history[:session_ended_tick]),
       f"session_end per tick={[se for _, _, _, se in tick_history]}")
    ok("M14: the session-end marker was persisted DURABLY into the manifest "
       "(`manifest['session']['ended_at']`) — re-read fresh off disk, not "
       "just this call's own return value",
       bool((final_manifest.get("session") or {}).get("ended_at")),
       f"session={final_manifest.get('session')}")

    # ══ IDEMPOTENT RE-TICK — a further tick after end is a no-op ══
    pre_replay_manifest_bytes = open(tron_ctx.state, "rb").read()
    pre_replay_main = _git_out(["rev-parse", MAIN], root)
    pre_replay_spawn_calls = len(eng.spawn_calls)
    pre_replay_orders = len(eng.orders)
    res_replay = tick.tick(eng)
    post_replay_manifest_bytes = open(tron_ctx.state, "rb").read()
    post_replay_main = _git_out(["rev-parse", MAIN], root)
    ok("M15 (IDEMPOTENT RE-TICK KILLER — must be GREEN): a further "
       "`tick.tick(eng)` call AFTER session-end is a true no-op — reports "
       "the SAME session-end marker back, spawns nothing new, orders no "
       "worker, mutates neither the manifest nor real git",
       res_replay.get("session_end") == final_manifest.get("session")
       and res_replay["spawned"] == [] and res_replay["outcomes"] == {}
       and len(eng.spawn_calls) == pre_replay_spawn_calls
       and len(eng.orders) == pre_replay_orders
       and post_replay_manifest_bytes == pre_replay_manifest_bytes
       and post_replay_main == pre_replay_main,
       f"replay_result={res_replay} spawn_calls_before={pre_replay_spawn_calls} "
       f"spawn_calls_after={len(eng.spawn_calls)} "
       f"manifest_unchanged={post_replay_manifest_bytes == pre_replay_manifest_bytes} "
       f"main_unchanged={post_replay_main == pre_replay_main}")

    final_main = _git_out(["rev-parse", MAIN], root)
    total_real_lands = sum(real_land_calls.values())
    ok("FINAL (TERMINAL — must be GREEN): THREE real blocks, one with a real "
       "`Depends on` edge, starting from the PIPELINE alone (all 📋, no "
       "pre-seeded gates), each reached ✅ ON TRUNK + slot freed + gate "
       "CLOSED, dep-ordering held, exactly 3 spawns + exactly 6 real "
       "land.sh runs (2 per block: merge + record), and the run reached a "
       "clean, idempotent SESSION-END — a genuine multi-block dispatch-to-"
       "session-end drive, entirely via core.tick.tick",
       all(final_gates.get(b, {}).get("stage") == gate.STAGE_CLOSED for b in ORDER)
       and final_main != main_before
       and len(eng.spawn_calls) == 3
       and total_real_lands == 6
       and session_ended_tick is not None
       and bool((final_manifest.get("session") or {}).get("ended_at")),
       f"final_main={final_main} spawn_calls={len(eng.spawn_calls)} "
       f"total_real_lands={total_real_lands} real_land_calls={real_land_calls} "
       f"session={final_manifest.get('session')}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.multiblock_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"tron instance dir (real engine.ctx.Ctx)={inst}")
    print(f"manifest={tron_ctx.state}")
    print(f"BLOCKS={ORDER} (B depends_on A; C has none) worker_count=1")
    print(f"ticks used={ticks_used} (cap={MAX_TICKS}) session_ended_tick={session_ended_tick}")
    print(f"spawn_tick={spawn_tick}")
    print(f"done_tick (record_landed observed)={done_tick}")
    print(f"close_tick={close_tick}")
    print(f"spawn_tick(01-02) > done_tick(01-01): "
          f"{spawn_tick.get(BLOCK_B)} > {done_tick.get(BLOCK_A)} = "
          f"{spawn_tick.get(BLOCK_B, -1) > done_tick.get(BLOCK_A, -1)}")
    print(f"spawn_tick(01-02) >= close_tick(01-01) (same-tick reuse OK): "
          f"{spawn_tick.get(BLOCK_B)} >= {close_tick.get(BLOCK_A)} = "
          f"{spawn_tick.get(BLOCK_B, -1) >= close_tick.get(BLOCK_A, -1)}")
    print("per-tick outcomes: " + " | ".join(
        f"t{i}:{o}{'+spawn(' + ','.join(s) + ')' if s else ''}"
        f"{'+SESSION-END' if se else ''}"
        for i, o, s, se in tick_history))
    print(f"main before={main_before}")
    print(f"main after (final)={final_main}")
    print(f"spawn_calls (must be exactly 3, one per block)={eng.spawn_calls}")
    print(f"real land.sh invocations per case_id (must be 1 each, 6 total)="
          f"{real_land_calls}")
    print(f"session (durable manifest field)={final_manifest.get('session')}")
    print(f"idempotent re-tick result={res_replay}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
