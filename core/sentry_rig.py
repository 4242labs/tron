"""core.sentry_rig — real-git, no-LLM rig proving `core.sentry`'s pacing
ladder (wave 7: "a gate can never hang silently") does EXACTLY what
`contracts/blueprint-contracts.md` §5 promises, on the REAL surface: a real
`git init` repo copied from the same scaffold every prior `core/*_rig.py`
uses, `meta/scripts/land.sh` run for real via `subprocess` when (and only
when) this rig chooses to run it, a REAL `engine.ctx.Ctx` pointing at a real
`manifest.yaml`, and a minimal duck-typed `eng` — never a faked/
monkeypatched trunk. Driven entirely via repeated `core.tick.tick(eng)`
calls (the WAKE daemon), exactly like `core/tick_rig.py` /
`core/dispatch_rig.py` / `core/multiblock_rig.py` — never a direct
`core.sentry.pace` call of this rig's own, so this is also the wiring proof
(`core/tick.py` really does call `sentry.pace` after driving gates, before
persist).

TWO blocks, seeded together and driven through the SAME interleaved tick
loop (the multi-gate convention `core/multiblock_rig.py` already
establishes — one `react()` per tick, reacting to whatever each block's own
gate needs) — seeded TOGETHER, deliberately, not sequentially: `core/
session.py`'s clean-terminal check (wave 6, wired into `core/tick.py`
unconditionally) reads "nothing in-flight" off the manifest alone, and this
rig's own pipeline fixture is intentionally EMPTY (zero rows — every gate
here is seeded directly, never dispatched, exactly like `core/tick_rig.py`);
with only ONE gate in flight, the tick where it turns terminal (closed OR
escalated) is ALSO the tick "nothing in-flight" first reads true against an
empty view, which would fire a (structurally honest, but for THIS rig
premature) SESSION-END and freeze every later tick into a no-op. Seeding
BOTH gates up front keeps at least one genuinely in-flight until the very
end, so this rig can drive its STUCK gate all the way through nudge ->
escalate -> quiescent AND its HAPPY gate all the way to a clean close, in
the same run, without ever tripping that terminal early:

  stuck-01 (branch `feat/stuck-01`) — the cited example (blueprint-
  contracts.md §5 / this brick's own spec): "a worker that never runs
  land.sh at gate.merge". The rig plays the worker up through a well-formed
  local-pass report (so the gate genuinely reaches gate.merge, a grant
  genuinely gets minted and the worker genuinely gets ordered to land it) —
  then STOPS reacting to this block entirely: `land.sh` is never run for
  its case-id, ever, so the gate holds at gate.merge, tick after tick, with
  nothing to observe but "not yet landed".

  happy-01 (branch `feat/happy-01`) — reacted to FULLY, every tick, exactly
  the way `core/tick_rig.py` plays its own single block: local-pass report,
  a REAL `land.sh` at gate.merge, a REAL declared test command re-run in a
  REAL clean detached worktree at gate.trunk, a real record commit + a
  SECOND real `land.sh` at gate.record, real branch teardown at close —
  genuine, continuous progress, tick after tick.

Walked wake-by-wake against `core.sentry`'s own exported knobs
(`sentry.GATE_NUDGE_AFTER` / `sentry.GATE_IDLE_CAP` — this rig hardcodes
NEITHER number, so a future retune of either knob keeps this proof correct
unmodified), the whole per-tick history is captured and then asserted
post-hoc:

  - stuck-01's ONE re-nudge (a real `eng._to_worker` order, distinct
    `sentry.nudge.merge` kind) lands on the FIRST tick `holding` reads
    `>= GATE_NUDGE_AFTER` — never before, never twice while still holding.
  - stuck-01's escalation (`gate_state["stage"] -> gate.STAGE_ESCALATED`, a
    structured `manifest["escalations"]` entry whose own recorded
    `holding` field reads EXACTLY `GATE_IDLE_CAP`) lands on the FIRST tick
    `holding` reads `>= GATE_IDLE_CAP` — never before, and stays the ONLY
    entry for the rest of the run (the quiescent tail: a terminal gate
    `core.sentry.pace` — like `core/tick.py`'s own `decide` step — skips
    outright).
  - happy-01, despite sharing the EXACT SAME clock the whole time (proving
    `core.sentry`'s per-gate `holding_since` anchoring is genuinely
    per-gate, never a global "time since the run started"), reaches a
    genuine clean close and is NEVER escalated, and — at this brick's
    chosen `GATE_NUDGE_AFTER` margin — never even nudged (the margin
    comfortably clears the ladder's own structural order-then-detect delay
    at gate.record, the ONE stage every prior happy-path rig's own drive
    naturally holds at for more than a single tick).

Phase SOURCE (no git involved) then closes the loop: `CLOSE_ATTEMPT_CAP`
(and any per-stage cap constant) is GONE from `core/gate.py`'s source; the
two pacing knobs live in `core/sentry.py` alone; neither module shells out
to a raw `git`/`subprocess` call outside the documented `gitobs`/`state`
seams this whole `core/` stack already keeps to.

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
sys.path.insert(0, HERE)                                 # core/{gate,sentry,state,snapshot,tick}.py

import grants               # noqa: E402 — respected contract, real, unmodified
import trunk                 # noqa: E402 — respected contract, real, unmodified
from ctx import Ctx          # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import gate                  # noqa: E402 — core/gate.py, the DONE ladder (never self-caps)
import sentry                 # noqa: E402 — core/sentry.py, the module under test
import state                 # noqa: E402 — core/state.py
import tick                  # noqa: E402 — core/tick.py, wired to call sentry.pace

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
MAIN = "main"
CODE_FILE_REL = "src/lib/tip.ts"          # a real, non-meta/ source file — the "real code change"
BLOCK_S, BRANCH_S, WID_S = "stuck-01", "feat/stuck-01", "engineer-stuck-01"
BLOCK_H, BRANCH_H, WID_H = "happy-01", "feat/happy-01", "engineer-happy-01"
MAX_TICKS = 40

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers (same convention as core/tick_rig.py) ──
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
    """Copy the REAL scaffold into a throwaway tempdir with a fresh, real git
    history on `main`, then detach (ADR-0002 D1). Same shape as
    `core/tick_rig.py`."""
    d = tempfile.mkdtemp(prefix="tron-core-sentryrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-sentry-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


def seed_empty_pipeline(root, pipeline_rel, blocks_rel):
    """Wave-5 non-interference fixture (verbatim pattern from
    `core/tick_rig.py`): a REAL, git-tracked, ZERO-row pipeline so
    `core.gitobs.read_pipeline_view` always has real paths to snapshot and
    `core/switchboard.py::fill`'s SPAWN arm always reads "nothing to
    dispatch" — this rig seeds every gate directly (`gate.new_state_full`),
    never through dispatch."""
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, pipeline_rel)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write("# Pipeline\n\n## Roadmap\n\nNo rows — core.sentry_rig's own "
                "non-interference fixture (every gate here is seeded "
                "directly, never dispatched).\n")
    bdir = os.path.join(root, blocks_rel)
    os.makedirs(bdir, exist_ok=True)
    with open(os.path.join(bdir, "block-template.md"), "w") as f:
        f.write("# unused placeholder — engine/reader.py::load_blocks skips this filename\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: empty non-interference dispatch fixture (no rows)"], root)
    _git(["checkout", "--detach", MAIN], root)


BLOCK_DOC_TEMPLATE = """# Block {block}: sentry_rig fixture

**Phase:** 1 — Sentry pacing-ladder rig
**Status:** {status}
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.sentry_rig` — proves the ONE pacing ladder
(`core/sentry.py`) nudges a genuinely stuck gate at `gate_nudge_after`,
escalates it exactly at `gate_idle_cap` (never before, never never), and
never once fires against a gate that keeps making real progress.
"""


def seed_block_doc(root, block, block_file_rel, status="🔄 In progress"):
    _git(["checkout", "-B", MAIN, MAIN], root)
    path = os.path.join(root, block_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(BLOCK_DOC_TEMPLATE.format(block=block, status=status))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: block {block} ({status})"], root)
    _git(["checkout", "--detach", MAIN], root)
    return block_file_rel


def make_code_commit(root, branch, code_file_rel, marker):
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    with open(path, "a") as f:
        f.write(f"\n// {marker} — core.sentry_rig real code change\n")
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
    new_content = content.replace("**Status:** 🔄 In progress", "**Status:** ✅ Done")
    assert new_content != content, "seed status line not found — fixture drift"
    with open(path, "w") as f:
        f.write(new_content)
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"record: {branch} done"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def run_land(root, grants_dir, case_id):
    """Run the REAL `meta/scripts/land.sh` via subprocess — the rig playing
    the worker ordered to land its own grant, per ADR-0002 D2."""
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
    `core/gate.py` + `core/sentry.py` need. Deliberately carries NO
    `_now()` — this rig exercises `core.sentry`'s FALLBACK clock (its own
    manifest-persisted tick counter, incremented once per `pace()` call),
    the same path every other `core/*_rig.py` eng fixture already falls
    through unmodified; the boundary math below reads `holding` straight
    off the real, persisted `gate_state["holding_since"]`/`holding_stage`
    fields each tick, never assumed from a wake count, so it stays correct
    regardless of which clock source is in play."""
    def __init__(self, root, tron_ctx, test_command, worker_count=2):
        self.paths = {
            "root": root,
            "main_branch": MAIN,
            "test_command": test_command,
            "test_env": None,
            "ci_check_name": None,
            "worker_count": worker_count,
            "pipeline_rel": "meta/pipeline-not-dispatched-by-sentry-rig.md",
            "blocks_rel": "meta/blocks-not-dispatched-by-sentry-rig/",
        }
        self.dry = False                 # HARD RULE: real trunk observation throughout
        self.ctx = tron_ctx              # REAL engine.ctx.Ctx
        self.events = _Events()
        self.log_lines = []
        self.orders = []
        self.workers = {}
        self.spawn_calls = []            # non-interference proof — must stay empty
        self.pages = []                  # wave 8 (core/casestate.py): eng._page_operator calls

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

    def _spawn_architect(self):
        # Wave 18 (GAP-E): `core/architect.py::advance` calls this lazily
        # the first tick it ever pops a job — now genuinely exercised,
        # since every `core/casestate.py::open_case` call (a sentry cap
        # escalation included) routes ARCHITECT-FIRST. No real transport,
        # exactly like `_spawn_worker`/`_to_worker` above.
        pass

    def _page_operator(self, case_id, block, detail, worker_id=None, **_kwargs):
        """Wave 8 (core/casestate.py): the STUBBED operator-page hook a cap
        escalation now also fires (`sentry.py::_escalate` -> `casestate.
        open_case`) — no real transport, exactly like `_to_worker` above.
        `**_kwargs`: wave 17 (GAP-A) widened the real `eng._page_operator`
        call surface (`manifest=`/`page_kind=`, `core/casestate.py`'s own
        THE-FLOOR re-ping ladder) — tolerated and ignored here; this rig's
        own S8 (QUIESCENT-AFTER) asserts on `pace()`'s `nudged`/`escalated`
        RETURN value only, which the floor ladder never feeds (see `core/
        sentry.py::pace`'s own docstring), so a re-pinged stuck-01 keeps
        appearing in `eng.pages` after its cap without disturbing S8 at
        all."""
        self.pages.append((case_id, block, detail, worker_id))


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
                                 "(rig-supplied local report, delivered via a structured "
                                 "worker.done inbox line)"}


def nudge_orders(eng, wid):
    return [o for o in eng.orders if o[0] == wid and o[2].startswith("sentry.nudge.")]


def main():
    root = build_root()
    seed_empty_pipeline(root, "meta/pipeline-not-dispatched-by-sentry-rig.md",
                        "meta/blocks-not-dispatched-by-sentry-rig")
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    eng = MiniEng(root, tron_ctx, test_command="true")

    block_file_s = seed_block_doc(root, BLOCK_S, "meta/blocks/stuck-01.md")
    code_tip_s = make_code_commit(root, BRANCH_S, CODE_FILE_REL, "stuck-01-never-landed")
    ok("PRE-S: rig-as-worker made a real CODE commit on the STUCK branch, "
       "off trunk — never touching the block doc, never (ever) landed",
       bool(code_tip_s) and not is_ancestor(root, code_tip_s, MAIN), f"code_tip_s={code_tip_s}")

    block_file_h = seed_block_doc(root, BLOCK_H, "meta/blocks/happy-01.md")
    code_tip_h = make_code_commit(root, BRANCH_H, CODE_FILE_REL, "happy-01-real-progress")
    ok("PRE-H: rig-as-worker made a real CODE commit on the HAPPY branch, "
       "off trunk, never touching the block doc",
       bool(code_tip_h) and not is_ancestor(root, code_tip_h, MAIN), f"code_tip_h={code_tip_h}")

    # ── seed BOTH gates together, BEFORE any tick — see module docstring:
    #     with an intentionally empty pipeline, at least one gate must stay
    #     genuinely in-flight the whole time, or core/session.py's clean-
    #     terminal check fires (vacuously — "nothing in-flight" reads true
    #     against an empty view) the instant the ONLY gate goes terminal,
    #     freezing every later tick into a no-op before happy-01 could ever
    #     be driven ──
    eng.workers[WID_S] = {"block": BLOCK_S, "status": "assigned"}
    eng.workers[WID_H] = {"block": BLOCK_H, "status": "assigned"}
    manifest0 = {"gates": {
        BLOCK_S: gate.new_state_full(eng, BLOCK_S, block_file_s, BRANCH_S, WID_S),
        BLOCK_H: gate.new_state_full(eng, BLOCK_H, block_file_h, BRANCH_H, WID_H),
    }}
    state.save(tron_ctx, manifest0)

    local_reported = {BLOCK_S: False, BLOCK_H: False}
    merge_landed_cases = set()      # HAPPY only, ever — STUCK's own grant is NEVER landed
    record_committed = {BLOCK_H: False}
    record_landed_cases = set()
    torn_down = {BLOCK_H: False}
    real_land_calls = {}            # case_id -> count, across the whole rig

    triage_answered = set()

    def react_architect_triage(manifest):
        """Wave 18 (GAP-E): a sentry cap escalation now opens an
        ARCHITECT-first case (`core/casestate.py::open_case` -> `core/
        architect.py::enqueue_triage`), never an immediate operator page.
        S4 below still proves stuck-01's escalation genuinely reaches the
        operator (paged via `eng._page_operator`, never a bare
        `manifest["escalations"]` record alone) — the SAME "escalate all
        the way through" script every other re-pointed rig in this wave
        uses — while ALSO (S4 itself) proving the page never fires the
        SAME tick the cap trips."""
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if (cur and cur.get("kind") == "triage" and cur.get("ordered")
                and cur.get("triage_id") not in triage_answered):
            append_jsonl(tron_ctx.worker_inbox,
                        {"tag": "architect.triage_verdict",
                         "triage_id": cur["triage_id"], "verdict": "operator"})
            triage_answered.add(cur["triage_id"])

    def react(manifest):
        """One reaction per tick, for EACH block's own gate: STUCK gets its
        local-pass report ONCE (so it genuinely reaches gate.merge — the
        cited example needs a gate stuck AT MERGE, not stuck at LOCAL) and
        is then NEVER reacted to again (its merge grant, once minted, is
        never landed — the whole point). HAPPY gets the full normal
        reaction at every stage, every tick, exactly like every prior
        tick-driven rig's own single-block worker-stand-in."""
        react_architect_triage(manifest)
        gates = manifest.get("gates") or {}

        gs = gates.get(BLOCK_S)
        if gs and gs.get("stage") == gate.STAGE_LOCAL and not local_reported[BLOCK_S]:
            append_jsonl(tron_ctx.worker_inbox,
                        {"tag": "worker.done", "block": BLOCK_S, "slots": LOCAL_PASS_REPORT})
            local_reported[BLOCK_S] = True

        gh = gates.get(BLOCK_H)
        if not gh:
            return
        stage = gh.get("stage")
        if stage == gate.STAGE_LOCAL and not local_reported[BLOCK_H]:
            append_jsonl(tron_ctx.worker_inbox,
                        {"tag": "worker.done", "block": BLOCK_H, "slots": LOCAL_PASS_REPORT})
            local_reported[BLOCK_H] = True
        elif stage == gate.STAGE_MERGE and gh.get("merge_case_id"):
            case_id = gh["merge_case_id"]
            if case_id not in merge_landed_cases:
                run_land(root, grants_dir, case_id)
                real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                merge_landed_cases.add(case_id)
        elif stage == gate.STAGE_RECORD:
            if gh.get("record_ordered") and not record_committed[BLOCK_H] and not gh.get("record_case_id"):
                make_record_commit(root, BRANCH_H, block_file_h)
                record_committed[BLOCK_H] = True
            if gh.get("record_case_id") and gh["record_case_id"] not in record_landed_cases:
                case_id = gh["record_case_id"]
                run_land(root, grants_dir, case_id)
                real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
                record_landed_cases.add(case_id)
        elif stage == gate.STAGE_CLOSE and gh.get("close_ordered") and not torn_down[BLOCK_H]:
            _git(["branch", "-D", BRANCH_H], root)
            torn_down[BLOCK_H] = True

    tick_history = []   # (i, outcomes, nudged, escalated, gates-snapshot)
    for i in range(1, MAX_TICKS + 1):
        res = tick.tick(eng)
        m = state.load(tron_ctx)
        react(m)
        gates_snap = {b: dict(g) for b, g in (m.get("gates") or {}).items()}
        tick_history.append({"i": i, "outcomes": dict(res["outcomes"]),
                             "nudged": list(res["nudged"]), "escalated": list(res["escalated"]),
                             "gates": gates_snap, "session_end": res.get("session_end")})
        gs_now = gates_snap.get(BLOCK_S, {})
        gh_now = gates_snap.get(BLOCK_H, {})
        if gs_now.get("stage") == gate.STAGE_ESCALATED and gh_now.get("stage") == gate.STAGE_CLOSED:
            break

    # ── wave 18 (GAP-E): the break above fires on GATE stage alone (never
    #     touched by this wave) — the instant it trips, stuck-01's cap
    #     escalation has only just opened an ARCHITECT-owned case, not yet
    #     paged. Keep driving (bounded, `react`'s own `react_architect_
    #     triage` answers the triage) until the operator page genuinely
    #     fires, before S4 (below) asserts on it. ──
    for _ in range(15):
        m_check = state.load(tron_ctx)
        stuck_case_check = next((c for c in (m_check.get("cases") or {}).values()
                                 if c.get("block") == BLOCK_S), None)
        if stuck_case_check is not None and any(p[1] == BLOCK_S for p in eng.pages):
            break
        res = tick.tick(eng)
        m = state.load(tron_ctx)
        react(m)
        gates_snap = {b: dict(g) for b, g in (m.get("gates") or {}).items()}
        tick_history.append({"i": tick_history[-1]["i"] + 1, "outcomes": dict(res["outcomes"]),
                             "nudged": list(res["nudged"]), "escalated": list(res["escalated"]),
                             "gates": gates_snap, "session_end": res.get("session_end")})

    ok(f"RUN0: the whole interleaved drive converged (stuck-01 escalated, "
       f"happy-01 closed) inside {MAX_TICKS} ticks (used {tick_history[-1]['i']})",
       tick_history[-1]["gates"].get(BLOCK_S, {}).get("stage") == gate.STAGE_ESCALATED
       and tick_history[-1]["gates"].get(BLOCK_H, {}).get("stage") == gate.STAGE_CLOSED,
       f"ticks_used={tick_history[-1]['i']} "
       f"final_stuck_stage={tick_history[-1]['gates'].get(BLOCK_S, {}).get('stage')} "
       f"final_happy_stage={tick_history[-1]['gates'].get(BLOCK_H, {}).get('stage')}")

    final_manifest = state.load(tron_ctx)

    # ══ STUCK — S1: first-ever sighting, no holding counted on tick 1 ══
    t1 = tick_history[0]
    ok("S1: gate.local bare-holds on the first tick (no report drained "
       "yet) — never advances, sentry sees this as the FIRST sighting of "
       "this gate (a fresh pacing episode, no holding counted, no nudge, "
       "no escalate)",
       t1["outcomes"].get(BLOCK_S) == ("local_waiting",
           "no well-formed local-pass report this call (bare/absent never advances)")
       and t1["gates"][BLOCK_S]["stage"] == gate.STAGE_LOCAL
       and t1["gates"][BLOCK_S].get("holding_stage") == gate.STAGE_LOCAL
       and BLOCK_S not in t1["nudged"] and not t1["escalated"],
       f"outcome={t1['outcomes'].get(BLOCK_S)} "
       f"holding_stage={t1['gates'][BLOCK_S].get('holding_stage')}")

    # ══ STUCK — the merge-mint tick: find it, then walk holding wake-by-wake ══
    merge_mint_tick = next(t for t in tick_history
                           if t["gates"].get(BLOCK_S, {}).get("merge_case_id"))
    merge_case_id_s = merge_mint_tick["gates"][BLOCK_S]["merge_case_id"]
    ok("S2: gate.merge minted a content-bound grant for stuck-01 + ordered "
       "the worker to land it — the ONE real order this gate ever gets "
       "(the rig plays the misbehaving worker from here: it NEVER runs "
       "land.sh for this case-id, ever)",
       bool(merge_case_id_s) and any(o[2] == "gate.merge" for o in eng.orders),
       f"merge_case_id_s={merge_case_id_s}")

    nudge_tick = next((t for t in tick_history if BLOCK_S in t["nudged"]), None)
    escalate_tick = next((t for t in tick_history if BLOCK_S in dict(t["escalated"])), None)

    ok("S3 (NUDGE KILLER — must be GREEN): stuck-01 got exactly ONE "
       "re-nudge (a real `eng._to_worker` order, distinct "
       "`sentry.nudge.merge` kind) across the whole drive — fired the "
       "FIRST tick `pace()` reads `holding >= GATE_NUDGE_AFTER`",
       nudge_tick is not None and len(nudge_orders(eng, WID_S)) == 1,
       f"nudge_tick={nudge_tick['i'] if nudge_tick else None} "
       f"nudge_orders={nudge_orders(eng, WID_S)}")

    tick_before_nudge = tick_history[tick_history.index(nudge_tick) - 1] if nudge_tick else None
    ok("S3b (NOT-BEFORE KILLER — must be GREEN): the tick strictly BEFORE "
       "the nudge fired had NO sentry.nudge order yet for stuck-01 — the "
       "nudge landed on the FIRST qualifying tick, never earlier",
       tick_before_nudge is not None and BLOCK_S not in tick_before_nudge["nudged"],
       f"tick_before_nudge={tick_before_nudge['i'] if tick_before_nudge else None}")

    escalate_record = None
    stuck_case = None
    if escalate_tick is not None:
        escalate_record = dict(escalate_tick["escalated"]).get(BLOCK_S)
        # the STRUCTURED manifest["escalations"] record, not just the
        # (block, detail) tuple `tick.tick`'s own result surfaces
        manifest_records = [r for r in (final_manifest.get("escalations") or [])
                            if r.get("block") == BLOCK_S]
        # wave 8 (core/casestate.py): the SAME escalation ALSO opens a
        # parked operator case — re-pointed here (never weakened: the
        # `manifest["escalations"]` record above is asserted UNCHANGED,
        # this is an ADDITIONAL, stricter requirement) per the brick's own
        # "keep the honest record" + "one path for needs-the-operator" design.
        stuck_case = next((c for c in (final_manifest.get("cases") or {}).values()
                           if c.get("block") == BLOCK_S), None)
    ok("S4 (ESCALATE KILLER — must be GREEN): stuck-01 ESCALATED exactly "
       "once — `gate_state['stage'] == gate.STAGE_ESCALATED`, a structured "
       "record landed in `manifest['escalations']` (durable, re-read fresh "
       "off disk) — after, and only after, the one re-nudge above — AND "
       "(wave 8, core/casestate.py) the SAME cap escalation opened a parked "
       "operator CASE for stuck-01 (source `sentry.cap`, `decision=None`, "
       "never resumed across this whole rig — the operator page fired via "
       "the stubbed `eng._page_operator` hook, never a bare record alone)",
       escalate_tick is not None and nudge_tick is not None
       and escalate_tick["i"] > nudge_tick["i"]
       and escalate_record is not None
       and len(manifest_records) == 1
       and stuck_case is not None
       and stuck_case.get("source") == "sentry.cap"
       and stuck_case.get("decision") is None
       and any(p[1] == BLOCK_S for p in eng.pages),
       f"escalate_tick={escalate_tick['i'] if escalate_tick else None} "
       f"nudge_tick={nudge_tick['i'] if nudge_tick else None} "
       f"manifest_records={manifest_records if escalate_tick else None} "
       f"stuck_case={stuck_case} pages={eng.pages}")

    tick_before_escalate = (tick_history[tick_history.index(escalate_tick) - 1]
                            if escalate_tick else None)
    ok("S5 (NOT-BEFORE KILLER — must be GREEN): the tick strictly BEFORE "
       "escalation still showed stuck-01 holding at gate.merge (not yet "
       "escalated, no escalations recorded yet for it) — the cap tripped "
       "on the FIRST qualifying tick, never earlier",
       tick_before_escalate is not None
       and tick_before_escalate["gates"][BLOCK_S]["stage"] == gate.STAGE_MERGE
       and BLOCK_S not in dict(tick_before_escalate["escalated"]),
       f"tick_before_escalate={tick_before_escalate['i'] if tick_before_escalate else None} "
       f"stage_then={tick_before_escalate['gates'][BLOCK_S]['stage'] if tick_before_escalate else None}")

    ok("S6 (THE EXACT BOUNDARY KILLER — must be GREEN): the escalation "
       "record's own `holding` field reads EXACTLY `sentry.GATE_IDLE_CAP` "
       "— the cap tripped on the tick holding FIRST reached the cap, "
       "never before (a smaller recorded holding = an early/false "
       "escalate) and never later (a bigger one = sentry missed its own "
       "boundary)",
       manifest_records[0].get("holding") == sentry.GATE_IDLE_CAP
       and manifest_records[0].get("gate_idle_cap") == sentry.GATE_IDLE_CAP,
       f"recorded_holding={manifest_records[0].get('holding')} "
       f"GATE_IDLE_CAP={sentry.GATE_IDLE_CAP} GATE_NUDGE_AFTER={sentry.GATE_NUDGE_AFTER}")

    ok("S7: the merge grant was NEVER landed — main was never advanced by "
       "stuck-01's content, no land.sh ever ran for its case-id (a "
       "genuinely stuck gate, proven on real git, not simulated)",
       not is_ancestor(root, code_tip_s, MAIN)
       and not grants.read_consumed(grants_dir, merge_case_id_s)
       and merge_case_id_s not in real_land_calls,
       f"code_tip_s={code_tip_s} is_ancestor={is_ancestor(root, code_tip_s, MAIN)} "
       f"consumed={grants.read_consumed(grants_dir, merge_case_id_s)}")

    ticks_after_escalate = tick_history[tick_history.index(escalate_tick) + 1:] if escalate_tick else []
    ok("S8 (QUIESCENT-AFTER KILLER — must be GREEN): every tick AFTER "
       "escalation is a true no-op for stuck-01 — `core/tick.py`'s own "
       "`decide` step already excludes a terminal gate from `act`, and "
       "`core.sentry.pace` independently skips a terminal gate too "
       "(belt-and-suspenders): stuck-01 never again appears in any later "
       "tick's `outcomes`/`nudged`/`escalated`, and `manifest["
       "'escalations']` never grows a second entry for it",
       all(BLOCK_S not in t["outcomes"] and BLOCK_S not in t["nudged"]
           and BLOCK_S not in dict(t["escalated"]) for t in ticks_after_escalate)
       and len(manifest_records) == 1,
       f"ticks_checked={[t['i'] for t in ticks_after_escalate]}")

    # ══ HAPPY — never escalated, never (at this margin) even nudged ══
    happy_close_tick = next((t for t in tick_history
                             if t["gates"].get(BLOCK_H, {}).get("stage") == gate.STAGE_CLOSED), None)
    happy_escalations = [r for r in (final_manifest.get("escalations") or [])
                         if r.get("block") == BLOCK_H]
    ok("H1 (TERMINAL — must be GREEN): happy-01 reached a genuine clean "
       "close (gate.STAGE_CLOSED, real replica clean, worker slot really "
       "released) — driven entirely by core.tick.tick, sentry wired in "
       "and running every single tick alongside stuck-01",
       happy_close_tick is not None
       and eng.workers.get(WID_H, {}).get("status") == "released",
       f"happy_close_tick={happy_close_tick['i'] if happy_close_tick else None} "
       f"worker={eng.workers.get(WID_H)}")

    ok("H2 (THE PROGRESS KILLER — must be GREEN): across happy-01's ENTIRE "
       "drive (local -> merge -> trunk -> record -> close, real land.sh "
       "twice, a real declared-test re-run) — sharing the EXACT SAME clock "
       "as stuck-01's own run to its cap — `manifest['escalations']` "
       "gained NOT ONE entry for happy-01 (proving `holding_since` "
       "anchoring is genuinely PER-GATE, never a global run-clock), and "
       "sentry never even nudged it (this brick's GATE_NUDGE_AFTER margin "
       "comfortably clears the ladder's own structural order-then-detect "
       "delay at gate.record)",
       happy_escalations == [] and nudge_orders(eng, WID_H) == [],
       f"happy_escalations={happy_escalations} "
       f"happy_nudge_orders={nudge_orders(eng, WID_H)}")

    main_after = _git_out(["rev-parse", MAIN], root)
    ok("H3: the worker's OWN real code commit genuinely landed on trunk "
       "via gate.merge's real land.sh, and the ✅ record commit genuinely "
       "landed via a SECOND, independently content-bound grant",
       is_ancestor(root, code_tip_h, MAIN) and main_after != code_tip_h
       # main_after should be the RECORD commit's sha (landed after code) —
       # confirmed structurally below via the doc-on-trunk check (H4).
       and real_land_calls.get(happy_close_tick and
                               final_manifest["gates"][BLOCK_H].get("merge_case_id"), 0) == 1,
       f"code_tip_h={code_tip_h} main_after={main_after}")

    doc_on_main = _git_out(["show", f"{MAIN}:{block_file_h}"], root)
    ok("H4: the block doc AS READ FROM main shows ✅ (real git show on "
       "trunk) — happy-01 genuinely closed, never escalated",
       "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")

    ok("H5: SWITCHBOARD's SPAWN arm never fired across this whole rig — "
       "both gates were seeded directly (`gate.new_state_full`), never "
       "dispatched (this rig's own scope, mirroring core/tick_rig.py's)",
       eng.spawn_calls == [], f"spawn_calls={eng.spawn_calls}")

    # ══════════════════════════════════════════════════════════════════
    # PHASE SOURCE — the cap moved: gone from gate.py, lives only in
    # sentry.py (a plain-text proof, no git involved).
    # ══════════════════════════════════════════════════════════════════
    gate_src = open(os.path.join(HERE, "gate.py")).read()
    sentry_src = open(os.path.join(HERE, "sentry.py")).read()
    ok("SRC1 (CAP-MOVED KILLER — must be GREEN): `CLOSE_ATTEMPT_CAP` (the "
       "gate's own former per-stage cap) and its `close_attempts` counter "
       "are BOTH gone from core/gate.py's source — the gate is a pure "
       "predicate-driven state machine now, no self-capping anywhere",
       "CLOSE_ATTEMPT_CAP = " not in gate_src and '"close_attempts"' not in gate_src
       and 'gate_state["close_attempts"]' not in gate_src,
       "grep-equivalent source scan of core/gate.py")
    ok("SRC2: `core/sentry.py` is the ONE place either pacing knob lives — "
       "`GATE_NUDGE_AFTER` / `GATE_IDLE_CAP`, both exported, both read by "
       "this rig's own assertions above (S6) rather than hardcoded",
       "GATE_NUDGE_AFTER = " in sentry_src and "GATE_IDLE_CAP = " in sentry_src,
       "grep-equivalent source scan of core/sentry.py")
    ok("SRC3: neither module shells out to a raw git/subprocess call of "
       "its own — all git observation stays inside core/gitobs.py (the ONE "
       "seam), all persistence inside core/state.py, exactly like every "
       "other module in this stack (checked as actual `import subprocess`/"
       "`subprocess.` USAGE, not prose that merely talks about the "
       "discipline — both modules' own docstrings say 'never a raw "
       "subprocess', which would false-positive a bare substring check)",
       "import subprocess" not in gate_src and "subprocess." not in gate_src
       and "import subprocess" not in sentry_src and "subprocess." not in sentry_src
       and "\nimport git\n" not in gate_src and "\nimport git\n" not in sentry_src,
       "grep-equivalent source scan of core/{gate,sentry}.py (import/call sites only)")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.sentry_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"tron instance dir (real engine.ctx.Ctx)={inst}")
    print(f"manifest={tron_ctx.state}")
    print(f"sentry.GATE_NUDGE_AFTER={sentry.GATE_NUDGE_AFTER} "
          f"sentry.GATE_IDLE_CAP={sentry.GATE_IDLE_CAP}")
    print(f"BLOCK_S={BLOCK_S} BRANCH_S={BRANCH_S} code_tip_s(never landed)={code_tip_s} "
          f"merge_case_id_s={merge_case_id_s}")
    print(f"  nudge_tick={nudge_tick['i'] if nudge_tick else None} "
          f"escalate_tick={escalate_tick['i'] if escalate_tick else None}")
    print(f"  escalation record={manifest_records[0] if escalate_tick else None}")
    print(f"BLOCK_H={BLOCK_H} BRANCH_H={BRANCH_H} code_tip_h={code_tip_h} "
          f"happy_close_tick={happy_close_tick['i'] if happy_close_tick else None}")
    print(f"  final escalations (must have exactly 1, stuck-01's)="
          f"{final_manifest.get('escalations')}")
    print(f"  happy-01 nudge orders (must be empty)={nudge_orders(eng, WID_H)}")
    print(f"ticks used={tick_history[-1]['i']} (cap={MAX_TICKS})")
    print("per-tick summary: " + " | ".join(
        f"t{t['i']}:S={t['gates'].get(BLOCK_S, {}).get('stage')}"
        f",H={t['gates'].get(BLOCK_H, {}).get('stage')}"
        f"{'+nudge' + str(t['nudged']) if t['nudged'] else ''}"
        f"{'+ESCALATE' if t['escalated'] else ''}"
        for t in tick_history))
    print(f"real land.sh invocations per case_id={real_land_calls}")
    print(f"final main tip={_git_out(['rev-parse', MAIN], root)}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
