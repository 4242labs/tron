"""block_01_34_test — landing-primitive consolidation, observable-keyed gates
(block 01-34, ADR-0003 D-A/D-B/D-C, AC-1...AC-6). AC-7 is operator-run — not here.

SIM tron-40 failed a METHOD, not a shortage of fixes: past cycles hand-rolled a NEW
copy of the landing orchestration per call site (seven `mint->order->observe` copies),
verified only on replays that can't see the live flows, and walled a merely-slow
pre-carve worker on a bare tick count. This block:

  T1  collapses the seven copies into ONE primitive, `Engine._land_via_grant`
      (fsm.py) -> `land.land_via_grant` (land.py) — the four sub-primitives
      (`_mint_or_reuse_grant`/`_order_land`/`_observe_landed`/
      `_consume_grant_administratively`) are now PRIVATE to land.py, unreachable
      except through it (AC-1). Every former call site (merge-gate, record-redrive,
      record-paperwork, drain-landings, close-confirm, violation-repair) is a thin
      scope-supplying shim now. The record-stage paperwork arm (which had NO grant
      path at all before 01-32/33's emergency patch) lands through the exact same
      sequence (AC-2).
  T2  the test-stage (trunk) gate re-derives its OWN observable EVERY evaluation —
      never gated on a worker report — keyed on the branch-tip sha
      (`_test_stage_verdict`, fsm.py): re-run on a sha change, reuse the cached
      verdict for the same sha. Three-way: true -> advance, idempotent, never bumps
      `stall_attempts`; false -> the ordinary attempt path, `gate_step_cap` may
      fire; unavailable (cannot execute) -> hold, never caps (P6) (AC-3).
  T3  `carve_observe_ticks` (a bespoke operator wall on a tick-count deadline) is
      RETIRED — carve is a worker ritual, observed with no deadline; a genuinely
      stuck pre-carve worker trips the SAME ordinary worker-liveness path every
      other stall uses, on its own wall-clock dial (`carve_liveness_timeout`) (AC-5).
  T4  dead code + the carve deadline plumbing are deleted; `carve_observe_ticks` is
      retired, `carve_liveness_timeout` declared with a default.

Real throwaway git repos + real `land.sh` subprocess runs for the landing-primitive
cases (same convention as block_01_32_test.py/record_landing_test.py); dry FSM
fixtures (sentry_test's builders) elsewhere. AC-4 (non-ff -> worker rebase, never an
operator park) and AC-6 (write-boundary allowlist unchanged) are REGRESSION guards —
neither mechanism moved in this block, but both are load-bearing on the SAME
consolidated primitive and must survive it untouched.

Run: python3 engine/block_01_34_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import grants                                             # noqa: E402
import trunk                                               # noqa: E402
import land                                                 # noqa: E402
from fsm import Engine                                     # noqa: E402
from sentry_test import build, started                     # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── real-git fixture (block_01_32_test.py/tron13_test.py convention) ──
def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _mkrepo(prefix="tron-0134-"):
    d = tempfile.mkdtemp(prefix=prefix)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    os.makedirs(os.path.join(d, "meta"))
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | to-do |\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


def _eng(d, block="A-01", with_architect=False):
    """A started engine over the REAL repo `d`, local mode, non-dry."""
    ctx, _ = build(blocks=[(block, "🔄", "none")])
    eng = Engine(ctx)
    started(eng)
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["main_branch"] = "main"
    eng.paths["remote"] = None
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    if with_architect:
        eng.st.workers.append({"id": "ARCH-PERSIST", "role": "architect", "session_id": "",
                               "shortid": "", "status": "idle", "current_job": None,
                               "block": None, "mbox_seq": 0})
    eng.st.branches[block] = f"feat/{block.lower()}"
    return eng


LAND_SH = os.path.join(os.path.dirname(HERE), "templates", "project-scaffold",
                       "templates", "meta", "scripts", "land.sh")


def _run_land(repo, case_id, grants_dir, main="main"):
    return subprocess.run(["bash", LAND_SH, case_id, "--main", main],
                          cwd=repo, capture_output=True, text=True,
                          env={**os.environ, "LAND_GRANTS_DIR": grants_dir})


# ══════════════════════════════════════════════════════════════════════════
# AC-1 test:<single_land_primitive_structural>
# ══════════════════════════════════════════════════════════════════════════
def t_ac1_land_primitive_structural():
    sub_primitives = ("_mint_or_reuse_grant", "_order_land", "_observe_landed",
                      "_consume_grant_administratively")
    for name in sub_primitives:
        ok(f"AC-1: land.{name} exists as a module-private sub-primitive",
           hasattr(land, name) and callable(getattr(land, name)))
    for name in sub_primitives:
        ok(f"AC-1: Engine carries NO '{name}' method any more (moved off the class "
           f"entirely, not merely renamed)", not hasattr(Engine, name))
    ok("AC-1: Engine._land_via_grant is the ONE seam", hasattr(Engine, "_land_via_grant"))
    ok("AC-1: land.land_via_grant is the orchestration this seam delegates to",
       hasattr(land, "land_via_grant") and callable(land.land_via_grant))

    engine_dir = os.path.dirname(os.path.abspath(land.__file__))
    call_markers = tuple(n + "(" for n in sub_primitives)
    offenders = []
    for fn in sorted(os.listdir(engine_dir)):
        if not fn.endswith(".py") or fn == "land.py":
            continue
        with open(os.path.join(engine_dir, fn)) as fh:
            text = fh.read()
        for marker in call_markers:
            if marker in text:
                offenders.append((fn, marker.rstrip("(")))
    ok("AC-1 backstop: no module OTHER than land.py names any of the four "
       "sub-primitives at all — structurally unreachable except through "
       "_land_via_grant, not merely a 'no second caller' convention",
       not offenders, f"offenders={offenders}")

    with open(os.path.join(engine_dir, "fsm.py")) as fh:
        fsm_src = fh.read()
    n_calls = fsm_src.count("self._land_via_grant(")
    ok("AC-1: every former call-site (merge, record-redrive, record-paperwork, "
       "drain-landings, close-confirm x2, violation-repair x2) routes through the "
       "ONE seam (>= 6 call sites)", n_calls >= 6, f"n_calls={n_calls}")


# ══════════════════════════════════════════════════════════════════════════
# AC-2 test:<land_primitive_correct_record_arm_survives>
# ══════════════════════════════════════════════════════════════════════════
def t_ac2_land_via_grant_correct_sequence():
    # fail-closed: a branch with NO content diff at all (an empty commit — not yet
    # merged, so observation-first doesn't short-circuit it as already-landed, but
    # nothing for `git patch-id` to hash either) resolves an unresolvable ("")
    # patch-id — never mints, never orders.
    d0 = _mkrepo("tron-0134-ac2fc-")
    _git(d0, "checkout", "-qb", "feat/empty")
    _git(d0, "commit", "--allow-empty", "-qm", "nothing")
    _git(d0, "checkout", "-q", "main")
    eng0 = _eng(d0)
    outcome0 = eng0._land_via_grant("case-fc", "A-01", "feat/empty", "ENG-A-01",
                                    "gate.land", "test")
    ok("AC-2 fail-closed: an unresolvable patch-id never mints a grant",
       outcome0 == "fail-closed", f"outcome={outcome0}")
    ok("AC-2 fail-closed: nothing was written under the grants dir",
       not os.path.isdir(eng0.ctx.grants_dir) or not os.listdir(eng0.ctx.grants_dir))
    shutil.rmtree(d0, ignore_errors=True)

    d = _mkrepo("tron-0134-ac2-")
    _git(d, "checkout", "-qb", "feat/a-01")
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | done |\n")
    _git(d, "commit", "-aqm", "A-01 done")
    _git(d, "checkout", "-q", "main")
    _git(d, "checkout", "-q", "--detach", "HEAD")
    eng = _eng(d)
    branch = "feat/a-01"

    # observation-first -> mint -> order -> "pending" (not yet observed).
    outcome1 = eng._land_via_grant("CASE-1", "A-01", branch, "ENG-A-01",
                                   "gate.land", "test")
    ok("AC-2: a fresh, landable branch mints+orders and returns 'pending'",
       outcome1 == "pending", f"outcome={outcome1}")
    live = grants.read_live(eng.ctx.grants_dir, "CASE-1")
    ok("AC-2: a patch-id-bound grant is now LIVE",
       bool(live) and bool(live.get("patch_id")), f"live={live}")

    # a second call over UNCHANGED content reuses the SAME grant — never re-mints,
    # never re-orders (AC-5 of 01-32, preserved by the consolidation).
    minted_at = live.get("minted_at")
    outcome1b = eng._land_via_grant("CASE-1", "A-01", branch, "ENG-A-01",
                                    "gate.land", "test")
    live2 = grants.read_live(eng.ctx.grants_dir, "CASE-1")
    ok("AC-2: re-evaluating unchanged content reuses the SAME grant (never re-mints)",
       outcome1b == "pending" and live2.get("minted_at") == minted_at,
       f"live={live} live2={live2}")

    # the worker (never the engine) runs land.sh.
    r = _run_land(d, "CASE-1", eng.ctx.grants_dir)
    ok("AC-2: land.sh (the worker's hands) lands it", r.returncode == 0,
       f"out={r.stdout} err={r.stderr}")

    # observation-first: the NEXT call observes the landed tip and consumes.
    outcome2 = eng._land_via_grant("CASE-1", "A-01", branch, "ENG-A-01",
                                   "gate.land", "test")
    ok("AC-2: the primitive OBSERVES the land and returns 'landed'", outcome2 == "landed",
       f"outcome={outcome2}")
    ok("AC-2: the grant is now consumed (receipt on file)",
       grants.read_consumed(eng.ctx.grants_dir, "CASE-1") is not None)

    # already-landed short-circuit (AC-2's "incl. consumed-grant+receipt"): even
    # once the branch is DELETED (post-close cleanup — a live ancestry read can no
    # longer resolve a tip at all), the consumed receipt alone still proves it.
    _git(d, "branch", "-D", branch)
    outcome3 = eng._land_via_grant("CASE-1", "A-01", branch, "ENG-A-01",
                                   "gate.land", "test")
    ok("AC-2: the already-landed short-circuit survives branch deletion (the "
       "consumed receipt, never a live git read, is authoritative)",
       outcome3 == "landed", f"outcome={outcome3}")
    shutil.rmtree(d, ignore_errors=True)


def t_ac2_administrative_consume_survives_crash_window():
    """AC-2: the ADR-0002 D2 crash-after-advance administrative consume (N3) — trunk
    already moved (as if land.sh crashed after its own ref-advance but before its
    own consume) while a grant is still LIVE. `_land_via_grant`'s observation-first
    arm must catch and consume it administratively — proving the ONE primitive
    reproduces this shape too, not only the separate `_sweep_grant_consume`."""
    d = _mkrepo("tron-0134-ac2n3-")
    _git(d, "checkout", "-qb", "feat/a-01")
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | done |\n")
    _git(d, "commit", "-aqm", "A-01 done")
    _git(d, "checkout", "-q", "main")
    eng = _eng(d)
    pid = trunk.patch_id(d, "feat/a-01", "main")
    grants.mint(eng.ctx.grants_dir, "CASE-N3", "A-01", "feat/a-01", pid)
    _git(d, "merge", "-q", "--ff-only", "feat/a-01")   # the "crashed land.sh"'s own CAS, simulated raw
    outcome = eng._land_via_grant("CASE-N3", "A-01", "feat/a-01", "ENG-A-01",
                                  "gate.land", "test")
    ok("AC-2 N3: the primitive's observation-first arm catches the crash-window "
       "advance and consumes administratively", outcome == "landed", f"outcome={outcome}")
    ok("AC-2 N3: the grant is consumed, engine-observed",
       (grants.read_consumed(eng.ctx.grants_dir, "CASE-N3") or {}).get("result")
       == "engine-observed", f"receipt={grants.read_consumed(eng.ctx.grants_dir, 'CASE-N3')}")
    shutil.rmtree(d, ignore_errors=True)


def t_ac2_record_stage_arm_survives_via_primitive():
    """AC-2: the record-stage paperwork landing (previously had NO grant path at
    all, SIM-WAVE-HARD-FAIL) lands through the SAME `_land_via_grant` sequence as
    every other site — provably survives consolidation."""
    d = _mkrepo("tron-0134-ac2rec-")
    _, merged_sha, _ = _git(d, "rev-parse", "HEAD")
    branch = "feat/a-01"
    _git(d, "checkout", "-qb", branch)
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | done |\n")
    _git(d, "commit", "-aqm", "record: A-01 status -> done")
    _, cur_tip, _ = _git(d, "rev-parse", branch)
    _git(d, "checkout", "-q", "main")
    _git(d, "checkout", "-q", "--detach", "HEAD")
    eng = _eng(d)
    g = eng.st.gate.setdefault("A-01", {"stage": "record", "pr": None,
                                        "merged_sha": merged_sha})
    eng._drive_record_paperwork_landing("A-01", g, "ENG-A-01", branch, cur_tip)
    case_id = g.get("record_landing_case")
    ok("AC-2 record-arm: the (previously grant-path-less) record-stage paperwork "
       "landing mints+orders through the ONE primitive", bool(case_id), f"g={g}")
    live = grants.read_live(eng.ctx.grants_dir, case_id) if case_id else None
    ok("AC-2 record-arm: a patch-id-bound grant is live", bool(live), f"live={live}")

    r = _run_land(d, case_id, eng.ctx.grants_dir)
    ok("AC-2 record-arm: land.sh lands the record flip", r.returncode == 0,
       f"out={r.stdout} err={r.stderr}")

    eng._drive_record_paperwork_landing("A-01", g, "ENG-A-01", branch, cur_tip)
    ok("AC-2 record-arm: observed landed -> the case clears (the ✅ advances on "
       "refresh, never a stage write here)", g.get("record_landing_case") is None,
       f"g={g}")
    ok("AC-2 record-arm: the grant is consumed",
       grants.read_consumed(eng.ctx.grants_dir, case_id) is not None)
    shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════
# AC-3 test:<gate_observable_sha_keyed_three_way>
# ══════════════════════════════════════════════════════════════════════════
def t_ac3_gate_observable_sha_keyed_three_way():
    d = _mkrepo("tron-0134-ac3-")
    ctr_dir = tempfile.mkdtemp(prefix="tron-0134-ac3-ctr-")
    counter = os.path.join(ctr_dir, "count.txt")

    def _count():
        return sum(1 for _ in open(counter)) if os.path.exists(counter) else 0

    eng = _eng(d, with_architect=True)
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})

    # true -> advance, idempotent, never bumps stall_attempts, runs the suite once
    # per sha (never re-run for the same sha on a re-report).
    eng.paths["test_command"] = f'echo x >> "{counter}" && exit 0'
    _, m1, _ = _git(d, "rev-parse", "HEAD")
    g["merged_sha"] = m1
    eng._h_worker_done({"block": "A-01"})
    ok("AC-3: a genuinely observed pass advances trunk -> record",
       g.get("stage") == "record", f"g={g}")
    ok("AC-3: the declared suite ran exactly once for this sha", _count() == 1,
       f"count={_count()}")
    ok("AC-3: a true observable advance never bumps stall_attempts",
       g.get("stall_attempts", 0) == 0, f"g={g}")

    eng._h_worker_done({"block": "A-01"})   # a stale/duplicate re-report
    ok("AC-3: re-reporting an already-true stage advances idempotently and never "
       "increments stall_attempts", g.get("stall_attempts", 0) == 0, f"g={g}")
    ok("AC-3: the suite did NOT re-run for the unchanged sha (cached verdict, "
       "reused, never a worker-reported pass)", _count() == 1, f"count={_count()}")

    # false (genuinely absent) -> the ordinary attempt path; gate_step_cap fires
    # after repeated attempts; the suite re-runs on the SHA change, then caches.
    g["stage"] = "trunk"
    g.pop("stall_attempts", None)
    eng.paths["test_command"] = f'echo x >> "{counter}" && exit 1'
    _git(d, "commit", "--allow-empty", "-qm", "second commit")
    _, m2, _ = _git(d, "rev-parse", "HEAD")
    g["merged_sha"] = m2
    eng._h_worker_done({"block": "A-01"})
    ok("AC-3: a genuinely failing (absent) observable holds at trunk — never a "
       "false pass", g.get("stage") == "trunk", f"g={g}")
    ok("AC-3: the suite RE-RAN for the changed sha (CASE-008: the tip moved -> "
       "never a stale cached verdict)", _count() == 2, f"count={_count()}")
    ok("AC-3: a genuinely-absent observable takes the ordinary attempt path "
       "(stall_attempts accrues)", g.get("stall_attempts", 0) == 1, f"g={g}")

    eng._h_worker_done({"block": "A-01"})   # same failing sha — reused, no re-run
    ok("AC-3: the suite does not re-run for the SAME still-failing sha (uncached "
       "across content only, not per-tick)", _count() == 2, f"count={_count()}")
    eng._h_worker_done({"block": "A-01"})   # third attempt at the same absent observable
    eng._drain_triggers()                    # the cap's wall:raised trigger settles here
    ok("AC-3: gate_step_cap fires only on a genuinely-absent observable, after "
       "repeated attempts (default cap 2)", "A-01" in eng.st.blocked,
       f"blocked={eng.st.blocked} g={g}")

    # unavailable (read cannot execute) -> HOLD, never fails, never caps, no matter
    # how many times it's re-evaluated (P6: unavailable != failed).
    d2 = _mkrepo("tron-0134-ac3b-")
    eng2 = _eng(d2, with_architect=True)
    g2 = eng2.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})
    eng2.paths["test_command"] = None   # nothing declared to validate against
    _, m3, _ = _git(d2, "rev-parse", "HEAD")
    g2["merged_sha"] = m3
    for _ in range(5):
        eng2._h_worker_done({"block": "A-01"})
    ok("AC-3: an unavailable (cannot-confirm) read HOLDS — never fails, never caps, "
       "however many times it is re-evaluated",
       g2.get("stage") == "trunk" and "A-01" not in eng2.st.blocked
       and g2.get("stall_attempts", 0) == 0,
       f"g={g2} blocked={eng2.st.blocked}")
    ok("AC-3: unavailable routes to the architect FIRST, exactly once per episode "
       "(never re-triaged every tick)",
       (eng2._architect() or {}).get("current_job", {}).get("kind") == "triage",
       f"arch={eng2._architect()}")

    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(d2, ignore_errors=True)
    shutil.rmtree(ctr_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════
# AC-4 test:<nonff_worker_rebase_no_operator_wall> (regression — untouched
# mechanism, load-bearing on the consolidated primitive)
# ══════════════════════════════════════════════════════════════════════════
def t_ac4_nonff_worker_rebase_no_operator_wall():
    d = _mkrepo("tron-0134-ac4-")
    _git(d, "checkout", "-qb", "feat/a-01")
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | in-progress |\n")
    _git(d, "commit", "-aqm", "wip")
    _git(d, "checkout", "-q", "main")
    with open(os.path.join(d, "meta", "extra.md"), "w") as fh:
        fh.write("unrelated\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "unrelated trunk advance")   # trunk moves under the branch
    _git(d, "checkout", "-q", "--detach", "HEAD")
    eng = _eng(d)
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})

    eng._drive_gate("A-01", g, on_report=True)   # attempts the ff-merge -> non-ff
    ok("AC-4: a non-ff at merge orders a worker REBASE, never an operator park",
       g.get("rebase_pending") is True and g.get("stage") == "local", f"g={g}")
    ok("AC-4: the engine never rebases anything itself (no rebase state on trunk's "
       "own checkout)",
       not os.path.exists(os.path.join(d, ".git", "rebase-merge"))
       and not os.path.exists(os.path.join(d, ".git", "rebase-apply")))
    ok("AC-4: no case/wall was raised — the worker's ritual, never an operator wall",
       not eng.st.pending_cases and "A-01" not in eng.st.blocked,
       f"cases={eng.st.pending_cases} blocked={eng.st.blocked}")

    # the worker resolves it itself: rebases in its OWN worktree, re-validates,
    # reports done again — a pure rebase needs no re-review, lands under the SAME
    # standing grant via the consolidated primitive.
    _git(d, "checkout", "-q", "feat/a-01")
    rc, _, err = _git(d, "rebase", "main")
    ok("AC-4 setup: the worker's own rebase succeeds cleanly", rc == 0, f"err={err}")
    _git(d, "checkout", "-q", "--detach", "HEAD")
    eng._drive_gate("A-01", g, on_report=True)     # fresh report -> re-attempts the ff,
                                                     # this time it succeeds -> mints+orders
                                                     # under the SAME standing grant, no
                                                     # second operator ask for this content
    ok("AC-4: the fresh (rebased) report re-attempts the ff and this time mints+"
       "orders the land — never a second operator ask for the SAME content",
       g.get("stage") == "local" and bool(g.get("landing_case")), f"g={g}")
    case_id = g.get("landing_case")
    r = _run_land(d, case_id, eng.ctx.grants_dir)   # the worker's own hands
    ok("AC-4: land.sh lands the rebased branch cleanly", r.returncode == 0,
       f"out={r.stdout} err={r.stderr}")
    eng._drive_gate("A-01", g, on_report=True)   # the engine OBSERVES the land
    ok("AC-4: the standing grant's landing is observed -> the gate advances to trunk",
       g.get("stage") == "trunk", f"g={g}")
    shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════
# AC-5 test:<carve_no_wall_both_sides>
# ══════════════════════════════════════════════════════════════════════════
def t_ac5_carve_no_wall_both_sides():
    # Side A: a slow spec-reading worker (well past the RETIRED tick-count budget,
    # nowhere near the new wall-clock carve_liveness_timeout) raises NO case at all
    # and simply proceeds.
    d = _mkrepo("tron-0134-ac5a-")
    eng = _eng(d)
    w = next(x for x in eng.st.workers if x["id"] == "ENG-A-01")
    w["_carve_pending"] = True
    eng._now_s = lambda: 1_000_000.0
    eng._check_carve_bootstrap()          # starts the liveness clock (first observation)
    eng._now_s = lambda: 1_000_000.0 + 60   # far past the old 5-tick default; far under
    eng._check_carve_bootstrap()            # the new default carve_liveness_timeout (300s)
    ok("AC-5a: a merely slow pre-carve worker raises NO case at all (the retired "
       "tick-deadline wall never fires)",
       not eng.st.pending_cases and "A-01" not in eng.st.blocked,
       f"cases={eng.st.pending_cases} blocked={eng.st.blocked}")
    ok("AC-5a: it proceeds — still on the roster, still pending, no substitute carve",
       any(x["id"] == "ENG-A-01" for x in eng.st.workers) and w.get("_carve_pending") is True,
       f"workers={eng.st.workers}")
    shutil.rmtree(d, ignore_errors=True)

    # Side B: a genuinely stuck pre-carve worker trips the SAME ordinary
    # worker-liveness path every other stall uses (worker:stalled -> _h_recover),
    # never a carve-specific case kind.
    d2 = _mkrepo("tron-0134-ac5b-")
    eng2 = _eng(d2)
    w2 = next(x for x in eng2.st.workers if x["id"] == "ENG-A-01")
    w2["_carve_pending"] = True
    eng2._now_s = lambda: 2_000_000.0
    eng2._check_carve_bootstrap()
    eng2._now_s = lambda: 2_000_000.0 + 301   # past the default carve_liveness_timeout
    eng2._check_carve_bootstrap()
    eng2._drain_triggers()
    ok("AC-5b: no carve-specific case kind is ever opened",
       not any("carve" in str(c.get("kind", "")).lower()
               for c in eng2.st.pending_cases.values()),
       f"cases={eng2.st.pending_cases}")
    ok("AC-5b: the ordinary liveness path fired — one stall recorded, a FRESH "
       "worker redispatched (never a bespoke wall on the first trip)",
       eng2.st.counters.get("stalls", {}).get("A-01") == 1
       and any(x.get("block") == "A-01" for x in eng2.st.workers)
       and "A-01" not in eng2.st.blocked,
       f"counters={eng2.st.counters} workers={eng2.st.workers} blocked={eng2.st.blocked}")
    shutil.rmtree(d2, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════
# AC-6 test:<write_boundary_allowlist_unchanged>
# ══════════════════════════════════════════════════════════════════════════
def t_ac6_write_boundary_allowlist_unchanged():
    d = _mkrepo("tron-0134-ac6-")
    trunk.reset_audit()
    for sub in ("checkout", "merge", "commit", "branch", "rebase", "push", "reset"):
        try:
            trunk._run(["git", "-C", d, sub])
            ok(f"AC-6: `{sub}` still refused by the sealed wrapper allowlist", False,
               "no exception raised")
        except trunk.SealedAllowlistViolation:
            ok(f"AC-6: `{sub}` still refused by the sealed wrapper allowlist", True)
    okr, _, _ = trunk._run(["git", "-C", d, "rev-parse", "HEAD"])
    ok("AC-6: reads still pass through unchanged (rev-parse)", okr == 0)
    ok("AC-6: scratch-scoped `worktree add --detach` (validation checkouts) still "
       "passes", trunk._subcommand_allowed(
           ["git", "-C", d, "worktree", "add", "--detach", "-q", "/tmp/x", "abc"],
           scratch_root="/tmp"))

    # land.py — the ONLY new module this block adds — never itself shells out to
    # git or touches the project's version control; it only calls grants.py (its
    # own sealed folder) and trunk.py's read predicates (the SAME sealed wrapper
    # every other engine module already goes through).
    land_src = open(os.path.abspath(land.__file__)).read()
    ok("AC-6: land.py imports only grants + trunk — no subprocess/os.system of "
       "its own, no new git-write surface",
       "import subprocess" not in land_src and "os.system" not in land_src
       and "import grants" in land_src and "import trunk" in land_src)
    ok("AC-6: land.py never calls a git-WRITE verb directly (merge/rebase/"
       "checkout/push/reset/commit) — mint/order/observe/consume only, through "
       "grants.py + trunk.py's own read predicates",
       not any(f"trunk.{v}(" in land_src for v in
               ("merge", "rebase", "checkout", "push", "reset", "commit")))

    engine_dir = os.path.dirname(os.path.abspath(land.__file__))
    with open(os.path.join(engine_dir, "fsm.py")) as fh:
        fsm_src = fh.read()
    ok("AC-6: block_invariant_ok is UNTOUCHED — still exists, still the close-time "
       "invariant", hasattr(trunk, "block_invariant_ok"))
    ok("AC-6: _drive_close still calls it exactly once (unmoved by this block's "
       "landing-primitive consolidation)",
       fsm_src.count("trunk.block_invariant_ok(") == 1, f"count={fsm_src.count('trunk.block_invariant_ok(')}")

    # the operator seam never receives/constructs a git action of any kind.
    console_path = os.path.join(engine_dir, "console.py")
    with open(console_path) as fh:
        console_src = fh.read()
    ok("AC-6: the operator console never imports trunk.py or shells out itself — "
       "no git action of any kind ever reaches the operator seam",
       "import trunk" not in console_src and "subprocess" not in console_src)
    shutil.rmtree(d, ignore_errors=True)


def main():
    for fn in (t_ac1_land_primitive_structural,
              t_ac2_land_via_grant_correct_sequence,
              t_ac2_administrative_consume_survives_crash_window,
              t_ac2_record_stage_arm_survives_via_primitive,
              t_ac3_gate_observable_sha_keyed_three_way,
              t_ac4_nonff_worker_rebase_no_operator_wall,
              t_ac5_carve_no_wall_both_sides,
              t_ac6_write_boundary_allowlist_unchanged):
        fn()
    bad = [r for r in _results if not r[1]]
    for name, good, detail in _results:
        print(f"  [{'PASS' if good else 'FAIL'}] {name}" + (f" — {detail}" if detail and not good else ""))
    print(f"block_01_34_test: {'PASS' if not bad else 'FAIL'} ({len(_results)-len(bad)}/{len(_results)})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
