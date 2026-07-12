"""core.reviewers_rig — real-git, no-LLM rig proving `core.reviewers` (wave
10: cadence-PULL reviewers + the DONE-REVIEW gate) + `core.architect`'s new
`log-review` job kind do exactly what `contracts/blueprint-contracts.md` §1
("Cadence is PULL" / "Review is a milestone, not a verdict") and this
wave's own spec promise, entirely via repeated `core.tick.tick(eng)` calls
(the WAKE daemon) — never a direct `core.reviewers`/`core.architect` call
of this rig's own.

REAL surface only: a real `git init` repo copied from the SAME scaffold
every prior `core/*_rig.py` uses, `meta/scripts/land.sh` run for real via
`subprocess`, a REAL `engine.ctx.Ctx` pointing at a real `manifest.yaml` AND
(new this brick) a real `knobs.yaml` this rig writes itself (`cadence:
{code: N}` — the ONE knob `core.reviewers._cadence_cfg` reads), a REAL
declared test command (`true`) re-run in a REAL clean detached worktree,
and a minimal duck-typed `eng` — never a faked/monkeypatched trunk, never
faked cadence config, never fake content for an adhoc block.

The rig plays FOUR roles a real deployment splits across processes: the
WAKE daemon, the ordinary engineer (branch/local-pass/real `land.sh`/record
commit/teardown — the SAME react() shape every prior multi-block rig
uses, generalized here to react to WHATEVER `engineer-<block>` worker
records appear, not a static list — this is what lets it drive BOTH the
two pre-seeded ordinary blocks AND, later, the freshly-authored adhoc
block, off the SAME code path), the reviewer (sends a structured
`worker.review_done` report; a SECOND one only when the scenario wants the
DONE-REVIEW gate to actually release), and the architect (reacts to a
`log-review` job exactly like `core/architect_rig.py`'s own scripted
architect reacts to a `forward` job — authors + real-lands a genuinely NEW
pipeline row + block file per finding, on its own branch).

THREE independent scenarios, each its own real-git tempdir/manifest:

  SCENARIO A (the main happy-path killer) — two ordinary blocks
    (`01-01`/`01-02`, no deps), `cadence: {code: 2}`, `worker_count=1`
    (strict serialization: cadence due-check runs BEFORE block dispatch
    every `fill()` call, so this is also the "reviewer wins the free slot
    over the next block" proof, exercised the instant it becomes due).
    Drives: cadence ticks exactly twice (once per block's real ✅), a
    reviewer dispatches exactly once (counter reset, no double-dispatch on
    a later re-tick), the DONE-REVIEW gate HOLDS on the first
    `worker.review_done` and RELEASES only on the second (attestation),
    the attested findings queue a `log-review` that authors + REAL-lands
    ONE adhoc block file (a genuinely NEW pipeline row, no pre-existing
    file), which then dispatches + drives to ✅ + CLOSED exactly like any
    ordinary block, and the WHOLE run reaches a clean, idempotent
    SESSION-END.

  SCENARIO B (the clean-review killer) — same two-block/cadence fixture,
    but BOTH `worker.review_done` hand-backs carry ZERO findings. Proves a
    clean log-review queues NOTHING (no adhoc block ever authored, no
    `adhoc-*` pipeline row ever appears on trunk) and the run still reaches
    a clean session-end off just the two original blocks.

  SCENARIO C (the sentry-pacing killer) — same fixture, but the reviewer
    sends ONLY the first `worker.review_done` and NEVER attests. Proves
    the DONE-REVIEW gate is paced by `core/sentry.py`'s SAME ladder as any
    other gate stage (a re-nudge at `gate_nudge_after`, an escalation +
    parked operator case at `gate_idle_cap` — never a silent hang, never a
    self-cap inside `core/reviewers.py`), that the escalation frees the
    reviewer's slot for real (popped off `manifest["workers"]`, since a
    review pseudo-block carries no `manifest["gates"]` entry for the
    ordinary terminal-stage shortcut to key off), and that the run is
    still able to reach a clean session-end afterward (a capped review
    never wedges the whole drive).

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
sys.path.insert(0, HERE)                                 # core/{gate,state,snapshot,tick,...}.py

import grants               # noqa: E402 — respected contract, real, unmodified
import trunk                 # noqa: E402 — respected contract, real, unmodified
from ctx import Ctx          # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import gate                  # noqa: E402 — core/gate.py, the DONE ladder core.tick drives
import state                 # noqa: E402 — core/state.py
import tick                  # noqa: E402 — core/tick.py, wave 10's cadence/log-review wiring
import reviewers              # noqa: E402 — core/reviewers.py, the module under test
import architect               # noqa: E402 — core/architect.py, the log-review job kind under test
import router                  # noqa: E402 — core/router.py, the ASSIGN handshake (reviewer-skip under test)

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"

BLOCK_A, BLOCK_B = "01-01", "01-02"

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
    d = tempfile.mkdtemp(prefix="tron-core-reviewersrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-reviewers-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: reviewers_rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {a} | reviewers_rig fixture block A (no deps) | 📋 To do | Block `blocks/{a}.md` |
| {b} | reviewers_rig fixture block B (no deps) | 📋 To do | Block `blocks/{b}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: reviewers_rig fixture

**Phase:** 1 — reviewers_rig
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.reviewers_rig` — cadence-PULL trigger fixture.
"""

ADHOC_PIPELINE_SECTION = """
## Ad-hoc

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
"""

ADHOC_ROW_TEMPLATE = "| {block} | {title} | 📋 To do | Block `blocks/{block}.md` |\n"

ADHOC_BLOCK_DOC_TEMPLATE = """# Block {block}: log-review adhoc fixture

**Phase:** 1 — reviewers_rig log-review
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Authored by the SCRIPTED ARCHITECT (`core.reviewers_rig`, playing a real
`log-review` job) from a code-review finding: {title!r} — a genuinely NEW
adhoc block (no pre-existing pipeline row), landed via
`core.landing.land_via_grant` under a content-bound case-id.
"""


def seed_pipeline(root):
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(a=BLOCK_A, b=BLOCK_B))
    for block in (BLOCK_A, BLOCK_B):
        bpath = os.path.join(root, BLOCKS_REL, f"{block}.md")
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        with open(bpath, "w") as f:
            f.write(BLOCK_DOC_TEMPLATE.format(block=block))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + blocks {BLOCK_A}/{BLOCK_B} "
                          f"(both to-do, no deps, no gates)"], root)
    _git(["checkout", "--detach", MAIN], root)


def write_knobs(tron_ctx, cadence):
    """The ONE new file this brick's rigs write that no prior `core/*_rig.py`
    ever needed: `knobs.yaml`'s top-level `cadence: {<type>: <n>}` map —
    `core.reviewers._cadence_cfg`'s own read target (via `core.knobs.load`,
    real file IO — never faked/monkeypatched). SCHEMA-COMPLIANT (`contracts/
    schema/knobs.schema.yaml`, wave 16): `cadence:` stays its own top-level
    block, a sibling of `knobs:`, never nested — a bare `knobs: {worker_
    count: null}` rides along so the file satisfies the schema's REQUIRED
    `knobs:`/`worker_count` shape, deliberately declaring NEITHER silence
    knob (the precedent `core/liveness.py`'s own docstring names by name:
    proves a knobs.yaml configuring OTHER knobs only still reads as "no
    silence knobs configured", never a crash on an unrelated file)."""
    os.makedirs(os.path.dirname(tron_ctx.knobs_file), exist_ok=True)
    with open(tron_ctx.knobs_file, "w") as f:
        yaml.safe_dump({"knobs": {"worker_count": None}, "cadence": cadence},
                       f, sort_keys=False, default_flow_style=False)


def make_code_commit(root, branch, code_file_rel, marker):
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(f"// {marker} — core.reviewers_rig real code change\n")
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
    block file for a log-review finding — the ONE content this rig writes
    for a `log` job's own adhoc entry (mirrors `core/architect_rig.py`'s
    own `make_forward_block_doc`, but that one only needed the block FILE:
    a `forward` job's target row already exists on trunk; a `log-review`
    adhoc finding has NO pipeline row at all yet, so this authors BOTH, in
    ONE commit, on the architect's own branch)."""
    _git(["checkout", "-B", branch, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    with open(ppath) as f:
        content = f.read()
    row = ADHOC_ROW_TEMPLATE.format(block=block, title=title)
    if "## Ad-hoc" not in content:
        content = content.rstrip("\n") + "\n" + ADHOC_PIPELINE_SECTION + row
    else:
        lines = content.splitlines(keepends=True)
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
    with open(bpath, "w") as f:
        f.write(ADHOC_BLOCK_DOC_TEMPLATE.format(block=block, title=title))
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
    `core/session.py` + `core/architect.py` + `core/reviewers.py` +
    `core/sentry.py` + `core/casestate.py` (via `core/tick.py`) need."""
    def __init__(self, root, tron_ctx, test_command, worker_count=1):
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
        self.pages = []

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

    def _page_operator(self, case_id, block, detail, worker_id=None, **_kwargs):
        # **_kwargs: wave 17 (GAP-A) widened the real `eng._page_operator`
        # call surface (`manifest=`/`page_kind=`, `core/casestate.py`'s own
        # THE-FLOOR re-ping ladder) — tolerated and ignored here, never
        # weakening C-K5's own exact-count assertion (this scenario's own
        # `drive()` stops the SAME tick the case opens, before any re-ping
        # ladder ever gets a second chance to fire).
        self.pages.append((case_id, block, detail, worker_id))


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
                                 "(rig-supplied local report, delivered via a structured "
                                 "worker.done inbox line)"}


class RunHistory:
    """Per-scenario mutable tracking, factored out of `main()` so all three
    scenarios below share IDENTICAL react() logic without global state
    leaking between them."""
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
        self.reviewer_seen = {}          # agent_id -> first-seen tick
        self.review_first_sent = set()   # agent_ids sent the 1st review_done
        self.review_hold_tick = {}       # agent_id -> first tick observed "held"
        self.review_attest_sent = set()  # agent_ids sent the 2nd (attest)
        self.review_release_tick = {}    # agent_id -> first tick observed released (popped)
        self.adhoc_authored = set()
        self.adhoc_landed_tick = {}
        self.cadence_at_dispatch = {}    # agent_id -> manifest["cadence"] snapshot, dispatch tick
        self.reconciled_reported = set()  # M-05 (wave 9): blocks already reported architect.reconciled
        self.triage_answered = set()      # wave 18 (GAP-E): triage_ids already answered
        self.tick_history = []           # (i, outcomes, spawned, session_end)

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
                                 f"{block}-reviewersrig-change")
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
                    run_land(self.root, self.grants_dir, case_id)
                    self.landed_cases.add(case_id)
            elif stage == gate.STAGE_RECORD:
                if g.get("record_ordered") and not self.record_committed[block] \
                        and not g.get("record_case_id"):
                    make_record_commit(self.root, branch, block_file_rel)
                    self.record_committed[block] = True
                if g.get("record_case_id") and g["record_case_id"] not in self.landed_cases:
                    case_id = g["record_case_id"]
                    run_land(self.root, self.grants_dir, case_id)
                    self.landed_cases.add(case_id)
            elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not self.torn_down[block]:
                _git(["branch", "-D", branch], self.root)
                self.torn_down[block] = True

            if stage == gate.STAGE_CLOSED and block not in self.close_tick:
                self.close_tick[block] = i

    def react_reviewer(self, i, manifest, *, attest, findings_first, findings_second):
        workers = manifest.get("workers") or {}
        for agent_id, w in list(workers.items()):
            if not agent_id.startswith("reviewer-"):
                continue
            typ = w.get("type")
            if agent_id not in self.reviewer_seen:
                self.reviewer_seen[agent_id] = i
                self.cadence_at_dispatch[agent_id] = dict(manifest.get("cadence") or {})
            status = w.get("status")
            if status == "reviewing" and agent_id not in self.review_first_sent:
                append_jsonl(self.tron_ctx.worker_inbox,
                            {"tag": "worker.review_done", "agent_id": agent_id, "type": typ,
                             "slots": {"findings": findings_first}})
                self.review_first_sent.add(agent_id)
            elif status == "held":
                if agent_id not in self.review_hold_tick:
                    self.review_hold_tick[agent_id] = i
                if attest and agent_id not in self.review_attest_sent:
                    append_jsonl(self.tron_ctx.worker_inbox,
                                {"tag": "worker.review_done", "agent_id": agent_id, "type": typ,
                                 "slots": {"findings": findings_second}})
                    self.review_attest_sent.add(agent_id)
        # released reviewers are gone from `workers` — capture the FIRST
        # tick a previously-seen agent_id is no longer on file.
        for agent_id in self.reviewer_seen:
            if agent_id not in workers and agent_id not in self.review_release_tick:
                self.review_release_tick[agent_id] = i

    def react_architect_reconcile(self, i, manifest):
        """M-05 (wave 9, `core/architect.py`): a block landing ✅ ALSO
        enqueues a `reconcile` job for the NEXT in-scope block by pipeline
        order, gating ITS dispatch until the architect reports done — no
        content-check in this no-LLM brick, so just report
        `architect.reconciled` once ordered, exactly like `core/
        multiblock_rig.py`/`core/architect_rig.py`'s own scripted
        architect already do. Unrelated to `log-review` (a DIFFERENT job
        kind) but shares the SAME `architect` queue/current_job, so this
        rig must play both roles or a fixture with >1 ordinary block
        never gets past the first one."""
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if cur and cur.get("kind") == "reconcile" and cur.get("ordered") \
                and cur.get("block") not in self.reconciled_reported:
            append_jsonl(self.tron_ctx.worker_inbox,
                        {"tag": "architect.reconciled", "block": cur["block"]})
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
                run_land(self.root, self.grants_dir, case_id)
                self.landed_cases.add(case_id)
                if block not in self.adhoc_landed_tick:
                    self.adhoc_landed_tick[block] = i

    def react_architect_triage(self, i, manifest):
        """Wave 18 (GAP-E): a `sentry.cap` escalation on a held reviewer now
        opens a case that is architect-first (`core/casestate.py::
        open_case` -> `core/architect.py::enqueue_triage`), never an
        immediate operator page. This rig's own C-K5/C-K7 exercise the
        OPERATOR-facing surface (an `eng._page_operator` firing at all,
        never wedging the drive) — so it always scripts the architect to
        answer `operator`, the SAME "escalate all the way through" shape
        every other re-pointed rig in this wave uses, letting the
        pre-existing operator-facing assertions hold with the ONE added
        architect hop genuinely exercised in between."""
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if (cur and cur.get("kind") == "triage" and cur.get("ordered")
                and cur.get("triage_id") not in self.triage_answered):
            append_jsonl(self.tron_ctx.worker_inbox,
                        {"tag": "architect.triage_verdict",
                         "triage_id": cur["triage_id"], "verdict": "operator"})
            self.triage_answered.add(cur["triage_id"])

    def react(self, i, manifest, *, attest=True, findings_first=None, findings_second=None):
        self.react_engineers(i, manifest)
        self.react_reviewer(i, manifest, attest=attest,
                            findings_first=findings_first or [], findings_second=findings_second or [])
        self.react_architect_reconcile(i, manifest)
        self.react_architect_log(i, manifest)
        self.react_architect_triage(i, manifest)

    def record_done_ticks(self, i, outcomes):
        for block, (outcome, _detail) in outcomes.items():
            if outcome == "record_landed" and block not in self.done_tick:
                self.done_tick[block] = i


def drive(eng, tron_ctx, hist, max_ticks, *, attest, findings_first, findings_second,
          stop_when=None):
    session_ended_tick = None
    i = 0
    for i in range(max_ticks):
        res = tick.tick(eng)
        manifest = state.load(tron_ctx)
        se = res.get("session_end")
        hist.tick_history.append((i, dict(res["outcomes"]), list(res["spawned"]), se))
        hist.record_done_ticks(i, res["outcomes"])
        hist.react(i, manifest, attest=attest, findings_first=findings_first,
                  findings_second=findings_second)
        if se is not None and session_ended_tick is None:
            session_ended_tick = i
            break
        if stop_when and stop_when(i, manifest, hist):
            break
    return i, session_ended_tick


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO A — the main happy-path killer
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_a():
    root = build_root()
    seed_pipeline(root)
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    write_knobs(tron_ctx, {"code": 2})
    grants_dir = tron_ctx.grants_dir

    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    hist = RunHistory(root, grants_dir, tron_ctx)

    finding = [{"title": "adhoc-code-1: missing input validation"}]
    ticks_used, session_ended_tick = drive(
        eng, tron_ctx, hist, max_ticks=260,
        attest=True, findings_first=finding, findings_second=finding)

    final_manifest = state.load(tron_ctx)
    final_gates = final_manifest.get("gates") or {}

    ok("A-M0: SCENARIO A converged to a clean session-end",
       session_ended_tick is not None, f"ticks_used={ticks_used + 1} session_ended_tick={session_ended_tick}")

    # ── KILLER 1: cadence PULL dispatches exactly once, strictly after
    #     BOTH blocks' ✅ was observed, with the counter reset ──
    ok("A-K1 (CADENCE-PULL-ONCE KILLER — must be GREEN): exactly ONE code "
       "reviewer was ever dispatched across the whole run",
       len(hist.reviewer_seen) == 1, f"reviewer_seen={hist.reviewer_seen}")
    rid = next(iter(hist.reviewer_seen), None)
    ok("A-K2: the reviewer was dispatched STRICTLY AFTER both fixture "
       "blocks' ✅ was observed on trunk (cadence counted both dones "
       "before tripping the threshold)",
       rid is not None and BLOCK_A in hist.done_tick and BLOCK_B in hist.done_tick
       and hist.reviewer_seen[rid] > max(hist.done_tick[BLOCK_A], hist.done_tick[BLOCK_B]),
       f"reviewer_seen={hist.reviewer_seen} done_tick={hist.done_tick}")
    ok("A-K3 (COUNTER-RESET KILLER — must be GREEN): the cadence counter "
       "for 'code' reads 0 in the manifest the SAME tick the reviewer was "
       "spawned (consumed on dispatch, never left armed)",
       rid is not None and hist.cadence_at_dispatch.get(rid, {}).get("code") == 0,
       f"cadence_at_dispatch[{rid}]={hist.cadence_at_dispatch.get(rid)}")
    ok("A-K4 (NO-DOUBLE-DISPATCH KILLER — must be GREEN): the reviewer's "
       "agent-id appears in exactly ONE tick's `spawned` list across the "
       "WHOLE drive — a re-tick never double-dispatches",
       sum(1 for _i, _o, spawned, _se in hist.tick_history if rid in spawned) == 1,
       f"spawned lists={[s for _, _, s, _ in hist.tick_history]}")

    # ── KILLER 2: DONE-REVIEW gate holds on the 1st hand-back, releases
    #     only on the 2nd (attestation) ──
    ok("A-K5 (COVERAGE-HOLD KILLER — must be GREEN): the reviewer's "
       "record was observed 'held' (the DONE-REVIEW gate) strictly AFTER "
       "the first worker.review_done — a hand-back never releases on the "
       "first report alone",
       rid in hist.review_hold_tick, f"review_hold_tick={hist.review_hold_tick}")
    ok("A-K6 (ATTEST-RELEASES KILLER — must be GREEN): the reviewer's "
       "worker record was popped (slot freed) strictly AFTER the SECOND "
       "worker.review_done (attestation), never before",
       rid in hist.review_release_tick and rid in hist.review_hold_tick
       and hist.review_release_tick[rid] > hist.review_hold_tick[rid],
       f"release_tick={hist.review_release_tick.get(rid)} hold_tick={hist.review_hold_tick.get(rid)}")
    ok("A-K7: the reviewer's slot was REALLY released via eng (never a "
       "trust-release with no external bookkeeping)",
       eng.workers.get(rid, {}).get("status") == "released",
       f"eng.workers[{rid}]={eng.workers.get(rid)}")

    # ── KILLER 3: log-review with findings authors + real-lands an adhoc
    #     block that then dispatches + closes ──
    adhoc_block = "adhoc-code-1"
    ok(f"A-K8 (ADHOC-AUTHORED KILLER — must be GREEN): the architect "
       f"authored + landed the adhoc block {adhoc_block!r} for the "
       "attested finding",
       adhoc_block in hist.adhoc_authored and adhoc_block in hist.adhoc_landed_tick,
       f"authored={hist.adhoc_authored} landed_tick={hist.adhoc_landed_tick}")
    doc_on_main = _git_out(["show", f"{MAIN}:{BLOCKS_REL}/{adhoc_block}.md"], root)
    ok(f"A-K9: block {adhoc_block!r} doc AS READ FROM main shows ✅ (real "
       "git show on trunk) — it dispatched + closed exactly like an "
       "ordinary block",
       "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")
    g_adhoc = final_gates.get(adhoc_block, {})
    branch_gone = not trunk.branch_exists(root, f"feat/{adhoc_block}", False)
    clean_now, clean_detail = trunk.replica_clean(root, f"feat/{adhoc_block}", MAIN, False)
    ok(f"A-K10: {adhoc_block} gate reached CLOSED with a genuinely clean "
       "replica + slot released",
       branch_gone and clean_now and g_adhoc.get("stage") == gate.STAGE_CLOSED,
       f"branch_gone={branch_gone} clean={clean_now} stage={g_adhoc.get('stage')} "
       f"detail={clean_detail}")
    case_ids = {e for e in hist.landed_cases if e.startswith("paperwork-logreview-")}
    ok("A-K11 (CONTENT-BOUND CASE-ID KILLER — must be GREEN): the adhoc "
       "block landed under a case-id bound to role='logreview' (distinct "
       "from gate.py's merge/record/forward roles), via the REAL land.sh",
       len(case_ids) == 1, f"logreview_case_ids={case_ids}")

    # ── KILLER 4: the whole run (2 blocks + reviewer + log-review) reaches
    #     a clean session-end; the architect ends idle+empty ──
    for block in (BLOCK_A, BLOCK_B, adhoc_block):
        g = final_gates.get(block, {})
        ok(f"A-K12[{block}]: reached CLOSED on trunk",
           g.get("stage") == gate.STAGE_CLOSED, f"stage={g.get('stage')}")
    architect_final = final_manifest.get("architect") or {}
    ok("A-K13: the architect ends IDLE with an EMPTY queue — the log-review "
       "job never lingers",
       architect_final.get("status") == "idle" and architect_final.get("current_job") is None
       and not (final_manifest.get("architect_queue") or []),
       f"architect={architect_final} queue={final_manifest.get('architect_queue')}")
    ok("A-K14: no reviewer worker record lingers in the final manifest "
       "(fully released, not just marked)",
       rid not in (final_manifest.get("workers") or {}),
       f"workers={list((final_manifest.get('workers') or {}).keys())}")

    # ── idempotent re-tick ──
    pre_bytes = open(tron_ctx.state, "rb").read()
    pre_main = _git_out(["rev-parse", MAIN], root)
    pre_orders = len(eng.orders)
    res_replay = tick.tick(eng)
    post_bytes = open(tron_ctx.state, "rb").read()
    post_main = _git_out(["rev-parse", MAIN], root)
    ok("A-K15 (IDEMPOTENT RE-TICK KILLER — must be GREEN): a further tick "
       "after session-end is a true no-op — no new order, manifest + real "
       "git byte-identical",
       res_replay.get("spawned") == [] and res_replay.get("outcomes") == {}
       and len(eng.orders) == pre_orders and post_bytes == pre_bytes and post_main == pre_main,
       f"replay={res_replay}")

    print("\n== SCENARIO A (happy path) ==")
    print(f"root={root}")
    print(f"ticks_used={ticks_used + 1} session_ended_tick={session_ended_tick}")
    print(f"reviewer_seen={hist.reviewer_seen} review_hold_tick={hist.review_hold_tick} "
          f"review_release_tick={hist.review_release_tick}")
    print(f"adhoc_authored={hist.adhoc_authored} adhoc_landed_tick={hist.adhoc_landed_tick}")
    print(f"done_tick={hist.done_tick} close_tick={hist.close_tick}")


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO B — the clean-review killer (zero findings)
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_b():
    root = build_root()
    seed_pipeline(root)
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    write_knobs(tron_ctx, {"code": 2})
    grants_dir = tron_ctx.grants_dir

    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    hist = RunHistory(root, grants_dir, tron_ctx)

    ticks_used, session_ended_tick = drive(
        eng, tron_ctx, hist, max_ticks=200,
        attest=True, findings_first=[], findings_second=[])

    final_manifest = state.load(tron_ctx)
    final_gates = final_manifest.get("gates") or {}

    ok("B-M0: SCENARIO B (clean review) converged to a clean session-end",
       session_ended_tick is not None, f"ticks_used={ticks_used + 1}")
    rid = next(iter(hist.reviewer_seen), None)
    ok("B-K1: exactly one reviewer dispatched, held then released (the "
       "DONE-REVIEW gate itself doesn't care whether findings are empty)",
       len(hist.reviewer_seen) == 1 and rid in hist.review_hold_tick
       and rid in hist.review_release_tick, f"reviewer_seen={hist.reviewer_seen}")
    ok("B-K2 (CLEAN-REVIEW-QUEUES-NOTHING KILLER — must be GREEN): NO "
       "adhoc block was ever authored or landed for this run",
       not hist.adhoc_authored and not hist.adhoc_landed_tick,
       f"adhoc_authored={hist.adhoc_authored}")
    on_main = _git_out(["show", f"{MAIN}:{PIPELINE_REL}"], root)
    ok("B-K3: the pipeline on trunk carries NO 'Ad-hoc' section at all — "
       "nothing was ever queued to author",
       "## Ad-hoc" not in on_main, "pipeline.md head=" + "\n".join(on_main.splitlines()[:20]))
    architect_final = final_manifest.get("architect") or {}
    ok("B-K4: the architect ends IDLE with an EMPTY queue",
       architect_final.get("status") == "idle" and architect_final.get("current_job") is None
       and not (final_manifest.get("architect_queue") or []),
       f"architect={architect_final}")
    for block in (BLOCK_A, BLOCK_B):
        g = final_gates.get(block, {})
        ok(f"B-K5[{block}]: reached CLOSED on trunk (session settles on "
           "just the two original blocks)",
           g.get("stage") == gate.STAGE_CLOSED, f"stage={g.get('stage')}")

    print("\n== SCENARIO B (clean review, no findings) ==")
    print(f"root={root}")
    print(f"ticks_used={ticks_used + 1} session_ended_tick={session_ended_tick}")
    print(f"reviewer_seen={hist.reviewer_seen}")


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO C — the sentry-pacing killer (a reviewer that never attests)
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_c():
    root = build_root()
    seed_pipeline(root)
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    write_knobs(tron_ctx, {"code": 2})
    grants_dir = tron_ctx.grants_dir

    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    hist = RunHistory(root, grants_dir, tron_ctx)

    finding = [{"title": "adhoc-code-1: never attested, never lands"}]

    def stop_when(i, manifest, h):
        return bool(manifest.get("escalations"))

    ticks_used, session_ended_tick = drive(
        eng, tron_ctx, hist, max_ticks=80,
        attest=False, findings_first=finding, findings_second=finding,
        stop_when=stop_when)

    # ── wave 18 (GAP-E): the cap escalation opens an ARCHITECT-first case
    #     now (never an immediate operator page) — `stop_when` above fires
    #     the instant `manifest["escalations"]` appears, which is BEFORE the
    #     architect's own (scripted-in-react) `operator` verdict has had a
    #     chance to land. Keep driving (bounded, `react`'s own
    #     `react_architect_triage` answers it) until the page genuinely
    #     fires, before asserting on it below — never a pre-timed/scripted
    #     resume, same "observe it for real" discipline this rig's own
    #     `maybe_resume`-style rigs already keep. ──
    for _ in range(20):
        if eng.pages:
            break
        tick.tick(eng)
        hist.react(0, state.load(tron_ctx), attest=False,
                  findings_first=finding, findings_second=finding)

    final_manifest = state.load(tron_ctx)
    rid = next(iter(hist.reviewer_seen), None)

    ok("C-M0: SCENARIO C reached a sentry escalation before the tick cap",
       bool(final_manifest.get("escalations")), f"ticks_used={ticks_used + 1}")
    ok("C-K1: exactly one reviewer dispatched, held, and NEVER attested "
       "(no second worker.review_done sent by this rig)",
       len(hist.reviewer_seen) == 1 and rid in hist.review_hold_tick
       and rid not in hist.review_attest_sent, f"reviewer_seen={hist.reviewer_seen}")

    nudge_orders = [o for o in eng.orders if o[0] == rid and o[2].startswith("sentry.nudge.")]
    ok("C-K2 (NUDGE KILLER — must be GREEN): sentry re-sent the "
       "coverage-attest order to the stuck reviewer at least once, before "
       "escalating",
       len(nudge_orders) >= 1, f"nudge_orders={nudge_orders}")

    escalations = [e for e in (final_manifest.get("escalations") or [])
                  if e.get("block") == "review:code"]
    ok("C-K3 (ESCALATE KILLER — must be GREEN): sentry escalated the "
       "stuck review — a structured `manifest['escalations']` record for "
       "block='review:code', stage='review'",
       len(escalations) == 1 and escalations[0].get("stage") == "review",
       f"escalations={escalations}")

    cases = [c for c in (final_manifest.get("cases") or {}).values()
            if c.get("block") == "review:code"]
    ok("C-K4 (PARKED-CASE KILLER — must be GREEN): the escalation opened a "
       "parked operator case (kind='cap') for the review, exactly like a "
       "block-gate cap already does",
       len(cases) == 1 and cases[0].get("kind") == "cap" and cases[0].get("source") == "sentry.cap",
       f"cases={cases}")
    ok("C-K5: the operator was really paged (eng._page_operator fired)",
       len(eng.pages) == 1 and eng.pages[0][1] == "review:code",
       f"pages={eng.pages}")

    ok("C-K6 (SLOT-FREED KILLER — must be GREEN): the reviewer's worker "
       "record is GONE from the manifest (popped — the ONLY thing that "
       "frees a review pseudo-block's slot) and eng reports it released",
       rid not in (final_manifest.get("workers") or {})
       and eng.workers.get(rid, {}).get("status") == "released",
       f"workers={list((final_manifest.get('workers') or {}).keys())} "
       f"eng.workers[{rid}]={eng.workers.get(rid)}")

    # ── R3 (ADR-0005): the sentry.cap escalation opened a GENUINE operator case
    #     (C-K4/C-K5). Two properties now hold together:
    #     (a) the run must NOT false-green to session-end while that case is open
    #         — ending past an unresolved operator escalation was the exact
    #         false-green R3 closes; and
    #     (b) the cap must not WEDGE the drive either — once the operator answers,
    #         the run reaches a clean session-end off the two ordinary blocks.
    #     (Before R3, session.check ignored open cases, so this drive "ended
    #     clean" WITH the cap escalation still dangling — the false-green.) ──
    i2a, held = drive(
        eng, tron_ctx, hist, max_ticks=10,
        attest=False, findings_first=finding, findings_second=finding)
    ok("C-K7a (R3 ESCALATION-HELD KILLER — must be GREEN): the run does NOT reach "
       "session-end while the sentry.cap operator case is unresolved (no false-green "
       "past an open escalation)",
       held is None, f"held={held} ticks={i2a + 1}")

    import casestate   # settle the cap case exactly as the operator's own reply would
    m = state.load(tron_ctx)
    cap_case = next(c for c in (m.get("cases") or {}).values()
                    if c.get("source") == "sentry.cap")
    casestate.settle(eng, m, cap_case["case_id"], "abandon")
    state.save(tron_ctx, m)

    i2, session_ended_tick2 = drive(
        eng, tron_ctx, hist, max_ticks=60,
        attest=False, findings_first=finding, findings_second=finding)
    ok("C-K7 (NEVER-WEDGED KILLER — must be GREEN): once the operator answers the "
       "cap escalation the run reaches a clean session-end — the cap awaited a "
       "decision, never wedged the drive (and never false-greened past it, C-K7a)",
       session_ended_tick2 is not None, f"ticks_used_after_settle={i2 + 1}")
    ok("C-K8: no SECOND 'code' reviewer was ever dispatched after the cap "
       "(the counter stays consumed; no new block landed since)",
       len(hist.reviewer_seen) == 1, f"reviewer_seen={hist.reviewer_seen}")

    print("\n== SCENARIO C (sentry pacing, never attests) ==")
    print(f"root={root}")
    print(f"ticks_used_to_cap={ticks_used + 1} escalations={escalations}")
    print(f"nudge_orders={nudge_orders}")
    print(f"session_ended_tick_after_cap={session_ended_tick2}")


def run_scenario_d_review_done_type_derive():
    """Z-lock (s2 first-honest-SIM): a `worker.review_done` that omits `type`
    (classify didn't parse one out of the reviewer's free-text hand-back) must
    NOT be dropped when the sender is a reviewer ON FILE — the type is derived
    from its own worker record, so the attestation is never silently lost."""
    root = build_root()
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)
    aid = "reviewer-code-1"
    manifest = {"workers": {aid: {"block": reviewers.review_block("code"),
                                  "type": "code", "status": "reviewing", "wid": aid}}}
    reviewers.on_review_done(
        eng, manifest, {"tag": "worker.review_done", "agent_id": aid})  # NO type
    ok("D-TYPE (REVIEW-DONE TYPE-DERIVE LOCK — must be GREEN): a review_done "
       "with no parsed `type`, from a reviewer on file, is accepted (type "
       "derived from its worker record) not dropped — status held, not lost",
       manifest["workers"].get(aid, {}).get("status") == "held",
       f"worker={manifest['workers'].get(aid)}")


def run_scenario_e_reviewer_never_build_assigned():
    """T2-10 regression (router build-ASSIGN of a reviewer). A reviewer comes
    ONLINE carrying its `review:<type>` PSEUDO-block. `router._route_online`
    must NOT send it the engineer build-ASSIGN ("you own block review:code,
    read its spec at None and build it end to end, declare a branch") — a
    read-only reviewer correctly refuses to build and walls the run (the LIVE
    T2-10 reviewer wall → architect triage → operator page, breaking an
    otherwise-clean SIM). The reviewer is already ordered at spawn
    (`reviewers.dispatch`, PMT-SPAWN); the router just marks it assigned."""
    root = build_root()
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=1)

    aid = "reviewer-code-1"
    workers = {aid: {"block": reviewers.review_block("code"), "type": "code",
                     "status": "reviewing", "wid": aid}}
    manifest = {"workers": workers, "gates": {}}
    router._route_online(eng, manifest, workers, manifest["gates"],
                        {"tag": "worker.online", "agent_id": aid,
                         "slots": {"branch": "feat/should-not-be-asked-for"}})
    to_reviewer = [o for o in eng.orders if o[0] == aid]
    build_orders = [o for o in to_reviewer
                    if "ASSIGN" in (o[2] or "") or "build it end to end" in (o[1] or "")]
    ok("E-K1 (REVIEWER-NEVER-BUILD-ASSIGNED KILLER — must be GREEN): a reviewer's "
       "worker.online produces NO engineer build-ASSIGN (no PMT-ASSIGN, no 'build "
       "it end to end' order) — the router never orders a read-only reviewer to "
       "branch/build, so the T2-10 reviewer wall can't fire",
       not build_orders,
       f"orders_to_reviewer={[(o[2], (o[1] or '')[:48]) for o in to_reviewer]}")
    ok("E-K2: the reviewer is marked assigned (a repeat worker.online is inert) — "
       "its review order already went out at spawn (PMT-SPAWN)",
       workers[aid].get("assigned") is True, f"worker={workers[aid]}")

    # CONTRAST: an ordinary ENGINEER online still gets the build-ASSIGN — the
    # reviewer skip is scoped to `review:<type>` pseudo-blocks (the only worker
    # block containing a ':'), never weakening the real assign path.
    eid = "engineer-01-02"
    ew = {eid: {"block": "01-02", "block_file": "meta/blocks/01-02.md", "status": "spawned"}}
    m2 = {"workers": ew, "gates": {}}
    router._route_online(eng, m2, ew, m2["gates"],
                        {"tag": "worker.online", "agent_id": eid})
    eng_build = [o for o in eng.orders if o[0] == eid and "build it end to end" in (o[1] or "")]
    ok("E-K3 (ENGINEER-STILL-ASSIGNED — scope guard): an ordinary engineer's "
       "worker.online DOES still get the build-ASSIGN + is marked assigned — the "
       "reviewer skip is scoped to review:<type> pseudo-blocks only",
       len(eng_build) == 1 and ew[eid].get("assigned") is True,
       f"eng_orders={[(o[2], (o[1] or '')[:48]) for o in eng.orders if o[0] == eid]}")

    # ── E-K4: the discriminator is the `review:` PREFIX, not a bare ':' — a
    #    (typo'd) human-authored pipeline ID cell carrying a stray ':' is a real
    #    ENGINEER block and MUST still get the build-ASSIGN, never silently skipped. ──
    cid = "engineer-S1-05"
    cw = {cid: {"block": "S1-05: retry-path", "block_file": "meta/blocks/S1-05.md",
                "status": "spawned"}}
    m3 = {"workers": cw, "gates": {}}
    router._route_online(eng, m3, cw, m3["gates"],
                        {"tag": "worker.online", "agent_id": cid})
    colon_build = [o for o in eng.orders if o[0] == cid and "build it end to end" in (o[1] or "")]
    ok("E-K4 (STRAY-COLON-IS-STILL-A-BUILD KILLER — must be GREEN): an engineer "
       "block id containing a stray ':' (not a `review:` prefix) still gets the "
       "build-ASSIGN — the reviewer skip keys off the `review:` prefix, not a bare "
       "':' anywhere (no silent-default stall on a typo'd pipeline row)",
       len(colon_build) == 1 and cw[cid].get("assigned") is True,
       f"colon_orders={[(o[2], (o[1] or '')[:48]) for o in eng.orders if o[0] == cid]}")

    # ── E-K5: _open_gate_if_branch must NEVER open a gate ladder for a reviewer —
    #    a `review:<type>` living in manifest['gates'] crashes the next tick. Even
    #    if a (non-deterministic) reviewer report carries slots.branch. ──
    gates = {}
    rw = {aid: {"block": reviewers.review_block("code"), "type": "code",
                "status": "reviewing", "wid": aid, "assigned": True}}
    router._open_gate_if_branch(eng, rw, gates,
                               {"tag": "worker.online", "agent_id": aid,
                                "slots": {"branch": "feat/reviewer-should-not-gate"}})
    ok("E-K5 (REVIEWER-NEVER-GATED KILLER — must be GREEN): a reviewer report "
       "carrying a stray branch does NOT open a gate.local — no `review:<type>` "
       "entry ever lands in manifest['gates'] (which would crash the next tick)",
       "review:code" not in gates and gates == {}, f"gates={gates}")

    print("\n== SCENARIO E (reviewer never build-ASSIGNed) ==")
    print(f"root={root}")
    print(f"orders_to_reviewer={[(o[2], (o[1] or '')[:48]) for o in to_reviewer]}")


def main():
    run_scenario_a()
    run_scenario_b()
    run_scenario_c()
    run_scenario_d_review_done_type_derive()
    run_scenario_e_reviewer_never_build_assigned()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.reviewers_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
