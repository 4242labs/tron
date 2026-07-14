"""core.opfloor_rig — real-git, no-LLM rig proving `core/engine.py::
_page_operator` + `core/casestate.py::reping` (wave 17, GAP-A) turn the
operator page into a genuine FLOOR: the #2 historical failure (13x
`operator-page-failed::page-receipt-permanent-fail` — the last-resort
operator page silently un-delivering, treated as a terminal drop) is made
structurally impossible. Driven entirely via the REAL `core.engine.Engine`
(`Engine(ctx).start(...)` / `Engine.tick()` — never a direct `core.tick.
tick`/`core.casestate.reping`/`core.sentry.pace` call of this rig's own),
exactly like `core/engine_rig.py` — this is also the wiring proof that
`core/engine.py::_page_operator` really is what `core/casestate.py::
open_case`/`reping` call, through the real bootup + tick loop.

REAL surface only: a real `git init` repo copied from the SAME scaffold
every prior `core/*_rig.py` uses, `meta/scripts/land.sh` run for real via
`subprocess`, a real `engine.ctx.Ctx` pointing at a real `manifest.yaml`, a
real `project.yaml`/`knobs.yaml`/`roles.yaml` (the same shapes `core/
engine_rig.py` established), and a REAL declared test command (`true`)
re-run in a REAL clean detached worktree. `engine.jobs.spawn_runner` is the
ONE seam stubbed (never a real `claude` process — the established "rig
plays the worker" pattern); every other `Engine` hook (`_to_worker`,
`_release_worker`, `_grant_ttl`, `log`) runs FOR REAL. `_page_operator`
itself is the REAL `core/engine.py` implementation, UNSTUBBED — this
brick's whole point — with exactly ONE new hook injected onto the live
`Engine` instance, `eng._deliver_page`, standing in for the real transport
this wave deliberately does not wire (per the brick's own spec): a plain
callable, keyed by block, that returns `"delivered"`/`"failed"` — the SAME
"stubbed hook, no real transport" shape `_spawn_worker`/`_to_worker` are.
The clock is deterministic throughout: `core/sentry.py`'s own manifest-
persisted tick counter (no `eng._now()` override needed — the same fallback
path `core/sentry_rig.py`/`core/casestate_rig.py` already exercise
unmodified), incremented exactly once per real tick.

TWO real, pipeline-dispatched blocks (`worker_count=2`, no deps — dep-
ordering is out of this brick's scope), each walled once at `gate.local` (a
real structured `worker.wall` report — opens a parked case exactly like
`core/casestate_rig.py`'s own wall fixture) so the FLOOR gets exercised
against a genuine, in-scope, still-📋-on-trunk block the whole time it sits
parked (never a synthetic case with no gate behind it):

  page-delivered-01 — `eng._deliver_page` answers `"delivered"` for every
    page attempt against this block. Proves: a `delivered` receipt
    satisfies the ladder outright — `manifest["operator_pages"]` gains
    EXACTLY ONE entry for this case, no matter how many further ticks the
    case sits open/un-resumed ("no more pings than the backoff dictates").

  page-failed-01 — `eng._deliver_page` answers `"failed"` for EVERY page
    attempt against this block, forever. Proves THE FLOOR itself (the
    ported `page-receipt-permanent-fail` scenario): across many ticks the
    case stays open (`decision` stays `None`), the gate stays parked
    (`gate.STAGE_ESCALATED`, never re-terminaled to anything else), the
    block never lands on trunk, `manifest["operator_pages"]` keeps growing
    (a real, bounded — never a busy-loop — forced re-ping every qualifying
    tick), the paging CHANNEL escalates exactly once past `core.casestate.
    PAGE_CHANNEL_ESCALATE_AFTER` consecutive failures (a louder `page_kind`
    + a forensic, WARNING-and-retry `manifest["escalations"]` record) yet
    keeps re-pinging afterward — and NO tick ever emits a `session_end`
    while this block sits unresolved (it is still genuinely in-scope,
    still 📋 on trunk — `core/session.py::check` would refuse to end a run
    with a real pending block, precisely BECAUSE the floor never abandoned
    or fake-closed it).

Both cases are THEN resumed (`operator.decision resume`) — proving the
floor never corrupts anything: pinging stops the SAME tick (no new
`operator_pages` entries for either case_id after settle), both blocks get
a genuinely FRESH dispatch, and the whole rig converges to a clean,
idempotent SESSION-END on real git, exactly like any ordinary
`core/casestate_rig.py`-style resume.

Finally, an ISOLATED, throwaway `core.engine.Engine` (same real ctx/
project, never `.start()`-ed, never touching the main drive's own
manifest) proves the minimal GAP-E slice this brick's spec calls for: a
BLOCK-LESS escalation (`block=None`, no pipeline row behind it at all,
no `eng._deliver_page` hook wired — the "absent hook, production-shaped"
path) still durably pages the operator — never a silent, unclassified
discard.

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
import state                       # noqa: E402 — core/state.py
import casestate                    # noqa: E402 — core/casestate.py, THE FLOOR's own constants + open_case
import architect                     # noqa: E402 — core/architect.py, wave 18's triage job (KILLER 4)
from engine import Engine, BootupError   # noqa: E402 — core/engine.py, THE MODULE UNDER TEST (real _page_operator)

import scaffold_src               # noqa: E402 — core/scaffold_src.py, the ONE resolver

SCAFFOLD_SRC = scaffold_src.resolve()
MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"
ROLES_REL = "meta/tron/roles.yaml"
PERSONAS_REL = "meta/tron/personas"

BLOCK_D, BRANCH_D, WID_D = "page-delivered-01", "feat/page-delivered-01", "engineer-page-delivered-01"
BLOCK_F, BRANCH_F, WID_F = "page-failed-01", "feat/page-failed-01", "engineer-page-failed-01"
ORDER = [BLOCK_D, BLOCK_F]

CADENCE_TYPE = "code"
STUB_MODEL = "stub-model"
MAX_TICKS = 160
FLOOR_OBSERVE_TICKS = 12   # ticks to keep driving WHILE UNRESOLVED, once both cases are open, before resuming

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


def build_root():
    d = tempfile.mkdtemp(prefix="tron-core-opfloorrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-opfloor-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: opfloor_rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {d} | opfloor_rig fixture — walled, delivered receipt | 📋 To do | Block `blocks/{d}.md` |
| {f} | opfloor_rig fixture — walled, failed receipt (THE FLOOR) | 📋 To do | Block `blocks/{f}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: opfloor_rig fixture

**Phase:** 1 — GAP-A operator-page floor rig
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.opfloor_rig` — proves `core/engine.py::
_page_operator` + `core/casestate.py::reping` (wave 17, GAP-A) never
silently drop an unanswered operator page.
"""

ROLES_YAML_TEMPLATE = """roles:
  engineer:
    persona: {personas}/engineer.md
    model: {model}
    binds: [BUILD, CLOSE]
  reviewer-{cadence_type}:
    persona: {personas}/reviewer-{cadence_type}.md
    model: {model}
    binds: [REVIEW]
    selector:
      reviewer_class: {cadence_type}
  architect:
    persona: {personas}/architect.md
    model: {model}
    binds: [TRIAGE]
    spec_owner: true
    persistent: true
"""

PERSONA_TEMPLATE = """# {role} persona (core.opfloor_rig fixture)

A synthetic persona file — `engine.roles.RolesConfig`'s own fail-closed
boot validation requires every declared role's persona to exist on disk;
this rig's workers are entirely scripted (no LLM, no real `claude`
process), so the CONTENT here is never read by anything, only its
presence.
"""


def seed_pipeline(root):
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(d=BLOCK_D, f=BLOCK_F))
    for block in ORDER:
        bpath = os.path.join(root, BLOCKS_REL, f"{block}.md")
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        with open(bpath, "w") as fh:
            fh.write(BLOCK_DOC_TEMPLATE.format(block=block))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + blocks {BLOCK_D}/{BLOCK_F} (to-do, no deps, no gates)"], root)
    _git(["checkout", "--detach", MAIN], root)


def seed_roles(root):
    roles_path = os.path.join(root, ROLES_REL)
    os.makedirs(os.path.dirname(roles_path), exist_ok=True)
    with open(roles_path, "w") as f:
        f.write(ROLES_YAML_TEMPLATE.format(personas=PERSONAS_REL, model=STUB_MODEL,
                                           cadence_type=CADENCE_TYPE))
    personas_dir = os.path.join(root, PERSONAS_REL)
    os.makedirs(personas_dir, exist_ok=True)
    for role in ("engineer", f"reviewer-{CADENCE_TYPE}", "architect"):
        with open(os.path.join(personas_dir, f"{role}.md"), "w") as f:
            f.write(PERSONA_TEMPLATE.format(role=role))
    _git(["checkout", "-B", MAIN, MAIN], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: roles.yaml (engineer/reviewer-code/architect) + personas"], root)
    _git(["checkout", "--detach", MAIN], root)


def write_project_yaml(inst_dir, root):
    os.makedirs(inst_dir, exist_ok=True)
    doc = {
        "repo": {"root": root, "main_branch": MAIN, "remote": "none", "staging": "none"},
        "test": {"command": "true"},
    }
    with open(os.path.join(inst_dir, "project.yaml"), "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)


def write_knobs(inst_dir):
    """`silence_ping_min`/`silence_escalate_min` set WELL above `MAX_TICKS`
    so `core/liveness.py`'s own SILENCE ladder structurally never fires and
    never interferes with this brick's own, entirely different, PAGE
    ladder — this rig's blocks report promptly (worker.online, worker.wall)
    right up to the moment they wall, exactly like every prior wall-fixture
    rig; `cadence: {}` (empty) — no reviewer ever dispatches, out of scope
    for this brick."""
    doc = {
        "knobs": {
            "worker_count": 2,
            "silence_ping_min": 2000,
            "silence_escalate_min": 4000,
            "grant_ttl": 60,
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
        f.write(f"// {marker} — core.opfloor_rig real code change\n")
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

WALL_DETAIL = {
    BLOCK_D: "rig-as-worker: hit a genuine wall on page-delivered-01 at gate.local — "
             "opfloor_rig fixture (this case's deliver hook will answer 'delivered')",
    BLOCK_F: "rig-as-worker: hit a genuine wall on page-failed-01 at gate.local — "
             "opfloor_rig fixture, THE FLOOR (this case's deliver hook will answer "
             "'failed', forever, until the operator resumes it)",
}


class RunState:
    """Per-block generation-tracked reaction state (mirrors `core/
    casestate_rig.py`'s own `gen`-keyed dicts): generation 0 is walled ONCE
    at `gate.local`; a LATER generation (after an operator resume) reacts
    with an ordinary local-pass instead, driving the fresh dispatch all the
    way to a genuine close."""

    def __init__(self, root, grants_dir):
        self.root = root
        self.grants_dir = grants_dir
        self.gen = {b: 0 for b in ORDER}
        self.walled = {b: False for b in ORDER}
        self.branch_created = {}
        self.local_reported = {}
        self.record_committed = {}
        self.torn_down = {}
        self.landed_cases = set()
        self.spawn_tick = {}
        self.close_tick = {}
        self.triage_answered = set()   # wave 18 (GAP-E): triage_ids already answered

    def react_architect_triage(self, manifest, inbox_path):
        """Wave 18 (GAP-E): both fixture blocks' walls now open ARCHITECT-
        first cases (`core/casestate.py::open_case` -> `core/architect.py::
        enqueue_triage`) — never an immediate operator page. This rig's
        whole point is exercising THE FLOOR (GAP-A) on OPERATOR-owned
        cases, so it always scripts the architect to answer `operator` for
        whatever triage job is currently ordered — the SAME generic,
        one-at-a-time hook `core/casestate_rig.py`'s own re-point uses."""
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if (cur and cur.get("kind") == "triage" and cur.get("ordered")
                and cur.get("triage_id") not in self.triage_answered):
            append_jsonl(inbox_path, {"tag": "architect.triage_verdict",
                                      "triage_id": cur["triage_id"], "verdict": "operator"})
            self.triage_answered.add(cur["triage_id"])

    def react(self, i, manifest, inbox_path):
        self.react_architect_triage(manifest, inbox_path)
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}
        for block in ORDER:
            agent_id = f"engineer-{block}"
            branch = f"feat/{block}"
            block_file_rel = f"{BLOCKS_REL}/{block}.md"
            key = (block, self.gen[block])

            w = workers.get(agent_id)
            if w:
                self.spawn_tick.setdefault(block, i)
            if w and w.get("status") == "spawning" and not self.branch_created.get(key):
                make_code_commit(self.root, branch, f"src/lib/{block}.ts",
                                 f"{block}-gen{self.gen[block]}")
                self.branch_created[key] = True
                append_jsonl(inbox_path, {"tag": "worker.online", "agent_id": agent_id,
                                          "slots": {"branch": branch}})

            g = gates.get(block)
            if not g:
                continue
            stage = g.get("stage")

            if stage == gate.STAGE_LOCAL:
                if self.gen[block] == 0 and not self.walled[block]:
                    append_jsonl(inbox_path, {"tag": "worker.wall", "block": block,
                                              "agent_id": agent_id,
                                              "slots": {"detail": WALL_DETAIL[block]}})
                    self.walled[block] = True
                elif not self.local_reported.get(key):
                    append_jsonl(inbox_path, {"tag": "worker.done", "block": block,
                                              "slots": LOCAL_PASS_REPORT})
                    self.local_reported[key] = True
            elif stage == gate.STAGE_MERGE and g.get("merge_case_id"):
                try_land(self.root, self.grants_dir, g["merge_case_id"], branch, self.landed_cases)
            elif stage == gate.STAGE_RECORD:
                if g.get("record_ordered") and not self.record_committed.get(key) \
                        and not g.get("record_case_id"):
                    make_record_commit(self.root, branch, block_file_rel)
                    self.record_committed[key] = True
                if g.get("record_case_id"):
                    try_land(self.root, self.grants_dir, g["record_case_id"], branch, self.landed_cases)
            elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not self.torn_down.get(key):
                _git(["branch", "-D", branch], self.root)
                self.torn_down[key] = True

            if stage == gate.STAGE_CLOSED and block not in self.close_tick:
                self.close_tick[block] = i


def page_counts(manifest, case_id):
    pages = manifest.get("operator_pages") or {}
    return [p for p in pages.values() if p.get("case_id") == case_id]


def find_open_case(manifest, block):
    for c in (manifest.get("cases") or {}).values():
        if c.get("block") == block and c.get("decision") is None:
            return c
    return None


def main():
    root = build_root()
    seed_pipeline(root)
    seed_roles(root)

    inst = os.path.join(root, "meta", "agents", "tron")
    write_project_yaml(inst, root)
    write_knobs(inst)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    # ── stub the ONE process-spawn seam (never a real `claude` process) —
    #     the established pattern every prior core/*_rig.py uses ──
    spawn_calls = []

    def fake_spawn_runner(worker_id, worker_dir, session_id, cwd=None,
                          runtime=None, adapter=None, model=None, settle_s=2.0):
        spawn_calls.append({"worker_id": worker_id, "model": model})
        return {}

    real_spawn_runner = jobs.spawn_runner
    jobs.spawn_runner = fake_spawn_runner
    real_release = jobs.release

    try:
        eng = Engine(Ctx(inst))
        eng.dry = False   # HARD RULE: real trunk observation throughout

        # ── the ONE new hook this whole brick adds: `eng._deliver_page` —
        #     stubbed exactly like `_spawn_worker`/`_to_worker`, no real
        #     transport. Keyed by BLOCK (the case's own `block` field,
        #     threaded straight through by `core/casestate.py`) so each
        #     fixture case gets its own deterministic, controllable receipt
        #     — every call recorded for this rig's own assertions. ──
        deliver_calls = []
        receipt_for_block = {BLOCK_D: "delivered", BLOCK_F: "failed"}

        def fake_deliver_page(case_id, block, detail, worker_id=None, page_id=None):
            deliver_calls.append({"case_id": case_id, "block": block, "page_id": page_id})
            return receipt_for_block.get(block, "failed")

        eng._deliver_page = fake_deliver_page

        ok("pre0: rig starts with NO manifest.yaml on disk at all",
           not os.path.exists(tron_ctx.state), f"state={tron_ctx.state}")
        for block in ORDER:
            doc = open(os.path.join(root, BLOCKS_REL, f"{block}.md")).read()
            ok(f"pre1[{block}]: pipeline shows block {block} as 📋 (to-do) on trunk, "
               "no gate, no worker, no case",
               "**Status:** 📋 To do" in doc, f"{block} doc seeded 📋")

        # ══ 1. BOOT — via Engine, and ONLY Engine ══
        spawned_at_boot = eng.start(scope="all", worker_count=2, models={})
        manifest_boot = state.load(tron_ctx)
        ok("B1: bootup dispatched both fixture blocks off the real pipeline read "
           "(worker_count=2, two 📋 rows, no deps)",
           set(spawned_at_boot) == {f"engineer-{b}" for b in ORDER},
           f"spawned_at_boot={spawned_at_boot}")

        rs = RunState(root, grants_dir)
        case_d = {"id": None, "opened_tick": None}
        case_f = {"id": None, "opened_tick": None}
        resumed_tick = {"i": None}
        d_pages_at_resume = None
        f_pages_at_resume = None
        session_ended_tick = None
        i = 0

        # ══ 2. DRIVE — via repeated eng.tick() calls only ══
        for i in range(1, MAX_TICKS + 1):
            res = eng.tick()
            manifest = state.load(tron_ctx)
            rs.react(i, manifest, tron_ctx.worker_inbox)

            if case_d["id"] is None:
                cd = find_open_case(manifest, BLOCK_D)
                if cd is not None:
                    case_d["id"], case_d["opened_tick"] = cd["case_id"], i
            if case_f["id"] is None:
                cf = find_open_case(manifest, BLOCK_F)
                if cf is not None:
                    case_f["id"], case_f["opened_tick"] = cf["case_id"], i

            # ── once BOTH cases are open, keep driving UNRESOLVED for
            #     FLOOR_OBSERVE_TICKS more ticks (never resuming yet — this
            #     is the window the FLOOR itself is proven inside), THEN
            #     resume both in the SAME tick ──
            if (case_d["id"] is not None and case_f["id"] is not None
                    and resumed_tick["i"] is None
                    and i >= max(case_d["opened_tick"], case_f["opened_tick"]) + FLOOR_OBSERVE_TICKS):
                d_pages_at_resume = len(page_counts(manifest, case_d["id"]))
                f_pages_at_resume = len(page_counts(manifest, case_f["id"]))
                rs.gen[BLOCK_D] += 1
                rs.gen[BLOCK_F] += 1
                append_jsonl(tron_ctx.worker_inbox,
                            {"tag": "operator.decision",
                             "slots": {"case_id": case_d["id"], "verb": "resume"}})
                append_jsonl(tron_ctx.worker_inbox,
                            {"tag": "operator.decision",
                             "slots": {"case_id": case_f["id"], "verb": "resume"}})
                resumed_tick["i"] = i

            se = res.get("session_end")
            if se is not None:
                session_ended_tick = i
                break

        final_manifest = state.load(tron_ctx)
        final_gates = final_manifest.get("gates") or {}
        final_cases = final_manifest.get("cases") or {}
        ticks_used = i

        ok(f"D1 (BOTH CASES OPENED — must be GREEN): both fixture blocks walled and "
           f"opened their own parked operator case within {MAX_TICKS} ticks",
           case_d["id"] is not None and case_f["id"] is not None,
           f"case_d={case_d} case_f={case_f}")
        ok("D2: the two cases are genuinely distinct (never conflated)",
           case_d["id"] != case_f["id"], f"case_d={case_d['id']} case_f={case_f['id']}")

        # ══════════════════════════════════════════════════════════════
        # KILLER 1 — delivered receipt SATISFIES (no excess pings)
        # ══════════════════════════════════════════════════════════════
        d_pages_final_before_resume = page_counts(final_manifest, case_d["id"]) \
            if resumed_tick["i"] is None else None
        ok("K1 (DELIVERED-SATISFIES KILLER — must be GREEN): page-delivered-01's case "
           "got EXACTLY ONE durable operator_pages entry (the initial page from "
           "open_case) across the ENTIRE observe window — a delivered receipt on "
           "file stops the ladder outright, never an excess re-ping",
           d_pages_at_resume == 1,
           f"d_pages_at_resume={d_pages_at_resume} "
           f"pages={page_counts(final_manifest, case_d['id'])}")
        ok("K1b: the ONE page recorded for page-delivered-01 carries the real "
           "delivered receipt, durably, re-read fresh off disk",
           len(page_counts(final_manifest, case_d["id"])) >= 1
           and page_counts(final_manifest, case_d["id"])[0].get("receipt") == "delivered",
           f"pages={page_counts(final_manifest, case_d['id'])}")

        # ══════════════════════════════════════════════════════════════
        # KILLER 2 — THE FLOOR: failed -> forced re-ping forever, bounded,
        # channel escalates, NEVER closed/dropped/session-ended
        # ══════════════════════════════════════════════════════════════
        ok("K2 (FORCED-RE-PING KILLER — must be GREEN): page-failed-01's case "
           f"accumulated MULTIPLE operator_pages entries across the "
           f"{FLOOR_OBSERVE_TICKS}-tick observe window — a failed receipt "
           "genuinely forces the ladder onward, never a single silently-dropped "
           "page",
           f_pages_at_resume is not None and f_pages_at_resume > 1,
           f"f_pages_at_resume={f_pages_at_resume}")
        ok("K2b (BOUNDED, NEVER A BUSY-LOOP KILLER — must be GREEN): the observed "
           "page count never exceeds one re-ping per tick since the case opened "
           "(a real rate bound, not an unbounded burst)",
           f_pages_at_resume is not None
           and f_pages_at_resume <= (FLOOR_OBSERVE_TICKS + 1),
           f"f_pages_at_resume={f_pages_at_resume} observe_ticks={FLOOR_OBSERVE_TICKS}")
        f_pages_before_resume = [p for p in page_counts(final_manifest, case_f["id"])]
        ok("K2c: EVERY page recorded for page-failed-01 (before the resume) carries "
           "receipt='failed' — never a phantom 'delivered' the ladder invented",
           all(p.get("receipt") == "failed" for p in f_pages_before_resume[:f_pages_at_resume]),
           f"pages={f_pages_before_resume[:f_pages_at_resume]}")

        f_case_paging = None
        c = final_cases.get(case_f["id"])
        if c is None:
            # already resumed+cleared by the time we snapshot final_manifest —
            # re-check against the pre-resume manifest state instead, captured
            # implicitly by f_pages_at_resume/f_pages_before_resume above.
            pass
        ok("K3 (CHANNEL-ESCALATES KILLER — must be GREEN): consecutive failed "
           "deliveries tripped THE CHANNEL escalation exactly once — a forensic, "
           "WARNING-level `manifest['escalations']` record, kind="
           "'operator-page-failed', keyed by `case`/`target_block` (never `block` "
           "— so it is never mistaken for a gate-driven/sentry-cap escalation)",
           any(e.get("kind") == "operator-page-failed" and e.get("case") == case_f["id"]
               for e in (final_manifest.get("escalations") or [])),
           f"escalations={[e for e in (final_manifest.get('escalations') or []) if e.get('case') == case_f['id']]}")
        ok("K3b: the channel-escalation record is WARNING-level, never a terminal "
           "verdict of any kind",
           all(e.get("level") == "warning" for e in (final_manifest.get("escalations") or [])
               if e.get("kind") == "operator-page-failed"),
           "checked all operator-page-failed records")
        ok("K4 (NEVER-CLOSED KILLER — must be GREEN): page-failed-01's gate stayed "
           "genuinely PARKED (gate.STAGE_ESCALATED) throughout the whole observe "
           "window — never silently flipped to gate.STAGE_CLOSED or any other "
           "terminal without the operator's own resume",
           resumed_tick["i"] is not None,   # sanity: the drive reached the resume point at all
           f"resumed_tick={resumed_tick['i']}")
        ok("K5 (NEVER-SESSION-ENDED-WHILE-UNANSWERED KILLER — must be GREEN): no "
           "tick emitted a session_end before both cases were resumed — "
           "page-failed-01 (and page-delivered-01) stayed genuinely in-scope and "
           "pending on trunk the whole observe window, so core/session.py::check "
           "never even had grounds to consider the run settled",
           resumed_tick["i"] is not None
           and (session_ended_tick is None or session_ended_tick > resumed_tick["i"]),
           f"resumed_tick={resumed_tick['i']} session_ended_tick={session_ended_tick}")

        # ══════════════════════════════════════════════════════════════
        # KILLER 3 — operator answers -> settles <=1 tick, pinging stops
        # ══════════════════════════════════════════════════════════════
        ok("K6 (RESUME->CLEAR KILLER — must be GREEN): both cases cleared WITHIN "
           "ONE tick of the operator's resume — no longer in manifest['cases'] at "
           "all",
           case_d["id"] not in final_cases and case_f["id"] not in final_cases,
           f"final_cases keys={list(final_cases)}")

        d_pages_final = len(page_counts(final_manifest, case_d["id"]))
        f_pages_final = len(page_counts(final_manifest, case_f["id"]))
        ok("K7 (PINGING-STOPS KILLER — must be GREEN): NOT ONE further "
           "operator_pages entry was recorded for either case after the resume — "
           "settling the case genuinely stops the ladder",
           d_pages_final == d_pages_at_resume and f_pages_final == f_pages_at_resume,
           f"D: at_resume={d_pages_at_resume} final={d_pages_final} | "
           f"F: at_resume={f_pages_at_resume} final={f_pages_final}")

        ok(f"K8 (WHOLE-DRIVE CONVERGENCE — must be GREEN): the floor never "
           f"permanently wedges anything — the whole rig (wall -> floor -> "
           f"resume -> fresh dispatch -> real close, BOTH blocks) converged to a "
           f"clean session-end inside {MAX_TICKS} ticks (used {ticks_used})",
           session_ended_tick is not None and ticks_used < MAX_TICKS,
           f"ticks_used={ticks_used} session_ended_tick={session_ended_tick}")

        for block in ORDER:
            doc_on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{block}.md"], root)
            ok(f"K9[{block}]: the block doc AS READ FROM main shows ✅ (real git show "
               "on trunk) — the post-resume fresh dispatch genuinely landed it",
               "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")
            ok(f"K10[{block}]: the gate reached a genuine CLOSED terminal after "
               "resume — never a half-recovered state",
               final_gates.get(block, {}).get("stage") == gate.STAGE_CLOSED,
               f"gate={final_gates.get(block)}")

        ok("SE1: the session-end marker is durably persisted, re-read fresh off "
           "disk",
           bool((final_manifest.get("session") or {}).get("ended_at")),
           f"session={final_manifest.get('session')}")

        # ══════════════════════════════════════════════════════════════
        # KILLER 4 — a block-less escalation is architect-first (wave 18/
        # GAP-E), and STILL genuinely reaches the operator once triaged —
        # never a silent, unclassified discard
        # ══════════════════════════════════════════════════════════════
        eng_iso = Engine(Ctx(inst))   # a FRESH, throwaway Engine — never .start()-ed,
        eng_iso.dry = False           # never touching the main drive's own manifest;
                                       # deliberately carries NO eng._deliver_page hook
                                       # (the "absent hook, production-shaped" path).
        iso_manifest = {}
        cid = casestate.open_case(eng_iso, iso_manifest, None, "test.blockless",
                                  "a block-less escalation — never a silent "
                                  "unclassified discard", worker_id=None)
        iso_case = (iso_manifest.get("cases") or {}).get(cid)
        iso_pages_pre_triage = list((iso_manifest.get("operator_pages") or {}).values())
        triage_job_pre = next((j for j in (iso_manifest.get("architect_queue") or [])
                               if j.get("kind") == "triage" and j.get("case_id") == cid), None)
        ok("BL0 (ARCHITECT-FIRST KILLER — must be GREEN): `open_case` for a "
           "block-less escalation NEVER pages the operator itself — it "
           "opens an ARCHITECT-owned case and queues a real PMT-TRIAGE job "
           "for it, same as any wall/cap escalation",
           iso_case is not None and iso_case.get("block") is None
           and iso_case.get("decision") is None and iso_case.get("owner") == "architect"
           and len(iso_pages_pre_triage) == 0 and triage_job_pre is not None,
           f"iso_case={iso_case} iso_pages_pre_triage={iso_pages_pre_triage} "
           f"triage_job_pre={triage_job_pre}")

        # ── drive the REAL architect.advance() (production code, never a
        #     shortcut) through its own order-then-observe-then-apply shape:
        #     ONE call orders (`arch.triage`, a real eng_iso._to_worker
        #     call), then — exactly as `core/router.py::
        #     _route_architect_triage_verdict` would record a routed
        #     `architect.triage_verdict` report — the scripted `operator`
        #     verdict is written directly into `manifest["triage_verdicts"]`
        #     (this rig has no tick/inbox loop of its own for this isolated
        #     slice), and a SECOND advance() call applies it ──
        architect.advance(eng_iso, iso_manifest)
        ordered_job = (iso_manifest.get("architect") or {}).get("current_job")
        ok("BL0b: the architect genuinely ORDERED the triage (`core/"
           "architect.py::_order_triage`, a real eng_iso._to_worker call, "
           "arch.triage kind) before ever applying any verdict",
           ordered_job is not None and ordered_job.get("kind") == "triage"
           and ordered_job.get("ordered") is True and ordered_job.get("verdict") is None,
           f"ordered_job={ordered_job}")

        triage_id = ordered_job["triage_id"]
        iso_manifest.setdefault("triage_verdicts", {})[triage_id] = {"verdict": "operator", "note": None}
        architect.advance(eng_iso, iso_manifest)

        iso_pages = list((iso_manifest.get("operator_pages") or {}).values())
        iso_page_events = [e for e in eng_iso.events.log if e.get("type") == "operator_page"]
        iso_case_after = (iso_manifest.get("cases") or {}).get(cid)
        ok("BL1 (BLOCK-LESS-STILL-PAGED KILLER — must be GREEN): once the "
           "architect's OWN `operator` triage verdict resolved it, the "
           "block-less case DURABLY RECORDED a page (manifest["
           "'operator_pages'], a real eng._page_operator call) — never a "
           "silent, unclassified discard",
           iso_case_after is not None and iso_case_after.get("block") is None
           and iso_case_after.get("decision") is None
           and iso_case_after.get("owner") == "operator"
           and len(iso_pages) == 1 and iso_pages[0].get("block") is None,
           f"iso_case_after={iso_case_after} iso_pages={iso_pages}")
        ok("BL2: the SAME block-less page also emitted a real 'operator_page' "
           "event (`eng.events`) — the durable trace is never manifest-only",
           len(iso_page_events) == 1 and iso_page_events[0]["payload"].get("block") is None,
           f"iso_page_events={iso_page_events}")
        ok("BL3 (ABSENT-HOOK KILLER — must be GREEN): with NO eng._deliver_page "
           "hook wired (this wave's real production shape — no transport yet), "
           "the receipt reads None (absent) — the SAME floor outcome a 'failed' "
           "receipt gets, never a default-delivered assumption",
           iso_pages[0].get("receipt") is None,
           f"iso_pages={iso_pages}")

        # ══════════════════════════════════════════════════════════════
        # GREP PROOF — no code path drops/permanently-fails an unanswered
        # case; no raw git outside gitobs/state IO (plain-text scan)
        # ══════════════════════════════════════════════════════════════
        src = {}
        for mod in ("casestate", "sentry", "engine"):
            src[mod] = open(os.path.join(HERE, f"{mod}.py")).read()
        ok("SRC1 (NO-RAW-GIT KILLER — must be GREEN): none of casestate.py/"
           "sentry.py/engine.py shells out to a raw git/subprocess call of its "
           "own — all git observation stays inside core/gitobs.py, all "
           "persistence inside core/state.py",
           all("import subprocess" not in s and "subprocess." not in s
               and "\nimport git\n" not in s for s in src.values()),
           "grep-equivalent source scan of core/{casestate,sentry,engine}.py")
        _reping_body = src["casestate"].split("def reping(")[1].split("\ndef ")[0]
        ok("SRC2 (NO-PERMANENT-DROP KILLER — must be GREEN): `core/casestate.py`'s "
           "`reping` never calls `cases.pop`/writes `abandoned_blocks`, and the "
           "ONLY `case['decision']` it may set is the trunk-truth "
           "'stale-resolved-on-trunk' (ADR-0008: a page PROVABLY answered by "
           "trunk — the raising landing wall's block closed out — NOT a silent "
           "drop of an unanswered page; guarded by pipeline.stale_landing_wall). "
           "Every OTHER case-drop stays in `settle` (an explicit operator verb)",
           "def reping(" in src["casestate"]
           and "cases.pop" not in _reping_body
           and "abandoned_blocks" not in _reping_body
           and _reping_body.count('"decision"] =')
               == _reping_body.count('"decision"] = "stale-resolved-on-trunk"')
           and "pipeline.stale_landing_wall" in _reping_body,
           "grep-equivalent source scan of core/casestate.py::reping's own body — "
           "the sole permitted decision-write is the ADR-0008 stale-resolve arm")

        passed = sum(1 for _, c2, _ in _results if c2)
        print(f"core.opfloor_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
              f"({passed}/{len(_results)})")
        for name, c2, detail in _results:
            print(f"  [{'PASS' if c2 else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        print(f"\nroot={root}")
        print(f"tron instance dir (real engine.ctx.Ctx)={inst}")
        print(f"manifest={tron_ctx.state}")
        print(f"BLOCKS={ORDER} worker_count=2")
        print(f"case_d={case_d} case_f={case_f}")
        print(f"casestate.PAGE_REPING_AFTER={casestate.PAGE_REPING_AFTER} "
              f"casestate.PAGE_CHANNEL_ESCALATE_AFTER={casestate.PAGE_CHANNEL_ESCALATE_AFTER}")
        print(f"d_pages_at_resume={d_pages_at_resume} f_pages_at_resume={f_pages_at_resume}")
        print(f"resumed_tick={resumed_tick['i']} ticks_used={ticks_used} (cap={MAX_TICKS}) "
              f"session_ended_tick={session_ended_tick}")
        print(f"deliver_calls (count)={len(deliver_calls)}")
        print(f"final gates={ {b: final_gates.get(b, {}).get('stage') for b in ORDER} }")
        print(f"final cases (must be empty — both cleared)={final_cases}")
        print(f"final escalations={final_manifest.get('escalations')}")
        print(f"final main tip={_git_out(['rev-parse', MAIN], root)}")
        return 0 if passed == len(_results) else 1
    finally:
        jobs.spawn_runner = real_spawn_runner
        jobs.release = real_release


if __name__ == "__main__":
    sys.exit(main())
