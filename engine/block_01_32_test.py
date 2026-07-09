"""block_01_32_test — merge inversion T1+T2+T3 (ADR-0002 D1+D2).

T1 (worker close rituals), T2 (read-path refactor), AND T3 (grants, land.sh, the
sealed wrapper allowlist, verify_docs, mutation-arm deletion) all have coverage in
this file — see the AC-1..AC-8 tests in the T3 section below (grants.py, land.sh,
the reference-transaction hook). Docs reconciliation is not code and carries no test.

  AC-2 test:clobber_dead — the wave-1b stale-branch pipeline clobber cannot land stale
       content: `trunk.merge_ff_only`'s 01-17 auto-rebase-and-retry arm is retired
       (a real-git proof: a first ff-refusal is NEVER silently rebased, conflict-free
       or not — trunk stays untouched); the FSM gate never blind-retries a held
       approval once a rebase has been ordered (only a FRESH `on_report` — the
       worker's rebase-then-re-validate ritual, reported — re-enters the merge
       attempt); a worker that genuinely cannot resolve it walls to the architect
       WITH content (not silently accepted, not corrupted, not a bare operator page).

  AC-1 (wrapper audit, T2) — the git wrapper's audit trail proves the CAS merge arm
       never checks out the root (the trunk.py:227 hazard is gone) and never issues a
       merge command — only `update-ref` CAS.

  AC-6 test:<root_reattach_detected> (T2) — both halves: `merge_ff_only`'s own
       structural refusal while the root is attached (landing holds), and the engine's
       per-tick detection (same tick, existing case machinery, self-clearing).

  AC-3/AC-4/AC-5/AC-7/AC-8 (T3) — grant lifecycle (mint/consume/expire/administrative
       consume), land.sh's own protocol (lock, CAS, already-landed arm), concurrent
       closes, verify_docs parity, and the detect-only floor.

Review round 1 (adversarial review of PR #118) fixes, each with its own dedicated
test(s), added in this pass:
  F1 — the per-block grantless-land detection now compares the grant's OWN patch-id
       against the patch-id of what actually landed (never bare live/consumed
       existence) — `t_f1_live_grant_content_match_authorizes_and_consumes` (the
       legitimate crash-window shape still authorizes) and
       `t_f1_live_grant_content_mismatch_is_violation` (an existing grant + substituted
       content landed via a raw `update-ref` is caught as a gate-bypass violation, the
       block never closes on it).
  F2 — `_auto_settle_walls_for_block`/`_on_block_done` now exempt VIOLATION_KINDS from
       auto-settle and the hold-release — `t_f2_plain_wall_autosettles_on_observed_done`
       (regression: a plain mis-tagged wall still self-heals) and
       `t_f2_violation_case_never_autosettles_hold_stays` (a gate-bypass case survives
       observed-done, the block stays held).
  F3 — `trunk._subcommand_allowed` now scopes `worktree add/remove` to the scratch
       root structurally (normalize + reject `..` traversal), not caller convention —
       `t_f3_worktree_add_remove_scoped_to_scratch_root`.
  F4 — a `SealedAllowlistViolation` raised inside a handler now escalates as its own
       distinct forensic kind + an architect-routed VIOLATION case, never the generic
       `handler-raised`/`handler-exception` bucket —
       `t_f4_sealed_allowlist_violation_escalates_distinctly`.
  F5 — `land.sh`'s already-landed arm now confirms the grant's content is actually
       present in the branch's own history before trusting bare ancestry —
       `t_f5_stale_regressed_branch_refuses_false_already_landed`.
  F6 — `land.sh` validates `CASE_ID` against a safe token pattern before any path
       interpolation — `t_f6_land_sh_rejects_unsafe_case_id`.

Review round 2 (adversarial review of PR #118) fixes, each with its own dedicated
test(s), added in this pass:
  N1 — `_trunk_sha_prev`/`_trunk_sha` used to be plain Engine instance attrs, reset
       to "" in `__init__` — but production constructs a FRESH `Engine(ctx)` every
       tick (wake.py), so the observed-advance window never survived a tick
       boundary and the crash-window bypass check misfired on every legitimate
       land. Now persisted in `self.st.trunk_sha_observed` (state.py). The F1 tests
       above are REWRITTEN to prove it across TWO separate `Engine(ctx)`
       constructions sharing one state file (never a manually-stubbed window) —
       `t_f1_live_grant_content_match_authorizes_and_consumes`,
       `t_f1_live_grant_content_mismatch_is_violation` — plus a dedicated
       legacy-state/first-tick-safety case,
       `t_n1_legacy_state_missing_field_degrades_safely_once`.
  N2 — the F4 sealed-allowlist escalation handler now guards against minting an
       unbounded case/architect-job per RECURRING trip (an existing undecided case
       for the same origin is reused; the forensic event still fires every time) —
       `t_n2_sealed_allowlist_recurring_trip_mints_only_one_case`.
  N3 — `_under_scratch_root` is now fail-closed (a missing `scratch_root` REFUSES,
       never passes unconditionally) and real-path-aware (symlinks resolved, not
       just `..`-collapsed) — `t_n3_scratch_root_fail_closed_and_realpath`.

Run: python3 engine/block_01_32_test.py   (exit 0 = pass). No tokens, no network for
the FSM cases; the real-git case shells out to a throwaway `git init` repo, same
convention as block_01_17_test.py/tron13_test.py.
"""
import os
import sys
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import trunk                                            # noqa: E402
from fsm import Engine                                   # noqa: E402
from sentry_test import build, started                   # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── real-git fixture (block_01_17_test/tron13_test convention) ──
def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _mkrepo(prefix="tron-0132-"):
    d = tempfile.mkdtemp(prefix=prefix)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    os.makedirs(os.path.join(d, "meta"))
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | to-do |\n| A-02 | to-do |\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


# ── AC-2 (real git): the wave-1b shape itself — a stale close-out branch cut before
# another block's row landed would REVERT it if silently merged/rebased by the engine ──
def t_clobber_dead_real_git():
    d = _mkrepo()
    # The soon-to-close worker's branch, cut from base: touches ONLY its own row.
    _git(d, "checkout", "-qb", "feat/a-02")
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | to-do |\n| A-02 | done |\n")
    _git(d, "commit", "-aqm", "A-02 done")
    _git(d, "checkout", "-q", "main")
    # Meanwhile A-01 landed on trunk FIRST — trunk's pipeline.md now differs from the
    # closer's pre-image on the SAME file (the exact wave-1b shape: a non-ff on a
    # shared, small paperwork file).
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | done |\n| A-02 | to-do |\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "A-01 done")
    okm, err = trunk.merge_ff_only(d, "feat/a-02", "main")
    ok("AC-2 clobber_dead: the stale close-out branch is REFUSED, never silently "
       "rebased-and-landed", okm is False, f"err={err}")
    trunk_content = open(os.path.join(d, "meta", "pipeline.md")).read()
    ok("AC-2 clobber_dead: trunk's A-01 row is untouched — no revert, ever",
       "A-01 | done" in trunk_content)
    ok("AC-2 clobber_dead: no rebase was ever attempted on trunk's behalf (no residue)",
       not os.path.exists(os.path.join(d, ".git", "rebase-merge"))
       and not os.path.exists(os.path.join(d, ".git", "rebase-apply")))
    shutil.rmtree(d, ignore_errors=True)


# ── FSM-level: the DONE ritual around a non-ff, real git under a dry engine ──
def _eng(block="A-01"):
    ctx, _ = build(blocks=[(block, "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    eng.st.branches[block] = f"feat/{block}"
    return eng


def _stub(exists=True, ff_sequence=None):
    """ff_sequence: a list of (ok, err) tuples, one consumed per merge_ff_only call
    (the last value repeats once exhausted) — models the worker's branch state
    changing (or not) across successive rebase attempts."""
    calls = {"n": 0}
    seq = list(ff_sequence or [(False, "not a fast-forward")])

    def _merge(*a, **k):
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        return seq[i]

    trunk.branch_exists = lambda *a, **k: exists
    trunk.merge_ff_only = _merge
    return calls


def t_non_ff_orders_rebase_not_wall():
    orig = (trunk.branch_exists, trunk.merge_ff_only)
    _stub()
    try:
        eng = _eng()
        g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
        eng._drive_gate("A-01", g)                      # -> local (first pass)
        eng._drive_gate("A-01", g, on_report=True)       # ff refused
        ok("AC-2 non-ff: stays at local (worker's ritual, not an engine wall)",
           g.get("stage") == "local")
        ok("AC-2 non-ff: rebase_pending is set (the ordered ritual step)",
           g.get("rebase_pending") is True)
        ok("AC-2 non-ff: no case/wall raised — the worker gets first crack at it",
           not eng.st.pending_cases)
    finally:
        trunk.branch_exists, trunk.merge_ff_only = orig


def t_held_approval_never_retries_without_fresh_report():
    # ASK mode: an operator "approve" grant must never let a BARE idle tick retry the
    # merge once a rebase has been ordered — only a fresh on_report (the worker's
    # reported rebase + re-validate) may re-enter the merge attempt. This is the
    # concrete fsm.py fix (01-32 T1): `elif on_report or (approved_merge and not
    # rebase_pending):` — the direct behavioral proof that a held grant alone can't
    # silently re-drive git state nobody re-validated.
    orig = (trunk.branch_exists, trunk.merge_ff_only)
    calls = _stub()
    try:
        eng = _eng()
        eng.st.approvals["merge"] = "ASK"
        g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
        eng._drive_gate("A-01", g)                      # -> local
        eng._drive_gate("A-01", g, on_report=True)       # evidence -> ASK parks a case
        cid = next(c for c in eng.st.pending_cases)
        eng._h_apply_decision({"case": cid, "decision": "approve", "block": "A-01"})
        ok("setup: approve grants approved_merge", g.get("approved_merge") is True)
        n_before = calls["n"]
        ok("setup: the grant's own merge attempt hit the non-ff refusal, rebase ordered",
           g.get("rebase_pending") is True and n_before >= 1)
        # A bare tick — NOT a fresh report — must not call merge_ff_only again.
        eng._drive_gate("A-01", g)
        ok("AC-2 grant crash-safety: a bare idle tick never re-attempts the merge while "
           "a rebase is pending (no blind retry on stale/unreviewed git state)",
           calls["n"] == n_before, f"calls before={n_before} after={calls['n']}")
        ok("AC-2 grant crash-safety: the gate is still at local, not trunk — nothing "
           "landed behind the worker's back", g.get("stage") == "local")
    finally:
        trunk.branch_exists, trunk.merge_ff_only = orig


def t_fresh_report_after_rebase_lands():
    # The happy path this whole ritual exists for: the worker rebases + re-validates in
    # its OWN worktree (never TRON), then reports done again — THAT fresh on_report is
    # what re-drives the merge attempt, and only then.
    orig = (trunk.branch_exists, trunk.merge_ff_only)
    calls = _stub(ff_sequence=[(False, "not a fast-forward"), (True, "")])
    try:
        eng = _eng()
        g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
        eng._drive_gate("A-01", g)                      # -> local
        eng._drive_gate("A-01", g, on_report=True)       # ff refused -> rebase ordered
        ok("setup: rebase ordered after the first refusal", g.get("rebase_pending") is True)
        # A bare tick still must not retry (same invariant as above).
        eng._drive_gate("A-01", g)
        ok("AC-2: idle ticks between the order and the worker's fresh report never retry",
           calls["n"] == 1)
        # The worker's fresh report — rebase done, re-validated — re-enters the merge.
        eng._drive_gate("A-01", g, on_report=True)
        ok("AC-2: the fresh on_report re-attempts the merge (worker-owned resolution)",
           calls["n"] == 2)
        ok("AC-2: it lands -> re-validate on trunk (rebase_pending cleared)",
           g.get("stage") == "trunk" and not g.get("rebase_pending"))
    finally:
        trunk.branch_exists, trunk.merge_ff_only = orig


def t_unresolvable_rebase_walls_architect_with_content():
    # The worker keeps reporting done, but the branch never actually becomes
    # fast-forwardable (an unfinishable rebase, e.g. a conflict it can't resolve) —
    # this must NEVER hang forever and NEVER silently corrupt trunk. It walls, with
    # real content, and (per block 01-31, ADR-0002 D2) routes to the architect FIRST,
    # never straight to the operator.
    orig = (trunk.branch_exists, trunk.merge_ff_only)
    _stub()   # every attempt refuses — the worker can never land it
    try:
        eng = _eng()
        arch = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
               "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
        eng.st.workers.append(arch)
        g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
        clock = {"t": 1000.0}
        eng._now_s = lambda: clock["t"]
        eng._drive_gate("A-01", g)                      # -> local
        eng._drive_gate("A-01", g, on_report=True)       # ff refused -> rebase ordered
        eng._tq = []
        eng._drive_gate("A-01", g)                       # anchor idle_since at 'local'
        clock["t"] += eng._pace("gate_idle_cap", 3) + 1  # past the idle cap
        eng._drive_gate("A-01", g)
        eng._drain_triggers()
        case = next((c for cid, c in eng.st.pending_cases.items()
                    if c.get("block") == "A-01"), None)
        ok("AC-2: an unresolvable rebase walls (never a silent hang, never a corrupt land)",
           case is not None and "A-01" not in eng.st.gate, f"case={case} gate={eng.st.gate}")
        ok("AC-2: the wall CARRIES content (never a contentless placeholder)",
           bool(case and case.get("detail")), f"case={case}")
        ok("AC-2: it dispatches the architect first — never a direct operator page "
           "(ADR-0002 D2, 01-31)",
           (arch.get("current_job") or {}).get("kind") == "triage"
           and (arch.get("current_job") or {}).get("case") is not None, f"arch={arch}")
    finally:
        trunk.branch_exists, trunk.merge_ff_only = orig


# ══════════════════════════════════════════════════════════════════════════════
# T2 (01-32, ADR-0002 D1): read-path refactor — the git wrapper's audit trail, the
# checkout-free CAS merge arm, engine-wide truth-ref re-keying, detached root at seat
# + the per-tick detachment check (AC-6, test:<root_reattach_detected>), and the
# scratch-dir spawn bootstrap's carve-observation window.
# ══════════════════════════════════════════════════════════════════════════════

# ── AC-1 wrapper audit: the CAS merge never checks out the root, and the wrapper's
# audit trail records every git invocation so the write-boundary is assertable, not
# just believed ──
def t_wrapper_audit_no_checkout_on_cas_land():
    # T3 re-scope: `merge_ff_only` is now `would_ff` — a PURE ff-ability read (the T2
    # transitional CAS write is retired with every other mutation arm). The wrapper
    # audit must show ZERO mutating git subcommands for a "merge" check: no checkout
    # (the trunk.py:227 hazard, gone since T2), no merge, and now no update-ref
    # either — the advance is land.sh's (a separate OS process outside this wrapper
    # entirely), never the engine's.
    d = _mkrepo("tron-0132-audit-")
    _git(d, "checkout", "-qb", "feat/a-01")
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | done |\n| A-02 | to-do |\n")
    _git(d, "commit", "-aqm", "A-01 done")
    _git(d, "checkout", "-q", "main")
    trunk.reset_audit()
    okm, err = trunk.merge_ff_only(d, "feat/a-01", "main")
    ok("AC-1 wrapper: the ff-ability check reads ok", okm, f"err={err}")
    audit = trunk.audit_log()
    ok("AC-1 wrapper: the audit trail is non-empty (every invocation recorded)",
       len(audit) > 0)
    ok("AC-1 wrapper: NOT ONE recorded invocation is a `checkout` — the old "
       "trunk.py:227 hazard is structurally gone",
       not any(argv[3:4] == ["checkout"] for argv, _rc in audit), f"audit={audit}")
    ok("AC-1 wrapper (T3): no `update-ref` either — the engine never advances trunk; "
       "land.sh does, outside this wrapper entirely",
       not any(argv[3:4] == ["update-ref"] for argv, _rc in audit), f"audit={audit}")
    ok("AC-1 wrapper: no `merge` command either — never a merge commit, never implicit",
       not any(argv[3:4] == ["merge"] for argv, _rc in audit), f"audit={audit}")
    _, main_tip, _ = _git(d, "rev-parse", "main")
    _, branch_tip, _ = _git(d, "rev-parse", "feat/a-01")
    ok("AC-1 wrapper (T3): trunk did NOT move — would_ff is a read, never a write",
       main_tip != branch_tip, f"main={main_tip} branch={branch_tip}")
    shutil.rmtree(d, ignore_errors=True)


# ── AC-6 (trunk-level mechanism): merge_ff_only's own structural refusal — the
# "landing holds until detachment is restored" half of AC-6, independent of the
# engine's own case-tracking state ──
def t_merge_ff_only_require_detached_refuses_then_succeeds():
    d = _mkrepo("tron-0132-detach-")
    _git(d, "checkout", "-qb", "feat/a-01")
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | done |\n| A-02 | to-do |\n")
    _git(d, "commit", "-aqm", "A-01 done")
    _git(d, "checkout", "-q", "main")           # root ATTACHED to main — the violation shape
    ok("AC-6 setup: root_head_detached reads False while attached",
       trunk.root_head_detached(d) is False)
    okm, err = trunk.merge_ff_only(d, "feat/a-01", "main", require_detached=True)
    ok("AC-6: merge_ff_only refuses to advance trunk while the root is attached "
       "(structural — 'landing holds until detachment is restored')",
       okm is False and "detached" in err, f"okm={okm} err={err}")
    trunk_content = open(os.path.join(d, "meta", "pipeline.md")).read()
    ok("AC-6: trunk is untouched by the refused attempt", "A-01 | to-do" in trunk_content)
    _git(d, "checkout", "-q", "--detach", "HEAD")
    ok("AC-6: root_head_detached reads True once detached", trunk.root_head_detached(d) is True)
    okm2, err2 = trunk.merge_ff_only(d, "feat/a-01", "main", require_detached=True)
    ok("AC-6: the SAME merge succeeds once detachment is restored — no other change",
       okm2 is True, f"err2={err2}")
    shutil.rmtree(d, ignore_errors=True)


# ── AC-6 (engine-level detection): a re-attached root is detected within ONE tick,
# routed through the EXISTING case machinery (never a new mechanism), and self-clears
# once detachment is restored ──
def t_check_root_detached_opens_case_then_self_clears():
    d = _mkrepo("tron-0132-detect-")
    eng = _eng()
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["main_branch"] = "main"
    eng.paths["remote"] = None                 # local mode — the only mode this applies to
    arch = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
           "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
    eng.st.workers.append(arch)
    try:
        # d is attached to `main` by _mkrepo's own `git init` (never detached) — the
        # violation shape, no worker action needed to reproduce it.
        eng._check_root_detached()
        eng._drain_triggers()
        ok("AC-6: an attached root is detected THE SAME TICK it's checked — a case opens",
           "root-reattach" in eng.st.blocked, f"blocked={eng.st.blocked}")
        case = next((c for c in eng.st.pending_cases.values()
                    if c.get("block") == "root-reattach"), None)
        ok("AC-6: the case carries real content (never a contentless placeholder)",
           bool(case and case.get("detail")), f"case={case}")
        ok("AC-6: it routes to the architect FIRST (ADR-0002 D2/D3), not a bare operator page",
           (arch.get("current_job") or {}).get("kind") == "triage", f"arch={arch}")
        # Idempotent: a second tick's check while still attached must not open a SECOND
        # case (the existing `block in self.st.blocked` dedupe, reused, not reinvented).
        n_cases_before = len(eng.st.pending_cases)
        eng._check_root_detached()
        eng._drain_triggers()
        ok("AC-6: re-checking while still attached is idempotent (no duplicate case)",
           len(eng.st.pending_cases) == n_cases_before)
        # Restore detachment -> the very next check self-clears, no operator round-trip.
        _git(d, "checkout", "-q", "--detach", "HEAD")
        eng._check_root_detached()
        ok("AC-6: detachment restored -> the hold releases on its own",
           "root-reattach" not in eng.st.blocked, f"blocked={eng.st.blocked}")
        ok("AC-6: the case closes with it (case-owns-hold, 01-31/ADR-0002 D5)",
           not any(c.get("block") == "root-reattach" for c in eng.st.pending_cases.values()))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── T3 (01-34, ADR-0003 D-A) supersedes this file's own original T2 carve-wall
# tests: carve is a WORKER RITUAL, not an operator wall — the tick-deadline wall
# this pair used to assert is RETIRED (a false timing failure). Kept here (renamed,
# rewritten) rather than deleted so this file's own history stays legible; the
# block-01-34 test file carries the AC-5 both-sides regression coverage. ──
def t_carve_bootstrap_slow_worker_raises_no_case():
    d = _mkrepo("tron-0132-carve-")
    eng = _eng()
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["main_branch"] = "main"
    w = {"id": "ENG-A-01", "role": "engineer", "block": "A-01", "status": "working",
        "_carve_pending": True}   # not yet carved, spawned "long" ago
    eng.st.workers.append(w)
    try:
        eng._now_s = lambda: 1_000_000.0
        eng._check_carve_bootstrap()             # first observation: starts the liveness clock
        eng._now_s = lambda: 1_000_000.0 + 60     # well past any tick count, nowhere near the
        eng._check_carve_bootstrap()              # default carve_liveness_timeout (300s)
        eng._drain_triggers()
        ok("T3 (01-34, D-A): a merely slow pre-carve worker raises NO case at all "
           "(the old tick-deadline wall is retired)",
           "A-01" not in eng.st.blocked and not eng.st.pending_cases,
           f"blocked={eng.st.blocked} cases={eng.st.pending_cases}")
        ok("T3: still pending — no substitute carve, no release", w.get("_carve_pending") is True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_carve_bootstrap_satisfied_stops_checking():
    d = _mkrepo("tron-0132-carve-ok-")
    _git(d, "branch", "feat/A-01")               # the worker's own carve, observed
    eng = _eng()
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["main_branch"] = "main"
    w = {"id": "ENG-A-01", "role": "engineer", "block": "A-01", "status": "working",
        "_carve_pending": True}
    eng.st.workers.append(w)
    try:
        eng._check_carve_bootstrap()
        eng._drain_triggers()
        ok("T3 carve bootstrap: an observed carve clears the pending marker, no wall",
           "_carve_pending" not in w and "A-01" not in eng.st.blocked, f"w={w}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# T3 (01-32, ADR-0002 D2): merge inversion proper — grants, land.sh, the sealed
# wrapper allowlist, verify_docs, the reference-transaction hook, detect-only floor.
# ══════════════════════════════════════════════════════════════════════════════
import grants                                             # noqa: E402

LAND_SH = os.path.join(os.path.dirname(HERE), "templates", "project-scaffold",
                       "templates", "meta", "scripts", "land.sh")
HOOK_SH = os.path.join(os.path.dirname(HERE), "templates", "project-scaffold",
                       "templates", "meta", ".githooks", "reference-transaction")


def _run_land(repo, case_id, grants_dir, main="main"):
    return subprocess.run(["bash", LAND_SH, case_id, "--main", main],
                          cwd=repo, capture_output=True, text=True,
                          env={**os.environ, "LAND_GRANTS_DIR": grants_dir})


def _mkrepo_detached(prefix="tron-0132-t3-"):
    """Real repo, root DETACHED (local-mode seat convention), a clean feat/a-01
    branch touching only its own pipeline row — ready to land."""
    d = _mkrepo(prefix)
    _git(d, "checkout", "-qb", "feat/a-01")
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | done |\n| A-02 | to-do |\n")
    _git(d, "commit", "-aqm", "A-01 done")
    _git(d, "checkout", "-q", "main")
    _git(d, "checkout", "-q", "--detach", "HEAD")
    return d


def _eng_real(d, block="A-01"):
    """A started engine over the REAL repo `d`, local mode, non-dry — the shape the
    T3 E2E cases drive."""
    eng = _eng(block)
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["main_branch"] = "main"
    eng.paths["remote"] = None
    eng.st.branches[block] = f"feat/{block.lower()}"   # the fixture repo's branch name
    return eng


# ── T3 sealed allowlist: an off-list git subcommand raises loud (never swallowed) ──
def t_sealed_allowlist_refuses_offlist_git():
    d = _mkrepo("tron-0132-seal-")
    raised = False
    trunk.reset_audit()
    try:
        trunk._run(["git", "-C", d, "update-ref", "refs/heads/main", "HEAD"])
    except trunk.SealedAllowlistViolation:
        raised = True
    ok("T3 seal: `update-ref` through the wrapper raises SealedAllowlistViolation "
       "(structurally impossible, never a best-effort '' read)", raised)
    ok("T3 seal: the refused ATTEMPT is still recorded in the audit trail (rc=126)",
       any(argv[3:4] == ["update-ref"] and rc == 126 for argv, rc in trunk.audit_log()))
    for sub in ("checkout", "merge", "commit", "branch", "rebase", "push", "reset"):
        try:
            trunk._run(["git", "-C", d, sub])
            ok(f"T3 seal: `{sub}` refused", False, "no exception raised")
        except trunk.SealedAllowlistViolation:
            ok(f"T3 seal: `{sub}` refused", True)
    okr, _, _ = trunk._run(["git", "-C", d, "rev-parse", "HEAD"])
    ok("T3 seal: reads still pass (rev-parse)", okr == 0)
    ok("T3 seal: `worktree add` WITHOUT --detach is refused even though `worktree` "
       "is listed", not trunk._subcommand_allowed(
           ["git", "-C", d, "worktree", "add", "/tmp/x", "somebranch"]))
    # N3 (review round 2): `scratch_root` is now REQUIRED (fail-closed) — a
    # worktree add/remove with none supplied refuses outright (see
    # `t_n3_scratch_root_fail_closed_and_realpath`), so this positive case must
    # supply one that actually contains the target.
    ok("T3 seal: `worktree add --detach` (scratch validation checkouts) passes "
       "when the target is scratch-scoped",
       trunk._subcommand_allowed(
           ["git", "-C", d, "worktree", "add", "--detach", "-q", "/tmp/x", "abc"],
           scratch_root="/tmp"))
    shutil.rmtree(d, ignore_errors=True)


# ── AC-1 test:<worker_lands_engine_observes> — the full close-out E2E ──
def t_worker_lands_engine_observes():
    d = _mkrepo_detached("tron-0132-ac1-")
    eng = _eng_real(d)
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    trunk.reset_audit()
    # Worker reports done -> the gate verifies ff-ability, mints a grant, orders
    # land.sh — and does NOT advance trunk itself.
    eng._drive_gate("A-01", g, on_report=True)
    case_id = g.get("landing_case")
    ok("AC-1: the gate minted a grant and ordered the land (landing_case set)",
       bool(case_id), f"g={g}")
    live = grants.read_live(eng.ctx.grants_dir, case_id)
    ok("AC-1: the grant is LIVE in TRON's own folder, patch-id-bound",
       bool(live) and bool(live.get("patch_id")), f"live={live}")
    _, main_before, _ = _git(d, "rev-parse", "main")
    _, tip, _ = _git(d, "rev-parse", "feat/a-01")
    ok("AC-1: trunk did NOT move on the engine's own account", main_before != tip)
    # The WORKER runs land.sh (rebase-before-close already holds: the branch is ff).
    r = _run_land(d, case_id, eng.ctx.grants_dir)
    ok("AC-1: land.sh (the worker's hands) lands it", r.returncode == 0,
       f"stdout={r.stdout} stderr={r.stderr}")
    _, main_after, _ = _git(d, "rev-parse", "main")
    ok("AC-1: trunk now IS the branch tip — landed by the script, not the engine",
       main_after == tip)
    ok("AC-1: land.sh consumed the grant (receipt on file)",
       grants.read_consumed(eng.ctx.grants_dir, case_id) is not None
       and grants.read_live(eng.ctx.grants_dir, case_id) is None)
    # Engine observes + closes: next tick's gate pass sees branch_merged.
    eng._drive_gate("A-01", g)
    ok("AC-1: the engine OBSERVES the landing and advances to trunk re-validate",
       g.get("stage") == "trunk" and g.get("merged_sha"), f"g={g}")
    # The write-boundary audit: zero engine git-writes, full stop (fetch/scratch
    # worktree admin never fire in this scenario either).
    writes = [(argv, rc) for argv, rc in trunk.audit_log()
              if argv[0] == "git" and len(argv) > 3
              and argv[3] in ("update-ref", "checkout", "merge", "commit", "branch",
                              "rebase", "push", "reset", "mv", "rm")]
    ok("AC-1: wrapper audit shows ZERO engine git-writes across the whole close-out "
       "(minus fetch transport + scratch worktree admin — neither fired here)",
       not writes, f"writes={writes}")
    shutil.rmtree(d, ignore_errors=True)


# ── AC-3 test:<grantless_land_prevented_and_detected> ──
def t_grantless_land_prevented_and_detected():
    d = _mkrepo_detached("tron-0132-ac3-")
    eng = _eng_real(d)
    arch = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
           "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
    eng.st.workers.append(arch)
    # Arm 1 — the script refuses: no grant on file at all.
    r = _run_land(d, "no-such-case", eng.ctx.grants_dir)
    ok("AC-3 prevent (script): land.sh refuses with no live grant",
       r.returncode != 0 and "no live grant" in (r.stderr + r.stdout),
       f"rc={r.returncode} out={r.stdout} err={r.stderr}")
    _, main_tip, _ = _git(d, "rev-parse", "main")
    _, branch_tip, _ = _git(d, "rev-parse", "feat/a-01")
    ok("AC-3 prevent (script): trunk untouched by the refusal", main_tip != branch_tip)
    # Arm 2 — the hook refuses where installed: simulate git's own invocation shape.
    old, new = main_tip, branch_tip
    hr = subprocess.run(["bash", HOOK_SH, "prepared"],
                        input=f"{old} {new} refs/heads/main\n",
                        cwd=d, capture_output=True, text=True,
                        env={**os.environ, "LAND_GRANTS_DIR": eng.ctx.grants_dir})
    ok("AC-3 prevent (hook): the reference-transaction hook refuses a grantless "
       "trunk ref-update", hr.returncode != 0, f"out={hr.stdout} err={hr.stderr}")
    hr2 = subprocess.run(["bash", HOOK_SH, "prepared"],
                         input=f"{old} {new} refs/heads/feat/other\n",
                         cwd=d, capture_output=True, text=True,
                         env={**os.environ, "LAND_GRANTS_DIR": eng.ctx.grants_dir})
    ok("AC-3 hook is TRUNK-SCOPED: a non-trunk ref write passes untouched "
       "(never taxes fleet branches)", hr2.returncode == 0, f"err={hr2.stderr}")
    # Arm 3 — forced past both (raw update-ref, exactly what a rogue writer would
    # do): next tick detects -> violation case -> architect; block never closes.
    _git(d, "update-ref", "refs/heads/main", new, old)
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    eng._tq = []
    eng._drive_gate("A-01", g)
    eng._drain_triggers()
    case = next((c for c in eng.st.pending_cases.values()
                if c.get("block") == "A-01"), None)
    ok("AC-3 detect: the forced land is caught next tick -> violation case",
       case is not None and "A-01" not in eng.st.gate,
       f"case={case} gate={eng.st.gate}")
    ok("AC-3 detect: the case names the grantless-land shape",
       bool(case) and "grant" in (case.get("detail") or ""), f"case={case}")
    ok("AC-3 detect: routed architect-first (ADR-0002 D3)",
       (arch.get("current_job") or {}).get("kind") == "triage", f"arch={arch}")
    ok("AC-3: the block never closes on it (blocked, no gate)",
       "A-01" in eng.st.blocked, f"blocked={eng.st.blocked}")
    shutil.rmtree(d, ignore_errors=True)


# ── AC-4 test:<grant_crash_windows> — all four arms ──
def t_grant_crash_windows():
    d = _mkrepo_detached("tron-0132-ac4-")
    gd = tempfile.mkdtemp(prefix="tron-0132-grants-")
    pid = trunk.patch_id(d, "feat/a-01", "main")
    ok("AC-4 setup: a real patch-id derives", bool(pid), f"pid={pid}")

    # Arm D first (fail-closed): "" never mints, never matches.
    ok("AC-4 ''-rider: an empty patch-id NEVER mints",
       grants.mint(gd, "CASE-EMPTY", "A-01", "feat/a-01", "") is None
       and grants.read_raw(gd, "CASE-EMPTY") is None)
    minted = grants.mint(gd, "CASE-1", "A-01", "feat/a-01", pid)
    ok("AC-4 setup: a real grant mints", bool(minted))
    ok("AC-4 ''-rider: a '' comparison NEVER matches, even a live grant",
       grants.matches(minted, "") is False)
    ok("AC-4 ''-rider: nor does '' vs '' (both sides fail-closed)",
       grants.matches({"patch_id": ""}, "") is False)

    # Arm A — consume-then-crash (crash BEFORE the ref advance): the grant is
    # still LIVE; a retry re-validates and lands with NO operator re-ask.
    r = _run_land(d, "CASE-1", gd)
    ok("AC-4 pre-advance crash window: the retry (the first actual run here) "
       "validates the still-live grant and lands, no re-ask", r.returncode == 0,
       f"out={r.stdout} err={r.stderr}")
    _, main_tip, _ = _git(d, "rev-parse", "main")
    _, tip, _ = _git(d, "rev-parse", "feat/a-01")
    ok("AC-4: landed", main_tip == tip)

    # Arm B — post-advance crash: trunk advanced, grant consumed + receipt on file
    # -> a retry exits 0 via the already-landed arm (consumed+receipt half)...
    r2 = _run_land(d, "CASE-1", gd)
    ok("AC-4 post-advance retry (consumed + receipt on file) exits 0 — a non-event",
       r2.returncode == 0 and "already consumed" in r2.stdout,
       f"rc={r2.returncode} out={r2.stdout}")
    # ...and the LIVE-grant half: re-mint a live grant for an already-landed branch
    # (the exact crash-after-advance-before-consume window shape) — the retry finds
    # the tip already an ancestor WHILE a live grant exists, consumes it, exits 0.
    grants.mint(gd, "CASE-2", "A-01", "feat/a-01", pid)
    r3 = _run_land(d, "CASE-2", gd)
    ok("AC-4 post-advance crash retry (grant still LIVE) exits 0 via the "
       "already-landed arm and consumes administratively",
       r3.returncode == 0 and "already an ancestor" in r3.stdout
       and grants.read_consumed(gd, "CASE-2") is not None
       and grants.read_live(gd, "CASE-2") is None,
       f"rc={r3.returncode} out={r3.stdout}")
    # The ENGINE-side administrative consume (TRON's own crash-window arm): a live
    # grant whose landing TRON observed is consumed as a write in its own folder.
    grants.mint(gd, "CASE-3", "A-01", "feat/a-01", pid)
    got = grants.consume(gd, "CASE-3", result="engine-observed")
    ok("AC-4 administrative consume: engine-side consume writes the receipt",
       bool(got) and grants.read_consumed(gd, "CASE-3") is not None)
    ok("AC-4 administrative consume is idempotent (a second call returns the "
       "existing receipt, never double-writes)",
       grants.consume(gd, "CASE-3") == grants.read_consumed(gd, "CASE-3"))

    # Arm C — loud expiry re-open: an expired grant refuses in land.sh AND the
    # engine's own read treats it as not-live; the FSM re-opens loudly. Backdate the
    # mint (grants.mint's `now` param) two hours — robustly past the default 60-min
    # TTL for both readers (land.sh's `date +%s` read is whole-second).
    import time as _t
    grants.mint(gd, "CASE-4", "A-02", "feat/a-01", pid, ttl_min=60,
                now=_t.time() - 7200)
    ok("AC-4 expiry: read_live treats an expired grant as gone (fail-closed)",
       grants.read_live(gd, "CASE-4") is None
       and grants.read_raw(gd, "CASE-4") is not None)
    r4 = _run_land(d, "CASE-4", gd)
    ok("AC-4 expiry: land.sh refuses an expired grant LOUDLY (never a silent re-mint)",
       r4.returncode != 0 and "expired" in (r4.stderr + r4.stdout),
       f"rc={r4.returncode} err={r4.stderr}")
    # Engine side: _grant_expired_reopen fires the loud re-open (case cleared,
    # architect routed) — driven directly at the seam.
    eng = _eng_real(d, block="A-02")
    arch = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
           "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
    eng.st.workers.append(arch)
    # point the engine's grants dir at our fixture dir
    import ctx as _ctxmod
    g = {"stage": "local", "pr": None, "approved_merge": True,
        "landing_case": "CASE-4"}
    orig_gd = _ctxmod.Ctx.grants_dir
    _ctxmod.Ctx.grants_dir = property(lambda self: gd)
    try:
        fired = eng._grant_expired_reopen("A-02", g, "CASE-4", "ENG-A-02")
    finally:
        _ctxmod.Ctx.grants_dir = orig_gd
    ok("AC-4 expiry: the engine re-opens the case LOUDLY (approved_merge cleared, "
       "architect triaged — never an operator-silent lapse)",
       fired is True and not g.get("approved_merge")
       and (arch.get("current_job") or {}).get("kind") == "triage",
       f"fired={fired} g={g} arch={arch}")
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(gd, ignore_errors=True)


# ── AC-4 rider: the ENGINE-side administrative consume walks first-parent over the
# observed window and consumes every matching live grant (two advances, one window —
# the land.sh-crashed-before-consume shape at fleet scale) ──
def t_administrative_consume_first_parent_walk():
    d = _mkrepo("tron-0132-walk-")
    _git(d, "checkout", "-qb", "feat/a-01")
    with open(os.path.join(d, "meta", "a01.md"), "w") as fh:
        fh.write("a01\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "A-01")
    _git(d, "checkout", "-q", "main")
    _git(d, "checkout", "-q", "--detach", "HEAD")
    eng = _eng_real(d)
    gd = eng.ctx.grants_dir
    _, old, _ = _git(d, "rev-parse", "main")
    # Land 1 (simulating land.sh's update-ref, crash BEFORE its consume).
    pid1 = trunk.patch_id(d, "feat/a-01", "main")
    grants.mint(gd, "CASE-W1", "A-01", "feat/a-01", pid1)
    _, tip1, _ = _git(d, "rev-parse", "feat/a-01")
    _git(d, "update-ref", "refs/heads/main", tip1, old)
    # Land 2 in the SAME window: a second branch off the new trunk.
    _git(d, "branch", "feat/a-02", tip1)
    wt = os.path.join(d, ".wtw")
    _git(d, "worktree", "add", "--detach", "-q", wt)
    _git(wt, "checkout", "-q", "feat/a-02")
    with open(os.path.join(wt, "meta", "a02.md"), "w") as fh:
        fh.write("a02\n")
    _git(wt, "add", "-A"); _git(wt, "commit", "-qm", "A-02")
    _git(d, "worktree", "remove", "--force", wt)
    pid2 = trunk.patch_id(d, "feat/a-02", "main")
    grants.mint(gd, "CASE-W2", "A-02", "feat/a-02", pid2)
    _, tip2, _ = _git(d, "rev-parse", "feat/a-02")
    _git(d, "update-ref", "refs/heads/main", tip2, tip1)
    # The engine's next observation: one window, two advances -> first-parent walk
    # matches each step's patch-id and consumes BOTH grants administratively.
    eng._sweep_grant_consume(old, tip2)
    ok("AC-4 walk: BOTH crash-window grants consumed over one observation window "
       "(first-parent walk, per step)",
       grants.read_consumed(gd, "CASE-W1") is not None
       and grants.read_consumed(gd, "CASE-W2") is not None
       and not grants.list_live(gd),
       f"live={grants.list_live(gd)}")
    shutil.rmtree(d, ignore_errors=True)


# ── AC-5 test:<concurrent_closes_cas> ──
def t_concurrent_closes_cas():
    d = _mkrepo("tron-0132-ac5-")
    gd = tempfile.mkdtemp(prefix="tron-0132-ac5-grants-")
    # Two workers' branches off the same base, disjoint files.
    _git(d, "checkout", "-qb", "feat/a-01")
    with open(os.path.join(d, "meta", "a01.md"), "w") as fh:
        fh.write("a01 work\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "A-01")
    _git(d, "checkout", "-q", "main")
    _git(d, "checkout", "-qb", "feat/a-02")
    with open(os.path.join(d, "meta", "a02.md"), "w") as fh:
        fh.write("a02 work\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "A-02")
    _git(d, "checkout", "-q", "main")
    _git(d, "checkout", "-q", "--detach", "HEAD")
    pid1 = trunk.patch_id(d, "feat/a-01", "main")
    pid2 = trunk.patch_id(d, "feat/a-02", "main")
    grants.mint(gd, "CASE-A01", "A-01", "feat/a-01", pid1)
    grants.mint(gd, "CASE-A02", "A-02", "feat/a-02", pid2)
    # Close 1 lands.
    r1 = _run_land(d, "CASE-A01", gd)
    ok("AC-5: the first close lands", r1.returncode == 0, f"err={r1.stderr}")
    # Close 2 — trunk moved: strict-ff check fails (the CAS-loser shape; with the
    # flock serializing real concurrency, the loser always surfaces as exactly this).
    r2 = _run_land(d, "CASE-A02", gd)
    ok("AC-5: the concurrent loser fails LOUDLY (not a fast-forward), told to "
       "rebase-retry", r2.returncode != 0 and "not a fast-forward" in r2.stderr,
       f"rc={r2.returncode} err={r2.stderr}")
    # PURE rebase (disjoint files -> content unchanged) -> the patch-id survives ->
    # the SAME grant carries; retry lands with no re-ask.
    _git(d, "worktree", "add", "--detach", "-q", os.path.join(d, ".wt2"))
    wt = os.path.join(d, ".wt2")
    _git(wt, "checkout", "-q", "feat/a-02")
    rc_rb, _, err_rb = _git(wt, "rebase", "main")
    _git(d, "worktree", "remove", "--force", wt)
    ok("AC-5 setup: the pure rebase applies cleanly (disjoint files)", rc_rb == 0, err_rb)
    pid2_re = trunk.patch_id(d, "feat/a-02", "main")
    ok("AC-5: a pure rebase preserves the patch-id (grant carries)",
       pid2_re == pid2, f"before={pid2} after={pid2_re}")
    r3 = _run_land(d, "CASE-A02", gd)
    ok("AC-5: the rebase-retry lands under the ORIGINAL grant — no gate re-ask",
       r3.returncode == 0, f"err={r3.stderr}")
    # Content-CHANGING rebase: a third branch whose rebase alters its diff ->
    # patch-id changes -> the old grant no longer matches -> land.sh refuses ->
    # fail-toward-gate (re-ask), by design.
    _, main_now, _ = _git(d, "rev-parse", "main")
    _git(d, "branch", "feat/a-03", main_now)
    wt3 = os.path.join(d, ".wt3")
    _git(d, "worktree", "add", "--detach", "-q", wt3)
    _git(wt3, "checkout", "-q", "feat/a-03")
    with open(os.path.join(wt3, "meta", "a03.md"), "w") as fh:
        fh.write("a03 v1\n")
    _git(wt3, "add", "-A"); _git(wt3, "commit", "-qm", "A-03 v1")
    pid3 = trunk.patch_id(d, "feat/a-03", "main")
    grants.mint(gd, "CASE-A03", "A-03", "feat/a-03", pid3)
    with open(os.path.join(wt3, "meta", "a03.md"), "w") as fh:
        fh.write("a03 v2 - content changed\n")
    _git(wt3, "add", "-A"); _git(wt3, "commit", "-qam", "A-03 v2", "--amend")
    _git(d, "worktree", "remove", "--force", wt3)
    pid3_re = trunk.patch_id(d, "feat/a-03", "main")
    ok("AC-5 setup: the content change altered the patch-id", pid3_re != pid3)
    r4 = _run_land(d, "CASE-A03", gd)
    ok("AC-5: a content-changing rebase invalidates the grant -> land.sh refuses -> "
       "the gate re-asks (fail-toward-gate, by design)",
       r4.returncode != 0 and "does not match" in r4.stderr,
       f"rc={r4.returncode} err={r4.stderr}")
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(gd, ignore_errors=True)


# ── AC-7 test:<verify_docs_parity> — ported fixtures give identical verdicts ──
def _mkrepo_docs():
    """The tron13_test lander fixture, ported verbatim (AC-7's fixture-parity clause)."""
    d = tempfile.mkdtemp(prefix="tron-0132-ac7-")
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    os.makedirs(os.path.join(d, "meta", "blocks", "archive"))
    os.makedirs(os.path.join(d, "meta", "logs"))
    os.makedirs(os.path.join(d, "src"))
    files = {
        "meta/pipeline.md": "| A-01 | logic | 📋 |\n| A-02 | ui | 📋 |\n",
        "meta/blocks/A-01.md": "# A-01\n**Status:** ✅ Done\n",
        "meta/blocks/archive/.keep": "",
        "meta/logs/.keep": "",
        "src/app.txt": "code\n",
        "README.md": "readme\n",
    }
    for p, c in files.items():
        with open(os.path.join(d, p), "w") as fh:
            fh.write(c)
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    return d


def _docs_branch(d, branch, writer):
    _git(d, "checkout", "-qb", branch)
    writer()
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "paperwork")
    _git(d, "checkout", "-q", "main")


def t_verify_docs_parity():
    ALLOW = ["meta/", "README.md"]
    DENY = ["meta/blocks/", "meta/pipeline.md"]
    # Fixture 1 (old: landed) -> ok: a clean paperwork-only branch.
    d = _mkrepo_docs()
    _docs_branch(d, "docs/close", lambda: open(
        os.path.join(d, "meta", "logs", "log-1.md"), "w").write("session log\n"))
    code, detail = trunk.verify_docs(d, "docs/close", ALLOW, "main", False, denylist=DENY)
    ok("AC-7 allow verdict: clean paperwork -> 'ok' (old land_docs would land)",
       code == "ok", f"{code}: {detail}")
    # Fixture 2 (old: violation) -> violation: code on a paperwork branch.
    def w2():
        with open(os.path.join(d, "src", "sneak.txt"), "w") as fh:
            fh.write("code\n")
        with open(os.path.join(d, "meta", "logs", "log.md"), "w") as fh:
            fh.write("log\n")
    _docs_branch(d, "docs/dirty", w2)
    code, detail = trunk.verify_docs(d, "docs/dirty", ALLOW, "main", False, denylist=DENY)
    ok("AC-7 deny verdict: code on a paperwork branch -> 'violation', same offender",
       code == "violation" and "src/sneak.txt" in detail, f"{code}: {detail}")
    # Fixture 3 (old: landed via line-scope) -> ok: own-block pipeline line + own
    # block doc via exact-file allow inside a denied dir.
    def w3():
        _git(d, "mv", "meta/blocks/A-01.md", "meta/blocks/archive/A-01.md")
        with open(os.path.join(d, "meta", "blocks", "archive", "A-01.md"), "a") as fh:
            fh.write("**Completed:** 2026-07-08\n")
        p = os.path.join(d, "meta", "pipeline.md")
        txt = open(p).read()
        open(p, "w").write(txt.replace("| A-01 | logic | 📋 |", "| A-01 | logic | ✅ |"))
    _docs_branch(d, "feat/a-01", w3)
    allow3 = ALLOW + ["meta/blocks/A-01.md", "meta/blocks/archive/A-01.md"]
    code, detail = trunk.verify_docs(d, "feat/a-01", allow3, "main", False,
                                     denylist=DENY, line_scoped={"meta/pipeline.md": "A-01"})
    ok("AC-7 line-scope verdict: own-block archival + own pipeline line -> 'ok'",
       code == "ok", f"{code}: {detail}")
    # Fixture 4 (old: violation) — IN-GRANT out-of-scope: the same line-scoped grant
    # shape, but the pipeline edit names ANOTHER block's row.
    def w4():
        p = os.path.join(d, "meta", "pipeline.md")
        txt = open(p).read()
        open(p, "w").write(txt.replace("| A-02 | ui | 📋 |", "| A-02 | ui | ✅ |"))
    _docs_branch(d, "feat/a-01-sneaky", w4)
    code, detail = trunk.verify_docs(d, "feat/a-01-sneaky", ALLOW, "main", False,
                                     denylist=DENY, line_scoped={"meta/pipeline.md": "A-01"})
    ok("AC-7 in-grant out-of-scope: a pipeline line naming ANOTHER block -> 'violation'",
       code == "violation" and "pipeline" in detail, f"{code}: {detail}")
    # Fixture 5 (old: non-ff) -> non-ff: clean content, trunk moved past the branch.
    def w5():
        with open(os.path.join(d, "meta", "logs", "log-nf.md"), "w") as fh:
            fh.write("log\n")
    _docs_branch(d, "docs/behind", w5)
    with open(os.path.join(d, "src", "app.txt"), "a") as fh:
        fh.write("moved\n")
    _git(d, "add", "-A"); _git(d, "commit", "-qm", "trunk moved")
    code, detail = trunk.verify_docs(d, "docs/behind", ALLOW, "main", False, denylist=DENY)
    ok("AC-7 non-ff verdict: clean content but trunk moved -> 'non-ff' (owner rebases)",
       code == "non-ff", f"{code}: {detail}")
    # Fixture 6 (old: none) -> none: no branch / empty diff.
    code, _d1 = trunk.verify_docs(d, "no-such-branch", ALLOW, "main", False, denylist=DENY)
    ok("AC-7 none verdict: a missing branch -> 'none'", code == "none")
    # Read-only rider: nothing verify_docs ever judged got landed or deleted.
    ok("AC-7 read-only: every judged branch still exists, untouched",
       all(trunk.branch_exists(d, b) for b in
           ("docs/close", "docs/dirty", "feat/a-01", "feat/a-01-sneaky", "docs/behind")))
    ok("AC-7 read-only: none of the paperwork reached trunk via verify_docs",
       _git(d, "show", "main:meta/logs/log-1.md")[0] != 0)
    shutil.rmtree(d, ignore_errors=True)


# ── AC-8 test:<detect_only_floor> ──
def t_detect_only_floor():
    d = _mkrepo_detached("tron-0132-ac8-")
    eng = _eng_real(d)
    arch = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
           "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
    eng.st.workers.append(arch)
    # No meta/scripts/land.sh in the project, no hook installed -> detect-only,
    # declared loudly (flow log + forensic failure + manifest flag).
    eng._declare_enforcement_mode()
    ok("AC-8: boot declares DETECT-ONLY on the manifest",
       eng.st.data.get("enforcement_mode") == "detect-only",
       f"mode={eng.st.data.get('enforcement_mode')}")
    fails = [e for e in eng.events.tail(50) if e.get("kind") == "failure"
             and e.get("code") == "detect-only-floor"] \
        if hasattr(eng.events, "tail") else []
    logged = os.path.exists(eng.ctx.event_log) and \
        "detect-only-floor" in open(eng.ctx.event_log).read()
    ok("AC-8: the declaration is LOUD — a forensic record exists (never a quiet flag)",
       logged or bool(fails), f"event_log={eng.ctx.event_log}")
    # The detection arm still catches an out-of-gate land (same shape as AC-3 arm 3).
    _, old, _ = _git(d, "rev-parse", "main")
    _, new, _ = _git(d, "rev-parse", "feat/a-01")
    _git(d, "update-ref", "refs/heads/main", new, old)
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    eng._tq = []
    eng._drive_gate("A-01", g)
    eng._drain_triggers()
    case = next((c for c in eng.st.pending_cases.values()
                if c.get("block") == "A-01"), None)
    ok("AC-8: with NO script and NO hook, the detection arm still catches the "
       "out-of-gate land (violation case, block held)",
       case is not None and "A-01" in eng.st.blocked,
       f"case={case} blocked={eng.st.blocked}")
    # And the positive arm: seat land.sh -> the mode reads prevent+detect.
    os.makedirs(os.path.join(d, "meta", "scripts"), exist_ok=True)
    shutil.copy(LAND_SH, os.path.join(d, "meta", "scripts", "land.sh"))
    eng._declare_enforcement_mode()
    ok("AC-8: seating land.sh flips the declaration to prevent+detect",
       eng.st.data.get("enforcement_mode") == "prevent+detect",
       f"mode={eng.st.data.get('enforcement_mode')}")
    shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# Review round 1 (adversarial review of PR #118): F1–F6, each with its own test(s).
# F7 (the stale module docstring) is the docstring update above — no test of its own.
# ══════════════════════════════════════════════════════════════════════════════
import util                                                # noqa: E402


def _events(eng):
    return util.read_jsonl(eng.ctx.event_log)


def _eng_on(ctx, d):
    """N1 (review round 2): wire a `Engine(ctx)` against the REAL repo `d`, non-dry —
    the same wiring `_eng_real` does, but callable MULTIPLE TIMES against the SAME
    ctx, so a test can construct several independent, fresh Engine objects over one
    persisted state file — the actual production shape (wake.py's `locked_tick` +
    daemon loop construct a brand-new `Engine(ctx)` every tick, never one long-lived
    instance, per ADR-0002 D1's deliberate stateless rebuild-from-trunk)."""
    eng = Engine(ctx)
    eng.dry = False
    eng.paths["root"] = d
    eng.paths["main_branch"] = "main"
    eng.paths["remote"] = None
    return eng


# ── F1: the per-block grantless-land detection now compares the grant's OWN
# patch-id against the patch-id of what actually landed — never bare live/consumed
# existence (the crash-window arm still authorizes on a genuine content match; a
# grant whose content does NOT match what landed is the gate-bypass violation
# shape, even though a grant record technically exists) ──
#
# N1 (review round 2, ADR-0002 D2): the round-1 version of these two tests proved F1's
# CONTENT-MATCH logic by manually stubbing `eng._trunk_sha_prev`/`eng._trunk_sha` on
# one long-lived Engine instance — which could never have caught the N1 bug (those
# attrs are reset to "" in `__init__` and production constructs a FRESH `Engine(ctx)`
# every tick, so `_trunk_sha_prev` was ALWAYS "" in reality; a hand-set attr on one
# surviving instance sails right past that). Rewritten below to prove the window
# survives the ACTUAL shape: TWO SEPARATE `Engine(ctx)` constructions sharing one
# ctx/state file, `_refresh_from_trunk()` run for real on each, never a manually
# stubbed window.
def t_f1_live_grant_content_match_authorizes_and_consumes():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    d = _mkrepo_detached("tron-0132-f1-match-")
    # Engine A: the tick that FIRST observes trunk — a real, fresh construction,
    # exactly like wake.py's first tick of a session.
    eng_a = _eng_on(ctx, d)
    eng_a.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                             "session_id": "dry", "status": "working"})
    eng_a.st.branches["A-01"] = "feat/a-01"
    eng_a._tq = []
    eng_a._refresh_from_trunk()          # persists trunk_sha_observed = old_tip
    pid = trunk.patch_id(d, "feat/a-01", "main")
    # `trunk.truth_sha` (what `_refresh_from_trunk` persists) is a SHORT sha
    # (`rev-parse --short`) — read the observation back from the engine itself
    # rather than re-deriving a full-length one that would never string-equal it.
    old_tip = eng_a.st.trunk_sha_observed
    _, branch_tip, _ = _git(d, "rev-parse", "feat/a-01")
    grants.mint(eng_a.ctx.grants_dir, "CASE-F1-OK", "A-01", "feat/a-01", pid)
    eng_a.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                      "landing_case": "CASE-F1-OK"})
    eng_a.st.save()                       # persist gate + trunk_sha_observed to disk
    ok("N1 setup: Engine A observed and durably persisted the pre-land trunk sha",
       bool(old_tip), f"observed={old_tip}")

    # Land: land.sh advances the ref but crashes BEFORE its own consume — a raw
    # update-ref (never through land.sh), grant left LIVE.
    _git(d, "update-ref", "refs/heads/main", branch_tip, old_tip)

    # Engine B: a COMPLETELY FRESH Engine(ctx) — same ctx, but NO in-memory attr
    # carries over from Engine A. Only `self.st` (re-read from disk) can supply the
    # pre-advance baseline.
    eng_b = _eng_on(ctx, d)
    ok("N1: Engine B starts with NO in-memory trunk-sha window (a truly fresh instance)",
       eng_b._trunk_sha_prev == "" and eng_b._trunk_sha == "")
    eng_b._tq = []
    eng_b._refresh_from_trunk()          # must recover old_tip from st, never from ""
    ok("N1: Engine B's own refresh recovers the DURABLE prior observation, not ''",
       eng_b._trunk_sha_prev == old_tip, f"prev={eng_b._trunk_sha_prev}")
    g = eng_b.st.gate.get("A-01")
    eng_b._drive_gate("A-01", g)
    ok("F1/N1: a LIVE grant whose content matches the observed window still "
       "authorizes the crash-window land (no false violation) — proven across TWO "
       "fresh Engine(ctx) constructions, never a manually-stubbed window",
       g.get("stage") == "trunk" and "A-01" not in eng_b.st.blocked,
       f"g={g} blocked={eng_b.st.blocked}")
    ok("F1: the grant is consumed administratively once content is confirmed",
       grants.read_consumed(eng_b.ctx.grants_dir, "CASE-F1-OK") is not None
       and grants.read_live(eng_b.ctx.grants_dir, "CASE-F1-OK") is None)
    shutil.rmtree(d, ignore_errors=True)


def t_f1_live_grant_content_mismatch_is_violation():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    d = _mkrepo_detached("tron-0132-f1-mismatch-")
    eng_a = _eng_on(ctx, d)
    eng_a.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                             "session_id": "dry", "status": "working"})
    eng_a.st.workers.append({"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
                             "status": "idle", "current_job": None, "block": None, "mbox_seq": 0})
    eng_a.st.branches["A-01"] = "feat/a-01"
    eng_a._tq = []
    eng_a._refresh_from_trunk()
    pid = trunk.patch_id(d, "feat/a-01", "main")
    # `trunk.truth_sha` (what `_refresh_from_trunk` persists) is a SHORT sha
    # (`rev-parse --short`) — read the observation back from the engine itself
    # rather than re-deriving a full-length one that would never string-equal it.
    old_tip = eng_a.st.trunk_sha_observed
    grants.mint(eng_a.ctx.grants_dir, "CASE-F1-BAD", "A-01", "feat/a-01", pid)
    eng_a.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                      "landing_case": "CASE-F1-BAD"})
    eng_a.st.save()
    ok("N1 setup: Engine A observed and durably persisted the pre-land trunk sha",
       bool(old_tip), f"observed={old_tip}")

    # SUBSTITUTE the content before it lands: amend feat/a-01 with DIFFERENT
    # content, then force-land the tampered tip via a raw update-ref (never
    # land.sh) — the still-live grant names the ORIGINAL (now-stale) patch-id.
    _git(d, "checkout", "-q", "feat/a-01")
    with open(os.path.join(d, "meta", "pipeline.md"), "w") as fh:
        fh.write("| A-01 | done |\n| A-02 | done |\n")   # sneaks A-02 done too
    _git(d, "commit", "-aqm", "A-01 done (tampered)", "--amend")
    _git(d, "checkout", "-q", "--detach", "HEAD")         # restore the detached-root seat
    _, tampered_tip, _ = _git(d, "rev-parse", "feat/a-01")
    _git(d, "update-ref", "refs/heads/main", tampered_tip, old_tip)

    # Engine B: a COMPLETELY FRESH Engine(ctx) — proves the violation is caught even
    # though NOTHING in-memory survived from Engine A's observation.
    eng_b = _eng_on(ctx, d)
    eng_b._tq = []
    eng_b._refresh_from_trunk()
    ok("N1: Engine B recovers the durable prior observation across a fresh construction",
       eng_b._trunk_sha_prev == old_tip, f"prev={eng_b._trunk_sha_prev}")
    g = eng_b.st.gate.get("A-01")
    eng_b._drive_gate("A-01", g)
    eng_b._drain_triggers()
    case = next((c for c in eng_b.st.pending_cases.values()
                if c.get("block") == "A-01"), None)
    ok("F1/N1: existing grant + substituted content landed via raw update-ref -> "
       "detected as a violation, never authorized by the grant's bare existence — "
       "proven across TWO fresh Engine(ctx) constructions",
       case is not None and "A-01" not in eng_b.st.gate, f"case={case} gate={eng_b.st.gate}")
    ok("F1: the case names the gate-bypass shape",
       bool(case) and case.get("kind") == "gate-bypass", f"case={case}")
    arch_b = next(w for w in eng_b.st.workers if w.get("role") == "architect")
    ok("F1: routed architect-first",
       (arch_b.get("current_job") or {}).get("kind") == "triage", f"arch={arch_b}")
    ok("F1: the block never closes on it (blocked, no gate)",
       "A-01" in eng_b.st.blocked, f"blocked={eng_b.st.blocked}")
    ok("F1: the stale grant is left untouched — never falsely consumed",
       grants.read_live(eng_b.ctx.grants_dir, "CASE-F1-BAD") is not None
       and grants.read_consumed(eng_b.ctx.grants_dir, "CASE-F1-BAD") is None)
    shutil.rmtree(d, ignore_errors=True)


# ── N1 (review round 2): a state file that predates `trunk_sha_observed` (or a
# genuine first-ever tick) must degrade SAFELY — adopt the current tip as baseline
# (an empty window this tick: nothing to sweep, no bypass check misfires), never
# treat the absent field as a literal "" that could misfire repeatedly. Because the
# observation is persisted immediately, the gap is a ONE-TIME event, never a
# repeating violation storm. ──
def t_n1_legacy_state_missing_field_degrades_safely_once():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    d = _mkrepo_detached("tron-0132-n1-legacy-")
    eng = _eng_on(ctx, d)
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    eng.st.branches["A-01"] = "feat/a-01"
    ok("N1 legacy: a fresh/legacy state file has no trunk_sha_observed key at all",
       "trunk_sha_observed" not in eng.st.data)
    eng._tq = []
    eng._refresh_from_trunk()
    ok("N1 legacy: the first tick with an absent field adopts the CURRENT tip as "
       "baseline (old==new) rather than leaving a bogus empty-string prev",
       eng._trunk_sha_prev == eng._trunk_sha and bool(eng._trunk_sha),
       f"prev={eng._trunk_sha_prev} new={eng._trunk_sha}")
    ok("N1 legacy: the observation is persisted immediately — the gap is ONE-TIME",
       eng.st.trunk_sha_observed == eng._trunk_sha)
    baseline = eng.st.trunk_sha_observed

    # A second tick (nothing advanced) proves the gap never repeats: the SAME
    # persisted value feeds `prev`, not another "adopt baseline" pass.
    eng._tq = []
    eng._refresh_from_trunk()
    ok("N1 legacy: the second tick has a REAL persisted prev, confirming the "
       "degrade-safely path only ever fires once",
       eng._trunk_sha_prev == baseline)
    shutil.rmtree(d, ignore_errors=True)


# ── F2: auto-settle/hold-release now exempt VIOLATION_KINDS — a plain mis-tagged
# wall still self-heals; a gate-bypass (or any GATE_GIVEUP_SPLIT_CODES) case never
# does, and the block stays held even once the row reads done ──
def t_f2_plain_wall_autosettles_on_observed_done():
    eng = _eng()
    wid = "ENG-A-01"
    eng._tq = []
    eng._h_escalate({"block": "A-01", "worker_id": wid,
                     "detail": "mis-tagged — actually done"})
    cid = next(iter(eng.st.pending_cases))
    ok("F2 setup: a plain wall case is open, undecided",
       eng.st.pending_cases[cid].get("kind") == "wall"
       and eng.st.pending_cases[cid].get("decision") is None)
    eng._on_block_done("A-01")
    ok("F2: a plain mis-tagged wall STILL auto-settles on observed-done "
       "(regression guard — F-1 self-healing survives the VIOLATION_KINDS split)",
       cid not in eng.st.pending_cases, f"cases={eng.st.pending_cases}")
    ok("F2: the hold releases too", "A-01" not in eng.st.blocked,
       f"blocked={eng.st.blocked}")


def t_f2_violation_case_never_autosettles_hold_stays():
    eng = _eng()
    wid = "ENG-A-01"
    eng._tq = []
    eng._h_escalate({"block": "A-01", "worker_id": wid,
                     "detail": "merged outside the gate (no matching grant)",
                     "code": "gate-bypass"})
    cid = next(iter(eng.st.pending_cases))
    ok("F2 setup: the case is a VIOLATION kind (gate-bypass), undecided",
       eng.st.pending_cases[cid].get("kind") == "gate-bypass"
       and eng.st.pending_cases[cid].get("decision") is None)
    ok("F2 setup: the block is held", "A-01" in eng.st.blocked)
    eng._on_block_done("A-01")
    ok("F2: the VIOLATION case survives — never auto-settled by observed-done",
       cid in eng.st.pending_cases, f"cases={eng.st.pending_cases}")
    ok("F2: the block STAYS held even though the row reads done (ADR-0002 D2)",
       "A-01" in eng.st.blocked, f"blocked={eng.st.blocked}")


# ── F3: `worktree add/remove` scoped to the scratch root STRUCTURALLY — normalize
# + reject `..` traversal, never caller convention alone ──
def t_f3_worktree_add_remove_scoped_to_scratch_root():
    d = _mkrepo("tron-0132-f3-scratch-")
    scratch = os.path.join(d, "meta", "agents", "tron", "scratch")
    os.makedirs(scratch, exist_ok=True)
    inside = os.path.join(scratch, "wt1")
    outside = os.path.join(d, "outside-wt")
    raised = False
    try:
        trunk._run(["git", "-C", d, "worktree", "add", "--detach", "-q", outside, "HEAD"],
                  scratch_root=scratch)
    except trunk.SealedAllowlistViolation:
        raised = True
    ok("F3: worktree add OUTSIDE the scratch root raises SealedAllowlistViolation", raised)
    ok("F3: the refused add never materialized a worktree", not os.path.exists(outside))

    traversal = os.path.join(scratch, "..", "..", "..", "escape-wt")
    raised2 = False
    try:
        trunk._run(["git", "-C", d, "worktree", "add", "--detach", "-q", traversal, "HEAD"],
                  scratch_root=scratch)
    except trunk.SealedAllowlistViolation:
        raised2 = True
    ok("F3: a `../` traversal trick resolving outside scratch is refused", raised2)

    okc, _, errc = trunk._run(["git", "-C", d, "worktree", "add", "--detach", "-q", inside, "HEAD"],
                              scratch_root=scratch)
    ok("F3: a scratch-scoped `worktree add --detach` is allowed", okc == 0, f"err={errc}")
    okr, _, errr = trunk._run(["git", "-C", d, "worktree", "remove", "--force", inside],
                              scratch_root=scratch)
    ok("F3: a scratch-scoped `worktree remove` is allowed", okr == 0, f"err={errr}")
    ok("F3: `worktree list` stays free regardless of scratch_root",
       trunk._subcommand_allowed(["git", "-C", d, "worktree", "list", "--porcelain"],
                                 scratch_root=scratch))
    shutil.rmtree(d, ignore_errors=True)


# ── N3 (review round 2): `_under_scratch_root` is (a) now FAIL-CLOSED — a missing
# `scratch_root` REFUSES rather than passing unconditionally — and (b) REAL, not
# lexical: both sides are realpath'd (symlinks resolved) before the containment
# compare, so a symlink physically inside scratch_root that points outside it can't
# talk its way past a bare `normpath` check either. ──
def t_n3_scratch_root_fail_closed_and_realpath():
    d = _mkrepo("tron-0132-n3-")
    scratch = os.path.join(d, "meta", "agents", "tron", "scratch")
    os.makedirs(scratch, exist_ok=True)

    # (a) NO scratch_root supplied at all -> REFUSE (fail-closed), never the old
    # unconditional pass-through.
    noroot_target = os.path.join(scratch, "wt-noroot")
    raised_missing = False
    try:
        trunk._run(["git", "-C", d, "worktree", "add", "--detach", "-q", noroot_target, "HEAD"])
    except trunk.SealedAllowlistViolation:
        raised_missing = True
    ok("N3: worktree add/remove with NO scratch_root supplied is REFUSED "
       "(fail-closed, not an unconditional pass)", raised_missing)
    ok("N3: the refused add never materialized a worktree", not os.path.exists(noroot_target))

    # (b) a symlink PHYSICALLY inside scratch_root but pointing OUTSIDE it -> refused.
    # A lexical-only check (bare os.path.normpath) never resolves the symlink and
    # would see this path as textually contained; realpath must catch it.
    outside_real = os.path.join(d, "outside-real")
    os.makedirs(outside_real, exist_ok=True)
    escape_link = os.path.join(scratch, "escape-link")
    os.symlink(outside_real, escape_link)
    target_via_symlink = os.path.join(escape_link, "wt")
    raised_symlink = False
    try:
        trunk._run(["git", "-C", d, "worktree", "add", "--detach", "-q",
                   target_via_symlink, "HEAD"], scratch_root=scratch)
    except trunk.SealedAllowlistViolation:
        raised_symlink = True
    ok("N3: a symlink INSIDE scratch_root pointing OUTSIDE it is refused "
       "(realpath, not lexical normpath alone)", raised_symlink)
    ok("N3: the refused symlink-escape add never materialized a worktree",
       not os.path.exists(os.path.join(outside_real, "wt")))

    # (c) a legitimate scratch-scoped add/remove (a real scratch_root, no symlink
    # trickery) is still allowed — the fail-closed default doesn't break the one
    # real caller.
    legit = os.path.join(scratch, "wt-legit")
    okc, _, errc = trunk._run(["git", "-C", d, "worktree", "add", "--detach", "-q",
                               legit, "HEAD"], scratch_root=scratch)
    ok("N3: a legitimate scratch-scoped worktree add is still allowed", okc == 0, f"err={errc}")
    okr, _, errr = trunk._run(["git", "-C", d, "worktree", "remove", "--force", legit],
                              scratch_root=scratch)
    ok("N3: a legitimate scratch-scoped worktree remove is still allowed", okr == 0, f"err={errr}")
    shutil.rmtree(d, ignore_errors=True)


# ── F4: a tripped seal escalates as its OWN distinct forensic kind + VIOLATION
# case, never the generic handler-raised/handler-exception bucket ──
def t_f4_sealed_allowlist_violation_escalates_distinctly():
    eng = _eng()
    arch = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
           "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
    eng.st.workers.append(arch)
    orig_route = eng._route

    def _boom(trig, slots):
        raise trunk.SealedAllowlistViolation("git subcommand refused: update-ref")
    eng._route = _boom
    try:
        eng._tq = [("some:trigger", {"block": "A-01"})]
        eng._drain_triggers()
    finally:
        eng._route = orig_route
    fails = [e for e in _events(eng) if e.get("kind") == "failure"]
    ok("F4: a tripped seal produces the DISTINCT code, never the generic "
       "'handler-exception' bucket",
       any(e.get("code") == "sealed-allowlist-tripped" for e in fails), f"fails={fails}")
    ok("F4: NOT filed as an ordinary handler-raised event",
       not any(e.get("code") == "handler-exception" for e in fails), f"fails={fails}")
    case = next((c for c in eng.st.pending_cases.values()
                if c.get("kind") == "sealed-allowlist-tripped"), None)
    ok("F4: a VIOLATION-kind case is opened for the tripped seal",
       case is not None, f"cases={eng.st.pending_cases}")
    ok("F4: routed architect-first",
       (arch.get("current_job") or {}).get("kind") == "triage", f"arch={arch}")


# ── N2 (review round 2): the F4 handler must not mint an unbounded case/architect
# job per trip — a RECURRING trip (same origin, still undecided) reuses the existing
# case; the forensic event is still recorded on EVERY trip, only the case/job MINT
# is guarded (contrast `_h_escalate`'s own `if block in self.st.blocked: return`). ──
def t_n2_sealed_allowlist_recurring_trip_mints_only_one_case():
    eng = _eng()
    arch = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
           "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
    eng.st.workers.append(arch)
    orig_route = eng._route

    def _boom(trig, slots):
        raise trunk.SealedAllowlistViolation("git subcommand refused: update-ref")
    eng._route = _boom
    try:
        eng._tq = [("some:trigger", {"block": "A-01"})]
        eng._drain_triggers()
        eng._tq = [("some:trigger", {"block": "A-01"})]   # a SECOND, recurring trip
        eng._drain_triggers()
    finally:
        eng._route = orig_route
    fails = [e for e in _events(eng) if e.get("kind") == "failure"
            and e.get("code") == "sealed-allowlist-tripped"]
    ok("N2: the forensic event is still recorded on EVERY trip, never silenced",
       len(fails) == 2, f"fails={fails}")
    cases = [c for c in eng.st.pending_cases.values()
            if c.get("kind") == "sealed-allowlist-tripped"]
    ok("N2: two consecutive trips for the SAME origin mint only ONE case (idempotent)",
       len(cases) == 1, f"cases={eng.st.pending_cases}")

    # Once the open case is DECIDED, a further trip is a genuinely NEW episode and
    # mints its own case again — the guard is against an UNDECIDED duplicate only,
    # never a permanent one-case-ever cap.
    cid = next(c for c in eng.st.pending_cases)
    eng.st.pending_cases[cid]["decision"] = "ack"
    eng._route = _boom
    try:
        eng._tq = [("some:trigger", {"block": "A-01"})]
        eng._drain_triggers()
    finally:
        eng._route = orig_route
    cases_after = [c for c in eng.st.pending_cases.values()
                  if c.get("kind") == "sealed-allowlist-tripped"]
    ok("N2: once the open case is decided, a further trip mints a fresh one "
       "(the guard targets an undecided duplicate, not a lifetime cap)",
       len(cases_after) == 2, f"cases={eng.st.pending_cases}")


# ── F5 (AC-4 update): the already-landed arm must confirm the grant's content is
# actually present, never trust bare ancestry — a regressed branch tip refuses
# loudly instead of a false "already landed, exit 0" ──
def t_f5_stale_regressed_branch_refuses_false_already_landed():
    d = _mkrepo_detached("tron-0132-f5-stale-")
    gd = tempfile.mkdtemp(prefix="tron-0132-f5-grants-")
    pid = trunk.patch_id(d, "feat/a-01", "main")
    grants.mint(gd, "CASE-STALE", "A-01", "feat/a-01", pid)
    # Regress the branch: force it back onto trunk's OWN unchanged tip — it now
    # carries NOTHING new, yet is (trivially) an ancestor of trunk.
    _git(d, "branch", "-f", "feat/a-01", "main")
    r = _run_land(d, "CASE-STALE", gd)
    ok("F5: a regressed branch tip (no new content) is REFUSED, never a false "
       "already-landed exit 0",
       r.returncode != 0, f"rc={r.returncode} out={r.stdout} err={r.stderr}")
    ok("F5: the refusal names the unconfirmed-content shape (never a silent pass)",
       "could not be confirmed" in r.stderr, f"err={r.stderr}")
    ok("F5: the grant is untouched — neither consumed nor deleted",
       grants.read_live(gd, "CASE-STALE") is not None
       and grants.read_consumed(gd, "CASE-STALE") is None,
       f"live={grants.read_live(gd, 'CASE-STALE')}")
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(gd, ignore_errors=True)


# ── F6: CASE_ID validated against a safe token pattern BEFORE any path
# interpolation ──
def t_f6_land_sh_rejects_unsafe_case_id():
    d = _mkrepo_detached("tron-0132-f6-")
    gd = tempfile.mkdtemp(prefix="tron-0132-f6-grants-")
    for bad_id in ("../../etc/passwd", "case/with/slash", "case;rm -rf", "case id"):
        r = _run_land(d, bad_id, gd)
        ok(f"F6: unsafe case id {bad_id!r} is rejected before any path use",
           r.returncode == 2 and "invalid case id" in r.stderr,
           f"rc={r.returncode} err={r.stderr}")
    ok("F6: rejecting an unsafe case id never creates anything under the grants dir",
       not os.listdir(gd) if os.path.isdir(gd) else True)
    # A safe token still works normally (regression guard).
    pid = trunk.patch_id(d, "feat/a-01", "main")
    grants.mint(gd, "CASE-OK.1_2-3", "A-01", "feat/a-01", pid)
    r = _run_land(d, "CASE-OK.1_2-3", gd)
    ok("F6: a safe case id (letters/digits/._-) still lands normally",
       r.returncode == 0, f"rc={r.returncode} err={r.stderr}")
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(gd, ignore_errors=True)


def main():
    for fn in (t_clobber_dead_real_git, t_non_ff_orders_rebase_not_wall,
              t_held_approval_never_retries_without_fresh_report,
              t_fresh_report_after_rebase_lands,
              t_unresolvable_rebase_walls_architect_with_content,
              t_wrapper_audit_no_checkout_on_cas_land,
              t_merge_ff_only_require_detached_refuses_then_succeeds,
              t_check_root_detached_opens_case_then_self_clears,
              t_carve_bootstrap_slow_worker_raises_no_case,
              t_carve_bootstrap_satisfied_stops_checking,
              t_sealed_allowlist_refuses_offlist_git,
              t_worker_lands_engine_observes,
              t_grantless_land_prevented_and_detected,
              t_grant_crash_windows,
              t_administrative_consume_first_parent_walk,
              t_concurrent_closes_cas,
              t_verify_docs_parity,
              t_detect_only_floor,
              t_f1_live_grant_content_match_authorizes_and_consumes,
              t_f1_live_grant_content_mismatch_is_violation,
              t_n1_legacy_state_missing_field_degrades_safely_once,
              t_f2_plain_wall_autosettles_on_observed_done,
              t_f2_violation_case_never_autosettles_hold_stays,
              t_f3_worktree_add_remove_scoped_to_scratch_root,
              t_n3_scratch_root_fail_closed_and_realpath,
              t_f4_sealed_allowlist_violation_escalates_distinctly,
              t_n2_sealed_allowlist_recurring_trip_mints_only_one_case,
              t_f5_stale_regressed_branch_refuses_false_already_landed,
              t_f6_land_sh_rejects_unsafe_case_id):
        fn()
    bad = [r for r in _results if not r[1]]
    for name, good, detail in _results:
        print(f"  [{'PASS' if good else 'FAIL'}] {name}" + (f" — {detail}" if detail and not good else ""))
    print(f"block_01_32_test: {'PASS' if not bad else 'FAIL'} ({len(_results)-len(bad)}/{len(_results)})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
