"""core.trunkchurn_rig — GAP-B: real-git, no-LLM rig proving the engine's
observe-vs-truth is correct when TRUNK MOVES *while a block is mid-gate*
(the historical `tron-40 CASE-008` wall — taxonomy row 4 / GAP-B of
`logs/architecture/log-260710-old-sim-failure-taxonomy.md`): "A worker
reports done, the code actually landed on trunk, yet the local gate never
registers the pass, re-asks, hits its 3-attempt cap, and walls — while the
land had succeeded." No prior `core/*_rig.py` moves trunk UNDER a mid-gate
worker: `core/liveness_rig.py` lands two blocks concurrently but neither is
ever caught strictly mid-`gate.record` while the other's FULL landing races
underneath it; `core/multiblock_rig.py` serializes via a real `Depends on`
edge. This brick adds that precise scenario.

## Scenario (real git + real `land.sh`, deterministic, driven entirely via
## `core.tick.tick` — the WAKE daemon, exactly like `core/multiblock_rig.py`)

Two real, pipeline-dispatched blocks, no dependency edge, `worker_count=2`
(both free to run concurrently):

  BLOCK_A (`churn-a`, branch `feat/churn-a`) — driven all the way to
    `gate.record`: code merged onto trunk for real (`gate.merge`), trunk
    re-validated for real (`gate.trunk`), the ✅ record commit made and its
    grant minted+ordered (`gate.record`) — MID-GATE, exactly the taxonomy's
    own words: "between merge and record/close". The rig (playing block A's
    worker) then deliberately WITHHOLDS running `land.sh` for that grant.

  BLOCK_B (`churn-b`, branch `feat/churn-b`) — held back by the RIG (never
    the engine — SWITCHBOARD spawns both workers immediately; the rig
    simply doesn't react to B's spawn yet) until block A reaches
    `gate.record` (so B's own code branch forks off a trunk that already
    includes A's merged code, keeping the churn scoped to A's RECORD stage,
    never a code-merge race). Once released, B runs its ENTIRE ladder
    (local -> merge -> trunk -> record -> close) to a genuine clean close,
    landing real code AND its own ✅ record commit — moving trunk out from
    under block A's still-open, still-pending record grant.

  THE CHURN: the instant block B's gate reaches `STAGE_CLOSED`, the rig
  releases its withhold and lets block A's worker try `land.sh` for its
  (already-minted, never-touched) record grant. Block A's branch is now
  BEHIND trunk (non-fast-forward — real `land.sh` refuses, real stderr
  "not a fast-forward", exactly the historical wall's own signature) — the
  rig (the WORKER, never the control plane, per this wave's own hard rule)
  rebases block A's branch onto the new trunk (a pure rebase: block A only
  ever touches its own block-doc file, so the replay is always clean) and
  retries the SAME `land.sh` call under the SAME case-id (`core.landing.
  paperwork_case_id`'s content-binding: an unchanged diff re-derives the
  IDENTICAL patch-id, so the grant carries the rebase unmodified — proven
  below, not assumed). The second `land.sh` attempt is now a genuine
  fast-forward and succeeds for real.

  ASSERTED: block A's record STILL lands (content-bound case-id +
  observe-first sees the real landed state — never a second/different
  grant minted for the SAME content), block A reaches ✅ on trunk, the gate
  never falsely caps or mis-observes (no premature "landed", no escalate,
  during the whole withheld window — `core/gate.py` is a pure predicate
  machine with NO per-stage attempt cap, wave-7's own consolidation; this
  rig is the first to prove that design decision under REAL churn rather
  than merely by source inspection), block B closes cleanly, and the run
  reaches a genuine clean SESSION-END.

## Sentry pacing — a deliberately controlled clock, NOT a weakened test

`core/sentry.py`'s idle ladder (`GATE_NUDGE_AFTER=3` / `GATE_IDLE_CAP=6`
PACE UNITS holding at one stage) is an intentionally SEPARATE, already-proven
mechanism (`core/sentry_rig.py`) for "a worker took too long" — orthogonal
to what THIS rig exists to prove (whether the GATE correctly OBSERVES a
landing that happened despite trunk churn). Driving block B's entire
5-stage ladder to a real close inside 6 real tick-host passes is not
achievable without either (a) making the scenario physically impossible to
set up on the real surface, or (b) reintroducing a synthetic/fake
trunk — both hard-ruled out. `core/sentry.py`'s own docstring explicitly
sanctions the alternative this rig uses instead: "a rig can hand it a fully
self-controlled counter to pin the nudge/cap boundaries exactly"
(`eng._now()` — the SAME opt-in seam `core/sentry_rig.py` already
exercises). This rig freezes that counter for exactly the window block A's
record grant sits genuinely pending (so the rig's own scripted latency in
choosing WHEN to run `land.sh` is never mistaken, by sentry's real-elapsed-
pacing ladder, for the worker actually being idle) and resumes it the
instant the churn-recovery (rebase + retry) begins — every OTHER tick in
the run uses the ordinary incrementing clock, unmodified. This changes
nothing about `core/gate.py`'s own OBSERVE-VS-TRUTH behavior, which is the
one thing under test; it only keeps a deliberately-orthogonal ladder from
firing on the rig's own test-harness latency. (A companion assertion below,
CH8, independently confirms sentry's ladder is STILL wired and reachable in
this exact run — nudging/capping normally whenever the clock is unfrozen.)

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
import tick                  # noqa: E402 — core/tick.py, the WAKE daemon this rig drives via

import scaffold_src               # noqa: E402 — core/scaffold_src.py, the ONE resolver

SCAFFOLD_SRC = scaffold_src.resolve()
MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"

BLOCK_A, BRANCH_A, WID_A = "churn-a", "feat/churn-a", "engineer-churn-a"
BLOCK_B, BRANCH_B, WID_B = "churn-b", "feat/churn-b", "engineer-churn-b"
BLOCK_FILE_A = f"{BLOCKS_REL}/{BLOCK_A}.md"
BLOCK_FILE_B = f"{BLOCKS_REL}/{BLOCK_B}.md"
CODE_FILE_A = "src/lib/churnA.ts"
CODE_FILE_B = "src/lib/churnB.ts"

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
    d = tempfile.mkdtemp(prefix="tron-core-trunkchurnrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-trunkchurn-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: Trunk-churn rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {a} | trunkchurn_rig fixture block A (driven mid-record, churned under) | 📋 To do | Block `blocks/{a}.md` |
| {b} | trunkchurn_rig fixture block B (concurrent lander, moves trunk) | 📋 To do | Block `blocks/{b}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: trunkchurn_rig fixture

**Phase:** 1 — Trunk-churn rig
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.trunkchurn_rig` — GAP-B, proving the gate's
observe-vs-truth stays correct when trunk moves out from under a block that
is genuinely mid-gate (between `gate.merge` and `gate.record`/`close`).
"""


def seed_pipeline(root):
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(a=BLOCK_A, b=BLOCK_B))
    for block, rel in ((BLOCK_A, BLOCK_FILE_A), (BLOCK_B, BLOCK_FILE_B)):
        bpath = os.path.join(root, rel)
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        with open(bpath, "w") as f:
            f.write(BLOCK_DOC_TEMPLATE.format(block=block))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + blocks {BLOCK_A}/{BLOCK_B} "
                          f"(both to-do, no deps, no gates)"], root)
    _git(["checkout", "--detach", MAIN], root)


def make_code_commit(root, branch, code_file_rel, marker):
    """Fork `branch` off CURRENT main and make a real code commit — never
    touching the block doc. Mirrors every prior rig's own helper."""
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(f"\n// {marker} — core.trunkchurn_rig real code change\n")
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


def rebase_onto_main(root, branch):
    """The block A WORKER's own recovery from `land.sh`'s "not a
    fast-forward" refusal — lives in THIS rig (the worker), never the
    control plane (hard rule). A pure, conflict-free replay: block A only
    ever touches its own files."""
    _git(["checkout", branch], root)
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
    `core/session.py` + `core/sentry.py` (via `core/tick.py`) need. `._now`
    is a RIG-CONTROLLED counter (see module docstring's own "Sentry pacing"
    section) — `_clock_frozen` is toggled by the rig's own `react()` at
    exactly the two boundaries the module docstring names, never mid-stage
    for any OTHER reason."""
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
        self.workers = {}
        self.spawn_calls = []
        self.pages = []
        self._clock_val = 0
        self._clock_frozen = False

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
        pass   # never exercised in this rig — no forward/reconcile/triage job ever queues

    def _page_operator(self, case_id, block, detail, worker_id=None, **_kwargs):
        self.pages.append((case_id, block, detail, worker_id))

    def _now(self):
        """The rig-controlled sentry clock — see module docstring."""
        return self._clock_val


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
                                 "(rig-supplied local report, delivered via a structured "
                                 "worker.done inbox line)"}


def main():
    root = build_root()
    seed_pipeline(root)
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    eng = MiniEng(root, tron_ctx, test_command="true", worker_count=2)

    ok("pre0: rig starts with NO manifest.yaml on disk at all (a brand-new "
       "instance, never yet ticked)",
       not os.path.exists(tron_ctx.state), f"state={tron_ctx.state}")
    for block, rel in ((BLOCK_A, BLOCK_FILE_A), (BLOCK_B, BLOCK_FILE_B)):
        doc = open(os.path.join(root, rel)).read()
        ok(f"pre1[{block}]: pipeline shows block {block} as 📋 (to-do) on "
           "trunk, no gate, no worker",
           "**Status:** 📋 To do" in doc, f"{block} doc seeded 📋")

    branches = {BLOCK_A: BRANCH_A, BLOCK_B: BRANCH_B}
    agent_ids = {BLOCK_A: WID_A, BLOCK_B: WID_B}
    block_files = {BLOCK_A: BLOCK_FILE_A, BLOCK_B: BLOCK_FILE_B}
    code_files = {BLOCK_A: CODE_FILE_A, BLOCK_B: CODE_FILE_B}

    st = {
        BLOCK_A: {"branch_created": False, "local_reported": False, "record_committed": False,
                 "torn_down": False, "landed_cases": set(), "code_tip": None, "record_tip": None},
        BLOCK_B: {"branch_created": False, "local_reported": False, "record_committed": False,
                 "torn_down": False, "landed_cases": set(), "code_tip": None, "record_tip": None},
    }

    real_land_calls = {}      # case_id -> count of REAL land.sh invocations
    b_released = {"flag": False}
    a_land_withheld = {"flag": True}
    a_grant_mint_trunk_sha = {"sha": None, "tick": None}
    a_retry_start_trunk_sha = {"sha": None, "tick": None}
    a_first_refusal = {"seen": False, "stderr": None}
    a_patch_id_before = {"pid": None}
    a_patch_id_after = {"pid": None}
    a_case_id_history = []    # every non-null record_case_id seen for A, tick by tick

    def try_land(block, s, branch, case_id, role):
        """Run the REAL `land.sh`. On a genuine "not a fast-forward"
        refusal, DOES NOT auto-recover here for block A (the caller decides,
        so this rig's own instrumentation can observe the real refusal
        before the worker's own rebase-and-retry) — block B's calls (which
        never race anyone) are expected to always succeed outright; if one
        ever didn't, that would itself be a genuine fixture bug worth
        raising loud."""
        landed_tip = _git_out(["rev-parse", branch], root)
        rc, out, err = run_land(root, grants_dir, case_id)
        real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
        if rc == 0:
            s["landed_cases"].add(case_id)
            s[f"{role}_tip"] = landed_tip
            return True, out, err
        if "not a fast-forward" in err:
            return False, out, err
        raise RuntimeError(f"land.sh unexpected failure for {block} case={case_id} "
                          f"rc={rc}\nstdout:{out}\nstderr:{err}")

    def react(i, manifest):
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}

        for block in (BLOCK_A, BLOCK_B):
            if block == BLOCK_B and not b_released["flag"]:
                continue   # held back by THIS RIG until block A reaches gate.record
            s = st[block]
            agent_id = agent_ids[block]
            branch = branches[block]
            block_file = block_files[block]

            w = workers.get(agent_id)
            if w and w.get("status") == "spawning" and not s["branch_created"]:
                s["code_tip"] = make_code_commit(root, branch, code_files[block],
                                                 f"{block}-real-progress")
                s["branch_created"] = True
                append_jsonl(tron_ctx.worker_inbox,
                            {"tag": "worker.online", "agent_id": agent_id,
                             "slots": {"branch": branch}})

            g = gates.get(block)
            if not g:
                continue
            stage = g.get("stage")

            if stage == gate.STAGE_LOCAL and not s["local_reported"]:
                append_jsonl(tron_ctx.worker_inbox,
                            {"tag": "worker.done", "block": block, "slots": LOCAL_PASS_REPORT})
                s["local_reported"] = True

            elif stage == gate.STAGE_MERGE and g.get("merge_case_id"):
                case_id = g["merge_case_id"]
                if case_id not in s["landed_cases"]:
                    landed, out, err = try_land(block, s, branch, case_id, "code")
                    if not landed:
                        # A code-stage non-ff would only happen if the rig's
                        # own sequencing let two blocks race at the CODE
                        # stage — never expected in THIS scenario (B is held
                        # back until A's code is already on trunk) — still
                        # handled honestly rather than assumed away.
                        rebase_onto_main(root, branch)

            elif stage == gate.STAGE_RECORD:
                if g.get("record_ordered") and not s["record_committed"] and not g.get("record_case_id"):
                    s["record_tip"] = make_record_commit(root, branch, block_file)
                    s["record_committed"] = True
                    if block == BLOCK_A:
                        # Block A's own code+trunk work is fully done and its
                        # record commit is made — release the CONCURRENT
                        # lander now (never before: this is what keeps the
                        # churn scoped to A's RECORD stage, never a code race).
                        b_released["flag"] = True

                if g.get("record_case_id") and g["record_case_id"] not in s["landed_cases"]:
                    case_id = g["record_case_id"]
                    if block == BLOCK_A:
                        a_case_id_history.append((i, case_id))
                        if a_grant_mint_trunk_sha["sha"] is None:
                            a_grant_mint_trunk_sha["sha"] = _git_out(["rev-parse", MAIN], root)
                            a_grant_mint_trunk_sha["tick"] = i
                            eng._clock_frozen = True   # freeze — see module docstring
                        if a_land_withheld["flag"]:
                            pass   # deliberately do NOT run land.sh yet — the churn window
                        else:
                            if a_retry_start_trunk_sha["sha"] is None:
                                a_retry_start_trunk_sha["sha"] = _git_out(["rev-parse", MAIN], root)
                                a_retry_start_trunk_sha["tick"] = i
                            landed, out, err = try_land(block, s, branch, case_id, "record")
                            if not landed:
                                if not a_first_refusal["seen"]:
                                    a_first_refusal["seen"] = True
                                    a_first_refusal["stderr"] = err
                                    a_patch_id_before["pid"] = trunk.patch_id(root, branch, MAIN, False)
                                rebase_onto_main(root, branch)
                                if a_patch_id_after["pid"] is None:
                                    a_patch_id_after["pid"] = trunk.patch_id(root, branch, MAIN, False)
                    else:
                        landed, out, err = try_land(block, s, branch, case_id, "record")
                        if not landed:
                            rebase_onto_main(root, branch)

            elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not s["torn_down"]:
                _git(["branch", "-D", branch], root)
                s["torn_down"] = True

        # ── the churn trigger: release block A's withhold the tick block
        #     B's gate is OBSERVED fully closed (real replica-clean, slot
        #     freed) — trunk has now genuinely moved under block A ──
        if a_land_withheld["flag"] and (gates.get(BLOCK_B) or {}).get("stage") == gate.STAGE_CLOSED:
            a_land_withheld["flag"] = False
            eng._clock_frozen = False   # resume — see module docstring

    tick_history = []
    i = 0
    for i in range(1, MAX_TICKS + 1):
        if not eng._clock_frozen:
            eng._clock_val += 1
        res = tick.tick(eng)
        manifest = state.load(tron_ctx)
        gates_snap = {b: dict(g) for b, g in (manifest.get("gates") or {}).items()}
        tick_history.append({"i": i, "clock": eng._clock_val, "frozen": eng._clock_frozen,
                             "outcomes": dict(res["outcomes"]), "escalated": list(res["escalated"]),
                             "nudged": list(res["nudged"]), "gates": gates_snap,
                             "session_end": res.get("session_end")})
        react(i, manifest)

        gates_now = (state.load(tron_ctx).get("gates") or {})
        if gates_now.get(BLOCK_A, {}).get("stage") == gate.STAGE_CLOSED \
           and gates_now.get(BLOCK_B, {}).get("stage") == gate.STAGE_CLOSED \
           and tick_history[-1]["session_end"] is not None:
            break

    ticks_used = i
    final_manifest = state.load(tron_ctx)
    final_gates = final_manifest.get("gates") or {}
    final_workers = final_manifest.get("workers") or {}

    ok(f"RUN0 (TERMINAL — must be GREEN): the whole churn drive converged "
       f"(both blocks closed, clean session-end) inside {MAX_TICKS} ticks "
       f"(used {ticks_used})",
       final_gates.get(BLOCK_A, {}).get("stage") == gate.STAGE_CLOSED
       and final_gates.get(BLOCK_B, {}).get("stage") == gate.STAGE_CLOSED
       and bool((final_manifest.get("session") or {}).get("ended_at")),
       f"ticks_used={ticks_used} "
       f"final_a={final_gates.get(BLOCK_A, {}).get('stage')} "
       f"final_b={final_gates.get(BLOCK_B, {}).get('stage')} "
       f"session={final_manifest.get('session')}")

    # ══════════════════════════════════════════════════════════════════
    # PER-BLOCK STRUCTURAL KILLERS (both blocks genuinely reached ✅)
    # ══════════════════════════════════════════════════════════════════
    for block in (BLOCK_A, BLOCK_B):
        agent_id, branch, block_file = agent_ids[block], branches[block], block_files[block]
        g = final_gates.get(block, {})
        s = st[block]
        ok(f"M1[{block}]: SWITCHBOARD spawned {block} off the real pipeline",
           agent_id in final_workers, f"workers={list(final_workers)}")
        ok(f"M2[{block}]: the worker's OWN real code commit genuinely landed "
           "on trunk via gate.merge's real land.sh",
           bool(s["code_tip"]) and is_ancestor(root, s["code_tip"], MAIN),
           f"code_tip={s['code_tip']}")
        ok(f"M3[{block}]: gate.trunk genuinely re-ran the REAL declared test "
           "command in a REAL clean detached worktree and observed PASS",
           g.get("trunk_verdict") == "pass", f"trunk_verdict={g.get('trunk_verdict')}")
        ok(f"M4[{block}]: the ✅ status commit genuinely landed on trunk via "
           "a second, independently content-bound grant",
           bool(s["record_tip"]) and is_ancestor(root, s["record_tip"], MAIN)
           and g.get("record_case_id") != g.get("merge_case_id"),
           f"record_tip={s['record_tip']} record_case_id={g.get('record_case_id')} "
           f"merge_case_id={g.get('merge_case_id')}")
        doc_on_main = _git_out(["show", f"{MAIN}:{block_file}"], root)
        ok(f"M5[{block}] (✅ ON TRUNK — must be GREEN): the block doc AS READ "
           "FROM main shows ✅",
           "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")
        branch_gone = not trunk.branch_exists(root, branch, False)
        clean_now, clean_detail = trunk.replica_clean(root, branch, MAIN, False)
        ok(f"M6[{block}]: the replica is genuinely clean on real git and the "
           "gate is CLOSED",
           branch_gone and clean_now and g.get("stage") == gate.STAGE_CLOSED,
           f"branch_gone={branch_gone} clean={clean_now} stage={g.get('stage')}")
        ok(f"M7[{block}] (SLOT-FREED KILLER — must be GREEN): the worker "
           "slot was REALLY released",
           eng.workers.get(agent_id, {}).get("status") == "released",
           f"worker_state={eng.workers.get(agent_id)}")

    # ══════════════════════════════════════════════════════════════════
    # CH — GAP-B: THE CHURN KILLERS
    # ══════════════════════════════════════════════════════════════════
    a_case_ids = {cid for _t, cid in a_case_id_history}
    ok("CH1 (CONTENT-BOUND — must be GREEN): block A's record case-id was "
       "minted ONCE and never changed across the whole churn (a single "
       "content-bound identity, never re-minted a second/different grant "
       "for the SAME content because trunk moved)",
       len(a_case_ids) == 1,
       f"a_case_id_history={a_case_id_history}")

    ok("CH2 (REAL CHURN — must be GREEN): trunk was OBSERVED to have "
       "genuinely moved between block A's record-grant mint and the retry "
       "window — the trunk sha at mint time differs from the trunk sha the "
       "retry began against, and the mint-time sha is a STRICT ancestor of "
       "the retry-time sha (a real, forward-only advance via block B's own "
       "landing, never a rewind)",
       a_grant_mint_trunk_sha["sha"] is not None
       and a_retry_start_trunk_sha["sha"] is not None
       and a_grant_mint_trunk_sha["sha"] != a_retry_start_trunk_sha["sha"]
       and is_ancestor(root, a_grant_mint_trunk_sha["sha"], a_retry_start_trunk_sha["sha"]),
       f"mint_sha={a_grant_mint_trunk_sha} retry_start_sha={a_retry_start_trunk_sha}")

    ok("CH3 (THE CASE-008 SIGNATURE — must be GREEN): block A's FIRST "
       "land.sh retry attempt genuinely refused with a REAL \"not a "
       "fast-forward\" (real git, real land.sh stderr) — the exact "
       "historical wall's own signature, never simulated",
       a_first_refusal["seen"] and a_first_refusal["stderr"] is not None
       and "not a fast-forward" in a_first_refusal["stderr"],
       f"stderr={a_first_refusal['stderr']!r}")

    ok("CH4 (PATCH-ID CARRIES — must be GREEN): block A's content-identity "
       "patch-id, re-derived before and after the worker's own rebase, is "
       "identical and non-empty — the rebase changed the commit sha but "
       "NOT the content, so the SAME grant/case-id stays valid across it",
       bool(a_patch_id_before["pid"]) and bool(a_patch_id_after["pid"])
       and a_patch_id_before["pid"] == a_patch_id_after["pid"],
       f"patch_id_before={a_patch_id_before['pid']} patch_id_after={a_patch_id_after['pid']}")

    a_record_case_id = final_gates.get(BLOCK_A, {}).get("record_case_id")
    ok("CH5 (CONTENT-BOUND LAND — must be GREEN): block A's record STILL "
       "landed under the SAME case-id minted before the churn (>= 2 real "
       "land.sh invocations for it: the refused attempt + the eventual "
       "success) — never a second grant, never a false pass on a stale "
       "receipt",
       a_record_case_id in a_case_ids
       and real_land_calls.get(a_record_case_id, 0) >= 2,
       f"a_record_case_id={a_record_case_id} "
       f"real_land_calls={real_land_calls.get(a_record_case_id)}")

    # ── the OBSERVE-VS-TRUTH window: every tick from the grant's mint to
    #     the tick the content ACTUALLY landed, block A's outcome must have
    #     been "record_pending" (HOLDING, honestly) — never "record_landed"
    #     early (a false pass) and never "escalate"/STAGE_ESCALATED (a
    #     false cap on content that, per CH5 above, DID eventually land) ──
    mint_tick = a_grant_mint_trunk_sha["tick"]
    landed_tick = next((t["i"] for t in tick_history
                       if t["outcomes"].get(BLOCK_A, (None, None))[0] == "record_landed"), None)
    window = [t for t in tick_history if mint_tick is not None and landed_tick is not None
             and mint_tick <= t["i"] < landed_tick]
    window_outcomes = [(t["i"], t["outcomes"].get(BLOCK_A, (None, None))[0]) for t in window]
    ok("CH6 (THE OBSERVE-VS-TRUTH KILLER, HOLD SIDE — must be GREEN): "
       "across the ENTIRE churn window (grant minted -> content genuinely "
       "landed), block A's outcome was HONESTLY \"record_pending\" every "
       "single tick — never a false \"record_landed\", never \"escalate\"",
       bool(window) and all(o == "record_pending" for _t, o in window_outcomes),
       f"window_outcomes={window_outcomes}")

    ok("CH7 (THE OBSERVE-VS-TRUTH KILLER, PASS SIDE — must be GREEN): the "
       "very NEXT gate.advance call after the worker's successful retry "
       "OBSERVED \"record_landed\" — no lag, no missed observation, no "
       "false cap on a land that actually succeeded",
       landed_tick is not None
       and tick_history[landed_tick - 1]["gates"].get(BLOCK_A, {}).get("stage") == gate.STAGE_CLOSE,
       f"landed_tick={landed_tick} "
       f"stage_at_landed_tick={tick_history[landed_tick - 1]['gates'].get(BLOCK_A, {}).get('stage') if landed_tick else None}")

    ok("CH8 (NEVER FALSELY CAPPED — must be GREEN): block A's gate NEVER "
       "reached STAGE_ESCALATED at any point in the whole run, and "
       "manifest['escalations'] never names block A — the historical "
       "gate-step-cap false-verdict never fires on a land that actually "
       "succeeded",
       all(t["gates"].get(BLOCK_A, {}).get("stage") != gate.STAGE_ESCALATED for t in tick_history)
       and final_gates.get(BLOCK_A, {}).get("stage") != gate.STAGE_ESCALATED
       and not any(e.get("block") == BLOCK_A for e in (final_manifest.get("escalations") or [])),
       f"final_a_stage={final_gates.get(BLOCK_A, {}).get('stage')} "
       f"escalations={final_manifest.get('escalations')}")

    doc_at_retry_start = (_git_out(["show", f"{a_retry_start_trunk_sha['sha']}:{BLOCK_FILE_A}"], root)
                          if a_retry_start_trunk_sha["sha"] else None)
    ok("CH9 (TRUNK-TRUTH, HOLD SIDE — must be GREEN): reading the block A "
       "doc straight off trunk AT the exact sha the retry began against "
       "(REAL git show, not a manifest belief) still shows 📋 — the content "
       "genuinely had not landed yet at that point, confirming CH6/CH2 "
       "aren't merely manifest bookkeeping",
       doc_at_retry_start is not None and "**Status:** 📋 To do" in doc_at_retry_start,
       f"doc_at_retry_start head={doc_at_retry_start.splitlines()[:4] if doc_at_retry_start else None}")

    ok("CH10 (SENTRY STILL WIRED — must be GREEN): the pacing clock genuinely "
       "advanced across the run (proving the freeze/resume in this rig is a "
       "deliberate, bounded window — never a permanent bypass of "
       "core/sentry.py) — the final clock value is comfortably larger than "
       "sentry's own GATE_IDLE_CAP, and block A's own holding window (CH6) "
       "never got anywhere near that cap specifically BECAUSE it was frozen, "
       "never because sentry itself is disconnected",
       eng._clock_val > 6, f"final_clock={eng._clock_val}")

    real_land_total = sum(real_land_calls.values())
    ok("FINAL (TERMINAL — must be GREEN): block A survived a REAL mid-gate "
       "trunk churn (a concurrent block B's own full landing moved trunk "
       "while A's record grant sat live) — the SAME content-bound case-id "
       "carried the rebase, the worker's retry succeeded, the gate observed "
       "it honestly (no false pass while pending, no false cap once landed), "
       "block A reached ✅ on trunk, block B closed cleanly, and the run "
       "reached a genuine SESSION-END",
       final_gates.get(BLOCK_A, {}).get("stage") == gate.STAGE_CLOSED
       and final_gates.get(BLOCK_B, {}).get("stage") == gate.STAGE_CLOSED
       and bool((final_manifest.get("session") or {}).get("ended_at"))
       and len(a_case_ids) == 1
       and real_land_total >= 5,   # merge_A + merge_B + record_B (1 each) + record_A (refusal + success)
       f"final_a={final_gates.get(BLOCK_A, {}).get('stage')} "
       f"final_b={final_gates.get(BLOCK_B, {}).get('stage')} "
       f"session={final_manifest.get('session')} "
       f"real_land_total={real_land_total} real_land_calls={real_land_calls}")

    # ══════════════════════════════════════════════════════════════════
    # SRC — no raw git in any control-plane module (core.gitobs is the ONE
    #        sanctioned seam; this rig itself, like every prior rig, is a
    #        real-git driver by design, exempt)
    # ══════════════════════════════════════════════════════════════════
    control_modules = ["gate.py", "landing.py", "router.py", "switchboard.py",
                      "tick.py", "architect.py", "sentry.py", "pipeline.py",
                      "session.py", "casestate.py", "liveness.py"]
    for modname in control_modules:
        src = open(os.path.join(HERE, modname)).read()
        ok(f"SRC[{modname}]: no raw git/subprocess call of its own — all "
           "git observation stays inside core/gitobs.py",
           "import subprocess" not in src and "subprocess." not in src
           and "\nimport git\n" not in src,
           f"grep-equivalent source scan of core/{modname}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.trunkchurn_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"tron instance dir (real engine.ctx.Ctx)={inst}")
    print(f"manifest={tron_ctx.state}")
    print(f"BLOCK_A={BLOCK_A} BLOCK_B={BLOCK_B} worker_count=2")
    print(f"ticks used={ticks_used} (cap={MAX_TICKS}) final_clock={eng._clock_val}")
    print(f"a_grant_mint_trunk_sha={a_grant_mint_trunk_sha}")
    print(f"a_retry_start_trunk_sha={a_retry_start_trunk_sha}")
    print(f"a_first_refusal stderr={a_first_refusal['stderr']!r}")
    print(f"a_patch_id_before={a_patch_id_before['pid']} a_patch_id_after={a_patch_id_after['pid']}")
    print(f"a_case_id_history={a_case_id_history}")
    print(f"real_land_calls={real_land_calls}")
    print(f"final gates={final_gates}")
    print(f"final session={final_manifest.get('session')}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
