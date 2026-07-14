"""core.engine_rig — real-git, no-LLM rig proving `core.engine.Engine`
(wave 12: the entrypoint that assembles EVERY `core/*.py` module into a
runnable whole — `contracts/rebuild-spec.md` T1-A bootup A1-A9;
`contracts/blueprint-contracts.md` §1) does exactly what its own module
docstring promises: `Engine(ctx).start(...)` boots a REAL session (manifest
written, the persistent pool-excluded architect spawned, the first
SWITCHBOARD dispatch performed) and `Engine.run(...)` drives it, via
repeated `Engine.tick()` calls (never a direct `core.tick.tick`/`core.
switchboard.fill`/... call of this rig's own — THIS is the wiring proof),
all the way to a genuine, clean, idempotent SESSION-END — bootup through
done, through `Engine` and only `Engine`.

REAL surface only: a real `git init` repo copied from the SAME scaffold
every prior `core/*_rig.py` uses, `meta/scripts/land.sh` run for real via
`subprocess`, a REAL `engine.ctx.Ctx` pointing at a real `manifest.yaml`, a
real `project.yaml`/`knobs.yaml`/`roles.yaml` this rig writes itself (the
ONE new file shape this brick needs that no prior rig did: `Engine.__init__`
calls `ctx.repo_paths(ctx.load_project())` and, on any spawn,
`engine.roles.RolesConfig.load(roles_path, ...)` — for REAL, never
monkeypatched), and a REAL declared test command (`true`) re-run in a REAL
clean detached worktree. Unlike every prior `core/*_rig.py`, this rig does
NOT build its own `MiniEng` stand-in — it constructs the ACTUAL `core.
engine.Engine` and drives everything through it. The ONE seam stubbed is
`engine.jobs.spawn_runner` (monkeypatched to a no-op that just records the
call — never a real `claude` process), exactly the established "rig plays
the worker, never spawns a real agent" pattern every prior rig's own
`_spawn_worker` stood in for; every OTHER `Engine` hook (`_to_worker`,
`_release_worker`, `_page_operator`, `_grant_ttl`, `log`) runs FOR REAL,
touching only TRON's own folder (`ctx.workers_dir`/`ctx.home_log`).

The rig plays FOUR roles a real deployment splits across processes: the
WAKE daemon (calls `eng.tick()`/`eng.run()` — never `core.tick.tick`
directly), the ordinary engineer (branch/local-pass/real `land.sh`/record
commit/teardown — generalized over WHATEVER `engineer-<block>` worker
record appears, exactly `core/reviewers_rig.py`'s own `RunHistory.
react_engineers` shape, which is what lets this SAME code drive both the
three pre-seeded blocks AND, later, the freshly-authored log-review adhoc
block), the reviewer (`worker.review_done`, hold then attest), and the
architect (reacts to BOTH a `reconcile` job — M-05, `core/architect.py` —
and a `log` job — wave 10 — exactly like `core/multiblock_rig.py`/`core/
reviewers_rig.py`'s own scripted architects).

Fixture: THREE real pipeline blocks, `01-01`/`01-03` (no deps) + `01-02`
(**Depends on:** `01-01`, the SAME real dependency edge `core/multiblock_
rig.py` proves), `worker_count=1` (strict serialization — cadence due-check
runs BEFORE block dispatch every `fill()` call, so this is ALSO the
"reviewer wins the free slot over the next block" proof), `cadence: {code:
2}` (a `reviewer-code` review fires once two blocks land ✅), a `roles.yaml`
binding `engineer` (BUILD+CLOSE), `reviewer-code` (REVIEW, selector
`reviewer_class: code`) and `architect` (TRIAGE, `spec_owner: true`,
`persistent: true`) — every capability class (`BUILD`/`REVIEW`/`TRIAGE`/
`CLOSE`) resolvable, `engine.roles.RolesConfig`'s own fail-closed boot
validation satisfied for real. The reviewer's FIRST hand-back carries one
finding; its SECOND (attest) hand-back carries none of its own (falls back
to the stashed first-hand-back finding, `core/reviewers.py::on_review_done`'s
own documented fallback) — `core/architect.py::enqueue_log_review` queues a
`log` job the scripted architect authors + REAL-lands as a genuinely NEW
pipeline row + block file (mirrors `core/reviewers_rig.py`'s own
`make_adhoc_doc`), which then dispatches + drives to ✅ + CLOSED through the
SAME generalized engineer react loop as any ordinary block — proving
"any log-review adhoc block closes" for real, not just "landed".

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
import architect                  # noqa: E402 — core/architect.py, ARCHITECT_WID
import state                       # noqa: E402 — core/state.py
from engine import Engine, BootupError   # noqa: E402 — core/engine.py, THE MODULE UNDER TEST

import scaffold_src               # noqa: E402 — core/scaffold_src.py, the ONE resolver

SCAFFOLD_SRC = scaffold_src.resolve()
MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"
ROLES_REL = "meta/tron/roles.yaml"
PERSONAS_REL = "meta/tron/personas"

BLOCK_A, BLOCK_B, BLOCK_C = "01-01", "01-02", "01-03"
BLOCKS = {
    BLOCK_A: {"depends_on": []},
    BLOCK_B: {"depends_on": [BLOCK_A]},
    BLOCK_C: {"depends_on": []},
}
ORDER = [BLOCK_A, BLOCK_B, BLOCK_C]

CADENCE_TYPE = "code"
CADENCE_THRESHOLD = 2
STUB_MODEL = "stub-model"
MAX_TICKS = 400

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
    d = tempfile.mkdtemp(prefix="tron-core-enginerig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-engine-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: engine_rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {a} | engine_rig fixture block A (no deps) | 📋 To do | Block `blocks/{a}.md` |
| {b} | engine_rig fixture block B (depends on {a}) | 📋 To do | Block `blocks/{b}.md` |
| {c} | engine_rig fixture block C (no deps) | 📋 To do | Block `blocks/{c}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: engine_rig fixture

**Phase:** 1 — engine_rig
**Status:** 📋 To do
**Depends on:** {depends_on}
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.engine_rig` — proves `core.engine.Engine`
(bootup -> tick loop) drives a real multi-block + real dependency + real
cadence-reviewer + real log-review-adhoc pipeline to a genuine clean
SESSION-END, entirely through `Engine`.
"""

ADHOC_PIPELINE_SECTION = """
## Ad-hoc

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
"""

ADHOC_ROW_TEMPLATE = "| {block} | {title} | 📋 To do | Block `blocks/{block}.md` |\n"

ADHOC_BLOCK_DOC_TEMPLATE = """# Block {block}: log-review adhoc fixture

**Phase:** 1 — engine_rig log-review
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Authored by the SCRIPTED ARCHITECT (`core.engine_rig`, playing a real
`log` job) from a code-review finding: {title!r} — a genuinely NEW adhoc
block (no pre-existing pipeline row), landed via `core.landing.
land_via_grant` under a content-bound case-id, then dispatched and driven
to ✅ + CLOSED exactly like any ordinary block.
"""

PERSONA_TEMPLATE = """# {role} persona (core.engine_rig fixture)

A synthetic persona file — `engine.roles.RolesConfig`'s own fail-closed
boot validation requires every declared role's persona to exist on disk;
this rig's workers are entirely scripted (no LLM, no real `claude`
process — `engine.jobs.spawn_runner` is stubbed), so the CONTENT here is
never read by anything, only its presence.
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


def seed_pipeline(root):
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


def seed_roles(root):
    """The ONE new project-authored surface this brick's rig needs that no
    prior `core/*_rig.py` ever did: a real `roles.yaml` (ADR-0002 D4) +
    real persona files, committed to trunk — `core.engine.Engine` resolves
    both for REAL on every spawn (`engine.roles.RolesConfig`, never
    monkeypatched)."""
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
        "repo": {
            "root": root,
            "main_branch": MAIN,
            "remote": "none",
            "staging": "none",
        },
        "test": {"command": "true"},
    }
    with open(os.path.join(inst_dir, "project.yaml"), "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)


def write_knobs(inst_dir):
    """Deliverable knobs, SCHEMA-COMPLIANT nested form (`contracts/schema/
    knobs.schema.yaml`, wave 16 — closes the fidelity gap the old FLAT
    write here used to mask): `worker_count` (informational — `Engine.
    start`'s own `worker_count` PARAM is what actually governs the pool,
    exactly the headless-launcher shape `tron-meta/sims/autopilot/
    bootstrap.py` uses; nothing in `core/` reads a `worker_count` knob),
    `silence_ping_min`/`silence_escalate_min` (`core.liveness._silence_
    knobs`'s own read target — set generously high relative to `MAX_TICKS`
    so the ladder is genuinely CONFIGURED [not a no-op] but never actually
    fires across this fixture's real run: `core/liveness_rig.py`, wave 11,
    already proves the ping/stall ladder itself exhaustively; this brick's
    own job is the WHOLE-ENGINE wiring proof, not a second liveness proof),
    `grant_ttl` (`Engine._grant_ttl`'s own read target), all nested under
    `knobs:`; `cadence: {code: 2}` (`core.reviewers._cadence_cfg`'s own
    read target) is its OWN top-level block, a sibling of `knobs:`, never
    nested."""
    doc = {
        "knobs": {
            "worker_count": 1,
            "silence_ping_min": 80,
            "silence_escalate_min": 160,
            "grant_ttl": 60,
        },
        "cadence": {CADENCE_TYPE: CADENCE_THRESHOLD},
    }
    with open(os.path.join(inst_dir, "knobs.yaml"), "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)


def make_code_commit(root, branch, code_file_rel, marker):
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(f"// {marker} — core.engine_rig real code change\n")
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


def make_adhoc_doc(root, branch, block, title):
    """The rig-as-architect authoring a REAL, genuinely NEW pipeline row +
    block file for a log-review finding, in ONE commit, on the architect's
    own branch (mirrors `core/reviewers_rig.py::make_adhoc_doc`)."""
    _git(["checkout", "-B", branch, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    with open(ppath) as f:
        original = f.read()
    row = ADHOC_ROW_TEMPLATE.format(block=block, title=title)
    if "## Ad-hoc" not in original:
        content = original.rstrip("\n") + "\n" + ADHOC_PIPELINE_SECTION + row
    else:
        lines = original.splitlines(keepends=True)
        idx = next(i for i, l in enumerate(lines) if l.strip().startswith("## Ad-hoc"))
        j = idx + 1
        while j < len(lines) and not lines[j].strip().startswith("|:"):
            j += 1
        lines.insert(j + 1, row)
        content = "".join(lines)
    with open(ppath, "w") as f:
        f.write(content)
    bpath = os.path.join(root, BLOCKS_REL, f"{block}.md")
    os.makedirs(os.path.dirname(bpath), exist_ok=True)
    with open(bpath, "w") as bf:
        bf.write(ADHOC_BLOCK_DOC_TEMPLATE.format(block=block, title=title))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"arch(log-review): author adhoc block {block}"], root)
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


def rebase_onto_main(root, branch):
    """A real worker's own recovery from `land.sh`'s "not a fast-forward"
    refusal: replay `branch`'s own commits onto the CURRENT `main` tip
    (mirrors `core/liveness_rig.py`/`core/architect_rig.py`'s own identical
    helper) — needed here because the architect (persistent, pool-excluded,
    genuinely CONCURRENT with whatever engineer/reviewer currently holds
    the single `worker_count=1` slot) can land its own content (a `log`
    job's adhoc block file) while an engineer's branch sits forked,
    advancing `main` out from under it."""
    _git(["checkout", branch], root)
    r = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", MAIN, branch])
    if r.returncode != 0:
        _git(["rebase", MAIN], root)
    _git(["checkout", "--detach", MAIN], root)


def try_land(root, grants_dir, case_id, branch):
    """Run the REAL `land.sh`; on a genuine "not a fast-forward"/CAS-failed
    refusal (the architect's own concurrent landing advanced `main` out
    from under this branch's stale fork point), rebase onto the fresh
    `main` and return False so the caller retries the SAME case_id on a
    LATER tick (`land_via_grant`'s own patch-id-bound grant survives a
    conflict-free rebase unchanged — same content, new base). A genuinely
    UNEXPECTED failure is fail-loud, same as every other rig in this
    stack. Returns True only once land.sh itself reports success."""
    rc, out, err = run_land(root, grants_dir, case_id)
    if rc == 0:
        return True
    combined = (out or "") + (err or "")
    if "not a fast-forward" in combined or "CAS failed" in combined:
        rebase_onto_main(root, branch)
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

FINDING = {"title": "tidy inconsistent status wording across landed blocks"}


class RunHistory:
    """Per-run mutable tracking, generalized over WHATEVER `engineer-*`/
    `reviewer-*` worker record appears in the REAL, persisted manifest —
    this is what lets the SAME react loop drive the three pre-seeded
    blocks AND, later, the freshly-authored log-review adhoc block,
    without this rig ever needing to know its id up front (mirrors
    `core/reviewers_rig.py::RunHistory`)."""

    def __init__(self, root, grants_dir, tron_ctx):
        self.root = root
        self.grants_dir = grants_dir
        self.tron_ctx = tron_ctx
        self.branch_created = {}
        self.local_reported = {}
        self.record_committed = {}
        self.torn_down = {}
        self.spawn_tick = {}
        self.done_tick = {}
        self.close_tick = {}
        self.landed_cases = set()
        self.reviewer_seen = {}
        self.review_first_sent = set()
        self.review_hold_tick = {}
        self.review_attest_sent = set()
        self.review_release_tick = {}
        self.adhoc_authored = set()
        self.adhoc_landed_tick = {}
        self.reconciled_reported = set()
        self.tick_history = []   # (i, outcomes, spawned, session_end)

    def _track(self, block):
        self.branch_created.setdefault(block, False)
        self.local_reported.setdefault(block, False)
        self.record_committed.setdefault(block, False)
        self.torn_down.setdefault(block, False)

    def react_engineers(self, i, manifest):
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}
        for agent_id, w in list(workers.items()):
            if not agent_id.startswith("engineer-"):
                continue
            block = w.get("block")
            if not block:
                continue
            self._track(block)
            branch = f"feat/{block}"
            if block not in self.spawn_tick:
                self.spawn_tick[block] = i
            if w.get("status") == "spawning" and not self.branch_created[block]:
                make_code_commit(self.root, branch, f"src/lib/{block}.ts",
                                 f"{block}-enginerig-change")
                self.branch_created[block] = True
                append_jsonl(self.tron_ctx.worker_inbox,
                            {"tag": "worker.online", "agent_id": agent_id,
                             "slots": {"branch": branch}})

            g = gates.get(block)
            if not g:
                continue
            stage = g.get("stage")
            block_file_rel = f"{BLOCKS_REL}/{block}.md"

            if stage == gate.STAGE_LOCAL and not self.local_reported[block]:
                append_jsonl(self.tron_ctx.worker_inbox,
                            {"tag": "worker.done", "block": block, "slots": LOCAL_PASS_REPORT})
                self.local_reported[block] = True
            elif stage == gate.STAGE_MERGE and g.get("merge_case_id"):
                case_id = g["merge_case_id"]
                if case_id not in self.landed_cases:
                    if try_land(self.root, self.grants_dir, case_id, branch):
                        self.landed_cases.add(case_id)
            elif stage == gate.STAGE_RECORD:
                if g.get("record_ordered") and not self.record_committed[block] \
                        and not g.get("record_case_id"):
                    make_record_commit(self.root, branch, block_file_rel)
                    self.record_committed[block] = True
                if g.get("record_case_id") and g["record_case_id"] not in self.landed_cases:
                    case_id = g["record_case_id"]
                    if try_land(self.root, self.grants_dir, case_id, branch):
                        self.landed_cases.add(case_id)
            elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not self.torn_down[block]:
                _git(["branch", "-D", branch], self.root)
                self.torn_down[block] = True

            if stage == gate.STAGE_CLOSED and block not in self.close_tick:
                self.close_tick[block] = i

    def react_reviewer(self, i, manifest):
        workers = manifest.get("workers") or {}
        for agent_id, w in list(workers.items()):
            if not agent_id.startswith("reviewer-"):
                continue
            typ = w.get("type")
            if agent_id not in self.reviewer_seen:
                self.reviewer_seen[agent_id] = i
            status = w.get("status")
            if status == "reviewing" and agent_id not in self.review_first_sent:
                append_jsonl(self.tron_ctx.worker_inbox,
                            {"tag": "worker.review_done", "agent_id": agent_id, "type": typ,
                             "slots": {"findings": [FINDING]}})
                self.review_first_sent.add(agent_id)
            elif status == "held":
                if agent_id not in self.review_hold_tick:
                    self.review_hold_tick[agent_id] = i
                if agent_id not in self.review_attest_sent:
                    # Second hand-back carries NO findings of its own — falls
                    # back to the stashed first-hand-back finding
                    # (`core/reviewers.py::on_review_done`'s own documented
                    # fallback), exactly like a real reviewer confirming
                    # coverage without re-stating what it already reported.
                    append_jsonl(self.tron_ctx.worker_inbox,
                                {"tag": "worker.review_done", "agent_id": agent_id, "type": typ,
                                 "slots": {}})
                    self.review_attest_sent.add(agent_id)
        for agent_id in self.reviewer_seen:
            if agent_id not in workers and agent_id not in self.review_release_tick:
                self.review_release_tick[agent_id] = i

    def react_architect_reconcile(self, i, manifest):
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if cur and cur.get("kind") == "reconcile" and cur.get("ordered") \
                and cur.get("block") not in self.reconciled_reported:
            append_jsonl(self.tron_ctx.worker_inbox,
                        {"tag": "architect.reconciled", "block": cur["block"],
                         "agent_id": architect.ARCHITECT_WID})
            self.reconciled_reported.add(cur["block"])

    def react_architect_log(self, i, manifest):
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if not (cur and cur.get("kind") == "log" and cur.get("ordered")):
            return
        for e in cur.get("adhoc") or []:
            block, branch = e["block"], e["branch"]
            title = (e.get("finding") or {}).get("title") or f"finding for {block}"
            if block not in self.adhoc_authored:
                make_adhoc_doc(self.root, branch, block, title)
                self.adhoc_authored.add(block)
            case_id = e.get("case_id")
            if case_id and case_id not in self.landed_cases:
                if try_land(self.root, self.grants_dir, case_id, branch):
                    self.landed_cases.add(case_id)
                    if block not in self.adhoc_landed_tick:
                        self.adhoc_landed_tick[block] = i

    def react(self, i, manifest):
        self.react_engineers(i, manifest)
        self.react_reviewer(i, manifest)
        self.react_architect_reconcile(i, manifest)
        self.react_architect_log(i, manifest)

    def record_done_ticks(self, i, outcomes):
        for block, (outcome, _detail) in outcomes.items():
            if outcome == "record_landed" and block not in self.done_tick:
                self.done_tick[block] = i


def main():
    root = build_root()
    seed_pipeline(root)
    seed_roles(root)

    inst = os.path.join(root, "meta", "agents", "tron")
    write_project_yaml(inst, root)
    write_knobs(inst)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    # ── stub the ONE process-spawn seam: engine.jobs.spawn_runner — never a
    #     real `claude` process. Both `Engine._spawn_worker` (engineers +
    #     reviewers) and `Engine._spawn_architect` (the persistent architect)
    #     go through this SAME `jobs.spawn_runner` call, so one monkeypatch
    #     covers both. Records (worker_id, model, cwd) for the rig's own
    #     assertions — nothing else about `Engine`'s real spawn plumbing
    #     (retire_stale_dir, worker-dir/scratch-dir creation, role/model
    #     resolution via a REAL roles.yaml) is touched. ──
    spawn_calls = []

    def fake_spawn_runner(worker_id, worker_dir, session_id, cwd=None,
                          runtime=None, adapter=None, model=None, settle_s=2.0):
        spawn_calls.append({"worker_id": worker_id, "model": model, "cwd": cwd,
                            "session_id": session_id})
        return {}

    real_spawn_runner = jobs.spawn_runner
    jobs.spawn_runner = fake_spawn_runner

    # ── wrap (never replace) the REAL `jobs.release` — this hook stays
    #     genuinely real (writes the `.stop` sentinel, SIGTERMs the runner's
    #     process group) per the hard rule; the wrapper only ADDS the rig's
    #     own call-count instrumentation, exactly like `spawn_calls` above,
    #     so M3 below can prove "REALLY released" against the real seam
    #     (never `manifest["workers"][wid]["status"]`, a field `core/gate.py`
    #     ::_advance_close never touches — release is a SEPARATE bookkeeping
    #     channel from the gate's own terminal stage, by design). ──
    release_calls = []
    real_release = jobs.release

    def wrapped_release(worker_id, idx=None):
        release_calls.append(worker_id)
        return real_release(worker_id, idx=idx)

    jobs.release = wrapped_release

    try:
        # ── pre-flight: NO pre-seeded gate, NO pre-seeded worker, NO manifest ──
        ok("pre0: rig starts with NO manifest.yaml on disk at all (a brand-new "
           "instance, never yet ticked)",
           not os.path.exists(tron_ctx.state), f"state={tron_ctx.state}")
        for block in ORDER:
            doc = open(os.path.join(root, BLOCKS_REL, f"{block}.md")).read()
            ok(f"pre1[{block}]: pipeline shows block {block} as 📋 (to-do) on trunk, "
               "no gate, no worker",
               "**Status:** 📋 To do" in doc, f"{block} doc seeded 📋")
        ok("pre2: block 01-02's own doc carries the REAL `Depends on: 01-01` edge",
           "**Depends on:** 01-01" in
           open(os.path.join(root, BLOCKS_REL, f"{BLOCK_B}.md")).read(),
           "01-02 doc Depends-on header")

        # ══ 1. CONSTRUCT + BOOT — via Engine, and ONLY Engine ══
        eng = Engine(Ctx(inst))
        eng.dry = False   # HARD RULE: real trunk observation throughout

        ok("B0: Engine() resolved real repo_paths off a real project.yaml — "
           "root/main_branch/test_command all present, worker_count floored at 1",
           eng.paths.get("root") == root and eng.paths.get("main_branch") == MAIN
           and eng.paths.get("test_command") == "true" and eng.paths.get("worker_count") == 1,
           f"paths={eng.paths}")

        spawned_at_boot = eng.start(scope="all", worker_count=1, models={})
        manifest_after_boot = state.load(tron_ctx)

        ok("B1 (BOOTUP KILLER — must be GREEN): start() wrote a real, durable "
           "manifest.yaml with a session start marker",
           os.path.exists(tron_ctx.state) and bool(
               (manifest_after_boot.get("session") or {}).get("started_at")),
           f"session={manifest_after_boot.get('session')}")
        ok("B2: bootup resolved scope='all' to all three roadmap ids",
           sorted((manifest_after_boot.get("scope") or {}).get("ids") or []) == sorted(ORDER),
           f"scope={manifest_after_boot.get('scope')}")
        ok("B3 (POOL-EXCLUDED KILLER — must be GREEN): the persistent architect "
           "was spawned at boot (a real jobs.spawn_runner call for "
           f"{architect.ARCHITECT_WID!r}) but carries NO manifest['workers'] entry "
           "— never counted toward the worker_count pool",
           (manifest_after_boot.get("architect") or {}).get("spawned") is True
           and any(c["worker_id"] == architect.ARCHITECT_WID for c in spawn_calls)
           and architect.ARCHITECT_WID not in (manifest_after_boot.get("workers") or {}),
           f"architect={manifest_after_boot.get('architect')} "
           f"spawn_calls={[c['worker_id'] for c in spawn_calls]} "
           f"workers={list((manifest_after_boot.get('workers') or {}).keys())}")
        ok("B4: the architect's spawn resolved a REAL model off roles.yaml "
           "(never an ambient default)",
           next((c["model"] for c in spawn_calls if c["worker_id"] == architect.ARCHITECT_WID),
               None) == STUB_MODEL,
           f"spawn_calls={spawn_calls}")
        ok("B5 (FIRST DISPATCH KILLER — must be GREEN): bootup's own first "
           "SWITCHBOARD dispatch spawned 01-01 (a real worker record + a real "
           "jobs.spawn_runner call) and left 01-02 DEP-GATED (no worker record "
           "at all yet — 01-01 not yet ✅ on trunk)",
           "engineer-01-01" in spawned_at_boot
           and "engineer-01-01" in (manifest_after_boot.get("workers") or {})
           and "engineer-01-02" not in (manifest_after_boot.get("workers") or {})
           and any(c["worker_id"] == "engineer-01-01" for c in spawn_calls),
           f"spawned_at_boot={spawned_at_boot} "
           f"workers={list((manifest_after_boot.get('workers') or {}).keys())}")
        ok("B6: 01-03 (no dep) was NOT spawned at boot either — worker_count=1's "
           "single slot went to 01-01 by living-doc order, never two spawns in "
           "one bootup pass",
           "engineer-01-03" not in (manifest_after_boot.get("workers") or {}),
           f"workers={list((manifest_after_boot.get('workers') or {}).keys())}")

        ok("B7 (RE-ENTRANT BOOTUP KILLER — must be GREEN): calling start() again "
           "on a now-live session refuses loud (BootupError), never a silent "
           "second bootup/second architect spawn",
           _raises(BootupError, lambda: eng.start(scope="all", worker_count=1)),
           "expected BootupError on a second start() call")

        # ══ 2. RUN — via Engine.run(), and ONLY Engine.run() (one tick per
        #     call, so this rig's own react() can inspect the manifest after
        #     EVERY tick, exactly like every prior core/*_rig.py's own loop) ══
        hist = RunHistory(root, grants_dir, tron_ctx)
        session_ended_tick = None
        i = 0
        for i in range(MAX_TICKS):
            res_list = eng.run(max_ticks=1)
            res = res_list[0]
            manifest = state.load(tron_ctx)
            se = res.get("session_end")
            hist.tick_history.append((i, dict(res["outcomes"]), list(res["spawned"]), se))
            hist.record_done_ticks(i, res["outcomes"])
            hist.react(i, manifest)
            if se is not None and session_ended_tick is None:
                session_ended_tick = i
                break

        final_manifest = state.load(tron_ctx)
        final_gates = final_manifest.get("gates") or {}
        final_workers = final_manifest.get("workers") or {}
        ticks_used = i + 1

        ok(f"R0 (WHOLE-ENGINE CONVERGENCE — must be GREEN): the whole drive "
           f"(3 real blocks + a real dependency + a real cadence review + a real "
           f"log-review adhoc block) converged to a clean session-end, entirely "
           f"via Engine.run(), inside {MAX_TICKS} ticks (used {ticks_used})",
           session_ended_tick is not None and ticks_used < MAX_TICKS,
           f"ticks_used={ticks_used} session_ended_tick={session_ended_tick}")

        # ══ THE THREE ORIGINAL BLOCKS ══
        for block in ORDER:
            branch = f"feat/{block}"
            block_file_rel = f"{BLOCKS_REL}/{block}.md"
            g = final_gates.get(block, {})
            agent_id = f"engineer-{block}"
            ok(f"M1[{block}]: SWITCHBOARD (via Engine) spawned {block} — a real "
               "worker record + a real jobs.spawn_runner call",
               block in hist.spawn_tick
               and any(c["worker_id"] == agent_id for c in spawn_calls),
               f"spawn_tick={hist.spawn_tick.get(block)}")
            doc_on_main = _git_out(["show", f"{MAIN}:{block_file_rel}"], root)
            ok(f"M2[{block}] (ALL THREE ✅ ON TRUNK — must be GREEN): the block "
               "doc AS READ FROM main shows ✅",
               "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")
            branch_gone = not trunk.branch_exists(root, branch, False)
            clean_now, _detail = trunk.replica_clean(root, branch, MAIN, False)
            ok(f"M3[{block}] (SLOT-FREED KILLER — must be GREEN): the replica is "
               "genuinely clean, the gate is CLOSED, and Engine._release_worker "
               "made a REAL jobs.release() call for this worker (never a "
               "trust-release)",
               branch_gone and clean_now and g.get("stage") == gate.STAGE_CLOSED
               and agent_id in release_calls,
               f"branch_gone={branch_gone} clean={clean_now} stage={g.get('stage')} "
               f"released={agent_id in release_calls}")

        # ══ THE DEP-ORDERING KILLER ══
        ok("M4 (DEP-ORDERING KILLER — must be GREEN): 01-02 was not spawned until "
           "01-01 was OBSERVED ✅ on trunk (record_landed)",
           BLOCK_A in hist.done_tick and BLOCK_B in hist.spawn_tick
           and hist.spawn_tick[BLOCK_B] > hist.done_tick[BLOCK_A],
           f"done_tick[{BLOCK_A}]={hist.done_tick.get(BLOCK_A)} "
           f"spawn_tick[{BLOCK_B}]={hist.spawn_tick.get(BLOCK_B)}")

        # ══ THE RECONCILE-GATE KILLER (M-05) ══ — `_enqueue_reconcile` targets
        # the NEXT in-scope block AFTER the one that just landed, by
        # living-doc order: 01-01 landing -> reconcile targets 01-02;
        # 01-02 landing -> reconcile targets 01-03 (the SAME two-edge chain
        # `core/multiblock_rig.py` proves, here driven entirely through Engine).
        ok("M5: the architect reconciled both edges (target 01-02 after 01-01 "
           "lands, target 01-03 after 01-02 lands)",
           BLOCK_B in hist.reconciled_reported and BLOCK_C in hist.reconciled_reported,
           f"reconciled_reported={hist.reconciled_reported}")

        # ══ THE CADENCE-REVIEWER KILLER ══
        reviewer_ids = [a for a in hist.reviewer_seen if a.startswith(f"reviewer-{CADENCE_TYPE}-")]
        ok("M6 (CADENCE-REVIEWER KILLER — must be GREEN): a reviewer-code "
           "dispatched (cadence PULL, real worker_count=1 slot contention with "
           "the block pool), HELD on the first worker.review_done, and was "
           "genuinely RELEASED on the second (attest) — popped off "
           "manifest['workers'], never a manifest['gates'] entry",
           len(reviewer_ids) >= 1
           and all(rid in hist.review_hold_tick for rid in reviewer_ids)
           and all(rid in hist.review_release_tick for rid in reviewer_ids)
           and all(rid not in final_workers for rid in reviewer_ids),
           f"reviewer_ids={reviewer_ids} hold={hist.review_hold_tick} "
           f"release={hist.review_release_tick}")

        # ══ THE LOG-REVIEW ADHOC KILLER ══ — every landed block (the three
        # originals AND, in turn, any adhoc block itself) feeds the SAME
        # cadence counter (`core.reviewers.bump_cadence` counts every
        # `record_landed` block, adhoc included — a genuine code change no
        # less than an ordinary one), so this fixture's own cadence:2
        # threshold can legitimately fire the review->log-review chain MORE
        # than once (>= 1, never assumed to be exactly one) before it
        # naturally runs out of newly-landed blocks to count and the run
        # settles. Every adhoc block this chain produces must land AND close.
        adhoc_blocks = list(hist.adhoc_authored)
        ok("M7 (LOG-REVIEW ADHOC KILLER — must be GREEN): at least one attested "
           "review's finding queued a real architect `log` job that authored + "
           "REAL-landed a genuinely NEW pipeline row + block file, and EVERY "
           "adhoc block authored was, in fact, landed",
           len(adhoc_blocks) >= 1
           and all(b in hist.adhoc_landed_tick for b in adhoc_blocks),
           f"adhoc_blocks={adhoc_blocks} adhoc_landed_tick={hist.adhoc_landed_tick}")
        if adhoc_blocks:
            closes_ok = True
            detail_bits = []
            for adhoc in adhoc_blocks:
                adhoc_doc = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{adhoc}.md"], root)
                this_ok = (adhoc in hist.spawn_tick and adhoc in hist.close_tick
                          and final_gates.get(adhoc, {}).get("stage") == gate.STAGE_CLOSED
                          and "**Status:** ✅ Done" in adhoc_doc)
                closes_ok = closes_ok and this_ok
                detail_bits.append(f"{adhoc}: spawn={hist.spawn_tick.get(adhoc)} "
                                   f"close={hist.close_tick.get(adhoc)} "
                                   f"stage={final_gates.get(adhoc, {}).get('stage')}")
            ok("M8 (LOG-REVIEW ADHOC CLOSES — must be GREEN): EVERY adhoc block "
               "was then DISPATCHED (a real engineer-<id> worker) and driven to "
               "✅ ON TRUNK + a genuine CLOSED gate, exactly like any ordinary "
               "block — never just 'landed', it CLOSES",
               closes_ok, "; ".join(detail_bits))
        else:
            ok("M8 (LOG-REVIEW ADHOC CLOSES — must be GREEN): skipped, no adhoc "
               "block was ever authored (M7 already failed)", False, "no adhoc block")

        # ══ SESSION-END KILLERS ══
        all_block_ids = ORDER + adhoc_blocks
        ok("M9 (SESSION-END KILLER — must be GREEN): the clean session-end "
           "terminal fired only once EVERY in-scope block (all three original "
           "+ the adhoc log-review block) was ✅ + CLOSED",
           session_ended_tick is not None
           and all(final_gates.get(b, {}).get("stage") == gate.STAGE_CLOSED for b in all_block_ids),
           f"final stages={ {b: final_gates.get(b, {}).get('stage') for b in all_block_ids} }")
        ok("M10: no earlier tick emitted a session-end",
           all(se is None for _i, _o, _s, se in hist.tick_history[:session_ended_tick]),
           f"session_end per tick={[se for _, _, _, se in hist.tick_history]}")
        ok("M11: the session-end marker is durable — re-read fresh off disk",
           bool((final_manifest.get("session") or {}).get("ended_at")),
           f"session={final_manifest.get('session')}")

        # ══ IDEMPOTENT RE-TICK — via Engine, entirely ══
        pre_replay_manifest_bytes = open(tron_ctx.state, "rb").read()
        pre_replay_main = _git_out(["rev-parse", MAIN], root)
        pre_replay_spawn_calls = len(spawn_calls)
        res_replay = eng.tick()
        post_replay_manifest_bytes = open(tron_ctx.state, "rb").read()
        post_replay_main = _git_out(["rev-parse", MAIN], root)
        ok("M12 (IDEMPOTENT RE-TICK KILLER — must be GREEN): a further "
           "eng.tick() call AFTER session-end is a true no-op — same session-end "
           "marker back, nothing spawned, nothing mutated (manifest bytes AND "
           "real git both byte-identical before/after)",
           res_replay.get("session_end") == final_manifest.get("session")
           and res_replay["spawned"] == [] and res_replay["outcomes"] == {}
           and len(spawn_calls) == pre_replay_spawn_calls
           and post_replay_manifest_bytes == pre_replay_manifest_bytes
           and post_replay_main == pre_replay_main,
           f"replay_result={res_replay} spawn_calls_before={pre_replay_spawn_calls} "
           f"spawn_calls_after={len(spawn_calls)}")

        # ══ FINAL ══
        total_engineer_spawns = len({c["worker_id"] for c in spawn_calls if c["worker_id"].startswith("engineer-")})
        ok("FINAL (TERMINAL — must be GREEN): bootup -> a real 3-block + real-"
           "dependency + real cadence-review + real log-review-adhoc drive -> a "
           "clean, idempotent SESSION-END — the WHOLE engine, entirely through "
           "Engine, with a REAL roles.yaml resolving every real spawn's role/model",
           session_ended_tick is not None
           and bool((final_manifest.get("session") or {}).get("ended_at"))
           and total_engineer_spawns == len(all_block_ids)
           and all(final_gates.get(b, {}).get("stage") == gate.STAGE_CLOSED for b in all_block_ids)
           and len(reviewer_ids) >= 1,
           f"total_engineer_spawns={total_engineer_spawns} all_block_ids={all_block_ids} "
           f"session={final_manifest.get('session')}")
    finally:
        jobs.spawn_runner = real_spawn_runner
        jobs.release = real_release

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.engine_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"tron instance dir (real engine.ctx.Ctx)={inst}")
    print(f"manifest={tron_ctx.state}")
    print(f"BLOCKS={ORDER} (B depends_on A; C has none) worker_count=1 cadence={{'{CADENCE_TYPE}': {CADENCE_THRESHOLD}}}")
    print(f"ticks used={ticks_used} (cap={MAX_TICKS}) session_ended_tick={session_ended_tick}")
    print(f"spawn_tick={hist.spawn_tick}")
    print(f"done_tick (record_landed observed)={hist.done_tick}")
    print(f"close_tick={hist.close_tick}")
    print(f"reconciled_reported={hist.reconciled_reported}")
    print(f"reviewer_ids={reviewer_ids} hold={hist.review_hold_tick} release={hist.review_release_tick}")
    print(f"adhoc_blocks={adhoc_blocks} adhoc_landed_tick={hist.adhoc_landed_tick}")
    print(f"spawn_calls (worker_id/model)={[(c['worker_id'], c['model']) for c in spawn_calls]}")
    print(f"session (durable manifest field)={final_manifest.get('session')}")
    print(f"idempotent re-tick result={res_replay}")
    return 0 if passed == len(_results) else 1


def _raises(exc_type, fn):
    try:
        fn()
    except exc_type:
        return True
    except Exception:
        return False
    return False


if __name__ == "__main__":
    sys.exit(main())
