"""core.classify_rig — real-git, TRON_JUDGE_STUB-deterministic rig proving
`core.classify` (wave 13: the ONE LLM judgment, pinned to the OBSERVE phase
so `decide`/`route`/`act` stay pure — `contracts/rebuild-spec.md` T2/T5).

NO real LLM call anywhere in this rig — `TRON_JUDGE_STUB` (`engine/judge.py`
's own offline-testability contract) stands in for `classify_message`,
exactly the way `engine/e2e_test.py::report` already drives it: a canned
`{"classify_message": [...]}` JSON file, `judge._stub_cache`/`_stub_idx`
reset before each canned response is queued, so every scenario below is
byte-reproducible. Real surface for everything ELSE: a real `git init` repo
copied from the same scaffold `core/dispatch_rig.py`/`core/architect_rig.py`
use, a REAL `engine.ctx.Ctx`, `core.tick.tick(eng)` as the WAKE daemon —
never a faked trunk, never a faked pipeline read.

Two scenarios:

  SCENARIO 1 (real-tick integration) — ONE block from a real 📋 pipeline row,
  driven via `core.tick.tick`: a STRUCTURED `worker.online` report ASSIGNs
  the gate with the model NEVER consulted (AC-1), then a genuinely FREE-TEXT
  local-pass report ("01-01 is done...") is classified by the stub into
  `{tag: worker.done, slots: {block: 01-01, verdict: pass, evidence: ...}}`
  and drives the SAME gate from `gate.local` to `gate.merge` (AC-2) — the
  real classify path, wired through `core/snapshot.py`'s observe pass,
  entirely deterministic via the stub. Judge-call-count instrumentation
  (monkeypatched counters around `judge.call`/`snapshot.build`/
  `router.route`/`gate.advance`) proves the ONE model touch happens inside
  `snapshot.build` (observe) and NEVER inside `router.route`/`gate.advance`
  (route/decide/act) — AC-5.

  SCENARIO 2 (direct unit calls) — `core.classify.classify` exercised
  directly against a plain manifest dict (no tick/gate machinery needed to
  prove these): a structured report bypasses the model too (AC-1, unit
  level); an out-of-enum tag retried-then-exhausted collapses to
  `unclassified` -> a real architect triage job queued + the raw body
  logged, never a crash (AC-3); an ENGINE_ONLY tag (`worker.stalled`) is
  rejected the identical way, since a classifier is never allowed to emit an
  engine-produced tag (AC-4); the deterministic operator CASE-<n> settle
  regex is proven too (bonus — "keep it working", per the design).

Plus a structural/grep proof (`judge.call` appears in exactly ONE `core/
*.py` module, `classify.py`) and, at the end, a live re-run of all 12 prior
`core/*_rig.py` fixtures as subprocesses — wave 13 is purely additive; every
one of them still sends only structured inbox lines, so `classify()` is a
same-tag echo for all of them, zero behavior change.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # judge.py / ctx.py / grants.py / trunk.py
sys.path.insert(0, HERE)                                 # core/{classify,gate,state,snapshot,tick,...}.py

import util                  # noqa: E402 — engine/util.py, atomic_write/append_jsonl (respected)
import judge                  # noqa: E402 — engine/judge.py, the ONE LLM seam (stubbed throughout)
import trunk                   # noqa: E402 — respected contract, real, unmodified
from ctx import Ctx             # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import gate                      # noqa: E402 — core/gate.py, the DONE ladder core.tick drives
import state                      # noqa: E402 — core/state.py
import snapshot                    # noqa: E402 — core/snapshot.py, wave 13's observe-phase wiring
import router                       # noqa: E402 — core/router.py, structured ASSIGN (must stay LLM-free)
import tick                          # noqa: E402 — core/tick.py, the whole per-tick pass
import classify                       # noqa: E402 — core/classify.py, the module under test
import architect                       # noqa: E402 — core/architect.py, log-review job (triage reuse)
import casestate                        # noqa: E402 — core/casestate.py, VERBS + case-id shape

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
MAIN = "main"
CODE_FILE_REL = "src/lib/tip.ts"
BLOCK = "01-01"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"
BLOCK_FILE_REL = f"{BLOCKS_REL}/{BLOCK}.md"
BRANCH = f"feat/{BLOCK}"
AGENT_ID = f"engineer-{BLOCK}"

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers (same convention as core/dispatch_rig.py) ──
def _git(args, cwd, check=True):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}) rc={r.returncode}\n"
                           f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return r


def _git_out(args, cwd):
    return _git(args, cwd).stdout.strip()


def build_root():
    d = tempfile.mkdtemp(prefix="tron-core-classifyrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-classify-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: classify_rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {block} | classify_rig fixture block | 📋 To do | Block `blocks/{block}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: classify_rig fixture

**Phase:** 1 — classify_rig
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.classify_rig` — proves wave 13's ONE LLM
judgment (`core/classify.py::classify_message`) is pinned to the OBSERVE
phase: a structured report bypasses it entirely; a genuinely free-text
report is the one place it's touched, deterministically via
`TRON_JUDGE_STUB`.
"""


def seed_pipeline(root):
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(block=BLOCK))
    bpath = os.path.join(root, BLOCK_FILE_REL)
    os.makedirs(os.path.dirname(bpath), exist_ok=True)
    with open(bpath, "w") as f:
        f.write(BLOCK_DOC_TEMPLATE.format(block=BLOCK))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + block {BLOCK} (to-do, no gate)"], root)
    _git(["checkout", "--detach", MAIN], root)


def make_code_commit(root, branch, code_file_rel, marker):
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    with open(path, "a") as f:
        f.write(f"\n// {marker} — core.classify_rig real code change\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"feat({branch}): {marker}"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


class _Events:
    def __init__(self):
        self.log = []

    def event(self, type_, **payload):
        self.log.append({"type": type_, "payload": payload})


class MiniEng:
    """The minimal duck-typed `eng` — everything `core/gate.py` + `core/
    pipeline.py` + `core/switchboard.py` + `core/router.py` + `core/
    classify.py` need. `.ctx` is a REAL `engine.ctx.Ctx`, so `eng.ctx.
    load_routing()` (`classify.py`'s own max_retries read) and `judge.call`
    's own `_v_classify` validator (which ALSO reads `ctx.routing`) resolve
    against a REAL `routing.yaml` — the actual repo-root canon file, copied
    verbatim (never hand-authored/forked for this rig)."""

    def __init__(self, root, tron_ctx, worker_count=1):
        self.paths = {
            "root": root,
            "main_branch": MAIN,
            "test_command": "true",
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
        pass

    def _page_operator(self, case_id, block, detail, worker_id=None, **_kwargs):
        # **_kwargs: wave 17 (GAP-A) widened the real `eng._page_operator`
        # call surface (`manifest=`/`page_kind=`, `core/casestate.py`'s own
        # THE-FLOOR re-ping ladder) — this rig's own stub never needed
        # either, so it just tolerates and ignores them (never weakens any
        # assertion this rig already makes).
        self.log_lines.append(("operator_page", f"{case_id} {block} {detail}"))


def _tron_ctx(root):
    """A real `engine.ctx.Ctx` under `root`, with the REAL repo-root
    `routing.yaml` copied in verbatim (`judge.py`'s validator + `classify.py`
    's own `invalid_output.max_retries` read both need it on disk — reused
    AS-IS, per the hard rule, never a rig-authored fork of it)."""
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    ctx = Ctx(inst)
    shutil.copy(os.path.join(APP_ROOT, "routing.yaml"), ctx.routing)
    return ctx


def _set_stub(ctx, tag, slots, confidence=0.9):
    """Exactly `engine/e2e_test.py::report`'s own stub-priming discipline:
    write ONE canned `classify_message` response, point `TRON_JUDGE_STUB` at
    it, and reset BOTH `judge._stub_cache`/`_stub_idx` so the fresh file is
    re-read and the per-tool pop-index restarts at 0 for this call."""
    stub = {"classify_message": [{"tag": tag, "slots": slots, "confidence": confidence}]}
    stub_path = os.path.join(ctx.dir, "stub.json")
    util.atomic_write(stub_path, json.dumps(stub))
    os.environ["TRON_JUDGE_STUB"] = stub_path
    judge._stub_cache = None
    judge._stub_idx.clear()


# ═══════════════════════════════════════════════════════════════════════
# call-count instrumentation — proves the model is touched ONLY inside
# core.snapshot.build (observe), NEVER inside core.router.route or
# core.gate.advance (route/decide/act) — AC-5.
# ═══════════════════════════════════════════════════════════════════════
_judge_call_count = [0]
_route_deltas = []
_advance_deltas = []
_snapshot_deltas = []


def _instrument():
    orig_judge_call = judge.call
    orig_route = router.route
    orig_advance = gate.advance
    orig_build = snapshot.build

    def counting_judge_call(*a, **kw):
        _judge_call_count[0] += 1
        return orig_judge_call(*a, **kw)

    def wrapped_route(*a, **kw):
        before = _judge_call_count[0]
        r = orig_route(*a, **kw)
        _route_deltas.append(_judge_call_count[0] - before)
        return r

    def wrapped_advance(*a, **kw):
        before = _judge_call_count[0]
        r = orig_advance(*a, **kw)
        _advance_deltas.append(_judge_call_count[0] - before)
        return r

    def wrapped_build(*a, **kw):
        before = _judge_call_count[0]
        r = orig_build(*a, **kw)
        _snapshot_deltas.append(_judge_call_count[0] - before)
        return r

    judge.call = counting_judge_call
    router.route = wrapped_route
    gate.advance = wrapped_advance
    snapshot.build = wrapped_build
    return orig_judge_call, orig_route, orig_advance, orig_build


def _restore(orig_judge_call, orig_route, orig_advance, orig_build):
    judge.call = orig_judge_call
    router.route = orig_route
    gate.advance = orig_advance
    snapshot.build = orig_build


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 1 — real-tick integration (structured bypass + free-text drive)
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_1():
    root = build_root()
    seed_pipeline(root)
    tron_ctx = _tron_ctx(root)
    eng = MiniEng(root, tron_ctx, worker_count=1)

    orig = _instrument()
    try:
        # ── tick 1: SWITCHBOARD spawns the block off the real pipeline ──
        os.environ.pop("TRON_JUDGE_STUB", None)
        res1 = tick.tick(eng)
        ok("S1-A0: SWITCHBOARD spawned block 01-01 off the real 📋 pipeline "
           "row (identity-only, no report yet)",
           res1["spawned"] == [AGENT_ID], f"spawned={res1['spawned']}")

        # ── the rig-as-worker forks its OWN branch, reports online via a
        #     STRUCTURED line (`{"tag": "worker.online", ...}`) ──
        make_code_commit(root, BRANCH, CODE_FILE_REL, f"{BLOCK}-classifyrig-change")
        util.append_jsonl(tron_ctx.worker_inbox,
                          {"tag": "worker.online", "agent_id": AGENT_ID,
                           "slots": {"branch": BRANCH}})

        idx_before = dict(judge._stub_idx)
        count_before = _judge_call_count[0]

        # ── tick 2: ASSIGN — the structured report resolves via
        #     classify.py's own structured-bypass check; the model must
        #     NEVER be consulted for it (AC-1) ──
        res2 = tick.tick(eng)
        manifest2 = state.load(tron_ctx)
        gate2 = (manifest2.get("gates") or {}).get(BLOCK, {})

        ok("S1-K1 (STRUCTURED-BYPASS KILLER — must be GREEN): the "
           "structured worker.online report ASSIGNed the gate (gate.local "
           "opened, bound to the worker's OWN reported branch) with the "
           "judge NEVER invoked — zero judge.call()s this tick",
           gate2.get("stage") == gate.STAGE_LOCAL and gate2.get("branch") == BRANCH
           and _judge_call_count[0] == count_before,
           f"stage={gate2.get('stage')} branch={gate2.get('branch')} "
           f"judge_calls_this_tick={_judge_call_count[0] - count_before}")
        ok("S1-K1b: the stub queue itself was never popped for this "
           "structured report (belt-and-suspenders on the same claim)",
           dict(judge._stub_idx) == idx_before,
           f"stub_idx_before={idx_before} stub_idx_after={dict(judge._stub_idx)}")

        # ── the rig-as-worker's local pass, delivered as GENUINELY
        #     FREE TEXT — no `tag` key at all, `classify_message`'s own
        #     {text, sender} input shape — classified by the stub into
        #     worker.done ──
        evidence = ("npm ci --no-audit --no-fund && npx vitest run -> 9/9 "
                    "green (rig-supplied local pass, delivered via a "
                    "FREE-TEXT inbox line, classified by the stubbed judge)")
        _set_stub(tron_ctx, "worker.done",
                 {"block": BLOCK, "verdict": "pass", "evidence": evidence})
        util.append_jsonl(
            tron_ctx.worker_inbox,
            {"text": f"{BLOCK} is done — {evidence}",
             "sender": {"kind": "worker", "id": AGENT_ID}})

        count_before_3 = _judge_call_count[0]
        route_before = len(_route_deltas)
        advance_before = len(_advance_deltas)
        snap_before = len(_snapshot_deltas)

        # ── tick 3: the ONE real classify_message call — free text -> the
        #     stubbed tag -> the SAME gate's local_report -> advances past
        #     gate.local (AC-2) ──
        res3 = tick.tick(eng)
        manifest3 = state.load(tron_ctx)
        gate3 = (manifest3.get("gates") or {}).get(BLOCK, {})

        ok("S1-K2 (FREE-TEXT-CLASSIFIES KILLER — must be GREEN): the "
           "free-text report was classified into worker.done and fed the "
           "gate's local_report — the SAME block's gate advanced from "
           "gate.local to gate.merge this tick",
           gate3.get("stage") == gate.STAGE_MERGE,
           f"stage_after={gate3.get('stage')} outcomes={res3.get('outcomes')}")
        ok("S1-K3: exactly ONE judge.call() fired this tick (one free-text "
           "line drained -> one classify_message call, never more)",
           _judge_call_count[0] - count_before_3 == 1,
           f"judge_calls_this_tick={_judge_call_count[0] - count_before_3}")
        ok("S1-K4: the stub was popped EXACTLY once for this call",
           judge._stub_idx.get("classify_message") == 1,
           f"stub_idx={dict(judge._stub_idx)}")

        # ── AC-5: the model touch happened inside snapshot.build (observe)
        #     and NEVER inside router.route or gate.advance (route/act) ──
        new_snapshot_deltas = _snapshot_deltas[snap_before:]
        new_route_deltas = _route_deltas[route_before:]
        new_advance_deltas = _advance_deltas[advance_before:]
        ok("S1-K5 (OBSERVE-ONLY KILLER — must be GREEN): the ONE model call "
           "happened INSIDE core.snapshot.build (the observe pass) this "
           "tick — never inside core.router.route or core.gate.advance "
           "(route/decide/act stayed at zero model calls, structurally)",
           sum(new_snapshot_deltas) == 1
           and all(d == 0 for d in new_route_deltas)
           and all(d == 0 for d in new_advance_deltas),
           f"snapshot_deltas={new_snapshot_deltas} route_deltas={new_route_deltas} "
           f"advance_deltas={new_advance_deltas}")

        print("\n== SCENARIO 1 (real-tick integration) ==")
        print(f"root={root}")
        print(f"tron instance dir={tron_ctx.dir}")
        print(f"gate after tick2 (ASSIGN, structured)={gate2}")
        print(f"gate after tick3 (free-text classify)={gate3}")
        print(f"judge_call_count(total)={_judge_call_count[0]}")
        print(f"route_deltas={_route_deltas} advance_deltas={_advance_deltas} "
              f"snapshot_deltas={_snapshot_deltas}")
    finally:
        _restore(*orig)
        os.environ.pop("TRON_JUDGE_STUB", None)


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 2 — direct unit calls: invalid/out-of-enum, ENGINE_ONLY,
# structured bypass (unit level), CASE-<n> settle regex
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_2():
    root = build_root()   # only needed for a real routing.yaml-bearing ctx; no pipeline/tick here
    tron_ctx = _tron_ctx(root)
    eng = MiniEng(root, tron_ctx, worker_count=1)
    manifest = {}

    # ── unit-level structured bypass: model never touched ──
    _set_stub(tron_ctx, "SHOULD-NEVER-BE-POPPED", {})
    idx_before = dict(judge._stub_idx)   # captured AFTER the reset _set_stub itself performs
    tag, slots = classify.classify(
        eng, {"tag": "worker.done", "block": BLOCK,
              "slots": {"verdict": "pass", "evidence": "x"}}, manifest)
    ok("S2-K1: a structured report resolves via classify.classify() with "
       "the model NEVER consulted (unit level — the stub queue is never "
       "popped even though a poisoned response was primed)",
       tag == "worker.done" and slots == {"verdict": "pass", "evidence": "x"}
       and dict(judge._stub_idx) == idx_before,
       f"tag={tag} slots={slots} stub_idx_before={idx_before} "
       f"stub_idx_after={dict(judge._stub_idx)}")

    # ── invalid/out-of-enum tag -> unclassified -> architect triage
    #     (wave 18/GAP-E: a case-less PMT-TRIAGE job, architect-first),
    #     logged with the raw body, never a crash, never a direct
    #     operator page ──
    raw_text_invalid = "the deploy pipeline is on fire, someone please look"
    _set_stub(tron_ctx, "totally.not.a.real.tag", {"note": "made up"})
    queue_len_before = len(manifest.get("architect_queue") or [])
    tag2, slots2 = classify.classify(
        eng, {"text": raw_text_invalid, "sender": {"kind": "worker", "id": "engineer-99"}},
        manifest)
    queue_after = manifest.get("architect_queue") or []
    triage_job = next((j for j in queue_after if j.get("kind") == "triage"
                       and j.get("case_id") is None
                       and j.get("source") == "classify.unclassified"), None)
    ok("S2-K2 (INVALID-OUTPUT KILLER — must be GREEN): an out-of-enum tag "
       "from the judge collapses to unclassified — never a guessed flow "
       "decision, never a crashed classify",
       tag2 == "unclassified", f"tag2={tag2}")
    ok("S2-K3 (ARCHITECT-TRIAGE KILLER — must be GREEN): unclassified was "
       "handed to the architect FIRST as a real, case-less PMT-TRIAGE job "
       "(kind=triage, case_id=None, source=classify.unclassified) — a "
       "genuine scope_forward/answer/operator triage, never a direct "
       "operator page, never a second LLM call",
       len(queue_after) == queue_len_before + 1 and triage_job is not None
       and triage_job.get("detail") == raw_text_invalid
       and triage_job.get("worker_id") == "engineer-99",
       f"queue_before={queue_len_before} queue_after={queue_after}")
    ok("S2-K4 (FORENSIC-LOG KILLER — must be GREEN): the raw body was "
       "logged (both the home-log line AND a durable events.event record) "
       "— never silently swallowed",
       any(raw_text_invalid in msg for _ch, msg in eng.log_lines)
       and any(e["type"] == "unclassified" and e["payload"].get("raw") == raw_text_invalid
              for e in eng.events.log),
       f"log_lines_tail={eng.log_lines[-2:]} events_tail={eng.events.log[-2:]}")

    # ── ENGINE_ONLY tag rejected — a classifier is never allowed to emit
    #     an engine-produced tag (worker.stalled/worker.dead) ──
    raw_text_engine_only = "worker-07 hasn't said anything in ages, is it dead?"
    _set_stub(tron_ctx, "worker.stalled", {})
    queue_len_before2 = len(manifest.get("architect_queue") or [])
    tag3, _slots3 = classify.classify(
        eng, {"text": raw_text_engine_only, "sender": {"kind": "worker", "id": "engineer-01"}},
        manifest)
    queue_after2 = manifest.get("architect_queue") or []
    ok("S2-K5 (ENGINE-ONLY-REJECTED KILLER — must be GREEN): worker.stalled "
       "(engine-liveness-produced only) from the classifier is rejected as "
       "invalid output, same as any other out-of-enum tag -> unclassified",
       tag3 == "unclassified" and len(queue_after2) == queue_len_before2 + 1,
       f"tag3={tag3} queue_len_before={queue_len_before2} queue_len_after={len(queue_after2)}")

    # ── deterministic operator CASE-<n> settle regex (bonus — "keep it
    #     working", the design's own words) — zero model calls ──
    settle_manifest = {"cases": {"case-01-01-1": {
        "case_id": "case-01-01-1", "block": BLOCK, "source": "worker.wall",
        "decision": None, "detail": "walled"}}}
    _set_stub(tron_ctx, "SHOULD-NEVER-BE-POPPED-EITHER", {})
    idx_before2 = dict(judge._stub_idx)   # captured AFTER the reset _set_stub itself performs
    tag4, slots4 = classify.classify(
        eng, {"text": "please resume case-01-01-1, all clear now",
              "sender": {"kind": "operator", "id": "the-operator"}},
        settle_manifest)
    ok("S2-K6 (BONUS — CASE-SETTLE-REGEX KILLER): an operator's free text "
       "naming a GENUINELY open case id + a settle verb resolves to "
       "operator.decision via a deterministic regex, zero model calls",
       tag4 == "operator.decision" and slots4 == {"case_id": "case-01-01-1", "verb": "resume"}
       and dict(judge._stub_idx) == idx_before2,
       f"tag4={tag4} slots4={slots4}")

    # ── the SAME text against a manifest with NO open case at all must NOT
    #     misfire — falls through to the (stubbed) real judgment instead ──
    _set_stub(tron_ctx, "operator.status_query", {})
    tag5, _slots5 = classify.classify(
        eng, {"text": "please resume case-01-01-1, all clear now",
              "sender": {"kind": "operator", "id": "the-operator"}},
        {"cases": {}})
    ok("S2-K7: the same CASE-<n>-shaped text against a manifest with NO "
       "open case falls through to the real judgment (never a false-"
       "positive settle for a case that doesn't exist)",
       tag5 == "operator.status_query", f"tag5={tag5}")

    print("\n== SCENARIO 2 (direct unit calls) ==")
    print(f"tron instance dir={tron_ctx.dir}")
    print(f"final architect_queue={manifest.get('architect_queue')}")
    print(f"events tail={eng.events.log[-6:]}")


# ═══════════════════════════════════════════════════════════════════════
# structural / grep proof — judge.call lives in exactly ONE core/*.py
# module (classify.py); no raw git/subprocess crept into the edited files
# ═══════════════════════════════════════════════════════════════════════
def run_grep_proof():
    core_files = sorted(
        f for f in os.listdir(HERE)
        if f.endswith(".py") and not f.endswith("_rig.py") and f != "__init__.py")
    judge_call_files = []
    for fname in core_files:
        with open(os.path.join(HERE, fname)) as fh:
            text = fh.read()
        if re.search(r"\bjudge\.call\s*\(", text):
            judge_call_files.append(fname)
    ok("G1 (GREP PROOF — must be GREEN): judge.call(...) appears in EXACTLY "
       "ONE core/*.py module (classify.py) — decide/route/act never touch it",
       judge_call_files == ["classify.py"], f"judge_call_files={judge_call_files}")

    for fname in ("classify.py", "snapshot.py", "router.py", "tick.py"):
        with open(os.path.join(HERE, fname)) as fh:
            text = fh.read()
        # ACTUAL code usage only (`import subprocess` / `subprocess.run(...)`
        # etc.) — every one of these files' own docstrings mentions the word
        # "subprocess" in prose ("No git/subprocess of any kind here..."),
        # which must never false-positive this check.
        has_subprocess = bool(re.search(
            r"^\s*import subprocess\b|subprocess\.(run|Popen|call|check_output|check_call)\s*\(",
            text, re.MULTILINE))
        has_raw_git = bool(re.search(r"^\s*\[?[\"']git[\"']|\bimport git\b", text, re.MULTILINE))
        ok(f"G2[{fname}]: no raw subprocess/git call introduced (no raw git "
           "outside core.gitobs/core.state IO)",
           not has_subprocess and not has_raw_git,
           f"has_subprocess={has_subprocess} has_raw_git={has_raw_git}")


# ═══════════════════════════════════════════════════════════════════════
# all 12 prior core/*_rig.py fixtures — wave 13 is purely additive; every
# one of them sends only structured inbox lines, so classify() is a
# same-tag echo for all of them, zero behavior change
# ═══════════════════════════════════════════════════════════════════════
PRIOR_RIGS = ["landing_rig", "gate_rig", "gate_full_rig", "tick_rig", "dispatch_rig",
              "multiblock_rig", "sentry_rig", "casestate_rig", "architect_rig",
              "reviewers_rig", "liveness_rig", "engine_rig"]


def run_prior_rigs():
    env = dict(os.environ)
    env.pop("TRON_JUDGE_STUB", None)
    for name in PRIOR_RIGS:
        path = os.path.join(HERE, f"{name}.py")
        r = subprocess.run([sys.executable, path], cwd=HERE, capture_output=True,
                           text=True, env=env, timeout=600)
        last_line = next((ln for ln in reversed(r.stdout.strip().splitlines())
                          if ln.strip().startswith(f"core.{name}:")), "")
        ok(f"P[{name}]: still fully green after wave 13's snapshot/router/"
           f"tick edits (subprocess exit={r.returncode})",
           r.returncode == 0, last_line or (r.stdout[-300:] + r.stderr[-300:]))


def run_scenario_self_triage_guard():
    """s3 first-honest-SIM lock: an UNCLASSIFIED message from the architect
    ITSELF never spawns a new triage — it resolves its OWN in-flight triage
    benignly (or drops as narration) — never the phantom-triage self-loop that
    left the triage unresolved and wedged the architect busy at session-end.
    A real worker's unclassified message STILL triages (GAP-E net intact)."""
    root = build_root()
    tron_ctx = _tron_ctx(root)
    eng = MiniEng(root, tron_ctx, worker_count=1)
    arch_id = architect.ARCHITECT_WID
    mA = {"architect": {"status": "busy",
                        "current_job": {"kind": "triage", "triage_id": "triage-1",
                                        "worker_id": "engineer-01-03"}},
          "architect_queue": []}
    classify._triage_unclassified(
        eng, mA, "Sorted: it's a branch declaration, no architect action.",
        {"kind": "worker", "id": arch_id}, ["unclassified"])
    ok("SG1 (SELF-SOURCE CREATION GUARD, R1a — must be GREEN): architect narration "
       "of its own in-flight triage creates NOTHING — no new triage AND no verdict "
       "write. The old source-AGNOSTIC benign 'answer' write is deleted: it swallowed "
       "a GENUINE worker.wall the instant the architect narrated (M1). Resolution of "
       "the in-flight triage is now the R1b architect-idle backstop, never narration",
       not (mA.get("triage_verdicts") or {})
       and len(mA.get("architect_queue") or []) == 0,
       f"verdicts={mA.get('triage_verdicts')} queue={mA.get('architect_queue')}")
    mB = {"architect": {"status": "idle", "current_job": None}, "architect_queue": []}
    classify._triage_unclassified(
        eng, mB, "help — I'm blocked on a missing local fixture dep",
        {"kind": "worker", "id": "engineer-01-04"}, ["unclassified"])
    ok("SG2 (SAFETY-NET PARITY — must be GREEN): a real worker's unclassified "
       "message STILL enqueues an architect triage (GAP-E net intact)",
       len(mB.get("architect_queue") or []) == 1,
       f"queue={mB.get('architect_queue')}")


def main():
    run_scenario_1()
    run_scenario_2()
    run_grep_proof()
    run_prior_rigs()
    run_scenario_self_triage_guard()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.classify_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
