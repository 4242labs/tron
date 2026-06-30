"""e2e_test — the full-lifecycle dry E2E of the rebuilt SENTRY engine.

The revived `.sandbox/smoke_test.py` (retired in 01-02 because the engine wasn't
rebuilt yet). It drives ONE run end-to-end with the real transport path
(inbox → classify → ingest → route), token-free: `classify_message` is stubbed
per message and trunk is simulated (a fixture canon repo + monkeypatched
refresh/open_prs that the test mutates to play the agents' git writes). No real
worker agents — that's the live run (01-07); this proves the deterministic flow.

Lifecycle exercised: bootup → dispatch (dep-gated) → DONE gate (validate-local →
PR → CI → ✅) → reconcile-ahead gate (M-05) → cadence reviewer (PULL) → log-review
→ drain → clean session end.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import util            # noqa: E402
import judge           # noqa: E402
import trunk           # noqa: E402
from ctx import Ctx    # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, NOW  # noqa: E402  (shared fixture builder)

_results = []
_PRS = {}              # simulated open PRs keyed by branch (the test mutates this)


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def report(ctx, text, tag, slots):
    """Inject one inbound message + the classify result it must yield, then run a fresh tick."""
    stub = {"classify_message": [{"tag": tag, "slots": slots, "confidence": 1.0}]}
    util.atomic_write(os.path.join(ctx.dir, "stub.json"),
                      __import__("json").dumps(stub))
    os.environ["TRON_JUDGE_STUB"] = os.path.join(ctx.dir, "stub.json")
    judge._stub_cache = None
    judge._stub_idx.clear()
    util.append_jsonl(ctx.worker_inbox, {"text": text, "sender": {"kind": "worker"}})
    return Engine(ctx).tick()


def quiet_tick(ctx):
    """A tick with no inbound message (drives gates on fresh trunk evidence)."""
    os.environ.pop("TRON_JUDGE_STUB", None)
    return Engine(ctx).tick()


def land(repo, bid):
    """Play an agent landing a block ✅ on trunk: flip its block-file status + drop its PR."""
    p = os.path.join(repo, "meta", "blocks", f"{bid}.md")
    with open(p) as fh:
        text = fh.read()
    for glyph in ("📋", "🔄"):
        text = text.replace(f"**Status:** {glyph}", "**Status:** ✅")
    util.atomic_write(p, text)
    _PRS.pop(f"feat/{bid}", None)


def pipe(ctx):
    st = util.load_yaml(ctx.state)
    return {r["id"]: r["status"] for r in st.get("pipeline", [])}


def workers(ctx, role=None):
    st = util.load_yaml(ctx.state)
    return [w for w in st.get("active_workers", [])
            if role is None or w.get("role") == role]


def run():
    # Fixture: A-02 depends on A-01 (exercises the dep + reconcile gate); review every 2 blocks.
    ctx, repo = build(blocks=[("A-01", "📋", "none"), ("A-02", "📋", "none")])
    # A-02 depends on A-01:
    a2 = os.path.join(repo, "meta", "blocks", "A-02.md")
    util.atomic_write(a2, open(a2).read().replace("**Depends on:** none", "**Depends on:** A-01"))
    k = util.load_yaml(ctx.knobs_file)
    k["cadence"] = {"code": 2}
    util.save_yaml(ctx.knobs_file, k)

    orig_refresh, orig_prs = trunk.refresh, trunk.open_prs
    trunk.refresh = lambda *a, **k: (True, "ok")
    trunk.open_prs = lambda root, dry=False: dict(_PRS)
    try:
        eng = Engine(ctx)
        eng.start(2)
        ok("bootup spawns architect, no worker pre-dispatch on dep-gated A-02",
           eng._architect() is not None
           and any(w.get("block") == "A-01" for w in workers(ctx, "engineer"))
           and not any(w.get("block") == "A-02" for w in workers(ctx, "engineer")))

        report(ctx, "A-01 done", "worker.done", {"block": "A-01"})
        st = util.load_yaml(ctx.state)
        ok("worker.done opens the DONE gate (local/DONE-LOCAL), block not ✅",
           st.get("gate", {}).get("A-01", {}).get("stage") == "local"
           and pipe(ctx)["A-01"] != "done")

        _PRS["feat/A-01"] = {"number": 1, "checks": "passing"}
        quiet_tick(ctx)
        st = util.load_yaml(ctx.state)
        ok("PR + green CI -> merge stage (still not ✅ on a claim)",
           st.get("gate", {}).get("A-01", {}).get("stage") == "merge"
           and pipe(ctx)["A-01"] != "done")

        land(repo, "A-01")
        quiet_tick(ctx)
        st = util.load_yaml(ctx.state)
        ok("✅ on trunk -> CLOSE: engineer HELD (slot not freed yet), reconcile A-02 raised (M-05)",
           pipe(ctx)["A-01"] == "done"
           and st.get("gate", {}).get("A-01", {}).get("stage") == "close"
           and any(w.get("block") == "A-01" for w in workers(ctx, "engineer"))
           and ("A-02" in [j.get("block") for j in st.get("architect_queue", [])]
                or (next((w for w in st.get("active_workers", []) if w.get("role") == "architect"),
                         {}).get("current_job") or {}).get("block") == "A-02"))

        report(ctx, "A-01 cleaned up", "worker.done", {"block": "A-01"})   # CLOSE clean-confirm (T7)
        st = util.load_yaml(ctx.state)
        ok("CLOSE confirmed -> engineer released, gate cleared",
           not any(w.get("block") == "A-01" for w in workers(ctx, "engineer"))
           and "A-01" not in st.get("gate", {}))
        ok("A-02 dispatch is gated until reconciled", not any(
            w.get("block") == "A-02" for w in workers(ctx, "engineer")))

        report(ctx, "A-02 reconciled", "architect.reconciled", {"block": "A-02"})
        ok("architect.reconciled lifts the gate -> A-02 dispatched",
           any(w.get("block") == "A-02" for w in workers(ctx, "engineer")))

        report(ctx, "A-02 done", "worker.done", {"block": "A-02"})
        _PRS["feat/A-02"] = {"number": 2, "checks": "passing"}
        quiet_tick(ctx)
        land(repo, "A-02")
        quiet_tick(ctx)
        ok("A-02 lands ✅ -> CLOSE; cadence reviewer comes due (PULL)",
           pipe(ctx)["A-02"] == "done" and workers(ctx, "reviewer"))
        report(ctx, "A-02 cleaned up", "worker.done", {"block": "A-02"})   # release ENG-A-02

        # Reviewer DONE-REVIEW gate (T5): the first hand-back challenges full coverage (held);
        # the attestation releases it + queues the architect remediation.
        report(ctx, "code review done", "worker.review_done", {"type": "code"})
        st = util.load_yaml(ctx.state)
        ok("review_done opens DONE-REVIEW gate (reviewer HELD to attest coverage)",
           "review:code" in st.get("gate", {}) and bool(workers(ctx, "reviewer")))
        report(ctx, "code review fully covered", "worker.review_done", {"type": "code"})
        st = util.load_yaml(ctx.state)
        ok("review attested -> reviewer released + architect remediation queued",
           not workers(ctx, "reviewer"))

        ended = report(ctx, "log review done", "architect.logged", {"block": "adhoc", "adhoc": []})
        final = pipe(ctx)
        st = util.load_yaml(ctx.state)
        all_done = all(v == "done" for v in final.values()) and bool(final)
        session_closed = (st.get("session") or {}).get("started_at") is None
        ok("drains to a clean session end (all blocks ✅, session closed)",
           all_done and session_closed, f"pipe={final}")
    finally:
        trunk.refresh, trunk.open_prs = orig_refresh, orig_prs


def main():
    try:
        run()
    except Exception as e:
        ok("e2e run raised", False, repr(e))
    passed = sum(1 for _, c, _ in _results if c)
    print(f"e2e_test: {'PASS' if passed == len(_results) else 'FAIL'} ({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
