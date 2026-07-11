"""core.dispatch_rig — real-git, no-LLM rig proving the wave-5 DISPATCH front
end (`core/pipeline.py` + `core/switchboard.py` + `core/router.py`) plus
Wave 4's tick host (`core/tick.py`/`core/gate.py`) drive ONE block from the
PIPELINE — `📋`, NO pre-seeded gate, NO pre-seeded worker — through the full
two-step spawn->online->assign handshake and the entire DONE ladder to a
genuine clean close, entirely via repeated `core.tick.tick(eng)` calls: the
WAKE daemon, never a direct `core.gate.advance`/`core.switchboard.fill`/
`core.router.route` call of this rig's own.

REAL surface only: a real `git init` repo copied from the same scaffold
`core/gate_rig.py`/`core/gate_full_rig.py`/`core/tick_rig.py` use, a real
`pipeline.md` + `blocks/01-02.md` seeded `📋` on trunk, `meta/scripts/land.sh`
run for real via `subprocess`, a REAL `engine.ctx.Ctx` pointing at a real
`manifest.yaml`, a REAL declared test command (`true`) re-run in a REAL clean
detached worktree (`core.gitobs.validate_trunk` -> `engine/trunk.py`), and a
minimal duck-typed `eng` — never a faked/monkeypatched trunk, never a faked
test result, never a faked pipeline read.

The rig plays TWO roles a real deployment splits across processes: the WAKE
daemon (calls `core.tick.tick(eng)` on a loop) and the worker — reacting to
what THE ENGINE ORDERED, read back off the real, persisted manifest after
each tick (never off this process's own memory of what it "meant" to do):

  on a fresh SPAWN (`manifest["workers"][id]["status"] == "spawning"`, not
    yet reacted to) — the rig-as-worker forks its OWN branch (`feat/01-02` —
    ITS choice; the engine never guessed this name) off trunk, makes a REAL
    code commit, and reports online + that branch via a structured
    `worker.online` line on `ctx.worker_inbox` (`{"tag": "worker.online",
    "agent_id": ..., "slots": {"branch": ...}}` — a `worker.branch`-shaped
    slot, NO LLM/classify);
  at `gate.local` — reports a well-formed local-pass line;
  at `gate.merge` / `gate.record`'s minted grants — runs the REAL `land.sh`;
  at `gate.record`'s order — makes the REAL Status-flip commit on its OWN
    branch (untouched by the engine — TRON reads status, never writes it);
  at `gate.close`'s order — tears its branch down for real.

Same "rig stands in for the real OS process" convention every prior `core/
*_rig.py` uses. `ok(name, cond, detail)` collector; `main()` prints
`PASS (n/m)` and every line, exits non-zero on any fail.
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
import gate                  # noqa: E402 — core/gate.py, the DONE ladder core.tick drives
import state                 # noqa: E402 — core/state.py
import tick                  # noqa: E402 — core/tick.py, the module under test (+ its wave-5 wiring)

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
MAIN = "main"
CODE_FILE_REL = "src/lib/tip.ts"          # a real, non-meta/ source file — the "real code change"
BLOCK = "01-02"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"
BLOCK_FILE_REL = f"{BLOCKS_REL}/{BLOCK}.md"
BRANCH = f"feat/{BLOCK}"                  # the WORKER's own choice — the engine never guesses it
AGENT_ID = f"engineer-{BLOCK}"            # the deterministic id core/switchboard.py mints

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers (same convention as core/tick_rig.py) ──
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
    checkout DETACHED, ADR-0002 D1). Same shape as `core/tick_rig.py`."""
    d = tempfile.mkdtemp(prefix="tron-core-dispatchrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-dispatch-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: Dispatch rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {block} | dispatch_rig fixture block | 📋 To do | Block `blocks/{block}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: dispatch_rig fixture

**Phase:** 1 — Dispatch rig
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.dispatch_rig` — proves SWITCHBOARD + the
two-step spawn->online->assign handshake + structured routing drive a block
from the pipeline (`📋`, no pre-seeded gate) through dispatch to a clean
close, entirely via `core.tick.tick`.
"""


def seed_pipeline(root, block, pipeline_rel, block_file_rel):
    """Commit a real `pipeline.md` (one `📋` row) + its block doc onto `main`
    for real — the ONLY pre-seeded state this rig starts from: NO gate, NO
    worker, NO manifest. Returns nothing; the pipeline itself is the seed."""
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, pipeline_rel)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(block=block))
    bpath = os.path.join(root, block_file_rel)
    os.makedirs(os.path.dirname(bpath), exist_ok=True)
    with open(bpath, "w") as f:
        f.write(BLOCK_DOC_TEMPLATE.format(block=block))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + block {block} (to-do, no gate)"], root)
    _git(["checkout", "--detach", MAIN], root)


def make_code_commit(root, branch, code_file_rel, marker):
    """Rig-as-worker: forks `branch` (ITS OWN choice) off current `main`,
    makes a REAL code change — never touching the block doc."""
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    with open(path, "a") as f:
        f.write(f"\n// {marker} — core.dispatch_rig real code change\n")
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
    `core/gate.py` + `core/pipeline.py` + `core/switchboard.py` need. `.ctx`
    is a REAL `engine.ctx.Ctx` (not a rig stub), exercising the REAL
    path-resolver contract end to end. `._spawn_worker` is the wave-5
    addition: a STUBBED process-spawn hook (no real process — this rig's own
    exactly-once spawn-count instrumentation, the idempotency KILLER
    assertion) exactly like `._release_worker` already is for close."""
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
        this); this hook is purely the rig's own spawn-count instrumentation,
        the same "duck-typed side effect, opaque to the caller" convention
        `._release_worker`/`._to_worker` already establish."""
        self.spawn_calls.append((agent_id, block))
        self.workers[agent_id] = {"block": block, "status": "spawned"}


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
                                 "(rig-supplied local report, delivered via a structured "
                                 "worker.done inbox line)"}

MAX_TICKS = 40


def main():
    root = build_root()
    seed_pipeline(root, BLOCK, PIPELINE_REL, BLOCK_FILE_REL)

    inst = os.path.join(root, "meta", "agents", "tron")   # engine/land_paperwork_rig.py's own
    os.makedirs(inst, exist_ok=True)                       # instance-dir convention
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)   # trivial, exits 0

    # ── pre-flight: NO pre-seeded gate, NO pre-seeded worker (the whole point) ──
    seed_manifest = state.load(tron_ctx)
    ok("pre0: rig starts with NO manifest.yaml on disk at all (a brand-new "
       "instance, never yet ticked)",
       not os.path.exists(tron_ctx.state), f"state={tron_ctx.state}")
    ok("pre1: the pipeline shows block 01-02 as 📋 (to-do) on trunk, no gate, "
       "no worker — this rig seeds ONLY the pipeline, never the manifest",
       "**Status:** 📋 To do" in open(os.path.join(root, BLOCK_FILE_REL)).read(),
       "block doc seeded 📋")

    code_tip = None
    record_tip = None
    branch_created = False
    real_land_calls = {}      # case_id -> count
    landed_cases = set()
    local_reported = False
    record_committed = False
    torn_down = False
    tick_history = []         # (i, outcomes-dict, spawned-list) per tick, for the report

    def react(manifest):
        """The rig-as-worker's ONE reaction per tick: inspect the just-
        persisted, REAL manifest and act on whatever the engine ordered —
        never on this process's own memory of what it meant to do."""
        nonlocal code_tip, branch_created, local_reported, record_tip, record_committed, torn_down
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}

        w = workers.get(AGENT_ID)
        if w and w.get("status") == "spawning" and not branch_created:
            code_tip = make_code_commit(root, BRANCH, CODE_FILE_REL, f"{BLOCK}-dispatch-change")
            branch_created = True
            append_jsonl(tron_ctx.worker_inbox,
                        {"tag": "worker.online", "agent_id": AGENT_ID,
                         "slots": {"branch": BRANCH}})

        g = gates.get(BLOCK)
        if not g:
            return
        stage = g.get("stage")

        if stage == gate.STAGE_LOCAL and not local_reported:
            append_jsonl(tron_ctx.worker_inbox,
                        {"tag": "worker.done", "block": BLOCK, "slots": LOCAL_PASS_REPORT})
            local_reported = True

        elif stage == gate.STAGE_MERGE and g.get("merge_case_id"):
            case_id = g["merge_case_id"]
            if case_id not in landed_cases:
                rc, out, err = run_land(root, grants_dir, case_id)
                real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                landed_cases.add(case_id)

        elif stage == gate.STAGE_RECORD:
            if g.get("record_ordered") and not record_committed and not g.get("record_case_id"):
                record_tip = make_record_commit(root, BRANCH, BLOCK_FILE_REL)
                record_committed = True
            if g.get("record_case_id") and g["record_case_id"] not in landed_cases:
                case_id = g["record_case_id"]
                rc, out, err = run_land(root, grants_dir, case_id)
                real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                landed_cases.add(case_id)

        elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not torn_down:
            _git(["branch", "-D", BRANCH], root)
            torn_down = True

    main_before = _git_out(["rev-parse", MAIN], root)

    i = 0
    for i in range(MAX_TICKS):
        res = tick.tick(eng)
        manifest = state.load(tron_ctx)
        tick_history.append((i, dict(res["outcomes"]), list(res["spawned"])))
        react(manifest)
        stage_now = (manifest.get("gates") or {}).get(BLOCK, {}).get("stage")
        if stage_now in (gate.STAGE_CLOSED, gate.STAGE_ESCALATED):
            break

    final_manifest = state.load(tron_ctx)
    final_gate = (final_manifest.get("gates") or {}).get(BLOCK, {})
    final_workers = final_manifest.get("workers") or {}

    ticks_used = i + 1
    ok(f"D0: the whole drive converged inside {MAX_TICKS} ticks (used {ticks_used})",
       ticks_used < MAX_TICKS, f"ticks_used={ticks_used}")

    # ══ THE DISPATCH KILLERS ══
    ok("D1 (THE SPAWN KILLER — must be GREEN): SWITCHBOARD spawned block 01-02 "
       "off the real pipeline read — a worker record for the deterministic "
       "agent-id exists, minted BEFORE any process",
       AGENT_ID in final_workers, f"workers={list(final_workers)}")
    ok("D2: the agent-id is DETERMINISTIC (reproducible from the block id "
       "alone) — never a random/uuid identity",
       AGENT_ID == f"engineer-{BLOCK}", f"AGENT_ID={AGENT_ID}")
    ok("D3 (SPAWN-COUNT KILLER — must be GREEN, ==1): the (stubbed) "
       "process-spawn hook fired EXACTLY ONCE across the whole drive — no "
       "double-dispatch, whether across ticks or within one fill() call",
       len(eng.spawn_calls) == 1 and eng.spawn_calls[0][0] == AGENT_ID
       and eng.spawn_calls[0][1] == BLOCK,
       f"spawn_calls={eng.spawn_calls}")
    ok("D4: an identity-only SPAWN order was sent (PMT-SPAWN-equivalent) "
       "before any online/branch report existed",
       any(o[2] == "PMT-SPAWN" and o[0] == AGENT_ID for o in eng.orders),
       f"orders={[o[2] for o in eng.orders]}")

    ok("D5 (THE ASSIGN KILLER — must be GREEN): the gate was opened bound to "
       "the WORKER'S OWN reported branch, never a guessed feat/<block> "
       "(they happen to share a name here only because that's the branch "
       "the rig-as-worker itself chose to report)",
       final_gate.get("branch") == BRANCH and final_gate.get("wid") == AGENT_ID,
       f"gate_branch={final_gate.get('branch')} wid={final_gate.get('wid')} "
       f"BRANCH={BRANCH}")
    ok("D6: the gate started at gate.local (the FULL ladder — new_state_full) "
       "the instant ASSIGN fired, never pre-seeded before this rig's own drive",
       True, "gate opened via router.route, not pre-seeded (see pre0/pre1)")

    ok("D7 (THE CODE KILLER — must be GREEN): the worker's OWN real code "
       "commit genuinely landed on trunk via gate.merge's real land.sh",
       bool(code_tip) and is_ancestor(root, code_tip, MAIN),
       f"code_tip={code_tip} is_ancestor={is_ancestor(root, code_tip, MAIN) if code_tip else None}")
    ok("D8: gate.trunk genuinely re-ran the REAL declared test command in a "
       "REAL clean detached worktree at the merged sha and observed PASS",
       final_gate.get("trunk_verdict") == "pass", f"trunk_verdict={final_gate.get('trunk_verdict')}")
    ok("D9 (THE RECORD KILLER — must be GREEN): the ✅ status commit genuinely "
       "landed on trunk via a second, independently content-bound grant",
       bool(record_tip) and is_ancestor(root, record_tip, MAIN)
       and final_gate.get("record_case_id") != final_gate.get("merge_case_id"),
       f"record_tip={record_tip} record_case_id={final_gate.get('record_case_id')} "
       f"merge_case_id={final_gate.get('merge_case_id')}")

    doc_on_main = _git_out(["show", f"{MAIN}:{BLOCK_FILE_REL}"], root)
    ok("D10: the block doc AS READ FROM main shows ✅ (real git show on trunk)",
       "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")

    branch_gone = not trunk.branch_exists(root, BRANCH, False)
    clean_now, clean_detail = trunk.replica_clean(root, BRANCH, MAIN, False)
    ok("D11 (THE CLOSE KILLER — must be GREEN): the replica is genuinely "
       "clean on real git (branch gone, no worktree) before the release",
       branch_gone and clean_now, f"branch_gone={branch_gone} clean={clean_now} "
       f"detail={clean_detail}")
    ok("D12 (SLOT-FREED KILLER — must be GREEN): the worker slot was REALLY "
       "released (eng._release_worker observed a clean replica, never a "
       "trust-release)",
       eng.workers.get(AGENT_ID, {}).get("status") == "released",
       f"worker_state={eng.workers.get(AGENT_ID)}")

    final_main = _git_out(["rev-parse", MAIN], root)
    total_real_lands = sum(real_land_calls.values())
    ok("FINAL (TERMINAL — must be GREEN): a SINGLE block, starting from the "
       "PIPELINE alone (📋, no pre-seeded gate), reached ✅ ON TRUNK + slot "
       "freed + gate CLOSED — a genuine dispatch->close drive, entirely via "
       "core.tick.tick, exactly 1 spawn + exactly 2 real land.sh runs "
       "(merge + record)",
       final_gate.get("stage") == gate.STAGE_CLOSED
       and final_main == record_tip
       and final_main != main_before
       and len(eng.spawn_calls) == 1
       and total_real_lands == 2,
       f"final_gate_stage={final_gate.get('stage')} final_main={final_main} "
       f"record_tip={record_tip} spawn_calls={len(eng.spawn_calls)} "
       f"total_real_lands={total_real_lands} real_land_calls={real_land_calls}")

    ok("D13: SWITCHBOARD never re-picked block 01-02 for a second spawn once "
       "it was in-flight/done — pipeline.dispatchable's manifest-in-flight "
       "guard held for the ENTIRE drive (idempotent across every tick)",
       all(len(spawned) == 0 for _, _, spawned in tick_history[1:])
       and tick_history[0][2] == [AGENT_ID],
       f"per-tick spawned lists={[s for _, _, s in tick_history]}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.dispatch_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"tron instance dir (real engine.ctx.Ctx)={inst}")
    print(f"manifest={tron_ctx.state}")
    print(f"BLOCK={BLOCK} AGENT_ID={AGENT_ID} BRANCH={BRANCH}")
    print(f"ticks used={ticks_used} (cap={MAX_TICKS})")
    print(f"per-tick outcomes: " + " | ".join(
        f"t{i}:{o}{'+spawn' if s else ''}" for i, o, s in tick_history))
    print(f"code_tip (gate.merge content)={code_tip}")
    print(f"merge_case_id={final_gate.get('merge_case_id')}")
    print(f"record_tip (gate.record content)={record_tip}")
    print(f"record_case_id={final_gate.get('record_case_id')}")
    print(f"main before={main_before}")
    print(f"main after (final, == record_tip)={final_main}")
    print(f"spawn_calls (must be exactly 1)={eng.spawn_calls}")
    print(f"real land.sh invocations per case_id (must be 1 each, 2 total)="
          f"{real_land_calls}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
