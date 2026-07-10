"""core.liveness_rig — real-git, no-LLM rig proving `core.liveness` (wave 11:
the engine's worker-SILENCE side-system — "a worker silent too long is
pinged, then declared stalled and recovered", rebuild-spec.md H1/H2) does
EXACTLY what its own module docstring promises, on the REAL surface: a real
`git init` repo copied from the same scaffold every prior `core/*_rig.py`
uses, `meta/scripts/land.sh` run for real via `subprocess`, a REAL
`engine.ctx.Ctx` pointing at a real `manifest.yaml` AND (new this brick) a
real `knobs.yaml` this rig writes itself (`silence_ping_min`/
`silence_escalate_min` — the two knobs `core.liveness._silence_knobs` reads),
driven entirely via repeated `core.tick.tick(eng)` calls (the WAKE daemon,
never a direct `core.liveness.sweep`/`core.router.route` call of this rig's
own — so this is also the wiring proof: `core/tick.py` really does run
`liveness.sweep` after `router.route`, before persist).

TWO real, pipeline-dispatched blocks, seeded together (`worker_count=2`, a
real 2-row `pipeline.md`, NO pre-seeded gate or worker — SWITCHBOARD's own
SPAWN mints both, wave 5):

  silent-01 (branch `feat/silent-01`) — the cited example: a worker that
    NEVER reports anything at all. The rig plays the worker up through
    SWITCHBOARD's own identity-only SPAWN order, then goes completely dark
    — no `worker.online`, ever — until the operator's own `resume` decision
    (sent by THIS rig, once the stall it expects has genuinely fired)
    re-dispatches it: from there it plays a perfectly ordinary engineer
    (branch, `worker.online`, local-pass, real `land.sh` x2, a real
    declared-test re-run, real branch teardown) all the way to a genuine
    clean close.

  live-01 (branch `feat/live-01`) — reacted to FULLY, every tick, from its
    own SPAWN through a real close — PLUS a `worker.progress` heartbeat sent
    EVERY single tick of the whole run (this rig's own stand-in for
    "keeps reporting/progressing"), sharing the EXACT SAME liveness clock as
    silent-01's entire silent-then-stalled run.

Walked wake-by-wake against `core.liveness`'s own two knobs (read straight
off the `knobs.yaml` this rig writes — `PING_MIN`/`ESCALATE_MIN` below are
NOT hardcoded into any assertion; every boundary check derives its expected
tick from the FIRST tick `core.liveness.sweep` actually anchored a fresh
`last_seen` for silent-01, the same "first sighting" episode-start
`core/liveness.py::sweep`'s own docstring describes), the whole per-tick
history is captured and then asserted post-hoc:

  - silent-01 is PINGED (a real `eng._to_worker` order, distinct
    `heartbeat.ping` kind) on the FIRST tick silence reads `>=
    silence_ping_min` — never before, never twice.
  - silent-01 is declared STALLED — `worker:stalled`, ENGINE-produced (never
    an inbound `classify`/router tag; asserted both by a source-scan of
    `core/router.py` AND by injecting a well-formed-looking
    `{"tag": "worker.stalled", ...}` line straight into the worker inbox and
    proving it is a structural no-op, drained and silently ignored, never
    routed to anything) — on the FIRST tick silence reads `>=
    silence_escalate_min`, never before: a parked case opens (source
    `worker.stalled`), the block's slot is genuinely freed (no gate ever
    existed for it — `core.liveness.sweep`'s own gateless-release arm pops
    the stale worker record directly, `eng._release_worker` observed too),
    and the block itself is never silently dropped (still `to-do` on trunk,
    still in the pipeline, just excluded from dispatch while the case stays
    open).
  - The operator's `resume` (sent by this rig once it observes the stall)
    re-dispatches silent-01 under the SAME deterministic agent-id
    (`core/switchboard.py`'s own contract), and it reaches a genuine clean
    close exactly like any other block — proving "recover, never a silent
    kill" end to end.
  - live-01, despite sharing the EXACT SAME clock the whole time (proving
    `last_seen` anchoring is genuinely per-worker, never a global run
    clock), is NEVER pinged and NEVER stalled — `manifest["cases"]` gains
    not one entry for it, `eng.orders` carries not one `heartbeat.ping` for
    its agent-id — and reaches its own genuine clean close.
  - Once BOTH blocks are ✅ on trunk and nothing is in-flight, `core/
    session.py::check` (wired into `core/tick.py` unconditionally, wave 6)
    fires a clean SESSION-END — the stalled->parked->resumed block's own
    proof that recovery reaches the SAME terminal every ordinary block does.

Phase SOURCE (no git involved) closes the loop: `core/router.py`'s dispatch
table carries no arm for an inbound `worker.stalled` tag (grep-equivalent
scan); neither `core/liveness.py` nor `core/router.py` shells out to a raw
`git`/`subprocess` call of its own — all git observation stays inside
`core/gitobs.py`, all persistence inside `core/state.py`, exactly like every
other module in this stack.

ALL 10 prior rigs (`core/{landing,gate,gate_full,tick,dispatch,multiblock,
sentry,casestate,architect,reviewers}_rig.py`) ship no `knobs.yaml` at
`ctx.knobs_file` naming EITHER silence knob at all (`core.reviewers_rig.py`'s
own `knobs.yaml` sets `cadence:` only) — `core.liveness.sweep` reads that as
"nothing configured" and is a genuine no-op for every one of them (see
`core/liveness.py`'s own docstring): this brick is proven, by construction,
to never re-point a single assertion in any of the 10.

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
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # grants.py / trunk.py / ctx.py live here
sys.path.insert(0, HERE)                                 # core/{gate,liveness,state,snapshot,tick}.py

import grants               # noqa: E402 — respected contract, real, unmodified
import trunk                 # noqa: E402 — respected contract, real, unmodified
from ctx import Ctx          # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import gate                  # noqa: E402 — core/gate.py, the DONE ladder core.tick drives
import casestate              # noqa: E402 — core/casestate.py, the recovery primitive liveness reuses
import liveness                # noqa: E402 — core/liveness.py, the module under test
import state                 # noqa: E402 — core/state.py
import tick                  # noqa: E402 — core/tick.py, wired to call liveness.sweep after route

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"

BLOCK_SILENT, BRANCH_SILENT, WID_SILENT = "silent-01", "feat/silent-01", "engineer-silent-01"
BLOCK_LIVE, BRANCH_LIVE, WID_LIVE = "live-01", "feat/live-01", "engineer-live-01"
BLOCK_FILE_SILENT = f"{BLOCKS_REL}/{BLOCK_SILENT}.md"
BLOCK_FILE_LIVE = f"{BLOCKS_REL}/{BLOCK_LIVE}.md"

PING_MIN = 3
ESCALATE_MIN = 5
MAX_TICKS = 200

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


def is_ancestor(root, sha, ref=MAIN):
    r = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", sha, ref])
    return r.returncode == 0


def build_root():
    d = tempfile.mkdtemp(prefix="tron-core-livenessrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-liveness-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: Liveness rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {silent} | silence -> ping -> stall -> parked -> resume | 📋 To do | Block `blocks/{silent}.md` |
| {live} | keeps reporting -> never pinged/stalled | 📋 To do | Block `blocks/{live}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: liveness_rig fixture

**Phase:** 1 — Liveness rig
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.liveness_rig`.
"""


def seed_pipeline(root):
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(silent=BLOCK_SILENT, live=BLOCK_LIVE))
    for block, rel in ((BLOCK_SILENT, BLOCK_FILE_SILENT), (BLOCK_LIVE, BLOCK_FILE_LIVE)):
        bpath = os.path.join(root, rel)
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        with open(bpath, "w") as f:
            f.write(BLOCK_DOC_TEMPLATE.format(block=block))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + blocks {BLOCK_SILENT}/{BLOCK_LIVE} "
                          f"(both to-do, no deps, no gates)"], root)
    _git(["checkout", "--detach", MAIN], root)


def write_knobs(tron_ctx):
    """The ONE new file this brick's rig writes that no prior `core/*_rig.py`
    ever needed (`core/reviewers_rig.py`'s own `knobs.yaml` sets `cadence:`
    only, never either silence knob): `core.liveness._silence_knobs`'s own
    read target, via `eng.ctx.load_knobs()` — real file IO, never faked."""
    os.makedirs(os.path.dirname(tron_ctx.knobs_file), exist_ok=True)
    with open(tron_ctx.knobs_file, "w") as f:
        yaml.safe_dump({"silence_ping_min": PING_MIN, "silence_escalate_min": ESCALATE_MIN},
                       f, sort_keys=False, default_flow_style=False)


def make_code_commit(root, branch, code_file_rel, marker):
    """Forks/resets `branch` at the CURRENT `main` tip (`checkout -B`) and
    makes a real code commit on a file UNIQUE to this block (never the SAME
    path two concurrently-live blocks in this rig both touch) — so the
    ONLY reason a later `land.sh` attempt can ever read non-fast-forward is
    a genuinely STALE base (main moved past this branch's own fork point
    while it sat forked — exactly the concurrent-blocks race `try_land`
    below exists to recover from), never a textual rebase conflict."""
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(f"\n// {marker} — core.liveness_rig real code change\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"feat({branch}): {marker}"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def rebase_onto_main(root, branch):
    """A real worker's own recovery from `land.sh`'s "not a fast-forward"
    refusal (`meta/scripts/land.sh`'s own advice: "rebase your branch onto
    trunk and retry") — replays `branch`'s own commits onto the CURRENT
    `main` tip. Each block in this rig touches its OWN file (see
    `make_code_commit` above), so this is always a clean, conflict-free
    replay — never a textual merge conflict, purely a stale-base recovery
    for a block that sat forked while a CONCURRENT block's own landing
    advanced `main` out from under it."""
    _git(["checkout", branch], root)
    _git(["rebase", MAIN], root)
    _git(["checkout", "--detach", MAIN], root)


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
    `core/gate.py` + `core/switchboard.py` + `core/sentry.py` + `core/
    casestate.py` + `core/liveness.py` need. Deliberately carries NO
    `_now()` — this rig exercises `core.liveness`'s FALLBACK clock (its own
    manifest-persisted tick counter, incremented once per `sweep()` call —
    the SAME "self-controlled counter" convention `core/sentry_rig.py`
    already established for its own, separate `core.sentry` counter)."""
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
        self.dry = False                 # HARD RULE: real trunk observation throughout
        self.ctx = tron_ctx              # REAL engine.ctx.Ctx
        self.events = _Events()
        self.log_lines = []
        self.orders = []
        self.workers = {}                # wid -> {"block":..., "status": ...}  (rig-side bookkeeping)
        self.spawn_calls = []
        self.pages = []                  # eng._page_operator calls (casestate.open_case)

    def log(self, channel, msg):
        self.log_lines.append((channel, msg))

    def _truth_ref(self):
        return MAIN

    def _to_worker(self, wid, msg, kind):
        self.orders.append((wid, msg, kind))

    def _grant_ttl(self):
        return 60

    def _release_worker(self, wid, reason="released"):
        self.workers[wid] = {**self.workers.get(wid, {}), "status": "released", "reason": reason}

    def _spawn_worker(self, agent_id, block):
        self.spawn_calls.append((agent_id, block))
        self.workers[agent_id] = {"block": block, "status": "spawned"}

    def _page_operator(self, case_id, block, detail, worker_id=None):
        self.pages.append((case_id, block, detail, worker_id))


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
                                 "(rig-supplied local report, delivered via a structured "
                                 "worker.done inbox line)"}


def heartbeat_orders(eng, wid):
    return [o for o in eng.orders if o[0] == wid and o[2] == "heartbeat.ping"]


def main():
    root = build_root()
    seed_pipeline(root)
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir
    write_knobs(tron_ctx)

    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=2)

    ok("pre0: rig starts with NO manifest.yaml on disk at all (a brand-new "
       "instance, never yet ticked)",
       not os.path.exists(tron_ctx.state), f"state={tron_ctx.state}")
    ok("pre1: knobs.yaml carries ONLY the two silence knobs this brick "
       "reads — real file IO, never faked/monkeypatched",
       tron_ctx.load_knobs() == {"silence_ping_min": PING_MIN,
                                 "silence_escalate_min": ESCALATE_MIN},
       f"knobs={tron_ctx.load_knobs()}")

    # ── per-block worker-stand-in state (mirrors core/dispatch_rig.py's react()) ──
    st = {
        BLOCK_SILENT: {"active": False, "branch_created": False, "local_reported": False,
                       "record_committed": False, "torn_down": False,
                       "landed_cases": set(), "real_land_calls": {},
                       "code_tip": None, "record_tip": None},
        BLOCK_LIVE: {"active": True, "branch_created": False, "local_reported": False,
                    "record_committed": False, "torn_down": False,
                    "landed_cases": set(), "real_land_calls": {},
                    "code_tip": None, "record_tip": None},
    }
    branches = {BLOCK_SILENT: BRANCH_SILENT, BLOCK_LIVE: BRANCH_LIVE}
    agent_ids = {BLOCK_SILENT: WID_SILENT, BLOCK_LIVE: WID_LIVE}
    block_files = {BLOCK_SILENT: BLOCK_FILE_SILENT, BLOCK_LIVE: BLOCK_FILE_LIVE}
    # Each block touches its OWN code file — see make_code_commit's own
    # docstring for why (a clean, conflict-free rebase-retry when TWO
    # concurrently-live blocks race to land onto the SAME main).
    code_files = {BLOCK_SILENT: "src/lib/silent01.ts", BLOCK_LIVE: "src/lib/live01.ts"}

    def heartbeat(agent_id):
        append_jsonl(tron_ctx.worker_inbox, {"tag": "worker.progress", "agent_id": agent_id})

    def try_land(block, s, branch, case_id, role):
        """Run the REAL `land.sh`; on a genuine "not a fast-forward" refusal
        (a CONCURRENT block's own landing advanced `main` out from under
        this branch's stale fork point — this rig deliberately drives TWO
        blocks in flight at once, unlike every prior single/serialized-
        block rig) rebase onto the fresh `main` and let the NEXT react()
        call retry the SAME case-id — exactly the recovery `land.sh`'s own
        refusal message names. A genuinely UNEXPECTED failure (anything
        other than that one, well-understood race) is fail-loud, same as
        every other rig in this stack.

        On success, (re-)captures the branch's OWN current tip as the
        landed sha for `role` ("merge"/"record") — a REBASE (above) mints a
        brand-new sha for the SAME content, so the tip this rig must assert
        `is_ancestor(..., MAIN)` against is whatever the branch reads AT
        THE MOMENT land.sh actually observed it landed, never the
        ORIGINAL pre-rebase commit sha `make_code_commit`/
        `make_record_commit` happened to return."""
        landed_tip = _git_out(["rev-parse", branch], root)
        rc, out, err = run_land(root, grants_dir, case_id)
        s["real_land_calls"][case_id] = s["real_land_calls"].get(case_id, 0) + 1
        if rc == 0:
            s["landed_cases"].add(case_id)
            s[f"{role}_tip"] = landed_tip
            return
        if "not a fast-forward" in err:
            rebase_onto_main(root, branch)
            return
        raise RuntimeError(f"land.sh unexpected failure for {block} case={case_id} "
                          f"rc={rc}\nstdout:{out}\nstderr:{err}")

    def react_active(manifest, block):
        """The ordinary engineer reaction (spawn->online->local->merge->
        trunk->record->close), PLUS a `worker.progress` heartbeat sent
        EVERY call — this rig's own "keeps reporting/progressing" stand-in,
        proving last_seen anchoring is genuinely per-worker (H2's own
        margin: never even close to `silence_ping_min` between sightings)."""
        s = st[block]
        agent_id = agent_ids[block]
        branch = branches[block]
        block_file = block_files[block]
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}

        w = workers.get(agent_id)
        if w and w.get("status") == "spawning" and not s["branch_created"]:
            make_code_commit(root, branch, code_files[block], f"{block}-real-progress")
            s["branch_created"] = True
            append_jsonl(tron_ctx.worker_inbox,
                        {"tag": "worker.online", "agent_id": agent_id, "slots": {"branch": branch}})

        if w is not None:
            heartbeat(agent_id)   # "still alive, still working" — every call

        g = gates.get(block)
        if not g:
            return
        stage = g.get("stage")

        if stage == gate.STAGE_LOCAL and not s["local_reported"]:
            append_jsonl(tron_ctx.worker_inbox,
                        {"tag": "worker.done", "block": block, "slots": LOCAL_PASS_REPORT})
            s["local_reported"] = True
        elif stage == gate.STAGE_MERGE and g.get("merge_case_id"):
            case_id = g["merge_case_id"]
            if case_id not in s["landed_cases"]:
                try_land(block, s, branch, case_id, "code")
        elif stage == gate.STAGE_RECORD:
            if g.get("record_ordered") and not s["record_committed"] and not g.get("record_case_id"):
                make_record_commit(root, branch, block_file)
                s["record_committed"] = True
            if g.get("record_case_id") and g["record_case_id"] not in s["landed_cases"]:
                case_id = g["record_case_id"]
                try_land(block, s, branch, case_id, "record")
        elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not s["torn_down"]:
            _git(["branch", "-D", branch], root)
            s["torn_down"] = True

    # ── the operator's own bookkeeping — set once the rig OBSERVES the
    #     stall it expects, never before (never a scripted/pre-timed resume) ──
    resume_sent = {"at_tick": None, "case_id": None}
    stall_seen = {"at_tick": None, "case_id": None, "trunk_sha": None}
    ping_seen = {"at_tick": None}
    first_sighting_tick = {"at": None}

    def maybe_resume(manifest, i):
        if resume_sent["at_tick"] is not None:
            return
        cases = manifest.get("cases") or {}
        case = next((c for c in cases.values()
                    if c.get("block") == BLOCK_SILENT and c.get("source") == "worker.stalled"
                    and c.get("decision") is None), None)
        if case is None:
            return
        stall_seen["at_tick"] = stall_seen["at_tick"] or i
        stall_seen["case_id"] = case["case_id"]
        stall_seen["trunk_sha"] = _git_out(["rev-parse", MAIN], root)
        append_jsonl(tron_ctx.worker_inbox,
                    {"tag": "operator.decision",
                     "slots": {"case_id": case["case_id"], "verb": "resume"}})
        resume_sent["at_tick"] = i
        resume_sent["case_id"] = case["case_id"]
        st[BLOCK_SILENT]["active"] = True   # from the NEXT tick's react(), play it live

    tick_history = []
    i = 0
    for i in range(1, MAX_TICKS + 1):
        res = tick.tick(eng)
        manifest = state.load(tron_ctx)
        workers_snap = {w: dict(v) for w, v in (manifest.get("workers") or {}).items()}
        gates_snap = {b: dict(g) for b, g in (manifest.get("gates") or {}).items()}
        cases_snap = {c: dict(v) for c, v in (manifest.get("cases") or {}).items()}
        tick_history.append({"i": i, "pinged": list(res["pinged"]), "stalled": list(res["stalled"]),
                             "workers": workers_snap, "gates": gates_snap, "cases": cases_snap,
                             "session_end": res.get("session_end")})

        if WID_SILENT in workers_snap and first_sighting_tick["at"] is None \
           and workers_snap[WID_SILENT].get("last_seen") is not None:
            first_sighting_tick["at"] = i
        if WID_SILENT in res["pinged"] and ping_seen["at_tick"] is None:
            ping_seen["at_tick"] = i

        maybe_resume(manifest, i)

        for block in (BLOCK_SILENT, BLOCK_LIVE):
            if st[block]["active"]:
                react_active(manifest, block)

        gs = (manifest.get("gates") or {}).get(BLOCK_SILENT, {})
        gl = (manifest.get("gates") or {}).get(BLOCK_LIVE, {})
        if gs.get("stage") == gate.STAGE_CLOSED and gl.get("stage") == gate.STAGE_CLOSED \
           and res.get("session_end") is not None:
            break

    ticks_used = i
    final_manifest = state.load(tron_ctx)

    ok(f"RUN0: the whole drive converged (both blocks closed, clean "
       f"session-end) inside {MAX_TICKS} ticks (used {ticks_used})",
       (final_manifest.get("gates") or {}).get(BLOCK_SILENT, {}).get("stage") == gate.STAGE_CLOSED
       and (final_manifest.get("gates") or {}).get(BLOCK_LIVE, {}).get("stage") == gate.STAGE_CLOSED
       and bool((final_manifest.get("session") or {}).get("ended_at")),
       f"ticks_used={ticks_used} "
       f"final_silent_stage={(final_manifest.get('gates') or {}).get(BLOCK_SILENT, {}).get('stage')} "
       f"final_live_stage={(final_manifest.get('gates') or {}).get(BLOCK_LIVE, {}).get('stage')} "
       f"session={final_manifest.get('session')}")

    # ══════════════════════════════════════════════════════════════════
    # SILENT-01 — the ping/stall/recover ladder
    # ══════════════════════════════════════════════════════════════════
    ok("PRE0: SWITCHBOARD spawned silent-01 off the real pipeline (no "
       "pre-seeded gate/worker) — the deterministic agent-id exists",
       any(WID_SILENT == aid for aid, _b in eng.spawn_calls), f"spawn_calls={eng.spawn_calls}")
    ok("S0: silent-01 NEVER sent worker.online for its FIRST spawn cycle — "
       "the whole point: a spawned worker that goes completely dark",
       stall_seen["at_tick"] is not None
       and not any(t["gates"].get(BLOCK_SILENT) for t in tick_history[:stall_seen["at_tick"]]),
       f"stall_tick={stall_seen['at_tick']} — no gate ever opened for silent-01 before the stall "
       f"(it never reported worker.online)")

    fs = first_sighting_tick["at"]
    ok("S1 (FIRST-SIGHTING KILLER — must be GREEN): `core.liveness.sweep` "
       "anchored silent-01's `last_seen` on a genuine first-sighting tick, "
       "no ping/stall counted on that same call",
       fs is not None
       and WID_SILENT not in tick_history[fs - 1]["pinged"]
       and not any(WID_SILENT == wid for _b, wid, _c in tick_history[fs - 1]["stalled"]),
       f"first_sighting_tick={fs}")

    expected_ping_tick = fs + PING_MIN if fs is not None else None
    ok("S2 (PING-EXACT-BOUNDARY KILLER — must be GREEN): silent-01 was "
       "PINGED (a real eng._to_worker order, distinct `heartbeat.ping` "
       "kind) on EXACTLY the first tick silence reached "
       "silence_ping_min — never before, never twice",
       ping_seen["at_tick"] is not None and ping_seen["at_tick"] == expected_ping_tick
       and len(heartbeat_orders(eng, WID_SILENT)) == 1,
       f"ping_tick={ping_seen['at_tick']} expected={expected_ping_tick} "
       f"heartbeat_orders={heartbeat_orders(eng, WID_SILENT)}")

    tick_before_ping = tick_history[ping_seen["at_tick"] - 2] if ping_seen["at_tick"] else None
    ok("S2b (NOT-BEFORE KILLER — must be GREEN): the tick strictly BEFORE "
       "the ping had NO heartbeat.ping order yet for silent-01",
       tick_before_ping is not None and WID_SILENT not in tick_before_ping["pinged"],
       f"tick_before_ping={tick_before_ping['i'] if tick_before_ping else None}")

    expected_stall_tick = fs + ESCALATE_MIN if fs is not None else None
    ok("S3 (STALL-EXACT-BOUNDARY KILLER — must be GREEN): silent-01 was "
       "declared STALLED on EXACTLY the first tick silence reached "
       "silence_escalate_min (strictly after the ping) — a parked case "
       "opened (source `worker.stalled`)",
       stall_seen["at_tick"] is not None and stall_seen["at_tick"] == expected_stall_tick
       and expected_ping_tick is not None and expected_stall_tick > expected_ping_tick,
       f"stall_tick={stall_seen['at_tick']} expected={expected_stall_tick} "
       f"ping_tick={ping_seen['at_tick']}")

    tick_before_stall = tick_history[stall_seen["at_tick"] - 2] if stall_seen["at_tick"] else None
    ok("S3b (NOT-BEFORE KILLER — must be GREEN): the tick strictly BEFORE "
       "the stall showed no worker.stalled case yet for silent-01",
       tick_before_stall is not None
       and not any(c.get("block") == BLOCK_SILENT and c.get("source") == "worker.stalled"
                  for c in tick_before_stall["cases"].values()),
       f"tick_before_stall={tick_before_stall['i'] if tick_before_stall else None}")

    stall_tick_record = next(t for t in tick_history if t["i"] == stall_seen["at_tick"])
    stall_case = stall_tick_record["cases"].get(stall_seen["case_id"])
    ok("S4 (RECOVER-NEVER-A-SILENT-KILL KILLER — must be GREEN): the stall "
       "opened a REAL parked operator case (source worker.stalled, kind "
       "stall, decision=None, the operator paged via eng._page_operator) — "
       "never a bare drop",
       stall_case is not None and stall_case.get("source") == "worker.stalled"
       and stall_case.get("kind") == "stall" and stall_case.get("worker_id") == WID_SILENT
       and any(p[0] == stall_seen["case_id"] for p in eng.pages),
       f"stall_case={stall_case} pages={eng.pages}")

    ok("S5 (SLOT-FREED KILLER — must be GREEN): silent-01's worker record "
       "was popped out of manifest['workers'] the SAME tick it stalled — "
       "no gate ever existed to key a terminal stage off of, so freeing "
       "the slot is core.liveness's own job (mirrors core/sentry.py's "
       "reviewer gateless-release precedent) — AND the rig-side "
       "eng._release_worker bookkeeping observed the SAME release",
       WID_SILENT not in stall_tick_record["workers"]
       and eng.workers.get(WID_SILENT, {}).get("status") == "released",
       f"workers_at_stall={list(stall_tick_record['workers'])} "
       f"eng_worker={eng.workers.get(WID_SILENT)}")

    doc_at_stall = (_git_out(["show", f"{stall_seen['trunk_sha']}:{BLOCK_FILE_SILENT}"], root)
                   if stall_seen["trunk_sha"] else None)
    ok("S6 (NEVER-SILENTLY-DROPPED KILLER — must be GREEN): silent-01's "
       "block doc, read straight off the REAL trunk sha AT the moment of "
       "the stall, still shows 📋 (untouched — TRON never writes project "
       "git outside land.sh; abandon is a DIFFERENT, operator-only verb "
       "casestate.settle offers, never fired here) — the block was parked, "
       "never dropped",
       doc_at_stall is not None and "**Status:** 📋 To do" in doc_at_stall,
       f"trunk_sha_at_stall={stall_seen['trunk_sha']} "
       f"doc_head={doc_at_stall.splitlines()[:4] if doc_at_stall else None}")

    ok("S7 (RESUME-REDISPATCH KILLER — must be GREEN): the operator's "
       "`resume` (sent by this rig ONLY after it observed the real stall) "
       "re-dispatched silent-01 under the SAME deterministic agent-id — "
       "never a second/different identity",
       resume_sent["at_tick"] is not None
       and sum(1 for aid, b in eng.spawn_calls if aid == WID_SILENT and b == BLOCK_SILENT) == 2,
       f"resume_tick={resume_sent['at_tick']} "
       f"silent_spawn_calls={[c for c in eng.spawn_calls if c[0] == WID_SILENT]}")

    ok("S8 (CLEAN-CLOSE-AFTER-RECOVER KILLER — must be GREEN): silent-01's "
       "REDISPATCHED worker's OWN real code commit genuinely landed on "
       "trunk, the ✅ record commit genuinely landed via a second grant, "
       "and the gate reached a genuine CLOSED (replica clean, slot really "
       "released a SECOND time)",
       st[BLOCK_SILENT]["code_tip"] is not None
       and is_ancestor(root, st[BLOCK_SILENT]["code_tip"], MAIN)
       and st[BLOCK_SILENT]["record_tip"] is not None
       and is_ancestor(root, st[BLOCK_SILENT]["record_tip"], MAIN)
       and (final_manifest.get("gates") or {}).get(BLOCK_SILENT, {}).get("stage") == gate.STAGE_CLOSED,
       f"code_tip={st[BLOCK_SILENT]['code_tip']} record_tip={st[BLOCK_SILENT]['record_tip']} "
       f"final_stage={(final_manifest.get('gates') or {}).get(BLOCK_SILENT, {}).get('stage')}")

    doc_final_silent = _git_out(["show", f"{MAIN}:{BLOCK_FILE_SILENT}"], root)
    ok("S9: the block doc for silent-01, AS READ FROM main, shows ✅ — the "
       "recovered worker genuinely finished, not merely closed structurally",
       "**Status:** ✅ Done" in doc_final_silent, f"doc head={doc_final_silent.splitlines()[:4]}")

    ok("S10 (STALE-CASE-CLEARED KILLER — must be GREEN): the parked case "
       "was CLEARED the same tick it was settled — no longer in "
       "manifest['cases'] at all by the end of the run",
       stall_seen["case_id"] not in (final_manifest.get("cases") or {}),
       f"final_cases={final_manifest.get('cases')}")

    # ══════════════════════════════════════════════════════════════════
    # LIVE-01 — never pinged, never stalled, despite the SAME clock
    # ══════════════════════════════════════════════════════════════════
    live_final = (final_manifest.get("gates") or {}).get(BLOCK_LIVE, {})
    ok("H1 (TERMINAL — must be GREEN): live-01 reached a genuine clean "
       "close, driven entirely by core.tick.tick, liveness wired in and "
       "sweeping every single tick alongside silent-01's whole silent run",
       live_final.get("stage") == gate.STAGE_CLOSED
       and eng.workers.get(WID_LIVE, {}).get("status") == "released",
       f"live_final_stage={live_final.get('stage')} eng_worker={eng.workers.get(WID_LIVE)}")

    ok("H2 (THE PING/STALL KILLER — must be GREEN): across live-01's "
       "ENTIRE drive — sharing the EXACT SAME liveness clock as "
       "silent-01's own run through ping AND stall — it was NEVER pinged "
       "(zero heartbeat.ping orders for its agent-id) and NEVER stalled "
       "(manifest['cases'] gained not one entry naming live-01), proving "
       "`last_seen` anchoring is genuinely PER-WORKER, never a global "
       "run clock",
       heartbeat_orders(eng, WID_LIVE) == []
       and not any(c.get("block") == BLOCK_LIVE for c in (final_manifest.get("cases") or {}).values()),
       f"live_heartbeat_orders={heartbeat_orders(eng, WID_LIVE)} "
       f"final_cases={final_manifest.get('cases')}")

    doc_final_live = _git_out(["show", f"{MAIN}:{BLOCK_FILE_LIVE}"], root)
    ok("H3: the block doc for live-01, AS READ FROM main, shows ✅",
       "**Status:** ✅ Done" in doc_final_live, f"doc head={doc_final_live.splitlines()[:4]}")

    ok("H4 (CLEAN SESSION-END KILLER — must be GREEN): with BOTH blocks "
       "✅ on trunk and nothing in-flight, core/session.py fired a clean "
       "SESSION-END — the recovered (stalled->parked->resumed) block "
       "reaches the SAME terminal an ordinary block does",
       bool((final_manifest.get("session") or {}).get("ended_at")),
       f"session={final_manifest.get('session')}")

    # ══════════════════════════════════════════════════════════════════
    # ENGINE-PRODUCED — worker.stalled is never an inbound classify/router tag
    # ══════════════════════════════════════════════════════════════════
    cases_before_injection = len(final_manifest.get("cases") or {})
    append_jsonl(tron_ctx.worker_inbox,
                {"tag": "worker.stalled", "agent_id": "not-a-real-worker",
                 "block": "not-a-real-block", "slots": {"detail": "adversarial inbound tag"}})
    tick.tick(eng)   # drains it — must be a structural no-op
    manifest_after_injection = state.load(tron_ctx)
    ok("T1 (INBOUND-TAG KILLER — must be GREEN): injecting a well-formed-"
       "looking `{\"tag\": \"worker.stalled\", ...}` line straight into the "
       "worker inbox is a structural no-op — router.route has no dispatch "
       "arm for it at all (falls through exactly like any other "
       "unrecognized tag), so it opens NO new case and touches NOTHING",
       len(manifest_after_injection.get("cases") or {}) == cases_before_injection
       and "not-a-real-block" not in (manifest_after_injection.get("gates") or {}),
       f"cases_before={cases_before_injection} "
       f"cases_after={len(manifest_after_injection.get('cases') or {})}")

    router_src = open(os.path.join(HERE, "router.py")).read()
    liveness_src = open(os.path.join(HERE, "liveness.py")).read()
    ok("T2 (SOURCE-SCAN KILLER — must be GREEN): `core/router.py`'s "
       "dispatch table carries no `tag == \"worker.stalled\"` (or "
       "equivalent) branch anywhere in its source — worker:stalled is "
       "ENGINE-produced (core.liveness.sweep calling core.casestate."
       "open_case directly), never something an inbound report can "
       "trigger by naming the tag",
       'tag == "worker.stalled"' not in router_src
       and '"worker.stalled"' not in router_src,
       "grep-equivalent source scan of core/router.py")
    ok("T3: `core/liveness.py` is the ONE place `casestate.open_case` gets "
       "called with source `worker.stalled` — the engine's own declaration, "
       "never routed input",
       'casestate.open_case(eng, manifest, block, "worker.stalled"' in liveness_src,
       "grep-equivalent source scan of core/liveness.py")

    # ══════════════════════════════════════════════════════════════════
    # PHASE SOURCE — no raw git/subprocess in either control module
    # ══════════════════════════════════════════════════════════════════
    ok("SRC1: `core/liveness.py` shells out to no raw git/subprocess call "
       "of its own — all git observation stays inside core/gitobs.py, all "
       "persistence inside core/state.py",
       "import subprocess" not in liveness_src and "subprocess." not in liveness_src
       and "\nimport git\n" not in liveness_src,
       "grep-equivalent source scan of core/liveness.py")
    ok("SRC2: `core/router.py` (edited this brick to wire `liveness.touch`) "
       "STILL shells out to no raw git/subprocess call of its own",
       "import subprocess" not in router_src and "subprocess." not in router_src
       and "\nimport git\n" not in router_src,
       "grep-equivalent source scan of core/router.py")
    tick_src = open(os.path.join(HERE, "tick.py")).read()
    ok("SRC3: `core/tick.py` (edited this brick to wire `liveness.sweep`) "
       "STILL shells out to no raw git/subprocess call of its own",
       "import subprocess" not in tick_src and "subprocess." not in tick_src
       and "\nimport git\n" not in tick_src,
       "grep-equivalent source scan of core/tick.py")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.liveness_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"tron instance dir (real engine.ctx.Ctx)={inst}")
    print(f"manifest={tron_ctx.state}")
    print(f"knobs: silence_ping_min={PING_MIN} silence_escalate_min={ESCALATE_MIN}")
    print(f"BLOCK_SILENT={BLOCK_SILENT} first_sighting_tick={fs} "
          f"ping_tick={ping_seen['at_tick']} (expected {expected_ping_tick}) "
          f"stall_tick={stall_seen['at_tick']} (expected {expected_stall_tick}) "
          f"resume_tick={resume_sent['at_tick']}")
    print(f"BLOCK_LIVE={BLOCK_LIVE} heartbeat_orders_count="
          f"{len(heartbeat_orders(eng, WID_LIVE))} (must be 0)")
    print(f"ticks used={ticks_used} (cap={MAX_TICKS})")
    print(f"final session={final_manifest.get('session')}")
    print(f"final cases={final_manifest.get('cases')}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
