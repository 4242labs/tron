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

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
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
            "block": None, "worker_id": "engineer-01-03", "ordered": True,
            "verdict": None, "resolved": False}
    mA["architect"]["current_job"] = jobA
    for _ in range(architect._ARCHITECT_IDLE_DEBOUNCE_TICKS + 1):
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
            "ordered": True, "verdict": None, "resolved": False}
    mB["architect"]["current_job"] = jobB
    for _ in range(architect._ARCHITECT_IDLE_DEBOUNCE_TICKS + 1):
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
            "ordered": True, "verdict": None, "resolved": False}
    mC["architect"]["current_job"] = jobC
    for _ in range(architect._ARCHITECT_IDLE_DEBOUNCE_TICKS + 10):
        architect._advance_triage(engW, mC, jobC)
    ok("PT3 (WORKING-ARCHITECT HOLD, R1b/A3 — must be GREEN): while the architect is "
       "provably mid-turn (_worker_working True) the backstop NEVER fires, however "
       "many ticks — no premature page, no multi-turn race",
       jobC.get("resolved") is not True and jobC.get("verdict") is None
       and jobC.get("idle_ticks", 0) == 0,
       f"resolved={jobC.get('resolved')} verdict={jobC.get('verdict')} "
       f"idle_ticks={jobC.get('idle_ticks')}")

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


def run_reconcile_backstop_scenario():
    """T2-12 regression: a NO-OP reconcile must not silently WEDGE the fleet. The
    architect takes its ordered reconcile turn, finds no forward impact, and its
    free-text ('no forward impact / work complete') is never routed as a structured
    `architect.reconciled` — so the block never enters `manifest['reconciled']` and,
    before the fix, `advance` held `current_job` busy FOREVER while the runner sat
    idle: 01-03's dispatch hung with no wall/page/retry. The shared R1b idle backstop
    (`_architect_settled_idle`) clears the gate once the architect settles idle after
    its ordered turn — completion tied to ENGINE STATE, never to parsed prose."""
    root = build_root()
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)

    # RB1 — settled idle, no architect.reconciled -> backstop marks reconciled + clears.
    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    jobA = {"kind": "reconcile", "block": "01-03", "after": "01-02", "ordered": True}
    mA = {"architect": {"status": "busy", "current_job": jobA, "spawned": True},
          "architect_queue": [], "reconciled": []}
    for _ in range(architect._ARCHITECT_IDLE_DEBOUNCE_TICKS + 1):
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
    jobB = {"kind": "reconcile", "block": "01-03", "after": "01-02", "ordered": True}
    mB = {"architect": {"status": "busy", "current_job": jobB, "spawned": True},
          "architect_queue": [], "reconciled": []}
    for _ in range(architect._ARCHITECT_IDLE_DEBOUNCE_TICKS + 10):
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
            "idle_ticks": 0}
    mC = {"architect": {"status": "busy", "current_job": jobC, "spawned": True},
          "architect_queue": [], "reconciled": ["01-03"]}
    architect.advance(eng2, mC)
    ok("RB3 (NORMAL RECONCILE PATH INTACT — must be GREEN): when architect.reconciled "
       "IS observed (block already in manifest['reconciled']) the gate clears via the "
       "normal arm and '01-03' appears exactly once (backstop never double-adds)",
       mC["architect"].get("current_job") is None
       and (mC.get("reconciled") or []).count("01-03") == 1,
       f"reconciled={mC.get('reconciled')} architect={mC['architect']}")

    # RB4 — live-like STARTED-then-SETTLED (peer-review #2 hardening): the architect
    # is observed working (turn genuinely taken), THEN settles idle -> the started-latch
    # permits the backstop to arm and clear the reconcile.
    class _StartsThenIdleEng(MiniEng):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._wk = [True, True]      # working for two ticks, then idle
        def _worker_working(self, wid):
            if wid != architect.ARCHITECT_WID:
                return False
            return self._wk.pop(0) if self._wk else False
    engS = _StartsThenIdleEng(root, tron_ctx, test_command="true", worker_count=1)
    jobD = {"kind": "reconcile", "block": "01-03", "after": "01-02", "ordered": True}
    mD = {"architect": {"status": "busy", "current_job": jobD, "spawned": True},
          "architect_queue": [], "reconciled": []}
    for _ in range(architect._ARCHITECT_IDLE_DEBOUNCE_TICKS + 3):
        architect.advance(engS, mD)
    ok("RB4 (STARTED-THEN-SETTLED ARMS — must be GREEN): once the architect is observed "
       "working (turn taken) and THEN settles idle, the backstop arms and clears the "
       "reconcile — the started-latch permits arming after a genuine turn",
       "01-03" in (mD.get("reconciled") or []) and mD["architect"].get("current_job") is None,
       f"reconciled={mD.get('reconciled')} architect={mD['architect']}")

    # RB5 — live-like COLD-START / SILENTLY-DEAD (peer-review #2 KILLER): the architect
    # is NEVER observed working. The backstop must NEVER arm (no silent false-clear of a
    # reconcile that never ran); the reconcile HOLDS so the run fails honestly on budget.
    class _NeverStartsEng(MiniEng):
        def _worker_working(self, wid):
            return False                 # architect never comes up
    engN = _NeverStartsEng(root, tron_ctx, test_command="true", worker_count=1)
    jobE = {"kind": "reconcile", "block": "01-03", "after": "01-02", "ordered": True}
    mE = {"architect": {"status": "busy", "current_job": jobE, "spawned": True},
          "architect_queue": [], "reconciled": []}
    for _ in range(architect._ARCHITECT_IDLE_DEBOUNCE_TICKS + 20):
        architect.advance(engN, mE)
    ok("RB5 (COLD-START/DEAD HOLD KILLER — must be GREEN): an architect NEVER observed "
       "working (slow cold-start or silently dead) NEVER arms the reconcile backstop, "
       "however many ticks — no silent false-clear; the reconcile holds (run fails "
       "honestly on budget) rather than falsely marking reconciled (peer-review #2)",
       "01-03" not in (mE.get("reconciled") or [])
       and mE["architect"].get("current_job") is not None,
       f"reconciled={mE.get('reconciled')} architect={mE['architect']}")

    # RB6 — ADR-0006 R1c (COLD-START ARCHITECT-LIVENESS KILLER): the same cold-start/
    # dead architect that RB5 proves the backstop must HOLD is now PAGED exactly once
    # (the pool-excluded architect finally has a liveness net) — the hold is loud, not
    # silent-to-budget. Reuses RB5's engN/mE state after its 22-tick drive.
    arch_pages = [p for p in getattr(engN, "operator_pages", [])
                  if (p.get("worker_id") == architect.ARCHITECT_WID
                      or p.get("block") == "01-03")]
    ok("RB6 (R1c COLD-START ARCHITECT PAGE — must be GREEN): a never-started architect is "
       "paged the operator EXACTLY ONCE (once-guard holds across the whole drive), while "
       "the reconcile job is still held (RB5) — a dead architect no longer wedges silently",
       len(arch_pages) == 1 and mE["architect"]["current_job"].get("stall_paged") is True
       and mE["architect"]["current_job"].get("cold_ticks", 0)
           >= architect._ARCHITECT_COLD_START_CAP_TICKS,
       f"arch_pages={arch_pages} job={mE['architect']['current_job']}")

    # RB7 — ADR-0006 R1d (STARTED-THEN-REFUSED FORWARD/LOG KILLER): the architect
    # TOOK its ordered forward turn (observed working) then settled idle having
    # authored NO branch (`land_via_grant` -> "fail-closed" for a never-created
    # branch). The job must NOT poll to budget nor benign-clear (dropping work) —
    # it routes LOUD to the operator once and frees the architect. Distinct from
    # R1c (never-started): here `arch_started` is set, so R1c stays silent and
    # R1d owns it — the clean partition.
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
        for _ in range(architect._ARCHITECT_IDLE_DEBOUNCE_TICKS + 4):
            architect.advance(engR, mF)
    finally:
        architect.landing.land_via_grant = _real_lvg
    r1d_pages = [p for p in getattr(engR, "operator_pages", [])
                 if p.get("block") == "09-09"]
    ok("RB7 (R1d STARTED-THEN-REFUSED FORWARD — must be GREEN): an architect that took its "
       "forward turn but authored no branch (fail-closed + settled idle) is routed to the "
       "operator ONCE and freed — never a silent wedge, never a benign drop; R1c stays quiet "
       "(arch_started set, so not the cold-start window)",
       len(r1d_pages) == 1 and mF["architect"].get("current_job") is None
       and not jobF.get("landed"),
       f"r1d_pages={r1d_pages} architect={mF['architect']} last_outcome={jobF.get('last_outcome')}")


def main():
    run_reconcile_gate_scenario()
    run_forward_scenario()
    run_phantom_triage_grace_scenario()
    run_reconcile_backstop_scenario()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.architect_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
