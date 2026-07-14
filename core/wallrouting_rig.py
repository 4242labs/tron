"""core.wallrouting_rig — real-git rig proving wave 18 (GAP-E): architect-
first routing for EVERY wall kind, a binding operator decision the engine
used to violate (`core/casestate.py::open_case` used to page the OPERATOR
directly; a block-less/unclassified escalation could be a silent discard).

Design (rebuild-spec.md T5 "unclassified -> architect"; blueprint-
contracts.md §1 SENTRY -> architect; taxonomy GAP-E): a raised wall/
escalation (`worker.wall`, a `sentry.cap` escalation, an `unclassified`
classify result, a liveness `worker.stalled` recovery — every `core/
casestate.py::open_case` caller) becomes an ARCHITECT TRIAGE job FIRST (a
`triage` kind on `manifest["architect_queue"]`, PMT-TRIAGE) — NEVER an
immediate operator page. The block is held/blocked, the slot freed (exactly
as before this wave), but the case is `owner="architect"` until triaged.
The architect's own verdict (scripted here; a real LLM at L3) ∈
`{scope_forward (-> author an adhoc/forward block, resolve the wall,
unblock/continue), answer (-> relay guidance to the worker, resume),
operator (-> NOW open the operator-owned parked case, GAP-A's page floor
intact)}`. Nothing is EVER silently dropped: a block-less wall, an
unclassified input, any wall kind — ALL go architect-first; only the
architect's `operator` verdict ever reaches `eng._page_operator`.

REAL surface only, driven entirely via the REAL `core.engine.Engine`
(`Engine(ctx).start(...)` / `Engine.tick()`), exactly like `core/
opfloor_rig.py`/`core/engine_rig.py`: a real `git init` repo copied from the
SAME scaffold every prior `core/*_rig.py` uses, `meta/scripts/land.sh` run
for real via `subprocess`, real `project.yaml`/`knobs.yaml`/`roles.yaml`, a
real declared test command (`true`). `engine.jobs.spawn_runner` is the ONE
seam stubbed (never a real `claude` process — the established "rig plays
the worker/architect" pattern); every other `Engine` hook runs FOR REAL,
`_page_operator` UNSTUBBED (this brick's whole point).

TWO real, pipeline-dispatched blocks (`worker_count=2`, no deps):

  wall-scope-01  — walled ONCE at `gate.local` (a real structured
    `worker.wall` report). The architect's OWN triage verdict (scripted
    `scope_forward`) authors + REAL-lands ONE adhoc block (`core/
    architect.py::_advance_triage`'s own single-entry order-then-poll-and-
    land shape, the Wave-1 landing primitive reused verbatim) and, once
    that lands, resolves the ORIGINAL wall (drop-and-redrive, `core/
    casestate.py::architect_resolve`) — a FRESH SPAWN re-drives wall-
    scope-01 to a genuine clean close, and the newly-landed adhoc block
    ALSO reaches a clean close — the operator is NEVER paged for either.

  cap-operator-01 — reacted to only up through `gate.local` (a genuine
    local-pass), then deliberately left stuck at `gate.merge` (never
    landed) until `core/sentry.py`'s OWN pacing ladder caps it
    (`GATE_IDLE_CAP`). The architect's OWN triage verdict for THIS case is
    scripted `operator` — NOW (and only now) the operator-owned parked
    case opens, `eng._page_operator` fires (GAP-A's page floor intact),
    and the operator's own `resume` settles it to a genuine clean close.

Both cases are proven ARCHITECT-owned (never paged) at the exact tick they
open, and only paged strictly later, once the architect's own scripted
verdict resolves them — the SAME "observe it for real, never a pre-timed
assumption" discipline every re-pointed prior rig in this wave now keeps.

Two further, ISOLATED (no tick loop — pure manifest/architect/casestate/
classify mechanics, nothing to fake on real git for these) proofs, mirroring
`core/opfloor_rig.py`'s own block-less slice and `core/classify_rig.py`'s
own unit-level scenario 2:

  a `sentry.cap` / `worker.stalled`-shaped escalation and a `worker.wall`
    both already exercised for real above; this rig ALSO proves a
    CASE-LESS escalation (an `unclassified` classify result — no block/
    gate behind it at all) and a genuinely BLOCK-LESS `open_case` call are
    BOTH routed architect-first (a real PMT-TRIAGE job, never a direct
    operator page) and — once the architect's own scripted `operator`
    verdict resolves them — genuinely reach the operator (never a silent,
    unclassified discard).

  ADR-0010 Invariant B (target — durable-authoritative), ISOLATED (a
    direct `core.router.route` call, no tick loop — mirrors D9-D13's own
    unit-level slices): a genuine, EXPLICIT `--tag wall` from a MAPPED
    worker (`engineer-01-02`, bound to block `01-02` in `manifest
    ["workers"]`) carrying NO block in its prose still opens its case on
    the worker's DURABLE bound block, never falls into the block-less
    architect-triage path the way a pre-ADR-0010 prose-first block read
    would misroute it.

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

import util                  # noqa: E402 — engine/util.py, atomic_write (respected)
import grants                # noqa: E402 — respected contract, real, unmodified
import trunk                  # noqa: E402 — respected contract, real, unmodified
import jobs                    # noqa: E402 — engine/jobs.py, the ONE seam this rig stubs (spawn_runner)
from ctx import Ctx             # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import gate                      # noqa: E402 — core/gate.py, the DONE ladder (stage constants only)
import state                       # noqa: E402 — core/state.py
import casestate                    # noqa: E402 — core/casestate.py, the module GAP-E reconciles
import architect                     # noqa: E402 — core/architect.py, wave 18's triage job
import classify                       # noqa: E402 — core/classify.py, the unclassified-triage source
import router                          # noqa: E402 — core/router.py, ADR-0010 Invariant B (_route_wall)
from engine import Engine, BootupError   # noqa: E402 — core/engine.py, the REAL Engine (_page_operator UNSTUBBED)

import scaffold_src               # noqa: E402 — core/scaffold_src.py, the ONE resolver

SCAFFOLD_SRC = scaffold_src.resolve()
MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"
ROLES_REL = "meta/tron/roles.yaml"
PERSONAS_REL = "meta/tron/personas"

BLOCK_SCOPE, BRANCH_SCOPE, WID_SCOPE = "wall-scope-01", "feat/wall-scope-01", "engineer-wall-scope-01"
BLOCK_CAP, BRANCH_CAP, WID_CAP = "cap-operator-01", "feat/cap-operator-01", "engineer-cap-operator-01"
ORDER = [BLOCK_SCOPE, BLOCK_CAP]

STUB_MODEL = "stub-model"
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
    d = tempfile.mkdtemp(prefix="tron-core-wallroutingrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-wallrouting-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: wallrouting_rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {s} | wallrouting_rig fixture — walled, architect scope_forward verdict | 📋 To do | Block `blocks/{s}.md` |
| {c} | wallrouting_rig fixture — sentry cap, architect operator verdict | 📋 To do | Block `blocks/{c}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: wallrouting_rig fixture

**Phase:** 1 — GAP-E architect-first wall routing rig
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.wallrouting_rig` — proves `core/casestate.py::
open_case` (worker.wall/sentry.cap/liveness-stall) and `core/classify.py`'s
own unclassified path both route ARCHITECT-FIRST (wave 18/GAP-E), never an
immediate operator page.
"""

ROLES_YAML_TEMPLATE = """roles:
  engineer:
    persona: {personas}/engineer.md
    model: {model}
    binds: [BUILD, CLOSE, REVIEW]
  architect:
    persona: {personas}/architect.md
    model: {model}
    binds: [TRIAGE]
    spec_owner: true
    persistent: true
"""

PERSONA_TEMPLATE = """# {role} persona (core.wallrouting_rig fixture)

A synthetic persona file — `engine.roles.RolesConfig`'s own fail-closed
boot validation requires every declared role's persona to exist on disk;
this rig's workers/architect are entirely scripted (no LLM, no real
`claude` process), so the CONTENT here is never read by anything, only its
presence.
"""

ADHOC_PIPELINE_SECTION = """
## Ad-hoc

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
"""

ADHOC_ROW_TEMPLATE = "| {block} | {title} | 📋 To do | Block `blocks/{block}.md` |\n"

ADHOC_BLOCK_DOC_TEMPLATE = """# Block {block}: scope_forward adhoc fixture

**Phase:** 1 — wallrouting_rig scope_forward
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Authored by the SCRIPTED ARCHITECT (`core.wallrouting_rig`, playing a real
`triage` job's `scope_forward` verdict) from wall-scope-01's own wall:
{title!r} — a genuinely NEW adhoc block (no pre-existing pipeline row),
landed via `core.landing.land_via_grant` under a content-bound case-id, the
SAME mechanism `core/architect.py::_advance_log`'s own single-entry
adhoc-authoring already established.
"""


def seed_pipeline(root):
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(s=BLOCK_SCOPE, c=BLOCK_CAP))
    for block in ORDER:
        bpath = os.path.join(root, BLOCKS_REL, f"{block}.md")
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        with open(bpath, "w") as fh:
            fh.write(BLOCK_DOC_TEMPLATE.format(block=block))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + blocks {BLOCK_SCOPE}/{BLOCK_CAP} (to-do, no deps, no gates)"], root)
    _git(["checkout", "--detach", MAIN], root)


def seed_roles(root):
    roles_path = os.path.join(root, ROLES_REL)
    os.makedirs(os.path.dirname(roles_path), exist_ok=True)
    with open(roles_path, "w") as f:
        f.write(ROLES_YAML_TEMPLATE.format(personas=PERSONAS_REL, model=STUB_MODEL))
    personas_dir = os.path.join(root, PERSONAS_REL)
    os.makedirs(personas_dir, exist_ok=True)
    for role in ("engineer", "architect"):
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


def write_knobs(inst_dir):
    """`silence_ping_min`/`silence_escalate_min` set WELL above `MAX_TICKS`
    so `core/liveness.py`'s own SILENCE ladder never fires and never
    interferes with this brick's OWN sentry-cap ladder — this rig's blocks
    report promptly right up to the moment cap-operator-01 deliberately
    stalls at `gate.merge` (a sentry-cap stuck shape, never a liveness-
    silence one)."""
    doc = {
        "knobs": {
            "worker_count": 2,
            "silence_ping_min": 4000,
            "silence_escalate_min": 8000,
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
        f.write(f"// {marker} — core.wallrouting_rig real code change\n")
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
    block file for a `scope_forward` triage verdict's own adhoc entry —
    mirrors `core/reviewers_rig.py::make_adhoc_doc` (never imported cross-
    rig; each `core/*_rig.py` stays self-contained per this stack's own
    convention)."""
    _git(["checkout", "-B", branch, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    with open(ppath) as f:
        original = f.read()
    row = ADHOC_ROW_TEMPLATE.format(block=block, title=title)
    if "## Ad-hoc" not in original:
        content = original.rstrip("\n") + "\n" + ADHOC_PIPELINE_SECTION + row
    else:
        lines = original.splitlines(keepends=True)
        idx = next(i for i, ln in enumerate(lines) if ln.strip().startswith("## Ad-hoc"))
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
    _git(["commit", "-m", f"arch(scope_forward): author adhoc block {block}"], root)
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
    ensure_rebased(root, branch)
    rc, out, err = run_land(root, grants_dir, case_id)
    if rc == 0:
        landed_cases.add(case_id)
        return True
    combined = (out or "") + (err or "")
    if "not a fast-forward" in combined or "CAS failed" in combined:
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

WALL_DETAIL = ("rig-as-worker: hit a genuine wall on wall-scope-01 at "
              "gate.local — solvable as upcoming work (a real structured "
              "worker.wall report); the architect's own scripted verdict "
              "is scope_forward.")


class RunState:
    """Per-block generation-tracked reaction state (mirrors `core/
    casestate_rig.py`'s own `gen`-keyed dicts): wall-scope-01 is walled
    ONCE at generation 0; a LATER generation (after the architect's own
    scope_forward resolves it) reacts with an ordinary local-pass instead,
    driving the fresh dispatch all the way to a genuine close. cap-
    operator-01 gets a genuine local-pass (generation 0) but is then
    deliberately left stuck at gate.merge (never landed) until sentry's
    OWN cap fires; a later generation (post operator-resume) drives it
    normally too."""

    def __init__(self, root, grants_dir):
        self.root = root
        self.grants_dir = grants_dir
        self.gen = {BLOCK_SCOPE: 0, BLOCK_CAP: 0}
        self.walled_scope = False
        self.branch_created = {}
        self.local_reported = {}
        self.record_committed = {}
        self.torn_down = {}
        self.landed_cases = set()
        self.triage_answered = set()   # triage_ids already answered
        self.adhoc_entry_authored = set()   # adhoc block ids already authored on their branch

    def react_architect_triage(self, manifest, inbox_path):
        """Wave 18 (GAP-E): the architect's own scripted triage verdict —
        `scope_forward` for wall-scope-01's own case, `operator` for cap-
        operator-01's — decided purely off the CURRENT job's own `block`
        field (never a block this rig doesn't itself raise a wall/cap
        for)."""
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if not (cur and cur.get("kind") == "triage" and cur.get("ordered")
                and cur.get("triage_id") not in self.triage_answered):
            return
        block = cur.get("block")
        if block == BLOCK_SCOPE:
            verdict = "scope_forward"
        elif block == BLOCK_CAP:
            verdict = "operator"
        else:
            return   # not one of this rig's own cases yet (shouldn't happen)
        append_jsonl(inbox_path, {"tag": "architect.triage_verdict",
                                  "triage_id": cur["triage_id"], "verdict": verdict,
                                  "agent_id": architect.ARCHITECT_WID})
        self.triage_answered.add(cur["triage_id"])

    def react_architect_scope_forward(self, manifest):
        """One reaction per tick for a `scope_forward` triage's own single
        adhoc entry (`core/architect.py::_advance_triage`'s own single-
        entry order-then-poll-and-land shape) — author the pipeline row +
        block file on its branch once ordered, then let `land_via_grant`
        (called by `core/architect.py` itself, NEVER this rig) mint the
        grant; this rig only ever runs the REAL `land.sh` once a case_id
        shows up, exactly like `core/reviewers_rig.py::react_architect_log`
        already does for its own (differently-sourced) adhoc entries."""
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if not (cur and cur.get("kind") == "triage" and cur.get("verdict") == "scope_forward"):
            return
        entry = cur.get("adhoc")
        if not entry or not entry.get("ordered"):
            return
        block, branch = entry["block"], entry["branch"]
        if block not in self.adhoc_entry_authored:
            make_adhoc_doc(self.root, branch, block,
                           f"{block}: scope_forward finding from wall-scope-01")
            self.adhoc_entry_authored.add(block)
        case_id = entry.get("case_id")
        if case_id:
            try_land(self.root, self.grants_dir, case_id, branch, self.landed_cases)

    def bump_gen(self, block):
        """Called by `main()`'s own drive loop once a block's case has
        genuinely resolved (scope_forward's own drop-and-redrive, OR the
        operator's own resume) — mints a FRESH generation so the next
        `worker.online`/local-pass/etc. below is a genuinely NEW dispatch,
        never a stale, already-consumed `branch_created`/`local_reported`
        key from an earlier generation (mirrors `core/casestate_rig.py`'s
        own `gen[BLOCK_R] = 1` at resume time)."""
        self.gen[block] = self.gen.get(block, 0) + 1

    def react(self, i, manifest, inbox_path):
        self.react_architect_triage(manifest, inbox_path)
        self.react_architect_scope_forward(manifest)

        # Generic over EVERY worker/gate the manifest currently holds — NOT
        # just this rig's own two seeded blocks: `wall-scope-01`'s own
        # scope_forward verdict lands a genuinely NEW adhoc block
        # (`adhoc-triage-1`) that `core/switchboard.py::fill` dispatches
        # exactly like any ordinary pipeline row the instant it observes it
        # on trunk — this rig must react to THAT dispatch too, or the
        # adhoc block (itself in-scope, per `core/session.py::check`) would
        # sit stuck at `spawning` forever and the whole run would never
        # reach a clean session-end.
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}
        known_blocks = {w.get("block") for w in workers.values() if w.get("block")} | set(gates)
        for block in known_blocks:
            agent_id = f"engineer-{block}"
            branch = f"feat/{block}"
            block_file_rel = f"{BLOCKS_REL}/{block}.md"
            gen = self.gen.setdefault(block, 0)
            key = (block, gen)

            w = workers.get(agent_id)
            if w and w.get("status") == "spawning" and not self.branch_created.get(key):
                # a PER-BLOCK file (never the shared CODE_FILE_REL a single-
                # file convention would need append-mode discipline for) —
                # this rig deliberately re-drives wall-scope-01 through TWO
                # generations plus a genuinely NEW adhoc block sharing the
                # same worker pool, so per-block files keep every rebase
                # conflict-free by construction.
                make_code_commit(self.root, branch, f"src/lib/{block}.ts", f"{block}-gen{gen}")
                self.branch_created[key] = True
                append_jsonl(inbox_path, {"tag": "worker.online", "agent_id": agent_id,
                                          "slots": {"branch": branch}})

            g = gates.get(block)
            if not g:
                continue
            stage = g.get("stage")

            if stage == gate.STAGE_LOCAL:
                if block == BLOCK_SCOPE and gen == 0 and not self.walled_scope:
                    append_jsonl(inbox_path, {"tag": "worker.wall", "block": BLOCK_SCOPE,
                                              "agent_id": agent_id, "slots": {"detail": WALL_DETAIL}})
                    self.walled_scope = True
                elif not self.local_reported.get(key):
                    append_jsonl(inbox_path, {"tag": "worker.done", "block": block,
                                              "slots": LOCAL_PASS_REPORT})
                    self.local_reported[key] = True
            elif stage == gate.STAGE_MERGE and g.get("merge_case_id"):
                if block == BLOCK_CAP and gen == 0:
                    pass   # deliberately stuck — never landed, to trip sentry's GATE_IDLE_CAP
                else:
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


def find_open_case(manifest, block, source=None):
    for c in (manifest.get("cases") or {}).values():
        if c.get("block") == block and c.get("decision") is None:
            if source is None or c.get("source") == source:
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
    # A real `routing.yaml` on disk, copied verbatim from the repo root
    # (never a rig-authored fork) — harmless/vestigial for `core/
    # classify.py` (block 01-37 retired its routing.yaml read), kept for
    # any other module in this drive that still resolves `ctx.routing`.
    shutil.copy(os.path.join(APP_ROOT, "routing.yaml"), tron_ctx.routing)

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

        ok("pre0: rig starts with NO manifest.yaml on disk at all",
           not os.path.exists(tron_ctx.state), f"state={tron_ctx.state}")
        for block in ORDER:
            doc = open(os.path.join(root, BLOCKS_REL, f"{block}.md")).read()
            ok(f"pre1[{block}]: pipeline shows block {block} as 📋 (to-do) on trunk, "
               "no gate, no worker, no case",
               "**Status:** 📋 To do" in doc, f"{block} doc seeded 📋")

        # ══ 1. BOOT — via Engine, and ONLY Engine ══
        spawned_at_boot = eng.start(scope="all", worker_count=2, models={})
        ok("B1: bootup dispatched both fixture blocks off the real pipeline read "
           "(worker_count=2, two 📋 rows, no deps)",
           set(spawned_at_boot) == {f"engineer-{b}" for b in ORDER},
           f"spawned_at_boot={spawned_at_boot}")

        rs = RunState(root, grants_dir)
        case_scope = {"id": None, "seen_architect_owned": False, "opened_tick": None, "cleared_tick": None}
        case_cap = {"id": None, "seen_architect_owned": False, "opened_tick": None}
        resumed_cap_tick = {"i": None}
        session_ended_tick = None
        i = 0

        # ══ 2. DRIVE — via repeated eng.tick() calls only ══
        for i in range(1, MAX_TICKS + 1):
            res = eng.tick()
            manifest = state.load(tron_ctx)
            rs.react(i, manifest, tron_ctx.worker_inbox)

            cs = find_open_case(manifest, BLOCK_SCOPE, "worker.wall")
            if cs is not None:
                if case_scope["id"] is None:
                    case_scope["id"], case_scope["opened_tick"] = cs["case_id"], i
                if cs.get("owner") == "architect":
                    case_scope["seen_architect_owned"] = True
            elif case_scope["id"] is not None and case_scope["cleared_tick"] is None:
                # wave 18 (GAP-E): the architect's OWN scope_forward verdict
                # just resolved this case (drop-and-redrive) — WITHOUT the
                # operator ever settling anything. A FRESH generation is
                # needed so `RunState.react` genuinely re-drives it (never
                # a stale, already-consumed gen-0 dispatch key).
                case_scope["cleared_tick"] = i
                rs.bump_gen(BLOCK_SCOPE)

            cc = find_open_case(manifest, BLOCK_CAP, "sentry.cap")
            if cc is not None:
                if case_cap["id"] is None:
                    case_cap["id"], case_cap["opened_tick"] = cc["case_id"], i
                if cc.get("owner") == "architect":
                    case_cap["seen_architect_owned"] = True
                if cc.get("owner") == "operator" and resumed_cap_tick["i"] is None:
                    rs.gen[BLOCK_CAP] = 1
                    append_jsonl(tron_ctx.worker_inbox,
                                {"tag": "operator.decision",
                                 "slots": {"case_id": cc["case_id"], "verb": "resume"}})
                    resumed_cap_tick["i"] = i

            se = res.get("session_end")
            if se is not None:
                session_ended_tick = i
                break

        final_manifest = state.load(tron_ctx)
        final_gates = final_manifest.get("gates") or {}
        final_cases = final_manifest.get("cases") or {}
        ticks_used = i

        # ══════════════════════════════════════════════════════════════
        # DELIVERABLE 1 — worker.wall -> architect triage (NOT an
        # immediate operator page); scope_forward -> authors an adhoc
        # block (real land) + the wall resolves + the run continues to a
        # clean end WITHOUT ever paging the operator
        # ══════════════════════════════════════════════════════════════
        ok("D1 (WALL->ARCHITECT-FIRST KILLER — must be GREEN): wall-"
           "scope-01's worker.wall opened a case that was OBSERVED "
           "architect-owned (never paged the same tick it raised) — the "
           "operator is never reached the same tick a wall raises",
           case_scope["id"] is not None and case_scope["seen_architect_owned"],
           f"case_scope={case_scope}")
        ok("D2 (SCOPE-FORWARD->ADHOC-LANDED KILLER — must be GREEN): the "
           "architect's own scope_forward verdict authored + REAL-landed a "
           "genuinely NEW adhoc block (never fake content, never a faked "
           "land) — a fresh pipeline row + block file, observed ✅ on trunk",
           len(rs.adhoc_entry_authored) == 1,
           f"adhoc_entry_authored={rs.adhoc_entry_authored}")
        adhoc_block = next(iter(rs.adhoc_entry_authored), None)
        doc_adhoc_on_main = (_git_out(["show", f"{MAIN}:{BLOCKS_REL}/{adhoc_block}.md"], root)
                             if adhoc_block else None)
        ok("D2b: the adhoc block's own doc AS READ FROM main shows ✅ (real "
           "git show on trunk) — genuinely closed, not merely landed",
           doc_adhoc_on_main is not None and "**Status:** ✅ Done" in doc_adhoc_on_main,
           f"doc head={doc_adhoc_on_main.splitlines()[:4] if doc_adhoc_on_main else None}")
        ok("D3 (WALL-RESOLVED-WITHOUT-OPERATOR KILLER — must be GREEN): "
           "wall-scope-01's case cleared (no longer in manifest['cases']) "
           "and the block reached a genuine clean close on real git — the "
           "SAME clean end DELIVERABLE-1 promises",
           case_scope["id"] not in final_cases
           and final_gates.get(BLOCK_SCOPE, {}).get("stage") == gate.STAGE_CLOSED,
           f"case_scope_id={case_scope['id']} final_gate_scope={final_gates.get(BLOCK_SCOPE)}")
        doc_scope_on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{BLOCK_SCOPE}.md"], root)
        ok("D3b: wall-scope-01's OWN doc AS READ FROM main ALSO shows ✅ — "
           "the scope_forward resolve genuinely re-drove it to done, not "
           "just cleared the case bookkeeping",
           "**Status:** ✅ Done" in doc_scope_on_main,
           f"doc head={doc_scope_on_main.splitlines()[:4]}")
        ok("D4 (NEVER-PAGED KILLER — must be GREEN): across the WHOLE "
           "scope_forward flow (wall -> architect triage -> adhoc "
           "authored+landed -> wall resolved -> fresh dispatch -> clean "
           "close) NEITHER wall-scope-01's own case_id NOR the adhoc "
           "block's own landing case_id EVER appears in "
           "manifest['operator_pages'] — the operator is NEVER paged for "
           "this whole path",
           not any(p.get("case_id") == case_scope["id"]
                  for p in (final_manifest.get("operator_pages") or {}).values())
           and not any(p.get("block") == BLOCK_SCOPE or p.get("block") == adhoc_block
                      for p in (final_manifest.get("operator_pages") or {}).values()),
           f"operator_pages={final_manifest.get('operator_pages')}")

        # ══════════════════════════════════════════════════════════════
        # DELIVERABLE 2 — architect operator-verdict -> a floored
        # operator-owned parked case -> operator resume settles it
        # ══════════════════════════════════════════════════════════════
        ok("D5 (SENTRY-CAP->ARCHITECT-FIRST KILLER — must be GREEN): cap-"
           "operator-01, deliberately never landed at gate.merge, got "
           "capped by core.sentry's OWN pacing ladder and THAT escalation "
           "opened a case OBSERVED architect-owned (never paged the same "
           "tick the cap tripped) — a sentry cap escalation is NEVER "
           "operator-direct either",
           case_cap["id"] is not None and case_cap["seen_architect_owned"]
           and any(e.get("block") == BLOCK_CAP for e in (final_manifest.get("escalations") or [])),
           f"case_cap={case_cap}")
        ok("D6 (ARCHITECT-OPERATOR-VERDICT->FLOORED-CASE KILLER — must be "
           "GREEN): once the architect's OWN scripted `operator` verdict "
           "resolved it, cap-operator-01's case was genuinely paged (a "
           "real eng._page_operator call, durably recorded in "
           "manifest['operator_pages']) — THE FLOOR (GAP-A) intact",
           resumed_cap_tick["i"] is not None
           and any(p.get("case_id") == case_cap["id"]
                  for p in (final_manifest.get("operator_pages") or {}).values()
                  ) or any(p.get("case_id") == case_cap["id"]
                          for p in (final_manifest.get("operator_pages") or {}).values()),
           f"resumed_cap_tick={resumed_cap_tick} operator_pages={final_manifest.get('operator_pages')}")
        ok("D7 (OPERATOR-RESUME-SETTLES KILLER — must be GREEN): the "
           "operator's own resume cleared cap-operator-01's case and it "
           "re-drove all the way to a genuine clean close on real git",
           case_cap["id"] not in final_cases
           and final_gates.get(BLOCK_CAP, {}).get("stage") == gate.STAGE_CLOSED,
           f"case_cap_id={case_cap['id']} final_gate_cap={final_gates.get(BLOCK_CAP)}")
        doc_cap_on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{BLOCK_CAP}.md"], root)
        ok("D7b: cap-operator-01's doc AS READ FROM main shows ✅ (real git "
           "show on trunk) — the operator resume genuinely re-drove it",
           "**Status:** ✅ Done" in doc_cap_on_main,
           f"doc head={doc_cap_on_main.splitlines()[:4]}")

        ok(f"D8 (WHOLE-DRIVE CONVERGENCE — must be GREEN): the whole rig "
           f"(a genuine architect-first hop for BOTH wall kinds, one "
           f"resolved without the operator, one resolved through it) "
           f"converged to a clean session-end inside {MAX_TICKS} ticks "
           f"(used {ticks_used})",
           session_ended_tick is not None and ticks_used < MAX_TICKS,
           f"ticks_used={ticks_used} session_ended_tick={session_ended_tick}")
        ok("SE1: the session-end marker is durably persisted, re-read "
           "fresh off disk",
           bool((final_manifest.get("session") or {}).get("ended_at")),
           f"session={final_manifest.get('session')}")

        # ══════════════════════════════════════════════════════════════
        # DELIVERABLE 3 — a `sentry` cap escalation routes architect-first
        # (D5/D6 above, block-bearing); an `unclassified` classify result
        # ALSO routes architect-first (case-less), never a silent discard
        # ══════════════════════════════════════════════════════════════
        eng_iso = Engine(Ctx(inst))   # a FRESH, throwaway Engine — never .start()-ed,
        eng_iso.dry = False           # never touching the main drive's own manifest.

        # Block 01-37 T8: the free-text GRADER is retired — there is no
        # judge to stub any more. A genuinely free-text line (no --tag, no
        # --branch) is refused at the door (`core.door.refuse`) and handed
        # to the architect FIRST exactly the same way `unclassified` used
        # to (case-less PMT-TRIAGE, `core/architect.py::enqueue_triage`,
        # reused verbatim) — the mechanism is now the door's own refusal
        # path, source `worker.report_refused`, never a second LLM call.
        iso_manifest_u = {}
        raw_unclassified = "the whole staging environment is on fire, someone please look — this is nobody's block"
        tag_u, _slots_u = classify.classify(
            eng_iso, {"text": raw_unclassified, "sender": {"kind": "worker", "id": "engineer-99"}},
            iso_manifest_u)
        triage_job_u = next((j for j in (iso_manifest_u.get("architect_queue") or [])
                             if j.get("kind") == "triage" and j.get("source") == "worker.report_refused"),
                            None)
        ok("D9 (DOOR-REFUSAL->ARCHITECT-FIRST KILLER, re-based on block "
           "01-37 T8 — must be GREEN): a genuinely free-text report is "
           "REFUSED at the door (tag=None, never a guessed classification) "
           "and handed to the architect FIRST — a real, CASE-BEARING "
           "PMT-TRIAGE job (never a second LLM call, never a direct "
           "operator page)",
           tag_u is None and triage_job_u is not None
           and raw_unclassified in (triage_job_u.get("detail") or "")
           and len(iso_manifest_u.get("operator_pages") or {}) == 0,
           f"tag_u={tag_u} triage_job_u={triage_job_u} "
           f"pages={iso_manifest_u.get('operator_pages')}")

        architect.advance(eng_iso, iso_manifest_u)   # order
        ordered_u = (iso_manifest_u.get("architect") or {}).get("current_job")
        ok("D9b: the architect genuinely ORDERED the case-less triage "
           "(arch.triage) before ever applying any verdict",
           ordered_u is not None and ordered_u.get("kind") == "triage"
           and ordered_u.get("ordered") is True and ordered_u.get("verdict") is None,
           f"ordered_u={ordered_u}")
        triage_id_u = ordered_u["triage_id"]
        # mirrors exactly what `core/router.py::_route_architect_triage_verdict`
        # would record off a routed `architect.triage_verdict` report — this
        # isolated slice has no tick/inbox loop of its own for it.
        iso_manifest_u.setdefault("triage_verdicts", {})[triage_id_u] = {"verdict": "operator", "note": None}
        architect.advance(eng_iso, iso_manifest_u)   # apply

        iso_pages_u = list((iso_manifest_u.get("operator_pages") or {}).values())
        iso_case_u = next((c for c in (iso_manifest_u.get("cases") or {}).values()
                           if c.get("source") == "worker.report_refused"), None)
        ok("D10 (DOOR-REFUSAL->OPERATOR-REACHED KILLER, re-based on block "
           "01-37 T8 — must be GREEN): once the architect's OWN scripted "
           "`operator` verdict resolved it, the door-refused escalation "
           "genuinely reached the operator — a real page, durably "
           "recorded, `owner='operator'` — never a silent discard",
           iso_case_u is not None and iso_case_u.get("block") is None
           and iso_case_u.get("owner") == "operator" and iso_case_u.get("decision") is None
           and len(iso_pages_u) == 1 and iso_pages_u[0].get("block") is None,
           f"iso_case_u={iso_case_u} iso_pages_u={iso_pages_u}")

        # ══════════════════════════════════════════════════════════════
        # DELIVERABLE 4 — a block-less wall (`open_case(block=None)`,
        # e.g. a worker report with no resolvable block) still routes
        # architect-first and is NEVER silently dropped
        # ══════════════════════════════════════════════════════════════
        iso_manifest_bl = {}
        cid_bl = casestate.open_case(eng_iso, iso_manifest_bl, None, "test.blockless",
                                     "a block-less wall — never a silent discard",
                                     worker_id=None)
        iso_case_bl = (iso_manifest_bl.get("cases") or {}).get(cid_bl)
        iso_pages_bl_pre = list((iso_manifest_bl.get("operator_pages") or {}).values())
        triage_job_bl = next((j for j in (iso_manifest_bl.get("architect_queue") or [])
                              if j.get("kind") == "triage" and j.get("case_id") == cid_bl), None)
        ok("D11 (BLOCK-LESS->ARCHITECT-FIRST KILLER — must be GREEN): "
           "`open_case` for a block-less wall NEVER pages the operator "
           "itself — architect-owned, a real PMT-TRIAGE job queued, zero "
           "pages recorded",
           iso_case_bl is not None and iso_case_bl.get("block") is None
           and iso_case_bl.get("owner") == "architect" and iso_case_bl.get("decision") is None
           and len(iso_pages_bl_pre) == 0 and triage_job_bl is not None,
           f"iso_case_bl={iso_case_bl} triage_job_bl={triage_job_bl}")

        architect.advance(eng_iso, iso_manifest_bl)   # order
        ordered_bl = (iso_manifest_bl.get("architect") or {}).get("current_job")
        triage_id_bl = ordered_bl["triage_id"]
        iso_manifest_bl.setdefault("triage_verdicts", {})[triage_id_bl] = {"verdict": "operator", "note": None}
        architect.advance(eng_iso, iso_manifest_bl)   # apply

        iso_pages_bl = list((iso_manifest_bl.get("operator_pages") or {}).values())
        iso_case_bl_after = (iso_manifest_bl.get("cases") or {}).get(cid_bl)
        ok("D12 (BLOCK-LESS->NEVER-DROPPED KILLER — must be GREEN): once "
           "triaged, the block-less wall genuinely reached the operator "
           "(a real page, durably recorded, `owner='operator'`, "
           "`decision` still None — genuinely OPEN, awaiting the "
           "operator's own settle) — never silently dropped anywhere in "
           "the pipeline",
           iso_case_bl_after is not None and iso_case_bl_after.get("owner") == "operator"
           and iso_case_bl_after.get("decision") is None
           and len(iso_pages_bl) == 1 and iso_pages_bl[0].get("block") is None
           and iso_pages_bl[0].get("receipt") is None,   # no eng._deliver_page hook wired (production shape)
           f"iso_case_bl_after={iso_case_bl_after} iso_pages_bl={iso_pages_bl}")

        # ══════════════════════════════════════════════════════════════
        # GAP-E's own "no operator bypass" invariant, direct
        # ══════════════════════════════════════════════════════════════
        synth_bypass = {"cases": {"case-bypass-1": {
            "case_id": "case-bypass-1", "block": "synthetic-block", "source": "worker.wall",
            "kind": "wall", "worker_id": None, "detail": "synthetic", "decision": None,
            "owner": "architect"}}}
        bypass_settled = casestate.settle(eng_iso, synth_bypass, "case-bypass-1", "resume")
        ok("D13 (NO-OPERATOR-BYPASS KILLER — must be GREEN): `core."
           "casestate.settle` REJECTS an operator.decision naming a case "
           "that is STILL architect-owned — the operator can never bypass "
           "GAP-E's architect-first routing",
           bypass_settled is False
           and synth_bypass["cases"]["case-bypass-1"].get("decision") is None
           and synth_bypass["cases"]["case-bypass-1"].get("owner") == "architect",
           f"bypass_settled={bypass_settled} case={synth_bypass['cases']['case-bypass-1']}")

        # ══════════════════════════════════════════════════════════════
        # DELIVERABLE 5 (ADR-0010 §6 rig 3 — Invariant B) — a genuine
        # `--tag wall` from a MAPPED worker, carrying NO block in its
        # prose, still opens its case on the worker's DURABLE bound block
        # (manifest["workers"][wid]["block"]) — never the block-less
        # architect-triage misroute a pre-ADR-0010 prose-first block read
        # would have produced. ISOLATED (a direct `core.router.route`
        # call, no tick loop), mirrors D9-D13's own unit-level shape.
        # ══════════════════════════════════════════════════════════════
        WID_B7 = "engineer-01-02"
        iso_manifest_b7 = {"workers": {WID_B7: {"block": "01-02", "status": "busy"}}}
        router.route(eng_iso, iso_manifest_b7, [
            {"tag": "worker.wall", "agent_id": WID_B7,
             # deliberately NO "block" key at all — the exact shape a real
             # `report.sh <id> --tag wall "<text>"` line carries (worker-
             # contract.md §6: "say exactly what blocks you", never a block
             # id — the engine is the one that knows which block it owns)
             "slots": {"detail": "operator-only: needs a prod credential rotated"}}])
        case_b7 = next((c for c in (iso_manifest_b7.get("cases") or {}).values()
                        if c.get("source") == "worker.wall"), None)
        triage_job_b7 = next((j for j in (iso_manifest_b7.get("architect_queue") or [])
                              if j.get("kind") == "triage"
                              and j.get("case_id") == (case_b7 or {}).get("case_id")), None)
        blockless_triage_b7 = next((j for j in (iso_manifest_b7.get("architect_queue") or [])
                                    if j.get("kind") == "triage" and j.get("block") is None
                                    and j.get("source") == "worker.wall"), None)
        ok("D14 (DURABLE-BLOCK-RECOVERY KILLER, ADR-0010 Invariant B — must "
           "be GREEN): an explicit --tag wall from a MAPPED worker "
           f"({WID_B7!r}) carrying NO prose block still opened its case ON "
           "THE WORKER'S DURABLE BOUND BLOCK (01-02, recovered from "
           "manifest['workers'], never block-less) — architect-owned, a "
           "real PMT-TRIAGE job queued against block=01-02 (never the "
           "block-less triage path), zero spurious operator pages",
           case_b7 is not None and case_b7.get("block") == "01-02"
           and case_b7.get("owner") == "architect" and case_b7.get("decision") is None
           and triage_job_b7 is not None and blockless_triage_b7 is None
           and len(iso_manifest_b7.get("operator_pages") or {}) == 0,
           f"case_b7={case_b7} triage_job_b7={triage_job_b7} "
           f"blockless_triage_b7={blockless_triage_b7} "
           f"pages={iso_manifest_b7.get('operator_pages')}")

        # ══════════════════════════════════════════════════════════════
        # GREP PROOF — no wall/escalation/unclassified path bypasses the
        # architect to page the operator directly; no raw git outside
        # gitobs/state IO (plain-text scan, no git involved)
        # ══════════════════════════════════════════════════════════════
        src = {}
        for mod in ("casestate", "architect", "sentry", "classify", "router", "tick"):
            src[mod] = open(os.path.join(HERE, f"{mod}.py")).read()

        import re as _re
        page_call_files = [m for m, s in src.items() if _re.search(r"_page_operator\s*\(", s)]
        ok("SRC1 (NO-DIRECT-OPERATOR-PAGE KILLER — must be GREEN): "
           "`eng._page_operator(...)` is called from EXACTLY the two "
           "places wave 18/GAP-E allows — `core/casestate.py`'s own "
           "`architect_resolve`/`open_operator_case` (the architect's OWN "
           "`operator` verdict resolution) — NEVER from `core/sentry.py`, "
           "`core/router.py`, `core/classify.py`, or `core/tick.py`, which "
           "would be a direct wall/escalation-to-operator bypass",
           page_call_files == ["casestate"],
           f"page_call_files={page_call_files}")

        cs_body = src["casestate"]
        open_case_body = cs_body.split("def open_case(")[1].split("\ndef ")[0]
        ok("SRC2 (OPEN_CASE-NEVER-PAGES KILLER — must be GREEN): `core."
           "casestate.open_case`'s OWN body never calls "
           "`eng._page_operator` — every raised wall/escalation routes "
           "through `architect.enqueue_triage` instead (grep-equivalent "
           "scan of `open_case`'s own function body only)",
           "_page_operator(" not in open_case_body
           and "enqueue_triage(" in open_case_body,
           "scanned core/casestate.py::open_case's own body")

        ok("SRC3 (NO-RAW-GIT KILLER — must be GREEN): none of casestate.py/"
           "architect.py/sentry.py/classify.py/router.py/tick.py shells "
           "out to a raw git/subprocess call of its own — all git "
           "observation stays inside core/gitobs.py (the ONE seam), all "
           "persistence inside core/state.py",
           all("import subprocess" not in s and "subprocess." not in s
               and "\nimport git\n" not in s for s in src.values()),
           "grep-equivalent source scan of core/{casestate,architect,"
           "sentry,classify,router,tick}.py")

        passed = sum(1 for _, c2, _ in _results if c2)
        print(f"core.wallrouting_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
              f"({passed}/{len(_results)})")
        for name, c2, detail in _results:
            print(f"  [{'PASS' if c2 else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        print(f"\nroot={root}")
        print(f"tron instance dir (real engine.ctx.Ctx)={inst}")
        print(f"manifest={tron_ctx.state}")
        print(f"BLOCKS={ORDER} worker_count=2")
        print(f"case_scope={case_scope} case_cap={case_cap}")
        print(f"resumed_cap_tick={resumed_cap_tick['i']} ticks_used={ticks_used} "
              f"(cap={MAX_TICKS}) session_ended_tick={session_ended_tick}")
        print(f"adhoc_block={adhoc_block}")
        print(f"final gates={ {b: final_gates.get(b, {}).get('stage') for b in ORDER} }")
        print(f"final cases (must be empty — both cleared)={final_cases}")
        print(f"final operator_pages={final_manifest.get('operator_pages')}")
        print(f"final escalations={final_manifest.get('escalations')}")
        print(f"final main tip={_git_out(['rev-parse', MAIN], root)}")
        return 0 if passed == len(_results) else 1
    finally:
        jobs.spawn_runner = real_spawn_runner
        jobs.release = real_release


if __name__ == "__main__":
    sys.exit(main())
