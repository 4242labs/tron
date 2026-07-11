"""core.tick_rig — real-git, no-LLM rig proving `core.tick`'s bounded tick
host drives ONE already-in-flight block gate to a genuine clean close ACROSS
REAL TICKS — driven entirely by repeated `core.tick.tick(eng)` calls (the
WAKE daemon), never by calling `core.gate.advance` directly — plus the
CRASH-REPLAY idempotency proof this brick exists to make: reload the
manifest fresh from disk mid-run (simulating a crashed tick that ran its
pass for real but never got to persist) and re-run the tick; it must
converge with NO double-land, proven with real shas.

REAL surface only: a real `git init` repo copied from the same scaffold
`core/gate_rig.py` / `core/gate_full_rig.py` / `core/landing_rig.py` use,
`meta/scripts/land.sh` run for real via `subprocess`, a REAL
`engine.ctx.Ctx` pointing at a real `manifest.yaml` (under
`<root>/meta/agents/tron/`, the same instance-dir convention
`engine/land_paperwork_rig.py::build_inst` uses), a REAL declared test
command (`true`) re-run in a REAL clean detached worktree
(`core.gitobs.validate_trunk` -> `engine/trunk.py`), and a minimal
duck-typed `eng` — never a faked/monkeypatched trunk, never a faked test
result, never a faked manifest reload.

The rig plays TWO roles a real deployment splits across two processes: the
WAKE daemon (calls `core.tick.tick(eng)` on a loop) and the worker (writes a
structured local-pass report to `ctx.worker_inbox`, runs the REAL `land.sh`
when a gate mints a grant, tears down its branch when ordered to close) —
exactly the same "rig stands in for the real OS process" convention
`core/gate_full_rig.py` / `core/gate_rig.py` / `core/landing_rig.py` already
use for the landing primitive underneath.

Sequence (block `01-02`, branch `feat/01-02`):
  seed    a real code commit on the branch (never touching the block doc); a
          `gate_state` built via `core.gate.new_state_full` (the ONE direct
          `core.gate` call this rig makes — constructing the ALREADY
          in-flight state the brick is scoped to drive, per the wave-4 spec;
          every ADVANCE from here on goes through `core.tick.tick` only) is
          written straight into a manifest and persisted via `core.state`.
  T1-T2   gate.local: a bare tick holds (no report drained yet, proves the
          ordering side effect fires exactly once); the rig writes a
          structured `{"tag": "worker.done", ...}` report to the inbox and
          the NEXT tick drains it and advances to gate.merge.
  T3      gate.merge mints a content-bound grant + orders the worker
          (`merge_pending`) — the manifest is SNAPSHOT here (raw bytes) as
          the crash-replay's "before" state.
  (real)  the rig-as-worker runs the REAL `land.sh` for that grant — main
          genuinely advances to the code commit's own real sha.
  T5      the NEXT tick observes the real land (real ancestry) and advances
          gate.merge -> gate.trunk.
  CRASH-REPLAY the manifest on disk is rolled back to the T3 snapshot bytes
          (stage still `gate.merge`, same case-id) — AS IF the T5 pass ran
          for real but crashed before its own `core.state.save` ever landed
          on disk (the exact "crash before persist" window
          contracts/blueprint-contracts.md §5 describes; the real git repo
          and real grants dir are UNTOUCHED by this — only the manifest
          reverts). Re-running `core.tick.tick(eng)` against this stale
          manifest must re-derive "already landed" from real git/grants
          state and advance to gate.trunk WITHOUT ever calling `land.sh`
          again — asserted by an explicit land.sh-call counter (this rig's
          own instrumentation) AND by `git rev-parse main` staying
          byte-for-byte unchanged across the whole replay.
  T7-T13  driven the SAME way (tick.tick only): gate.trunk's real declared-
          test re-run -> gate.record's content-checked ✅ commit, landed via
          a SECOND, independently content-bound grant -> close (real branch
          teardown, replica verified clean on real git, worker slot
          released).

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.
"""
import json
import os
import sys
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # grants.py / trunk.py / ctx.py live here
sys.path.insert(0, HERE)                                 # core/{gate,state,snapshot,tick}.py

import grants               # noqa: E402 — respected contract, real, unmodified
import trunk                 # noqa: E402 — respected contract, real, unmodified
from ctx import Ctx          # noqa: E402 — engine/ctx.py, the real runtime-context resolver
import gate                  # noqa: E402 — core/gate.py, the DONE ladder core.tick drives
import state                 # noqa: E402 — core/state.py, the module under test (with core.tick)
import tick                  # noqa: E402 — core/tick.py, the module under test

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
MAIN = "main"
CODE_FILE_REL = "src/lib/tip.ts"          # a real, non-meta/ source file — the "real code change"

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers (same convention as core/gate_full_rig.py) ──
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
    history on `main`, then detach (local no-remote mode keeps the root
    checkout DETACHED, ADR-0002 D1). Same shape as `core/gate_full_rig.py`."""
    d = tempfile.mkdtemp(prefix="tron-core-tickrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-tick-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


BLOCK_DOC_TEMPLATE = """# Block {block}: tick_rig fixture

**Phase:** 1 — Tick host rig
**Status:** {status}
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.tick_rig` — proves the bounded TICK HOST
(`core.tick.tick`) drives a block already in-flight at `gate.local` all the
way to a genuine clean close, across real ticks, with a real crash-replay
idempotency proof along the way.
"""


def seed_block_doc(root, block, block_file_rel):
    _git(["checkout", "-B", MAIN, MAIN], root)
    path = os.path.join(root, block_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(BLOCK_DOC_TEMPLATE.format(block=block, status="🔄 In progress"))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: block {block} (in progress)"], root)
    _git(["checkout", "--detach", MAIN], root)
    return block_file_rel


def seed_empty_pipeline(root, pipeline_rel, blocks_rel):
    """Wave-5 non-interference fixture: a REAL, git-tracked pipeline + blocks
    dir with ZERO dispatchable rows, so `core.gitobs.read_pipeline_view`'s
    `git archive` has real paths to snapshot (never a missing-pathspec
    failure) and `core.switchboard`'s SPAWN arm (added to `core.tick.tick`
    since this rig was written) always reads "nothing to dispatch" here —
    this rig stays scoped to driving an ALREADY in-flight, directly-seeded
    gate only, exactly as before."""
    _git(["checkout", "-B", MAIN, MAIN], root)
    ppath = os.path.join(root, pipeline_rel)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write("# Pipeline\n\n## Roadmap\n\nNo rows — core.tick_rig's own "
                "wave-5 non-interference fixture (this rig drives an "
                "already in-flight gate only, never a fresh dispatch).\n")
    bdir = os.path.join(root, blocks_rel)
    os.makedirs(bdir, exist_ok=True)
    with open(os.path.join(bdir, "block-template.md"), "w") as f:
        f.write("# unused placeholder — engine/reader.py::load_blocks skips this filename\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: empty wave-5 dispatch fixture (no rows)"], root)
    _git(["checkout", "--detach", MAIN], root)


def make_code_commit(root, branch, code_file_rel, marker):
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    with open(path, "a") as f:
        f.write(f"\n// {marker} — core.tick_rig real code change\n")
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
    `core/gate.py` need, PLUS `.ctx` is a REAL `engine.ctx.Ctx` (not a rig
    stub) pointing at a real instance dir, so `core.tick`/`core.state`/
    `core.snapshot` exercise the REAL path-resolver contract end to end
    (`.state`, `.worker_inbox`, `.grants_dir`, `.scratch_dir`).

    Wave 5 (`core/switchboard.py`) added a SPAWN arm to `core.tick.tick`
    itself: it fires whenever a worker slot is free, reading
    `core/pipeline.py::dispatchable`'s trunk-pinned pipeline read. THIS rig
    is scoped to driving an ALREADY in-flight gate only (the wave-4 spec's
    own seeding requirement, `gate.new_state_full` called directly, never a
    fresh dispatch) — `pipeline_rel`/`blocks_rel` are pointed at paths this
    rig never seeds, so `dispatchable` always reads an absent pipeline (a
    valid "nothing to dispatch" state, `engine/reader.py::parse_pipeline`'s
    own contract for a missing file) and the SPAWN arm never fires here,
    proven by `spawn_calls` staying empty for the whole drive (see FINAL's
    own assertion below)."""
    def __init__(self, root, tron_ctx, test_command):
        self.paths = {
            "root": root,
            "main_branch": MAIN,
            "test_command": test_command,     # the project's DECLARED trunk-validation command
            "test_env": None,
            "ci_check_name": None,            # None -> command mode, never CI mode, in this rig
            "worker_count": 1,
            "pipeline_rel": "meta/pipeline-not-seeded-by-tick-rig.md",
            "blocks_rel": "meta/blocks-not-seeded-by-tick-rig/",
        }
        self.dry = False                 # HARD RULE: real trunk observation throughout
        self.ctx = tron_ctx              # REAL engine.ctx.Ctx
        self.events = _Events()
        self.log_lines = []
        self.orders = []
        self.workers = {}                # wid -> {"block":..., "status": "assigned"|"released"}
        self.spawn_calls = []            # wave-5 non-interference proof — must stay empty

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
        """Wave 5's SPAWN stub — must NEVER fire in this rig (see class
        docstring): `pipeline_rel`/`blocks_rel` point at paths this rig never
        seeds, so `core/pipeline.py::dispatchable` always reads empty."""
        self.spawn_calls.append((agent_id, block))


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green "
                                 "(rig-supplied local report, delivered via a structured "
                                 "worker.done inbox line — not a direct advance() call)"}


def main():
    root = build_root()
    seed_empty_pipeline(root, "meta/pipeline-not-seeded-by-tick-rig.md",
                        "meta/blocks-not-seeded-by-tick-rig")
    inst = os.path.join(root, "meta", "agents", "tron")   # engine/land_paperwork_rig.py's own
    os.makedirs(inst, exist_ok=True)                       # instance-dir convention
    tron_ctx = Ctx(inst)
    grants_dir = tron_ctx.grants_dir

    BLOCK, BRANCH, WID = "01-02", "feat/01-02", "engineer-01-02"
    eng = MiniEng(root, tron_ctx, test_command="true")   # trivial, exits 0, ~0 tokens
    eng.workers[WID] = {"block": BLOCK, "status": "assigned"}

    block_file = seed_block_doc(root, BLOCK, "meta/blocks/01-02.md")
    code_tip = make_code_commit(root, BRANCH, CODE_FILE_REL, "01-02-tick-driven-change")
    ok("seed0: rig-as-worker made a real CODE commit on the branch, off trunk, "
       "never touching the block doc",
       bool(code_tip) and not is_ancestor(root, code_tip, MAIN), f"code_tip={code_tip}")

    # The ONE direct core.gate call this rig makes: construct the ALREADY
    # in-flight gate_state (the wave-4 spec's own seeding requirement) and
    # write it straight into a manifest via core.state — every ADVANCE from
    # here on is driven exclusively by core.tick.tick.
    gate_state = gate.new_state_full(eng, BLOCK, block_file, BRANCH, WID)
    manifest = {"gates": {BLOCK: gate_state}}
    state.save(tron_ctx, manifest)
    on_disk_seed = state.load(tron_ctx)
    ok("seed1: manifest persisted for real (core.state.save) with block 01-02 "
       "in-flight at gate.local — never written by any other module",
       on_disk_seed.get("gates", {}).get(BLOCK, {}).get("stage") == gate.STAGE_LOCAL,
       f"on-disk stage={on_disk_seed.get('gates', {}).get(BLOCK, {}).get('stage')}")

    real_land_calls = {}   # case_id -> count — this rig's own exactly-once instrumentation

    def wake(label):
        """One WAKE-daemon firing: `core.tick.tick(eng)` — the ONLY way this
        rig ever drives the gate forward (never a direct `gate.advance`)."""
        res = tick.tick(eng)
        outcome, detail = res["outcomes"].get(BLOCK, (None, None))
        return res, outcome, detail

    def land_now(case_id, label):
        rc, out, err = run_land(root, grants_dir, case_id)
        real_land_calls[case_id] = real_land_calls.get(case_id, 0) + 1
        return rc, out, err

    # ══ T1-T2: gate.local, tick-driven ══
    res1, o1, d1 = wake("t1")
    on_disk1 = state.load(tron_ctx)
    ok("T1: tick-driven gate.local — a bare tick (no report drained yet) holds "
       "at local, never advances (mirrors gate_full_rig's own bare-call proof, "
       "now through core.tick.tick instead of gate.advance directly)",
       o1 == "local_waiting" and on_disk1["gates"][BLOCK]["stage"] == gate.STAGE_LOCAL,
       f"outcome={o1} stage={on_disk1['gates'][BLOCK]['stage']}")
    ok("T1b: gate.local ordered the worker exactly once (idempotent side effect, "
       "persisted through the tick host)",
       len([o for o in eng.orders if o[2] == "gate.local"]) == 1, f"orders={eng.orders}")

    append_jsonl(tron_ctx.worker_inbox,
                {"tag": "worker.done", "block": BLOCK, "slots": LOCAL_PASS_REPORT})
    res2, o2, d2 = wake("t2")
    manifest2 = state.load(tron_ctx)
    ok("T2 (structured drain — no LLM/classify): the tick drained the "
       "worker.done/tag+slots inbox line and fed it as gate.local's "
       "local-pass report, advancing gate.local -> gate.merge",
       o2 == "local_passed" and manifest2["gates"][BLOCK]["stage"] == gate.STAGE_MERGE,
       f"outcome={o2} detail={d2}")
    ok("T2b: the drained inbox sidecar was released after a clean persist "
       "(no leftover .proc — the persist-gated at-least-once discipline)",
       not os.path.exists(tron_ctx.worker_inbox + ".proc")
       and not os.path.exists(tron_ctx.worker_inbox),
       f"inbox={tron_ctx.worker_inbox} proc-exists={os.path.exists(tron_ctx.worker_inbox + '.proc')}")

    # ══ T3: gate.merge mints + orders (real land not yet run) ══
    res3, o3, d3 = wake("t3")
    manifest3 = state.load(tron_ctx)
    merge_case_id = manifest3["gates"][BLOCK].get("merge_case_id")
    ok("T3: tick-driven gate.merge minted a content-bound grant + ordered the "
       "worker (merge_pending) — no land.sh run yet",
       o3 == "merge_pending" and bool(merge_case_id), f"outcome={o3} merge_case_id={merge_case_id}")

    # The crash-replay's "before" snapshot: raw manifest bytes RIGHT AFTER T3's
    # own persist — stage still gate.merge, merge_case_id already fixed.
    with open(tron_ctx.state, "rb") as f:
        pre_land_bytes = f.read()

    main_before_merge_land = _git_out(["rev-parse", MAIN], root)
    rc4, out4, err4 = land_now(merge_case_id, "worker-lands-merge")
    main_after_merge_land = _git_out(["rev-parse", MAIN], root)
    ok("T4 (real land): the rig-as-worker's REAL land.sh genuinely advanced "
       "main to the code commit's own real sha",
       rc4 == 0 and main_after_merge_land == code_tip and main_after_merge_land != main_before_merge_land,
       f"rc={rc4} out={out4!r} err={err4!r} main_before={main_before_merge_land} "
       f"main_after={main_after_merge_land} code_tip={code_tip}")

    res5, o5, d5 = wake("t5-observes-real-land")
    manifest5 = state.load(tron_ctx)
    ok("T5: the NEXT tick observed the real land (real ancestry) and advanced "
       "gate.merge -> gate.trunk, capturing the merged sha",
       o5 == "merge_landed" and manifest5["gates"][BLOCK]["stage"] == gate.STAGE_TRUNK
       and manifest5["gates"][BLOCK].get("merged_sha") == code_tip,
       f"outcome={o5} stage={manifest5['gates'][BLOCK]['stage']} "
       f"merged_sha={manifest5['gates'][BLOCK].get('merged_sha')}")

    # ══ CRASH-REPLAY ASSERTION — the idempotency proof (the whole point) ══
    # Roll the ON-DISK manifest back to the T3 snapshot: stage=gate.merge,
    # the SAME merge_case_id, as if T5's pass ran for real (it did — this is
    # not faked) but crashed before core.state.save ever landed on disk. The
    # real git repo and real grants dir are UNCHANGED by this — only the
    # manifest reverts, exactly the "crash before persist" window
    # contracts/blueprint-contracts.md §5 describes.
    with open(tron_ctx.state, "wb") as f:
        f.write(pre_land_bytes)
    reloaded = state.load(tron_ctx)
    ok("CR0: manifest RELOADED FRESH FROM DISK shows the stale pre-land state "
       "(gate.merge, not yet observed) — the simulated crash, injected for real "
       "on the actual manifest.yaml file, not mocked",
       reloaded["gates"][BLOCK]["stage"] == gate.STAGE_MERGE
       and reloaded["gates"][BLOCK].get("merge_case_id") == merge_case_id,
       f"reloaded_stage={reloaded['gates'][BLOCK]['stage']} "
       f"reloaded_case_id={reloaded['gates'][BLOCK].get('merge_case_id')}")

    land_calls_before_replay = real_land_calls.get(merge_case_id, 0)
    res_replay, o_replay, d_replay = wake("t6-crash-replay")
    manifest_replay = state.load(tron_ctx)
    main_after_replay = _git_out(["rev-parse", MAIN], root)

    ok("CR1 (THE KILLER — must be GREEN): the REPLAYED tick, working from the "
       "STALE reloaded manifest, re-derives 'already landed' from REAL git + "
       "REAL grants state and advances gate.merge -> gate.trunk WITHOUT ever "
       "calling land.sh again",
       o_replay == "merge_landed" and manifest_replay["gates"][BLOCK]["stage"] == gate.STAGE_TRUNK
       and land_calls_before_replay == 1
       and real_land_calls.get(merge_case_id, 0) == 1,
       f"outcome={o_replay} stage={manifest_replay['gates'][BLOCK]['stage']} "
       f"land_calls_for_case_id={real_land_calls.get(merge_case_id)} "
       f"(must stay 1 — no double-land)")

    ok("CR2 (real shas — exactly-once): main's tip is byte-for-byte UNCHANGED "
       "across the whole replay — still == the code commit's own real sha from "
       "the ONE real land.sh run, never a second/different advance",
       main_after_replay == main_after_merge_land == code_tip,
       f"main_before_replay={main_after_merge_land} main_after_replay={main_after_replay} "
       f"code_tip={code_tip}")

    ok("CR3: the replayed gate_state re-derived merged_sha identically "
       "post-replay (no corruption, no drift from the pre-crash value)",
       manifest_replay["gates"][BLOCK].get("merged_sha") == code_tip,
       f"merged_sha={manifest_replay['gates'][BLOCK].get('merged_sha')}")

    # ══ T7-T13: continue driving forward, tick.tick only — trunk -> record -> close ══
    res7, o7, d7 = wake("t7-trunk-validate")
    manifest7 = state.load(tron_ctx)
    ok("T7: tick-driven gate.trunk re-ran the REAL declared test command in a "
       "REAL clean detached worktree at the merged sha and observed PASS -> "
       "gate.record",
       o7 == "trunk_passed" and manifest7["gates"][BLOCK]["stage"] == gate.STAGE_RECORD,
       f"outcome={o7} detail={d7}")

    res8, o8, d8 = wake("t8-record-ordered")
    ok("T8: tick ordered the ✅ record commit; no commit yet -> record_waiting",
       o8 == "record_waiting", f"outcome={o8}")

    record_tip = make_record_commit(root, BRANCH, block_file)
    ok("seed2: rig-as-worker made the record commit (Status flip) on the "
       "already-merged branch, off the current trunk",
       bool(record_tip) and not is_ancestor(root, record_tip, MAIN), f"record_tip={record_tip}")

    res9, o9, d9 = wake("t9-record-mint")
    manifest9 = state.load(tron_ctx)
    record_case_id = manifest9["gates"][BLOCK].get("record_case_id")
    ok("T9: tick content-checked the record commit for real and minted a "
       "SECOND, independently content-bound grant (role=record, distinct "
       "from gate.merge's role=merge case-id)",
       o9 == "record_pending" and bool(record_case_id) and record_case_id != merge_case_id,
       f"outcome={o9} record_case_id={record_case_id} merge_case_id={merge_case_id}")

    rc10, out10, err10 = land_now(record_case_id, "worker-lands-record")
    ok("T10 (real land): the rig-as-worker's REAL land.sh landed the ✅ record "
       "commit for real", rc10 == 0, f"rc={rc10} out={out10!r} err={err10!r}")

    res11, o11, d11 = wake("t11-record-observed")
    manifest11 = state.load(tron_ctx)
    ok("T11: the NEXT tick observed the real ✅ land and advanced "
       "gate.record -> close",
       o11 == "record_landed" and manifest11["gates"][BLOCK]["stage"] == gate.STAGE_CLOSE,
       f"outcome={o11} detail={d11}")

    doc_on_main = _git_out(["show", f"{MAIN}:{block_file}"], root)
    ok("T12: the block doc AS READ FROM main shows ✅ (real git show on trunk)",
       "**Status:** ✅ Done" in doc_on_main, f"doc head={doc_on_main.splitlines()[:4]}")

    res13, o13, d13 = wake("t13-close-ordered")
    ok("T13: tick ordered close (slot still held, never force-released)",
       o13 == "close_ordered", f"outcome={o13}")

    _git(["branch", "-D", BRANCH], root)   # rig-as-worker tears down for real

    res14, o14, d14 = wake("t14-close-confirmed")
    manifest14 = state.load(tron_ctx)
    ok("T14 (TERMINAL — must be GREEN): tick observed the clean replica on "
       "REAL git and released the worker slot -> gate CLOSED, driven "
       "entirely by core.tick.tick across real ticks, never a direct "
       "gate.advance call",
       o14 == "closed" and manifest14["gates"][BLOCK]["stage"] == gate.STAGE_CLOSED
       and eng.workers.get(WID, {}).get("status") == "released",
       f"outcome={o14} stage={manifest14['gates'][BLOCK]['stage']} worker={eng.workers.get(WID)}")

    branch_gone = not trunk.branch_exists(root, BRANCH, False)
    clean_now, clean_detail = trunk.replica_clean(root, BRANCH, MAIN, False)
    ok("T15: the replica is genuinely clean on real git (branch gone, no "
       "worktree on it) before the release the tick already made",
       branch_gone and clean_now, f"branch_gone={branch_gone} clean={clean_now} detail={clean_detail}")

    final_main = _git_out(["rev-parse", MAIN], root)
    total_real_lands = sum(real_land_calls.values())
    ok("FINAL (TERMINAL — must be GREEN): block 01-02 shows ✅ ON TRUNK (real "
       "sha == the record commit's own tip), gate closed, worker slot freed — "
       "a genuine tick-driven clean close; exactly 2 REAL land.sh runs total "
       "(merge + record — the crash-replay's extra tick never produced a "
       "3rd/duplicate land)",
       final_main == record_tip and total_real_lands == 2,
       f"final_main={final_main} record_tip={record_tip} real_land_calls={real_land_calls} "
       f"total={total_real_lands}")

    ok("WAVE5: `core.switchboard`'s SPAWN arm (added to `core.tick.tick` "
       "since this rig was written) never fired across the whole drive — "
       "this rig seeds no pipeline, so it stays scoped to driving an "
       "ALREADY in-flight gate only, exactly as before",
       eng.spawn_calls == [], f"spawn_calls={eng.spawn_calls}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.tick_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"tron instance dir (real engine.ctx.Ctx)={inst}")
    print(f"manifest={tron_ctx.state}")
    print(f"BLOCK={BLOCK} BRANCH={BRANCH}")
    print(f"code_tip (gate.merge content)={code_tip}")
    print(f"merge_case_id={merge_case_id}")
    print(f"main after real land.sh (merge)={main_after_merge_land}")
    print(f"main after crash-replay tick (must be identical)={main_after_replay}")
    print(f"record_tip (gate.record content)={record_tip}")
    print(f"record_case_id={record_case_id}")
    print(f"final main tip (== record_tip)={final_main}")
    print(f"real land.sh invocations per case_id={real_land_calls} (must be 1 each, "
          f"2 total — exactly-once per content version, crash-replay included)")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
