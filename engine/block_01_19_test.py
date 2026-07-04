"""block_01_19_test — regressions for the 01-19 merge-ownership + order-send-discipline
set (tron-25/26 matched-pair findings, canon cb739ed).

  T1  one merge-ownership story in local mode: the engine lands the trunk merge; a worker
      is never ordered to merge and never merges. The non-ff arm (local mode's ONLY
      gate.merge sender — the tron-26 standoff: 20 per-tick "Merge it" re-sends into a
      walled worker's mailbox, ~25 min, operator-broken) now sends the engine-composed
      REBASE order (gate.changes precedent, no new template), stamps `rebase_pending`
      (branch_gap precedent), and keeps renudge=False so the idle machinery + cap stay
      LIVE on this path (F4: both naive readings were defective). The merge retry stays
      inside the on_report/approved_merge guard (F9) — per-tick while a grant is held,
      report-driven otherwise, never hoisted ahead of _merge_gated (ASK gate intact).
  T2  ONE stage-order composer (_send_gate_order): gate state + stage + wid + block ->
      the correct order with its mailbox kind, called by ALL order-composition sites
      (stage-emit tail, idle re-nudge, _post_unhold_nudge, the branch-gap direct send
      (R3-2), the non-ff flag-stamp first send (R3-1)). Kind-keyed dedupe (per-kind
      last-send-seq vs the runner-owned .mbox-hwm, jobs.read_hwm — F5/F8) and the
      walled-worker guard live INSIDE that seam. Suppression suppresses the SEND only
      (R2-3); a skipped send never consumes the idle nudge budget; settle-driven notices
      still deliver to walled workers (F3 — never a blanket guard in _to_worker/emit).
  T3  held-verb replay folds duplicate walls at BOTH replay seams (resume arm + sweep
      wall-invariant arm (a) — F2: tron-26's CASE-012 came through the sweep door) via
      the ONE shared _unhold_and_replay helper: PRE-SCAN before serial _ingest (F12);
      rule 1 folds echoes of the settled case (no case, never re-walls, never re-queues,
      folded text in the flow log — F7); rule 2 collapses remaining same-worker+block
      walls to one fresh raise (first position, newest text) whose re-wall/re-queue is
      legitimate (R2-2); rule 1 inert when the settled case is None; non-wall verbs
      replay unchanged in arrival order.
  T4  operator-relay honesty: any OPERATOR-sender line landing in a side-log-only
      handler (best_effort AND edit_self — the handler class, R2-5; the observed death
      path was operator.directive -> best_effort, F1) emits the not-relayed notice via
      the existing escalate.unclassified template, keyed on sender KIND (R2-9 — operator
      senders carry no id). The no-settle-match notice carries the same clause; a
      resolved block-less settle still emits no false "no match" (01-18 T4 guard).

T1/T2's flow cases are dry FSM-level (TRON_DRY, sentry_test's fixture builders); the
dedupe cases set `eng.dry = False` for REAL mailbox writes into the tmp instance's worker
store (the .mbox-hwm consumed-seq seam needs the real files). T3's sweep-seam cases use
`eng.dry = False` (block_01_17/01_18 convention: _sweep no-ops entirely under dry); the
resume-seam cases stay dry. Archival of replayed wall verbs is claim-time (01-18 T8,
upstream of _ingest) and is covered by block_01_18_test — here the fold's own visible
half (the flow-logged folded text) is asserted instead.

Run: python3 engine/block_01_19_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import jobs              # noqa: E402
import trunk             # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []

PING_WINDOW_S = 6 * 60 + 1   # past silence_ping_min (default 6) — the sweep window


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _capture(eng):
    """Spy on eng.emit — the tron07_test/block_01_18_test convention."""
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
                sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


def _capture_to_worker(eng):
    """Spy on eng._to_worker (block_01_13_test's convention) — replaces it outright: the
    rebase/branch-gap lines are engine-composed via `_to_worker` directly, never emit()."""
    sent = []
    eng._to_worker = lambda wid, text, kind: sent.append((wid, text, kind))
    return sent


def _capture_log(eng):
    """Spy on eng.log — the fold's flow-logged folded text is T3's visible surface."""
    lines = []
    orig = eng.log
    eng.log = lambda name, text: lines.append((name, text)) or orig(name, text)
    return lines


# ── fixture builders ──
def _eng(block="A-01", status="🔄"):
    """A started LOCAL-mode engine with ONE working engineer bound to `block`."""
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _wall(eng, block, wid, detail="flaky ci"):
    """Raise a wall against an ALREADY-rostered worker. Returns the parked case id."""
    eng._tq = []
    eng._h_escalate({"block": block, "worker_id": wid, "detail": detail})
    return next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")


def _stub_trunk(merged=False, exists=True, tip="TIP1234", ff=(False, "not a fast-forward")):
    """Swap the gate's git predicates; returns (originals, calls) — calls counts ff merges."""
    orig = (trunk.branch_merged, trunk.branch_exists, trunk.tip_sha,
            trunk.merge_ff_only, trunk.is_ancestor)
    calls = {"ff": 0}

    def _ff(*a, **k):
        calls["ff"] += 1
        return ff if isinstance(ff, tuple) else ff()
    trunk.branch_merged = lambda *a, **k: merged
    trunk.branch_exists = lambda *a, **k: exists
    trunk.tip_sha = lambda *a, **k: tip
    trunk.merge_ff_only = _ff
    trunk.is_ancestor = lambda root, sha, main, dry=False: True
    return orig, calls


def _restore_trunk(orig):
    (trunk.branch_merged, trunk.branch_exists, trunk.tip_sha,
     trunk.merge_ff_only, trunk.is_ancestor) = orig


def _queue_walls(eng, wid, specs):
    """Queue held verbs behind a wall via the real _ingest walled-check (T1 01-15 seam).
    specs: list of (tag, slots)."""
    for tag, slots in specs:
        eng._ingest(tag, slots, {"kind": "worker", "id": wid})


# ══ T1: one merge-ownership story in local mode ══

def t1_nonff_sends_rebase_order_never_gate_merge():
    # AC-1 T1 bullet: local-mode non-ff -> the worker receives the rebase order (never
    # gate.merge / "Merge it"); rebase_pending set.
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    orig, calls = _stub_trunk(ff=(False, "not a fast-forward (rebase-retry: "
                                         "branch feat/A-01 is checked out at wt)"))
    sent = _capture(eng)
    tw = _capture_to_worker(eng)
    try:
        eng._drive_gate("A-01", g, reason="worker reported done", on_report=True)
    finally:
        _restore_trunk(orig)
    ok("T1 non-ff never sends gate.merge in local mode",
       not any(tid == "gate.merge" for tid, _ in sent), f"sent={sent}")
    ok("T1 the worker receives the engine-composed rebase order (kind gate.rebase)",
       any(k == "gate.rebase" for _, _, k in tw), f"tw={tw}")
    ok("T1 the rebase order says do-not-merge / I land it — never 'Merge it'",
       any("do not merge" in t and "I land it" in t and "Merge it" not in t
           for _, t, k in tw if k == "gate.rebase"), f"tw={tw}")
    ok("T1 rebase_pending is stamped (branch_gap precedent)",
       g.get("rebase_pending") is True, f"g={g}")
    ok("T1 the gate holds at local (stage unmoved, gate preserved)",
       "A-01" in eng.st.gate and g.get("stage") == "local", f"g={g}")
    ok("T1 the merge WAS attempted by the engine (ownership stays engine-side)",
       calls["ff"] == 1, f"calls={calls}")


def t1_idle_renudge_sends_rebase_line_never_gate_local():
    # AC-1 T1 bullet: the idle re-nudge re-sends the rebase line (never gate.local)
    # while the flag is set.
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                        "rebase_pending": True})
    orig, _ = _stub_trunk()
    sent = _capture(eng)
    tw = _capture_to_worker(eng)
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    try:
        eng._drive_gate("A-01", g)                    # plain grantless tick: anchors idle
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._drive_gate("A-01", g)                    # idle re-nudge fires
    finally:
        _restore_trunk(orig)
    ok("T1 the idle re-nudge sends the rebase line while rebase_pending",
       any(k == "gate.rebase" for _, _, k in tw), f"tw={tw}")
    ok("T1 the idle re-nudge never sends gate.local while rebase_pending "
       "(the W12 re-validation-treadmill class)",
       not any(tid == "gate.local" for tid, _ in sent), f"sent={sent}")
    ok("T1 the nudge consumed its budget on the ACTUAL send (nudged_at set)",
       g.get("nudged_at") is not None, f"g={g}")


def t1_post_unhold_nudge_sends_rebase_line_never_gate_local():
    # AC-1 T1 bullet: _post_unhold_nudge re-sends the rebase line (never gate.local)
    # while the flag is set.
    eng = _eng()
    eng.st.gate["A-01"] = {"stage": "local", "pr": None, "rebase_pending": True}
    w = next(x for x in eng.st.workers if x["id"] == "ENG-A-01")
    sent = _capture(eng)
    tw = _capture_to_worker(eng)
    eng._post_unhold_nudge(w, "A-01")
    ok("T1 _post_unhold_nudge sends the rebase line while rebase_pending",
       any(k == "gate.rebase" for _, _, k in tw), f"tw={tw}")
    ok("T1 _post_unhold_nudge never sends gate.local while rebase_pending",
       not any(tid == "gate.local" for tid, _ in sent), f"sent={sent}")


def t1_idle_cap_still_fires_on_silent_post_rebase_stall():
    # AC-1 T1 bullet: the idle CAP still fires on a silent post-rebase-order stall —
    # renudge=False keeps the idle machinery LIVE (F4's silent-stuck hole never opens).
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                        "rebase_pending": True})
    orig, _ = _stub_trunk()
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    try:
        eng._drive_gate("A-01", g)                    # anchors idle_since
        clock["t"] += eng._pace("gate_idle_cap", 3) + 1
        eng._tq = []
        eng._drive_gate("A-01", g)                    # cap fires -> gate giveup -> wall
    finally:
        _restore_trunk(orig)
    ok("T1 the gate-idle-cap still fires on a silent post-rebase-order stall",
       any(t.startswith("wall:raised:A-01") for t, _ in eng._tq), f"tq={eng._tq}")
    ok("T1 the giveup popped the gate (no-silent-stuck law, unchanged)",
       "A-01" not in eng.st.gate, f"gate={eng.st.gate}")


def t1_rebase_report_lands_ff_clears_flag_anchors_post_merge():
    # AC-1 T1 bullets: after the worker's rebase+report the engine lands the ff-merge and
    # clears the flag; merged_sha anchors POST-merge (the 01-18 T1 invariant holds).
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    orig, _ = _stub_trunk(ff=(False, "not a fast-forward"))
    try:
        eng._drive_gate("A-01", g, on_report=True)    # non-ff -> flag
        ok("setup: the flag is set after the non-ff", g.get("rebase_pending") is True)
        # The worker rebased and re-reported: the retry now lands; the tip read AFTER
        # merge_ff_only returns is the post-rebase tip (01-18 T1).
        tips = {"n": 0}

        def post_tip(*a, **k):
            tips["n"] += 1
            return "PREIMAGE1234" if tips["n"] == 1 else "POSTMERGE5678"
        trunk.tip_sha = post_tip
        trunk.merge_ff_only = lambda *a, **k: (True, "")
        eng._drive_gate("A-01", g, on_report=True)
    finally:
        _restore_trunk(orig)
    ok("T1 the engine lands the ff-merge on the worker's rebase+report (stage -> trunk)",
       g.get("stage") == "trunk", f"g={g}")
    ok("T1 rebase_pending clears the moment the ff lands",
       "rebase_pending" not in g, f"g={g}")
    ok("T1 merged_sha anchors the POST-merge tip through this path (01-18 T1 invariant)",
       g.get("merged_sha") == "POSTMERGE5678", f"g={g}")


def t1_grantless_tick_never_attempts_the_merge_ask_gate_intact():
    # AC-1 T1 bullet: a grantless tick never attempts the merge (ASK gate intact) —
    # the retry stays inside the on_report/approved_merge guard, behind _merge_gated (F9).
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    eng.st.approvals["merge"] = "ASK"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    orig, calls = _stub_trunk(ff=(False, "not a fast-forward"))
    try:
        eng._drive_gate("A-01", g, on_report=True)    # ASK parks; no merge attempt
        ok("T1 ASK parks a merge case before any merge attempt",
           any(c.get("kind") == "merge" for c in eng.st.pending_cases.values())
           and calls["ff"] == 0, f"calls={calls} cases={eng.st.pending_cases}")
        eng._drive_gate("A-01", g)                    # grantless parked tick: holds quietly
        ok("T1 a grantless tick never attempts the merge (ASK gate intact)",
           calls["ff"] == 0, f"calls={calls}")
    finally:
        _restore_trunk(orig)


def t1_zero_gate_merge_across_the_whole_local_ladder():
    # AC-1 T1 bullet: local mode emits zero gate.merge messages across the whole ladder
    # (local -> non-ff -> rebase order -> landed -> trunk -> record).
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
    orig, _ = _stub_trunk(ff=(False, "not a fast-forward"))
    sent = _capture(eng)
    try:
        eng._drive_gate("A-01", g)                    # -> local (first order)
        eng._drive_gate("A-01", g, on_report=True)    # non-ff -> rebase order
        trunk.merge_ff_only = lambda *a, **k: (True, "")
        eng._drive_gate("A-01", g, on_report=True)    # rebase reported -> lands -> trunk
        eng._drive_gate("A-01", g, on_report=True)    # trunk evidence -> record
    finally:
        _restore_trunk(orig)
    ok("T1 the ladder walked local -> trunk -> record",
       g.get("stage") == "record", f"g={g}")
    ok("T1 zero gate.merge messages across the whole local ladder",
       not any(tid == "gate.merge" for tid, _ in sent), f"sent={sent}")


# ══ T2: one stage-order composer; deduped, never sent to a walled worker ══

def t2_all_sites_compose_through_the_one_helper():
    # AC-1 T2 bullet: all three sites (stage-emit tail, idle re-nudge, _post_unhold_nudge)
    # compose through the ONE helper — plus the two riders' callers (branch-gap direct
    # send R3-2, non-ff flag-stamp R3-1). Each site is driven with the composer swapped
    # for a recorder: the recorder firing (and no direct template emit appearing) proves
    # the site routes through the seam.
    # (a) the stage-emit tail
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": None, "pr": None})
    hits = []
    eng._send_gate_order = (lambda block, gg, stage, wid, force=False:
                            hits.append(("tail", stage, force)) or True)
    sent = _capture(eng)
    orig, _ = _stub_trunk(merged=False, exists=False)
    try:
        eng._drive_gate("A-01", g)                    # None -> local: a real advance
    finally:
        _restore_trunk(orig)
    ok("T2 (a) the stage-emit tail composes through the helper (force: a NEW stage)",
       hits == [("tail", "local", True)], f"hits={hits}")
    ok("T2 (a) no direct template emit bypasses the seam",
       not any(tid.startswith("gate.") for tid, _ in sent), f"sent={sent}")

    # (b) the gate idle re-nudge
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    hits = []
    eng._send_gate_order = (lambda block, gg, stage, wid, force=False:
                            hits.append(("nudge", stage, force)) or True)
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    orig, _ = _stub_trunk(merged=False, exists=False)
    try:
        eng._drive_gate("A-01", g)
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._drive_gate("A-01", g)
    finally:
        _restore_trunk(orig)
    ok("T2 (b) the idle re-nudge composes through the helper (never force)",
       ("nudge", "local", False) in hits, f"hits={hits}")

    # (c) _post_unhold_nudge
    eng = _eng()
    eng.st.gate["A-01"] = {"stage": "trunk", "pr": None}
    w = next(x for x in eng.st.workers if x["id"] == "ENG-A-01")
    hits = []
    eng._send_gate_order = (lambda block, gg, stage, wid, force=False:
                            hits.append(("unhold", stage, force)) or True)
    sent = _capture(eng)
    eng._post_unhold_nudge(w, "A-01")
    ok("T2 (c) _post_unhold_nudge composes through the helper",
       hits == [("unhold", "trunk", False)], f"hits={hits}")
    ok("T2 (c) no heartbeat fallback when the helper composed an order",
       not any(tid == "heartbeat.ping" for tid, _ in sent), f"sent={sent}")

    # (d) the branch-gap direct send (R3-2)
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    hits = []
    eng._send_gate_order = (lambda block, gg, stage, wid, force=False:
                            hits.append(("gap", stage, force)) or True)
    orig, _ = _stub_trunk(merged=False, exists=False)
    try:
        eng._drive_gate("A-01", g, on_report=True)    # done reported, no visible branch
    finally:
        _restore_trunk(orig)
    ok("T2 (d) the branch-gap direct send routes through the helper (R3-2, force=True: "
       "it already fired unconditionally)",
       ("gap", "local", True) in hits and g.get("branch_gap") is True, f"hits={hits} g={g}")

    # (e) the non-ff flag-stamp first send (R3-1)
    eng = _eng()
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    hits = []
    eng._send_gate_order = (lambda block, gg, stage, wid, force=False:
                            hits.append(("nonff", stage, force)) or True)
    orig, _ = _stub_trunk(ff=(False, "not a fast-forward"))
    try:
        eng._drive_gate("A-01", g, on_report=True)
    finally:
        _restore_trunk(orig)
    ok("T2 (e) the non-ff first rebase order goes out at flag-stamp time through the "
       "helper (R3-1, dedupe-safe)",
       ("nonff", "local", False) in hits and g.get("rebase_pending") is True,
       f"hits={hits} g={g}")


def t2_kind_keyed_dedupe_exactly_one_undelivered_rebase_order():
    # AC-1 T2 bullet: non-ff persisting N ticks -> exactly ONE undelivered rebase order
    # in the mailbox; a skipped send leaves nudged_at unset. Real mailbox + real hwm
    # (dry off): the dedupe reads the runner-owned .mbox-hwm consumed seq (F5).
    eng = _eng()
    eng.dry = False
    wid = "ENG-A-01"
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None,
                                        "approved_merge": True})   # grant held (F9)
    orig, calls = _stub_trunk(ff=(False, "not a fast-forward"))
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    mbox = jobs.mailbox_path(eng.ctx.worker_dir(wid))

    def rebase_lines():
        import json
        if not os.path.exists(mbox):
            return []
        return [json.loads(l) for l in open(mbox) if l.strip()
                and json.loads(l).get("kind") == "gate.rebase"]
    try:
        for _ in range(4):                            # per-tick retry while the grant holds
            eng._drive_gate("A-01", g)
        ok("T2 the engine retried the merge per tick while the grant was held",
           calls["ff"] == 4, f"calls={calls}")
        ok("T2 exactly ONE undelivered rebase order after N non-ff ticks (kind-keyed "
           "dedupe vs .mbox-hwm — the tron-26 20-copy backlog class is dead)",
           len(rebase_lines()) == 1, f"mbox={rebase_lines()}")
        # A deduped idle re-nudge never consumes the nudge budget.
        clock["t"] += eng._pace("gate_nudge_after", 2) + 1
        eng._drive_gate("A-01", g)
        ok("T2 a skipped (deduped) send leaves nudged_at unset — the re-check happens "
           "next tick", g.get("nudged_at") is None, f"g={g}")
        ok("T2 the skipped nudge really was skipped (still one copy)",
           len(rebase_lines()) == 1, f"mbox={rebase_lines()}")
        # The runner consumes the copy (writes its high-water) -> the next needed order
        # sends a FRESH copy: the dedupe is per-UNDELIVERED, never a permanent gag.
        with open(os.path.join(eng.ctx.worker_dir(wid), jobs.HWM), "w") as fh:
            fh.write(str(rebase_lines()[0]["seq"]))
        eng._drive_gate("A-01", g)
        ok("T2 a consumed copy un-gags the kind (fresh order after the hwm advances)",
           len(rebase_lines()) == 2, f"mbox={rebase_lines()}")
    finally:
        _restore_trunk(orig)


def t2_distinct_kinds_at_the_same_stage_never_cross_suppressed():
    # AC-1 T2 bullet: distinct kinds at the same stage (gate.local vs branch-gap vs the
    # rebase line) are never cross-suppressed — the dedupe key is the mailbox kind (F8),
    # never the stage name.
    import json
    eng = _eng()
    eng.dry = False
    wid = "ENG-A-01"
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    mbox = jobs.mailbox_path(eng.ctx.worker_dir(wid))

    def kinds():
        if not os.path.exists(mbox):
            return []
        return [json.loads(l).get("kind") for l in open(mbox) if l.strip()]
    ok("T2 setup: gate.local sent (undelivered)",
       eng._send_gate_order("A-01", g, "local", wid, force=True) is True
       and kinds() == ["gate.local"], f"kinds={kinds()}")
    ok("T2 an undelivered gate.local suppresses only ITS OWN kind",
       eng._send_gate_order("A-01", g, "local", wid) is False, f"kinds={kinds()}")
    g["branch_gap"] = True
    ok("T2 the branch-gap line still sends past the undelivered gate.local "
       "(kind key, not stage key)",
       eng._send_gate_order("A-01", g, "local", wid) is True
       and kinds() == ["gate.local", "gate.branch-gap"], f"kinds={kinds()}")
    g.pop("branch_gap")
    g["rebase_pending"] = True
    ok("T2 the rebase line still sends past both undelivered kinds",
       eng._send_gate_order("A-01", g, "local", wid) is True
       and kinds() == ["gate.local", "gate.branch-gap", "gate.rebase"],
       f"kinds={kinds()}")
    ok("T2 a second rebase order IS suppressed (its own kind is undelivered)",
       eng._send_gate_order("A-01", g, "local", wid) is False, f"kinds={kinds()}")


def t2_a_stage_advance_always_sends():
    # AC-1 T2 bullet: a NEW stage (real advance) always sends.
    import json
    eng = _eng()
    eng.dry = False
    wid = "ENG-A-01"
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    # An undelivered gate.local sits in the mailbox from the current stage…
    eng._send_gate_order("A-01", g, "local", wid, force=True)
    orig, _ = _stub_trunk(merged=True, exists=True, tip="MERGED123")
    try:
        eng._drive_gate("A-01", g)     # branch reached trunk -> stage advance -> trunk
    finally:
        _restore_trunk(orig)
    mbox = jobs.mailbox_path(eng.ctx.worker_dir(wid))
    kinds = [json.loads(l).get("kind") for l in open(mbox) if l.strip()]
    ok("T2 a stage ADVANCE always sends (gate.trunk landed despite the backlog)",
       g.get("stage") == "trunk" and "gate.trunk" in kinds, f"kinds={kinds} g={g}")


def t2_stage_advance_while_walled_no_send_unhold_delivers_new_stage():
    # AC-1 T2 bullets: a stage advance occurring WHILE the worker is walled updates
    # g["stage"] (no send — R2-3: suppression suppresses the SEND only), and un-hold
    # then delivers the NEW stage's order; a walled worker receives ZERO gate stage
    # orders while held.
    eng = _eng()
    wid = "ENG-A-01"
    eng.st.branches["A-01"] = "feat/A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    _wall(eng, "A-01", wid)
    sent = _capture(eng)
    tw = _capture_to_worker(eng)
    orig, _ = _stub_trunk(merged=True, exists=True, tip="MERGED123")
    try:
        eng._drive_gate("A-01", g)     # out-of-gate merge accepted -> advance to trunk
    finally:
        _restore_trunk(orig)
    ok("T2 the stage write ran while walled (bookkeeping never suppressed)",
       g.get("stage") == "trunk", f"g={g}")
    ok("T2 a walled worker receives ZERO gate stage orders while held",
       not any(tid.startswith("gate.") for tid, _ in sent) and not tw,
       f"sent={sent} tw={tw}")
    ok("T2 the walled-force send is refused inside the seam too",
       eng._send_gate_order("A-01", g, "trunk", wid, force=True) is False)
    # Un-hold -> the NEW stage's order is delivered.
    w = next(x for x in eng.st.workers if x["id"] == wid)
    eng._unhold_worker(w)
    eng._post_unhold_nudge(w, "A-01")
    ok("T2 un-hold delivers the NEW stage's order (gate.trunk, the stage that advanced "
       "while walled)", any(tid == "gate.trunk" for tid, _ in sent), f"sent={sent}")


def t2_branch_gap_gate_unholding_gets_the_branch_gap_line():
    # AC-1 T2 bullet: a branch-gap gate un-holding gets the branch-gap line, never
    # gate.local — the composer's byproduct fix (R2-1: _post_unhold_nudge had no
    # branch_gap awareness before the one seam existed).
    eng = _eng()
    eng.st.gate["A-01"] = {"stage": "local", "pr": None, "branch_gap": True}
    w = next(x for x in eng.st.workers if x["id"] == "ENG-A-01")
    sent = _capture(eng)
    tw = _capture_to_worker(eng)
    eng._post_unhold_nudge(w, "A-01")
    ok("T2 a branch-gap gate un-holding gets the branch-gap line",
       any(k == "gate.branch-gap" for _, _, k in tw), f"tw={tw}")
    ok("T2 …and never gate.local (the pre-composer divergence is dead)",
       not any(tid == "gate.local" for tid, _ in sent), f"sent={sent}")


def t2_changes_settle_still_lands_gate_changes_on_a_walled_worker():
    # AC-1 T2 bullet: a `changes` settle on a merge case whose worker is walled STILL
    # lands the gate.changes note in the mailbox — NEVER a blanket guard in
    # _to_worker/emit (F3: the D-16-1 swallow class; the mailbox is the only durable
    # channel and _post_unhold_nudge does not reconstruct settle-driven notices).
    eng = _eng()
    wid = "ENG-A-01"
    g = eng.st.gate.setdefault("A-01", {"stage": "local", "pr": None})
    cid = eng._open_case("A-01", "merge", wid, "merge A-01 to trunk")
    g["case_merge"] = cid
    _wall(eng, "A-01", wid)          # the worker is wall-held while its merge case parks
    tw = _capture_to_worker(eng)
    eng.dry = False                  # the changes arm guards on dry before _to_worker
    try:
        eng._h_apply_decision({"case": cid, "decision": "changes",
                               "detail": "tighten the diff first"})
    finally:
        eng.dry = True
    ok("T2 the operator's changes note STILL lands in the walled worker's mailbox",
       any(k == "gate.changes" and "tighten the diff first" in t for _, t, k in tw),
       f"tw={tw}")
    ok("T2 the gate awaits rework as before (settle semantics untouched)",
       g.get("awaiting_rework") is True, f"g={g}")


def t2_remote_ci_red_renudge_dedupes_until_consumed():
    # Impl-review adjudication 2 pin (NOTE 5): the remote CI-red arm keeps renudge=True
    # (the tail runs per tick) but the same-stage send goes through the kind-keyed
    # dedupe — at most one undelivered gate.merge; a consumed copy un-gags the kind and
    # the very next tick's renudge sends fresh. Flow control, never a gag, never the
    # tron-25 29-copy backlog class in remote mode either.
    import json
    eng = _eng()
    eng.dry = False
    eng.paths["remote"] = "origin"          # remote mode: the PR ladder owns the merge
    wid = "ENG-A-01"
    eng.st.branches["A-01"] = "feat/A-01"
    eng.st.data["open_prs"] = {"feat/A-01": {"number": 7, "checks": "failing"}}
    g = eng.st.gate.setdefault("A-01", {"stage": "ci", "pr": 7})
    mbox = jobs.mailbox_path(eng.ctx.worker_dir(wid))

    def merge_kinds():
        if not os.path.exists(mbox):
            return []
        return [json.loads(l) for l in open(mbox) if l.strip()
                and json.loads(l).get("kind") == "gate.merge"]
    for _ in range(3):
        eng._drive_gate("A-01", g)          # per-tick renudge while CI stays red
    ok("T2 remote CI-red: at most ONE undelivered gate.merge across N red ticks",
       len(merge_kinds()) == 1, f"mbox={merge_kinds()}")
    with open(os.path.join(eng.ctx.worker_dir(wid), jobs.HWM), "w") as fh:
        fh.write(str(merge_kinds()[0]["seq"]))
    eng._drive_gate("A-01", g)              # consumed -> the next renudge sends fresh
    ok("T2 remote CI-red: a consumed copy un-gags the kind (fresh order next tick)",
       len(merge_kinds()) == 2, f"mbox={merge_kinds()}")


# ══ T3: held-verb replay folds duplicate walls — at BOTH replay seams ══

def t3_resume_seam_folds_all_matching_echoes_zero_new_cases():
    # AC-1 T3 bullets (resume seam): 3 duplicate wall verbs matching the settled case ->
    # zero new cases, folded texts in the flow log, the worker never re-walled by a
    # fold, the remainder never re-queued by a fold. (Archival is claim-time, 01-18 T8.)
    eng = _eng()
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="the original wall")
    _queue_walls(eng, wid, [
        ("worker.wall", {"block": "A-01", "detail": "echo-one (re-send, unchanged)"}),
        ("worker.wall", {"block": "A-01", "detail": "echo-two (re-send, 2nd time)"}),
        ("worker.wall", {"block": "A-01", "detail": "echo-three (re-send, 3rd time)"}),
    ])
    logs = _capture_log(eng)
    eng._h_apply_decision({"case": cid, "decision": "resume", "block": "A-01"})
    eng._drain_triggers()              # folds emit nothing; prove it past the queue too
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("T3 resume: zero new cases from the three folded echoes (the CASE-004→012 "
       "treadmill is dead)",
       not any(c.get("kind") == "wall" for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")
    ok("T3 resume: the worker is un-held and never re-walled by a fold",
       w.get("status") != "walled", f"w={w}")
    ok("T3 resume: the remainder never re-queued by a fold (held_verbs empty)",
       not w.get("held_verbs"), f"w={w}")
    ok("T3 resume: every folded wall's text is in the flow log (mis-folds visible)",
       all(any(name == "flow" and "folded stale wall echo" in text and probe in text
               for name, text in logs)
           for probe in ("echo-one", "echo-two", "echo-three")), f"logs={logs}")


def t3_resume_seam_rule2_raise_requeues_the_rest_sender_first():
    # AC-1 T3 bullet (resume seam): a rule-2 fresh raise legitimately re-walls the worker
    # and re-queues the verbs behind it (R2-2). Impl-review I-2 pinned the reachable
    # model: admission resolves SENDER-FIRST, so a worker-sent wall can never name a
    # foreign block — the "novel-block raises separately" shape is unreachable; rule 2
    # fires when rule 1 has nothing to discriminate against (case is None here). The
    # wall is deliberately LABELED B-99 to pin the sender-first rewrite: the raised case
    # is for the worker's OWN block A-01.
    eng = _eng()
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="the original wall")
    _queue_walls(eng, wid, [
        ("worker.wall", {"block": "B-99", "detail": "a fresh blocker", "worker_id": wid}),
        ("worker.done", {"block": "A-01", "_raw": "done A-01 — local: evidence"}),
    ])
    eng.st.pending_cases.pop(cid)      # settle resolved by block, no case object (rule 1
    eng._h_apply_decision({"decision": "resume", "block": "A-01"})   # inert -> rule 2)
    eng._drain_triggers()              # the fresh raise is a queued trigger — drain it
    w = next(x for x in eng.st.workers if x["id"] == wid)
    new_walls = [c for c in eng.st.pending_cases.values() if c.get("kind") == "wall"]
    ok("T3 resume: exactly ONE new case from the rule-2 raise",
       len(new_walls) == 1 and "a fresh blocker" in (new_walls[0].get("detail") or ""),
       f"cases={eng.st.pending_cases}")
    ok("T3 resume: the case lands on the worker's OWN block — sender-first, never the "
       "raw B-99 label (I-2 model pin)",
       new_walls and new_walls[0].get("block") == "A-01", f"cases={eng.st.pending_cases}")
    ok("T3 resume: the fresh raise legitimately re-walls the worker mid-batch",
       w.get("status") == "walled", f"w={w}")
    ok("T3 resume: the verbs behind the fresh wall re-queue (they fold/replay at ITS "
       "settle)", [i.get("tag") for i in (w.get("held_verbs") or [])] == ["worker.done"],
       f"held={w.get('held_verbs')}")


def t3_resume_seam_blockless_and_mislabeled_echoes_fold_sender_first():
    # Impl-review I-2 + NOTE 5: rule 1's fold key is the SENDER-FIRST-resolved block —
    # a block-less echo (classify filled no ref on a "re-send, unchanged" line) and a
    # mislabeled echo both resolve to the worker's own block and FOLD; the raw-slot
    # compare would have let both escape into one-case-per-settle.
    eng = _eng()
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="the original wall")
    _queue_walls(eng, wid, [
        ("worker.wall", {"detail": "re-send, unchanged (no block ref)"}),
        ("worker.wall", {"block": "B-02", "detail": "same wall, mangled ref"}),
    ])
    logs = _capture_log(eng)
    eng._h_apply_decision({"case": cid, "decision": "resume", "block": "A-01"})
    eng._drain_triggers()
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("T3 sender-first fold: a BLOCK-LESS echo folds under rule 1 (never escapes into "
       "rule 2)", not any(c.get("kind") == "wall" for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")
    ok("T3 sender-first fold: the mislabeled echo folds too (both resolve to A-01)",
       sum(1 for name, text in logs
           if name == "flow" and "folded stale wall echo" in text) == 2, f"logs={logs}")
    ok("T3 sender-first fold: the worker is un-held, nothing re-queued",
       w.get("status") != "walled" and not w.get("held_verbs"), f"w={w}")


def t3_resume_seam_case_none_rule1_inert_rule2_collapses_newest_text():
    # AC-1 T3 bullets (resume seam): `case is None` -> rule 1 inert, rule 2 still
    # collapses, no crash; N same-worker+block walls -> one case, newest text.
    eng = _eng()
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="the original wall")
    _queue_walls(eng, wid, [
        ("worker.wall", {"block": "A-01", "detail": "wall v1"}),
        ("worker.wall", {"block": "A-01", "detail": "wall v2"}),
        ("worker.wall", {"block": "A-01", "detail": "wall v3 (newest)"}),
    ])
    # The settle resolves by BLOCK with no matching case object: pop the case so
    # _resolve_case comes back None while `block` still steers the resume arm.
    eng.st.pending_cases.pop(cid)
    eng._h_apply_decision({"decision": "resume", "block": "A-01"})
    eng._drain_triggers()              # the collapsed raise is a queued trigger
    w = next(x for x in eng.st.workers if x["id"] == wid)
    new_walls = [c for c in eng.st.pending_cases.values() if c.get("kind") == "wall"]
    ok("T3 resume/case-None: rule 1 inert, rule 2 collapses N walls to exactly ONE case",
       len(new_walls) == 1, f"cases={eng.st.pending_cases}")
    ok("T3 resume/case-None: the collapsed case carries the NEWEST text",
       "wall v3 (newest)" in (new_walls[0].get("detail") or "") if new_walls else False,
       f"cases={eng.st.pending_cases}")
    ok("T3 resume/case-None: the fresh raise re-walls the worker (a live wall owns the "
       "conversation)", w.get("status") == "walled", f"w={w}")
    ok("T3 resume/case-None: the collapsed case is keyed sender-first on the worker's "
       "own block", new_walls and new_walls[0].get("block") == "A-01",
       f"cases={eng.st.pending_cases}")


def t3_resume_seam_non_wall_verbs_replay_unchanged_in_arrival_order():
    # AC-1 T3 bullet: non-wall verbs replay exactly as today, in arrival order.
    eng = _eng()
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="the original wall")
    _queue_walls(eng, wid, [
        ("worker.wall", {"block": "A-01", "detail": "stale echo"}),
        ("worker.done", {"block": "A-01", "_raw": "done A-01 — local: evidence"}),
        ("worker.recorded", {"block": "A-01"}),
    ])
    replayed = []
    orig_ingest = eng._ingest

    def spy(tag, slots, sender):
        replayed.append(tag)
        return orig_ingest(tag, slots, sender)
    eng._ingest = spy
    eng._h_apply_decision({"case": cid, "decision": "resume", "block": "A-01"})
    ok("T3 resume: non-wall verbs replay unchanged, in arrival order (the echo folded "
       "ahead of them)", replayed == ["worker.done", "worker.recorded"],
       f"replayed={replayed}")


def _sweep_fixture(specs, settle="resume", case_block="A-01", parked=False):
    """A walled worker with held verbs and an already-SETTLED wall case the sweep's
    invariant arm (a) will act on (block_01_17/01_18 convention: dry off, clock owned).
    `case_block`: the settled case's block — "A-01" walls through the ordinary escalate
    path; anything else opens the case manually (a same-worker wall case for another
    ref, the rule-2 discriminator shape). `parked`: leave A-01 in st.blocked at arm-(a)
    time (the I-1 crash window: decision written, unblock never ran)."""
    ctx, _ = build(blocks=[("A-01", "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.dry = False
    wid = "ENG-A-01"
    eng.st.workers.append({"id": wid, "role": "engineer", "block": "A-01",
                           "session_id": "dry", "status": "idle"})
    eng._tq = []
    w = eng.st.workers[-1]
    if case_block == "A-01":
        eng._h_escalate({"block": "A-01", "worker_id": wid, "detail": "the original wall"})
        cid = next(c for c, v in eng.st.pending_cases.items() if v.get("kind") == "wall")
    else:
        eng._hold_worker(w)
        cid = eng._open_case(case_block, "wall", wid, "the original wall")
    _queue_walls(eng, wid, specs)
    eng.st.pending_cases[cid]["decision"] = settle    # settled; nothing un-held it (arm a)
    if parked:
        if "A-01" not in eng.st.blocked:
            eng.st.blocked.append("A-01")   # the settle's unblock never ran (I-1 window)
    elif "A-01" in eng.st.blocked:
        eng.st.blocked.remove("A-01")   # the settle's own unblock ran (tron-23 signature:
                                        # only the worker's un-hold was missed)
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    return eng, wid, cid, clock


def t3_sweep_seam_folds_all_matching_echoes_zero_new_cases():
    # AC-1 T3 bullets (sweep arm (a) — the treadmill's second door, F2/CASE-012):
    # 3 duplicate echoes -> zero new cases, folded texts logged, never re-walled,
    # remainder never re-queued.
    eng, wid, cid, clock = _sweep_fixture([
        ("worker.wall", {"block": "A-01", "detail": "sweep echo-one"}),
        ("worker.wall", {"block": "A-01", "detail": "sweep echo-two"}),
        ("worker.wall", {"block": "A-01", "detail": "sweep echo-three"}),
    ])
    logs = _capture_log(eng)
    eng._sweep()                       # anchors wall_bad_since
    clock["t"] += PING_WINDOW_S
    eng._sweep()                       # arm (a) fires: un-hold + fold + replay
    eng._drain_triggers()              # replayed raises are queued triggers — drain
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("T3 sweep: zero new cases from the folded echoes (CASE-012's door closed)",
       not any(c.get("kind") == "wall" for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")
    ok("T3 sweep: the worker is un-held and never re-walled by a fold",
       w.get("status") != "walled", f"w={w}")
    ok("T3 sweep: the remainder never re-queued by a fold",
       not w.get("held_verbs"), f"w={w}")
    ok("T3 sweep: every folded text is in the flow log",
       all(any(name == "flow" and "folded stale wall echo" in text and probe in text
               for name, text in logs)
           for probe in ("sweep echo-one", "sweep echo-two", "sweep echo-three")),
       f"logs={logs}")


def t3_sweep_seam_rule2_raise_requeues_the_rest():
    # AC-1 T3 bullet (sweep seam): a rule-2 raise -> exactly one new case; it re-walls
    # and re-queues the verbs behind it. Reachable model (I-2): the settled case is a
    # same-worker case for ANOTHER ref (B-77), so the A-01-resolving echo does not match
    # rule 1 and rule 2 raises it fresh — on the worker's own block, sender-first.
    eng, wid, cid, clock = _sweep_fixture([
        ("worker.wall", {"block": "B-99", "detail": "a fresh blocker via the sweep door",
                         "worker_id": "ENG-A-01"}),
        ("worker.done", {"block": "A-01", "_raw": "done A-01 — local: evidence"}),
    ], case_block="B-77")
    eng._sweep()
    clock["t"] += PING_WINDOW_S
    eng._sweep()
    eng._drain_triggers()              # the fresh raise is a queued trigger — drain it
    w = next(x for x in eng.st.workers if x["id"] == wid)
    new_walls = [c for c in eng.st.pending_cases.values() if c.get("kind") == "wall"]
    ok("T3 sweep: exactly ONE new case from the rule-2 raise",
       len(new_walls) == 1 and "a fresh blocker" in (new_walls[0].get("detail") or ""),
       f"cases={eng.st.pending_cases}")
    ok("T3 sweep: the case lands sender-first on the worker's own block (I-2 model pin)",
       new_walls and new_walls[0].get("block") == "A-01", f"cases={eng.st.pending_cases}")
    ok("T3 sweep: the fresh raise legitimately re-walls the worker",
       w.get("status") == "walled", f"w={w}")
    ok("T3 sweep: the verbs behind it re-queue for ITS settle",
       [i.get("tag") for i in (w.get("held_verbs") or [])] == ["worker.done"],
       f"held={w.get('held_verbs')}")


def t3_sweep_seam_swallowed_raise_never_strands_the_remainder():
    # Impl-review I-1 (the live repro, rule-2 door): the settled case is for another ref
    # AND A-01 is STILL in st.blocked (the settle's unblock never ran — crash window).
    # The rule-2 raise cannot land (_h_escalate's blocked-guard will swallow it at
    # drain) — the seam must NOT re-queue behind it: the done-report replays live
    # instead of stranding on the held_verbs of an un-walled worker.
    eng, wid, cid, clock = _sweep_fixture([
        ("worker.wall", {"detail": "block-less echo of some other trouble"}),
        ("worker.done", {"block": "A-01", "_raw": "done A-01 — local: evidence"}),
    ], case_block="B-77", parked=True)
    replayed = []
    orig_ingest = eng._ingest

    def spy(tag, slots, sender):
        replayed.append(tag)
        return orig_ingest(tag, slots, sender)
    eng._ingest = spy
    eng._sweep()
    clock["t"] += PING_WINDOW_S
    eng._sweep()
    eng._drain_triggers()
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("T3/I-1 sweep: the remainder is NEVER stranded behind a raise that cannot land "
       "(held_verbs empty)", not w.get("held_verbs"), f"w={w}")
    ok("T3/I-1 sweep: the done-report replayed live (not lost)",
       "worker.done" in replayed, f"replayed={replayed}")
    ok("T3/I-1 sweep: the worker is un-held (the swallowed raise walls nobody)",
       w.get("status") != "walled", f"w={w}")
    ok("T3/I-1 sweep: no phantom case (the guard-swallow is honest, pre-existing shape)",
       not any(c.get("kind") == "wall" for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")


def t3_sweep_seam_parked_block_keeps_an_operator_handle_via_the_blocked_arm():
    # Impl-review I-1 repro (a) + NOTE 5: the reviewer's literal shape — settled case for
    # A-01, A-01 still parked, a BLOCK-LESS echo (the I-2 escape shape) plus a done
    # behind it. Post-patch: the echo folds sender-first (rule 1), the done replays
    # live, nothing strands — and the parked-block-with-no-case residue is picked up by
    # the blocked-list invariant arm (01-18 T6), which re-raises the operator handle
    # one window later. No case-unreachable parked block survives.
    # (Echo-only queue: a replayed done-report would open a fresh gate for A-01, which
    # legitimately COVERS the block for the T6 arm — the gate's own nets own it then.
    # The done-behind-a-swallowed-raise no-strand half lives in the rule-2 test above.)
    eng, wid, cid, clock = _sweep_fixture([
        ("worker.wall", {"detail": "re-send, unchanged (no block ref)"}),
    ], parked=True)
    eng._sweep()                       # anchors wall_bad_since
    clock["t"] += PING_WINDOW_S
    eng._sweep()                       # arm (a): un-hold; the echo FOLDS (rule 1, I-2)
    eng._drain_triggers()
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("T3/I-1 sweep: the block-less echo folded (I-2) — no strand, nothing re-queued",
       not w.get("held_verbs") and w.get("status") != "walled", f"w={w}")
    ok("setup: the parked block sits case-less after the fold (the T6 arm's shape)",
       "A-01" in eng.st.blocked
       and not any(c.get("decision") is None for c in eng.st.pending_cases.values()),
       f"blocked={eng.st.blocked} cases={eng.st.pending_cases}")
    clock["t"] += PING_WINDOW_S
    eng._sweep()                       # the blocked-list arm re-raises the handle
    ok("T3/I-1 sweep: the operator handle is preserved — the blocked-list invariant arm "
       "re-raises a fresh case for the parked block",
       any(c.get("kind") == "wall" and c.get("block") == "A-01"
           and c.get("decision") is None for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")


def t3_sweep_seam_collapses_non_matching_walls_to_newest_text():
    # AC-1 T3 bullet (sweep seam): N same-worker+block NON-matching walls -> one case,
    # newest text (rule 2 discriminates against the settled case — here a same-worker
    # case for ANOTHER ref, the reachable non-matching shape under sender-first I-2;
    # the raw B-99/blockless labels all resolve to A-01, one group).
    eng, wid, cid, clock = _sweep_fixture([
        ("worker.wall", {"block": "B-99", "detail": "novel v1", "worker_id": "ENG-A-01"}),
        ("worker.wall", {"detail": "novel v2 (block-less)"}),
        ("worker.wall", {"block": "B-99", "detail": "novel v3 (newest)",
                         "worker_id": "ENG-A-01"}),
    ], case_block="B-77")
    eng._sweep()
    clock["t"] += PING_WINDOW_S
    eng._sweep()
    eng._drain_triggers()
    new_walls = [c for c in eng.st.pending_cases.values() if c.get("kind") == "wall"]
    ok("T3 sweep: N non-matching walls collapse to exactly ONE case",
       len(new_walls) == 1, f"cases={eng.st.pending_cases}")
    ok("T3 sweep: the collapsed case carries the NEWEST text",
       "novel v3 (newest)" in (new_walls[0].get("detail") or "") if new_walls else False,
       f"cases={eng.st.pending_cases}")
    ok("T3 sweep: the collapsed case lands sender-first on A-01",
       new_walls and new_walls[0].get("block") == "A-01", f"cases={eng.st.pending_cases}")


# ══ T4: operator-relay honesty ══

def t4_operator_directive_emits_the_not_relayed_notice_and_still_side_logs():
    # AC-1 T4 bullet: an operator line classified operator.directive (-> best_effort,
    # the OBSERVED death path — F1) emits the not-relayed notice and still side-logs.
    eng = _eng()
    sent = _capture(eng)
    logs = _capture_log(eng)
    eng._ingest("operator.directive",
                {"detail": "For ENG-A-01: please rebase and hold"},
                {"kind": "operator"})
    ok("T4 operator.directive emits the not-relayed notice (escalate.unclassified)",
       any(tid == "escalate.unclassified" and "not relayed" in (s.get("detail") or "")
           for tid, s in sent), f"sent={sent}")
    ok("T4 the notice names the levers that DO reach a worker (never 'gate orders only' "
       "— F11)", any("settle-driven notices" in (s.get("detail") or "")
                     for tid, s in sent if tid == "escalate.unclassified"), f"sent={sent}")
    ok("T4 the line still side-logs (today's forensic record, unchanged)",
       any(name == "side" and "best_effort" in text for name, text in logs),
       f"logs={logs}")


def t4_operator_knob_change_gets_the_same_notice_through_the_adjacent_door():
    # AC-1 T4 bullet: operator.knob_change (-> edit_self, the same side-log-only handler
    # class — R2-5) emits the same notice: one misclassification away from the identical
    # silent death, guarded as a class, not an enumerated handler.
    eng = _eng()
    sent = _capture(eng)
    eng._ingest("operator.knob_change",
                {"detail": "set gate_idle_cap to 5"},
                {"kind": "operator"})
    ok("T4 operator.knob_change emits the not-relayed notice too (handler class, R2-5)",
       any(tid == "escalate.unclassified" and "not relayed" in (s.get("detail") or "")
           for tid, s in sent), f"sent={sent}")


def t4_non_operator_best_effort_line_stays_quiet():
    # AC-1 T4 bullet: a non-operator best_effort line keeps today's quiet side-log —
    # the discriminator is sender KIND (R2-9), never slots.
    eng = _eng()
    sent = _capture(eng)
    eng._side("best_effort", {"detail": "worker chatter", "worker_id": "ENG-A-01"},
              {"kind": "worker", "id": "ENG-A-01"})
    ok("T4 a non-operator best_effort line stays quiet (side-log only)",
       not any(tid == "escalate.unclassified" for tid, _ in sent), f"sent={sent}")


def t4_no_settle_match_notice_carries_the_same_clause():
    # AC-1 T4 bullet: a no-settle-match operator line gets the same not-relayed clause
    # (the secondary path, same wording — one shared string, no drift).
    eng = _eng()
    sent = _capture(eng)
    eng._h_apply_decision({"case": "CASE-999", "decision": "resume"})
    ok("T4 the no-settle-match notice still fires (D-15-3 unchanged)",
       any(tid == "escalate.unclassified" and "matches no pending case"
           in (s.get("detail") or "") for tid, s in sent), f"sent={sent}")
    ok("T4 …and now carries the not-relayed clause",
       any("not relayed" in (s.get("detail") or "")
           for tid, s in sent if tid == "escalate.unclassified"), f"sent={sent}")


def t4_resolved_blockless_settle_still_emits_no_false_no_match():
    # AC-1 T4 bullet: a resolved block-less settle still emits no false "no match"
    # (the 01-18 T4 regression guard holds through this change).
    eng = _eng()
    wid = "ENG-A-01"
    for kind in ("paperwork", "residue"):
        cid = eng._open_case(None, kind, wid, f"{kind} unlandable — operator call")
        sent = _capture(eng)
        eng._h_apply_decision({"case": cid, "decision": "resume"})
        ok(f"T4 a resolved block-less '{kind}' settle emits no false no-match notice",
           not any(tid == "escalate.unclassified" for tid, _ in sent), f"sent={sent}")
        ok(f"T4 the '{kind}' case still closes as before", cid not in eng.st.pending_cases)


def main():
    for fn in sorted(k for k in globals() if k.startswith("t1_") or k.startswith("t2_")
                     or k.startswith("t3_") or k.startswith("t4_")):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
