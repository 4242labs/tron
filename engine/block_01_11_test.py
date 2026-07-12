"""block_01_11_test — E2E loop completion acceptance (block 01-11, AC-1…AC-7).

Deterministic, token-free: dry-mode engine fixtures (sentry_test's builders) for the gate
machinery, plus REAL throwaway git repos for the record-commit content check and the
CLOSE-cleanliness scan (those are git reads by design and must be proven against git).

Covers:
  AC-1  lint L19 negative case (a reply-expecting PMT with no channel line FAILS)
  AC-2  idle-at-gate, generic over the stage enum: runner-idle accrues on tick ->
        re-nudge at gate_nudge_after -> _gate_giveup escalation at gate_idle_cap;
        MANIFEST status mirrors the runner state (working <-> idle)
  AC-3  a re-nudge is a deliberate duplicate on a FRESH seq — the runner's seq-keyed
        dedupe delivers it (and still dedupes a same-seq re-append)
  AC-4  record step: trunk-stage evidence report -> gate orders RECORD (gate.record);
        ✅ on trunk at stage record -> content-check -> CLOSE; a record-PR window never
        parks on the operator (no merge case)
  AC-5  content check inspects the record commit's OWN diff (real git): the block-doc
        completion paperwork (Status flip + the skill-prescribed Completed date) passes;
        extra file / a non-metadata (code/prose) line fails; a concurrent unrelated merge
        in between does not false-positive
  AC-6  CLOSE cleanliness (real git): clean replica releases; leftover branch /
        uncommitted state is rejected and escalates at the cap — never trust-released
  AC-7  the `recorded` tag sweep is atomic: routing.yaml + tron.md + lint CANON_TAGS +
        the classify enum all know worker.recorded

Run: python3 engine/block_01_11_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import json
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import util             # noqa: E402
import jobs             # noqa: E402
import trunk            # noqa: E402
import lint             # noqa: E402
from ctx import Ctx     # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _eng(block="A-01", status="🔄"):
    ctx, repo = build(blocks=[(block, status, "none")])
    eng = Engine(ctx)
    started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def _mkrepo():
    d = tempfile.mkdtemp(prefix="tron-0111-")
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    os.makedirs(os.path.join(d, "blocks"))
    with open(os.path.join(d, "blocks", "A-01.md"), "w") as fh:
        fh.write("# Block A-01\n**Status:** 🔄 In progress\n**Merge approval:** auto\n\nbody\n")
    with open(os.path.join(d, "src.txt"), "w") as fh:
        fh.write("code\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


# ── AC-1: lint L19 fails on a reply-expecting PMT with no channel line ──
def t_l19_negative():
    d = tempfile.mkdtemp(prefix="tron-l19-")
    pdir = os.path.join(d, "prompts")
    os.makedirs(pdir)
    util.atomic_write(os.path.join(pdir, "PMT-BAD.md"), "no channel here\n")
    util.atomic_write(os.path.join(pdir, "registry.yaml"),
                      'reply_line: "reply: bash {report} {worker_id}"\n'
                      "prompts:\n  PMT-BAD: { file: PMT-BAD.md, slots: [] }\n")

    class _C:
        prompts_dir = pdir
        prompts_registry = os.path.join(pdir, "registry.yaml")
    res = lint._reply_contract(_C())
    ok("AC-1 L19 fails on an unflagged PMT without {report}",
       len(res) == 1 and not res[0].ok and "PMT-BAD" in res[0].detail)
    util.atomic_write(os.path.join(pdir, "registry.yaml"),
                      'reply_line: "reply: bash {report} {worker_id}"\n'
                      "prompts:\n  PMT-BAD: { file: PMT-BAD.md, slots: [], reply_expected: true }\n")
    res = lint._reply_contract(_C())
    ok("AC-1 L19 passes once flagged (loader appends the line)", res[0].ok)
    util.atomic_write(os.path.join(pdir, "registry.yaml"),
                      'reply_line: "no slots at all"\n'
                      "prompts:\n  PMT-BAD: { file: PMT-BAD.md, slots: [], reply_expected: true }\n")
    res = lint._reply_contract(_C())
    ok("AC-1 L19 fails on a reply_line without {report}/{worker_id}", not res[0].ok)
    shutil.rmtree(d, ignore_errors=True)


# ── AC-2: idle-at-gate accrues on tick -> nudge -> escalate; MANIFEST mirrors runner ──
def t_idle_gate(stage_name, setup):
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
    setup(eng, g)
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda *a, **k: True
    sent = []
    orig_emit = eng.emit
    eng.emit = lambda tid, slots=None, worker_id=None: sent.append(tid) or orig_emit(tid, slots, worker_id)
    clock = {"t": 1000.0}                             # S-1: idle is a WALL-CLOCK span
    eng._now_s = lambda: clock["t"]
    try:
        eng._drive_gate("A-01", g)                    # anchor idle_since
        n1 = g.get("idle_since")
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._drive_gate("A-01", g)                    # past nudge span -> re-nudge
        nudged = list(sent)
        clock["t"] += eng._pace("gate_idle_cap", 3)   # well past the cap
        eng._drive_gate("A-01", g)                    # -> escalate
        escalated = "A-01" not in eng.st.gate and any(t == ("wall:raised:A-01")
                                                      for t, _ in eng._tq)
    finally:
        jobs.runner_idle = orig_idle
    ok(f"AC-2 [{stage_name}] idle accrues on tick", n1 is not None)
    ok(f"AC-2 [{stage_name}] re-nudge fires at gate_nudge_after",
       any(t in ("gate.local", "gate.trunk", "gate.record", "gate.merge") for t in nudged),
       f"sent={nudged}")
    ok(f"AC-2 [{stage_name}] escalates at gate_idle_cap (gate dropped -> wall)", escalated)


def t_idle_stages():
    def at_local(eng, g):
        g["stage"] = "local"
        # local mode, branch not present -> stage recomputes to local each tick
    t_idle_gate("local", at_local)

    def at_record(eng, g):
        g["stage"] = "record"
    t_idle_gate("record", at_record)


def t_busy_never_accrues():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda *a, **k: False          # runner working
    try:
        for _ in range(5):
            eng._drive_gate("A-01", g)
        ok("AC-2 busy worker never accrues idle_ticks",
           g.get("idle_ticks", 0) == 0 and "A-01" in eng.st.gate)
    finally:
        jobs.runner_idle = orig_idle


def t_manifest_mirror():
    d = tempfile.mkdtemp(prefix="tron-wst-")
    jobs.configure(d)
    wdir = os.path.join(d, "ENG-A-01")
    os.makedirs(wdir)
    with open(os.path.join(wdir, jobs.RUNNER_STATE), "w") as fh:
        json.dump({"worker_id": "ENG-A-01", "session_id": "s", "pid": os.getpid(),
                   "state": "idle", "turns": 3, "updated_at": "2026-07-01T00:00:00Z"}, fh)
    idx = jobs.index()
    rstate = (jobs.find("ENG-A-01", idx) or {}).get("state")
    w = {"id": "ENG-A-01", "status": "working"}
    if w.get("status") in ("working", "idle") and rstate in ("working", "idle"):
        w["status"] = rstate                          # the _sweep reconcile line, unit-level
    ok("AC-2 MANIFEST mirrors the runner state (working -> idle)", w["status"] == "idle")
    jobs.configure(None)
    shutil.rmtree(d, ignore_errors=True)


# ── AC-3: re-nudge survives dedupe — fresh seq delivered, same seq deduped ──
def t_dedupe_seq():
    from worker_runner import Runner
    d = tempfile.mkdtemp(prefix="tron-mbox-")
    wdir = os.path.join(d, "w")
    os.makedirs(wdir)
    r = Runner("W", wdir, "s", None, "echo", "echo")
    jobs.send(wdir, 1, "gate.local", "validate")      # first send
    jobs.send(wdir, 1, "gate.local", "validate")      # at-least-once re-append: SAME seq
    jobs.send(wdir, 2, "gate.local", "validate")      # the re-nudge: FRESH seq
    pending = r._pending(0)
    ok("AC-3 fresh-seq re-nudge is delivered (2 messages, not 1 or 3)",
       [m["seq"] for m in pending] == [1, 2], f"got {[m['seq'] for m in pending]}")
    pending_after = r._pending(1)                     # hwm=1 -> only the nudge remains
    ok("AC-3 hwm dedupe still drops the applied seq", [m["seq"] for m in pending_after] == [2])
    shutil.rmtree(d, ignore_errors=True)


# ── AC-4: the record step ──
def t_record_step():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})
    sent = []
    orig_emit = eng.emit
    eng.emit = lambda tid, slots=None, worker_id=None: sent.append((tid, dict(slots or {}))) or orig_emit(tid, slots, worker_id)
    eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
    ok("AC-4 trunk-stage evidence report -> stage record", g.get("stage") == "record")
    rec = [s for t, s in sent if t == "gate.record"]
    ok("AC-4 gate.record ordered with a mode-filled {record_path}",
       rec and rec[0].get("record_path") == "land it on trunk yourself, now",
       f"sent={sent}")
    ok("AC-4 record never parks on the operator (no merge case opened)",
       not g.get("case_merge") and not eng.st.pending_cases)
    # ✅ lands on trunk -> content check (stubbed ok) -> CLOSE
    orig_ok = trunk.record_commit_ok
    trunk.record_commit_ok = lambda *a, **k: (True, "abc12345")
    try:
        row = eng.st.row("A-01")
        row["status"] = "done"
        eng._drive_gate("A-01", g)
        ok("AC-4 ✅ at stage record -> content check -> CLOSE (slot held)",
           g.get("stage") == "close" and g.get("record_checked") is True)
    finally:
        trunk.record_commit_ok = orig_ok
    # non-conforming record -> bypass escalation, never close
    eng2 = _eng(block="A-01")
    g2 = eng2.st.gate.setdefault("A-01", {"stage": "record", "pr": None})
    orig_ok = trunk.record_commit_ok
    trunk.record_commit_ok = lambda *a, **k: (False, "touches src.txt too")
    try:
        row = eng2.st.row("A-01")
        row["status"] = "done"
        eng2._drive_gate("A-01", g2)
        ok("AC-4/AC-5 non-conforming record -> escalated, gate dropped, no close",
           "A-01" not in eng2.st.gate
           and any(t == "wall:raised:A-01" for t, _ in eng2._tq))
    finally:
        trunk.record_commit_ok = orig_ok


# ── AC-5: content check against REAL git — own diff, concurrency-safe ──
def t_record_commit_real_git():
    d = _mkrepo()
    bf = "blocks/A-01.md"
    # pure Status flip -> conforming
    with open(os.path.join(d, bf), "w") as fh:
        fh.write("# Block A-01\n**Status:** ✅ Done\n**Merge approval:** auto\n\nbody\n")
    _git(d, "commit", "-aqm", "record A-01")
    okc, detail = trunk.record_commit_ok(d, bf)
    ok("AC-5 pure Status flip conforms", okc, detail)
    # a concurrent unrelated commit AFTER the record must not false-positive (own diff)
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("other block's merge\n")
    _git(d, "commit", "-aqm", "unrelated merge")
    okc, detail = trunk.record_commit_ok(d, bf)
    ok("AC-5 concurrent unrelated merge does not false-positive", okc, detail)
    # flip + the skill-prescribed Completed date -> CONFORMING (both are block-doc
    # completion paperwork; session-end skill §6 prescribes adding the Completed date,
    # so escalating it out-of-gate walled a legitimate record — s5 first-honest-SIM)
    with open(os.path.join(d, bf), "a") as fh:
        fh.write("**Completed:** 2026-07-01\n")
    _git(d, "commit", "-aqm", "record status + completed")
    okc, detail = trunk.record_commit_ok(d, bf)
    ok("AC-5 Status flip + Completed date conforms", okc, detail)
    # a genuine non-metadata line (code/prose) in the block doc -> still non-conforming
    with open(os.path.join(d, bf), "a") as fh:
        fh.write("some sneaky prose line\n")
    _git(d, "commit", "-aqm", "record with prose")
    okc, detail = trunk.record_commit_ok(d, bf)
    ok("AC-5 a non-metadata changed line still fails the check", not okc, detail)
    # flip + a second file in the SAME commit -> non-conforming (multi-file)
    with open(os.path.join(d, bf), "a") as fh:
        fh.write("**Completed:** 2026-07-02\n")
    with open(os.path.join(d, "src.txt"), "a") as fh:
        fh.write("sneak\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "record + sneak")
    okc, detail = trunk.record_commit_ok(d, bf)
    ok("AC-5 multi-file record commit fails the check", not okc, detail)
    shutil.rmtree(d, ignore_errors=True)


# ── R5 (ADR-0005): the record gate CONFORMS to the frozen skill §6 bundled
#    close-out — the block-doc Status/Completed flip + its archival rename +
#    this block's OWN pipeline row, as ONE commit, is accepted; out-of-lane is not ──
def t_record_closeout_bundle_r5():
    d = _mkrepo()
    bf = "blocks/A-01.md"
    arch = "blocks/archive/A-01.md"
    pf = "pipeline.md"
    with open(os.path.join(d, pf), "w") as fh:
        fh.write("| A-01 | 🔄 | Block `blocks/A-01.md` |\n"
                 "| B-02 | ✅ | Block `blocks/archive/B-02.md` |\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "seed pipeline")

    def _bundle_commit(extra=None, pipeline_line=None, mv=True):
        # flip Status + Completed on the block doc
        with open(os.path.join(d, bf), "w") as fh:
            fh.write("# Block A-01\n**Status:** ✅ Done\n**Completed:** 2026-07-11\n"
                     "**Merge approval:** auto\n\nbody\n")
        if mv:
            os.makedirs(os.path.join(d, "blocks", "archive"), exist_ok=True)
            _git(d, "mv", bf, arch)
        if pipeline_line is not None:
            with open(os.path.join(d, pf), "w") as fh:
                fh.write(pipeline_line)
        if extra is not None:
            os.makedirs(os.path.dirname(os.path.join(d, extra)), exist_ok=True)
            with open(os.path.join(d, extra), "w") as fh:
                fh.write("sneak\n")
        _git(d, "add", "-A")
        _git(d, "commit", "-qm", "§6 close-out bundle")

    # (1) the canonical §6 bundle: Status/Completed + archival rename + own pipeline row -> CONFORMS
    _bundle_commit(pipeline_line="| A-01 | ✅ | Block `blocks/archive/A-01.md` |\n"
                                 "| B-02 | ✅ | Block `blocks/archive/B-02.md` |\n")
    okc, detail = trunk.record_commit_ok(d, bf, pipeline_file=pf, block_id="A-01")
    ok("R5-RECORD-CLOSEOUT (must be GREEN): the frozen skill §6 bundle "
       "(Status/Completed + archival rename + own-row pipeline) is ACCEPTED as ONE "
       "record commit — engine conforms to the skill, no forced split", okc, detail)
    shutil.rmtree(d, ignore_errors=True)

    # (2) same bundle but the pipeline edit touches ANOTHER block's row -> REFUSED (out-of-lane)
    d = _mkrepo()
    with open(os.path.join(d, pf), "w") as fh:
        fh.write("| A-01 | 🔄 | Block `blocks/A-01.md` |\n| B-02 | 🔄 | Block `blocks/B-02.md` |\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "seed pipeline")
    _bundle_commit(pipeline_line="| A-01 | ✅ | Block `blocks/archive/A-01.md` |\n"
                                 "| B-02 | ✅ | Block `blocks/archive/B-02.md` |\n")   # flipped B-02 too
    okc, detail = trunk.record_commit_ok(d, bf, pipeline_file=pf, block_id="A-01")
    ok("R5 out-of-lane pipeline row (another block) is REFUSED", not okc, detail)
    shutil.rmtree(d, ignore_errors=True)

    # (3) same bundle but a stray code file rides along -> REFUSED
    d = _mkrepo()
    with open(os.path.join(d, pf), "w") as fh:
        fh.write("| A-01 | 🔄 | Block `blocks/A-01.md` |\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "seed pipeline")
    _bundle_commit(pipeline_line="| A-01 | ✅ | Block `blocks/archive/A-01.md` |\n",
                   extra="src/sneak.ts")
    okc, detail = trunk.record_commit_ok(d, bf, pipeline_file=pf, block_id="A-01")
    ok("R5 a stray code file bundled into the close-out is REFUSED", not okc, detail)
    shutil.rmtree(d, ignore_errors=True)

    # (4) a rename that is NOT the block-doc archival -> REFUSED
    d = _mkrepo()
    _git(d, "mv", "src.txt", "src2.txt")
    with open(os.path.join(d, bf), "w") as fh:
        fh.write("# Block A-01\n**Status:** ✅ Done\n**Merge approval:** auto\n\nbody\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "status + unrelated rename")
    okc, detail = trunk.record_commit_ok(d, bf, pipeline_file=pf, block_id="A-01")
    ok("R5 a non-archival rename in the record commit is REFUSED", not okc, detail)
    shutil.rmtree(d, ignore_errors=True)
    # full-path match (R4-3): a same-named file in another directory is a DIFFERENT path —
    # a pure flip of the decoy conforms for the decoy's path, and the check for the real
    # block doc still judges the real doc's own last commit (here: multi-file base -> fail).
    d2 = _mkrepo()
    os.makedirs(os.path.join(d2, "evil", "blocks"), exist_ok=True)
    with open(os.path.join(d2, "evil", "blocks", "A-01.md"), "w") as fh:
        fh.write("**Status:** ✅ Done\n")
    _git(d2, "add", "-A")
    _git(d2, "commit", "-qm", "decoy record")
    okc, detail = trunk.record_commit_ok(d2, "evil/blocks/A-01.md")
    ok("AC-5 sanity: the decoy conforms only for its own full path", okc, detail)
    okc, detail = trunk.record_commit_ok(d2, "blocks/A-01.md")
    ok("AC-5 full-path match: the decoy commit never answers for the real block doc",
       not okc and "blocks/A-01.md" in detail, detail)
    shutil.rmtree(d2, ignore_errors=True)

    # (5) token-boundary own-lane (Sonnet review HIGH): block '01-1' must NOT smuggle a
    #     flip of '01-10''s pipeline row — a bare `block_id in line` would accept it.
    d = _mkrepo()
    b1 = "blocks/01-1.md"
    pf5 = "pipeline.md"
    with open(os.path.join(d, b1), "w") as fh:
        fh.write("# Block 01-1\n**Status:** 🔄 In progress\n\nbody\n")
    with open(os.path.join(d, pf5), "w") as fh:
        fh.write("| 01-1  | 🔄 | Block `blocks/01-1.md` |\n"
                 "| 01-10 | 🔄 | Block `blocks/01-10.md` |\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "seed 01-1 + 01-10 rows")
    with open(os.path.join(d, b1), "w") as fh:
        fh.write("# Block 01-1\n**Status:** ✅ Done\n**Completed:** 2026-07-11\n\nbody\n")
    with open(os.path.join(d, pf5), "w") as fh:   # flip BOTH 01-1's row AND 01-10's row
        fh.write("| 01-1  | ✅ | Block `blocks/01-1.md` |\n"
                 "| 01-10 | ✅ | Block `blocks/01-10.md` |\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "flip 01-1 + smuggle 01-10")
    okc, detail = trunk.record_commit_ok(d, b1, pipeline_file=pf5, block_id="01-1")
    ok("R5 token-boundary own-lane: block '01-1' cannot smuggle a '01-10' pipeline row "
       "(a bare substring match would wrongly accept it) — REFUSED", not okc, detail)
    shutil.rmtree(d, ignore_errors=True)

    # (6) a bare deletion of the block doc with NO archival is REFUSED even if body empty
    d = _mkrepo()
    bstub = "blocks/A-09.md"
    with open(os.path.join(d, bstub), "w") as fh:
        fh.write("**Status:** 🔄 In progress\n")     # stub: empty non-status body
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "seed stub")
    _git(d, "rm", "-q", bstub); _git(d, "commit", "-qm", "vanish the block doc")
    okc, detail = trunk.record_commit_ok(d, bstub)
    ok("R5 a bare deletion (no archival) of a stub block doc is REFUSED — a block doc "
       "must never just vanish at record", not okc, detail)
    shutil.rmtree(d, ignore_errors=True)

    # (7) configured archive_dir (Sonnet review MED-HIGH): a project whose archive_dir is
    #     NOT nested under blocks_dir must still recognize the genuine archival.
    d = _mkrepo()
    ba = "blocks/A-07.md"
    arch_cfg = "attic/A-07.md"           # archive_dir = attic/, not blocks/archive/
    with open(os.path.join(d, ba), "w") as fh:
        fh.write("# Block A-07\n**Status:** 🔄 In progress\n\nbody\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "seed A-07")
    with open(os.path.join(d, ba), "w") as fh:
        fh.write("# Block A-07\n**Status:** ✅ Done\n**Completed:** 2026-07-11\n\nbody\n")
    os.makedirs(os.path.join(d, "attic"), exist_ok=True)
    _git(d, "mv", ba, arch_cfg); _git(d, "commit", "-qm", "archive to attic")
    okc, detail = trunk.record_commit_ok(d, ba, archive_dir="attic/")
    ok("R5 configured archive_dir: an archival to the project's own archive_dir (not "
       "blocks/archive/) is recognized and CONFORMS", okc, detail)
    okc2, detail2 = trunk.record_commit_ok(d, ba)   # without the config -> destination out-of-lane
    ok("R5 the SAME commit without the configured archive_dir does NOT falsely conform — "
       "proves the config is what recognizes the destination", not okc2, detail2)
    shutil.rmtree(d, ignore_errors=True)


# ── R4 (ADR-0005): a CAS-loser is a non-ff the worker REBASES, never a wall ──
def t_r4_nonff_rebase():
    """A branch trunk moved past (a concurrent lander won the land.sh CAS) is a
    `non-ff`, NOT a wall — the engine never walls it (no non-ff handler in core/fsm;
    grep-clean) and the worker rebases onto fresh main and re-lands. This locks the
    primitive that ritual relies on: `would_ff` reports non-ff on a diverged branch;
    after a PURE rebase the branch is ff-able again AND its patch-id is unchanged (so
    its land grant survives — no re-gate). Sustained churn is bounded elsewhere by the
    ONE sentry idle cap -> operator (loud), never an infinite loop."""
    d = _mkrepo()
    _git(d, "checkout", "-qb", "feat/A-01x")
    with open(os.path.join(d, "mine.txt"), "w") as fh:
        fh.write("my work\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "my work")
    pid_before = trunk.patch_id(d, "feat/A-01x")
    # a concurrent lander advances trunk past this branch's base
    _git(d, "checkout", "-q", "main")
    with open(os.path.join(d, "theirs.txt"), "w") as fh:
        fh.write("concurrent land\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "concurrent land")
    okff, err = trunk.would_ff(d, "feat/A-01x")
    ok("R4 a branch trunk moved past is a non-ff (never a wall)", not okff, err)
    # the worker's ritual: rebase onto fresh main, then it is landable again
    _git(d, "checkout", "-q", "feat/A-01x")
    _git(d, "rebase", "-q", "main")
    okff2, err2 = trunk.would_ff(d, "feat/A-01x")
    ok("R4 after rebase onto fresh main the branch is ff-able again", okff2, err2)
    pid_after = trunk.patch_id(d, "feat/A-01x")
    ok("R4 a PURE rebase preserves the patch-id (the land grant survives, no re-gate)",
       bool(pid_before) and pid_before == pid_after, f"before={pid_before} after={pid_after}")
    shutil.rmtree(d, ignore_errors=True)


# ── AC-6: CLOSE cleanliness against REAL git + the confirm path — scoped to the block ──
def t_replica_clean_real_git():
    d = _mkrepo()
    clean, detail = trunk.replica_clean(d, "feat/A-01")
    ok("AC-6 clean replica reads clean", clean, detail)
    _git(d, "branch", "feat/A-01")
    clean, detail = trunk.replica_clean(d, "feat/A-01")
    ok("AC-6 leftover branch is rejected", not clean and "feat/A-01" in detail, detail)
    # a worktree checked out on THIS block's branch is a leftover
    wt = os.path.join(d, "wt-a01")
    _git(d, "worktree", "add", wt, "feat/A-01")
    clean, detail = trunk.replica_clean(d, "feat/A-01")
    ok("AC-6 leftover worktree on the block branch is rejected",
       not clean and "worktree" in detail, detail)
    _git(d, "worktree", "remove", wt)
    _git(d, "branch", "-D", "feat/A-01")
    # ANOTHER worker's live worktree/branch must never read as this closer's dirt (concurrency)
    _git(d, "branch", "feat/B-02")
    wt2 = os.path.join(d, "wt-b02")
    _git(d, "worktree", "add", wt2, "feat/B-02")
    clean, detail = trunk.replica_clean(d, "feat/A-01")
    ok("AC-6 another worker's worktree does not false-positive", clean, detail)
    shutil.rmtree(d, ignore_errors=True)


def t_confirm_close_gate():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    orig = trunk.replica_clean
    trunk.replica_clean = lambda *a, **k: (False, "leftover branch feat/A-01")
    try:
        eng._confirm_close("A-01", g)                 # claim 1 -> rejected, held
        held = "A-01" in eng.st.gate and any(w.get("block") == "A-01"
                                             for w in eng.st.workers)
        eng._confirm_close("A-01", g)                 # claim 2
        eng._confirm_close("A-01", g)                 # claim 3 -> cap -> escalate
        escalated = "A-01" not in eng.st.gate and any(t == "wall:raised:A-01"
                                                      for t, _ in eng._tq)
    finally:
        trunk.replica_clean = orig
    ok("AC-6 dirty close claim is rejected (slot held)", held)
    ok("AC-6 dirty at the cap escalates — never trust-released", escalated)
    eng2 = _eng()
    g2 = eng2.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    orig = trunk.replica_clean
    trunk.replica_clean = lambda *a, **k: (True, "")
    try:
        eng2._confirm_close("A-01", g2)
        ok("AC-6 clean close claim releases the slot",
           "A-01" not in eng2.st.gate and not any(w.get("block") == "A-01"
                                                  for w in eng2.st.workers))
    finally:
        trunk.replica_clean = orig


# ── AC-7: the recorded-tag sweep is atomic across every catalog ──
def t_tag_sweep():
    routing = util.load_yaml(os.path.join(ROOT, "routing.yaml"))
    tags = routing.get("tags", {})
    # tron-07 W6a: the receipt has its OWN row now (block:next:recorded) — same tag, its
    # route split from the build claim so it can never read as a close confirmation.
    ok("AC-7 routing.yaml knows worker.recorded",
       tags.get("worker.recorded") == {"trigger": "block:next:recorded"})
    ok("AC-7 lint CANON_TAGS knows worker.recorded", "worker.recorded" in lint.CANON_TAGS)
    with open(os.path.join(ROOT, "tron.md")) as fh:
        ok("AC-7 tron.md catalog documents worker.recorded", "worker.recorded" in fh.read())
    ctx = Ctx(ROOT) if hasattr(Ctx, "__call__") else None
    import judge
    judge._tags_cache = None

    class _C:
        routing = os.path.join(ROOT, "routing.yaml")
    ok("AC-7 classify enum admits worker.recorded",
       "worker.recorded" in judge._allowed_tags(_C()))
    judge._tags_cache = None


def main():
    t_l19_negative()
    t_idle_stages()
    t_busy_never_accrues()
    t_manifest_mirror()
    t_dedupe_seq()
    t_record_step()
    t_record_commit_real_git()
    t_record_closeout_bundle_r5()
    t_r4_nonff_rebase()
    t_replica_clean_real_git()
    t_confirm_close_gate()
    t_tag_sweep()
    fails = [x for x in _results if not x[1]]
    for name, good, detail in _results:
        print(f"  [{'PASS' if good else 'FAIL'}] {name}" + (f" — {detail}" if detail and not good else ""))
    print(f"block_01_11_test: {'PASS' if not fails else 'FAIL'} ({len(_results) - len(fails)}/{len(_results)})")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
