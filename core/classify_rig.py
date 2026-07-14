"""core.classify_rig — real-git rig proving `core.classify` under
STRUCTURED-ONLY reporting (block 01-37 T3/T6/T8, ADR-0012 §6(b)). Replaces
the pre-01-37 free-text/`TRON_JUDGE_STUB` version wholesale: the free-text
GRADER this rig used to drive (`judge.call("classify_message", ...)`) is
RETIRED — there is no model in this module's call graph at all any more.
The word on a report IS the classification; every resolution here is
either structural (a real `core/vocab.py` tag/verb) or a DOOR REFUSAL
(`core.door`), never a judgment call.

Historical-incident coverage (T10: "each removed path's incident test
subsumed or ported") is PRESERVED, re-expressed for the new invariant:
T2-16 (the "placeholder" branch-declaration mis-grade) and ADR-0009 §4/
ADR-0010 §3's land-grant-FYI phantom-walls are exactly the free-text
narrations that USED to reach a judge that could mis-grade them — under
structured-only reporting there is no judge to mis-grade ANYTHING, so
every one of those exact historical trigger texts is proven to be
REFUSED at the door instead (S2-K10/K11 below) — a STRICTLY STRONGER
guarantee (never reaches judgment at all, rather than reaching one that
happens not to misfire).

Two scenarios:

  SCENARIO 1 (real-tick integration) — ONE block from a real 📋 pipeline
  row, driven via `core.tick.tick`: a STRUCTURED `worker.online` report
  ASSIGNs the gate (AC-1); a STRUCTURED `worker.done` report (never
  free-text any more) drives the SAME gate from `gate.local` to `gate.
  merge`; a `worker.flag` report (T7) ledgers + batches to the architect
  and advances NOTHING, opens NO case, pages no one.

  SCENARIO 2 (direct unit calls) — `core.classify.classify` exercised
  directly against a plain manifest dict: an unrecognized `--tag` verb is
  REFUSED at the door (T3/AC-4, full text + sender recorded, an
  architect-first case opened — never a crash, never a guessed flow
  decision); genuine free prose (no tag, no branch) is refused identically
  (T8); a progress+blocking combination (`--tag wall` + `--branch`) is
  refused by the R5/T6 partition (AC-7) — note this FLIPS the pre-01-37
  behavior, which let an explicit wall win over a branch modifier; the
  ADR now makes that exact combination illegal by class, on purpose (see
  S2-K9's own docstring below); a worker-shaped sender cannot mint
  `architect.reconciled` (ADR-0011 S-1 minters, T9); the deterministic
  operator CASE-<n> settle regex still works, zero judgment calls (now
  trivially true — there is no judgment tool left to call).

Plus a structural/grep proof: `judge` is imported by NO `core/*.py` module
at all (the free-text grader's sole call site, `core/classify.py`, no
longer imports `engine/judge.py` — a strictly stronger claim than the
pre-01-37 "exactly one module" proof) and, at the end, a live re-run of
every prior `core/*_rig.py` fixture as subprocesses — block 01-37's
structured-only door is purely additive to every one of them: every prior
rig already sent only structured lines, so `classify()` remains a same-tag
echo for all of them.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # ctx.py / grants.py / trunk.py
sys.path.insert(0, HERE)                                 # core/{classify,gate,state,snapshot,tick,...}.py

import util                  # noqa: E402 — engine/util.py, atomic_write/append_jsonl (respected)
import trunk                   # noqa: E402 — respected contract, real, unmodified
from ctx import Ctx             # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import gate                      # noqa: E402 — core/gate.py, the DONE ladder core.tick drives
import state                      # noqa: E402 — core/state.py
import snapshot                    # noqa: E402 — core/snapshot.py, block 01-37's structured-door wiring
import router                       # noqa: E402 — core/router.py, structured ASSIGN + T4/T7 arms
import tick                          # noqa: E402 — core/tick.py, the whole per-tick pass
import classify                       # noqa: E402 — core/classify.py, the module under test
import door                            # noqa: E402 — core/door.py, the T3/T6 admission door
import vocab                            # noqa: E402 — core/vocab.py, the closed vocabulary
import architect                         # noqa: E402 — core/architect.py, ARCHITECT_WID + triage reuse
import casestate                          # noqa: E402 — core/casestate.py, VERBS + case-id shape

import scaffold_src               # noqa: E402 — core/scaffold_src.py, the ONE resolver

SCAFFOLD_SRC = scaffold_src.resolve()
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

Synthetic block doc for `core.classify_rig` — proves block 01-37's
structured-only door (`core/classify.py` + `core/door.py`): a structured
report resolves off `core/vocab.py`'s closed vocabulary, deterministically;
anything else is refused at the door, never guessed at by a model.
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
    classify.py`/`core/door.py` need. `.ctx` is a REAL `engine.ctx.Ctx`."""

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
        # unconditionally — fallback_text verbatim.
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
        self.log_lines.append(("operator_page", f"{case_id} {block} {detail}"))


def _tron_ctx(root):
    """A real `engine.ctx.Ctx` under `root`."""
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    return Ctx(inst)


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 1 — real-tick integration (structured door only, no judgment)
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_1():
    root = build_root()
    seed_pipeline(root)
    tron_ctx = _tron_ctx(root)
    eng = MiniEng(root, tron_ctx, worker_count=1)

    # ── tick 1: SWITCHBOARD spawns the block off the real pipeline ──
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

    # ── tick 2: ASSIGN — the structured report resolves via classify.py's
    #     own vocab-backed door (AC-1) — no model exists anywhere in this
    #     call graph to consult ──
    res2 = tick.tick(eng)
    manifest2 = state.load(tron_ctx)
    gate2 = (manifest2.get("gates") or {}).get(BLOCK, {})

    ok("S1-K1 (STRUCTURED-DOOR KILLER — must be GREEN): the structured "
       "worker.online report ASSIGNed the gate (gate.local opened, bound to "
       "the worker's OWN reported branch)",
       gate2.get("stage") == gate.STAGE_LOCAL and gate2.get("branch") == BRANCH,
       f"stage={gate2.get('stage')} branch={gate2.get('branch')}")

    # ── the rig-as-worker's local pass, delivered STRUCTURED (T8: there is
    #     no free-text arm any more — a real worker's local-pass report is
    #     `report.sh --tag done --block <id> "<evidence>"`, ported here as
    #     the equivalent structured JSONL line) ──
    evidence = ("npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
               "(rig-supplied local pass, delivered STRUCTURED — --tag done)")
    util.append_jsonl(
        tron_ctx.worker_inbox,
        {"tag": "done", "agent_id": AGENT_ID, "text": evidence,
         "slots": {"block": BLOCK, "verdict": "pass", "evidence": evidence},
         "sender": {"kind": "worker", "id": AGENT_ID}})

    # ── tick 3: the structured done report feeds the gate's local_report ->
    #     advances past gate.local (AC-2's structured-only equivalent) ──
    res3 = tick.tick(eng)
    manifest3 = state.load(tron_ctx)
    gate3 = (manifest3.get("gates") or {}).get(BLOCK, {})

    ok("S1-K2 (STRUCTURED-DONE-ADVANCES — must be GREEN): the structured "
       "`--tag done` report fed the gate's local_report — the SAME block's "
       "gate advanced from gate.local to gate.merge this tick",
       gate3.get("stage") == gate.STAGE_MERGE,
       f"stage_after={gate3.get('stage')} outcomes={res3.get('outcomes')}")

    # ── T7 — a worker.flag report: ledgered + batched to the architect,
    #     never opens a case, never pages, never advances/blocks anything ──
    cases_before = len((manifest3.get("cases") or {}))
    util.append_jsonl(
        tron_ctx.worker_inbox,
        {"tag": "flag", "agent_id": AGENT_ID, "text": "fyi: noisy test output, ignorable",
         "slots": {"block": BLOCK}, "sender": {"kind": "worker", "id": AGENT_ID}})
    res4 = tick.tick(eng)
    manifest4 = state.load(tron_ctx)
    ledger = manifest4.get("flag_ledger") or []
    ok("S1-K3 (T7 VISIBILITY-FLAG KILLER — must be GREEN): a worker.flag "
       "report is ledgered (operator-readable) and pages NO ONE — no new "
       "case, no operator_page log line, and the gate is UNCHANGED",
       len(ledger) == 1 and ledger[0]["worker_id"] == AGENT_ID
       and len((manifest4.get("cases") or {})) == cases_before
       and not any(ch == "operator_page" for ch, _m in eng.log_lines)
       and (manifest4.get("gates") or {}).get(BLOCK, {}).get("stage") == gate.STAGE_MERGE,
       f"ledger={ledger} cases={manifest4.get('cases')} "
       f"gate={(manifest4.get('gates') or {}).get(BLOCK)}")

    print("\n== SCENARIO 1 (real-tick integration, structured-only) ==")
    print(f"root={root}")
    print(f"tron instance dir={tron_ctx.dir}")
    print(f"gate after ASSIGN={gate2}")
    print(f"gate after structured done={gate3}")
    print(f"flag_ledger={ledger}")


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 2 — direct unit calls: door refusals, minters, R5/T6 partition,
# CASE-<n> settle regex, historical phantom-wall incidents (now REFUSED,
# never reaching any judgment — there is none)
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_2():
    root = build_root()   # only needed for a real Ctx; no pipeline/tick here
    tron_ctx = _tron_ctx(root)
    eng = MiniEng(root, tron_ctx, worker_count=1)
    manifest = {}

    # ── structured bypass: a real vocab tag resolves deterministically ──
    tag, slots = classify.classify(
        eng, {"tag": "worker.done", "agent_id": AGENT_ID, "block": BLOCK,
              "slots": {"verdict": "pass", "evidence": "x"}}, manifest)
    ok("S2-K1: a structured report resolves via classify.classify() "
       "deterministically off core/vocab.py",
       tag == "worker.done" and slots == {"verdict": "pass", "evidence": "x"},
       f"tag={tag} slots={slots}")

    # ── unrecognized --tag verb -> REFUSED at the door (T3/AC-4): recorded
    #     with full text + sender, an architect-first case opened, never a
    #     crash, never a guessed flow decision ──
    raw_text_invalid = "the deploy pipeline is on fire, someone please look"
    queue_len_before = len(manifest.get("architect_queue") or [])
    events_before = len(eng.events.log)
    tag2, slots2 = classify.classify(
        eng, {"tag": "totally-not-a-real-verb", "text": raw_text_invalid,
              "sender": {"kind": "worker", "id": "engineer-99"}},
        manifest)
    queue_after = manifest.get("architect_queue") or []
    triage_job = next((j for j in queue_after if j.get("kind") == "triage"
                       and j.get("source") == "worker.report_refused"), None)
    ok("S2-K2 (DOOR-REFUSAL KILLER — must be GREEN): an unrecognized --tag "
       "verb is REFUSED (tag=None, never routed) — never a crash, never a "
       "guessed flow decision",
       tag2 is None and slots2 is None, f"tag2={tag2} slots2={slots2}")
    ok("S2-K3 (ARCHITECT-FIRST REFUSAL KILLER — must be GREEN): the "
       "refusal was handed to the architect FIRST as a real case "
       "(source=worker.report_refused) — never a direct operator page",
       len(queue_after) == queue_len_before + 1 and triage_job is not None,
       f"queue_before={queue_len_before} queue_after={queue_after}")
    ok("S2-K4 (FORENSIC-RECORD KILLER — must be GREEN): the refusal was "
       "recorded durably — the home-log line AND a durable events.event "
       "record — full attempted text preserved, never reduced to a count",
       len(eng.events.log) == events_before + 1
       and eng.events.log[-1]["type"] == "door_refusal"
       and raw_text_invalid in eng.events.log[-1]["payload"]["raw"]
       and any(raw_text_invalid in msg for _ch, msg in eng.log_lines),
       f"events_tail={eng.events.log[-1:]}")

    # ── genuine free prose (no tag, no branch) -> refused identically
    #     (T8: structured-only, no free-text judgment behind it at all) ──
    raw_prose = "hey, quick heads up, this one's tricky"
    tag_prose, slots_prose = classify.classify(
        eng, {"text": raw_prose, "sender": {"kind": "worker", "id": "engineer-01"}}, manifest)
    ok("S2-K5 (PROSE-ONLY REFUSED — must be GREEN, T8): a message with "
       "NEITHER --tag NOR --branch is refused at the door — structured-only "
       "reporting, no free-text judgment behind it",
       tag_prose is None and slots_prose is None,
       f"tag={tag_prose} slots={slots_prose}")

    # ── R5/T6 partition: a progress+blocking combination is illegal (AC-7).
    #     This is a DELIBERATE behavior FLIP from pre-01-37 (where an
    #     explicit --tag wall carrying a --branch modifier "won" over the
    #     branch): ADR-0012 R5 makes exactly this combination illegal BY
    #     CLASS — a worker cannot assert "I'm blocked" and "here is my new
    #     branch" in the SAME report any more; send them separately. ──
    tag_conflict, slots_conflict = classify.classify(
        eng, {"tag": "wall", "agent_id": "engineer-01-03",
              "slots": {"branch": "feat/01-03-ui"},
              "text": "genuinely blocked",
              "sender": {"kind": "worker", "id": "engineer-01-03"}},
        manifest)
    ok("S2-K6 (R5/T6 PARTITION KILLER — must be GREEN, AC-7): --tag wall "
       "combined with a --branch modifier (progress-advancing + blocking in "
       "ONE report) is REFUSED — the enumerated partition, not the one pair "
       "seen live",
       tag_conflict is None and slots_conflict is None,
       f"tag={tag_conflict} slots={slots_conflict}")
    # ...but a wall with NO branch modifier still resolves normally —
    # the partition never blocks a genuine, uncombined wall.
    tag_wall_ok, slots_wall_ok = classify.classify(
        eng, {"tag": "wall", "agent_id": "engineer-01-03", "text": "genuinely blocked",
              "sender": {"kind": "worker", "id": "engineer-01-03"}},
        manifest)
    ok("S2-K6b: an UN-combined wall (no branch modifier) still resolves to "
       "worker.wall normally — the partition never blocks a genuine wall",
       tag_wall_ok == "worker.wall", f"tag={tag_wall_ok} slots={slots_wall_ok}")

    # ── ADR-0011 S-1 minters (T9): a worker-shaped sender cannot mint
    #     architect.reconciled just by knowing the shape ──
    tag_forge, slots_forge = classify.classify(
        eng, {"tag": "reconciled", "agent_id": "engineer-99", "block": BLOCK,
              "sender": {"kind": "worker", "id": "engineer-99"}},
        manifest)
    ok("S2-K7 (MINTERS-ENFORCED KILLER — must be GREEN, T9): a WORKER "
       "sender cannot mint architect.reconciled — refused, never trusted "
       "just because it named the right shape",
       tag_forge is None and slots_forge is None,
       f"tag={tag_forge} slots={slots_forge}")
    # ...but the architect's OWN identity (agent_id == ARCHITECT_WID) may.
    tag_real, slots_real = classify.classify(
        eng, {"tag": "reconciled", "agent_id": architect.ARCHITECT_WID, "block": BLOCK},
        manifest)
    ok("S2-K7b: the architect's OWN identity mints architect.reconciled fine",
       tag_real == "architect.reconciled", f"tag={tag_real} slots={slots_real}")

    # ── T2-16 / ADR-0009 §4 / ADR-0010 §3 — the historical phantom-wall
    #     incidents, RE-PROVEN under structured-only: every one of these
    #     exact trigger texts is free prose that USED to reach a judge that
    #     could (and once did) mis-grade it worker.wall. There is no judge
    #     left to mis-grade ANYTHING — each is refused at the door instead,
    #     a strictly stronger guarantee (T10: incident subsumed, not lost). ──
    historical_phantom_texts = [
        "placeholder",                                          # T2-16
        "FYI — awaiting the land grant",                        # ADR-0009 §4 / ADR-0010 §3 (T3-01)
        "land.sh fast-forwarded trunk to X; grant consumed",
        "close-out paperwork committed; waiting on the land grant",
    ]
    for i, text in enumerate(historical_phantom_texts):
        t, s = classify.classify(
            eng, {"text": text, "sender": {"kind": "worker", "id": "engineer-t301"}}, manifest)
        ok(f"S2-K8.{i} (PHANTOM-WALL SUBSUMED — must be GREEN): historical "
           f"trigger {text!r} is refused at the door (never worker.wall, "
           f"never reaches any judgment — none exists)",
           t is None and s is None, f"tag={t} slots={s}")

    # ── deterministic operator CASE-<n> settle regex (bonus — "keep it
    #     working") — zero judgment calls, trivially, now ──
    settle_manifest = {"cases": {"case-01-01-1": {
        "case_id": "case-01-01-1", "block": BLOCK, "source": "worker.wall",
        "decision": None, "detail": "walled"}}}
    tag4, slots4 = classify.classify(
        eng, {"text": "please resume case-01-01-1, all clear now",
              "sender": {"kind": "operator", "id": "the-operator"}},
        settle_manifest)
    ok("S2-K9 (BONUS — CASE-SETTLE-REGEX KILLER): an operator's free text "
       "naming a GENUINELY open case id + a settle verb resolves to "
       "operator.decision via a deterministic regex",
       tag4 == "operator.decision" and slots4 == {"case_id": "case-01-01-1", "verb": "resume"},
       f"tag4={tag4} slots4={slots4}")

    # ── the SAME text against a manifest with NO open case at all must NOT
    #     misfire — now REFUSED (T8: no free-text fallback of any kind) ──
    tag5, slots5 = classify.classify(
        eng, {"text": "please resume case-01-01-1, all clear now",
              "sender": {"kind": "operator", "id": "the-operator"}},
        {"cases": {}})
    ok("S2-K10: the same CASE-<n>-shaped text against a manifest with NO "
       "open case is refused (never a false-positive settle; no free-text "
       "fallback left to fall through to)",
       tag5 is None and slots5 is None, f"tag5={tag5}")

    # ── BRANCH-DECLARATION KILLER (T2-16 root-fix, still intact): a
    #     tag-LESS report that declares a branch resolves DETERMINISTICALLY
    #     to worker.branch ──
    tag6, slots6 = classify.classify(
        eng, {"agent_id": "engineer-01-03", "text": "placeholder",
              "slots": {"branch": "feat/01-03-ui"},
              "sender": {"kind": "worker", "id": "engineer-01-03"}},
        manifest)
    ok("S2-K11 (BRANCH-DECLARATION KILLER — must be GREEN): a tag-less "
       "report carrying slots.branch resolves to worker.branch "
       "DETERMINISTICALLY — no judgment involved, so a contentless "
       "declaration ('placeholder') can never be mis-graded worker.wall",
       tag6 == "worker.branch" and slots6.get("branch") == "feat/01-03-ui",
       f"tag6={tag6} slots6={slots6}")

    print("\n== SCENARIO 2 (direct unit calls) ==")
    print(f"tron instance dir={tron_ctx.dir}")
    print(f"final architect_queue={manifest.get('architect_queue')}")
    print(f"events tail={eng.events.log[-6:]}")


# ═══════════════════════════════════════════════════════════════════════
# structural / grep proof — the free-text GRADER is retired: `judge` is
# imported by NO `core/*.py` module at all (strictly stronger than the
# pre-01-37 "exactly one module" claim); no raw git/subprocess crept in.
# ═══════════════════════════════════════════════════════════════════════
def run_grep_proof():
    core_files = sorted(
        f for f in os.listdir(HERE)
        if f.endswith(".py") and not f.endswith("_rig.py") and f != "__init__.py")
    judge_import_files = []
    judge_call_files = []
    for fname in core_files:
        with open(os.path.join(HERE, fname)) as fh:
            text = fh.read()
        if re.search(r"^\s*import\s+judge\b", text, re.MULTILINE):
            judge_import_files.append(fname)
        if re.search(r"\bjudge\.call\s*\(", text):
            judge_call_files.append(fname)
    ok("G1 (GRADER-RETIRED GREP PROOF — must be GREEN, T8): NO core/*.py "
       "module imports engine/judge.py any more — the free-text grader has "
       "no call site left anywhere in this engine",
       judge_import_files == [] and judge_call_files == [],
       f"judge_import_files={judge_import_files} judge_call_files={judge_call_files}")

    for fname in ("classify.py", "door.py", "snapshot.py", "router.py", "tick.py"):
        with open(os.path.join(HERE, fname)) as fh:
            text = fh.read()
        has_subprocess = bool(re.search(
            r"^\s*import subprocess\b|subprocess\.(run|Popen|call|check_output|check_call)\s*\(",
            text, re.MULTILINE))
        has_raw_git = bool(re.search(r"^\s*\[?[\"']git[\"']|\bimport git\b", text, re.MULTILINE))
        ok(f"G2[{fname}]: no raw subprocess/git call introduced (no raw git "
           "outside core.gitobs/core.state IO)",
           not has_subprocess and not has_raw_git,
           f"has_subprocess={has_subprocess} has_raw_git={has_raw_git}")

    # AC-1: no second hand-maintained copy of the tag/verb table remains.
    for fname in ("classify.py",):
        with open(os.path.join(HERE, fname)) as fh:
            text = fh.read()
        ok(f"G3[{fname}] (AC-1): the retired _REPORT_VERB_TAG/_canonical_tag "
           "hand-maintained copy is gone — core/vocab.py::VERB_TO_TAG is the "
           "single source",
           "_REPORT_VERB_TAG" not in text and "_canonical_tag" not in text,
           "grep clean" if ("_REPORT_VERB_TAG" not in text
                            and "_canonical_tag" not in text) else "STILL PRESENT")


# ═══════════════════════════════════════════════════════════════════════
# all prior core/*_rig.py fixtures — block 01-37's structured door is
# purely additive; every prior rig already sends only structured lines
# ═══════════════════════════════════════════════════════════════════════
PRIOR_RIGS = ["landing_rig", "gate_rig", "gate_full_rig", "tick_rig", "dispatch_rig",
              "multiblock_rig", "sentry_rig", "casestate_rig", "architect_rig",
              "reviewers_rig", "liveness_rig", "engine_rig"]


def run_prior_rigs():
    env = dict(os.environ)
    for name in PRIOR_RIGS:
        path = os.path.join(HERE, f"{name}.py")
        r = subprocess.run([sys.executable, path], cwd=HERE, capture_output=True,
                           text=True, env=env, timeout=600)
        last_line = next((ln for ln in reversed(r.stdout.strip().splitlines())
                          if ln.strip().startswith(f"core.{name}:")), "")
        ok(f"P[{name}]: still fully green after block 01-37's structured-door "
           f"edits (subprocess exit={r.returncode})",
           r.returncode == 0, last_line or (r.stdout[-300:] + r.stderr[-300:]))


def run_scenario_self_triage_guard():
    """s3 first-honest-SIM lock: a REFUSED message from the architect ITSELF
    never spawns a new triage — the architect narrating (a malformed/
    prose-only line from its OWN turn) creates nothing, same R1a self-source
    guard as before, re-expressed for the door-refusal path (`core.door.
    refuse` short-circuits on the architect's own identity exactly like
    `casestate.open_case`/`architect.enqueue_triage` already do). A real
    worker's equivalent refusal STILL triages (GAP-E net intact)."""
    root = build_root()
    tron_ctx = _tron_ctx(root)
    eng = MiniEng(root, tron_ctx, worker_count=1)
    arch_id = architect.ARCHITECT_WID
    mA = {"architect_queue": []}
    classify.classify(
        eng, {"text": "Sorted: it's a branch declaration, no architect action.",
              "sender": {"kind": "worker", "id": arch_id}},
        mA)
    ok("SG1 (SELF-SOURCE CREATION GUARD, R1a — must be GREEN): a refused "
       "message FROM the architect's own identity creates NO new triage "
       "case (open_case's own R1a guard fires, source-directional)",
       len(mA.get("architect_queue") or []) == 0,
       f"queue={mA.get('architect_queue')}")
    mB = {"architect_queue": []}
    classify.classify(
        eng, {"text": "help — I'm blocked on a missing local fixture dep",
              "sender": {"kind": "worker", "id": "engineer-01-04"}},
        mB)
    ok("SG2 (SAFETY-NET PARITY — must be GREEN): a real worker's refused "
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
