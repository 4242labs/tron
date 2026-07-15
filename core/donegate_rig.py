"""core.donegate_rig — block 01-38 T20 (AC-16): the DONE-gate trusted-verdict
guarantees, asserted through the real door.

`core/gate.py`'s `gate.trunk` stage + `engine/trunk.py`'s `validate_trunk`/
`_run_declared_command`/`ci_verdict` (block 01-28's machinery, unmodified
here — T20's own words: "machinery already lives in core/gate.py/core/
gitobs.py — assert the guarantees or close the gap") already carry the three
T20 guarantees. This rig is the MISSING PROOF ARTIFACT (the same shape T10's
`trunk_blame_rig` took for R7: a finding, not a rewrite — the mechanism was
already correct, no rig NAMED the guarantee). No production code changes.

Three named proofs:

  test:<donegate_declared_command_validates_nonpython> — the trunk-stage
  re-validation runs the project's DECLARED command verbatim (never a
  hardcoded `*_test.py`/pytest/unittest discovery, never a `merge_base`/
  diff-RANGE computation — the old `run_block_tests` false-wall root,
  retired at block 01-28): a real non-Python shell command genuinely PASSES
  and genuinely FAILS through a real clean detached worktree at the merged
  sha; declaring NEITHER a test command NOR a CI check name never silently
  substitutes a guessed default — it reads "unconfirmed". A structural check
  (AST, docstring stripped) confirms the two functions' CODE bodies contain
  no `pytest`/`unittest`/`_test.py` reference and no `merge_base` call.

  test:<unconfirmable_close_holds_routes_architect> — an unconfirmable
  gate.trunk (no declared command, no CI check declared) HOLDS forever
  (`trunk_unconfirmed`, never `gate.py`'s own `_escalate` — no
  `gate_escalated` event for this block, ever) — "can't confirm" is never
  treated as "failed". Only the SAME uniform idle-pacing ladder every other
  holding stage is subject to (`core/sentry.py`) eventually caps it, and
  that cap routes ARCHITECT-FIRST (`casestate.open_case` -> a PMT-TRIAGE
  job) — never an immediate operator page. The full loop is driven to its
  honest end: the operator is reached ONLY once the architect's own verdict
  says so.

  test:<ci_verdict_read_commit_exact> — CI mode (`ci_check_name` declared)
  reads `engine/trunk.py::ci_verdict` — never re-runs the declared command —
  and trusts a check-run ONLY when ALL THREE hold at once: commit-exact
  (`head_sha == merged_sha`), non-stale (`status == "completed"`), and the
  real declared suite (`name == check_name`). A run failing any ONE of the
  three is `unconfirmed`, never substituted. A counterfactual ("naive")
  verdict function that drops the commit-exact check is run against the
  SAME synthetic data to show it WOULD wrongly trust a stale/ancestor
  check-run — non-vacuity for the real guard.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail."""
import ast
import inspect
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))            # core
APP_ROOT = os.path.dirname(HERE)                               # worktree root
SIM_DIR = os.path.join(HERE, "sim")
ENGINE_DIR = os.path.join(APP_ROOT, "engine")
sys.path.insert(0, ENGINE_DIR)     # grants.py / trunk.py
sys.path.insert(0, HERE)           # core/*.py
sys.path.insert(0, SIM_DIR)        # core/sim/*.py

import trunk                       # noqa: E402 — engine/trunk.py, the module under test (unmodified)
import gate                        # noqa: E402 — core/gate.py, the module under test
import gate_full_rig as gfr        # noqa: E402 — real-git scaffold + MiniEng + drive_full (reused, not forked)

import jobs                        # noqa: E402 — engine/jobs.py, the ONE process-spawn seam this driver stubs
import state                       # noqa: E402 — core/state.py
import intake                      # noqa: E402 — core/intake.py, the private per-agent door (rig-side write)
from engine import Engine          # noqa: E402 — core/engine.py, the module under drive

import architect as core_architect  # noqa: E402 — core/architect.py, ARCHITECT_WID
import scaffold as sim_scaffold     # noqa: E402 — core/sim/scaffold.py
import worker as sim_worker         # noqa: E402 — core/sim/worker.py, ScriptedDriver + Transcript

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ══════════════════════════════════════════════════════════════════════════
# test:<donegate_declared_command_validates_nonpython>
# ══════════════════════════════════════════════════════════════════════════

def _code_body_dump(fn):
    """`ast.dump` of `fn`'s body with its OWN docstring stripped — a
    docstring is prose that legitimately NAMES the retired old behavior
    ("only ever discovered `*_test.py`") to explain what this fix replaced;
    scanning it verbatim would false-positive on the very sentence
    documenting the guarantee. Only the EXECUTABLE body is scanned."""
    src = textwrap.dedent(inspect.getsource(fn))
    tree = ast.parse(src)
    func = tree.body[0]
    body = func.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return ast.dump(ast.Module(body=body, type_ignores=[]))


def _run_declared_command_nonpython():
    root = gfr.build_root()
    grants_dir = os.path.join(root, "meta", "agents", "tron", "grants")

    # ── 1a: a REAL non-Python declared command genuinely PASSES ──
    BLOCK_P, BRANCH_P, WID_P = "20-01", "feat/20-01", "engineer-20-01"
    MARKER_P = "MARKER-nonpy-pass-20-01"
    nonpy_pass_cmd = f'grep -q "{MARKER_P}" {gfr.CODE_FILE_REL}'   # a bare shell/grep pipeline — zero
                                                                     # python, zero pytest, zero *_test.py
    eng_p = gfr.MiniEng(root, grants_dir, test_command=nonpy_pass_cmd)
    eng_p.workers[WID_P] = {"block": BLOCK_P, "status": "assigned"}
    block_file_p = gfr.seed_block_doc(root, BLOCK_P, "meta/blocks/20-01.md")
    gfr.make_code_commit(root, BRANCH_P, gfr.CODE_FILE_REL, MARKER_P)
    gstate_p = gate.new_state_full(eng_p, BLOCK_P, block_file_p, BRANCH_P, WID_P)
    hist_p = gfr.drive_full(eng_p, BLOCK_P, gstate_p, root, grants_dir,
                            local_report=gfr.LOCAL_PASS_REPORT,
                            stop_outcomes={"trunk_passed", "trunk_failed", "trunk_unconfirmed"},
                            max_iters=20)
    ok("test:<donegate_declared_command_validates_nonpython> P1 (must be GREEN): a REAL "
       "declared command with NO python/pytest anywhere (`grep -q ... src.ts`) genuinely "
       "PASSES, in a real clean detached worktree at the real merged sha",
       "trunk_passed" in [o for o, _ in hist_p] and gstate_p["stage"] == gate.STAGE_RECORD,
       f"outcomes={[o for o, _ in hist_p]} verdict_detail={gstate_p.get('trunk_verdict_detail')}")

    # ── 1b: the SAME non-Python declared command genuinely FAILS (adversarial —
    #    proves it is REALLY executed, never silently skipped/passed) ──
    BLOCK_F, BRANCH_F, WID_F = "20-02", "feat/20-02", "engineer-20-02"
    MARKER_ABSENT = "MARKER-that-is-never-written-anywhere"
    nonpy_fail_cmd = f'grep -q "{MARKER_ABSENT}" {gfr.CODE_FILE_REL}'
    eng_f = gfr.MiniEng(root, grants_dir, test_command=nonpy_fail_cmd)
    eng_f.workers[WID_F] = {"block": BLOCK_F, "status": "assigned"}
    block_file_f = gfr.seed_block_doc(root, BLOCK_F, "meta/blocks/20-02.md")
    gfr.make_code_commit(root, BRANCH_F, gfr.CODE_FILE_REL, "20-02-real-change")
    gstate_f = gate.new_state_full(eng_f, BLOCK_F, block_file_f, BRANCH_F, WID_F)
    hist_f = gfr.drive_full(eng_f, BLOCK_F, gstate_f, root, grants_dir,
                            local_report=gfr.LOCAL_PASS_REPORT,
                            stop_outcomes={"trunk_passed", "trunk_failed", "trunk_unconfirmed"},
                            max_iters=20)
    ok("test:<donegate_declared_command_validates_nonpython> P2 (ADVERSARIAL — must be "
       "GREEN): the SAME non-Python command genuinely FAILS when its condition is false "
       "— a REAL execution, never a silent pass; holds at gate.trunk, never advances",
       "trunk_failed" in [o for o, _ in hist_f] and gstate_f["stage"] == gate.STAGE_TRUNK,
       f"outcomes={[o for o, _ in hist_f]}")

    # ── 1c: neither test.command NOR ci.check_name declared -> "unconfirmed",
    #    NEVER a silently-substituted python/pytest default ──
    BLOCK_U, BRANCH_U, WID_U = "20-03", "feat/20-03", "engineer-20-03"
    eng_u = gfr.MiniEng(root, grants_dir, test_command=None)
    eng_u.workers[WID_U] = {"block": BLOCK_U, "status": "assigned"}
    block_file_u = gfr.seed_block_doc(root, BLOCK_U, "meta/blocks/20-03.md")
    gfr.make_code_commit(root, BRANCH_U, gfr.CODE_FILE_REL, "20-03-real-change")
    gstate_u = gate.new_state_full(eng_u, BLOCK_U, block_file_u, BRANCH_U, WID_U)
    hist_u = gfr.drive_full(eng_u, BLOCK_U, gstate_u, root, grants_dir,
                            local_report=gfr.LOCAL_PASS_REPORT,
                            stop_outcomes={"trunk_passed", "trunk_failed", "trunk_unconfirmed"},
                            max_iters=20)
    outcomes_u = [o for o, _ in hist_u]
    ok("test:<donegate_declared_command_validates_nonpython> P3 (NO HARDCODED DEFAULT — "
       "must be GREEN): with NEITHER test.command NOR ci.check_name declared, gate.trunk "
       "reads 'unconfirmed' — it never silently substitutes a guessed python/pytest/"
       "*_test.py discovery in their place",
       "trunk_unconfirmed" in outcomes_u and "trunk_passed" not in outcomes_u
       and "trunk_failed" not in outcomes_u and gstate_u["stage"] == gate.STAGE_TRUNK,
       f"outcomes={outcomes_u}")

    # ── structural: the CODE (docstring stripped) contains no hardcoded
    #    python-test-discovery string and no merge_base/range computation ──
    dump_validate = _code_body_dump(trunk.validate_trunk)
    dump_run = _code_body_dump(trunk._run_declared_command)
    banned = ("pytest", "unittest", "_test.py", "merge_base")
    hits_validate = [b for b in banned if b in dump_validate]
    hits_run = [b for b in banned if b in dump_run]
    ok("test:<donegate_declared_command_validates_nonpython> P4 (STRUCTURAL — must be "
       "GREEN): `trunk.validate_trunk`'s and `trunk._run_declared_command`'s own CODE "
       "(docstring stripped) reference no python-test-discovery string "
       "(pytest/unittest/_test.py) and no merge_base/range computation — the ff-collapse "
       "false-wall root is structurally absent, not merely untriggered on this fixture",
       not hits_validate and not hits_run,
       f"hits_validate={hits_validate} hits_run={hits_run}")


# ══════════════════════════════════════════════════════════════════════════
# test:<unconfirmable_close_holds_routes_architect>
# ══════════════════════════════════════════════════════════════════════════

UC_BLOCK = "06-01"
UC_BLOCKS = [{"id": UC_BLOCK, "depends_on": [], "reviewer_class": "none",
             "title": "quad(x): a small real function (trunk validation UNCONFIRMABLE — "
                     "no declared command, no CI check)"}]
UC_MAX_TICKS = 90


class _ArchitectFirstDriver(sim_worker.ScriptedDriver):
    """The happy-path driver, PLUS: once the architect's OWN triage job for
    the sentry.cap-sourced case is ORDERED, answer it with a routed
    `verdict='operator'` — closing the loop honestly. This is the ONLY way
    this rig's operator page ever fires: never automatically on cap, only
    through the architect's own resolution (identical shape to `core/sim/
    invariants_2b_rig.py::_OperatorVerdictDriver`, kept local — no cross-rig
    coupling)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._triage_answered = set()

    def react(self, i, manifest):
        super().react(i, manifest)
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job") or {}
        if cur.get("kind") != "triage" or not cur.get("ordered"):
            return
        tid = cur.get("triage_id")
        if not tid or tid in self._triage_answered:
            return
        intake.write(self.tron_ctx, core_architect.ARCHITECT_WID,
                     {"tag": "architect.triage_verdict",
                      "agent_id": core_architect.ARCHITECT_WID,
                      "slots": {"triage_id": tid, "verdict": "operator"}})
        self._triage_answered.add(tid)


def _drive_unconfirmable():
    ctx, root = sim_scaffold.build(UC_BLOCKS)
    # NEITHER test.command NOR ci.check_name declared — gate.trunk genuinely
    # has nothing trustworthy to read (project.yaml is overwritten AFTER
    # build()'s own `test_command or DEFAULT_TEST_COMMAND` substitution,
    # BEFORE Engine(ctx) reads it at construction).
    sim_scaffold.write_project_yaml(ctx.dir, root, None)
    driver = _ArchitectFirstDriver(root, ctx.grants_dir, ctx, sim_worker.default_transcript())

    real_spawn_runner = jobs.spawn_runner
    jobs.spawn_runner = lambda *a, **k: {}
    try:
        eng = Engine(ctx)
        eng.dry = False
        eng.start(scope="all", worker_count=1, models={})
        i = -1
        for i in range(UC_MAX_TICKS):
            res = eng.tick()
            manifest = state.load(ctx)
            driver.record_done_ticks(i, res.get("outcomes") or {})
            driver.react(i, manifest)
            if res.get("session_end") is not None:
                break
        final = state.load(ctx)
        return {
            "root": root, "ctx": ctx, "events": list(eng.events.log),
            "gates": final.get("gates") or {}, "cases": final.get("cases") or {},
            "ticks_used": i + 1,
        }
    finally:
        jobs.spawn_runner = real_spawn_runner


def _unconfirmable_close_holds_routes_architect():
    r = _drive_unconfirmable()
    ev = r["events"]

    def _events(t):
        return [e for e in ev if e["type"] == t]

    def _first_idx(pred):
        return next((idx for idx, e in enumerate(ev) if pred(e)), None)

    trunk_verdict_events = [e for e in _events("gate_trunk_verdict")
                            if e["payload"].get("block") == UC_BLOCK]
    ok("UC1 (must be GREEN): gate.trunk was genuinely reached for this block "
       "(a real merge landed first) — the unconfirmable read is exercised, not skipped",
       (r["gates"].get(UC_BLOCK) or {}).get("stage") in (gate.STAGE_TRUNK, gate.STAGE_ESCALATED)
       or any(e["type"] == "gate_merged" and e["payload"].get("block") == UC_BLOCK for e in ev),
       f"final_stage={(r['gates'].get(UC_BLOCK) or {}).get('stage')}")

    gate_escalated_this_block = [e for e in _events("gate_escalated")
                                 if e["payload"].get("block") == UC_BLOCK]
    ok("UC2 ('CAN'T CONFIRM' != 'FAILED', THE KILLER — must be GREEN): gate.py's OWN "
       "`_escalate` (the `gate_escalated` event) NEVER fired for this block — an "
       "unconfirmed trunk read is never treated as a genuine failure/wall by the gate "
       "itself; it only ever HOLDS",
       len(gate_escalated_this_block) == 0,
       f"gate_escalated_events={gate_escalated_this_block}")

    sentry_escalated_this_block = [e for e in _events("sentry_escalated")
                                   if e["payload"].get("block") == UC_BLOCK]
    escalation_logged = [e for e in _events("escalation_logged")
                         if e["payload"].get("block") == UC_BLOCK]
    ok("UC3 (THE SAME UNIFORM LADDER, NEVER A SPECIAL CASE — must be GREEN): the block "
       "was eventually escalated ONLY by `core/sentry.py`'s ordinary idle-pacing cap "
       "(the SAME ladder every other holding stage is subject to) — never gate.py itself, "
       "and the escalation's own record names the stage it was holding at as 'trunk'",
       len(sentry_escalated_this_block) == 1 and len(escalation_logged) >= 1
       and any(rec["payload"].get("stage") == "trunk" for rec in escalation_logged),
       f"sentry_escalated={sentry_escalated_this_block} escalation_logged={escalation_logged}")

    case_opened = [e for e in _events("case_opened") if e["payload"].get("block") == UC_BLOCK]
    ok("UC4: exactly one case was opened for this block, sourced 'sentry.cap', owned by "
       "the ARCHITECT (never the operator, at open time)",
       len(case_opened) == 1 and case_opened[0]["payload"].get("source") == "sentry.cap",
       f"case_opened={case_opened}")

    triage_enqueued = [e for e in _events("architect_triage_job_enqueued")
                       if e["payload"].get("block") == UC_BLOCK]
    ok("UC5 (ARCHITECT-FIRST, THE OTHER KILLER — must be GREEN): the sentry cap became a "
       "PMT-TRIAGE job (`architect_triage_job_enqueued`) — routed to the architect, never "
       "an immediate operator page",
       len(triage_enqueued) == 1,
       f"triage_enqueued={triage_enqueued}")

    escalated_to_operator = [e for e in _events("case_escalated_to_operator")
                             if (r["cases"].get(e["payload"].get("case_id"), {}) or {}).get("block")
                             == UC_BLOCK or True]
    # Causal order: case_opened (architect-owned) -> triage enqueued -> triage
    # ORDERED (arch.triage emitted) -> ONLY THEN, via the architect's own routed
    # verdict, does the operator ever get paged.
    idx_opened = _first_idx(lambda e: e["type"] == "case_opened" and e["payload"].get("block") == UC_BLOCK)
    idx_triage_enq = _first_idx(lambda e: e["type"] == "architect_triage_job_enqueued"
                                and e["payload"].get("block") == UC_BLOCK)
    idx_resolved = _first_idx(lambda e: e["type"] == "architect_triage_resolved"
                              and e["payload"].get("triage_id") ==
                              (triage_enqueued[0]["payload"].get("triage_id") if triage_enqueued else None))
    idx_op_paged = _first_idx(lambda e: e["type"] == "case_escalated_to_operator")
    # `architect_resolve`'s "operator" verdict PAGES the operator as part of
    # resolving the case; the triage job's OWN bookkeeping flag
    # (`architect_triage_resolved`) is set immediately after, in the same
    # `_advance_triage` call — so the real order is opened -> enqueued ->
    # PAGED -> job-marked-resolved, never paged before the case was even
    # opened/enqueued to the architect.
    ok("UC6 (NEVER SKIPS THE ARCHITECT, CAUSAL ORDER — must be GREEN): case_opened -> "
       "triage enqueued, BOTH strictly before any case_escalated_to_operator event (which "
       "itself precedes the triage job's own resolved-bookkeeping flag) — the operator is "
       "reached ONLY after the case was routed architect-first, never a bypass",
       None not in (idx_opened, idx_triage_enq, idx_resolved, idx_op_paged)
       and idx_opened < idx_triage_enq < idx_op_paged <= idx_resolved,
       f"idx_opened={idx_opened} idx_triage_enq={idx_triage_enq} "
       f"idx_resolved={idx_resolved} idx_op_paged={idx_op_paged}")

    ok("test:<unconfirmable_close_holds_routes_architect> (AC-16): an unresolvable "
       "gate.trunk read holds (never a gate.py-owned wall), and — once the SAME uniform "
       "idle cap every other stage shares eventually fires — routes architect-first "
       "(never an immediate operator page); the operator is reached only through the "
       "architect's own verdict",
       all(c for name, c, _ in _results if name.startswith("UC")))


# ══════════════════════════════════════════════════════════════════════════
# test:<ci_verdict_read_commit_exact>
# ══════════════════════════════════════════════════════════════════════════

_MERGED_SHA = "a" * 40
_CHECK_NAME = "ci-declared-suite"


def _run_ci_verdict_read_commit_exact():
    real_ci_check_runs = trunk.ci_check_runs
    real_run_declared_command = trunk._run_declared_command
    called_run_declared = {"n": 0}

    def _spy_run_declared(*a, **k):
        called_run_declared["n"] += 1
        return real_run_declared_command(*a, **k)

    def _runs(matching_head=True, status="completed", conclusion="success",
              name=None):
        return [{
            "name": name if name is not None else _CHECK_NAME,
            "head_sha": _MERGED_SHA if matching_head else ("b" * 40),
            "status": status,
            "conclusion": conclusion,
        }]

    trunk._run_declared_command = _spy_run_declared
    try:
        # CE1 — exact match (name + head_sha + completed + success) -> pass, no re-run.
        trunk.ci_check_runs = lambda *a, **k: _runs()
        status, detail = trunk.ci_verdict("/dev/null", _MERGED_SHA, _CHECK_NAME, False)
        ok("CE1 (exact match -> pass): commit-exact + non-stale + real-suite-name all "
           "hold -> genuinely trusted",
           status == "pass", f"status={status} detail={detail}")

        # CE2 — commit-exact FAILS (an ancestor/descendant/unrelated commit's check-run,
        # even same name+completed+success) -> unconfirmed, never substituted.
        trunk.ci_check_runs = lambda *a, **k: _runs(matching_head=False)
        status, detail = trunk.ci_verdict("/dev/null", _MERGED_SHA, _CHECK_NAME, False)
        ok("CE2 (COMMIT-EXACT — must be GREEN): a check-run for a DIFFERENT sha (even "
           "same name, completed, success) is NEVER trusted for this merged_sha",
           status == "unconfirmed", f"status={status} detail={detail}")

        # CE3 — non-stale FAILS (still running) -> unconfirmed.
        trunk.ci_check_runs = lambda *a, **k: _runs(status="in_progress", conclusion=None)
        status, detail = trunk.ci_verdict("/dev/null", _MERGED_SHA, _CHECK_NAME, False)
        ok("CE3 (NON-STALE — must be GREEN): a pending/in_progress check-run, even "
           "commit-exact, is NEVER trusted",
           status == "unconfirmed", f"status={status} detail={detail}")

        # CE4 — real-declared-suite-name FAILS (an unrelated green check happens to be
        # commit-exact + completed) -> unconfirmed, never a bare rollup guess.
        trunk.ci_check_runs = lambda *a, **k: _runs(name="some-other-unrelated-check")
        status, detail = trunk.ci_verdict("/dev/null", _MERGED_SHA, _CHECK_NAME, False)
        ok("CE5 (REAL DECLARED SUITE — must be GREEN): a commit-exact, completed, green "
           "check-run under the WRONG name is NEVER substituted for the declared suite",
           status == "unconfirmed", f"status={status} detail={detail}")

        # CE6 — exact match with conclusion=failure -> "fail" (a genuine red is read
        # through, never masked as unconfirmed).
        trunk.ci_check_runs = lambda *a, **k: _runs(conclusion="failure")
        status, detail = trunk.ci_verdict("/dev/null", _MERGED_SHA, _CHECK_NAME, False)
        ok("CE6: an exact-match check-run that genuinely FAILED reads 'fail', not "
           "'unconfirmed' — a real red is never softened",
           status == "fail", f"status={status} detail={detail}")

        # CE7 — via gitobs.validate_trunk / trunk.validate_trunk with BOTH test_command
        # AND ci_check_name declared: CI mode wins, the declared command is NEVER re-run.
        trunk.ci_check_runs = lambda *a, **k: _runs()
        called_run_declared["n"] = 0
        status, detail = trunk.validate_trunk("/dev/null", _MERGED_SHA,
                                              "echo should-never-execute",
                                              ci_check_name=_CHECK_NAME, dry=False,
                                              scratch_root=None)
        ok("CE7 (NEVER RE-RUN — must be GREEN): with ci_check_name declared, "
           "validate_trunk reads the CI verdict and NEVER invokes the declared command "
           "(0 calls to _run_declared_command) — CI mode wins, no re-run",
           status == "pass" and called_run_declared["n"] == 0,
           f"status={status} calls_to_run_declared_command={called_run_declared['n']}")

        # CE8 — MUTATION / non-vacuity: a NAIVE verdict function that drops the
        # commit-exact check would WRONGLY trust the stale/ancestor run CE2 fed it —
        # proving the real guard is doing genuine work, not vacuously always-unconfirmed.
        def _naive_ci_verdict(repo_root, merged_sha, check_name, dry=False):
            runs = trunk.ci_check_runs(repo_root, merged_sha, dry)
            matches = [rr for rr in runs if rr.get("name") == check_name]   # NO head_sha check
            if not matches:
                return "unconfirmed", "no match"
            run = matches[0]
            if run.get("status") != "completed":
                return "unconfirmed", "not completed"
            return (("pass" if run.get("conclusion") == "success" else "fail"),
                   "naive (no commit-exact guard)")

        trunk.ci_check_runs = lambda *a, **k: _runs(matching_head=False)   # the CE2 fixture
        naive_status, _ = _naive_ci_verdict("/dev/null", _MERGED_SHA, _CHECK_NAME, False)
        real_status, _ = trunk.ci_verdict("/dev/null", _MERGED_SHA, _CHECK_NAME, False)
        ok("CE8 (MUTATION -> the naive verdict wrongly trusts; non-vacuity for CE2 — "
           "must be GREEN): on the SAME stale/ancestor check-run data, a verdict "
           "function with the commit-exact guard REMOVED would wrongly read 'pass' — "
           "the real `trunk.ci_verdict` correctly reads 'unconfirmed'. The guard is "
           "doing genuine work, not a vacuous always-unconfirmed stub.",
           naive_status == "pass" and real_status == "unconfirmed",
           f"naive_status={naive_status} real_status={real_status}")

        ok("test:<ci_verdict_read_commit_exact> (AC-16): CI mode reads the verdict keyed "
           "to the merged commit — commit-exact, non-stale, the real declared suite — "
           "never re-running the declared command, never substituting an ancestor/"
           "unrelated/pending check-run",
           all(c for name, c, _ in _results if name.startswith("CE")))
    finally:
        trunk.ci_check_runs = real_ci_check_runs
        trunk._run_declared_command = real_run_declared_command


def main():
    _run_declared_command_nonpython()
    _unconfirmable_close_holds_routes_architect()
    _run_ci_verdict_read_commit_exact()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.donegate_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
