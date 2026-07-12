"""core.gate_full_rig — real-git, no-LLM rig proving `core.gate`'s FULL DONE
ladder (`gate.local -> gate.merge -> gate.trunk -> gate.record -> close`)
drives ONE block to a genuine clean close on the REAL surface: a real
`git init` repo copied from the same scaffold `core/gate_rig.py` /
`core/landing_rig.py` use, `meta/scripts/land.sh` run for real via
`subprocess`, a REAL declared test command run in a REAL clean detached
`git worktree` (`core.gitobs.validate_trunk` -> `engine/trunk.py`), and a
minimal duck-typed `eng` — never a faked/monkeypatched trunk, never a faked
test result.

Three scenarios:

  Phase A (happy path) — block `01-02`, worker branch `feat/01-02`. The rig
  plays the worker at every hand-off a real OS process would own: makes a
  real CODE commit on the branch (never touching the block doc), supplies a
  well-formed local-pass report, runs the REAL `land.sh` when gate.merge
  mints a grant, lets `gitobs.validate_trunk` run the project's declared
  test command (`true`, trivial, exits 0, ~0 tokens — no vitest/node
  needed) for real in a clean detached worktree at the merged sha, makes
  the record commit (Status flip, exactly one file) once trunk is green,
  runs `land.sh` again for the record grant, then tears the branch down for
  real. Asserts the terminal: block `01-02` shows ✅ on trunk (real `git
  show`), the worker slot is released, and `gate_state["stage"] ==
  "closed"` — a FULL-ladder clean close on real git.

  Phase B (adversarial — gate.local) — block `01-05`, branch `feat/01-05`.
  The rig drives `gate.advance` at `gate.local` with NO report (bare/absent)
  across several ticks. Must NOT advance to `gate.merge`: no grant minted,
  no worker order beyond the original local-validation nudge, main
  untouched.

  Phase C (adversarial — gate.trunk) — block `01-09`, branch `feat/01-09`,
  its OWN `eng` (same root/grants dir, a declared test command that FAILS:
  `exit 1`). The rig makes a real code commit, supplies a local-pass
  report, lands the merge for real (gate.merge genuinely succeeds — the
  CODE reaches trunk), then `gitobs.validate_trunk` runs the REAL failing
  command in a REAL clean worktree at the REAL merged sha. Must NOT advance
  to `gate.record`: `gate_state["stage"]` stays `"trunk"`, no record grant
  is ever minted, main is never advanced past the merge (the code landed —
  that part of the ladder is real and stays real — but the ✅ record commit
  never lands and the record case-id is never even minted).

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
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # grants.py / trunk.py live here
sys.path.insert(0, HERE)                                 # core/gate.py, core/landing.py

import grants     # noqa: E402 — respected contract, real, unmodified
import trunk      # noqa: E402 — respected contract, real, unmodified
import gate       # noqa: E402 — core/gate.py, the module under test

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
MAIN = "main"
CODE_FILE_REL = "src/lib/tip.ts"          # a real, non-meta/ source file — the "real code change"

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers (same convention as core/gate_rig.py / core/landing_rig.py) ──
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
    checkout DETACHED, ADR-0002 D1, so `land.sh`'s own `update-ref` never
    races a working-tree checkout). Same shape as `core/gate_rig.py` /
    `core/landing_rig.py`."""
    d = tempfile.mkdtemp(prefix="tron-core-gatefullrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-gate-full-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


BLOCK_DOC_TEMPLATE = """# Block {block}: gate_full_rig fixture

**Phase:** 1 — Full-ladder gate rig
**Status:** {status}
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.gate_full_rig` — proves the FULL DONE ladder
(gate.local -> gate.merge -> gate.trunk -> gate.record -> close) reaches a
genuine clean close on real git, real land.sh, and a real declared-test run.
"""


def seed_block_doc(root, block, block_file_rel):
    """Commit the block doc onto `main` for real (Status 🔄) — the baseline
    every worker branch forks from. Returns the block file's repo path."""
    _git(["checkout", "-B", MAIN, MAIN], root)
    path = os.path.join(root, block_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(BLOCK_DOC_TEMPLATE.format(block=block, status="🔄 In progress"))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: block {block} (in progress)"], root)
    _git(["checkout", "--detach", MAIN], root)
    return block_file_rel


def make_code_commit(root, branch, code_file_rel, marker):
    """Rig-as-worker: fork `branch` off current `main`, make a REAL code
    change (append a marker comment to a real source file) — never touching
    the block doc. This is the branch gate.merge lands and gate.trunk
    re-validates."""
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, code_file_rel)
    with open(path, "a") as f:
        f.write(f"\n// {marker} — core.gate_full_rig real code change\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"feat({branch}): {marker}"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def make_record_commit(root, branch, block_file_rel):
    """Rig-as-worker, second act on the SAME branch (now already merged to
    trunk by gate.merge): flip the block doc's Status field 🔄 -> ✅ —
    exactly that one file, exactly that one field."""
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


def make_code_commit_touching_doc(root, branch, code_file_rel, block_file_rel, marker):
    """Rig-as-worker, the T2-01-07 shape: the CODE commit gate.merge lands
    touches BOTH a real source file AND the block doc — a worker folding a
    completion note into the block doc during the code phase (NOT the Status
    field). Once merged, this already-landed commit is the LAST commit touching
    the block doc, so a `_advance_record` that anchored its baseline before the
    ladder ran would read THIS merge commit as the record commit and escalate it
    out-of-gate (it touches >1 file, and its block-doc lines aren't the Status
    field). Returns the branch tip."""
    _git(["checkout", "-B", branch, MAIN], root)
    cpath = os.path.join(root, code_file_rel)
    with open(cpath, "a") as f:
        f.write(f"\n// {marker} — core.gate_full_rig real code change\n")
    bpath = os.path.join(root, block_file_rel)
    with open(bpath, "a") as f:
        f.write(f"\n<!-- completion note ({marker}): domain logic implemented, suite green -->\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"feat({branch}): {marker} + completion note in block doc"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def make_closeout_commit(root, branch, block):
    """Rig-as-worker, session-end (third act on the SAME branch, now already
    ✅-on-trunk via gate.record): a REAL multi-file close-out commit — a
    session log plus a pipeline-sync line — the paperwork PMT-CLOSE lands via
    its OWN `close`-scoped grant, deliberately SEPARATE from the single-file
    record flip. Deliberately does NOT touch the block doc (record already
    flipped it) so this exercises the close LAND path without disturbing the
    record assertions. This is the commit whose missing land wedged every
    live close before T2-01-05's fix (the worker committed it, reported
    `clean`, and blocked forever on a grant `_advance_close` never minted)."""
    _git(["checkout", branch], root)
    log_rel = os.path.join("meta", "agents", "tron", "logs", f"close-{block}.md")
    log_path = os.path.join(root, log_rel)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w") as f:
        f.write(f"# close-out {block}\nsession-end paperwork (rig-as-worker)\n")
    pipe_path = os.path.join(root, "meta", "pipeline.md")
    with open(pipe_path, "a") as f:
        f.write(f"- {block}: done\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"close: {block} session-end paperwork"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def make_second_closeout_commit(root, branch, block):
    """Rig-as-worker: a SECOND close-out commit on the SAME branch AFTER the
    first close-out already landed — the exact T2-17 shape (a follow-up
    Completed-date fix the worker commits after its first close land). Distinct
    content -> a genuinely NEW patch-id, so a content-bound close case-id MUST
    differ from the first close's; a cached case-id would reuse the first's
    already-consumed receipt and land.sh would no-op this commit. Returns tip."""
    _git(["checkout", branch], root)
    pipe_path = os.path.join(root, "meta", "pipeline.md")
    with open(pipe_path, "a") as f:
        f.write(f"- {block}: completed 2026-07-12 (follow-up fix)\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"close: {block} follow-up completed-date fix"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def carve_worktree(root, branch, rel_path):
    """Rig-as-worker: carve a REAL linked worktree checked out on `branch` —
    the shape a real worker runs from (`meta/agents/tron/scratch/<wid>/...`).
    Its presence is exactly what `replica_clean` must observe gone before the
    slot releases; a rig that closes with NO worktree (as this one did before
    T2-01-05) can never exercise the teardown the real close hinges on.
    Returns the absolute worktree path."""
    wt = os.path.join(root, rel_path)
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    _git(["worktree", "add", wt, branch], root)
    return wt


def run_land(root, grants_dir, case_id):
    """Run the REAL `meta/scripts/land.sh` via subprocess — the rig playing
    the worker ordered to land its own grant, per ADR-0002 D2."""
    r = subprocess.run(
        ["bash", os.path.join(root, "meta", "scripts", "land.sh"), case_id,
         "--main", MAIN, "--grants-dir", grants_dir],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "LAND_MAIN_BRANCH": MAIN})
    return r.returncode, r.stdout, r.stderr


class _Events:
    def __init__(self):
        self.log = []

    def event(self, type_, **payload):
        self.log.append({"type": type_, "payload": payload})


class _Ctx:
    """Adds `scratch_dir` (the scratch-worktree-admin root
    `gitobs.validate_trunk`'s clean detached checkout is carved under) on
    top of `.grants_dir` — mirrors `engine/ctx.py`'s own property shapes,
    both real, both under the rig's real repo root."""
    def __init__(self, root, grants_dir):
        self.grants_dir = grants_dir
        self.scratch_dir = os.path.join(root, "meta", "agents", "tron", "scratch")


class MiniEng:
    """The minimal duck-typed `eng` — everything `core/landing.py` needs,
    PLUS `_release_worker` (brick 2's addition) PLUS the wave-3 additions
    `gate.trunk` reads: `.paths["test_command"]`/`["test_env"]`/
    `["ci_check_name"]` and `.ctx.scratch_dir`. `.workers` is a plain dict
    this rig owns and asserts against; `gate.py` never reads it directly,
    only ever calls `_release_worker`."""
    def __init__(self, root, grants_dir, test_command):
        self.paths = {
            "root": root,
            "main_branch": MAIN,
            "test_command": test_command,     # the project's DECLARED trunk-validation command
            "test_env": None,
            "ci_check_name": None,            # None -> command mode, never CI mode, in this rig
        }
        self.dry = False                 # HARD RULE: real trunk observation throughout
        self.ctx = _Ctx(root, grants_dir)
        self.events = _Events()
        self.log_lines = []
        self.orders = []
        self.workers = {}                # wid -> {"block":..., "status": "assigned"|"released"}

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


LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "npm ci --no-audit --no-fund && npx vitest run -> 9/9 green (rig-supplied local report)"}


def drive_full(eng, block, gstate, root, grants_dir, local_report=None,
               teardown_branch=None, teardown_worktree=None,
               stop_outcomes=frozenset(), max_iters=40):
    """The rig's tick-loop stand-in for the FULL ladder: repeatedly call
    `gate.advance`, playing the worker's real-OS-process actions on the
    outcomes that require one — `merge_pending`/`record_pending`/
    `close_pending` -> run the REAL land.sh for that stage's own case-id;
    `close_holding` (paperwork already on trunk, replica not yet clean) ->
    the worker's post-land teardown: remove any linked worktree on the
    branch, then delete the branch, for real. `local_report` is forwarded to
    every call (harmless once the stage has moved past `gate.local` —
    `advance` only consults it while stage == STAGE_LOCAL)."""
    case_key = {"merge_pending": "merge_case_id",
                "record_pending": "record_case_id",
                "close_pending": "close_case_id"}
    history = []
    torn_down = False
    for _ in range(max_iters):
        outcome, detail = gate.advance(eng, block, gstate, local_report=local_report)
        history.append((outcome, detail))
        if outcome in case_key:
            case_id = gstate[case_key[outcome]]
            rc, out, err = run_land(root, grants_dir, case_id)
            history.append(("land.sh", f"rc={rc} out={out!r} err={err!r}"))
            continue
        if outcome == "close_holding" and teardown_branch and not torn_down:
            if teardown_worktree:
                _git(["worktree", "remove", "--force", teardown_worktree], root)
            _git(["branch", "-D", teardown_branch], root)
            history.append(("teardown", f"removed worktree + deleted branch {teardown_branch}"))
            torn_down = True
            continue
        if outcome in stop_outcomes:
            break
    return history


def main():
    root = build_root()
    grants_dir = os.path.join(root, "meta", "agents", "tron", "grants")

    # ══ Phase A — happy path: local -> merge -> trunk -> record -> close ══
    BLOCK_A, BRANCH_A, WID_A = "01-02", "feat/01-02", "engineer-01-02"
    eng_a = MiniEng(root, grants_dir, test_command="true")   # trivial, exits 0, ~0 tokens
    eng_a.workers[WID_A] = {"block": BLOCK_A, "status": "assigned"}

    block_file_a = seed_block_doc(root, BLOCK_A, "meta/blocks/01-02.md")
    code_tip_a = make_code_commit(root, BRANCH_A, CODE_FILE_REL, "01-02-real-change")
    ok("A0: rig-as-worker made a real CODE commit on the branch, off trunk, "
       "never touching the block doc",
       bool(code_tip_a) and not is_ancestor(root, code_tip_a, MAIN),
       f"code_tip_a={code_tip_a}")

    gstate_a = gate.new_state_full(eng_a, BLOCK_A, block_file_a, BRANCH_A, WID_A)
    ok("A1: gate_state starts at STAGE_LOCAL (the full ladder's head)",
       gstate_a["stage"] == gate.STAGE_LOCAL, f"stage={gstate_a['stage']}")

    main_before_a = _git_out(["rev-parse", MAIN], root)

    # -- gate.local: one bare call first (proves the ordering side effect fires and
    #    a report-less call never advances), then drive with a well-formed report --
    outcome0, detail0 = gate.advance(eng_a, BLOCK_A, gstate_a)
    ok("A2: a bare gate.local call (no report) does NOT advance — holds at local",
       outcome0 == "local_waiting" and gstate_a["stage"] == gate.STAGE_LOCAL,
       f"outcome0={outcome0} detail0={detail0} stage={gstate_a['stage']}")
    ok("A3: gate.local ordered the worker exactly once (idempotent side effect)",
       len([o for o in eng_a.orders if o[2] == "gate.local"]) == 1,
       f"orders={eng_a.orders}")

    history_a = drive_full(eng_a, BLOCK_A, gstate_a, root, grants_dir,
                           local_report=LOCAL_PASS_REPORT,
                           stop_outcomes={"trunk_passed"}, max_iters=20)
    outcomes_a = [o for o, _ in history_a]

    ok("A4: gate.local advanced on the well-formed local-pass report",
       "local_passed" in outcomes_a, f"outcomes={outcomes_a}")
    ok("A5 (THE KILLER — must be GREEN): gate.merge genuinely landed the CODE branch "
       "on trunk via the REAL land.sh (real ancestry, no fake/no monkeypatch)",
       "merge_landed" in outcomes_a and "land.sh" in outcomes_a
       and is_ancestor(root, code_tip_a, MAIN),
       f"outcomes={outcomes_a} code_tip_a={code_tip_a} "
       f"is_ancestor={is_ancestor(root, code_tip_a, MAIN)}")
    merged_sha_a = gstate_a.get("merged_sha")
    ok("A6: gate.merge captured the merged sha == the code commit's own real sha",
       merged_sha_a == code_tip_a, f"merged_sha_a={merged_sha_a} code_tip_a={code_tip_a}")
    ok("A7 (THE OTHER KILLER — must be GREEN): gate.trunk genuinely ran the declared "
       "test command in a REAL clean detached worktree at the merged sha and observed "
       "PASS (no fake trunk, no fake test result)",
       "trunk_passed" in outcomes_a and gstate_a["stage"] == gate.STAGE_RECORD,
       f"outcomes={outcomes_a} stage={gstate_a['stage']} "
       f"trunk_verdict_detail={gstate_a.get('trunk_verdict_detail')}")

    main_after_merge_a = _git_out(["rev-parse", MAIN], root)
    ok("A8: main genuinely advanced to the code commit's own sha (real CAS, real land.sh)",
       main_after_merge_a == code_tip_a and main_after_merge_a != main_before_a,
       f"main_before={main_before_a} main_after={main_after_merge_a} code_tip_a={code_tip_a}")

    # -- gate.record, on the SAME branch, second act: the Status flip --
    record_tip_a = make_record_commit(root, BRANCH_A, block_file_a)
    ok("A9: rig-as-worker made the record commit (Status flip) on the already-merged "
       "branch, off the current trunk",
       bool(record_tip_a) and not is_ancestor(root, record_tip_a, MAIN),
       f"record_tip_a={record_tip_a}")

    history_a2 = drive_full(eng_a, BLOCK_A, gstate_a, root, grants_dir,
                            stop_outcomes={"record_landed"}, max_iters=20)
    outcomes_a2 = [o for o, _ in history_a2]
    ok("A10 (THE RECORD KILLER — must be GREEN): the ✅ status commit genuinely landed "
       "on trunk via a SECOND, independently content-bound grant (role='record', "
       "distinct from gate.merge's role='merge' case-id)",
       "record_landed" in outcomes_a2 and "land.sh" in outcomes_a2
       and is_ancestor(root, record_tip_a, MAIN)
       and gstate_a["record_case_id"] != gstate_a["merge_case_id"],
       f"outcomes={outcomes_a2} record_case_id={gstate_a.get('record_case_id')} "
       f"merge_case_id={gstate_a.get('merge_case_id')}")

    doc_on_main_a = _git_out(["show", f"{MAIN}:{block_file_a}"], root)
    ok("A11: the block doc AS READ FROM main shows ✅ (real git show on trunk)",
       "**Status:** ✅ Done" in doc_on_main_a,
       f"doc head={doc_on_main_a.splitlines()[:4]}")
    ok("A12: gate_state advanced to the close stage", gstate_a["stage"] == gate.STAGE_CLOSE,
       f"stage={gstate_a['stage']}")

    # Realistic close: the worker commits a SECOND, multi-file close-out on the
    # branch (session log + pipeline sync — separate from the record flip) and
    # is working from a REAL linked worktree. This is the exact shape that
    # exposed the 'close never lands, worker blocks forever, sentry escalates a
    # block whose work is actually done' root live in T2-01-05 — the old rig
    # closed with no close-out commit and no worktree, so it never touched the
    # close LAND path and the wall stayed invisible.
    closeout_tip_a = make_closeout_commit(root, BRANCH_A, BLOCK_A)
    wt_a = carve_worktree(root, BRANCH_A, os.path.join("meta", "agents", "tron",
                                                       "scratch", "engineer-01-02", "logic"))
    ok("A12b: rig-as-worker made a real multi-file close-out commit off trunk AND "
       "is on a real linked worktree on the branch (the shape a real close has)",
       bool(closeout_tip_a) and not is_ancestor(root, closeout_tip_a, MAIN)
       and any(b == BRANCH_A for _, b in trunk.list_worktrees(root)),
       f"closeout_tip={closeout_tip_a} worktrees={trunk.list_worktrees(root)}")

    history_a3 = drive_full(eng_a, BLOCK_A, gstate_a, root, grants_dir,
                            teardown_branch=BRANCH_A, teardown_worktree=wt_a,
                            stop_outcomes={"closed", "escalate"}, max_iters=12)
    outcomes_a3 = [o for o, _ in history_a3]
    ok("A13 (THE CLOSE KILLER — must be GREEN): close LANDED the close-out paperwork "
       "via its OWN content-bound grant (close_pending -> real land.sh -> replica "
       "teardown -> closed), no escalate; close_case_id distinct from merge & record",
       "close_pending" in outcomes_a3 and "land.sh" in outcomes_a3
       and "closed" in outcomes_a3 and "teardown" in outcomes_a3
       and "escalate" not in outcomes_a3
       and is_ancestor(root, closeout_tip_a, MAIN)
       and gstate_a.get("close_case_id") not in (None, gstate_a["record_case_id"],
                                                 gstate_a["merge_case_id"]),
       f"outcomes={outcomes_a3} close_case={gstate_a.get('close_case_id')}")

    branch_gone_a = not trunk.branch_exists(root, BRANCH_A, False)
    clean_now_a, clean_detail_a = trunk.replica_clean(root, BRANCH_A, MAIN, False)
    ok("A14: gate.py verified the replica clean on REAL git (branch deleted, no "
       "worktree on it) before releasing anything",
       branch_gone_a and clean_now_a,
       f"branch_gone={branch_gone_a} clean={clean_now_a} detail={clean_detail_a}")
    ok("A15 (THE SLOT KILLER — must be GREEN): the worker slot was REALLY released",
       eng_a.workers.get(WID_A, {}).get("status") == "released",
       f"worker_state={eng_a.workers.get(WID_A)}")

    final_sha_a = _git_out(["rev-parse", MAIN], root)
    ok("A16 (TERMINAL — must be GREEN): block 01-02 shows ✅ ON TRUNK (real sha), the "
       "close-out paperwork is the trunk tip, worker slot freed, gate_state == closed "
       "— a FULL-ladder clean close on real git, close-out landed and all",
       gstate_a["stage"] == gate.STAGE_CLOSED
       and eng_a.workers.get(WID_A, {}).get("status") == "released"
       and "**Status:** ✅ Done" in _git_out(["show", f"{MAIN}:{block_file_a}"], root)
       and final_sha_a == closeout_tip_a,
       f"gate_stage={gstate_a['stage']} worker={eng_a.workers.get(WID_A)} "
       f"final_main={final_sha_a} closeout_tip_a={closeout_tip_a}")

    # ══ Phase A' — T2-17 REGRESSION: a branch re-authored at the close stage
    #    gets a FRESH content-bound case-id and lands its new commit. Before the
    #    fix, gate.py CACHED the per-stage case-id (`gate_state.get(...) or ...`),
    #    so a follow-up commit reused the first close's already-consumed receipt
    #    and the worker's REAL land.sh short-circuited ("already consumed —
    #    nothing to do, exit 0") WITHOUT landing it: trunk stuck, worker wall,
    #    stall, operator escalation (the T2-17 REJECT). This drives the close
    #    stage TWICE on one branch through the REAL land.sh and asserts the
    #    second commit reaches trunk under a distinct case-id. ══
    BLOCK_R, BRANCH_R, WID_R = "01-07", "feat/01-07", "engineer-01-07"
    eng_r = MiniEng(root, grants_dir, test_command="true")
    eng_r.workers[WID_R] = {"block": BLOCK_R, "status": "assigned"}
    block_file_r = seed_block_doc(root, BLOCK_R, "meta/blocks/01-07.md")
    make_code_commit(root, BRANCH_R, CODE_FILE_REL, "01-07-real-change")
    gstate_r = gate.new_state_full(eng_r, BLOCK_R, block_file_r, BRANCH_R, WID_R)
    drive_full(eng_r, BLOCK_R, gstate_r, root, grants_dir,
               local_report=LOCAL_PASS_REPORT, stop_outcomes={"trunk_passed"}, max_iters=20)
    make_record_commit(root, BRANCH_R, block_file_r)
    drive_full(eng_r, BLOCK_R, gstate_r, root, grants_dir,
               stop_outcomes={"record_landed"}, max_iters=20)

    # first close-out lands, then HOLD (no teardown args) so the branch survives
    closeout1_r = make_closeout_commit(root, BRANCH_R, BLOCK_R)
    drive_full(eng_r, BLOCK_R, gstate_r, root, grants_dir,
               stop_outcomes={"close_holding"}, max_iters=12)
    close_case_1 = gstate_r.get("close_case_id")
    ok("A'1: first close-out commit landed on trunk under a content-bound close "
       "case-id (branch still alive, not yet torn down)",
       is_ancestor(root, closeout1_r, MAIN) and bool(close_case_1),
       f"close_case_1={close_case_1} landed1={is_ancestor(root, closeout1_r, MAIN)}")

    # the T2-17 follow-up: a SECOND close-out commit re-authors the branch
    closeout2_r = make_second_closeout_commit(root, BRANCH_R, BLOCK_R)
    ok("A'2: rig-as-worker re-authored the branch with a SECOND close-out commit "
       "off the current trunk (the follow-up-fix shape)",
       bool(closeout2_r) and not is_ancestor(root, closeout2_r, MAIN),
       f"closeout2_r={closeout2_r}")

    history_r = drive_full(eng_r, BLOCK_R, gstate_r, root, grants_dir,
                           teardown_branch=BRANCH_R, teardown_worktree=None,
                           stop_outcomes={"closed", "escalate"}, max_iters=14)
    close_case_2 = gstate_r.get("close_case_id")
    main_final_r = _git_out(["rev-parse", MAIN], root)
    ok("A'3 (T2-17 KILLER — must be GREEN): the re-authored branch got a FRESH "
       "content-bound close case-id (NOT the cached one), so the REAL land.sh landed "
       "the SECOND close-out commit — trunk reached it, no escalate. A cached case-id "
       "reuses the first's consumed receipt and land.sh no-ops the second commit.",
       close_case_2 != close_case_1
       and is_ancestor(root, closeout2_r, MAIN)
       and main_final_r == closeout2_r
       and "escalate" not in [o for o, _ in history_r],
       f"close_case_1={close_case_1} close_case_2={close_case_2} "
       f"main_final={main_final_r} closeout2={closeout2_r} "
       f"history={[o for o, _ in history_r]}")

    # ══ Phase B — adversarial: gate.local with a bare/absent report never advances ══
    BLOCK_B, BRANCH_B, WID_B = "01-05", "feat/01-05", "engineer-01-05"
    eng_b = MiniEng(root, grants_dir, test_command="true")
    eng_b.workers[WID_B] = {"block": BLOCK_B, "status": "assigned"}
    block_file_b = seed_block_doc(root, BLOCK_B, "meta/blocks/01-05.md")
    make_code_commit(root, BRANCH_B, CODE_FILE_REL, "01-05-untested-change")

    gstate_b = gate.new_state_full(eng_b, BLOCK_B, block_file_b, BRANCH_B, WID_B)
    main_before_b = _git_out(["rev-parse", MAIN], root)

    outcomes_b = []
    for report in (None, {}, {"verdict": "pass"}, {"verdict": "pass", "evidence": ""},
                  {"verdict": "fail", "evidence": "it broke"}):
        o, d = gate.advance(eng_b, BLOCK_B, gstate_b, local_report=report)
        outcomes_b.append(o)

    main_after_b = _git_out(["rev-parse", MAIN], root)
    ok("B1 (ADVERSARIAL — must NOT advance): a bare/absent/malformed local report "
       "NEVER advances gate.local to gate.merge — every call holds",
       all(o == "local_waiting" for o in outcomes_b)
       and gstate_b["stage"] == gate.STAGE_LOCAL,
       f"outcomes={outcomes_b} stage={gstate_b['stage']}")
    ok("B2: no grant was ever minted and no land.sh ever ran for block 01-05 — "
       "main is byte-for-byte unchanged across the whole drive",
       gstate_b.get("merge_case_id") is None and main_after_b == main_before_b,
       f"merge_case_id={gstate_b.get('merge_case_id')} "
       f"main_before={main_before_b} main_after={main_after_b}")
    ok("B3: gate.local's own worker-nudge fired exactly once (idempotent), never "
       "re-spammed across the five report-less/malformed ticks",
       len([o for o in eng_b.orders if o[2] == "gate.local"]) == 1,
       f"orders={eng_b.orders}")

    # ══ Phase C — adversarial: a FAILING declared trunk test never advances to record ══
    BLOCK_C, BRANCH_C, WID_C = "01-09", "feat/01-09", "engineer-01-09"
    eng_c = MiniEng(root, grants_dir, test_command="exit 1")   # REAL, deterministically FAILING
    eng_c.workers[WID_C] = {"block": BLOCK_C, "status": "assigned"}
    block_file_c = seed_block_doc(root, BLOCK_C, "meta/blocks/01-09.md")
    code_tip_c = make_code_commit(root, BRANCH_C, CODE_FILE_REL, "01-09-breaks-on-trunk")

    gstate_c = gate.new_state_full(eng_c, BLOCK_C, block_file_c, BRANCH_C, WID_C)
    history_c = drive_full(eng_c, BLOCK_C, gstate_c, root, grants_dir,
                           local_report=LOCAL_PASS_REPORT,
                           stop_outcomes={"trunk_failed"}, max_iters=20)
    outcomes_c = [o for o, _ in history_c]

    ok("C1: gate.merge genuinely landed 01-09's CODE on trunk (the merge itself is "
       "real and correct — it is gate.TRUNK's re-validation that must catch the red)",
       "merge_landed" in outcomes_c and is_ancestor(root, code_tip_c, MAIN),
       f"outcomes={outcomes_c} code_tip_c={code_tip_c}")
    ok("C2 (THE ADVERSARIAL TRUNK KILLER — must be GREEN): gate.trunk ran the REAL "
       "failing declared command (`exit 1`) in a REAL clean detached worktree at the "
       "REAL merged sha and observed FAIL — genuinely, not simulated",
       "trunk_failed" in outcomes_c and gstate_c["stage"] == gate.STAGE_TRUNK,
       f"outcomes={outcomes_c} stage={gstate_c['stage']} "
       f"verdict_detail={gstate_c.get('trunk_verdict_detail')}")

    for extra_call in range(3):
        o, d = gate.advance(eng_c, BLOCK_C, gstate_c)
        ok(f"C3.{extra_call}: re-driving gate.trunk after a FAIL never advances to "
           f"gate.record (holds, never escalates on a genuine red)",
           o == "trunk_failed" and gstate_c["stage"] == gate.STAGE_TRUNK,
           f"outcome={o} detail={d} stage={gstate_c['stage']}")

    ok("C4: no record grant was ever minted for 01-09 — the ✅ status commit was "
       "never even attempted, let alone landed",
       gstate_c.get("record_case_id") is None, f"record_case_id={gstate_c.get('record_case_id')}")
    doc_on_main_c = _git_out(["show", f"{MAIN}:{block_file_c}"], root)
    ok("C5: the block doc on trunk still shows 🔄 — never flipped to ✅",
       "**Status:** 🔄 In progress" in doc_on_main_c,
       f"doc head={doc_on_main_c.splitlines()[:4]}")

    # ══ Phase D — the T2-01-07 record-baseline wall: the merge commit ALSO
    #    touched the block doc; gate.record must WAIT for the clean flip, never
    #    escalate the already-landed merge commit as an out-of-gate record ══
    BLOCK_D, BRANCH_D, WID_D = "01-11", "feat/01-11", "engineer-01-11"
    eng_d = MiniEng(root, grants_dir, test_command="true")
    eng_d.workers[WID_D] = {"block": BLOCK_D, "status": "assigned"}
    block_file_d = seed_block_doc(root, BLOCK_D, "meta/blocks/01-11.md")
    code_tip_d = make_code_commit_touching_doc(root, BRANCH_D, CODE_FILE_REL,
                                               block_file_d, "01-11-logic")

    gstate_d = gate.new_state_full(eng_d, BLOCK_D, block_file_d, BRANCH_D, WID_D)
    # Drive local -> merge -> trunk -> record ORDER. The merge commit (which
    # touched the block doc) is now on trunk; gate.record must anchor its
    # baseline HERE and wait, never escalate that merge commit.
    hist_d1 = drive_full(eng_d, BLOCK_D, gstate_d, root, grants_dir,
                         local_report=LOCAL_PASS_REPORT,
                         stop_outcomes={"record_waiting"}, max_iters=20)
    outcomes_d1 = [o for o, _ in hist_d1]
    ok("D1 (THE RECORD-BASELINE KILLER — must be GREEN): with the merge commit "
       "itself touching the block doc, gate.record ORDERED the flip and is "
       "WAITING for it — it did NOT escalate the already-landed merge commit "
       "out-of-gate",
       "record_waiting" in outcomes_d1 and "escalate" not in outcomes_d1
       and gstate_d["stage"] == gate.STAGE_RECORD and gstate_d.get("record_ordered"),
       f"outcomes={outcomes_d1} stage={gstate_d['stage']} escalation={gstate_d.get('escalation')}")

    # Now the worker makes the REAL single-file Status flip; gate.record must
    # validate THAT commit, land it, and close cleanly.
    record_tip_d = make_record_commit(root, BRANCH_D, block_file_d)
    hist_d2 = drive_full(eng_d, BLOCK_D, gstate_d, root, grants_dir,
                         stop_outcomes={"record_landed", "escalate"}, max_iters=20)
    outcomes_d2 = [o for o, _ in hist_d2]
    ok("D2 (must be GREEN): gate.record validated the CLEAN single-file flip "
       "commit (not the merge commit), landed it via its own grant, never "
       "escalated",
       "record_landed" in outcomes_d2 and "escalate" not in outcomes_d2
       and is_ancestor(root, record_tip_d, MAIN)
       and gstate_d["stage"] == gate.STAGE_CLOSE,
       f"outcomes={outcomes_d2} stage={gstate_d['stage']} escalation={gstate_d.get('escalation')}")
    doc_on_main_d = _git_out(["show", f"{MAIN}:{block_file_d}"], root)
    ok("D3: the block doc on trunk shows ✅ — the clean flip genuinely landed",
       "**Status:** ✅ Done" in doc_on_main_d, f"doc head={doc_on_main_d.splitlines()[:4]}")

    # ══ RM (s5 first-honest-SIM lock): the record gate accepts the `**Status:**`
    #    flip AND the `**Completed:**` date the session-end skill (§6) prescribes
    #    — block-doc completion paperwork. Only genuine out-of-gate changes
    #    (code/other files/prose) still escalate. ══
    import tempfile
    rmd = tempfile.mkdtemp(prefix="gate-full-rig-record-meta-")
    rmbf = "meta/blocks/09-01.md"
    os.makedirs(os.path.join(rmd, "meta", "blocks"), exist_ok=True)
    def _rmw(text):
        with open(os.path.join(rmd, rmbf), "w") as f:
            f.write(text)
    _git(["init", "-b", MAIN], rmd)
    _git(["config", "user.email", "r@t.local"], rmd)
    _git(["config", "user.name", "record-meta-rig"], rmd)
    _rmw("# Block 09-01\n\n**Status:** 🔄 In progress\n")
    _git(["add", "-A"], rmd); _git(["commit", "-m", "seed"], rmd)
    _rmw("# Block 09-01\n\n**Status:** ✅ Done\n**Completed:** 2026-07-11\n")
    _git(["add", "-A"], rmd); _git(["commit", "-m", "record: done"], rmd)
    okA, detA = trunk.record_commit_ok(rmd, rmbf, dry=False, truth_ref=MAIN)
    ok("RM1 (RECORD-METADATA LOCK — must be GREEN): a record commit with the "
       "Status flip AND the skill-prescribed Completed date is conforming",
       okA is True, f"ok={okA} detail={detA}")
    _rmw("# Block 09-01\n\n**Status:** ✅ Done\n**Completed:** 2026-07-11\n\nsneaky extra prose\n")
    _git(["add", "-A"], rmd); _git(["commit", "-m", "record: sneaky"], rmd)
    okB, detB = trunk.record_commit_ok(rmd, rmbf, dry=False, truth_ref=MAIN)
    ok("RM2 (OUT-OF-GATE PARITY — must be GREEN): a record commit that also "
       "changes a non-metadata line is still escalated (out-of-gate)",
       okB is False, f"ok={okB} detail={detB}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.gate_full_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"BLOCK_A={BLOCK_A} BRANCH_A={BRANCH_A} code_tip_a={code_tip_a} "
          f"record_tip_a={record_tip_a}")
    print(f"main tip after Phase A close={_git_out(['rev-parse', MAIN], root)}")
    print(f"BLOCK_B={BLOCK_B} BRANCH_B={BRANCH_B} (never left gate.local)")
    print(f"BLOCK_C={BLOCK_C} BRANCH_C={BRANCH_C} code_tip_c={code_tip_c} "
          f"(merged, then held at gate.trunk on a real FAIL)")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
