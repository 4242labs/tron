"""sentry_test — the 01-03 SENTRY-engine acceptance suite (AC-3 … AC-11).

Deterministic, token-free: TRON_DRY stubs every side effect (no git, no spawn, no
LLM). Each case builds a throwaway TRON dir + a fixture canon repo (pipeline.md +
block files) so the real reader/refresh path runs, then drives the engine's
deterministic units directly. Exit 0 only if every case passes.

Covers: DONE gate (AC-3), bootup gateway + B12 (AC-4), escalation correlation
(AC-5), await ladder (AC-6), trunk-refresh fail-loud (AC-7), no-silent-stuck
(AC-8), reconcile trigger/gate (AC-9), plumbing nits (AC-10), run-control (AC-11).
"""
import os
import sys
import atexit
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"
# 01-21 T1: jobs.spawn_runner now fails closed without a resolved worker model. Most of
# the suite stays dry (never reaches it), but several cases deliberately flip
# `eng.dry = False` for one narrow real-send path and can collaterally trigger a real
# SWITCHBOARD dispatch in the same tick. This is the same override knob RUNTIME/ADAPTER
# already have — never a real model (these ticks never reach a real runtime either).
os.environ.setdefault("TRON_WORKER_MODEL", "test-model")

import util            # noqa: E402
import reader          # noqa: E402
import trunk           # noqa: E402
import jobs            # noqa: E402
from ctx import Ctx    # noqa: E402
from fsm import Engine  # noqa: E402

NOW = "2026-06-28T00:00:00Z"
_results = []

# 01-21 test-hygiene: a few cases across the suite flip `eng.dry = False` for a narrow
# real-send path and collaterally trigger a real SWITCHBOARD dispatch — spawning a real
# `worker_runner` OUTSIDE the FSM start()/wake.run() lifecycle the engine's own reaper
# (jobs.reap_all) guards, so it would otherwise linger orphaned after the test process
# exits. Every `build()` store is registered here and group-reaped at process exit — no
# test leaks a worker. (Now harmless in cost too: TRON_WORKER_MODEL pins the model, and
# these ticks never reach a real runtime — but a leaked process is still a leak.)
_reap_stores = set()
_reap_registered = False


def _reap_test_workers():
    for wd in list(_reap_stores):
        try:
            jobs.configure(wd)
            jobs.reap_all()
        except Exception:
            pass


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── fixture builders ──
def _block_md(bid, status="📋", deps="none", deploy="none"):
    return (f"# Block {bid}: test {bid}\n"
            f"**Phase:** Phase 1: Test\n**Status:** {status}\n"
            f"**Depends on:** {deps}\n**Reviewer class:** code\n"
            f"**Merge approval:** auto\n**Deploy:** {deploy}\n\n---\n\n## Body\n")


def build(blocks=None, scope=None):
    """blocks: list of (id, status, deploy). Returns (ctx, repo_root)."""
    blocks = blocks if blocks is not None else [("A-01", "📋", "none"),
                                                ("A-02", "📋", "none"),
                                                ("A-03", "📋", "none")]
    d = tempfile.mkdtemp(prefix="tron-sentry-")
    for f in ("routing.yaml", "messages.yaml", "knobs.yaml", "tron.md"):
        shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
    shutil.copytree(os.path.join(ROOT, "prompts"), os.path.join(d, "prompts"))
    repo = os.path.join(d, "repo")
    bdir = os.path.join(repo, "meta", "blocks")
    os.makedirs(bdir)
    util.save_yaml(os.path.join(d, "project.yaml"),
                   {"repo": {"root": repo, "main_branch": "main", "staging": "none"},
                    "pipeline_path": "meta/pipeline.md", "blocks_dir": "meta/blocks/"})
    util.atomic_write(os.path.join(d, "manifest.yaml"), "{}\n")
    rows = ["## Roadmap", "### Phase 1: Test", "| ID | Task | Status | Notes |",
            "|:--|:--|:--|:--|"]
    for bid, status, deploy in blocks:
        rows.append(f"| {bid} | t | {status} | Block `blocks/{bid}.md` |")
        util.atomic_write(os.path.join(bdir, f"{bid}.md"),
                          _block_md(bid, status, deploy=deploy))
    util.atomic_write(os.path.join(repo, "meta", "pipeline.md"), "\n".join(rows) + "\n")
    ctx = Ctx(d)
    global _reap_registered
    _reap_stores.add(ctx.workers_dir)
    if not _reap_registered:
        atexit.register(_reap_test_workers)
        _reap_registered = True
    if scope:
        util.save_yaml(ctx.state, {"scope": scope})
    return ctx, repo


def started(eng):
    eng.st.data["session"] = {"started_at": NOW}
    eng.st.live_config["worker_count"] = 2
    eng._refresh_from_trunk(count=False)


def events(ctx):
    return [e.get("text", "") for e in util.read_jsonl(ctx.home_log)]


# ── AC-7: trunk-refresh fail-loud ──
def t_failloud():
    orig = trunk.refresh
    trunk.refresh = lambda *a, **k: (False, "boom")
    try:
        # bootup: a single failure halts loud at once (no MANIFEST yet, A2).
        ctx, _ = build()
        eng = Engine(ctx)
        eng.start(2)
        ok("AC-7 bootup halts loud on dead trunk",
           eng.ended and any("trunk" in t.lower() for t in events(ctx)))
        # ticks: tolerate up to the death-cap, then halt loud — never silent.
        ctx2, _ = build()
        eng2 = Engine(ctx2)
        eng2.st.data["session"] = {"started_at": NOW}
        eng2.st.save()
        e1 = Engine(ctx2); e1.tick()
        e2 = Engine(ctx2); e2.tick()
        mid = Engine(ctx2).ended
        e3 = Engine(ctx2); halted = e3.tick()
        ok("AC-7 ticks halt loud at death-cap, not before",
           (not mid) and halted and Engine(ctx2).st.run_control == "halt")
    finally:
        trunk.refresh = orig


# ── AC-4: bootup gateway + B12 ──
def t_bootup():
    # empty pipeline -> plan-first, no agents, clean end.
    ctx, _ = build(blocks=[])
    eng = Engine(ctx); eng.start(2)
    ok("AC-4 empty pipeline -> plan-first exit, no architect",
       eng.ended and not eng._architect()
       and any("empty" in t.lower() or "plan first" in t.lower() for t in events(ctx)))
    # scope typo -> refused.
    ctx2, _ = build(scope={"mode": "range", "value": ["A-01", "ZZ-99"]})
    eng2 = Engine(ctx2)
    started_view = Engine(ctx2)
    started_view.st.data["session"] = {}
    eng2._refresh_from_trunk(count=False)
    ok("AC-4 scope typo detected", eng2._bootup_gateway() == "scope-typo")
    # legitimate (range present) -> proceeds.
    ctx3, _ = build(scope={"mode": "range", "value": ["A-01", "A-03"]})
    eng3 = Engine(ctx3); eng3._refresh_from_trunk(count=False)
    ok("AC-4 valid scope proceeds", eng3._bootup_gateway() is None)
    # B12 — re-running bootup (after a crash mid-bootup) is idempotent: one architect.
    ctx4, _ = build()
    Engine(ctx4).start(2)
    Engine(ctx4).start(2)            # second run as if the first crashed mid-bootup
    archs = [w for w in Engine(ctx4).st.workers if w.get("role") == "architect"]
    ok("AC-4/B12 re-run bootup idempotent (exactly one architect)", len(archs) == 1, f"got {len(archs)}")


# ── AC-3/AC-7: DONE gate — LOCAL -> MERGE -> TRUNK -> CLOSE on evidence (01-08 T5/T7) ──
def t_done_gate():
    ctx, _ = build(blocks=[("A-01", "📋", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    # no PR yet -> local (DONE-LOCAL), never ✅ on a bare claim.
    g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
    eng._drive_gate("A-01", g)
    ok("AC-3 no PR -> local (DONE-LOCAL) stage", g["stage"] == "local")
    ok("AC-3 never marks done from a claim",
       eng.st.row("A-01").get("status") != "done")
    # PR open + CI green -> merge (DONE-MERGE) stage (CI auto-deploys staging).
    eng.st.data["open_prs"] = {"feat/A-01": {"number": 7, "checks": "passing"}}
    eng._drive_gate("A-01", g)
    ok("AC-3 CI green -> merge (DONE-MERGE) stage", g["stage"] == "merge")
    # PR merged (gone), not ✅ -> trunk (DONE-TRUNK) re-validate.
    eng.st.data["open_prs"] = {}
    eng._drive_gate("A-01", g)
    ok("AC-3 PR merged, not ✅ -> trunk (DONE-TRUNK) stage", g["stage"] == "trunk")
    # ✅ on trunk -> close (CLOSE); the slot is HELD (worker NOT released until it confirms clean).
    eng.st.row("A-01")["status"] = "done"
    eng._drive_gate("A-01", g)
    ok("AC-7 ✅ -> close stage, slot HELD (worker not released)",
       g["stage"] == "close"
       and any(w.get("block") == "A-01" for w in eng.st.workers))


# ── AC-8: no-silent-stuck (merged but not re-validated on trunk) ──
def t_no_silent_stuck():
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    g = eng.st.gate.setdefault("A-01", {"stage": "merge", "pr": 7})
    eng.st.data["open_prs"] = {}        # PR gone, block not ✅ -> trunk re-validate
    clock = {"t": 1000.0}               # S-1: the wall-clock idle machinery owns this stall
    eng._now_s = lambda: clock["t"]
    eng._drive_gate("A-01", eng.st.gate.get("A-01", g))   # merge -> trunk (PR gone)
    ok("AC-8 trunk re-validate keeps re-nudging (not silent)",
       eng.st.gate.get("A-01", {}).get("stage") == "trunk")
    eng._drive_gate("A-01", eng.st.gate.get("A-01", g))   # anchor idle_since (W1 hold)
    clock["t"] += eng._pace("gate_idle_cap", 3) + 1
    eng._tq = []
    eng._drive_gate("A-01", eng.st.gate.get("A-01", g))   # cap exceeded -> escalate
    walled = any(t.startswith("wall:raised:A-01") for t, _ in eng._tq)
    ok("AC-8 escalates after the nudge cap", walled and "A-01" not in eng.st.gate)


# ── AC-9: reconcile trigger + readiness gate (M-05) ──
def t_reconcile():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng._spawn_architect()
    # A-01 lands ✅ -> the next scoped block must be reconciled before it can dispatch.
    eng.st.row("A-01")["status"] = "done"
    eng._on_block_done("A-01")
    queued = any(j.get("kind") == "reconcile" and j.get("block") == "A-02"
                 for j in eng.st.architect_queue) \
        or (eng._architect().get("current_job") or {}).get("block") == "A-02"
    ok("AC-9 ✅ enqueues a distinct reconcile job for the next block", queued)
    ok("AC-9 next block gated until reconciled", eng._reconcile_pending("A-02"))
    # architect reports reconciled -> gate lifts.
    eng._h_reconcile({"block": "A-02"})
    ok("AC-9 reconcile clears the readiness gate",
       "A-02" in eng.st.reconciled and not eng._reconcile_pending("A-02"))


# ── AC-5: escalation correlation (≤1 tick settle by case id) ──
def t_correlation():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    eng._h_escalate({"block": "A-01", "worker_id": "ENG-A-01", "detail": "stuck"})
    cases = list(eng.st.pending_cases)
    # 01-31 (ADR-0002 D3): architect-first is now universal — with no architect online
    # (this fixture's shape), the wall pages via _triage_to_architect's no-architect
    # fallback (escalate.unclassified), never the pre-01-31 direct escalate.wall
    # ("Above my pay grade"). The correlation id must still ride the page text — the
    # fallback inlines it as `[{case}] ...` since escalate.unclassified carries no
    # `case` slot of its own.
    ok("AC-5 escalation stamps a correlation id",
       len(cases) == 1 and "A-01" in eng.st.blocked
       and any(f"[{cases[0]}]" in t for t in events(ctx)))
    case_id = cases[0]
    eng._h_apply_decision({"case": case_id, "decision": "resume"})
    ok("AC-5 reply settles the case by id in one tick",
       not eng.st.pending_cases and "A-01" not in eng.st.blocked)


# ── AC-6: await ladder (three rungs; rung a never auto-clears) ──
def t_await():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng._spawn_architect()
    eng.st.workers.append({"id": "ENG-A-01", "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "working"})
    # rung (a): pre-registered checkpoint -> operator, parked, never auto-acked.
    eng.st.data["checkpoints"] = ["A-01"]
    eng._h_await({"block": "A-01", "worker_id": "ENG-A-01", "detail": "ship it?"})
    ok("AC-6 rung-a checkpoint -> operator case, no auto-clear",
       any(c.get("kind") == "await" for c in eng.st.pending_cases.values())
       and any("Checkpoint" in t for t in events(ctx)))
    # rung (b): scope/blueprint judgement -> architect.
    qbefore = len(eng.st.architect_queue) + (1 if (eng._architect().get("current_job")) else 0)
    eng._h_await({"block": "A-02", "worker_id": "ENG-A-02", "detail": "which schema?",
                  "kind": "scope"})
    triaged = any(j.get("kind") == "triage" for j in eng.st.architect_queue) \
        or (eng._architect().get("current_job") or {}).get("kind") == "triage"
    ok("AC-6 rung-b scope question -> architect triage", triaged)
    # rung (c): nothing substantive -> deterministic auto-ack (no case, no triage).
    cases_before = len(eng.st.pending_cases)
    eng._h_await({"block": "A-03", "worker_id": "ENG-A-03", "detail": "ok?",
                  "kind": "trivial"})
    ok("AC-6 rung-c trivial -> auto-ack (no escalation)",
       len(eng.st.pending_cases) == cases_before)


# ── AC-10: plumbing nits ──
def t_plumbing():
    # reader Phase regex tolerates a missing space after ###.
    d = tempfile.mkdtemp(prefix="tron-rx-")
    p = os.path.join(d, "pipeline.md")
    util.atomic_write(p, "## Roadmap\n###Phase 1: Tight\n| ID | Task | Status | Notes |\n"
                         "|:-|:-|:-|:-|\n| A-01 | t | 📋 | x |\n")
    rows = reader.parse_pipeline(p)
    ok("AC-10 reader Phase regex handles '###Phase'",
       rows and "Phase 1" in (rows[0].get("phase") or ""))
    # session reset clears counters (no stall-count leak across runs).
    ctx, _ = build()
    eng = Engine(ctx)
    eng.st.data["counters"] = {"stalls": {"A-01": 5}, "case_seq": 9}
    eng._reset_session_runtime()
    ok("AC-10 session reset clears counters", eng.st.counters == {})


# ── AC-11: run-control (PAUSE/DRAIN/HALT/RESUME) ──
def t_run_control():
    ctx, _ = build(blocks=[("A-01", "📋", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.live_config["worker_count"] = 1
    eng.pause()
    eng._switchboard()
    ok("AC-11 PAUSE freezes dispatch", eng.st.run_control == "pause" and not eng._pool())
    eng.drain()
    eng._switchboard()
    ok("AC-11 DRAIN starts nothing new", eng.st.run_control == "drain" and not eng._pool())
    eng.resume()
    eng._switchboard()
    ok("AC-11 RESUME restarts dispatch", eng.st.run_control is None and len(eng._pool()) == 1)
    eng.halt()
    ok("AC-11 HALT ends the run (terminal)",
       eng.ended and (eng.st.data.get("session") or {}).get("started_at") is None)


def main():
    for t in (t_failloud, t_bootup, t_done_gate, t_no_silent_stuck, t_reconcile,
              t_correlation, t_await, t_plumbing, t_run_control):
        try:
            t()
        except Exception as e:
            ok(f"{t.__name__} raised", False, repr(e))
    passed = sum(1 for _, c, _ in _results if c)
    print(f"sentry_test: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
