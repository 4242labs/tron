"""core.verdict_wire_rig — block 01-37 T9: the ADR-0011 salvage's "the rig
that never existed", PORTED onto current main and adapted to `core/vocab.py`
(never merged from the frozen `fix/adr-0011-closed-vocabulary` branch — that
lineage is read-only salvage). Drives a triage END-TO-END through the REAL
canon (`prompts/PMT-TRIAGE.md`, rendered by the REAL `engine/render.py::
Renderer`, never a hand-authored fallback string) and the REAL `scripts/
report.sh` (a genuine `bash`+`jq` subprocess, never a hand-written JSONL
line), and asserts the architect's verdict lands in `manifest[
"triage_verdicts"]` and the case resolves WITHOUT paging the operator.

Why this rig has to exist: every OTHER rig in this repo (`core/
architect_rig.py`'s own phantom-triage-grace scenarios included) hand-injects
the verdict dict straight into the manifest or calls `architect.
_advance_triage` directly — bypassing every lock the ADR names (the closed
vocabulary's own minters/slots, `report.sh`'s own flag set + door, `core/
router.py`'s top-level field read, `core/snapshot.py`'s slot promotion,
`core/vocab.py::PROMOTED_SLOT_KEYS`) and the door (`core/classify.py`/`core/
door.py`) that stands between a raw report and the flow. A rig that cannot
fail the way production fails is not a rig — this one drives the SAME
channel a real architect LLM would: read the REAL rendered order text,
extract the `triage_id` the way an LLM has to (regex over the rendered
prompt, never a value read back out of the manifest), and reply via a REAL
`bash scripts/report.sh ...` subprocess.

Adapted from the salvage (never byte-for-byte — the target moved):
  - `SCAFFOLD_SRC`/canon copy: the salvage hardcoded an absolute dev-machine
    path and hand-rolled its own canon copy; block 01-40 T1 already fixed
    the CI-breaking version of both repo-wide — this rig reuses `core.
    scaffold_src.resolve()` and `core.sim.seed_canon.install_canon` instead
    of re-forking either.
  - The salvage's R1b "idle-GUESS" backstop (fabricate a verdict from
    silence) is GONE from current `core/architect.py` (block 01-37 T10,
    ADR-0012 §6(b) — deleted, not ported: "the guess is dead code"). What
    replaces it — a bounded RE-ORDER (`RESPAWN_CAP`) then a genuine, LOUD
    operator page, never a content guess — is what SCENARIO A-MUTATE and
    SCENARIO C now assert instead of the salvage's `manifest["backstops"]`
    counter (which never existed in this stack's own `core/architect.py`).
  - `--kind` is gone (T3/T10: dead, no live consumer) — dropped from every
    call site.
  - SCENARIO D (`architect.escalate`) is NOT ported: that tag/handler does
    not exist in this stack's `core/vocab.py`/`core/router.py` and is out
    of this block's scope (T1-T11 never name it).

Four scenarios (A/A-MUTATE/B/C — the verdict wire itself; D dropped, see
above):
  A — the verdict wire, happy path (`--verdict answer`): the architect's
      real report.sh reply lands in `manifest["triage_verdicts"]`, the case
      resolves, ZERO operator pages.
  A-MUTATE — FALSE-PAGE mutation proof: `core/vocab.py::PROMOTED_SLOT_KEYS`
      monkeypatched back to its PRE-verdict-wire value (`("block",
      "agent_id")`) with the IDENTICAL real report.sh reply sent. Must go
      RED the way production went red: the verdict is dropped as malformed
      (`core/router.py`'s own top-level read finds nothing), the triage
      never resolves via the verdict wire — instead the NEW bounded
      re-order ladder exhausts and the operator IS paged (T10's own honest
      replacement for R1b's old content-guess).
  B — a genuine `--verdict operator` reply pages EXACTLY once, and the case
      stays open, genuinely operator-owned.
  C — FALSE-GREEN mutation proof (a malformed `--verdict notreal` reply):
      the malformed verdict is REJECTED at `core/router.py`, never
      recorded, and the job proceeds to the SAME bounded re-order -> page
      ladder as A-MUTATE — proving scenario A's green is genuinely
      discriminating, not a rig that reports success regardless of input.

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
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # ctx.py / trunk.py / render.py / prompts.py
sys.path.insert(0, HERE)                                 # core/{gate,state,snapshot,tick,...}.py

from ctx import Ctx            # noqa: E402 — engine/ctx.py, the real runtime-context resolver
from render import Renderer     # noqa: E402 — engine/render.py, the REAL canon renderer
import gate                      # noqa: E402 — core/gate.py
import state                      # noqa: E402 — core/state.py
import tick                        # noqa: E402 — core/tick.py
import snapshot                     # noqa: E402 — core/snapshot.py
import architect                     # noqa: E402 — core/architect.py
import vocab                          # noqa: E402 — core/vocab.py, PROMOTED_SLOT_KEYS (the mutated lock)
import scaffold_src                    # noqa: E402 — core/scaffold_src.py, the ONE scaffold resolver
sys.path.insert(0, os.path.join(HERE, "sim"))
import seed_canon                        # noqa: E402 — core/sim/seed_canon.py, the real canon installer

SCAFFOLD_SRC = scaffold_src.resolve()
MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"
BLOCK = "01-01"
BRANCH = f"feat/{BLOCK}"
AGENT_ID = f"engineer-{BLOCK}"
ARCH_ID = architect.ARCHITECT_WID

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git + canon helpers ─────────────────────────────────────────────
def _git(args, cwd, check=True):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}) rc={r.returncode}\n"
                           f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return r


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: verdict_wire_rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {block} | verdict_wire_rig fixture block | 📋 To do | Block `blocks/{block}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: verdict_wire_rig fixture

**Phase:** 1 — verdict_wire_rig
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-14

---

## Context

Synthetic block doc for `core.verdict_wire_rig` (block 01-37 T9, ADR-0012's
"the rig that never existed") — never landed in this rig; the wall/triage/
verdict wire is the whole point, not the block's own build.
"""


def build_root():
    d = tempfile.mkdtemp(prefix="tron-core-verdictwirerig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-verdictwire-rig"], root)

    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(block=BLOCK))
    bpath = os.path.join(root, BLOCKS_REL, f"{BLOCK}.md")
    os.makedirs(os.path.dirname(bpath), exist_ok=True)
    with open(bpath, "w") as f:
        f.write(BLOCK_DOC_TEMPLATE.format(block=BLOCK))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: pipeline + block {BLOCK} (to-do, no gate)"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


def _tron_ctx(root):
    """A real `engine.ctx.Ctx` under `root`, with the FULL REAL canon
    installed verbatim (`core.sim.seed_canon.install_canon` — the SAME
    seeder every other real-canon rig now uses, never a hand-rolled second
    copy) — `messages.yaml`, `routing.yaml`, `prompts/` (registry + every
    PMT-*.md, `PMT-TRIAGE.md` included), `worker-contract.md`, `tron.md`,
    `scripts/report.sh`, AND (block 01-37 T2) the generated `vocab.schema.
    json` a real `report.sh` door reads. THIS is what makes `eng.emit()`
    render the REAL `prompts/PMT-TRIAGE.md` instead of the canon-less
    fallback text every OTHER rig in this repo deliberately exercises."""
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    seed_canon.install_canon(inst, app_root=APP_ROOT)
    return Ctx(inst)


class _Events:
    def __init__(self):
        self.log = []

    def event(self, type_, **payload):
        self.log.append({"type": type_, "payload": payload})


class MiniEng:
    """The minimal duck-typed `eng` — REAL canon rendering (`emit`, below,
    mirrors `core.engine.Engine.emit`: try the real `Renderer` first, fall
    back to `fallback_text` ONLY on a construction exception — never fires
    here, since `_tron_ctx` ships the full real canon)."""

    def __init__(self, root, tron_ctx, worker_count=1):
        self.paths = {
            "root": root, "main_branch": MAIN, "test_command": "true",
            "test_env": None, "ci_check_name": None, "worker_count": worker_count,
            "pipeline_rel": PIPELINE_REL, "blocks_rel": BLOCKS_REL + "/",
        }
        self.dry = False
        self.ctx = tron_ctx
        self.events = _Events()
        self.log_lines = []
        self.orders = []            # (worker_id, REAL rendered text, kind)
        self.workers = {}
        self.spawn_calls = []
        self.operator_pages = []
        self._renderer = Renderer(tron_ctx)

    def log(self, channel, msg):
        self.log_lines.append((channel, msg))

    def _truth_ref(self):
        return MAIN

    def _to_worker(self, wid, msg, kind):
        self.orders.append((wid, msg, kind))

    def emit(self, template_id, fallback_text, slots=None, worker_id=None, kind=None):
        slots = dict(slots or {})
        if worker_id:
            slots.setdefault("worker_id", worker_id)
        slots.setdefault("report", self.ctx.p("scripts", "report.sh"))
        slots.setdefault("contract", self.ctx.worker_contract)
        try:
            line = self._renderer.render(template_id, slots)
        except Exception as e:   # noqa: BLE001 — captured, never hidden
            self.log_lines.append(("render_error", f"{template_id}: {e!r}"))
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

    def _page_operator(self, case_id, block, detail, worker_id=None, manifest=None, page_kind="operator_page"):
        self.operator_pages.append({"case_id": case_id, "block": block, "detail": detail,
                                    "worker_id": worker_id, "page_kind": page_kind})
        return "delivered"


def report_sh(ctx, worker_id, *flag_pairs_and_msg):
    """Invoke the REAL `report.sh` installed at `ctx.p('scripts',
    'report.sh')` as a genuine `bash` subprocess — the exact channel a real
    architect/worker uses, never a hand-written JSONL append."""
    script = ctx.p("scripts", "report.sh")
    r = subprocess.run(["bash", script, worker_id, *flag_pairs_and_msg],
                       capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def _extract_triage_id(order_text):
    """The way a REAL architect LLM has to: parse the triage_id out of the
    RENDERED order text (never read back out of the manifest — that would
    make this rig no better than the ones that hand-inject the verdict).
    `prompts/PMT-TRIAGE.md` (block 01-37 T11) names the exact reply command
    verbatim — `--triage-id <id>` — the same flag `scripts/report.sh`
    accepts; a legacy `triage_id='<id>'` (an older PMT-TRIAGE.md wording)
    is matched too, so a stale-canon rig fixture degrades gracefully rather
    than silently extracting nothing."""
    m = re.search(r"--triage-id\s+(\S+)", order_text)
    if m:
        return m.group(1)
    m = re.search(r"triage_id=(['\"])?([A-Za-z0-9_-]+)\1?", order_text)
    return m.group(2) if m else None


def _run_to_ordered_triage(eng, tron_ctx, root):
    """Drive: SPAWN -> ASSIGN(online+branch) -> a REAL `report.sh --tag
    wall` -> the architect pops + orders the triage job via the REAL
    PMT-TRIAGE.md. Returns (triage_id, order_text, case_id)."""
    res1 = tick.tick(eng)
    ok("A0: SWITCHBOARD spawned the fixture block off the real pipeline row",
       res1["spawned"] == [AGENT_ID], f"spawned={res1['spawned']}")

    _git(["checkout", "-B", BRANCH, MAIN], root)
    src = os.path.join(root, "src", "lib", "tip.ts")
    with open(src, "a") as f:
        f.write("\n// verdict_wire_rig marker\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"feat({BRANCH}): verdict_wire_rig marker"], root)
    _git(["checkout", "--detach", MAIN], root)
    rc, out, err = report_sh(tron_ctx, AGENT_ID, "--tag", "online", "--branch", BRANCH,
                             "checking in, branch declared")
    ok("A0b: the REAL report.sh accepted the worker's online+branch report",
       rc == 0, f"rc={rc} out={out!r} err={err!r}")

    res2 = tick.tick(eng)
    manifest = state.load(tron_ctx)
    gstate = (manifest.get("gates") or {}).get(BLOCK, {})
    ok("A0c: gate.local opened on the worker's declared branch (real ASSIGN)",
       gstate.get("stage") == gate.STAGE_LOCAL and gstate.get("branch") == BRANCH,
       f"gate={gstate}")

    rc, out, err = report_sh(tron_ctx, AGENT_ID, "--tag", "wall",
                             "blocked: the acceptance criteria for this fixture "
                             "block contradict the pipeline row — need a call")
    ok("A1: the REAL report.sh accepted the worker's wall report",
       rc == 0, f"rc={rc} out={out!r} err={err!r}")

    orders_before = len(eng.orders)
    tick.tick(eng)
    manifest = state.load(tron_ctx)
    cases = manifest.get("cases") or {}
    case_id = next((cid for cid, c in cases.items() if c.get("block") == BLOCK), None)
    ok("A2: the real worker.wall opened a parked, architect-owned case",
       case_id is not None and cases[case_id].get("owner") == "architect",
       f"cases={cases}")

    new_orders = eng.orders[orders_before:]
    triage_orders = [o for o in new_orders if o[2] == vocab.TPL_ARCH_TRIAGE]
    if not triage_orders:
        tick.tick(eng)
        new_orders = eng.orders[orders_before:]
        triage_orders = [o for o in new_orders if o[2] == vocab.TPL_ARCH_TRIAGE]
    ok("A3: the architect ordered the triage via a REAL canon-rendered "
       "arch.triage message (never the canon-less fallback text)",
       len(triage_orders) == 1 and triage_orders[0][1] != "",
       f"triage_orders={triage_orders}")
    order_text = triage_orders[0][1] if triage_orders else ""
    ok("A3b: the rendered order is the REAL prompts/PMT-TRIAGE.md body "
       "(its own distinctive text is present) — proves canon, not fallback",
       "I can't place this. Sort it." in order_text,
       f"order_text={order_text!r}")

    triage_id = _extract_triage_id(order_text)
    ok("A4: a triage_id was extracted from the REAL rendered order text "
       "(the way an architect LLM has to — never read off the manifest)",
       bool(triage_id), f"triage_id={triage_id!r} order_text={order_text!r}")
    return triage_id, order_text, case_id


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO A — the verdict wire, happy path
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_a():
    root = build_root()
    tron_ctx = _tron_ctx(root)
    eng = MiniEng(root, tron_ctx, worker_count=1)

    triage_id, _order_text, case_id = _run_to_ordered_triage(eng, tron_ctx, root)
    if not triage_id:
        print("== SCENARIO A aborted (no triage_id extracted) ==")
        return

    rc, out, err = report_sh(
        tron_ctx, ARCH_ID, "--tag", "verdict", "--triage-id", triage_id,
        "--verdict", "answer",
        "resolved: the acceptance criteria are correct as written; proceed.")
    ok("A5: the REAL report.sh accepted the architect's verdict reply",
       rc == 0, f"rc={rc} out={out!r} err={err!r}")

    for _ in range(5):
        tick.tick(eng)

    manifest = state.load(tron_ctx)
    verdicts = manifest.get("triage_verdicts") or {}
    v = verdicts.get(triage_id)
    ok("A6 (THE KILLER ASSERTION — must be GREEN): the architect's REAL "
       "report.sh verdict landed in manifest['triage_verdicts'] via the "
       "REAL wire (vocab.py minters/slots + report.sh's door + core/"
       "router.py top-level read + core/vocab.py::PROMOTED_SLOT_KEYS — "
       "all four locks)",
       v is not None and v.get("verdict") == "answer",
       f"triage_verdicts={verdicts}")

    ok("A7: the case resolved (no longer open) — architect_resolve's "
       "'answer' arm cleared it, the operator NEVER touched",
       case_id not in (manifest.get("cases") or {}),
       f"cases={manifest.get('cases')}")

    ok("A8 (ZERO PAGES — must be GREEN): the operator was NEVER paged for "
       "this triage — the whole point of architect-first routing actually "
       "working",
       len(eng.operator_pages) == 0, f"operator_pages={eng.operator_pages}")

    print("\n== SCENARIO A (verdict wire, happy path) ==")
    print(f"root={root}\ntriage_id={triage_id}\nverdicts={verdicts}")
    print(f"operator_pages={eng.operator_pages}")


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO A-MUTATE — FALSE-PAGE mutation proof (lock 4 reverted)
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_a_mutate():
    root = build_root()
    tron_ctx = _tron_ctx(root)
    eng = MiniEng(root, tron_ctx, worker_count=1)

    orig_keys = vocab.PROMOTED_SLOT_KEYS
    vocab.PROMOTED_SLOT_KEYS = ("block", "agent_id")
    try:
        triage_id, _order_text, case_id = _run_to_ordered_triage(eng, tron_ctx, root)
        if not triage_id:
            print("== SCENARIO A-MUTATE aborted (no triage_id extracted) ==")
            return

        rc, out, err = report_sh(
            tron_ctx, ARCH_ID, "--tag", "verdict", "--triage-id", triage_id,
            "--verdict", "answer",
            "resolved: the acceptance criteria are correct as written; proceed.")
        ok("MUT-A5: the REAL report.sh STILL accepted the identical "
           "architect verdict reply (report.sh's own door is fine — locks "
           "2/3 untouched by this mutation)",
           rc == 0, f"rc={rc} out={out!r} err={err!r}")

        # Drive well past RESPAWN_CAP re-orders so the bounded ladder (T10's
        # honest replacement for the deleted R1b content-guess) exhausts and
        # pages — `eng` has no `_read_hwm`/`_worker_working` hooks, so
        # `_turn_settled` degrades to "delivered the instant ordered=True"
        # (its own documented hookless fallback), arming a fresh re-order
        # decision on every `_advance_triage` call.
        for _ in range(architect.RESPAWN_CAP + 4):
            tick.tick(eng)

        manifest = state.load(tron_ctx)
        verdicts = manifest.get("triage_verdicts") or {}
        ok("MUT-A6 (FALSE-PAGE MUTATION — must be RED/caught, i.e. this "
           "assertion is TRUE: the verdict is DROPPED): with "
           "PROMOTED_SLOT_KEYS reverted, the SAME well-formed report.sh "
           "verdict reply is malformed at the top-level read and never "
           "lands via the wire",
           triage_id not in verdicts, f"verdicts={verdicts}")

        ok("MUT-A7 (FALSE-PAGE MUTATION — must be RED/caught): the case "
           "is STILL open — architect_resolve never ran off the (dropped) "
           "verdict",
           case_id in (manifest.get("cases") or {}), f"cases={manifest.get('cases')}")

        ok("MUT-A8 (FALSE-PAGE MUTATION — THE PROOF — must be RED/caught, "
           "i.e. this assertion is TRUE: the operator WAS paged): this is "
           "the EXACT defect class the verdict wire closes — a perfectly "
           "well-formed verdict, sent for real, still results in an "
           "operator page because the promotion lock alone is broken; "
           "T10's bounded re-order ladder is what surfaces it (never a "
           "content guess)",
           len(eng.operator_pages) >= 1, f"operator_pages={eng.operator_pages}")

        triage_orders = [o for o in eng.orders if o[2] == vocab.TPL_ARCH_TRIAGE]
        ok("MUT-A9 (the re-order ladder genuinely re-fired, never a single "
           "silent guess): more than one arch.triage order was sent for "
           "the SAME triage_id before the page — T10's bounded RETRY, not "
           "R1b's old one-shot fabricated verdict",
           len(triage_orders) > 1, f"triage_orders={len(triage_orders)}")

        print("\n== SCENARIO A-MUTATE (PROMOTED_SLOT_KEYS reverted — FALSE-PAGE proof) ==")
        print(f"root={root}\ntriage_id={triage_id}\nverdicts={verdicts}")
        print(f"operator_pages={eng.operator_pages}")
    finally:
        vocab.PROMOTED_SLOT_KEYS = orig_keys


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO B — a genuine `operator` verdict pages exactly once
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_b():
    root = build_root()
    tron_ctx = _tron_ctx(root)
    eng = MiniEng(root, tron_ctx, worker_count=1)

    triage_id, _order_text, case_id = _run_to_ordered_triage(eng, tron_ctx, root)
    if not triage_id:
        print("== SCENARIO B aborted (no triage_id extracted) ==")
        return

    rc, out, err = report_sh(
        tron_ctx, ARCH_ID, "--tag", "verdict", "--triage-id", triage_id,
        "--verdict", "operator",
        "genuinely the operator's call: policy conflict outside my remit.")
    ok("B1: the REAL report.sh accepted the architect's operator verdict",
       rc == 0, f"rc={rc} out={out!r} err={err!r}")

    for _ in range(5):
        tick.tick(eng)

    manifest = state.load(tron_ctx)
    verdicts = manifest.get("triage_verdicts") or {}
    v = verdicts.get(triage_id)
    ok("B2: the operator verdict landed via the real wire",
       v is not None and v.get("verdict") == "operator", f"verdicts={verdicts}")

    ok("B3 (EXACTLY ONE PAGE — must be GREEN): a genuine operator verdict "
       "pages EXACTLY once — never zero (swallowed), never a storm",
       len(eng.operator_pages) == 1, f"operator_pages={eng.operator_pages}")

    cases = manifest.get("cases") or {}
    ok("B4: the case stays OPEN, now genuinely operator-owned (THE FLOOR's "
       "own re-ping ladder owns it from here, unchanged by this block)",
       case_id in cases and cases[case_id].get("owner") == "operator",
       f"cases={cases}")

    print("\n== SCENARIO B (genuine operator verdict, real page) ==")
    print(f"root={root}\ntriage_id={triage_id}\nverdicts={verdicts}")
    print(f"operator_pages={eng.operator_pages}")


# ═══════════════════════════════════════════════════════════════════════
# SCENARIO C — FALSE-GREEN mutation proof: a MALFORMED verdict reply
# ═══════════════════════════════════════════════════════════════════════
def run_scenario_c():
    root = build_root()
    tron_ctx = _tron_ctx(root)
    eng = MiniEng(root, tron_ctx, worker_count=1)

    triage_id, _order_text, case_id = _run_to_ordered_triage(eng, tron_ctx, root)
    if not triage_id:
        print("== SCENARIO C aborted (no triage_id extracted) ==")
        return

    # A MALFORMED verdict — not one of scope_forward|answer|operator. The
    # wire is otherwise perfectly intact; this proves scenario A's green is
    # genuinely discriminating (this rig does not just report success no
    # matter what report.sh is handed).
    rc, out, err = report_sh(
        tron_ctx, ARCH_ID, "--tag", "verdict", "--triage-id", triage_id,
        "--verdict", "notreal", "this is not a legal verdict")
    ok("C1: the REAL report.sh itself accepts ANY --verdict string (it is "
       "not report.sh's job to validate the closed verdict enum — that is "
       "core/router.py's)",
       rc == 0, f"rc={rc} out={out!r} err={err!r}")

    for _ in range(architect.RESPAWN_CAP + 4):
        tick.tick(eng)

    manifest = state.load(tron_ctx)
    verdicts = manifest.get("triage_verdicts") or {}
    ok("C2 (FALSE-GREEN MUTATION PROOF — must be GREEN, i.e. this "
       "assertion is TRUE: the malformed verdict is REJECTED): core/"
       "router.py::_route_architect_triage_verdict drops an unrecognized "
       "verdict as malformed — never recorded",
       triage_id not in verdicts, f"verdicts={verdicts}")

    ok("C3 (FALSE-GREEN MUTATION PROOF — must be GREEN): with NO legal "
       "verdict ever recorded, the job proceeds exactly as if the "
       "architect had said nothing at all — the bounded re-order ladder "
       "exhausts and the operator IS paged LOUD (never fabricated content)",
       len(eng.operator_pages) >= 1, f"operator_pages={eng.operator_pages}")

    print("\n== SCENARIO C (malformed verdict — FALSE-GREEN mutation proof) ==")
    print(f"root={root}\ntriage_id={triage_id}\nverdicts={verdicts}")
    print(f"operator_pages={eng.operator_pages}")


def main():
    run_scenario_a()
    run_scenario_a_mutate()
    run_scenario_b()
    run_scenario_c()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.verdict_wire_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
