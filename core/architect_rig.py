"""core.architect_rig — real-git, no-LLM rig proving `core.architect`
(wave 9: the persistent, POOL-EXCLUDED architect; M-05's reconcile-gate)
does exactly what `contracts/blueprint-contracts.md` §1 "Architect" and
`contracts/rebuild-spec.md` C6/D1/T5 promise, entirely via repeated
`core.tick.tick(eng)` calls (the WAKE daemon) — never a direct
`core.architect.enqueue`/`.advance` call of this rig's own.

REAL surface only: a real `git init` repo copied from the SAME scaffold
every prior `core/*_rig.py` uses, `meta/scripts/land.sh` run for real via
`subprocess`, a REAL `engine.ctx.Ctx` pointing at a real `manifest.yaml`, a
REAL declared test command (`true`) re-run in a REAL clean detached
worktree (`core.gitobs.validate_trunk` -> `engine/trunk.py`), and a minimal
duck-typed `eng` — never a faked/monkeypatched trunk, never a faked test
result, never a faked pipeline read, never fake content for a forward job.

The rig plays THREE roles a real deployment splits across processes: the
WAKE daemon (calls `core.tick.tick(eng)` on a loop), the ordinary worker
(exactly like `core/multiblock_rig.py`'s own react() — forks its OWN
branch, reports online, local-passes, runs the REAL `land.sh` when a gate
mints a grant, makes the REAL ✅ record commit, tears its branch down when
ordered to close), and — NEW this brick — the scripted ARCHITECT: reacts to
`manifest["architect"]["current_job"]` (read back off the real, persisted
manifest after each tick, never this process's own memory) exactly the same
way:
  a `reconcile` job, once ordered (`job["ordered"]` True) — the architect
    has NO content to check in this brick (no LLM here, structured only,
    per the wave-9 spec) — reports done via a structured `architect.
    reconciled` line on `ctx.worker_inbox`, EXACTLY once;
  a `forward` job, once ordered — forks `arch/<block>-forward` off CURRENT
    trunk, writes a REAL, parseable block doc (`meta/blocks/<block>.md`,
    Status `📋 To do`), commits it; once the gate mints a grant for it
    (`job["case_id"]` shows up), runs the REAL `land.sh` for that case,
    exactly like a worker does for its own merge/record grants.

Two independent scenarios, each its OWN real-git tempdir/manifest (never
sharing state — the SAME "one root per scenario" discipline `core/gate_rig.
py`'s BLOCK_A/BLOCK_B split already uses):

  SCENARIO 1 — the RECONCILE-GATE ordering killer (M-05): a real two-block
    pipeline, `01-01` (no deps) then `01-02` (`Depends on: 01-01`, ALSO the
    M-05 reconcile target — the next in-scope block by living-doc order),
    `worker_count=2` (deliberately NOT 1 — slot contention must never be
    why `01-02` waits; only the reconcile gate may be). Asserts the
    STRICT ordering `spawn_tick(01-02) > reconciled_tick(01-02) >
    done_tick(01-01)`, a clean run to BOTH ✅ + CLOSED + a genuine clean
    SESSION-END, and dedupe (exactly one reconcile ever enqueued for the
    01-01 -> 01-02 edge, never re-enqueued once `01-02` is done, an
    idempotent re-tick after session-end changes nothing).

  SCENARIO 2 — the FORWARD killer: a real two-block pipeline, `02-01` (a
    normal, file'd block, no deps) alongside `02-02` — a roadmap row with
    NO block file at seed (`has_block_file=False`; `02-01` stays genuinely
    in-flight/pending the whole time specifically so `core/session.py::
    check`'s own "no block file -> invisible to scope" read never lets the
    run settle BEFORE the architect's forward job even starts — see the
    `_enqueue_forward_jobs` call site's own note). Asserts the architect's
    `forward` job authors + REAL-lands `02-02`'s block file under a
    content-bound grant (`core.landing.paperwork_case_id("forward", ...)`),
    `02-02` becomes dispatchable the instant it's observed on trunk, and
    drives to a genuine ✅ + CLOSED the SAME way any ordinary block does —
    plus a clean SESSION-END once BOTH blocks are done.

`eng._spawn_architect()` — the ONE new stubbed hook this brick's `MiniEng`
implements (never touched by any of the other 8 prior rigs' own `eng`
stand-ins: `core/architect.py::advance` calls it lazily, exactly once, only
the first tick it actually pops a queued job — none of gate_rig/
gate_full_rig/landing_rig ever call `core.tick.tick` at all, and tick_rig/
dispatch_rig/sentry_rig/casestate_rig's own fixtures never populate
`architect_queue` — see each one's own pipeline shape for why).

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.
"""
import os
import sys
import shutil
import subprocess
import tempfile
import json

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # grants.py / trunk.py / ctx.py live here
sys.path.insert(0, HERE)                                 # core/{gate,state,snapshot,tick,...}.py

import grants               # noqa: E402 — respected contract, real, unmodified
import trunk                 # noqa: E402 — respected contract, real, unmodified
from ctx import Ctx          # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import gate                  # noqa: E402 — core/gate.py, the DONE ladder core.tick drives
import state                 # noqa: E402 — core/state.py
import tick                  # noqa: E402 — core/tick.py, wave 9's architect-enqueue/advance wiring
import architect              # noqa: E402 — core/architect.py, the module under test
from engine import Engine as CoreEngine  # noqa: E402 — core/engine.py, R-A's REAL implementation
import jobs                    # noqa: E402 — engine/jobs.py, the runner-consumption seam (HWM file)

import scaffold_src               # noqa: E402 — core/scaffold_src.py, the ONE resolver

SCAFFOLD_SRC = scaffold_src.resolve()
MAIN = "main"
CODE_FILE_REL = "src/lib/tip.ts"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers (same convention as core/multiblock_rig.py) ──
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
    d = tempfile.mkdtemp(prefix="tron-core-architectrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-architect-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


def ensure_rebased(root, branch):
    """Real rebase-if-behind, same discipline as `core/casestate_rig.py`'s
    own helper — needed here because `worker_count=2` runs blocks (and the
    architect's own forward branch) concurrently, so a branch can genuinely
    fall behind trunk between its own creation and its land attempt."""
    _git(["checkout", branch], root)
    r = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", MAIN, branch])
    if r.returncode != 0:
        _git(["rebase", MAIN], root)
    _git(["checkout", "--detach", MAIN], root)


def make_code_commit(root, branch, code_file_rel, marker):
    """Writes a BRAND-NEW file unique to `branch` (never a shared append
    target) — sidesteps concurrent-branch rebase conflicts entirely (this
    rig's `worker_count=2` runs blocks genuinely concurrently, unlike
    `core/multiblock_rig.py`'s strict `worker_count=1` serialization, where
    two branches sharing one appended-to file never need a rebase against
    each other in the first place)."""
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(f"// {marker} — core.architect_rig real code change\n")
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


def make_forward_block_doc(root, branch, block, block_file_rel, depends_on="none"):
    """The rig-as-architect authoring a REAL, parseable missing block file
    on its OWN `arch/<block>-forward` branch — the ONLY content this rig
    ever writes for a `forward` job (never touching any OTHER block's
    doc)."""
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, block_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(FORWARD_BLOCK_DOC_TEMPLATE.format(block=block, depends_on=depends_on))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"arch(forward): author missing block file {block}"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def run_land(root, grants_dir, case_id):
    r = subprocess.run(
        ["bash", os.path.join(root, "meta", "scripts", "land.sh"), case_id,
         "--main", MAIN, "--grants-dir", grants_dir],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "LAND_MAIN_BRANCH": MAIN})
    return r.returncode, r.stdout, r.stderr


def append_jsonl(path, obj):
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
    `core/session.py` + `core/architect.py` (via `core/tick.py`) need.
    `._spawn_architect` is wave 9's ONE new stubbed hook — a spawn-count
    instrumentation exactly like `._spawn_worker` already is, never touched
    unless `core/architect.py::advance` actually pops a queued job."""
    def __init__(self, root, tron_ctx, test_command, worker_count=2):
        self.paths = {
            "root": root,
            "main_branch": MAIN,
            "test_command": test_command,
            "test_env": None,
            "ci_check_name": None,
            "worker_count": worker_count,
            "pipeline_rel": PIPELINE_REL,
            "blocks_rel": BLOCKS_REL + "/",
        }
        self.dry = False
        self.ctx = tron_ctx
        self.events = _Events()
        self.log_lines = []
        self.orders = []
        self.workers = {}
        self.spawn_calls = []
        self.architect_spawns = []

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
        self.spawn_calls.append((agent_id, block))
        self.workers[agent_id] = {"block": block, "status": "spawned"}

    def _spawn_architect(self):
        self.architect_spawns.append(True)

    def _page_operator(self, case_id, block, detail, worker_id=None, manifest=None):
        # Rig stub for the R1b LOUD backstop path (a genuine triage the architect
        # could not verdict resolves to 'operator' -> casestate pages). Records the
        # page and returns a delivered receipt, exactly the shape casestate reads.
        self.operator_pages = getattr(self, "operator_pages", [])
        self.operator_pages.append({"case_id": case_id, "block": block,
                                    "detail": detail, "worker_id": worker_id})
        return "delivered"


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
                                 "(rig-supplied local report, delivered via a structured "
                                 "worker.done inbox line)"}

MAX_TICKS = 150

PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: architect_rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
{rows}
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: architect_rig fixture

**Phase:** 1 — architect_rig
**Status:** 📋 To do
**Depends on:** {depends_on}
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.architect_rig`.
"""

FORWARD_BLOCK_DOC_TEMPLATE = """# Block {block}: architect-forwarded fixture

**Phase:** 1 — architect_rig
**Status:** 📋 To do
**Depends on:** {depends_on}
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Authored by the SCRIPTED ARCHITECT (`core.architect_rig`, playing a real
`forward` job) — a genuinely missing block file, landed via
`core.landing.land_via_grant` under a content-bound case-id.
"""


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 1 — the RECONCILE-GATE ordering killer (M-05)
# ═══════════════════════════════════════════════════════════════════════
BLOCK_X, BLOCK_Y = "01-01", "01-02"


def run_reconcile_gate_scenario():
    root = build_root()
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    rows = (
        f"| {BLOCK_X} | fixture block X (no deps) | 📋 To do | Block `blocks/{BLOCK_X}.md` |\n"
        f"| {BLOCK_Y} | fixture block Y (depends on {BLOCK_X}) | 📋 To do | Block `blocks/{BLOCK_Y}.md` |"
    )
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(rows=rows))
    for block, dep in ((BLOCK_X, "none"), (BLOCK_Y, BLOCK_X)):
        bpath = os.path.join(root, BLOCKS_REL, f"{block}.md")
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        with open(bpath, "w") as f:
            f.write(BLOCK_DOC_TEMPLATE.format(block=block, depends_on=dep))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + blocks {BLOCK_X}/{BLOCK_Y} "
                          f"({BLOCK_Y} depends on {BLOCK_X}, all to-do, no gates)"], root)
    _git(["checkout", "--detach", MAIN], root)

    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    # worker_count=2 — DELIBERATELY not 1: 01-02's own dep on 01-01 is
    # already satisfied the instant 01-01 lands, and a free slot is
    # available too (both slots never contended for) — the ONLY thing
    # that can still hold 01-02 back is the M-05 reconcile gate itself.
    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=2)

    branch = {BLOCK_X: f"feat/{BLOCK_X}", BLOCK_Y: f"feat/{BLOCK_Y}"}
    agent_id = {BLOCK_X: f"engineer-{BLOCK_X}", BLOCK_Y: f"engineer-{BLOCK_Y}"}

    branch_created = {BLOCK_X: False, BLOCK_Y: False}
    local_reported = {BLOCK_X: False, BLOCK_Y: False}
    record_committed = {BLOCK_X: False, BLOCK_Y: False}
    torn_down = {BLOCK_X: False, BLOCK_Y: False}
    landed_cases = set()
    real_land_calls = {}
    reconciled_reported = set()

    spawn_tick = {}
    done_tick = {}
    reconciled_tick = {}
    close_tick = {}
    tick_history = []

    def react(i, manifest):
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}

        for block in (BLOCK_X, BLOCK_Y):
            aid, br = agent_id[block], branch[block]
            block_file_rel = f"{BLOCKS_REL}/{block}.md"

            w = workers.get(aid)
            if w and block not in spawn_tick:
                spawn_tick[block] = i
            if w and w.get("status") == "spawning" and not branch_created[block]:
                make_code_commit(root, br, f"src/lib/{block}.ts", f"{block}-architectrig-change")
                branch_created[block] = True
                append_jsonl(tron_ctx.worker_inbox,
                            {"tag": "worker.online", "agent_id": aid, "slots": {"branch": br}})

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
                    ensure_rebased(root, br)
                    run_land(root, grants_dir, case_id)
                    real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                    landed_cases.add(case_id)
            elif stage == gate.STAGE_RECORD:
                if g.get("record_ordered") and not record_committed[block] and not g.get("record_case_id"):
                    make_record_commit(root, br, block_file_rel)
                    record_committed[block] = True
                if g.get("record_case_id") and g["record_case_id"] not in landed_cases:
                    case_id = g["record_case_id"]
                    ensure_rebased(root, br)
                    run_land(root, grants_dir, case_id)
                    real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                    landed_cases.add(case_id)
            elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not torn_down[block]:
                _git(["branch", "-D", br], root)
                torn_down[block] = True

            if stage == gate.STAGE_CLOSED and block not in close_tick:
                close_tick[block] = i

        # ── the SCRIPTED ARCHITECT: react to whatever job it currently
        #     holds — a `reconcile` job needs NO content-check in this
        #     brick (no LLM here), so once it's been ORDERED, report done
        #     via a structured `architect.reconciled` line, exactly once ──
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if cur and cur.get("kind") == "reconcile" and cur.get("ordered") \
                and cur.get("block") not in reconciled_reported:
            append_jsonl(tron_ctx.worker_inbox,
                        {"tag": "architect.reconciled", "block": cur["block"]})
            reconciled_reported.add(cur["block"])

    i = 0
    session_ended_tick = None
    for i in range(MAX_TICKS):
        res = tick.tick(eng)
        manifest = state.load(tron_ctx)
        se = res.get("session_end")
        tick_history.append((i, dict(res["outcomes"]), list(res["spawned"]), se))
        react(i, manifest)
        for block, arch_manifest in ((BLOCK_X, manifest), (BLOCK_Y, manifest)):
            reconciled = set((manifest.get("reconciled") or []))
            if block in reconciled and block not in reconciled_tick:
                reconciled_tick[block] = i
        if se is not None and session_ended_tick is None:
            session_ended_tick = i
            break

    for _i, _outcomes, _spawned, _se in tick_history:
        for _b, (_outcome, _detail) in _outcomes.items():
            if _outcome == "record_landed" and _b not in done_tick:
                done_tick[_b] = _i

    final_manifest = state.load(tron_ctx)
    final_gates = final_manifest.get("gates") or {}
    ticks_used = i + 1

    ok("S1-M0: SCENARIO 1 (reconcile-gate) converged to a clean session-end "
       f"inside {MAX_TICKS} ticks (used {ticks_used})",
       session_ended_tick is not None and ticks_used < MAX_TICKS,
       f"ticks_used={ticks_used} session_ended_tick={session_ended_tick}")

    ok("S1-K1 (RECONCILE-GATE ORDERING KILLER — must be GREEN): STRICT "
       "spawn_tick(01-02) > reconciled_tick(01-02) > done_tick(01-01) — "
       "captured off the REAL per-tick manifest/outcome reads, never "
       "asserted from fixture intent",
       BLOCK_X in done_tick and BLOCK_Y in reconciled_tick and BLOCK_Y in spawn_tick
       and reconciled_tick[BLOCK_Y] > done_tick[BLOCK_X]
       and spawn_tick[BLOCK_Y] > reconciled_tick[BLOCK_Y],
       f"done_tick[{BLOCK_X}]={done_tick.get(BLOCK_X)} "
       f"reconciled_tick[{BLOCK_Y}]={reconciled_tick.get(BLOCK_Y)} "
       f"spawn_tick[{BLOCK_Y}]={spawn_tick.get(BLOCK_Y)}")

    ok("S1-K2: 01-02 was NEVER dispatched before its formal dep (01-01 done) "
       "either — belt-and-suspenders, the ordinary dependency gate still "
       "holds too",
       spawn_tick.get(BLOCK_Y, -1) > done_tick.get(BLOCK_X, 1 << 30),
       f"spawn_tick[{BLOCK_Y}]={spawn_tick.get(BLOCK_Y)} done_tick[{BLOCK_X}]={done_tick.get(BLOCK_X)}")

    for block in (BLOCK_X, BLOCK_Y):
        g = final_gates.get(block, {})
        doc_on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{block}.md"], root)
        ok(f"S1-K3[{block}] (BOTH-✅ KILLER — must be GREEN): the block doc "
           "AS READ FROM main shows ✅ (real git show on trunk)",
           "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")
        branch_gone = not trunk.branch_exists(root, branch[block], False)
        clean_now, clean_detail = trunk.replica_clean(root, branch[block], MAIN, False)
        ok(f"S1-K4[{block}]: replica genuinely clean + gate CLOSED + slot "
           "really released",
           branch_gone and clean_now and g.get("stage") == gate.STAGE_CLOSED
           and eng.workers.get(agent_id[block], {}).get("status") == "released",
           f"branch_gone={branch_gone} clean={clean_now} stage={g.get('stage')} "
           f"detail={clean_detail} worker={eng.workers.get(agent_id[block])}")

    reconcile_enqueue_lines = [msg for _ch, msg in eng.log_lines
                               if f"enqueued reconcile for {BLOCK_Y!r}" in msg]
    ok("S1-K5 (DEDUPE KILLER — must be GREEN): exactly ONE reconcile was "
       "ever enqueued for the 01-01 -> 01-02 edge across the WHOLE drive "
       "(never re-enqueued while queued/current/already-reconciled)",
       len(reconcile_enqueue_lines) == 1,
       f"reconcile_enqueue_lines={reconcile_enqueue_lines}")

    architect_final = final_manifest.get("architect") or {}
    ok("S1-K6: the architect is IDLE with an EMPTY queue at the end — no "
       "lingering job, nothing to re-forward/re-reconcile",
       architect_final.get("status") == "idle" and architect_final.get("current_job") is None
       and not (final_manifest.get("architect_queue") or []),
       f"architect={architect_final} queue={final_manifest.get('architect_queue')}")

    # ── idempotent re-tick: session already ended -> a further tick.tick
    #     is a TRUE no-op — never re-enqueues/re-orders anything for
    #     either block, real git/manifest byte-identical ──
    pre_bytes = open(tron_ctx.state, "rb").read()
    pre_main = _git_out(["rev-parse", MAIN], root)
    pre_orders = len(eng.orders)
    res_replay = tick.tick(eng)
    post_bytes = open(tron_ctx.state, "rb").read()
    post_main = _git_out(["rev-parse", MAIN], root)
    ok("S1-K7 (IDEMPOTENT RE-TICK KILLER — must be GREEN): a further tick "
       "after session-end never re-enqueues/re-orders anything (a `done` "
       "block is NEVER re-forwarded/re-reconciled) — manifest + real git "
       "byte-identical, no new order",
       res_replay.get("spawned") == [] and res_replay.get("outcomes") == {}
       and len(eng.orders) == pre_orders
       and post_bytes == pre_bytes and post_main == pre_main,
       f"replay={res_replay} orders_before={pre_orders} orders_after={len(eng.orders)}")

    print(f"\n== SCENARIO 1 (reconcile-gate) ==")
    print(f"root={root}")
    print(f"ticks used={ticks_used} (cap={MAX_TICKS}) session_ended_tick={session_ended_tick}")
    print(f"spawn_tick={spawn_tick}")
    print(f"done_tick(record_landed observed)={done_tick}")
    print(f"reconciled_tick={reconciled_tick}")
    print(f"close_tick={close_tick}")
    print("per-tick outcomes: " + " | ".join(
        f"t{i}:{o}{'+spawn(' + ','.join(s) + ')' if s else ''}{'+SESSION-END' if se else ''}"
        for i, o, s, se in tick_history))
    print(f"reconcile_enqueue_lines={reconcile_enqueue_lines}")
    print(f"architect(final)={architect_final}")


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 2 — the FORWARD killer
# ═══════════════════════════════════════════════════════════════════════
BLOCK_P, BLOCK_Q = "02-01", "02-02"


def run_forward_scenario():
    root = build_root()
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    rows = (
        f"| {BLOCK_P} | fixture block P (no deps, has a file) | 📋 To do | Block `blocks/{BLOCK_P}.md` |\n"
        f"| {BLOCK_Q} | fixture block Q (MISSING its block file) | 📋 To do | (architect forwards this) |"
    )
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(rows=rows))
    bpath = os.path.join(root, BLOCKS_REL, f"{BLOCK_P}.md")
    os.makedirs(os.path.dirname(bpath), exist_ok=True)
    with open(bpath, "w") as f:
        f.write(BLOCK_DOC_TEMPLATE.format(block=BLOCK_P, depends_on="none"))
    # deliberately NO blocks/02-02.md on trunk at seed — the forward target.
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + block {BLOCK_P} ({BLOCK_Q} has NO "
                          f"block file yet — the forward target)"], root)
    _git(["checkout", "--detach", MAIN], root)

    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=2)

    branch = {BLOCK_P: f"feat/{BLOCK_P}", BLOCK_Q: f"feat/{BLOCK_Q}"}
    agent_id = {BLOCK_P: f"engineer-{BLOCK_P}", BLOCK_Q: f"engineer-{BLOCK_Q}"}
    forward_branch = architect._forward_branch(BLOCK_Q)   # "arch/02-02-forward"

    branch_created = {BLOCK_P: False, BLOCK_Q: False}
    local_reported = {BLOCK_P: False, BLOCK_Q: False}
    record_committed = {BLOCK_P: False, BLOCK_Q: False}
    torn_down = {BLOCK_P: False, BLOCK_Q: False}
    landed_cases = set()
    real_land_calls = {}
    forward_authored = False
    forward_tip = None
    forward_landed_tick = None
    q_has_file_tick = None
    q_spawn_tick = None

    tick_history = []

    def react(i, manifest):
        nonlocal forward_authored, forward_tip, forward_landed_tick, q_spawn_tick
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}

        for block in (BLOCK_P, BLOCK_Q):
            aid, br = agent_id[block], branch[block]
            block_file_rel = f"{BLOCKS_REL}/{block}.md"

            w = workers.get(aid)
            if w and block == BLOCK_Q and q_spawn_tick is None:
                q_spawn_tick = i
            if w and w.get("status") == "spawning" and not branch_created[block]:
                make_code_commit(root, br, f"src/lib/{block}.ts", f"{block}-architectrig-change")
                branch_created[block] = True
                append_jsonl(tron_ctx.worker_inbox,
                            {"tag": "worker.online", "agent_id": aid, "slots": {"branch": br}})

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
                    ensure_rebased(root, br)
                    run_land(root, grants_dir, case_id)
                    real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                    landed_cases.add(case_id)
            elif stage == gate.STAGE_RECORD:
                if g.get("record_ordered") and not record_committed[block] and not g.get("record_case_id"):
                    make_record_commit(root, br, block_file_rel)
                    record_committed[block] = True
                if g.get("record_case_id") and g["record_case_id"] not in landed_cases:
                    case_id = g["record_case_id"]
                    ensure_rebased(root, br)
                    run_land(root, grants_dir, case_id)
                    real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                    landed_cases.add(case_id)
            elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not torn_down[block]:
                _git(["branch", "-D", br], root)
                torn_down[block] = True

        # ── the SCRIPTED ARCHITECT: react to a `forward` job ──
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if cur and cur.get("kind") == "forward" and cur.get("block") == BLOCK_Q:
            if cur.get("ordered") and not forward_authored:
                forward_tip = make_forward_block_doc(
                    root, forward_branch, BLOCK_Q, f"{BLOCKS_REL}/{BLOCK_Q}.md", depends_on="none")
                forward_authored = True
            case_id = cur.get("case_id")
            if case_id and case_id not in landed_cases:
                ensure_rebased(root, forward_branch)
                run_land(root, grants_dir, case_id)
                real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                landed_cases.add(case_id)
                if is_ancestor(root, forward_tip, MAIN) and forward_landed_tick is None:
                    forward_landed_tick = i

    i = 0
    session_ended_tick = None
    for i in range(MAX_TICKS):
        res = tick.tick(eng)
        manifest = state.load(tron_ctx)
        se = res.get("session_end")
        tick_history.append((i, dict(res["outcomes"]), list(res["spawned"]), se))
        if q_has_file_tick is None:
            view, _ = None, None
            try:
                on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{BLOCK_Q}.md"], root)
                if on_main:
                    q_has_file_tick = i
            except RuntimeError:
                pass
        react(i, manifest)
        if se is not None and session_ended_tick is None:
            session_ended_tick = i
            break

    done_tick = {}
    for _i, _outcomes, _spawned, _se in tick_history:
        for _b, (_outcome, _detail) in _outcomes.items():
            if _outcome == "record_landed" and _b not in done_tick:
                done_tick[_b] = _i

    final_manifest = state.load(tron_ctx)
    final_gates = final_manifest.get("gates") or {}
    ticks_used = i + 1

    ok("S2-M0: SCENARIO 2 (forward) converged to a clean session-end inside "
       f"{MAX_TICKS} ticks (used {ticks_used})",
       session_ended_tick is not None and ticks_used < MAX_TICKS,
       f"ticks_used={ticks_used} session_ended_tick={session_ended_tick}")

    ok("S2-K1 (FORWARD-AUTHORS KILLER — must be GREEN): the architect "
       "authored the MISSING block file for 02-02 on its own "
       "arch/02-02-forward branch, a REAL commit",
       forward_authored and bool(forward_tip),
       f"forward_authored={forward_authored} forward_tip={forward_tip}")

    forward_case_ids = {c for c in real_land_calls if c.startswith("paperwork-forward-")}
    ok("S2-K2 (CONTENT-BOUND CASE-ID KILLER — must be GREEN): the forward "
       "job landed under a case-id bound to `role='forward'` (distinct from "
       "gate.py's merge/record roles), via the REAL land.sh, exactly once",
       len(forward_case_ids) == 1 and real_land_calls.get(next(iter(forward_case_ids), ""), 0) == 1,
       f"forward_case_ids={forward_case_ids} real_land_calls={real_land_calls}")

    ok("S2-K3 (LANDED-ON-TRUNK KILLER — must be GREEN): 02-02's block file "
       "is genuinely on trunk (real git show), authored content intact",
       bool(forward_tip) and is_ancestor(root, forward_tip, MAIN),
       f"forward_tip={forward_tip}")

    ok("S2-K4 (BECOMES-DISPATCHABLE KILLER — must be GREEN): SWITCHBOARD "
       "picked up 02-02 for real dispatch (a spawn) once — and only once — "
       "its file landed on trunk",
       q_spawn_tick is not None and q_has_file_tick is not None
       and q_spawn_tick >= q_has_file_tick,
       f"q_spawn_tick={q_spawn_tick} q_has_file_tick={q_has_file_tick}")

    for block in (BLOCK_P, BLOCK_Q):
        g = final_gates.get(block, {})
        doc_on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{block}.md"], root)
        ok(f"S2-K5[{block}] (DRIVES-TO-✅ KILLER — must be GREEN): the block "
           "doc AS READ FROM main shows ✅ (real git show on trunk)",
           "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")
        branch_gone = not trunk.branch_exists(root, branch[block], False)
        clean_now, _detail = trunk.replica_clean(root, branch[block], MAIN, False)
        ok(f"S2-K6[{block}]: replica genuinely clean + gate CLOSED + slot "
           "really released",
           branch_gone and clean_now and g.get("stage") == gate.STAGE_CLOSED
           and eng.workers.get(agent_id[block], {}).get("status") == "released",
           f"branch_gone={branch_gone} clean={clean_now} stage={g.get('stage')}")

    forward_branch_gone = not trunk.branch_exists(root, forward_branch, False)
    ok("S2-K7: the architect's OWN authoring branch never lingers as an "
       "extra worker/gate — never counted toward the worker pool (this "
       "run's whole drive used exactly worker_count=2 real dispatch slots, "
       "never three)",
       len({a for a, _b in eng.spawn_calls}) == 2,
       f"spawn_calls={eng.spawn_calls} forward_branch_gone={forward_branch_gone}")

    architect_final = final_manifest.get("architect") or {}
    ok("S2-K8: the architect is IDLE with an EMPTY queue at the end — the "
       "forward job never lingers, never re-fires for an already-landed "
       "block",
       architect_final.get("status") == "idle" and architect_final.get("current_job") is None
       and not (final_manifest.get("architect_queue") or []),
       f"architect={architect_final} queue={final_manifest.get('architect_queue')}")

    print(f"\n== SCENARIO 2 (forward) ==")
    print(f"root={root}")
    print(f"ticks used={ticks_used} (cap={MAX_TICKS}) session_ended_tick={session_ended_tick}")
    print(f"forward_tip={forward_tip} forward_landed_tick={forward_landed_tick}")
    print(f"q_has_file_tick={q_has_file_tick} q_spawn_tick={q_spawn_tick}")
    print(f"real_land_calls={real_land_calls}")
    print(f"architect(final)={architect_final}")


def run_phantom_triage_grace_scenario():
    """R1b (ADR-0005) idle-gated, source-DIRECTIONAL backstop lock. A triage the
    architect took its ordered turn on but never verdicted must neither wedge the
    fleet (blocker B) nor swallow a real escalation (M1). Directional by TRUSTED
    source: a low-confidence `classify.unclassified` phantom resolves BENIGN
    ('answer', never wedges session-end); a GENUINE `worker.wall` resolves LOUD
    ('operator', a real page — never swallowed). The backstop is keyed on the
    architect being settled-idle (`eng._worker_working` absent on MiniEng -> reads
    not-working under the dry rig, so it arms across the idle debounce), NOT a
    wall-clock tick count. It also HOLDS while the architect is provably mid-turn
    (PT3 below)."""
    root = build_root()
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)

    # PT1 — low-confidence phantom -> BENIGN 'answer' backstop.
    mA = {"architect": {"status": "busy"}, "triage_verdicts": {}}
    jobA = {"kind": "triage", "triage_id": "triage-1", "source": "classify.unclassified",
            "block": None, "worker_id": "engineer-01-03", "ordered": True, "dispatch_seq": True,
            "verdict": None, "resolved": False}
    mA["architect"]["current_job"] = jobA
    for _ in range(3):
        architect._advance_triage(eng, mA, jobA)
    ok("PT1 (LOW-CONFIDENCE BENIGN BACKSTOP, R1b — must be GREEN): a "
       "classify.unclassified phantom with no verdict auto-resolves BENIGN "
       "('answer') once the architect settles idle — never wedges session-end",
       jobA.get("resolved") is True and jobA.get("verdict") == "answer",
       f"resolved={jobA.get('resolved')} verdict={jobA.get('verdict')} "
       f"idle_ticks={jobA.get('idle_ticks')}")

    # PT2 — GENUINE worker.wall the architect could not verdict -> LOUD 'operator'
    # (blocker B fixed: it no longer wedges; M1 fixed: it is never swallowed benign).
    mB = {"architect": {"status": "busy"}, "triage_verdicts": {},
          "cases": {"case-01-02-1": {"case_id": "case-01-02-1", "block": "01-02",
                                     "source": "worker.wall", "worker_id": "engineer-01-02",
                                     "owner": "architect", "decision": None}}}
    jobB = {"kind": "triage", "triage_id": "triage-2", "source": "worker.wall",
            "block": "01-02", "case_id": "case-01-02-1", "worker_id": "engineer-01-02",
            "ordered": True, "dispatch_seq": True, "verdict": None, "resolved": False}
    mB["architect"]["current_job"] = jobB
    for _ in range(3):
        architect._advance_triage(eng, mB, jobB)
    paged = getattr(eng, "operator_pages", [])
    ok("PT2 (GENUINE LOUD BACKSTOP, R1b — must be GREEN): a real worker.wall the "
       "architect never verdicts resolves LOUD to 'operator' (paged), never wedged "
       "(blocker B) and never swallowed benign (M1)",
       jobB.get("resolved") is True and jobB.get("verdict") == "operator"
       and mB["cases"]["case-01-02-1"].get("owner") == "operator"
       and any(p["case_id"] == "case-01-02-1" for p in paged),
       f"resolved={jobB.get('resolved')} verdict={jobB.get('verdict')} "
       f"owner={mB['cases']['case-01-02-1'].get('owner')} paged={paged}")

    # ── ADR-0008 — STALE-WALL REVALIDATION (T2-18 REJECT root fix) ──────────
    # A genuine landing worker.wall whose block has already CLOSED out on trunk
    # is moot; the R1b operator verdict (from EITHER the idle backstop OR a
    # structured triage_verdict) must be downgraded to a benign resolve — never
    # a page. Durable signal = gate stage 'closed' (survives branch teardown, so
    # the branch being deleted by close-out is irrelevant here — no branch read).
    _WALL_LAND = ("land.sh refused: grant minted for commit 98a1347, but worker "
                  "committed 8f04a86 before landing, causing content mismatch")

    # STALE-A0 — THE LITERAL T2-18 PATH: a BLOCK-LESS worker.wall (case_id=None,
    # the classify-unclassified variant that minted case-worker-wall-1 in the real
    # REJECT). Its block gate is CLOSED on trunk. Guard A must downgrade the R1b
    # backstop operator->answer AND — because case_id is None — the answer arm must
    # relay to the worker and resolve WITHOUT ever calling open_operator_case: no
    # page AND no new case minted. This is the production shape on which guard A
    # actually fires (a case-BEARING wall escalates its own gate to ESCALATED, never
    # 'closed'), so it is the one that must be locked to the fullest.
    mS0 = {"architect": {"status": "busy"}, "triage_verdicts": {}, "cases": {},
           "gates": {"01-03": {"stage": "closed"}}}
    jobS0 = {"kind": "triage", "triage_id": "triage-stale-0", "source": "worker.wall",
             "block": None, "case_id": None, "worker_id": "engineer-01-03",
             "detail": _WALL_LAND, "ordered": True, "dispatch_seq": True, "verdict": None, "resolved": False}
    mS0["architect"]["current_job"] = jobS0
    _pages_before = len(getattr(eng, "operator_pages", []))
    for _ in range(3):
        architect._advance_triage(eng, mS0, jobS0)
    _pages_after = getattr(eng, "operator_pages", [])
    ok("STALE-A0 (BLOCK-LESS T2-18 PATH, ADR-0008 — must be GREEN): the literal defect "
       "shape — a case_id=None worker.wall whose block gate is CLOSED — downgrades "
       "operator->answer, pages NObody, AND mints NO new operator case (open_operator_case "
       "never called)",
       jobS0.get("resolved") is True and jobS0.get("verdict") == "answer"
       and len(_pages_after) == _pages_before and not mS0["cases"],
       f"resolved={jobS0.get('resolved')} verdict={jobS0.get('verdict')} "
       f"new_pages={len(_pages_after) - _pages_before} cases={mS0['cases']}")

    # STALE-A1 — the IDLE-BACKSTOP operator verdict, block closed -> answer, NO page.
    mS1 = {"architect": {"status": "busy"}, "triage_verdicts": {},
           "gates": {"01-03": {"stage": "closed"}},
           "cases": {"case-stale-1": {"case_id": "case-stale-1", "block": None,
                                      "source": "worker.wall", "worker_id": "engineer-01-03",
                                      "owner": "architect", "decision": None}}}
    jobS1 = {"kind": "triage", "triage_id": "triage-stale-1", "source": "worker.wall",
             "block": None, "case_id": "case-stale-1", "worker_id": "engineer-01-03",
             "detail": _WALL_LAND, "ordered": True, "dispatch_seq": True, "verdict": None, "resolved": False}
    mS1["architect"]["current_job"] = jobS1
    for _ in range(3):
        architect._advance_triage(eng, mS1, jobS1)
    paged = getattr(eng, "operator_pages", [])
    ok("STALE-A1 (IDLE-BACKSTOP STALE-WALL, ADR-0008 — must be GREEN): a genuine "
       "landing worker.wall whose block gate is CLOSED on trunk downgrades the R1b "
       "backstop operator->answer and pages NObody",
       jobS1.get("resolved") is True and jobS1.get("verdict") == "answer"
       and not any(p["case_id"] == "case-stale-1" for p in paged),
       f"resolved={jobS1.get('resolved')} verdict={jobS1.get('verdict')} "
       f"paged_stale1={[p for p in paged if p['case_id']=='case-stale-1']}")

    # STALE-A2 — the STRUCTURED 'operator' verdict path (finding 3): even an
    # explicit triage_verdict='operator' on a since-closed block is downgraded.
    mS2 = {"architect": {"status": "busy"},
           "triage_verdicts": {"triage-stale-2": {"verdict": "operator", "note": "page it"}},
           "gates": {"01-03": {"stage": "closed"}},
           "cases": {"case-stale-2": {"case_id": "case-stale-2", "block": None,
                                      "source": "worker.wall", "worker_id": "engineer-01-03",
                                      "owner": "architect", "decision": None}}}
    jobS2 = {"kind": "triage", "triage_id": "triage-stale-2", "source": "worker.wall",
             "block": None, "case_id": "case-stale-2", "worker_id": "engineer-01-03",
             "detail": _WALL_LAND, "ordered": True, "dispatch_seq": True, "verdict": None, "resolved": False}
    mS2["architect"]["current_job"] = jobS2
    architect._advance_triage(eng, mS2, jobS2)
    paged = getattr(eng, "operator_pages", [])
    ok("STALE-A2 (STRUCTURED-VERDICT STALE-WALL, ADR-0008 — must be GREEN): a "
       "structured triage_verdict='operator' on a landing wall whose block is CLOSED "
       "is ALSO downgraded operator->answer, no page (guard covers both operator paths)",
       jobS2.get("resolved") is True and jobS2.get("verdict") == "answer"
       and not any(p["case_id"] == "case-stale-2" for p in paged),
       f"resolved={jobS2.get('resolved')} verdict={jobS2.get('verdict')} "
       f"paged_stale2={[p for p in paged if p['case_id']=='case-stale-2']}")

    # STALE-NV1 (NON-VACUITY) — SAME wall but block gate NOT closed (merge) -> the
    # genuine wall STILL pages operator, exactly as PT2. Proves the guard suppresses
    # ONLY a provably-closed block, never an in-flight one.
    mN1 = {"architect": {"status": "busy"}, "triage_verdicts": {},
           "gates": {"01-04": {"stage": "merge"}},
           "cases": {"case-nv-1": {"case_id": "case-nv-1", "block": "01-04",
                                   "source": "worker.wall", "worker_id": "engineer-01-04",
                                   "owner": "architect", "decision": None}}}
    jobN1 = {"kind": "triage", "triage_id": "triage-nv-1", "source": "worker.wall",
             "block": "01-04", "case_id": "case-nv-1", "worker_id": "engineer-01-04",
             "detail": _WALL_LAND, "ordered": True, "dispatch_seq": True, "verdict": None, "resolved": False}
    mN1["architect"]["current_job"] = jobN1
    for _ in range(3):
        architect._advance_triage(eng, mN1, jobN1)
    paged = getattr(eng, "operator_pages", [])
    ok("STALE-NV1 (OPEN-BLOCK STILL PAGES, ADR-0008 non-vacuity — must be GREEN): a "
       "genuine landing worker.wall on a block whose gate is NOT closed (merge) still "
       "resolves LOUD to operator and pages — the guard never suppresses an in-flight block",
       jobN1.get("verdict") == "operator" and any(p["case_id"] == "case-nv-1" for p in paged),
       f"verdict={jobN1.get('verdict')} paged_nv1={[p for p in paged if p['case_id']=='case-nv-1']}")

    # STALE-NV2 (NON-VACUITY) — block CLOSED but detail is NON-landing (dep cycle):
    # the landing signature fails -> still pages (a non-landing wall is never suppressed
    # merely because its worker's block happens to be closed).
    mN2 = {"architect": {"status": "busy"}, "triage_verdicts": {},
           "gates": {"01-05": {"stage": "closed"}},
           "cases": {"case-nv-2": {"case_id": "case-nv-2", "block": None,
                                   "source": "worker.wall", "worker_id": "engineer-01-05",
                                   "owner": "architect", "decision": None}}}
    jobN2 = {"kind": "triage", "triage_id": "triage-nv-2", "source": "worker.wall",
             "block": None, "case_id": "case-nv-2", "worker_id": "engineer-01-05",
             "detail": "dependency cycle between 01-06 and 01-07 — cannot proceed",
             "ordered": True, "dispatch_seq": True, "verdict": None, "resolved": False}
    mN2["architect"]["current_job"] = jobN2
    for _ in range(3):
        architect._advance_triage(eng, mN2, jobN2)
    paged = getattr(eng, "operator_pages", [])
    ok("STALE-NV2 (NON-LANDING WALL STILL PAGES, ADR-0008 non-vacuity — must be GREEN): "
       "a genuine NON-landing worker.wall (dep cycle) on a closed block fails the landing "
       "signature and STILL pages operator — suppression is landing-scoped by content",
       jobN2.get("verdict") == "operator" and any(p["case_id"] == "case-nv-2" for p in paged),
       f"verdict={jobN2.get('verdict')} paged_nv2={[p for p in paged if p['case_id']=='case-nv-2']}")

    # PT3 — the backstop HOLDS while the architect is provably mid-turn: a real
    # `claude -p` turn posts nothing until it finishes, so a working architect must
    # NEVER trip the backstop however long the turn (the A3 multi-turn-race fix).
    class _WorkingEng(MiniEng):
        def _worker_working(self, wid):
            return wid == architect.ARCHITECT_WID   # architect always mid-turn
    engW = _WorkingEng(root, tron_ctx, test_command="true", worker_count=1)
    mC = {"architect": {"status": "busy"}, "triage_verdicts": {}}
    jobC = {"kind": "triage", "triage_id": "triage-3", "source": "worker.wall",
            "block": "01-02", "case_id": "case-01-02-9", "worker_id": "engineer-01-02",
            "ordered": True, "dispatch_seq": True, "verdict": None, "resolved": False}
    mC["architect"]["current_job"] = jobC
    for _ in range(10):
        architect._advance_triage(engW, mC, jobC)
    ok("PT3 (WORKING-ARCHITECT HOLD, R1b/A3, ADR-0009 re-keyed onto "
       "_turn_settled — must be GREEN): while the architect is provably "
       "mid-turn (_worker_working True) the backstop NEVER fires, however "
       "many ticks — no premature page, no multi-turn race",
       jobC.get("resolved") is not True and jobC.get("verdict") is None,
       f"resolved={jobC.get('resolved')} verdict={jobC.get('verdict')}")

    # PT4 — R1a enqueue backstop: enqueue_triage from the architect itself creates
    # nothing (defense-in-depth; the call-site guards in classify/router are primary).
    engE = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    mD = {"architect_queue": []}
    architect.enqueue_triage(engE, mD, None, "worker.wall", None,
                             "architect narration that somehow reached enqueue",
                             worker_id=architect.ARCHITECT_WID)
    ok("PT4 (SELF-SOURCE ENQUEUE BACKSTOP, R1a — must be GREEN): enqueue_triage whose "
       "sender is the architect itself queues NOTHING (defense-in-depth over the "
       "classify/router call-site guards)",
       len(mD.get("architect_queue") or []) == 0,
       f"queue={mD.get('architect_queue')}")

    # ── ADR-0009 §5 rig 7, H1 (worker-careful, benign) ──────────────────
    # The worker attempted `record` ahead of its own commit reaching trunk
    # and self-walled HONESTLY (a genuine wall, block + land signature).
    # Handling: architect-first -> a structured verdict `answer` ("land,
    # then record") -> the worker is relayed the note and the case
    # resolves WITHOUT ever paging the operator — Defect 1 alone (this
    # ADR's R-A..R-G) is what stops this from starving behind a wedged
    # architect; the VERDICT machinery itself (`architect_resolve`'s
    # "answer" arm) is pre-existing, exercised here end-to-end together
    # with the NEW land.sh-signature structural classify path (§4).
    engH1 = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    mH1 = {"architect": {"status": "busy"}, "triage_verdicts": {
              "triage-h1": {"verdict": "answer",
                            "note": "land your merge first, THEN re-attempt record — "
                                    "you're ahead of your own commit reaching trunk"}},
          "cases": {"case-h1-1": {"case_id": "case-h1-1", "block": "01-06",
                                  "source": "worker.wall", "worker_id": "engineer-01-06",
                                  "owner": "architect", "decision": None}}}
    jobH1 = {"kind": "triage", "triage_id": "triage-h1", "source": "worker.wall",
            "block": "01-06", "case_id": "case-h1-1", "worker_id": "engineer-01-06",
            "detail": "land.sh refused: grant minted for commit aaa1111, but worker "
                      "committed bbb2222 before landing, causing content mismatch",
            "ordered": True, "dispatch_seq": True, "verdict": None, "resolved": False}
    mH1["architect"]["current_job"] = jobH1
    architect._advance_triage(engH1, mH1, jobH1)
    h1_pages = getattr(engH1, "operator_pages", [])
    h1_relay = [o for o in engH1.orders if o[0] == "engineer-01-06"]
    ok("H1 (WORKER-CAREFUL PREMATURE-RECORD, ADR-0009 §5 rig 7 — must be "
       "GREEN): a genuine worker.wall (land-signature detail) with a "
       "structured 'answer' verdict resolves via architect_resolve WITHOUT "
       "ever paging the operator, and relays the 'land, then record' note "
       "back to the worker so it can re-drive",
       jobH1.get("resolved") is True and "case-h1-1" not in mH1["cases"]
       and len(h1_pages) == 0 and len(h1_relay) == 1,
       f"resolved={jobH1.get('resolved')} cases={mH1['cases']} "
       f"pages={h1_pages} relay={h1_relay}")


def run_reconcile_backstop_scenario():
    """T2-12 regression: a NO-OP reconcile must not silently WEDGE the fleet. The
    architect takes its ordered reconcile turn, finds no forward impact, and its
    free-text ('no forward impact / work complete') is never routed as a structured
    `architect.reconciled` — so the block never enters `manifest['reconciled']` and,
    before the fix, `advance` held `current_job` busy FOREVER while the runner sat
    idle: 01-03's dispatch hung with no wall/page/retry. The shared R1b backstop
    (`_turn_settled`, ADR-0009 re-keyed onto R-D's `read_hwm >= dispatch_seq` read)
    clears the gate once the architect's reconcile order is genuinely DELIVERED and
    it settles idle — completion tied to ENGINE STATE, never to parsed prose.

    ADR-0009 consolidation note: the OLD RB4/RB5/RB6 here proved the `arch_started`
    latch (settled-after-a-genuine-turn vs. never-started-at-all) — that latch is
    DELETED (§6): its DISTINGUISHING POWER for a hookless `eng` (no `_read_hwm`) is
    gone too (a hookless `_delivered` degrades to 'sent == delivered', so it can no
    longer tell 'cold-start-dead' apart from 'genuinely settled' — only a LIVE
    engine's real `read_hwm` can). RB5/RB6's actual INTENT (a dead architect must
    still reach a human, exactly once, never a silent wedge) is NOT lost — it moves
    to the new live-hwm rig `run_no_progress_budget_rig` (§8 rig 4a), which proves
    it PROPERLY, with a real (rig-controlled) `_read_hwm` signal backing it, rather
    than a hookless approximation that can't actually distinguish the two cases."""
    root = build_root()
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)

    # RB1 — settled idle, no architect.reconciled -> backstop marks reconciled + clears.
    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    jobA = {"kind": "reconcile", "block": "01-03", "after": "01-02",
            "ordered": True, "dispatch_seq": True}
    mA = {"architect": {"status": "busy", "current_job": jobA, "spawned": True},
          "architect_queue": [], "reconciled": []}
    for _ in range(3):
        architect.advance(eng, mA)
    ok("RB1 (RECONCILE NO-OP BACKSTOP KILLER — must be GREEN): a reconcile the "
       "architect took its turn on but never reported architect.reconciled clears on "
       "settled-idle (block marked reconciled, current_job freed, architect idle) — "
       "never a silent WEDGE of 01-03's dispatch (the T2-12 hang)",
       "01-03" in (mA.get("reconciled") or [])
       and mA["architect"].get("current_job") is None
       and mA["architect"].get("status") == "idle",
       f"reconciled={mA.get('reconciled')} architect={mA['architect']}")

    # RB2 — the backstop HOLDS while the architect is provably mid-turn (a real
    # `claude -p` reconcile turn posts nothing until it finishes).
    class _WorkingEng(MiniEng):
        def _worker_working(self, wid):
            return wid == architect.ARCHITECT_WID
    engW = _WorkingEng(root, tron_ctx, test_command="true", worker_count=1)
    jobB = {"kind": "reconcile", "block": "01-03", "after": "01-02",
            "ordered": True, "dispatch_seq": True}
    mB = {"architect": {"status": "busy", "current_job": jobB, "spawned": True},
          "architect_queue": [], "reconciled": []}
    for _ in range(10):
        architect.advance(engW, mB)
    ok("RB2 (WORKING-ARCHITECT HOLD — must be GREEN): while the architect is provably "
       "mid-reconcile-turn (_worker_working True) the backstop NEVER fires — current_job "
       "held, block never prematurely marked reconciled, however many ticks",
       "01-03" not in (mB.get("reconciled") or [])
       and mB["architect"].get("current_job") is not None,
       f"reconciled={mB.get('reconciled')} architect={mB['architect']}")

    # RB3 — normal path intact: a real architect.reconciled clears via the observed
    # arm, and the backstop never DOUBLE-adds the block.
    eng2 = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    jobC = {"kind": "reconcile", "block": "01-03", "after": "01-02", "ordered": True,
            "dispatch_seq": True}
    mC = {"architect": {"status": "busy", "current_job": jobC, "spawned": True},
          "architect_queue": [], "reconciled": ["01-03"]}
    architect.advance(eng2, mC)
    ok("RB3 (NORMAL RECONCILE PATH INTACT — must be GREEN): when architect.reconciled "
       "IS observed (block already in manifest['reconciled']) the gate clears via the "
       "normal arm and '01-03' appears exactly once (backstop never double-adds)",
       mC["architect"].get("current_job") is None
       and (mC.get("reconciled") or []).count("01-03") == 1,
       f"reconciled={mC.get('reconciled')} architect={mC['architect']}")

    # RB7 — ADR-0006 R1d (STARTED-THEN-REFUSED FORWARD/LOG KILLER, ADR-0009 re-keyed
    # onto `_turn_settled`/R-D): the architect's forward order was genuinely DELIVERED
    # (observed working, then idle) and it settled idle having authored NO branch
    # (`land_via_grant` -> "fail-closed" for a never-created branch). The job must NOT
    # poll to budget nor benign-clear (dropping work) — it routes LOUD to the operator
    # once and frees the architect.
    class _StartsThenIdleEng(MiniEng):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._wk = [True, True]      # working for two ticks, then idle
        def _worker_working(self, wid):
            if wid != architect.ARCHITECT_WID:
                return False
            return self._wk.pop(0) if self._wk else False
    engR = _StartsThenIdleEng(root, tron_ctx, test_command="true", worker_count=1)
    jobF = {"kind": "forward", "block": "09-09", "ordered": False}
    mF = {"architect": {"status": "busy", "current_job": jobF, "spawned": True},
          "architect_queue": [], "reconciled": []}
    # Deterministically model the REFUSAL: the architect authors no branch, so
    # land_via_grant reports "fail-closed" every poll (a real never-created branch
    # can spuriously read "landed" off an empty tip in `_observe_landed` — a git
    # artifact, not the R1d path under test). Stub the ONE grant seam.
    _real_lvg = architect.landing.land_via_grant
    architect.landing.land_via_grant = lambda *a, **k: "fail-closed"
    try:
        for _ in range(8):
            architect.advance(engR, mF)
    finally:
        architect.landing.land_via_grant = _real_lvg
    r1d_pages = [p for p in getattr(engR, "operator_pages", [])
                 if p.get("block") == "09-09"]
    ok("RB7 (R1d STARTED-THEN-REFUSED FORWARD — must be GREEN): an architect that took its "
       "forward turn but authored no branch (fail-closed + settled idle) is routed to the "
       "operator ONCE and freed — never a silent wedge, never a benign drop",
       len(r1d_pages) == 1 and mF["architect"].get("current_job") is None
       and not jobF.get("landed"),
       f"r1d_pages={r1d_pages} architect={mF['architect']} last_outcome={jobF.get('last_outcome')}")


class HwmEng(MiniEng):
    """ADR-0009 §8 (rigs 1-5) — a CONTROLLABLE eng stand-in backing the
    R-A..R-G duck-typed hooks (`_read_hwm`/`_is_alive`/`_runner_idle`/
    `_mbox_seq`/`_resend`) with an in-memory, fully rig-driven fake of the
    runner-consumption signals — never real files (real `engine/jobs.py`
    file behavior is proven elsewhere: `core/sim/teardown_rig.py`,
    `core/engine_rig.py`'s real mailbox send/receive, and RIG2's own
    direct test of `core.engine.Engine`'s REAL `_next_mbox_seq` below);
    this rig only needs to prove `core/architect.py`'s OWN CONSUMPTION of
    those signals is correct, deterministically, mutation-provably. A
    pluggable clock (`tick_clock`) drives every pace-unit-based comparison
    (REDELIVER_AFTER/NO_PROGRESS_BUDGET) exactly like `core/sentry_rig.py`
    already does for `core/sentry.py`."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._hwm = {}
        self._mbox = {}
        self._alive_map = {}
        self._idle_map = {}
        self._clk = 0
        self.working = False
        self.resend_calls = []
        self.respawn_calls = 0

    def _now(self):
        return self._clk

    def tick_clock(self, n=1):
        self._clk += n

    def _to_worker(self, wid, msg, kind):
        seq = self._mbox.get(wid, 0) + 1
        self._mbox[wid] = seq
        self.orders.append((wid, msg, kind))
        return seq

    def emit(self, template_id, fallback_text, slots=None, worker_id=None, kind=None):
        line = fallback_text
        if worker_id and not self.dry:
            self._to_worker(worker_id, line, kind or template_id)
        return line

    def _mbox_seq(self, wid):
        return self._mbox.get(wid)

    def _resend(self, wid, seq, text, kind):
        self.resend_calls.append((wid, seq, text, kind))
        return seq

    def _read_hwm(self, wid):
        return self._hwm.get(wid, 0)

    def consume(self, wid=None, seq=None):
        """Simulate the runner finishing a turn that consumed up through
        `seq` (default: the CURRENT mbox seq) — bumps the durable hwm,
        mirroring `worker_runner.py::_write_hwm`'s own "after each
        fully-finished turn" timing."""
        wid = wid or architect.ARCHITECT_WID
        if seq is None:
            seq = self._mbox.get(wid, 0)
        self._hwm[wid] = max(self._hwm.get(wid, 0), seq)

    def _is_alive(self, wid):
        return self._alive_map.get(wid, True)

    def _runner_idle(self, wid):
        return self._idle_map.get(wid, True)

    def _worker_working(self, wid):
        return self.working if wid == architect.ARCHITECT_WID else False

    def _spawn_architect(self):
        self.respawn_calls += 1
        # R-C: clean-slate — `retire_stale_dir` archives the whole dir, so
        # a re-spawn resets hwm -> 0 with an empty mailbox ("resumes from
        # hwm" is FALSE for this stack); mbox_seq (R-A, per-wid monotonic)
        # is untouched by a respawn — only THIS reset, never the counter.
        self._hwm[architect.ARCHITECT_WID] = 0


def _hwm_job(triage_id, worker_id):
    return {"kind": "triage", "triage_id": triage_id, "source": "classify.unclassified",
           "block": None, "worker_id": worker_id, "ordered": False,
           "verdict": None, "resolved": False}


def run_delivery_gap_rig():
    """§8 rig 1 — DELIVERY-GAP (literal T2-20): pin `read_hwm < dispatch_seq`
    for K ticks (runner alive+idle, the order silently never consumed — the
    exact T2-20 shape: 'state:idle turns:2 is positive proof seq-3 was
    never consumable') then let it consume -> re-delivers, completes,
    0 pages, the architect frees for the next job. Mutation: restore the
    `ordered`-boolean-only, fire-and-forget pre-ADR-0009 shape (disable the
    R-C/R-E redeliver loop) -> strands, pages -> reproduces the T2-20
    'a genuinely stuck architect order must still reach a human' signature
    (via R-G's no-progress budget, which absorbs the deleted R1c ladder's
    honest core — the same page, never a silent wedge)."""
    root = build_root()
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)

    def _fresh(tid, wid):
        eng = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
        job = _hwm_job(tid, wid)
        m = {"architect": {"status": "busy", "current_job": job, "spawned": True},
            "architect_queue": [], "triage_verdicts": {}}
        return eng, m, job

    # RUN A — the fix intact.
    eng, m, job = _fresh("triage-dg-a", "engineer-01")
    architect.advance(eng, m)   # orders — dispatch_seq stamped
    seq0 = job.get("dispatch_seq")
    K = architect.REDELIVER_AFTER + 2
    for _ in range(K):
        eng.tick_clock()
        architect.advance(eng, m)
    ok("RIG1-A1: the order was genuinely re-delivered (R-E, idle-gated) "
       "while pinned unconsumed — at the SAME dispatch_seq (runner dedups)",
       len(eng.resend_calls) >= 1 and all(c[1] == seq0 for c in eng.resend_calls),
       f"resend_calls={eng.resend_calls} seq0={seq0}")
    ok("RIG1-A2: 0 operator pages while the gap was still within budget",
       len(getattr(eng, "operator_pages", [])) == 0,
       f"pages={getattr(eng, 'operator_pages', [])}")
    eng.consume()   # the runner (finally) processes the (re-)delivered order
    eng.tick_clock()
    architect.advance(eng, m)
    ok("RIG1-A3 (THE DELIVERY-GAP KILLER — must be GREEN): once genuinely "
       "consumed, the job resolves — 0 pages for the WHOLE run, the "
       "architect is freed (current_job cleared) for the next triage",
       job.get("resolved") is True and len(getattr(eng, "operator_pages", [])) == 0
       and m["architect"].get("current_job") is None,
       f"resolved={job.get('resolved')} pages={getattr(eng, 'operator_pages', [])} "
       f"architect={m['architect']}")

    # RUN B — MUTATION: disable the redeliver loop entirely (restore the
    # `ordered`-boolean-only, fire-and-forget shape) — the SAME scenario
    # must now STRAND and eventually PAGE.
    eng2, m2, job2 = _fresh("triage-dg-b", "engineer-02")
    architect.advance(eng2, m2)
    _real_redeliver = architect._redeliver
    architect._redeliver = lambda eng_, d, now: None   # MUTATION: never re-send
    try:
        for _ in range(architect.NO_PROGRESS_BUDGET + 5):
            eng2.tick_clock()
            architect.advance(eng2, m2)
    finally:
        architect._redeliver = _real_redeliver
    pages2 = getattr(eng2, "operator_pages", [])
    ok("RIG1-B (MUTATION -> RED, non-vacuity proof): with re-delivery "
       "disabled, the SAME delivery gap STRANDS — never resolves — and "
       "eventually PAGES (R-G's no-progress budget), reproducing the "
       "T2-20 'a genuinely stuck architect order must still reach a "
       "human' signature the deleted R1c ladder used to own",
       job2.get("resolved") is not True and len(pages2) == 1,
       f"resolved={job2.get('resolved')} pages={pages2}")


def run_respawn_rig():
    """§8 rig 2 — RESPAWN (R-C/R-A): dir archived -> hwm->0 -> monotonic
    mbox_seq stays high -> order re-sent at the higher seq -> `turn_done`
    carries that seq (no `(wid,seq)` collision) -> verdict couriered ->
    completes, 0 pages. Two mutations: (1) architect.py's own respawn+
    resend loop (R-C), proven via the controllable HwmEng; (2) R-A's
    monotonic-upward reconciliation, proven DIRECTLY against `core.engine.
    Engine`'s REAL `_next_mbox_seq`/`_to_worker` — the property under
    mutation (2) is ENGINE-internal (the 'engine-restart wedge'), not
    architect.py's own recovery loop (already proven non-vacuous above)."""
    root = build_root()
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)

    # ── R-C: architect.py's own respawn+resend (via the controllable HwmEng) ──
    eng = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    eng._alive_map[architect.ARCHITECT_WID] = False   # DEAD from the start
    job = _hwm_job("triage-rs", "engineer-03")
    m = {"architect": {"status": "busy", "current_job": job, "spawned": True},
        "architect_queue": [], "triage_verdicts": {}}
    architect.advance(eng, m)   # orders — dispatch_seq stamped
    seq0 = job.get("dispatch_seq")
    for _ in range(3):
        eng.tick_clock()
        architect.advance(eng, m)
    ok("RIG2-A1: a DEAD architect (never alive) was clean-slate RE-SPAWNED "
       "(R-C) and its order RE-DELIVERED at the SAME dispatch_seq",
       eng.respawn_calls >= 1 and len(eng.resend_calls) >= 1
       and all(c[1] == seq0 for c in eng.resend_calls),
       f"respawn_calls={eng.respawn_calls} resend_calls={eng.resend_calls} seq0={seq0}")
    ok("RIG2-A2: the respawn's clean-slate reset hwm -> 0 while mbox_seq "
       "(dispatch_seq) stayed HIGH — 'resumes from hwm' is FALSE for this "
       "stack (R-C's own correction)",
       eng._hwm.get(architect.ARCHITECT_WID, -1) == 0 and seq0 and seq0 >= 1,
       f"hwm={eng._hwm} seq0={seq0}")
    eng._alive_map[architect.ARCHITECT_WID] = True   # the fresh incarnation comes up
    eng.consume()   # ... and processes the re-delivered order
    eng.tick_clock()
    architect.advance(eng, m)
    ok("RIG2-A3 (THE RESPAWN KILLER — must be GREEN): completes cleanly "
       "post-respawn — 0 pages, job resolved",
       job.get("resolved") is True and len(getattr(eng, "operator_pages", [])) == 0,
       f"resolved={job.get('resolved')} pages={getattr(eng, 'operator_pages', [])}")

    # MUTATION 1 (architect.py's R-C loop disabled): a dead architect is
    # NEVER re-spawned at all -> permanently wedged (never resolves; R-G
    # eventually pages, but the job itself never completes).
    eng_m1 = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    eng_m1._alive_map[architect.ARCHITECT_WID] = False
    job_m1 = _hwm_job("triage-rs-m1", "engineer-04")
    m_m1 = {"architect": {"status": "busy", "current_job": job_m1, "spawned": True},
           "architect_queue": [], "triage_verdicts": {}}
    architect.advance(eng_m1, m_m1)
    _real_spawn_fn = HwmEng._spawn_architect
    HwmEng._spawn_architect = lambda self: None   # MUTATION: respawn never fires
    try:
        for _ in range(10):
            eng_m1.tick_clock()
            architect.advance(eng_m1, m_m1)
    finally:
        HwmEng._spawn_architect = _real_spawn_fn
    ok("RIG2-B (MUTATION -> RED, non-vacuity for RIG2-A1/A3): with the "
       "respawn call disabled, a dead architect's order is NEVER "
       "re-delivered (no clean-slate incarnation to deliver it to) — "
       "never resolves",
       job_m1.get("resolved") is not True and eng_m1.respawn_calls == 0,
       f"resolved={job_m1.get('resolved')} respawn_calls={eng_m1.respawn_calls}")

    # ── R-A: tested DIRECTLY against `core.engine.Engine`'s REAL
    #     `_to_worker`/`_next_mbox_seq` — the "engine-restart wedge": a
    #     fresh engine process (its in-memory `_mailbox_seq` counter LOST
    #     to the crash, and no persisted `manifest["mbox_seq"]` entry
    #     either — the exact shape a real restart leaves) must reconcile
    #     its FIRST post-restart send UPWARD off the runner's REAL,
    #     already-high, on-disk high-water — never re-mint a seq the
    #     runner's own dedupe (`seq <= hwm: skip`,
    #     `engine/worker_runner.py::_pending`) would silently treat as
    #     already-consumed. ──
    real_eng = CoreEngine(tron_ctx, dry=False)
    wdir = tron_ctx.worker_dir(architect.ARCHITECT_WID)
    os.makedirs(wdir, exist_ok=True)
    with open(os.path.join(wdir, jobs.HWM), "w") as f:
        f.write("50")   # the runner ALREADY consumed up through seq 50 (a real prior incarnation)
    real_eng._manifest = {}   # a genuine restart: no persisted mbox_seq entry at all
    seq_fixed = real_eng._to_worker(architect.ARCHITECT_WID, "hello", "arch.triage")
    ok("RIG2-C1 (R-A ENGINE-RESTART KILLER — must be GREEN): a fresh "
       "`core.engine.Engine` (no persisted mbox_seq — the exact "
       "'in-memory counter lost to a crash' shape) reconciles its FIRST "
       "post-restart send UPWARD off the runner's REAL on-disk high-water "
       "— never re-collides with (or reads as stale-behind) already-"
       "consumed seq territory",
       seq_fixed is not None and seq_fixed > 50,
       f"seq_fixed={seq_fixed} hwm_on_disk=50")

    # MUTATION 2 (R-A): seed the seq from the persisted counter ALONE,
    # ignoring the runner's real hwm entirely (the pre-R-A, in-memory-
    # counter-only shape) — a fresh process with NO persisted counter
    # mints seq=1, which the runner's OWN dedupe treats as ALREADY
    # consumed — a permanently unreachable, silently-dropped send.
    real_eng2 = CoreEngine(tron_ctx, dry=False)
    real_eng2._manifest = {}
    def _seed_from_persisted_only(wid):
        mbox = real_eng2._manifest.setdefault("mbox_seq", {})
        seq = mbox.get(wid, 0) + 1
        mbox[wid] = seq
        return seq
    real_eng2._next_mbox_seq = _seed_from_persisted_only
    seq_mut = real_eng2._to_worker(architect.ARCHITECT_WID, "hello", "arch.triage")
    ok("RIG2-C2 (MUTATION -> RED, non-vacuity for RIG2-C1): seeding the "
       "seq from the persisted counter ALONE (ignoring the runner's real "
       "high-water, R-A's own 'max' rule disabled) mints a seq the "
       "runner's real hwm has ALREADY passed — the exact engine-restart "
       "wedge R-A closes",
       seq_mut is not None and seq_mut <= 50,
       f"seq_mut={seq_mut} hwm_on_disk=50")


def run_multi_order_rig():
    """§8 rig 3 — MULTI-ORDER (R-B): a job that issues a SECOND, order-
    requiring sub-state (triage `scope_forward`'s adhoc `entry`) must wait
    for its OWN hwm advance, never read 'delivered' off an EARLIER order's
    already-consumed dispatch_seq. Mutation: stamp dispatch_seq ONCE (never
    re-stamp the second order) -> the second, authoring turn reads
    'delivered' the instant the FIRST order's hwm passed -> false-completed
    before the architect ever took the second turn (red)."""
    root = build_root()
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    eng = HwmEng(root, tron_ctx, test_command="true", worker_count=1)

    job = {"kind": "triage", "triage_id": "triage-mo", "source": "worker.wall",
          "block": "01-07", "worker_id": "engineer-01-07",
          "ordered": False, "verdict": None, "resolved": False, "case_id": None}
    architect._order_triage(eng, job)   # order #1 — stamps job["dispatch_seq"]
    seq1 = job["dispatch_seq"]
    eng.consume()                        # the runner delivers order #1
    ok("RIG3-1: order #1 (the triage verdict ask) is delivered",
       architect._delivered(eng, job), f"seq1={seq1} hwm={eng._hwm}")

    entry = {"block": "adhoc-triage-1", "branch": "arch/adhoc-triage-1-logreview",
            "finding": "x", "case_id": None, "landed": False, "ordered": False}
    text2 = "[TRON] scope_forward order #2"
    eng._to_worker(architect.ARCHITECT_WID, text2, "arch.log-review")
    entry["ordered"] = True
    architect._stamp_dispatch(eng, entry, text2, "arch.log-review")   # order #2
    seq2 = entry["dispatch_seq"]
    ok("RIG3-2 (THE MULTI-ORDER KILLER — must be GREEN): order #2's OWN "
       "dispatch_seq is a DISTINCT, HIGHER seq than order #1's, and reads "
       "UNDELIVERED even though order #1's hwm already passed — a stale "
       "EARLIER order can never satisfy a LATER order's completion read",
       seq2 is not None and seq1 is not None and seq2 > seq1
       and not architect._delivered(eng, entry),
       f"seq1={seq1} seq2={seq2} hwm={eng._hwm} "
       f"delivered_entry={architect._delivered(eng, entry)}")
    eng.consume()   # the runner ALSO finishes order #2's turn
    ok("RIG3-3: once order #2's OWN hwm passes, entry reads delivered too",
       architect._delivered(eng, entry), f"hwm={eng._hwm} seq2={seq2}")

    # MUTATION: never re-stamp — order #2 reuses order #1's OLD dispatch_seq.
    entry_mut = {"block": "adhoc-triage-2", "dispatch_seq": seq1}
    ok("RIG3-4 (MUTATION -> RED, non-vacuity for RIG3-2): reusing the "
       "FIRST order's dispatch_seq for the SECOND turn reads 'delivered' "
       "immediately (hwm already passed seq1) — a false-complete before "
       "the architect ever took the second turn",
       architect._delivered(eng, entry_mut),
       f"entry_mut={entry_mut} hwm={eng._hwm}")


def run_no_progress_budget_rig():
    """§8 rig 4 — NO-PROGRESS-BUDGET (R-G), three sub-cases."""
    root = build_root()
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)

    # ── 4a — a permanently DEAD architect (respawns exhaust RESPAWN_CAP,
    #     never comes back) is paged EXACTLY ONCE, never looped, however
    #     long the drive continues past the budget. ──
    eng = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    eng._alive_map[architect.ARCHITECT_WID] = False
    job = _hwm_job("triage-np-a", "engineer-05")
    m = {"architect": {"status": "busy", "current_job": job, "spawned": True},
        "architect_queue": [], "triage_verdicts": {}}
    architect.advance(eng, m)
    for _ in range(architect.NO_PROGRESS_BUDGET + 10):
        eng.tick_clock()
        architect.advance(eng, m)
    pages_a = getattr(eng, "operator_pages", [])
    ok("RIG4a-1 (DEAD-ARCHITECT PAGE-ONCE KILLER — must be GREEN): a "
       "permanently dead architect is paged the operator EXACTLY ONCE "
       "past NO_PROGRESS_BUDGET, never looped, however long the drive "
       "continues",
       len(pages_a) == 1 and job.get("resolved") is not True,
       f"pages={pages_a} respawn_calls={eng.respawn_calls} "
       f"resolved={job.get('resolved')}")

    # MUTATION 4a: key the no-progress clock on the RAW hwm/respawn signal
    # instead of the working-excluded accumulator — a respawn's hwm reset
    # (3->0) would then read as "progress", resetting the clock forever ->
    # the page NEVER fires -> silent wedge (the rejected rev-2 design).
    eng_mut = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    eng_mut._alive_map[architect.ARCHITECT_WID] = False
    job_mut = _hwm_job("triage-np-a-mut", "engineer-06")
    m_mut = {"architect": {"status": "busy", "current_job": job_mut, "spawned": True},
             "architect_queue": [], "triage_verdicts": {}}
    _real_integrate = architect.liveness.working_excluded_integrate

    def _hwm_keyed_mutation(now, last_sample, accumulated, active, reset_on_active=True):
        if eng_mut.respawn_calls > job_mut.get("_seen_respawns", 0):
            job_mut["_seen_respawns"] = eng_mut.respawn_calls
            return now, 0   # MUTATION: a respawn resets the clock to 0 ("progress")
        return _real_integrate(now, last_sample, accumulated, active, reset_on_active)
    architect.liveness.working_excluded_integrate = _hwm_keyed_mutation
    # Also uncap respawns (a REAL RESPAWN_CAP bounds the thrash — this
    # mutation's own hypothesis, per the ADR, is specifically an
    # UNBOUNDED thrash that keeps "resetting the clock forever"; with the
    # cap left in place, respawns stop after 3 and the real accumulator
    # would still eventually page from there, masking the mutation).
    _real_cap = architect.RESPAWN_CAP
    architect.RESPAWN_CAP = 10 ** 9
    try:
        architect.advance(eng_mut, m_mut)
        for _ in range(architect.NO_PROGRESS_BUDGET + 10):
            eng_mut.tick_clock()
            architect.advance(eng_mut, m_mut)
    finally:
        architect.liveness.working_excluded_integrate = _real_integrate
        architect.RESPAWN_CAP = _real_cap
    pages_a_mut = getattr(eng_mut, "operator_pages", [])
    ok("RIG4a-2 (MUTATION -> RED, non-vacuity for RIG4a-1): keying the "
       "no-progress clock on the raw hwm/respawn signal instead of the "
       "working-excluded accumulator lets the RESPAWN_CAP-bounded thrash "
       "reset the clock forever — NEVER pages, a silent wedge",
       len(pages_a_mut) == 0 and job_mut.get("resolved") is not True,
       f"pages={pages_a_mut} respawn_calls={eng_mut.respawn_calls}")

    # ── 4b — a legit long WORKING turn (provably mid-turn the WHOLE drive)
    #     must NEVER page — the accumulator is PAUSED, not merely slow. ──
    eng2 = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    eng2.working = True
    job2 = _hwm_job("triage-np-b", "engineer-07")
    m2 = {"architect": {"status": "busy", "current_job": job2, "spawned": True},
         "architect_queue": [], "triage_verdicts": {}}
    architect.advance(eng2, m2)
    for _ in range(architect.NO_PROGRESS_BUDGET + 10):
        eng2.tick_clock()
        architect.advance(eng2, m2)
    pages_b = getattr(eng2, "operator_pages", [])
    ok("RIG4b-1 (WORKING-PAUSE KILLER — must be GREEN): a legit long "
       "WORKING turn (provably mid-turn the WHOLE drive, well past "
       "NO_PROGRESS_BUDGET pace-units) NEVER pages — the accumulator is "
       "PAUSED, not merely slow to accrue",
       len(pages_b) == 0, f"pages={pages_b} "
       f"unconsumed_work_excluded={job2.get('unconsumed_work_excluded')}")

    # MUTATION 4b: accrue WHILE working too (ignore the pause) -> false-
    # pages mid-turn, the exact defect this ADR kills.
    eng2b = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    eng2b.working = True
    job2b = _hwm_job("triage-np-b-mut", "engineer-08")
    m2b = {"architect": {"status": "busy", "current_job": job2b, "spawned": True},
          "architect_queue": [], "triage_verdicts": {}}
    architect.advance(eng2b, m2b)
    _real_integrate2 = architect.liveness.working_excluded_integrate

    def _accrue_while_working(now, last_sample, accumulated, active, reset_on_active=True):
        return now, accumulated + max(0, now - last_sample)   # MUTATION: ignore `active`
    architect.liveness.working_excluded_integrate = _accrue_while_working
    try:
        for _ in range(architect.NO_PROGRESS_BUDGET + 10):
            eng2b.tick_clock()
            architect.advance(eng2b, m2b)
    finally:
        architect.liveness.working_excluded_integrate = _real_integrate2
    pages_b_mut = getattr(eng2b, "operator_pages", [])
    ok("RIG4b-2 (MUTATION -> RED, non-vacuity for RIG4b-1): accruing while "
       "provably working (ignoring the pause) false-pages mid-turn — the "
       "exact defect the working-excluded accumulator exists to kill",
       len(pages_b_mut) == 1, f"pages={pages_b_mut}")

    # ── 4c — sizing: RESPAWN_CAP*settle < NO_PROGRESS_BUDGET < run_budget —
    #     a dead-then-recovering architect completes BEFORE any page. ──
    eng3 = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    eng3._alive_map[architect.ARCHITECT_WID] = False
    job3 = _hwm_job("triage-np-c", "engineer-09")
    m3 = {"architect": {"status": "busy", "current_job": job3, "spawned": True},
         "architect_queue": [], "triage_verdicts": {}}
    architect.advance(eng3, m3)
    recovery_span = 2 * architect.REDELIVER_AFTER   # comfortably inside RESPAWN_CAP*settle
    for _ in range(recovery_span):
        eng3.tick_clock()
        architect.advance(eng3, m3)
        if eng3.respawn_calls >= 1:
            eng3._alive_map[architect.ARCHITECT_WID] = True   # the respawned incarnation comes up
            eng3.consume()
    eng3.tick_clock()
    architect.advance(eng3, m3)
    pages_c = getattr(eng3, "operator_pages", [])
    ok("RIG4c-1 (SIZING KILLER — must be GREEN): RESPAWN_CAP*settle < "
       "NO_PROGRESS_BUDGET means recovery genuinely completes BEFORE any "
       "page — 0 pages, job resolved, well within the budget's own span",
       len(pages_c) == 0 and job3.get("resolved") is True
       and recovery_span < architect.NO_PROGRESS_BUDGET,
       f"pages={pages_c} resolved={job3.get('resolved')} "
       f"recovery_span={recovery_span} budget={architect.NO_PROGRESS_BUDGET}")

    # MUTATION 4c: budget < recovery span — the honest page now fires
    # MID-RECOVERY, before the respawn ladder ever gets a chance to finish.
    _real_budget = architect.NO_PROGRESS_BUDGET
    architect.NO_PROGRESS_BUDGET = 1   # MUTATION: budget far under recovery_span
    eng3b = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    eng3b._alive_map[architect.ARCHITECT_WID] = False
    job3b = _hwm_job("triage-np-c-mut", "engineer-10")
    m3b = {"architect": {"status": "busy", "current_job": job3b, "spawned": True},
          "architect_queue": [], "triage_verdicts": {}}
    try:
        architect.advance(eng3b, m3b)
        # Heal only on the LAST tick of the (same) recovery_span — a
        # genuine multi-tick recovery, unlike RIG4c-1's "heals on the
        # very first respawn" fast path — so the (mutated, tiny) budget
        # gets the SAME recovery_span worth of elapsed no-progress time
        # to fire against, exactly the "budget sized under the recovery
        # span" scenario this mutation names.
        for i in range(recovery_span):
            eng3b.tick_clock()
            architect.advance(eng3b, m3b)
            if i == recovery_span - 1:
                eng3b._alive_map[architect.ARCHITECT_WID] = True
                eng3b.consume()
    finally:
        architect.NO_PROGRESS_BUDGET = _real_budget
    pages_c_mut = getattr(eng3b, "operator_pages", [])
    ok("RIG4c-2 (MUTATION -> RED, non-vacuity for RIG4c-1): sizing the "
       "budget UNDER the recovery span pages MID-RECOVERY, before the "
       "respawn ladder ever gets a chance to finish — recovery no longer "
       "beats the honest page",
       len(pages_c_mut) >= 1, f"pages={pages_c_mut}")


def run_redeliver_idle_rig():
    """§8 rig 5 — REDELIVER-IDLE (R-E): a long LIVE turn (runner working,
    never idle) must NEVER trigger a re-send (would race it); runner idle
    + a genuine gap re-sends, throttled — roughly once per REDELIVER_AFTER
    interval, never a busy-loop. Mutation: drop the idle gate -> races a
    live turn (red)."""
    root = build_root()
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)

    # 5a — the runner is BUSY (not idle) the whole time — NO re-send may
    # ever fire, however long the gap.
    eng = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    eng._idle_map[architect.ARCHITECT_WID] = False
    job = _hwm_job("triage-ri-a", "engineer-11")
    m = {"architect": {"status": "busy", "current_job": job, "spawned": True},
        "architect_queue": [], "triage_verdicts": {}}
    architect.advance(eng, m)
    for _ in range(architect.REDELIVER_AFTER * 5):
        eng.tick_clock()
        architect.advance(eng, m)
    ok("RIG5-A1 (LIVE-TURN NO-RACE KILLER — must be GREEN): a runner "
       "reporting BUSY (not idle) the whole time — a long live turn — "
       "NEVER gets a re-send, however long the gap",
       len(eng.resend_calls) == 0, f"resend_calls={eng.resend_calls}")

    # 5b — idle + a genuine gap DOES re-send, throttled.
    eng2 = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    job2 = _hwm_job("triage-ri-b", "engineer-12")
    m2 = {"architect": {"status": "busy", "current_job": job2, "spawned": True},
         "architect_queue": [], "triage_verdicts": {}}
    architect.advance(eng2, m2)
    N = architect.REDELIVER_AFTER * 3
    for _ in range(N):
        eng2.tick_clock()
        architect.advance(eng2, m2)
    ok("RIG5-B1: an idle runner + a genuine unconsumed gap DOES re-send, "
       "throttled — roughly one per REDELIVER_AFTER interval, never a "
       "busy-loop (every tick)",
       0 < len(eng2.resend_calls) <= (N // architect.REDELIVER_AFTER) + 1,
       f"resend_calls={len(eng2.resend_calls)} N={N} "
       f"REDELIVER_AFTER={architect.REDELIVER_AFTER}")

    # MUTATION: drop the idle gate — re-send fires on the interval alone,
    # regardless of `_runner_idle` — races a live turn (5a's own scenario
    # would then ALSO re-send, which must never happen).
    eng3 = HwmEng(root, tron_ctx, test_command="true", worker_count=1)
    eng3._idle_map[architect.ARCHITECT_WID] = False   # busy — same as 5a
    job3 = _hwm_job("triage-ri-mut", "engineer-13")
    m3 = {"architect": {"status": "busy", "current_job": job3, "spawned": True},
         "architect_queue": [], "triage_verdicts": {}}
    architect.advance(eng3, m3)
    _real_advance_delivery = architect._advance_delivery

    def _mutated_advance_delivery(eng_, manifest_, d):
        now = architect._clock(eng_, manifest_)
        if d.get("last_sent_at") is None:
            d["last_sent_at"] = now
        if (now - d["last_sent_at"]) >= architect.REDELIVER_AFTER:
            architect._redeliver(eng_, d, now)   # MUTATION: no idle check at all
    architect._advance_delivery = _mutated_advance_delivery
    try:
        for _ in range(architect.REDELIVER_AFTER * 5):
            eng3.tick_clock()
            architect.advance(eng3, m3)
    finally:
        architect._advance_delivery = _real_advance_delivery
    ok("RIG5-C (MUTATION -> RED, non-vacuity for RIG5-A1): dropping the "
       "idle gate re-sends on the interval alone — the SAME busy-the-"
       "whole-time scenario (5a) now races a live turn",
       len(eng3.resend_calls) > 0, f"resend_calls={eng3.resend_calls}")


def main():
    run_reconcile_gate_scenario()
    run_forward_scenario()
    run_phantom_triage_grace_scenario()
    run_reconcile_backstop_scenario()
    run_delivery_gap_rig()
    run_respawn_rig()
    run_multi_order_rig()
    run_no_progress_budget_rig()
    run_redeliver_idle_rig()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.architect_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
