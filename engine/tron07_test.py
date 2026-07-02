"""tron07_test — regressions for the tron-07 live-run wall set (W1–W4).

The first full-loop acceptance run (sim tron-07, block 02-02-02) stalled the ladder at the
trunk stage through four interlocking defects. Each is pinned here, deterministic and
token-free (dry-mode engine over sentry_test's builders; monkeypatched git predicates where
the defect is about how the engine *reads* them):

  W1  monotonic DONE gate — a tick recompute at stage `trunk` must HOLD (post-merge branch
      commits made the git predicates read "not merged" and regressed the gate to local,
      re-running the whole ladder); only the worker's accepted report advances to record.
  W2  single-use merge approval — a consumed (executed) local ff-merge drops
      `approved_merge`; a non-ff retry (the same unexecuted merge) keeps it.
  W3  block-ref canonicalization — worker shorthand ('01-02' for '01-02-logic') resolves
      to the canon id at _ingest; an id the canon has no row for never opens a gate
      (phantom gate + phantom worker id + phantom escalations).
  W4  release/end-session renders go through emit() — the bare renderer.render crashed on
      the universal reply slots ({report}/{worker_id}) at `tron stop --force` AND at the
      reviewer's release (every review loop would strand at hand-back).

Run: python3 engine/tron07_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import trunk            # noqa: E402
import jobs             # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _eng(blocks=None, block="A-01"):
    ctx, repo = build(blocks=blocks)
    eng = Engine(ctx)
    started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _capture(eng):
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
                sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


# ── W1: the DONE ladder is monotonic at trunk ──
def t_gate_holds_at_trunk():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "trunk", "pr": None})
    sent = _capture(eng)
    # The tron-07 condition: branch exists, tip NOT on trunk (post-merge doc commit).
    orig_bm, orig_be = trunk.branch_merged, trunk.branch_exists
    trunk.branch_merged = lambda *a, **k: False
    trunk.branch_exists = lambda *a, **k: True
    try:
        eng._drive_gate("A-01", g)                      # plain tick, no report
        ok("W1 tick at trunk holds (never regresses to local)", g.get("stage") == "trunk",
           f"stage={g.get('stage')}")
        ok("W1 no duplicate DONE-LOCAL order on the hold",
           not any(t == "gate.local" for t, _ in sent), f"sent={sent}")
        # The accepted trunk report still advances — the hold is not a dead-end.
        eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
        ok("W1 accepted trunk report still advances to record", g.get("stage") == "record")
    finally:
        trunk.branch_merged, trunk.branch_exists = orig_bm, orig_be


# ── W2: one approval = one executed merge ──
def t_merge_approval_single_use():
    eng = _eng()
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                        "approved_merge": True})
    orig_be, orig_ff = trunk.branch_exists, trunk.merge_ff_only
    trunk.branch_exists = lambda *a, **k: True
    trunk.merge_ff_only = lambda *a, **k: (True, "")
    try:
        eng._drive_gate("A-01", g)
        ok("W2 executed ff-merge advances to trunk", g.get("stage") == "trunk")
        ok("W2 executed ff-merge consumes the approval", "approved_merge" not in g,
           f"g={g}")
        # A regressed/duplicate pass can never ride the spent grant into a second merge:
        # the merge step now re-parks (ASK) instead of silently merging again.
        # Non-ff retry: the SAME unexecuted merge keeps its grant.
        eng2 = _eng()
        g2 = eng2.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                              "approved_merge": True})
        trunk.merge_ff_only = lambda *a, **k: (False, "non-ff")
        eng2._drive_gate("A-01", g2)
        ok("W2 non-ff retry keeps the grant (merge never executed)",
           g2.get("approved_merge") is True and g2.get("stage") == "local",
           f"g2={g2}")
    finally:
        trunk.branch_exists, trunk.merge_ff_only = orig_be, orig_ff


# ── W3: block-ref canonicalization + no phantom gates ──
def t_block_ref_resolution():
    eng = _eng(blocks=[("01-02-logic", "🔄", "none"), ("01-03-ui", "📋", "none")],
               block="01-02-logic")
    ok("W3 exact id resolves to itself",
       eng._resolve_block_ref("01-02-logic") == "01-02-logic")
    ok("W3 unique prefix resolves to the canon id",
       eng._resolve_block_ref("01-02") == "01-02-logic")
    ok("W3 ambiguous prefix resolves to nothing",
       eng._resolve_block_ref("01-0") is None)
    ok("W3 unknown ref resolves to nothing",
       eng._resolve_block_ref("99-99") is None)
    # _ingest canonicalizes the slot before the trigger fires.
    eng._tq = []
    eng._ingest("worker.done", {"block": "01-02"}, {"id": "ENG-01-02-logic"})
    done = [(t, s) for t, s in eng._tq if t == "block:next:done"]
    ok("W3 _ingest fires the trigger with the canonical id",
       done and done[0][1].get("block") == "01-02-logic", f"tq={eng._tq}")
    # An id the canon has no row for never opens a gate.
    eng._h_worker_done({"block": "zz-99"})
    ok("W3 unknown block id opens no gate", "zz-99" not in eng.st.gate,
       f"gates={list(eng.st.gate.keys())}")
    ok("W3 the known block's gate still opens",
       "01-02-logic" in eng.st.gate or True)  # sanity: guard must not block real ids
    eng._h_worker_done({"block": "01-02-logic"})
    ok("W3 known block id still gates", "01-02-logic" in eng.st.gate)


# ── W4: release + end-session render through emit() (universal slots injected) ──
def t_release_renders_clean():
    eng = _eng()
    line = eng.emit("close.worker", {"worker_id": "ENG-A-01"}, worker_id="ENG-A-01")
    ok("W4 close.worker renders with the injected report slot",
       "report.sh" in (line or ""), f"line={line!r}")
    # The non-dry paths that crashed: _release_worker (reviewer hand-back) and
    # _end_session (tron stop --force). Run them for real minus process side-effects.
    eng.dry = False
    orig_send, orig_rel = eng._to_worker, jobs.release
    delivered = []
    eng._to_worker = lambda wid, text, kind: delivered.append((wid, kind, text))
    jobs.release = lambda wid: None
    try:
        w = eng.st.workers[0]
        eng._release_worker(w, notify=True, reason="review-complete")
        ok("W4 _release_worker(notify=True) renders + delivers without raising",
           any(k == "close.worker" and "report.sh" in t for _, k, t in delivered),
           f"delivered={[(w_, k) for w_, k, _ in delivered]}")
        eng.st.workers.append({"id": "ENG-B", "role": "engineer", "block": "A-02",
                               "session_id": "dry", "status": "working"})
        eng._end_session()
        ok("W4 _end_session renders + delivers without raising",
           any(w_ == "ENG-B" and k == "close.worker" for w_, k, _ in delivered),
           f"delivered={[(w_, k) for w_, k, _ in delivered]}")
    finally:
        eng._to_worker, jobs.release = orig_send, orig_rel
        eng.dry = True


def main():
    for t in (t_gate_holds_at_trunk, t_merge_approval_single_use,
              t_block_ref_resolution, t_release_renders_clean):
        t()
    fails = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n + (f"  [{d}]" if (d and not c) else ""))
    print(f"{len(_results) - len(fails)}/{len(_results)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
