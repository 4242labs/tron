"""replay_lock_test — T3 (01-26, behavior-lock).

WHAT THIS ACTUALLY IS (fix-cycle-1 correction): the 01-26 spec text says this fixture
is "built on the existing replay.py from 02-02". That is infeasible as written —
`tron-meta/experiments/replay.py` is a git-trunk DISPATCH-ORDER tool (it replays which
block gets picked next off trunk state); it has no way to feed a recorded MESSAGE
STREAM into this engine's `_ingest`/`_drain_triggers` pipeline. That mismatch is the
architect's spec defect to reconcile, not something this file can paper over by
pretending to use a module it structurally cannot use.

What this file DOES instead, and what actually satisfies AC-4's intent ("a replayed
past-defect stream produces the SAME outcome pre- and post-consolidation"):

  1. `t_*` — single-version REGRESSION checks. Each recorded/synthetic scenario below
     replayed through the CURRENT (post-01-26) engine only, asserting the known-correct
     outcome. These catch a regression in isolation but, on their own, cannot prove
     "same as before 01-26" — they have nothing pre-consolidation to compare against.

  2. `t_ab_*` — the genuine A/B BEHAVIOR DIFFERENTIAL. Each of the SAME recorded
     scenarios is run through BOTH engine versions IN-PROCESS: the post-consolidation
     `fsm.Engine` (this checkout) and the pre-consolidation `Engine` loaded fresh from
     `git show 28224cb:engine/fsm.py` (28224cb is exactly 01-26's parent commit,
     28224cb — the fsm.py as it stood immediately before this block's T1/T2/T5 touched
     it). The pre-version is written to a throwaway file and loaded via `importlib`
     under a DISTINCT module name (`fsm_pre_01_26`), never replacing `fsm` in
     `sys.modules` — the two Engine classes coexist and are driven side by side. Every
     other engine module (util/jobs/judge/reader/trunk/eventlog/state/render) is
     unchanged by 01-26, so both Engine classes share them unmodified — fsm.py is the
     only moving part, which is exactly what a differential needs to isolate. The
     comparison then asserts case-kind, escalation, and pacing-decision outcomes are
     IDENTICAL between the two versions — with TWO deliberate, named exceptions: T2
     (R-05) intentionally renames a gate-giveup case's `kind` from the pre-consolidation
     generic `'wall'` bucket to its own code (e.g. `'gate-contradiction'`) — that is the
     block's own stated purpose, not a regression, and the differential asserts that
     exact narrow divergence rather than pretending it doesn't exist. `gate-step-cap`,
     deliberately left unsplit, IS asserted byte-identical (kind=='wall' in both).
     SECOND exception (block 01-31, ADR-0002 D3): every wall now routes architect-first
     — with no architect online (this fixture's shape), `_h_escalate`'s fallback is
     `_triage_to_architect`'s own no-architect arm, which pages via
     `escalate.unclassified` rather than the pre-01-31 direct `escalate.wall`. The
     differential asserts case count and held-worker status stay byte-identical, and
     that exactly ONE page fires either way — naming the page-EVENT-NAME divergence
     explicitly rather than silently reconciling it (see
     `t_ab_treadmill_identical_pre_post`).

  `git show 28224cb:...` reads a LOCAL git object already fetched into this repo's
  ODB (no network at test time — same "no tokens, no network" guarantee as every other
  block_NN_test.py). If that read ever fails (28224cb ref missing, no git present),
  the affected t_ab_* case fails LOUDLY (via main()'s per-test capture below) rather
  than silently skipping the differential.

PROVENANCE of the recorded scenarios (unchanged from the original cut): `at`
timestamps, case ids, block ids, and `detail` strings below are transcribed VERBATIM
from a REAL past run's own recorded event stream: `runs/*/executor.jsonl` inside
`tron-meta/sims/reports/trivial-tip-converter-trivial-tron-26-20260704T123735Z-6bccc14/`
(this repo's TRON toolchain, a sibling of this checkout — read-only, never re-executed;
no live sim runs here, ever). That run is the historical CASE-004->012 wall treadmill
(9 consecutive `PAGE reason=wall` records on ONE block/row inside ~80 minutes, the exact
tron-26 incident 01-19/01-24's fixes target) plus a genuine `gate-contradiction`
escalation and a `gate-step-cap` ("stuck at local after 3 attempts") escalation on a
later block. The A/B differential (`t_ab_*`) locks the two behaviors 01-26 changes that
these recorded streams actually reach: the case-kind split (T2) and the treadmill
collapse-to-one-case (T5). It does NOT exercise T1's idle-cap/nudge wall-clock arithmetic —
every recorded scenario walls the worker before any timer accrues, so the consolidated
`_pace_ladder` short-circuits on its `if not idle` branch; T1's pacing arithmetic stays
covered by the pre-existing per-call-site tests (`block_01_1X_test.py`, 13 of which catch a
`_pace_ladder` cap/nudge regression — independently verified). Embedded as literals (not a runtime
file read) so this fixture is fully deterministic and never depends on tron-meta being
present on disk (a fresh tron-app checkout, CI, etc.).

This is NOT a live sim / TRON-over-a-sim-project run (AC-7, explicitly deferred) — every
case here drives the Engine's own deterministic units directly, in TRON_DRY, exactly like
every other block_NN_test.py in this suite.

Run: python3 engine/replay_lock_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import tempfile
import subprocess
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

from fsm import Engine, WALL_KINDS   # noqa: E402  (post-consolidation engine, this checkout)
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── load the pre-consolidation engine (28224cb:engine/fsm.py — 01-26's own parent
# commit) as an independent module, so t_ab_* can drive it side by side with the
# post-consolidation `fsm.Engine` above ──
_PRE_MODULE_NAME = "fsm_pre_01_26"
_pre_module_cache = []


def _pre_engine_module():
    """Returns the pre-01-26 fsm module (Engine class only differs in fsm.py; every
    other engine module is shared, unchanged). Loaded once, cached for the process."""
    if _pre_module_cache:
        return _pre_module_cache[0]
    blob = subprocess.run(
        ["git", "-C", ROOT, "show", "28224cb:engine/fsm.py"],
        capture_output=True, text=True, check=True).stdout
    tmpdir = tempfile.mkdtemp(prefix="tron-fsm-pre-01-26-")
    path = os.path.join(tmpdir, _PRE_MODULE_NAME + ".py")
    with open(path, "w") as f:
        f.write(blob)
    spec = importlib.util.spec_from_file_location(_PRE_MODULE_NAME, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_PRE_MODULE_NAME] = mod
    spec.loader.exec_module(mod)
    _pre_module_cache.append(mod)
    return mod


def _eng_for(engine_cls, block="01-adhoc-review-fixes"):
    ctx, _ = build(blocks=[(block, "🔄", "none")])
    eng = engine_cls(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _eng(block="01-adhoc-review-fixes"):
    return _eng_for(Engine, block)


# The recorded tron-26 treadmill: 9 `PAGE reason=wall` records, same case-shape
# (block="01-adhoc-review-fixes", detail="wall"), roughly 20-40s apart, spanning
# 2026-07-04T13:39:13Z .. 2026-07-04T14:59:03Z (executor.jsonl, cases CASE-004..CASE-012).
_TRON26_TREADMILL_CASES = 9

# The recorded gate-contradiction escalation on the NEXT block in that same run
# (executor.jsonl, CASE-014, 2026-07-04T15:24:55Z) — a genuine trunk-history regression,
# not a worker stall.
_TRON03UI_CONTRADICTION_DETAIL = (
    "gate-contradiction at 'trunk': merged sha c99e953 no longer in trunk history "
    "(force-push or reset?)")

# The recorded gate-step-cap escalation later in the SAME run (executor.jsonl, CASE-015,
# 2026-07-04T15:28:01Z) — repeated no-advance reports at one DONE-gate stage.
_TRON03UI_STEPCAP_DETAIL = "stuck at local after 3 attempts"


def t_treadmill_stream_collapses_to_one_case():
    """Replay the RECORDED shape of the tron-26 treadmill — the engine repeatedly
    re-observing the SAME wall condition on the SAME block, tick after tick, with no
    settle in between (exactly what a stuck worker/root cause looks like from the
    engine's own vantage) — through the current (T1/T2/T5-consolidated) engine. The
    idempotency guard `_h_escalate`'s `if block and block in self.st.blocked: return`
    must still collapse every re-observation into the ONE case already parked — never
    the historical 9-case treadmill. Single-version regression check; see t_ab_treadmill
    below for the pre/post differential this alone cannot prove."""
    eng = _eng()
    wid = "ENG-01-adhoc-review-fixes"
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
               sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    eng.dry = False
    try:
        for _ in range(_TRON26_TREADMILL_CASES):
            eng._tq = []
            eng._ingest("worker.wall", {"block": "01-adhoc-review-fixes", "detail": "wall"},
                       {"kind": "worker", "id": wid})
            eng._drain_triggers()
    finally:
        eng.dry = True
    wall_cases = [c for c in eng.st.pending_cases.values()
                 if c.get("kind") in WALL_KINDS and c.get("block") == "01-adhoc-review-fixes"]
    ok(f"T3 {_TRON26_TREADMILL_CASES} recorded re-observations collapse to exactly ONE "
       f"case (never the historical treadmill)", len(wall_cases) == 1, f"cases={wall_cases}")
    # 01-31 (ADR-0002 D3): architect-first, always — with no architect online (this
    # fixture's shape), the page fires via _triage_to_architect's no-architect fallback
    # (escalate.unclassified), never the pre-01-31 direct escalate.wall. Either way,
    # exactly ONE page for the whole collapsed treadmill, never once per re-observation.
    ok("T3 the operator was paged exactly once, not once per re-observation",
       sum(1 for tid, _ in sent if tid in ("escalate.wall", "escalate.unclassified")) == 1,
       f"sent={sent}")
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("T3 the worker is held exactly once (never re-held on each repeat)",
       w.get("status") == "walled", f"w={w}")


def t_recorded_gate_contradiction_replays_to_its_own_named_kind():
    """Replay the RECORDED gate-contradiction detail (verbatim historical text) through
    `_gate_giveup` directly (the trunk-ancestry contradiction arm's own call shape,
    fsm.py `_drive_gate`) and confirm T2's case-kind split holds under a genuine
    historical string: the resulting case names itself 'gate-contradiction', not the old
    generic 'wall' bucket, and the ordinary settle/hold mechanics (WALL_KINDS) still
    apply to it unchanged. Single-version regression check."""
    eng = _eng("01-03-ui")
    wid = "ENG-01-03-ui"
    eng.st.workers.append({"id": wid, "role": "engineer", "block": "01-03-ui",
                           "session_id": "dry", "status": "working"})
    g = eng.st.gate.setdefault("01-03-ui", {"stage": "trunk", "pr": None})
    eng._gate_giveup("01-03-ui", g, wid, _TRON03UI_CONTRADICTION_DETAIL,
                     "gate-contradiction", "audit trunk history; re-validate or reassign")
    eng._drain_triggers()
    cid, case = next(((cid, c) for cid, c in eng.st.pending_cases.items()
                      if c.get("block") == "01-03-ui"), (None, None))
    ok("T3 the recorded contradiction replays to its own named case kind",
       case is not None and case.get("kind") == "gate-contradiction", f"case={case}")
    ok("T3 the case still carries the exact recorded detail text",
       case is not None and case.get("detail") == _TRON03UI_CONTRADICTION_DETAIL,
       f"case={case}")
    # Ordinary settle mechanics (WALL_KINDS) still resolve it — a resume un-holds exactly
    # like any other wall-family case, same outcome pre- and post-split.
    eng._h_apply_decision({"case": cid, "decision": "resume", "block": "01-03-ui"})
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("T3 the split case still settles through the ordinary resume path",
       w.get("status") != "walled" and cid not in eng.st.pending_cases, f"w={w}")


def t_recorded_gate_step_cap_stays_unsplit():
    """Replay the RECORDED gate-step-cap detail (verbatim historical text, the SAME run's
    next escalation) — `gate-step-cap` is deliberately the ONE _gate_giveup code the 01-26
    spec does NOT name among the seven to split; this proves that call remains bucketed as
    the generic 'wall' kind, exactly as before (WALL_KINDS still finds it for hold/settle,
    but its case.kind is not distinguished — a recorded, intentional non-split, not an
    oversight). Single-version regression check."""
    eng = _eng("01-03-ui")
    wid = "ENG-01-03-ui"
    eng.st.workers.append({"id": wid, "role": "engineer", "block": "01-03-ui",
                           "session_id": "dry", "status": "working"})
    g = eng.st.gate.setdefault("01-03-ui", {"stage": "local", "pr": None})
    eng._gate_giveup("01-03-ui", g, wid, _TRON03UI_STEPCAP_DETAIL,
                     "gate-step-cap", "advance DONE gate stage 'local'")
    eng._drain_triggers()
    case = next((c for c in eng.st.pending_cases.values()
                if c.get("block") == "01-03-ui"), None)
    ok("T3 gate-step-cap stays the generic 'wall' kind (not one of the seven split codes)",
       case is not None and case.get("kind") == "wall", f"case={case}")


# ── t_ab_* — the genuine pre/post behavior differential (AC-4) ──

def _replay_treadmill(engine_cls):
    eng = _eng_for(engine_cls)
    wid = "ENG-01-adhoc-review-fixes"
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
               sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    eng.dry = False
    try:
        for _ in range(_TRON26_TREADMILL_CASES):
            eng._tq = []
            eng._ingest("worker.wall", {"block": "01-adhoc-review-fixes", "detail": "wall"},
                       {"kind": "worker", "id": wid})
            eng._drain_triggers()
    finally:
        eng.dry = True
    # A plain worker.wall never routes through _gate_giveup, so its kind is the literal
    # 'wall' string in BOTH engine versions (T2's split only ever touches _gate_giveup's
    # seven codes) — safe to compare with the literal, no WALL_KINDS needed pre-side.
    wall_cases = [c for c in eng.st.pending_cases.values()
                 if c.get("kind") == "wall" and c.get("block") == "01-adhoc-review-fixes"]
    w = next(x for x in eng.st.workers if x["id"] == wid)
    # 01-31 (ADR-0002 D3, the SECOND named divergence — see module docstring): the
    # post-engine pages via escalate.unclassified (architect-first, no-architect
    # fallback), the pre-engine via the direct escalate.wall. n_pages counts either —
    # the divergence itself is asserted separately, by engine_cls, in the caller.
    return {"n_cases": len(wall_cases),
            "n_pages": sum(1 for tid, _ in sent
                          if tid in ("escalate.wall", "escalate.unclassified")),
            "worker_status": w.get("status")}


def _replay_gate_contradiction(engine_cls):
    eng = _eng_for(engine_cls, "01-03-ui")
    wid = "ENG-01-03-ui"
    eng.st.workers.append({"id": wid, "role": "engineer", "block": "01-03-ui",
                           "session_id": "dry", "status": "working"})
    g = eng.st.gate.setdefault("01-03-ui", {"stage": "trunk", "pr": None})
    eng._gate_giveup("01-03-ui", g, wid, _TRON03UI_CONTRADICTION_DETAIL,
                     "gate-contradiction", "audit trunk history; re-validate or reassign")
    eng._drain_triggers()
    cid, case = next(((cid, c) for cid, c in eng.st.pending_cases.items()
                      if c.get("block") == "01-03-ui"), (None, None))
    kind = case.get("kind") if case else None
    detail = case.get("detail") if case else None
    eng._h_apply_decision({"case": cid, "decision": "resume", "block": "01-03-ui"})
    w = next(x for x in eng.st.workers if x["id"] == wid)
    return {"kind": kind, "detail": detail,
            "settled_worker_status": w.get("status"),
            "case_cleared": cid not in eng.st.pending_cases}


def _replay_gate_step_cap(engine_cls):
    eng = _eng_for(engine_cls, "01-03-ui")
    wid = "ENG-01-03-ui"
    eng.st.workers.append({"id": wid, "role": "engineer", "block": "01-03-ui",
                           "session_id": "dry", "status": "working"})
    g = eng.st.gate.setdefault("01-03-ui", {"stage": "local", "pr": None})
    eng._gate_giveup("01-03-ui", g, wid, _TRON03UI_STEPCAP_DETAIL,
                     "gate-step-cap", "advance DONE gate stage 'local'")
    eng._drain_triggers()
    case = next((c for c in eng.st.pending_cases.values()
                if c.get("block") == "01-03-ui"), None)
    return {"kind": case.get("kind") if case else None,
            "detail": case.get("detail") if case else None}


def t_ab_treadmill_identical_pre_post():
    """The genuine A/B differential (AC-4): the recorded 9-case treadmill stream run
    through BOTH the pre-01-26 engine (28224cb:engine/fsm.py, loaded fresh) and the
    post-01-26 engine (this checkout) must collapse to the exact same outcome — one
    case, one page, one hold. No T2 kind divergence is possible here (a plain
    worker.wall never reaches _gate_giveup), so this one is byte-identical, no carve-out."""
    pre_mod = _pre_engine_module()
    pre = _replay_treadmill(pre_mod.Engine)
    post = _replay_treadmill(Engine)
    ok("A/B pre/post: treadmill outcome IDENTICAL pre- vs post-consolidation "
       "(case count, page count, held-worker status)",
       pre == post, f"pre={pre} post={post}")


def t_ab_gate_step_cap_identical_pre_post():
    """The genuine A/B differential (AC-4): gate-step-cap is deliberately left UNSPLIT
    by T2 — its case kind must stay the literal 'wall' bucket in BOTH engine versions,
    byte-identical, no carve-out."""
    pre_mod = _pre_engine_module()
    pre = _replay_gate_step_cap(pre_mod.Engine)
    post = _replay_gate_step_cap(Engine)
    ok("A/B pre/post: gate-step-cap case kind/detail IDENTICAL pre- vs "
       "post-consolidation ('wall' both — T2 does not touch this code)",
       pre == post, f"pre={pre} post={post}")


def t_ab_gate_contradiction_equivalent_pre_post():
    """The genuine A/B differential (AC-4) for the ONE code T2 (R-05) deliberately
    changes: gate-contradiction's case `kind` goes from the pre-consolidation generic
    'wall' bucket to its own named code post-consolidation — that IS the block's stated
    purpose, so it is asserted as the exact, sole, named divergence rather than papered
    over as 'identical'. Everything else — the recorded detail text and the ordinary
    settle mechanics (resume clears the case + un-holds the worker) — must still be
    byte-identical between the two engine versions."""
    pre_mod = _pre_engine_module()
    pre = _replay_gate_contradiction(pre_mod.Engine)
    post = _replay_gate_contradiction(Engine)
    ok("A/B pre/post: gate-contradiction kind is the pre-consolidation generic 'wall' "
       "BEFORE, its own named kind AFTER (T2's intended, and ONLY, divergence)",
       pre["kind"] == "wall" and post["kind"] == "gate-contradiction",
       f"pre={pre} post={post}")
    pre_rest = {k: v for k, v in pre.items() if k != "kind"}
    post_rest = {k: v for k, v in post.items() if k != "kind"}
    ok("A/B pre/post: everything BESIDES the T2 kind rename is IDENTICAL "
       "(recorded detail text, settle mechanics, worker status)",
       pre_rest == post_rest, f"pre={pre_rest} post={post_rest}")


def main():
    for fn in sorted(k for k in globals() if k.startswith("t_")):
        try:
            globals()[fn]()
        except Exception as e:
            ok(f"{fn} raised", False, repr(e))
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
