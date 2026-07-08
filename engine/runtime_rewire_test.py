"""runtime_rewire_test — block 01-08 acceptance suite (AC-5/6/8/11/12).

Token-free, deterministic (TRON_DRY via sentry_test). Drives the worker-prompt-runtime
rewire's deterministic units directly:
  AC-5   architect reconcile is its own job (arch.reconcile{block, after}) vs forward
         (arch.forward{block}); reconcile targets only a dispatchable (not in-flight) block.
  AC-6   arch.triage carries the sender + a built detail (prefix only for a real-block worker).
  AC-8   the reviewer's assignment is the commit range since its last review; marker resets on dispatch.
  AC-11  a gate step that fails past the cap escalates to the operator (T9).
  AC-12  worker.question_peer routes to the architect; architect.relay / architect.escalate exist
         and resolve (relay to the asker / raise to the operator).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trunk                                   # noqa: E402
from fsm import Engine                         # noqa: E402
from sentry_test import build, started, events  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── AC-5: forward vs reconcile jobs + dispatchable-only reconcile target ──
def t_arch_jobs():
    ctx, _ = build(blocks=[("A-01", "📋", "none"), ("A-02", "📋", "none")])
    eng = Engine(ctx); started(eng); eng._spawn_architect()

    n = len(events(ctx))
    eng.st.architect_queue.append({"kind": "reconcile", "block": "A-02", "after": "A-01"})
    eng._pump_architect()
    ev = events(ctx)[n:]
    ok("AC-5 reconcile emits arch.reconcile{block, after}",
       any("A-01" in t and "A-02" in t for t in ev))

    eng._architect_advance()                   # free the architect for the next job
    n = len(events(ctx))
    eng.st.architect_queue.append({"kind": "forward", "block": "A-02"})
    eng._pump_architect()
    ev = events(ctx)[n:]
    ok("AC-5 forward emits arch.forward{block} (scope), not reconcile",
       any("scope A-02" in t for t in ev) and not any("just landed" in t for t in ev))


def t_reconcile_target_dispatchable():
    ctx, _ = build(blocks=[("A-01", "📋", "none"), ("A-02", "🔄", "none"), ("A-03", "📋", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-A-02", "role": "engineer", "block": "A-02",
                           "session_id": "dry", "status": "working"})        # A-02 mid-execution
    tgt = eng._next_reconcile_target("A-01")
    ok("AC-5 reconcile skips an in-flight block, targets the next clean one", tgt == "A-03")


# ── AC-6: triage carries sender + a built detail ──
def t_triage_detail():
    ctx, _ = build(blocks=[("A-01", "📋", "none")])
    eng = Engine(ctx); started(eng)
    d1 = eng._triage_detail({"detail": "how do I X?", "sender": "ENG-A-01", "block": "A-01"})
    ok("AC-6 real-block worker -> 'sender, on block X:' prefix",
       d1 == "ENG-A-01, on block A-01: how do I X?")
    d2 = eng._triage_detail({"detail": "finding", "sender": "REV-code", "block": "review:code"})
    ok("AC-6 review:* sender -> raw text, no prefix", d2 == "finding")
    d3 = eng._triage_detail({"detail": "hi", "sender": "ENG-A-01", "block": None})
    ok("AC-6 no block -> raw text, no prefix", d3 == "hi")


# ── AC-8: reviewer reviews the since-last-review range; marker resets on dispatch ──
def t_review_marker():
    ctx, _ = build(blocks=[("A-01", "📋", "none")])
    eng = Engine(ctx); started(eng)
    # T2 (01-32, ADR-0002 D1): _reviewer_assignment reads trunk.truth_sha (the mode's
    # truth ref), never trunk.head_sha, now that a detached local-mode root's literal
    # HEAD no longer tracks trunk's position — stub the seam the engine actually calls.
    orig = trunk.truth_sha
    trunk.truth_sha = lambda *a, **k: "sha1"
    try:
        a1 = eng._reviewer_assignment("code")
        ok("AC-8 marker reset to HEAD on first dispatch", eng.st.review_markers.get("code") == "sha1")
        ok("AC-8 first review covers full history (no prior marker)", "no prior" in a1)
        trunk.truth_sha = lambda *a, **k: "sha2"
        a2 = eng._reviewer_assignment("code")
        ok("AC-8 second review covers the range since the last marker", "sha1..sha2" in a2)
        ok("AC-8 marker advanced to the new HEAD", eng.st.review_markers.get("code") == "sha2")
    finally:
        trunk.truth_sha = orig


# ── AC-11: a gate step that fails past the cap escalates (T9) ──
def t_failure_cap():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    cap = int(eng.knobs.get("gate_step_cap", 2))
    walled = False
    for _ in range(cap + 2):                    # repeated 'done' with no PR -> stuck at 'local'
        eng._tq = []
        eng._h_worker_done({"block": "A-01"})
        if any(t.startswith("wall:raised:A-01") for t, _ in eng._tq):
            walled = True
    ok("AC-11 a gate step failing past the cap escalates to the operator", walled)
    ok("AC-11 escalation drops the gate (no silent re-prompt loop)", "A-01" not in eng.st.gate)


# ── AC-12: questions never dead-end — peer routes to architect; relay/escalate resolve ──
def t_question_peer_routes():
    ctx, _ = build(blocks=[("A-01", "📋", "none")])
    eng = Engine(ctx); started(eng); eng._spawn_architect()
    eng._ingest("worker.question_peer", {"detail": "which pattern?", "block": "A-01"},
                {"id": "ENG-A-01"})
    jobs_seen = list(eng.st.architect_queue)
    cur = eng._architect().get("current_job")
    if cur:
        jobs_seen.append(cur)
    triage = next((j for j in jobs_seen if (j or {}).get("kind") == "triage"), None)
    ok("AC-12 question_peer routes to the architect (a triage job)", triage is not None)
    ok("AC-12 the triage job carries the asker as sender",
       (triage or {}).get("sender") == "ENG-A-01")
    tags = eng.routing.get("tags", {})
    ok("AC-12 architect.relay + architect.escalate exist in the closed enum",
       "architect.relay" in tags and "architect.escalate" in tags)


def t_relay_and_escalate():
    ctx, _ = build(blocks=[("A-01", "📋", "none")])
    eng = Engine(ctx); started(eng); eng._spawn_architect()
    # relay: architect answers a triaged question -> advances the architect (job done).
    eng.st.architect_queue.append({"kind": "triage", "detail": "q", "sender": "ENG-A-01",
                                   "block": "A-01"})
    eng._pump_architect()
    eng._ingest("architect.relay", {"detail": "use a registry"}, {"id": "ARCH-PERSIST"})
    ok("AC-12 architect.relay advances the architect (triage resolved)",
       eng._architect().get("current_job") is None)
    # escalate: architect judges it the operator's call -> raise on the wall edge.
    eng.st.architect_queue.append({"kind": "triage", "detail": "q2", "sender": "ENG-A-01",
                                   "block": "A-01"})
    eng._pump_architect()
    eng._tq = []
    eng._ingest("architect.escalate", {"detail": "operator's call"}, {"id": "ARCH-PERSIST"})
    ok("AC-12 architect.escalate raises to the operator (wall edge)",
       any(t.startswith("wall:raised:A-01") for t, _ in eng._tq))


def main():
    for t in (t_arch_jobs, t_reconcile_target_dispatchable, t_triage_detail,
              t_review_marker, t_failure_cap, t_question_peer_routes, t_relay_and_escalate):
        t()
    bad = [r for r in _results if not r[1]]
    for name, good, detail in _results:
        print(f"  [{'PASS' if good else 'FAIL'}] {name}" + (f" — {detail}" if detail and not good else ""))
    print(f"runtime_rewire_test: {'PASS' if not bad else 'FAIL'} ({len(_results)-len(bad)}/{len(_results)})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
