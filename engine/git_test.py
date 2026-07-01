"""git_test — the 01-05 merge + git hygiene acceptance suite (AC-1 … AC-3).

Deterministic, token-free (TRON_DRY): no git, no spawn, no LLM. Reuses sentry_test's
fixture builders (a throwaway TRON dir + a fixture canon repo) and drives the engine's
deterministic merge-gate units directly. Exit 0 only if every case passes.

Covers:
  AC-1   the worker gate ends at trunk — CI green -> one merge-to-trunk step (no promote/prod)
  AC-2   agent-owned branch: TRON resolves the PR by the worker-REPORTED name, never feat/<block>
  AC-10  ask-before-merging — one control, four operator outcomes (01-08 T8)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

from fsm import Engine                       # noqa: E402
from sentry_test import build, started, events  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _eng(staging="none", block="A-01"):
    """An engine with one engineer on `block`, optionally two-gate (staging set)."""
    ctx, _ = build(blocks=[(block, "📋", "none")])
    eng = Engine(ctx); started(eng)
    eng.paths["staging"] = staging
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


# ── AC-2: the agent owns + names its branch; TRON resolves the PR by that name ──
def t_branch_ownership():
    eng = _eng()
    named = "fix/widget-overflow-260628"        # NOT the feat/<block> convention
    eng._ingest("worker.branch", {"block": "A-01", "branch": named}, {"id": "ENG-A-01"})
    ok("AC-2 worker.branch records the worker-named branch",
       eng.st.branches.get("A-01") == named)
    ok("AC-2 branch is NOT a guessed feat/<block>", named != eng._branch("A-01"))

    # A PR exists ONLY under the reported name. The gate must find it there (not feat/A-01).
    eng.st.data["open_prs"] = {named: {"number": 11, "checks": "passing"}}
    g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
    eng._drive_gate("A-01", g)
    ok("AC-2 gate resolves the PR via the reported branch -> merge",
       g["stage"] == "merge" and g.get("pr") == 11)

    # Control: a PR under the GUESSED name with NO report is ignored (TRON never guesses).
    eng2 = _eng(block="A-02")
    eng2.st.data["open_prs"] = {"feat/A-02-wrongguess": {"number": 9, "checks": "passing"}}
    g2 = eng2.st.gate.setdefault("A-02", {"stage": None, "pr": None})
    eng2._drive_gate("A-02", g2)
    ok("AC-2 unreported branch -> no guess, stays local",
       g2["stage"] == "local")


# ── AC-1: the worker gate ends at trunk — CI green -> one merge-to-trunk step (no promote) ──
def t_single_gate():
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    eng.st.data["open_prs"] = {"feat/A-01": {"number": 7, "checks": "passing"}}
    g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
    eng._drive_gate("A-01", g)
    ok("AC-1 default APPROVED: CI green -> one merge-to-trunk step", g["stage"] == "merge")
    ok("AC-1 default APPROVED raised no merge-gate case", not eng.st.pending_cases)


# ── AC-10: ask-before-merging — one control, four operator outcomes (01-08 T8) ──
def t_ask_before_merging():
    def fresh():
        eng = _eng()
        eng.st.branches["A-01"] = "feat/A-01"
        eng.st.approvals["merge"] = "ASK"                      # ask-before-merging ON
        eng.st.data["open_prs"] = {"feat/A-01": {"number": 7, "checks": "passing"}}
        g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
        eng._drive_gate("A-01", g)
        return eng, g

    # ASK parks ONE operator case at the trunk-merge step and holds (no merge instruction).
    eng, g = fresh()
    case_id = next((cid for cid, c in eng.st.pending_cases.items()
                    if c.get("kind") == "merge"), None)
    ok("AC-10 ASK parks one merge case at the trunk-merge step", case_id is not None)

    # 1. Approve -> agent merges (gate grants the merge).
    eng, g = fresh()
    cid = next(c for c in eng.st.pending_cases)
    eng._h_apply_decision({"case": cid, "decision": "approve", "block": "A-01"})
    ok("AC-10 approve -> merge granted, agent merges",
       g.get("approved_merge") is True and cid not in eng.st.pending_cases)

    # 2. I'll merge it myself -> agent skips merge, resumes at DONE-TRUNK.
    eng, g = fresh()
    cid = next(c for c in eng.st.pending_cases)
    eng._h_apply_decision({"case": cid, "decision": "self", "block": "A-01"})
    ok("AC-10 self-merge -> agent resumes at trunk stage",
       g.get("self_merge") is True and g.get("stage") == "trunk")

    # 3. Changes requested -> notes relayed; the gate holds for rework (not approved).
    eng, g = fresh()
    cid = next(c for c in eng.st.pending_cases)
    eng._h_apply_decision({"case": cid, "decision": "changes", "block": "A-01",
                           "detail": "rename the flag"})
    ok("AC-10 changes-requested -> awaiting rework, not approved, case closed",
       g.get("awaiting_rework") is True and not g.get("approved_merge")
       and cid not in eng.st.pending_cases)

    # 4. Drop -> block dropped at the merge moment, slot freed.
    eng, g = fresh()
    cid = next(c for c in eng.st.pending_cases)
    eng._h_apply_decision({"case": cid, "decision": "drop", "block": "A-01"})
    ok("AC-10 drop -> block dropped, gate cleared, slot freed",
       "A-01" in eng._dropped() and "A-01" not in eng.st.gate
       and not any(w.get("block") == "A-01" for w in eng.st.workers))


# ── 01-07: two-step dispatch — SPAWN (identity) then ASSIGN (work) on `online` ──
def t_two_step_engineer():
    ctx, _ = build(blocks=[("A-01", "📋", "none")])
    eng = Engine(ctx); started(eng)
    # SPAWN copy itself is identity-only (the prompt is the spawn process input, not an emit).
    spawn_copy = eng.renderer.render(
        "spawn.engineer", {"worker_id": "ENG-A-01", "role": "engineer",
                           "persona": "/p/engineer.md", "report": "/s/report.sh"})
    ok("two-step: SPAWN copy is identity-only (online check-in, no assignment)",
       "online" in spawn_copy.lower() and "acceptance criteria" not in spawn_copy.lower()
       and "/p/engineer.md" in spawn_copy and "/s/report.sh" in spawn_copy)

    n0 = len(events(ctx))
    eng._dispatch_engineer("A-01")
    spawn_ev = events(ctx)[n0:]
    w = next(x for x in eng.st.workers if x.get("role") == "engineer")
    pa = w.get("pending_assign") or {}
    ok("two-step: spawn records a pending engineer assignment",
       pa.get("kind") == "engineer" and pa.get("block") == "A-01" and pa.get("assignment"))
    ok("two-step: dispatch emits no assignment (work waits for online)",
       not any("Read its spec" in t for t in spawn_ev))

    n1 = len(events(ctx))
    eng._h_worker_online({"worker_id": w["id"]})
    assign_ev = events(ctx)[n1:]
    ok("two-step: online clears the pending assignment", w.get("pending_assign") is None)
    ok("two-step: online emits assign.engineer carrying the block",
       any("A-01" in t and "spec" in t.lower() for t in assign_ev))


def t_two_step_reviewer():
    ctx, _ = build(blocks=[("A-01", "📋", "none")])
    eng = Engine(ctx); started(eng)
    eng.cadence_cfg = {"code": 3}
    eng._dispatch_reviewer("code")
    w = next(x for x in eng.st.workers if x.get("role") == "reviewer")
    ok("two-step: reviewer spawn records a pending reviewer assignment",
       (w.get("pending_assign") or {}).get("kind") == "reviewer")
    n1 = len(events(ctx))
    eng._h_worker_online({"worker_id": w["id"]})
    assign_ev = events(ctx)[n1:]
    ok("two-step: reviewer online clears the pending assignment", w.get("pending_assign") is None)
    ok("two-step: reviewer online emits assign.reviewer (findings pass)",
       any("findings" in t.lower() for t in assign_ev))


def t_two_step_architect_noop():
    # The architect spawns identity-only too (PMT-SPAWN) but carries NO pending assignment —
    # its jobs arrive via the queue/pump. An `online` report from it is a harmless no-op (AC-5).
    ctx, _ = build(blocks=[("A-01", "📋", "none")])
    eng = Engine(ctx); started(eng)
    eng._spawn_architect()
    arch = eng._architect()
    ok("two-step: architect spawn carries no pending assignment",
       arch is not None and arch.get("pending_assign") is None)
    n1 = len(events(ctx))
    eng._h_worker_online({"worker_id": arch["id"]})
    ok("two-step: architect online emits no assignment",
       not any("acceptance criteria" in t.lower() or "findings" in t.lower()
               for t in events(ctx)[n1:]))


# ── local mode (no remote): the ENGINE owns the trunk merge — ff-only, ASK-gated ──
# These cover the DECISION logic under TRON_DRY (no git): the block branch is taken to exist
# (branch_exists stubbed True) and the ff-merge to succeed (dry) — the REAL git ff-merge, non-ff
# refusal, and branch-existence are proven against a live repo in the real-git suite.
import trunk as _trunk


def _stub_branch(exists=True, ff=(True, "")):
    _trunk.branch_exists = lambda *a, **k: exists
    _trunk.merge_ff_only = lambda *a, **k: ff


def t_local_merge_no_remote():
    orig = (_trunk.branch_exists, _trunk.merge_ff_only)
    _stub_branch()
    try:
        eng = _eng()                                        # _eng fixture declares no remote
        eng.st.branches["A-01"] = "feat/A-01"
        g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
        eng._drive_gate("A-01", g)                          # first pass: no PR -> request local validation
        ok("local: no PR -> first pass requests local validation", g["stage"] == "local")
        eng._drive_gate("A-01", g, on_report=True)          # evidence back, default APPROVED -> ff-merge
        ok("local: validated -> engine ff-merges -> re-validate on trunk", g["stage"] == "trunk")
        ok("local: default APPROVED raised no merge case", not eng.st.pending_cases)
    finally:
        _trunk.branch_exists, _trunk.merge_ff_only = orig


def t_local_merge_ask_gated():
    orig = (_trunk.branch_exists, _trunk.merge_ff_only)
    _stub_branch()
    try:
        eng = _eng()
        eng.st.branches["A-01"] = "feat/A-01"
        eng.st.approvals["merge"] = "ASK"                   # ask-before-merging ON
        g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
        eng._drive_gate("A-01", g)                          # -> local
        eng._drive_gate("A-01", g, on_report=True)          # evidence -> ASK parks, does NOT merge
        ok("local ASK: parks a merge case, holds at local (no merge)",
           g["stage"] == "local"
           and any(c.get("kind") == "merge" for c in eng.st.pending_cases.values()))
        eng._drive_gate("A-01", g)                          # tick while parked -> hold quietly
        ok("local ASK: parked tick holds quietly (gate not given up)",
           "A-01" in eng.st.gate and g["stage"] == "local")
        cid = next(c for c in eng.st.pending_cases)
        eng._h_apply_decision({"case": cid, "decision": "approve", "block": "A-01"})
        ok("local ASK: approve -> engine ff-merges -> trunk",
           g.get("approved_merge") is True and g["stage"] == "trunk")
    finally:
        _trunk.branch_exists, _trunk.merge_ff_only = orig


def t_local_merge_non_ff():
    # A non-ff (trunk moved under the branch) never fabricates a merge commit: the gate re-nudges
    # the worker to rebase and retry, and stays at local.
    orig = (_trunk.branch_exists, _trunk.merge_ff_only)
    _stub_branch(ff=(False, "not a fast-forward"))
    try:
        eng = _eng()
        eng.st.branches["A-01"] = "feat/A-01"
        g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
        eng._drive_gate("A-01", g)                          # -> local
        eng._drive_gate("A-01", g, on_report=True)          # ff refused -> rebase + retry, no force
        ok("local non-ff: stays at local for rebase, never force-merges", g["stage"] == "local")
    finally:
        _trunk.branch_exists, _trunk.merge_ff_only = orig


def t_local_merge_no_branch():
    # No block branch exists yet (branch_exists False) => nothing to merge: the gate stays at
    # local and never fabricates a merge — the AC-11 stall/escalate path is preserved.
    orig = _trunk.branch_exists
    _trunk.branch_exists = lambda *a, **k: False
    try:
        eng = _eng()
        eng.st.branches["A-01"] = "feat/A-01"
        g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
        eng._drive_gate("A-01", g)
        eng._drive_gate("A-01", g, on_report=True)          # branch absent -> no merge attempt
        ok("local no-branch: stays at local, no merge, no case", g["stage"] == "local"
           and not eng.st.pending_cases)
    finally:
        _trunk.branch_exists = orig


def main():
    for t in (t_branch_ownership, t_single_gate, t_ask_before_merging,
              t_local_merge_no_remote, t_local_merge_ask_gated, t_local_merge_non_ff,
              t_local_merge_no_branch,
              t_two_step_engineer, t_two_step_reviewer,
              t_two_step_architect_noop):
        t()
    bad = [r for r in _results if not r[1]]
    for name, good, detail in _results:
        print(f"  [{'PASS' if good else 'FAIL'}] {name}" + (f" — {detail}" if detail and not good else ""))
    print(f"git_test: {'PASS' if not bad else 'FAIL'} ({len(_results)-len(bad)}/{len(_results)})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
