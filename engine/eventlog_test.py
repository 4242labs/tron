"""eventlog_test — the 01-06 structured event + failure log acceptance suite (AC-1 … AC-5).

Deterministic, token-free: TRON_DRY stubs every side effect. Each case builds a throwaway
TRON dir + a fixture canon repo (the same fixture sentry_test uses), then drives the engine's
real failure paths so the records are produced exactly as they would be at runtime.

Covers: the common record header (AC-1), failure-record completeness (AC-2), one deliberately
induced failure per class — reconstructable with NO re-run (AC-3), unclassified logging (AC-4),
and the query path (AC-5). Exit 0 only if every case passes.
"""
import os
import re
import sys
import json
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import util            # noqa: E402
import trunk           # noqa: E402
import jobs            # noqa: E402
import judge           # noqa: E402
import wake            # noqa: E402
import eventlog        # noqa: E402
from ctx import Ctx    # noqa: E402
from fsm import Engine  # noqa: E402

NOW = "2026-06-28T00:00:00Z"
HEADER = {"at", "kind", "type", "actor", "block", "tag", "cid", "run", "tick", "trunk", "payload"}
FAILURE_FIELDS = {"fclass", "code", "operation", "cause", "inputs", "node", "next", "attempt"}
_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _block_md(bid, status="📋", deps="none", deploy="none"):
    return (f"# Block {bid}: test {bid}\n"
            f"**Phase:** Phase 1: Test\n**Status:** {status}\n"
            f"**Depends on:** {deps}\n**Reviewer class:** code\n"
            f"**Merge:** self\n**Deploy:** {deploy}\n\n---\n\n## Body\n")


def build(blocks=None):
    blocks = blocks or [("A-01", "📋", "none"), ("A-02", "📋", "none")]
    d = tempfile.mkdtemp(prefix="tron-eventlog-")
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
    rows = ["## Roadmap", "### Phase 1: Test", "| ID | Task | Status | Notes |", "|:--|:--|:--|:--|"]
    for bid, status, deploy in blocks:
        rows.append(f"| {bid} | t | {status} | Block `blocks/{bid}.md` |")
        util.atomic_write(os.path.join(bdir, f"{bid}.md"), _block_md(bid, status, deploy=deploy))
    util.atomic_write(os.path.join(repo, "meta", "pipeline.md"), "\n".join(rows) + "\n")
    return Ctx(d), repo


def engine(ctx, run=NOW):
    eng = Engine(ctx)
    eng.st.data["session"] = {"started_at": run}      # so _log_env stamps the run handle
    eng._refresh_from_trunk(count=False)
    return eng


def recs(ctx):
    return util.read_jsonl(ctx.event_log)


def failures(ctx):
    return [r for r in recs(ctx) if r.get("kind") == "failure"]


def header_ok(r):
    return HEADER <= set(r)


def failure_complete(r):
    """A failure record reconstructs the cause offline (AC-2): full header + every failure field,
    a known class, a non-empty operation + cause, a next-action, and pinned state context."""
    return (header_ok(r) and FAILURE_FIELDS <= set(r)
            and r.get("fclass") in eventlog.FAILURE_CLASSES
            and bool(r.get("code")) and bool(r.get("operation")) and bool(r.get("cause"))
            and r.get("next") is not None and "run" in r and "tick" in r and r.get("node"))


# ── AC-3: one deliberately induced failure per class ──
def induce_refresh_fail(ctx):
    eng = engine(ctx)
    orig = trunk.refresh
    trunk.refresh = lambda *a, **k: (False, "fetch failed: simulated network down")
    try:
        eng._refresh_from_trunk(count=True)            # below the death-cap -> next=retry
    finally:
        trunk.refresh = orig
    return [r for r in failures(ctx) if r.get("fclass") == "refresh-fail"]


def induce_classify_fail(ctx):
    # An invalid classifier output exhausts the budget -> classify-fail + auto-ack to unclassified.
    stub = os.path.join(ctx.dir, "stub.json")
    util.atomic_write(stub, json.dumps({"classify_message": [{"tag": "NOPE", "slots": {}}]}))
    os.environ["TRON_JUDGE_STUB"] = stub
    judge._stub_cache = None
    judge._stub_idx.clear()
    judge._tags_cache = None
    try:
        eng = engine(ctx)
        eng._classify({"text": "garble", "sender": {"kind": "worker", "id": "W-7"}})
    finally:
        del os.environ["TRON_JUDGE_STUB"]
        judge._stub_cache = None
        judge._stub_idx.clear()
    return [r for r in failures(ctx) if r.get("fclass") == "classify-fail"]


def induce_ingest_drop(ctx):
    eng = engine(ctx)

    def boom(_m):
        raise ValueError("simulated classify explosion")

    eng._classify = boom
    util.append_jsonl(ctx.worker_inbox, {"text": "anything", "sender": {"kind": "worker", "id": "W-3"}})
    eng.tick()                                          # the per-message guard records ingest-drop
    return [r for r in failures(ctx) if r.get("fclass") == "ingest-drop"]


def induce_gate_stuck(ctx):
    eng = engine(ctx)
    # A single-gate block whose PR is gone and re-nudge cap is exceeded -> escalate (no silent stuck).
    eng.st.gate["A-01"] = {"pr": 11, "post_merge_nudges": 99, "stage": "post-merge"}
    eng._drive_gate("A-01", eng.st.gate["A-01"])
    return [r for r in failures(ctx) if r.get("fclass") == "gate-stuck"]


def induce_dispatch_fail(ctx):
    eng = engine(ctx)
    eng.dry = False                                    # so _spawn reaches the spawn call
    orig = jobs.spawn_detached
    jobs.spawn_detached = lambda *a, **k: (_ for _ in ()).throw(OSError("simulated spawn failure"))
    raised = False
    try:
        eng._spawn("ENG-A-01", "spawn.engineer",
                   {"worker_id": "ENG-A-01", "block": "A-01", "branch": "feat/A-01"},
                   role="engineer", block="A-01")
    except OSError:
        raised = True
    finally:
        jobs.spawn_detached = orig
    return raised, [r for r in failures(ctx) if r.get("fclass") == "dispatch-fail"]


def induce_crash(ctx):
    # A whole tick raising is recorded as `crash` by wake.locked_tick, then re-raised for the
    # supervised loop. Monkeypatch tick to blow up; assert the record is written.
    orig = Engine.tick
    Engine.tick = lambda self: (_ for _ in ()).throw(RuntimeError("simulated tick crash"))
    raised = False
    try:
        wake.locked_tick(ctx)
    except RuntimeError:
        raised = True
    finally:
        Engine.tick = orig
    return raised, [r for r in failures(ctx) if r.get("fclass") == "crash"]


def t_per_class():
    """AC-3 + AC-2 + AC-1: induce one failure per class; each record is complete + reconstructable."""
    induced = {}
    ctx, _ = build();  induced["refresh-fail"] = induce_refresh_fail(ctx)
    ctx, _ = build();  induced["classify-fail"] = induce_classify_fail(ctx)
    ctx, _ = build();  induced["ingest-drop"] = induce_ingest_drop(ctx)
    ctx, _ = build();  induced["gate-stuck"] = induce_gate_stuck(ctx)
    ctx, _ = build();  dispatch_raised, induced["dispatch-fail"] = induce_dispatch_fail(ctx)
    ctx, _ = build();  crash_raised, induced["crash"] = induce_crash(ctx)

    # Reconstructable-with-no-re-run predicate per class: the record holds enough to pin the
    # exact trigger — either in the cause (the simulated detail) or in the captured inputs.
    reconstruct = {
        "refresh-fail": lambda r: "simulated network down" in (r.get("cause") or ""),
        "classify-fail": lambda r: "garble" in str((r.get("inputs") or {}).get("text", "")),
        "ingest-drop": lambda r: "simulated classify explosion" in (r.get("cause") or ""),
        "gate-stuck": lambda r: "nudges" in (r.get("inputs") or {}) and bool(r.get("cause")),
        "dispatch-fail": lambda r: "simulated spawn failure" in (r.get("cause") or ""),
        "crash": lambda r: "simulated tick crash" in (r.get("cause") or ""),
    }
    for cls in eventlog.FAILURE_CLASSES:
        rs = induced.get(cls, [])
        ok(f"AC-3 {cls} record emitted", len(rs) >= 1, f"got {len(rs)}")
        ok(f"AC-2 {cls} record complete", rs and all(failure_complete(r) for r in rs))
        # Reconstructable with no re-run: the record pins the exact trigger.
        ok(f"AC-3 {cls} reconstructable", rs and all(reconstruct[cls](r) for r in rs))

    ok("dispatch-fail re-raises after recording", dispatch_raised)
    ok("crash re-raises after recording", crash_raised)

    # refresh-fail next-action reflects the real branch (retry below the cap).
    rf = induced["refresh-fail"]
    ok("AC-2 refresh-fail next=retry below cap", rf and rf[0].get("next") == "retry")
    ok("AC-2 refresh-fail pins inputs", rf and rf[0].get("inputs", {}).get("main_branch") == "main")


def t_unclassified():
    """AC-4: every unclassified message is logged with its raw body + why no tag matched —
    both the exhausted path and the model-said-unclassified path."""
    ctx, _ = build()
    # Path 1: exhaustion (invalid output) -> auto-ack.
    induce_classify_fail(ctx)
    # Path 2: the model legitimately returns `unclassified`.
    stub = os.path.join(ctx.dir, "stub2.json")
    util.atomic_write(stub, json.dumps({"classify_message": [{"tag": "unclassified", "slots": {}}]}))
    os.environ["TRON_JUDGE_STUB"] = stub
    judge._stub_cache = None
    judge._stub_idx.clear()
    judge._tags_cache = None
    try:
        eng = engine(ctx)
        eng._classify({"text": "what is the meaning of life", "sender": {"kind": "operator"}})
    finally:
        del os.environ["TRON_JUDGE_STUB"]
        judge._stub_cache = None
        judge._stub_idx.clear()

    uncl = [r for r in recs(ctx) if r.get("kind") == "unclassified"]
    ok("AC-4 unclassified records written", len(uncl) >= 2, f"got {len(uncl)}")
    ok("AC-4 each carries raw body", all((r.get("payload") or {}).get("raw") for r in uncl))
    ok("AC-4 each carries why-no-tag", all((r.get("payload") or {}).get("why") for r in uncl))
    ok("AC-4 header complete", all(header_ok(r) for r in uncl))
    ok("AC-4 exhaustion reason captured",
       any("exhaust" in (r["payload"].get("why") or "") for r in uncl))
    ok("AC-4 no-tag-matched reason captured",
       any("no tag matched" in (r["payload"].get("why") or "") for r in uncl))


def t_header_and_events():
    """AC-1: the structured log is append-only and every record carries the common header
    (type·actor·block·tag·correlation-id·timestamp·payload-ref + run/tick/trunk state)."""
    ctx, _ = build()
    eng = engine(ctx)
    eng.events.event("dispatch", actor="ENG-A-01", block="A-01", role="engineer")
    eng.events.event("escalate", actor="ENG-A-01", block="A-01", cid="CASE-001", tag="worker.wall")
    rs = recs(ctx)
    ok("AC-1 events appended", len(rs) >= 2)
    ok("AC-1 every record has the full header", all(header_ok(r) for r in rs))
    ok("AC-1 timestamp present", all(r.get("at") for r in rs))
    ok("AC-1 correlation id carried when set",
       any(r.get("cid") == "CASE-001" for r in rs))
    ok("AC-1 run/tick/trunk state stamped",
       all("run" in r and "tick" in r and "trunk" in r for r in rs))


def t_query():
    """AC-5: query returns all failures for a run / block / class with full detail, newest-first."""
    ctx, _ = build()
    eng = engine(ctx, run="RUN-X")
    # Three failures across two blocks + one normal event interleaved.
    eng.events.failure("gate-stuck", "c1", "op1", "cause one", block="A-01", node="n", next_action="escalate")
    eng.events.event("dispatch", actor="W", block="A-02")
    eng.events.failure("dispatch-fail", "c2", "op2", "cause two", block="A-02", node="n", next_action="crash")
    eng.events.failure("gate-stuck", "c3", "op3", "cause three", block="A-01", node="n", next_action="escalate")

    all_fail = eventlog.query(ctx, failures_only=True)
    ok("AC-5 failures-only filters out events", all(r.get("kind") == "failure" for r in all_fail))
    ok("AC-5 returns every failure", len(all_fail) == 3, f"got {len(all_fail)}")
    ok("AC-5 newest-first", all_fail and all_fail[0].get("code") == "c3")

    by_block = eventlog.query(ctx, block="A-01", failures_only=True)
    ok("AC-5 filter by block", [r.get("code") for r in by_block] == ["c3", "c1"])

    by_class = eventlog.query(ctx, fclass="gate-stuck")
    ok("AC-5 filter by class", len(by_class) == 2 and all(r["fclass"] == "gate-stuck" for r in by_class))

    by_run = eventlog.query(ctx, run="RUN-X", failures_only=True)
    ok("AC-5 filter by run", len(by_run) == 3)
    ok("AC-5 filter by absent run is empty", eventlog.query(ctx, run="NOPE", failures_only=True) == [])

    limited = eventlog.query(ctx, failures_only=True, limit=1)
    ok("AC-5 limit honoured", len(limited) == 1 and limited[0].get("code") == "c3")
    ok("AC-5 full detail returned", all(failure_complete(r) for r in all_fail))


def t_ac6_pairing():
    """AC-6 guard: every declared failure class has at least one wire point in the engine, and no
    wire point names an undeclared class — so the taxonomy and the loud-failure points cannot drift
    apart. Closes AC-6 from manual-by-code to enforced: a new loud-failure point that forgets its
    record (or a class added without a wire point) fails here."""
    wired = set()
    for fname in ("fsm.py", "wake.py"):
        with open(os.path.join(HERE, fname)) as fh:
            wired |= set(re.findall(r'events\.failure\(.*?"([a-z-]+)"', fh.read(), re.DOTALL))
    ok("AC-6 no wire point names an undeclared class", wired <= eventlog.FAILURE_CLASSES,
       f"undeclared: {sorted(wired - eventlog.FAILURE_CLASSES)}")
    ok("AC-6 every declared class is wired", eventlog.FAILURE_CLASSES <= wired,
       f"unwired: {sorted(eventlog.FAILURE_CLASSES - wired)}")


def main():
    for t in (t_per_class, t_unclassified, t_header_and_events, t_query, t_ac6_pairing):
        try:
            t()
        except Exception as e:
            ok(f"{t.__name__} raised", False, repr(e))
    passed = sum(1 for _, c, _ in _results if c)
    print(f"eventlog_test: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
