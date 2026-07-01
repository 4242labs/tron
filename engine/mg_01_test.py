"""mg_01_test — merge-gate integrity acceptance (AC-3, AC-4, AC-5).

Deterministic, token-free (TRON_DRY): reuses sentry_test's fixture builders and drives
the engine's deterministic gate units directly. Exit 0 only if every case passes.

Covers:
  AC-3  a block whose commits already reached trunk with no PR for the gate to have seen
        (an out-of-gate merge) advances past `local` — straight to `trunk` re-validate, or
        (while a merge hold was pending) escalates the bypass instead of silently accepting it
  AC-4  a gate with no worker activity signal escalates after `gate_idle_cap` ticks (no hang)
  AC-5  a block stamped `Merge approval: needs-user` holds the merge stage on the operator,
        even when the global ask-before-merging knob is off (APPROVED)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import util             # noqa: E402
import trunk            # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _eng(block="A-01"):
    ctx, _ = build(blocks=[(block, "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _stamp_merge_approval(repo, block, value):
    """Rewrite the fixture block file's header field in place."""
    path = os.path.join(repo, "meta", "blocks", f"{block}.md")
    with open(path) as fh:
        text = fh.read()
    text = text.replace("**Merge approval:** auto", f"**Merge approval:** {value}")
    util.atomic_write(path, text)


# ── AC-3: trunk is the only done-truth — an out-of-gate merge is never silently accepted ──
def t_already_merged_skips_local():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
    orig = trunk.branch_merged
    trunk.branch_merged = lambda *a, **k: True
    try:
        eng._drive_gate("A-01", g)
    finally:
        trunk.branch_merged = orig
    ok("AC-3 already-merged branch skips local -> trunk re-validate", g.get("stage") == "trunk")


def t_bypass_during_pending_hold_escalates():
    eng = _eng()
    # Simulate a merge hold that was already parked (case_merge set, not yet approved/self-merged)
    # when the block's branch turns out to have reached trunk anyway — the exact defect: a merge
    # that happened outside the gate while an ASK hold was pending.
    g = eng.st.gate.setdefault("A-01", {"stage": "merge", "pr": None, "case_merge": "CASE-1"})
    orig = trunk.branch_merged
    trunk.branch_merged = lambda *a, **k: True
    try:
        eng._tq = []
        eng._drive_gate("A-01", g)
    finally:
        trunk.branch_merged = orig
    walled = any(t.startswith("wall:raised:A-01") for t, _ in eng._tq)
    ok("AC-3 out-of-gate merge during a pending hold escalates (not silently accepted)",
       walled and "A-01" not in eng.st.gate)


# ── AC-4: universal gate idle-timeout — no worker activity, no silent hang ──
def t_idle_gate_escalates():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
    eng._drive_gate("A-01", g)                          # None -> local (first advance)
    ok("AC-4 first pass parks at local", g.get("stage") == "local")
    cap = int(eng.knobs.get("gate_idle_cap", 3))
    for _ in range(cap - 1):
        eng._tq = []
        eng._drive_gate("A-01", eng.st.gate.get("A-01", g))
    ok("AC-4 still local before the cap is exceeded (not yet escalated)",
       eng.st.gate.get("A-01", {}).get("stage") == "local")
    eng._tq = []
    eng._drive_gate("A-01", eng.st.gate.get("A-01", g))  # cap exceeded -> escalate
    walled = any(t.startswith("wall:raised:A-01") for t, _ in eng._tq)
    ok("AC-4 escalates after gate_idle_cap ticks of no worker activity",
       walled and "A-01" not in eng.st.gate)


def t_idle_reset_on_advance():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
    eng._drive_gate("A-01", g)                          # None -> local
    eng._drive_gate("A-01", g)                           # local -> local (1 idle tick)
    ok("AC-4 idle_ticks accrues while stalled", g.get("idle_ticks", 0) == 1)
    eng.st.data["open_prs"] = {"feat/A-01": {"number": 7, "checks": "passing"}}
    eng._drive_gate("A-01", g)                          # local -> merge (a real advance)
    ok("AC-4 idle_ticks resets on a real stage advance",
       g.get("stage") == "merge" and g.get("idle_ticks", 0) == 0)


# ── AC-5: `Merge approval: needs-user` holds the merge stage on the operator ──
def t_needs_user_holds_regardless_of_global_knob():
    ctx, repo = build(blocks=[("A-01", "🔄", "none")])
    _stamp_merge_approval(repo, "A-01", "needs-user")
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    ok("AC-5 fixture: block reads merge_approval needs-user",
       eng._block_merge_approval("A-01") == "needs-user")
    ok("AC-5 fixture: global ask-before-merging is off (APPROVED)",
       eng.st.approvals.get("merge", "APPROVED") == "APPROVED")
    eng.st.data["open_prs"] = {"feat/A-01": {"number": 7, "checks": "passing"}}
    g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
    eng._drive_gate("A-01", g)
    case_id = next((cid for cid, c in eng.st.pending_cases.items()
                    if c.get("kind") == "merge"), None)
    ok("AC-5 needs-user parks an operator case at the trunk-merge step",
       case_id is not None and g.get("stage") != "trunk")


def main():
    for t in (t_already_merged_skips_local, t_bypass_during_pending_hold_escalates,
              t_idle_gate_escalates, t_idle_reset_on_advance,
              t_needs_user_holds_regardless_of_global_knob):
        t()
    bad = [r for r in _results if not r[1]]
    for name, good, detail in _results:
        print(f"  [{'PASS' if good else 'FAIL'}] {name}" + (f" — {detail}" if detail and not good else ""))
    print(f"mg_01_test: {'PASS' if not bad else 'FAIL'} ({len(_results)-len(bad)}/{len(_results)})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
