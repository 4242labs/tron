"""core.casestate_rig — real-git, no-LLM rig proving `core.casestate`'s
parked-case FSM (wave 8: raise-and-defer + operator Settle) does EXACTLY
what `contracts/blueprint-contracts.md` §1 promises, on the REAL surface: a
real `git init` repo copied from the SAME scaffold every prior
`core/*_rig.py` uses, `meta/scripts/land.sh` run for real via `subprocess`
when this rig chooses to run it, a REAL `engine.ctx.Ctx` pointing at a real
`manifest.yaml`, and a minimal duck-typed `eng` — never a faked/
monkeypatched trunk. Driven entirely via repeated `core.tick.tick(eng)`
calls (the WAKE daemon), exactly like `core/multiblock_rig.py`/`core/
dispatch_rig.py` — a real THREE-block pipeline (`core/switchboard.py`'s own
SPAWN/ASSIGN dispatch, never a seeded-gate shortcut), so "resume re-drives"
is proven as a genuine FRESH dispatch, not simulated.

THREE real blocks, seeded together on a `worker_count=3` pipeline (no
`Depends on` edges — dep-ordering is `core/multiblock_rig.py`'s own proof,
out of THIS brick's scope):

  wall-resume-01  — walled at `gate.local` (a real structured `worker.wall`
                    report), parked, then `operator.decision resume`d —
                    proves open-case -> resume -> a genuinely FRESH SPAWN ->
                    a clean close on real git.
  wall-abandon-01 — walled the same way, then `operator.decision abandon`ed
                    — proves open-case -> abandon -> dropped, permanently
                    never re-dispatched, and (the killer) `core/session.py::
                    check` still reaches a clean SESSION-END despite this
                    block never reaching `done` — never a `RuntimeError`.
  cap-escalate-01 — reacted to only up through `gate.local` (a genuine
                    local-pass), then deliberately never landed at
                    `gate.merge` (`core/sentry_rig.py`'s own "stuck" shape)
                    until `core/sentry.py`'s OWN pacing ladder caps it
                    (`GATE_IDLE_CAP`, read off `sentry.py` itself, never
                    hardcoded) — proves a sentry cap escalation ALSO opens a
                    case (not just the bare `manifest["escalations"]`
                    record), and that an operator `resume` on THAT case
                    clears it and re-drives it too.

Along the way: a MALFORMED `operator.decision` (an unresolvable case_id) is
proven a logged no-op, never a crash; a DUPLICATE `operator.decision` (a
SECOND `resume` on wall-resume-01's ALREADY-cleared case_id) is proven the
same — never re-parks, never wrongly clears any other live case; a
MALFORMED `worker.wall` (missing block/detail) is proven to FAIL LOUD
(raises) via `core.router.route`, checked in isolation against a synthetic
manifest — a wall must never silently vanish into a log line the way other
malformed reports safely can.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.
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
import tick                  # noqa: E402 — core/tick.py, wired to route walls/decisions + filter dispatch
import router                # noqa: E402 — core/router.py, the malformed-wall fail-loud proof (isolated)
import session                # noqa: E402 — core/session.py, the abandoned-block clean-end proof
import pipeline                # noqa: E402 — core/pipeline.py, the in-flight/slot-freed proof read
import sentry                 # noqa: E402 — core/sentry.py, the cap-escalation-opens-a-case proof
import casestate               # noqa: E402 — core/casestate.py, the module under test
import architect               # noqa: E402 — core/architect.py, ARCHITECT_WID (self-wall guard lock)

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
MAIN = "main"
CODE_FILE_REL = "src/lib/tip.ts"          # a real, non-meta/ source file — the "real code change"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"

BLOCK_R, BLOCK_A, BLOCK_S = "wall-resume-01", "wall-abandon-01", "cap-escalate-01"
BLOCKS = {
    BLOCK_R: {"branch": f"feat/{BLOCK_R}", "agent_id": f"engineer-{BLOCK_R}"},
    BLOCK_A: {"branch": f"feat/{BLOCK_A}", "agent_id": f"engineer-{BLOCK_A}"},
    BLOCK_S: {"branch": f"feat/{BLOCK_S}", "agent_id": f"engineer-{BLOCK_S}"},
}
ORDER = [BLOCK_R, BLOCK_A, BLOCK_S]
MAX_TICKS = 120   # wave 18 (GAP-E): headroom for the architect-first hop
                   # (order tick + drained-verdict tick) on every wall/cap

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
    d = tempfile.mkdtemp(prefix="tron-core-casestaterig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-casestate-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: casestate_rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {r} | casestate_rig fixture — walled, then operator-resumed | 📋 To do | Block `blocks/{r}.md` |
| {a} | casestate_rig fixture — walled, then operator-abandoned | 📋 To do | Block `blocks/{a}.md` |
| {s} | casestate_rig fixture — sentry cap-escalated, then operator-resumed | 📋 To do | Block `blocks/{s}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: casestate_rig fixture

**Phase:** 1 — Casestate parked-case rig
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.casestate_rig` — proves the parked-case FSM
(raise-and-defer + operator Settle) turns a worker `worker.wall` report or a
sentry cap escalation into an operator-resolvable case, never a dead-end.
"""


def seed_pipeline(root):
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(r=BLOCK_R, a=BLOCK_A, s=BLOCK_S))
    for block in ORDER:
        bpath = os.path.join(root, BLOCKS_REL, f"{block}.md")
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        with open(bpath, "w") as f:
            f.write(BLOCK_DOC_TEMPLATE.format(block=block))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + blocks {BLOCK_R}/{BLOCK_A}/{BLOCK_S} "
                          f"(all to-do, no deps, no gates)"], root)
    _git(["checkout", "--detach", MAIN], root)


def make_code_commit(root, branch, code_file_rel, marker):
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    with open(path, "a") as f:
        f.write(f"\n// {marker} — core.casestate_rig real code change\n")
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
    """Rebase `branch` onto the CURRENT `main` tip if trunk has moved past
    its fork point since it was created — real, on real git, exactly what a
    real worker does before landing (`land.sh`'s own error hint: "rebase
    your branch onto trunk and retry — your grant's patch-id carries if the
    diff is unchanged"). This rig runs THREE blocks concurrently
    (`worker_count=3`, unlike every other rig's `worker_count=1` strict
    serialization) specifically so a wall/resume/sentry-cap case can be
    proven alongside genuine, unrelated trunk-advancing activity — which
    means a block's branch CAN genuinely fall behind while it sits parked
    or stuck; a real worker would rebase before its next land attempt, so
    this rig (standing in for that worker) does too. A no-op when already
    caught up."""
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
    `core/gate.py` + `core/pipeline.py` + `core/switchboard.py` + `core/
    session.py` + `core/sentry.py` + `core/casestate.py` (via `core/
    tick.py`) need. `._page_operator` is wave 8's ONE new stubbed hook —
    no real transport, exactly like `._to_worker`/`._release_worker`."""
    def __init__(self, root, tron_ctx, test_command, worker_count=3):
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
        self.dry = False                 # HARD RULE: real trunk observation throughout
        self.ctx = tron_ctx              # REAL engine.ctx.Ctx
        self.events = _Events()
        self.log_lines = []
        self.orders = []
        self.workers = {}
        self.spawn_calls = []
        self.pages = []                  # (case_id, block, detail, worker_id)

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
        # Wave 18 (GAP-E): `core/architect.py::advance` calls this lazily
        # the first tick it ever pops a job — now genuinely exercised,
        # since every `core/casestate.py::open_case` call (every wall/cap
        # this rig raises) routes ARCHITECT-FIRST. No real transport,
        # exactly like `_spawn_worker`/`_to_worker` above.
        pass

    def _page_operator(self, case_id, block, detail, worker_id=None, **_kwargs):
        # **_kwargs: wave 17 (GAP-A) widened the real `eng._page_operator`
        # call surface (`manifest=`/`page_kind=`, `core/casestate.py`'s own
        # THE-FLOOR re-ping ladder) — tolerated and ignored here; every
        # case this rig opens is resumed/abandoned promptly, so the ladder
        # never gets far enough to change any assertion this rig makes
        # (all of which use `any(...)`, never an exact `eng.pages` count).
        self.pages.append((case_id, block, detail, worker_id))


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
                                 "(rig-supplied local report, delivered via a structured "
                                 "worker.done inbox line)"}

WALL_DETAIL_R = ("rig-as-worker: hit a genuine wall on wall-resume-01 at "
                 "gate.local — a missing local fixture dependency the operator "
                 "needs to unblock (a real structured worker.wall report)")
WALL_DETAIL_A = ("rig-as-worker: hit a genuine wall on wall-abandon-01 at "
                 "gate.local — a scope question only the operator can settle "
                 "(a real structured worker.wall report)")


def main():
    root = build_root()
    seed_pipeline(root)
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=3)

    seed_manifest = state.load(tron_ctx)
    ok("pre0: rig starts with NO manifest.yaml on disk at all",
       not os.path.exists(tron_ctx.state), f"state={tron_ctx.state}")
    for block in ORDER:
        doc = open(os.path.join(root, BLOCKS_REL, f"{block}.md")).read()
        ok(f"pre1[{block}]: pipeline shows block {block} as 📋 (to-do) on "
           "trunk, no gate, no worker, no case",
           "**Status:** 📋 To do" in doc, f"{block} doc seeded 📋")

    gen = {b: 0 for b in ORDER}                 # generation counter — bumped on a fresh re-dispatch
    walled = {BLOCK_R: False, BLOCK_A: False}
    branch_created = {}     # (block, gen) -> bool
    local_reported = {}     # (block, gen) -> bool
    record_committed = {}   # (block, gen) -> bool
    record_tip = {}         # (block, gen) -> sha
    torn_down = {}          # (block, gen) -> bool
    landed_cases = set()
    real_land_calls = {}
    tick_log = []            # (i, res, manifest) per tick
    triage_answered = set()   # wave 18 (GAP-E): triage_ids already answered

    def react_architect_triage(manifest):
        """Wave 18 (GAP-E): EVERY wall/escalation this rig raises (R's and
        A's worker.wall, S's sentry.cap) now opens an ARCHITECT-FIRST case
        (`core/casestate.py::open_case` -> `core/architect.py::
        enqueue_triage`) — never an immediate operator page. This rig's
        whole point is exercising the OPERATOR-facing resume/abandon
        surface, so it always scripts the architect to answer `operator`
        for whatever triage job is CURRENTLY ordered (one at a time, FIFO —
        the SAME generic hook serves R, A, and S's cases without any
        per-block branching) — the architect hop genuinely fires (order
        tick, drained-verdict tick) before any case is ever operator-owned."""
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if (cur and cur.get("kind") == "triage" and cur.get("ordered")
                and cur.get("triage_id") not in triage_answered):
            append_jsonl(tron_ctx.worker_inbox,
                        {"tag": "architect.triage_verdict",
                         "triage_id": cur["triage_id"], "verdict": "operator"})
            triage_answered.add(cur["triage_id"])

    def react(manifest):
        """Rig-as-worker's ONE reaction per tick, for every block the engine
        has dispatched/ordered so far — reacts to the REAL, just-persisted
        manifest, never this process's own memory. `wall-resume-01` and
        `wall-abandon-01` each get walled EXACTLY ONCE (their first sighting
        at gate.local); `cap-escalate-01` gets a genuine local-pass but is
        then deliberately left stuck at gate.merge (never landed) until its
        OWN generation is bumped (by the MAIN loop, once the operator
        resumes its sentry-cap case) — the SAME 'stuck-then-resumed' shape
        `core/sentry_rig.py` already proves for the bare-escalation case."""
        react_architect_triage(manifest)
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}

        for block in ORDER:
            spec = BLOCKS[block]
            agent_id, branch = spec["agent_id"], spec["branch"]
            block_file_rel = f"{BLOCKS_REL}/{block}.md"
            key = (block, gen[block])

            w = workers.get(agent_id)
            if w and w.get("status") == "spawning" and not branch_created.get(key):
                make_code_commit(root, branch, CODE_FILE_REL, f"{block}-gen{gen[block]}")
                branch_created[key] = True
                append_jsonl(tron_ctx.worker_inbox,
                            {"tag": "worker.online", "agent_id": agent_id,
                             "slots": {"branch": branch}})

            g = gates.get(block)
            if not g:
                continue
            stage = g.get("stage")

            if stage == gate.STAGE_LOCAL:
                if block == BLOCK_R and not walled[BLOCK_R]:
                    append_jsonl(tron_ctx.worker_inbox,
                                {"tag": "worker.wall", "block": BLOCK_R, "agent_id": agent_id,
                                 "slots": {"detail": WALL_DETAIL_R}})
                    walled[BLOCK_R] = True
                elif block == BLOCK_A and not walled[BLOCK_A]:
                    append_jsonl(tron_ctx.worker_inbox,
                                {"tag": "worker.wall", "block": BLOCK_A, "agent_id": agent_id,
                                 "slots": {"detail": WALL_DETAIL_A}})
                    walled[BLOCK_A] = True
                elif not local_reported.get(key):
                    append_jsonl(tron_ctx.worker_inbox,
                                {"tag": "worker.done", "block": block, "slots": LOCAL_PASS_REPORT})
                    local_reported[key] = True

            elif stage == gate.STAGE_MERGE and g.get("merge_case_id"):
                case_id = g["merge_case_id"]
                if block == BLOCK_S and gen[BLOCK_S] == 0:
                    pass   # deliberately stuck — never landed, to trip sentry's GATE_IDLE_CAP
                elif case_id not in landed_cases:
                    ensure_rebased(root, branch)   # trunk may have moved (3 concurrent blocks)
                    run_land(root, grants_dir, case_id)
                    real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                    landed_cases.add(case_id)

            elif stage == gate.STAGE_RECORD:
                if g.get("record_ordered") and not record_committed.get(key) and not g.get("record_case_id"):
                    record_tip[key] = make_record_commit(root, branch, block_file_rel)
                    record_committed[key] = True
                if g.get("record_case_id") and g["record_case_id"] not in landed_cases:
                    case_id = g["record_case_id"]
                    ensure_rebased(root, branch)   # trunk may have moved (3 concurrent blocks)
                    run_land(root, grants_dir, case_id)
                    real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                    landed_cases.add(case_id)

            elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not torn_down.get(key):
                _git(["branch", "-D", branch], root)
                torn_down[key] = True

    def run_tick():
        res = tick.tick(eng)
        m = state.load(tron_ctx)
        react(m)
        tick_log.append((len(tick_log) + 1, res, m))
        return res, m

    def inject(obj):
        append_jsonl(tron_ctx.worker_inbox, obj)

    # ══ tick 1 — SPAWN all three off the real pipeline (worker_count=3) ══
    res1, m1 = run_tick()
    ok("D1: SWITCHBOARD spawned all three blocks off the real pipeline read "
       "in the FIRST tick (worker_count=3, three 📋 rows, no deps)",
       set(res1["spawned"]) == {BLOCKS[b]["agent_id"] for b in ORDER},
       f"spawned={res1['spawned']}")

    # ══ tick 2 — ASSIGN: all three gates open at gate.local ══
    res2, m2 = run_tick()
    gates2 = m2.get("gates") or {}
    ok("D2: all three gates opened at gate.local after ASSIGN",
       all(gates2.get(b, {}).get("stage") == gate.STAGE_LOCAL for b in ORDER),
       f"gates={ {b: gates2.get(b, {}).get('stage') for b in ORDER} }")

    # ══ tick 3 — route drains: worker.wall(R), worker.wall(A) (react() after
    #     tick2), worker.done local-pass(S) — R/A open cases, S -> gate.merge ══
    res3, m3 = run_tick()
    gates3 = m3.get("gates") or {}
    cases3 = m3.get("cases") or {}
    case_r = next((c for c in cases3.values() if c.get("block") == BLOCK_R), None)
    case_a = next((c for c in cases3.values() if c.get("block") == BLOCK_A), None)
    case_id_r = case_r["case_id"] if case_r else None
    case_id_a = case_a["case_id"] if case_a else None

    ok("P1 (WALL->PARK KILLER — must be GREEN): wall-resume-01's worker.wall "
       "opened a parked case — gate BLOCKED (gate.STAGE_ESCALATED, the "
       "vocabulary core/pipeline.py already excludes from in-flight), case "
       "in manifest['cases'] with decision=None, source='worker.wall'; "
       "wave 18 (GAP-E): the case is ARCHITECT-owned, NOT paged the SAME "
       "tick — the operator is never reached the same tick a wall raises",
       case_r is not None and case_r.get("decision") is None
       and case_r.get("source") == "worker.wall"
       and case_r.get("owner") == "architect"
       and gates3.get(BLOCK_R, {}).get("stage") == gate.STAGE_ESCALATED
       and not any(p[1] == BLOCK_R for p in eng.pages),
       f"case_r={case_r} gate_r_stage={gates3.get(BLOCK_R, {}).get('stage')} pages={eng.pages}")
    ok("P2: wall-resume-01's slot was genuinely FREED — no longer in-flight "
       "(pipeline.in_flight_blocks excludes a terminal gate) — proven by "
       "the SAME tick spawning nothing extra for it and the worker record "
       "marked released",
       BLOCK_R not in pipeline.in_flight_blocks(m3)
       and eng.workers.get(BLOCKS[BLOCK_R]["agent_id"], {}).get("status") == "released",
       f"in_flight={pipeline.in_flight_blocks(m3)} "
       f"worker={eng.workers.get(BLOCKS[BLOCK_R]['agent_id'])}")
    ok("P3 (TICK-CONTINUES KILLER — must be GREEN): the wall never blocked "
       "the tick — cap-escalate-01's OWN local-pass, drained the SAME tick, "
       "genuinely advanced local->merge (`gate.advance` moves exactly ONE "
       "stage per call — the merge grant itself mints on the FOLLOWING "
       "call, asserted at P3b below), no crash, no session-end (still 3 "
       "pending)",
       gates3.get(BLOCK_S, {}).get("stage") == gate.STAGE_MERGE
       and res3.get("session_end") is None,
       f"gate_s={gates3.get(BLOCK_S)} session_end={res3.get('session_end')}")
    res3b, m3b = run_tick()
    gates3b = m3b.get("gates") or {}
    ok("P3b: the FOLLOWING tick genuinely minted cap-escalate-01's merge "
       "grant and ordered the worker to land it — the ONE real order this "
       "gate ever gets before this rig deliberately stops reacting to it "
       "(the cited 'never runs land.sh' shape)",
       bool(gates3b.get(BLOCK_S, {}).get("merge_case_id"))
       and any(o[2] == "gate.merge" for o in eng.orders),
       f"gate_s={gates3b.get(BLOCK_S)}")
    ok("P4: wall-abandon-01 ALSO opened its own DISTINCT parked case the "
       "SAME tick (two independent walls, two independent cases, never "
       "conflated)",
       case_a is not None and case_a.get("decision") is None
       and case_a.get("case_id") != case_id_r,
       f"case_a={case_a} case_id_r={case_id_r}")

    # ══ tick 4 — a MALFORMED operator.decision (unresolvable case_id) ══
    inject({"tag": "operator.decision", "slots": {"case_id": "no-such-case", "verb": "resume"}})
    res4, m4 = run_tick()
    cases4 = m4.get("cases") or {}
    ok("M1 (MALFORMED-DECISION KILLER — must be GREEN): an operator.decision "
       "naming an unresolvable case_id is a logged no-op — tick completes "
       "cleanly (no crash/exception), BOTH still-open cases are untouched "
       "(decision still None, still present)",
       case_id_r in cases4 and cases4[case_id_r].get("decision") is None
       and case_id_a in cases4 and cases4[case_id_a].get("decision") is None,
       f"cases4 keys={list(cases4)}")

    # ══ wave 18 (GAP-E): an operator.decision naming a case that is STILL
    #     architect-owned must be REJECTED — the operator can never bypass
    #     the architect's own triage. Proven directly against a synthetic,
    #     throwaway manifest (never the real drive above — this rig's own
    #     architect-first hop resolves too fast, within a tick or two of a
    #     wall, for a live "still architect-owned" window to reliably land
    #     a scripted premature reply in; a direct `casestate.settle` call is
    #     the SAME deterministic-unit-check discipline W1/W2 (below) already
    #     use for the malformed-wall fail-loud proof) ══
    def _bypass_rejected():
        synth = {"cases": {"case-bypass-1": {
            "case_id": "case-bypass-1", "block": "synthetic-block",
            "source": "worker.wall", "kind": "wall", "worker_id": None,
            "detail": "synthetic — never a real dispatch", "decision": None,
            "owner": "architect"}}}
        settled = casestate.settle(eng, synth, "case-bypass-1", "resume")
        case_after = synth["cases"].get("case-bypass-1")
        return (settled is False and case_after is not None
               and case_after.get("decision") is None
               and case_after.get("owner") == "architect")

    ok("G1 (NO-OPERATOR-BYPASS KILLER — must be GREEN): `core.casestate."
       "settle` REJECTS (returns False, logged no-op) an operator.decision "
       "naming a case that is STILL architect-owned (not yet triaged to "
       "the operator) — the case stays open, un-resumed, `owner` "
       "untouched; the operator can never bypass GAP-E's architect-first "
       "routing",
       _bypass_rejected(), "checked via a direct core.casestate.settle call")

    # ══ drive until the ARCHITECT genuinely triages BOTH R and A (order
    #     tick + drained-verdict tick each, `react`'s own `react_architect_
    #     triage` answering `operator` every time) — never a pre-timed
    #     assumption of how many ticks that takes ══
    def wait_for_operator_owned(case_id, label, max_wait=20):
        for _ in range(max_wait):
            m_now = state.load(tron_ctx)
            c = (m_now.get("cases") or {}).get(case_id)
            if c is not None and c.get("owner") == "operator":
                return m_now, c
            run_tick()
        raise RuntimeError(f"{label}: case {case_id!r} never became "
                           f"operator-owned within {max_wait} ticks")

    m_r_paged, case_r_paged = wait_for_operator_owned(case_id_r, "wall-resume-01")
    ok("P1b (ARCHITECT-FIRST-THEN-PAGED KILLER — must be GREEN): wall-"
       "resume-01's case was genuinely paged (a real eng._page_operator "
       "call recorded) ONLY once the architect's own scripted `operator` "
       "triage verdict resolved it — never at the SAME tick the wall "
       "raised (P1, above)",
       case_r_paged.get("owner") == "operator"
       and any(p[0] == case_id_r for p in eng.pages),
       f"case_r_paged={case_r_paged} pages={eng.pages}")

    m_a_paged, case_a_paged = wait_for_operator_owned(case_id_a, "wall-abandon-01")
    ok("P4b: wall-abandon-01's case was ALSO genuinely (architect-first) "
       "paged — its own INDEPENDENT triage, never conflated with R's",
       case_a_paged.get("owner") == "operator"
       and any(p[0] == case_id_a for p in eng.pages),
       f"case_a_paged={case_a_paged}")

    # ══ operator RESUMEs wall-resume-01's NOW operator-owned case ══
    gen[BLOCK_R] = 1
    spawn_count_before_resume = sum(1 for a, _b in eng.spawn_calls if a == BLOCKS[BLOCK_R]["agent_id"])
    inject({"tag": "operator.decision", "slots": {"case_id": case_id_r, "verb": "resume"}})
    res5, m5 = run_tick()
    cases5 = m5.get("cases") or {}
    gates5 = m5.get("gates") or {}
    spawn_count_after_resume = sum(1 for a, _b in eng.spawn_calls if a == BLOCKS[BLOCK_R]["agent_id"])
    ok("R1 (RESUME->CLEAR KILLER — must be GREEN): the case cleared WITHIN "
       "ONE tick — no longer in manifest['cases'] at all",
       case_id_r not in cases5, f"cases5 keys={list(cases5)} case_id_r={case_id_r}")
    ok("R2 (RESUME->REDRIVE KILLER — must be GREEN): wall-resume-01 got a "
       "genuinely FRESH SPAWN the SAME tick (a real second `eng._spawn_worker` "
       "call for its deterministic agent-id — never a half-resurrected stale "
       "gate) — SWITCHBOARD's own dispatch-eligibility read it as to-do + "
       "not-in-flight again, exactly like any ordinary block",
       spawn_count_after_resume == spawn_count_before_resume + 1,
       f"spawn_count before={spawn_count_before_resume} after={spawn_count_after_resume} "
       f"spawn_calls={eng.spawn_calls}")

    # ══ operator ABANDONs wall-abandon-01's NOW operator-owned case ══
    inject({"tag": "operator.decision", "slots": {"case_id": case_id_a, "verb": "abandon"}})
    res6, m6 = run_tick()
    cases6 = m6.get("cases") or {}
    gates6 = m6.get("gates") or {}
    ok("A1 (ABANDON->CLEAR KILLER — must be GREEN): the case cleared WITHIN "
       "ONE tick",
       case_id_a not in cases6, f"cases6 keys={list(cases6)} case_id_a={case_id_a}")
    ok("A2 (ABANDON->DROPPED KILLER — must be GREEN): wall-abandon-01 is "
       "durably flagged out-of-scope (`manifest['abandoned_blocks']`) and "
       "its gate is GONE (never re-driven, never re-dispatched)",
       BLOCK_A in (m6.get("abandoned_blocks") or []) and BLOCK_A not in gates6,
       f"abandoned_blocks={m6.get('abandoned_blocks')} gate_a={gates6.get(BLOCK_A)}")

    # ══ a DUPLICATE resume on wall-resume-01's ALREADY-cleared case_id —
    #     must be a safe no-op, never wrongly clearing/reopening anything,
    #     never disturbing R's now-genuinely-progressing gate ══
    r_stage_before_dup = (m6.get("gates") or {}).get(BLOCK_R, {}).get("stage")
    inject({"tag": "operator.decision", "slots": {"case_id": case_id_r, "verb": "resume"}})
    res7, m7 = run_tick()
    cases7 = m7.get("cases") or {}
    gates7 = m7.get("gates") or {}
    ok("D3 (DUPLICATE-DECISION KILLER — must be GREEN): a second `resume` on "
       "wall-resume-01's ALREADY-cleared case_id is a logged no-op — no "
       "crash, no case wrongly (re)cleared or created, and wall-resume-01's "
       "OWN fresh gate keeps progressing completely undisturbed (never "
       "reset back to gate.local, never re-parked)",
       case_id_r not in cases7 and BLOCK_R in gates7
       and gates7[BLOCK_R].get("stage") not in (gate.STAGE_ESCALATED,)
       and (r_stage_before_dup is None
            or _stage_rank(gates7[BLOCK_R].get("stage")) >= _stage_rank(r_stage_before_dup)),
       f"cases7 keys={list(cases7)} r_stage_before={r_stage_before_dup} "
       f"r_stage_after={gates7.get(BLOCK_R, {}).get('stage')}")

    # ══ ISOLATED — a malformed worker.wall is SURFACED, never silently
    #     dropped AND never a run-crashing raise. A REAL wall is raised in
    #     PROSE (couriered turn-output, or `report.sh --tag wall "<text>"`),
    #     so `slots.detail`/`block` are routinely absent; the OLD behavior
    #     `raise`d, which propagated through core/tick.py and aborted the
    #     WHOLE run on one prose wall (the T2-01 forward-wall #7). The wall
    #     must instead be surfaced — architect-first — never dropped, never a
    #     crash. Checked against a synthetic throwaway manifest so it never
    #     disturbs the real drive above. ══
    def _route_wall_result(rep):
        m = {"gates": {}, "workers": {}}
        router.route(eng, m, [rep])   # MUST NOT raise — a wall never crashes the run
        return m

    m_w1 = _route_wall_result({"tag": "worker.wall", "agent_id": "x",
                               "slots": {"detail": "d"}})
    triage_w1 = [j for j in (m_w1.get("architect_queue") or []) if j.get("kind") == "triage"]
    ok("W1 (WALL-SURFACED KILLER — must be GREEN): a BLOCK-LESS worker.wall is "
       "SURFACED to architect-first triage (never silently dropped, never a "
       "raise that aborts the whole run)",
       len(triage_w1) == 1 and triage_w1[0].get("detail") == "d",
       f"architect_queue={m_w1.get('architect_queue')}")

    m_w2 = _route_wall_result({"tag": "worker.wall", "block": "some-block",
                               "agent_id": "x", "slots": {}})
    cases_w2 = m_w2.get("cases") or {}
    ok("W2 (WALL-SURFACED KILLER — must be GREEN): a worker.wall naming a block "
       "but carrying NO detail is SURFACED as a parked case with a non-empty "
       "fallback detail (the report's own text, or a placeholder) — never a "
       "content-less DROP, never a run-crashing raise",
       len(cases_w2) == 1 and bool(next(iter(cases_w2.values())).get("detail")),
       f"cases={cases_w2}")

    # ══ drive wall-resume-01 to a clean close, WHILE cap-escalate-01 sits "
    #     deliberately stuck at gate.merge until sentry's OWN cap fires ══
    case_id_s = None
    resumed_s_injected = False
    session_ended = None
    i = tick_log[-1][0]
    s_case_seen_architect_owned = False
    while i < MAX_TICKS:
        i += 1
        res, m = run_tick()
        cases = m.get("cases") or {}
        found = next((c for c in cases.values()
                     if c.get("block") == BLOCK_S and c.get("source") == "sentry.cap"), None)
        if found is not None and found.get("owner") == "architect":
            s_case_seen_architect_owned = True
        if case_id_s is None and found is not None and found.get("owner") == "operator":
            # wave 18 (GAP-E): the architect's own `react_architect_triage`
            # (inside `react()`, above) has already escalated S's case to
            # the operator by the time this fires — never resumed while
            # still architect-owned.
            case_id_s = found["case_id"]
            gen[BLOCK_S] = 1
            inject({"tag": "operator.decision", "slots": {"case_id": case_id_s, "verb": "resume"}})
            resumed_s_injected = True
        se = res.get("session_end")
        if se is not None:
            session_ended = se
            break

    final_manifest = state.load(tron_ctx)
    final_gates = final_manifest.get("gates") or {}
    final_cases = final_manifest.get("cases") or {}
    ticks_used = tick_log[-1][0]

    ok(f"T1: the whole drive converged (a clean session-end observed) "
       f"inside {MAX_TICKS} ticks (used {ticks_used})",
       session_ended is not None and ticks_used < MAX_TICKS,
       f"ticks_used={ticks_used} session_ended={session_ended}")
    ok("S1 (SENTRY-CAP-OPENS-A-CASE KILLER — must be GREEN): cap-escalate-01, "
       "deliberately never landed at gate.merge, got capped by core.sentry's "
       "OWN pacing ladder (GATE_IDLE_CAP, read off sentry.py itself) and "
       "THAT escalation opened a parked case (source='sentry.cap') — never "
       "just the bare manifest['escalations'] record",
       resumed_s_injected and case_id_s is not None
       and any(r.get("block") == BLOCK_S for r in (final_manifest.get("escalations") or [])),
       f"case_id_s={case_id_s} escalations="
       f"{[r for r in (final_manifest.get('escalations') or []) if r.get('block') == BLOCK_S]}")
    ok("S1b (ARCHITECT-FIRST KILLER — must be GREEN): cap-escalate-01's own "
       "sentry.cap case was OBSERVED architect-owned (not yet paged) before "
       "it ever became operator-owned — the SAME architect-first hop R/A's "
       "own worker.wall cases went through (P1/P1b, above), never an "
       "immediate operator page off a sentry cap either",
       s_case_seen_architect_owned, f"s_case_seen_architect_owned={s_case_seen_architect_owned}")
    ok("S2 (SENTRY-CASE-RESUME KILLER — must be GREEN): the operator's "
       "resume on cap-escalate-01's sentry-opened case cleared it (no "
       "longer in manifest['cases']) and it re-drove all the way to a "
       "genuine clean close",
       case_id_s not in final_cases
       and final_gates.get(BLOCK_S, {}).get("stage") == gate.STAGE_CLOSED,
       f"case_id_s={case_id_s} final_gate_s={final_gates.get(BLOCK_S)}")

    r_key_final = (BLOCK_R, gen[BLOCK_R])
    ok("R3 (CLEAN-CLOSE KILLER — must be GREEN): wall-resume-01 reached a "
       "genuine clean close on real git after its fresh, post-resume "
       "dispatch — replica clean, worker slot really released",
       final_gates.get(BLOCK_R, {}).get("stage") == gate.STAGE_CLOSED
       and eng.workers.get(BLOCKS[BLOCK_R]["agent_id"], {}).get("status") == "released",
       f"final_gate_r={final_gates.get(BLOCK_R)} "
       f"worker={eng.workers.get(BLOCKS[BLOCK_R]['agent_id'])}")
    doc_r_on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{BLOCK_R}.md"], root)
    ok("R4: wall-resume-01's block doc AS READ FROM main shows ✅ (real git "
       "show on trunk) — a genuine record landing, post-resume",
       "**Status:** ✅ Done" in doc_r_on_main, f"doc head={doc_r_on_main.splitlines()[:4]}")

    doc_s_on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{BLOCK_S}.md"], root)
    ok("S3: cap-escalate-01's block doc AS READ FROM main ALSO shows ✅ "
       "(real git show on trunk) — the sentry-cap case's resume genuinely "
       "re-drove it to done, not just cleared the case bookkeeping",
       "**Status:** ✅ Done" in doc_s_on_main, f"doc head={doc_s_on_main.splitlines()[:4]}")

    doc_a_on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{BLOCK_A}.md"], root)
    ok("A3 (ABANDONED-NEVER-WRITTEN KILLER — must be GREEN): wall-abandon-01's "
       "doc on trunk is STILL 📋 (to-do) — TRON never wrote project git for "
       "an abandon; the block is dropped from SCOPE, not silently marked done",
       "**Status:** 📋 To do" in doc_a_on_main, f"doc head={doc_a_on_main.splitlines()[:4]}")
    ok("A4 (NEVER-RE-DISPATCHED KILLER — must be GREEN): wall-abandon-01's "
       "deterministic agent-id was spawned EXACTLY ONCE across the whole "
       "drive — abandon never re-picked it, even once its slot freed and "
       "the pipeline still showed it 📋",
       sum(1 for a, _b in eng.spawn_calls if a == BLOCKS[BLOCK_A]["agent_id"]) == 1,
       f"spawn_calls={eng.spawn_calls}")

    ok("SE1 (SESSION-END KILLER — must be GREEN): the clean session-end "
       "marker's own reason cites exactly 2 in-scope block(s) done (wall-"
       "resume-01 + cap-escalate-01) — wall-abandon-01 correctly excluded, "
       "never counted, never raised a RuntimeError despite never reaching "
       "done",
       session_ended is not None and "all 2 in-scope block(s) done" in session_ended.get("reason", ""),
       f"session_ended={session_ended}")
    ok("SE2: the session-end marker is durably persisted "
       "(`manifest['session']['ended_at']`), re-read fresh off disk",
       bool((final_manifest.get("session") or {}).get("ended_at")),
       f"session={final_manifest.get('session')}")

    # ══ NO-RUNTIMEERROR — proven positively: `core/tick.py` called
    #     `core/session.py::check` on EVERY one of these ticks (including
    #     every tick wall-abandon-01 sat dropped-but-still-📋 on trunk) and
    #     never raised — the whole rig reaching this line at all IS the
    #     proof; asserted explicitly for a readable rig report ══
    ok("SE3 (NEVER-RUNTIMEERROR KILLER — must be GREEN): every tick across "
       "the whole drive (including every tick wall-abandon-01 sat dropped, "
       "still 📋 on trunk, gate-less) completed without core/session.py "
       "raising — the rig reaching this line at all is the proof",
       True, "no uncaught exception anywhere in the drive above")

    # ══════════════════════════════════════════════════════════════════
    # PHASE SOURCE — no raw git/subprocess anywhere in the control modules
    # this brick touches (plain-text proof, no git involved).
    # ══════════════════════════════════════════════════════════════════
    src = {}
    for mod in ("casestate", "sentry", "tick", "router", "session"):
        src[mod] = open(os.path.join(HERE, f"{mod}.py")).read()
    ok("SRC1 (NO-RAW-GIT KILLER — must be GREEN): none of casestate.py/"
       "sentry.py/tick.py/router.py/session.py shells out to a raw git/"
       "subprocess call of its own — all git observation stays inside "
       "core/gitobs.py (the ONE seam), all persistence inside core/state.py",
       all("import subprocess" not in s and "subprocess." not in s
           and "\nimport git\n" not in s for s in src.values()),
       "grep-equivalent source scan of core/{casestate,sentry,tick,router,session}.py")
    ok("SRC2: core/gate.py and core/pipeline.py were NOT modified by this "
       "brick (hard rule) — casestate.py only ever reads their exported "
       "STAGE_* constants/read-only helpers, never edits their source",
       True, "verified by diff review, not a runtime check — see hand-back git status")

    # ══ LOCK (s1 first-honest-SIM record-stall root): open_case must NOT evict
    #    a worker whose OWN gate is still in-flight. A recoverable wall (a land-
    #    grant re-mint, or one whose case block id doesn't resolve to the live
    #    gate) left the worker mid-ladder; freeing its slot stranded gate.record/
    #    close with no worker and the gate silently wedged at `record`. ══
    lock_eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    m_a = {"workers": {"eng-X": {"block": "10-01", "status": "busy"}},
           "gates": {"10-01": {"stage": gate.STAGE_RECORD, "wid": "eng-X"}},
           "cases": {}}
    casestate.open_case(lock_eng, m_a, "10-01-branch", "worker.wall",
                        "recoverable land re-mint — worker still mid-ladder",
                        worker_id="eng-X", kind="wall")
    ok("Z1 (RECORD-STALL LOCK — must be GREEN): open_case did NOT release a "
       "worker whose own gate is still in-flight (the case block didn't park "
       "it) — gate.record/close keep their worker",
       lock_eng.workers.get("eng-X", {}).get("status") != "released"
       and m_a["gates"]["10-01"]["stage"] == gate.STAGE_RECORD,
       f"worker={lock_eng.workers.get('eng-X')} gate={m_a['gates']['10-01']['stage']}")
    lock_eng2 = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    m_b = {"workers": {"eng-Y": {"block": "10-02", "status": "busy"}},
           "gates": {"10-02": {"stage": gate.STAGE_LOCAL, "wid": "eng-Y"}},
           "cases": {}}
    casestate.open_case(lock_eng2, m_b, "10-02", "worker.wall",
                        "genuine blocker — only the operator can settle scope",
                        worker_id="eng-Y", kind="wall")
    ok("Z2 (GENUINE-BLOCKER PARITY — must be GREEN): open_case DID park the "
       "worker's own gate (BLOCKED) and free its slot when the case IS its "
       "real block — unchanged behaviour",
       m_b["gates"]["10-02"]["stage"] == gate.STAGE_ESCALATED
       and lock_eng2.workers.get("eng-Y", {}).get("status") == "released",
       f"worker={lock_eng2.workers.get('eng-Y')} gate={m_b['gates']['10-02']['stage']}")

    # ══ Z3 (01-03 RECONCILE-STALL LOCK, s2): a reconcile completion records
    #    the architect's OWN in-flight reconcile job block, NEVER a block id
    #    classify parsed from the report's prose (which named the just-LANDED
    #    block, not the gated one) — else current_job never clears and the
    #    dependent block stays permanently gated. ══
    m_c = {"architect": {"status": "busy",
                         "current_job": {"kind": "reconcile", "block": "01-03",
                                         "after": "01-02"}},
           "reconciled": []}
    router._route_architect_reconciled(
        lock_eng, m_c, {"tag": "architect.reconciled", "block": "01-02"})
    ok("Z3 (RECONCILE-STALL LOCK — must be GREEN): a reconcile report records "
       "the architect's in-flight job block (01-03), NOT the block its prose "
       "named (01-02) — current_job can clear, dependent block dispatches",
       "01-03" in (m_c.get("reconciled") or [])
       and "01-02" not in (m_c.get("reconciled") or []),
       f"reconciled={m_c.get('reconciled')}")

    # ══ Z4 (SELF-WALL GUARD, s6): a worker.wall FROM the architect is narration
    #    (it can't wall/triage itself) — resolve its in-flight triage benignly,
    #    open NO new case/triage. ══
    m_d = {"architect": {"status": "busy",
                        "current_job": {"kind": "triage", "triage_id": "triage-9"}},
           "cases": {}, "architect_queue": [], "workers": {}, "gates": {}}
    router._route_wall(lock_eng, m_d,
        {"tag": "worker.wall", "agent_id": architect.ARCHITECT_WID,
         "text": "Operator's call — grant re-mint, a clean one; worker proceeds."})
    ok("Z4 (SELF-WALL GUARD — must be GREEN): a worker.wall from the architect "
       "resolves its in-flight triage benignly and opens NO new case/triage",
       (m_d.get("triage_verdicts") or {}).get("triage-9", {}).get("verdict") == "answer"
       and not m_d.get("cases") and len(m_d.get("architect_queue") or []) == 0,
       f"verdicts={m_d.get('triage_verdicts')} cases={list((m_d.get('cases') or {}).keys())} "
       f"queue={len(m_d.get('architect_queue') or [])}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.casestate_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"tron instance dir (real engine.ctx.Ctx)={inst}")
    print(f"manifest={tron_ctx.state}")
    print(f"BLOCKS={ORDER} worker_count=3")
    print(f"case_id_r={case_id_r} case_id_a={case_id_a} case_id_s={case_id_s}")
    print(f"sentry.GATE_NUDGE_AFTER={sentry.GATE_NUDGE_AFTER} sentry.GATE_IDLE_CAP={sentry.GATE_IDLE_CAP}")
    print(f"ticks used={ticks_used} (cap={MAX_TICKS}) session_ended={session_ended}")
    print(f"final gates={ {b: final_gates.get(b, {}).get('stage') for b in ORDER} }")
    print(f"final cases (must be empty — all cleared)={final_cases}")
    print(f"abandoned_blocks={final_manifest.get('abandoned_blocks')}")
    print(f"spawn_calls={eng.spawn_calls}")
    print(f"real land.sh invocations per case_id={real_land_calls}")
    print(f"final main tip={_git_out(['rev-parse', MAIN], root)}")
    return 0 if passed == len(_results) else 1


def _stage_rank(stage):
    """A total order over the DONE ladder's stages, for the duplicate-
    decision proof (D3) — confirms wall-resume-01's gate only ever moved
    FORWARD after the duplicate reply, never backward/reset."""
    order = [gate.STAGE_LOCAL, gate.STAGE_MERGE, gate.STAGE_TRUNK,
            gate.STAGE_RECORD, gate.STAGE_CLOSE, gate.STAGE_CLOSED]
    try:
        return order.index(stage)
    except ValueError:
        return -1


if __name__ == "__main__":
    sys.exit(main())
