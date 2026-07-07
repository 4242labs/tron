r"""block_01_29_test — cut the never-observed worker-`retract` verb + its coupled
provenance guard (`_own_wall`), and prove nothing that matters moved (block 01-29,
ADR-tron-post-wave1-enhancements.md §C).

  T1  `_h_retract` (fsm.py, formerly def'd ~1308) and every retract site — the
      REPORT_VERBS tags-map entry, the walled-sender bypass in `_ingest`, the
      `retract_own_wall` side dispatch, the routing.yaml `worker.retract` row, and the
      bare `retract` in scripts/report.sh's tag enum + worker-contract.md — are gone.
  T2  the coupled provenance guard `_own_wall` (01-26 T5, FU-01-24a) is gone too,
      INCLUDING the `worker.wall` ingest stamp — but the `self._emit(...)` wall-trigger
      line it used to gate survived untouched (still fires on every `worker.wall`,
      stamped or not — there is no other caller of `_own_wall` left anywhere).
  T3  F-1 (a stale wall on already-settled/already-done work must self-clear, zero
      operator page) stays closed WITHOUT retract: the real fix was always the
      engine-OBSERVED `_sweep_wall_invariant` (fsm.py ~3488), independent of
      `_h_retract` — untouched by this block, proven here.

AC-2 (exact grep, must be EMPTY):
  grep -n "_own_wall\|_h_retract\|worker.retract\|retract_own_wall" \
       engine/fsm.py routing.yaml scripts/report.sh

AC-4 (no net behavior change to settle/wall lifecycle beyond retract removal) is a
light canary here — report.sh grammar, content-carrying settle, `--kind` routing,
negation-detection, fleet-hold, and F-4 each already have full dedicated coverage
elsewhere in the suite (block_01_24_test.py, block_01_20_test.py, block_01_27_test.py);
this file only proves each seam is still THERE post-cut, not a duplicate of their
depth.

Run: python3 engine/block_01_29_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

from fsm import (  # noqa: E402
    Engine, SPEC_OWNABLE_KINDS, GATE_GIVEUP_SPLIT_CODES, WALL_KINDS,
)
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── fixture builders (block_01_18_test/block_01_24_test convention) ──
def _eng(block="A-01", status="🔄"):
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _arch_idle(eng):
    w = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
         "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
    eng.st.workers.append(w)
    return w


def _wall(eng, block, wid, detail="flaky ci", kind=None):
    """Raise a wall against an already-rostered worker THROUGH THE REAL PIPELINE
    (`worker.wall` -> the deferred `wall:raised:<block>` trigger -> `_drain_triggers`
    -> `_h_escalate`) — same convention as block_01_24_test.py's `_wall`. Returns the
    parked case id."""
    eng._tq = []
    slots = {"block": block, "detail": detail}
    if kind:
        slots["kind"] = kind
    eng._ingest("worker.wall", slots, {"kind": "worker", "id": wid})
    eng._drain_triggers()
    return next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")


def _capture(eng):
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
                sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


def _capture_to_worker(eng):
    sent = []
    eng._to_worker = lambda wid, text, kind: sent.append((wid, text, kind))
    return sent


# ══════════════════════════════════════════════════════════════════════════════════
# AC-1/AC-2: the verb + its provenance guard are structurally gone
# ══════════════════════════════════════════════════════════════════════════════════

def ac2_grep_is_empty():
    r = subprocess.run(
        ["grep", "-n", r"_own_wall\|_h_retract\|worker.retract\|retract_own_wall",
         "engine/fsm.py", "routing.yaml", "scripts/report.sh"],
        cwd=ROOT, capture_output=True, text=True)
    ok("AC-2 the exact grep for every retract/_own_wall site is EMPTY "
       "(fsm.py, routing.yaml, scripts/report.sh)",
       r.returncode == 1 and r.stdout == "", f"rc={r.returncode} stdout={r.stdout!r}")


def ac1_h_retract_is_gone_from_the_engine_class():
    eng = _eng()
    ok("AC-1 _h_retract no longer exists as a bound method",
       getattr(eng, "_h_retract", None) is None)


def ac1_retract_report_tag_is_dropped_never_reaches_the_engine():
    """The structured `--tag retract` verb no longer resolves — report.sh still ACCEPTS
    an arbitrary tag string (it does no vocabulary checking itself, T1 (01-24 F-1a)'s
    grammar gate is only about flag POSITION), but `_structured`/REPORT_VERBS on the
    engine side now silently drops it as an unknown verb — never a trigger, never a
    guess, exactly the existing unknown-verb law (never a crash, never a false wall)."""
    d = tempfile.mkdtemp(prefix="tron-0129-report-")
    scripts = os.path.join(d, "scripts")
    os.makedirs(scripts)
    src = os.path.join(ROOT, "scripts", "report.sh")
    dst = os.path.join(scripts, "report.sh")
    shutil.copy(src, dst)
    os.chmod(dst, os.stat(dst).st_mode | stat.S_IEXEC)
    try:
        r = subprocess.run(["bash", dst, "ENG-A", "--tag", "retract", "old habits"],
                           capture_output=True, text=True, timeout=20)
        ok("setup: report.sh itself still accepts an arbitrary --tag string "
           "(no vocabulary check at the shell layer)",
           r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    eng = _eng()
    tag, slots = eng._structured({"tag": "retract", "text": "old habits",
                                  "sender": {"kind": "worker", "id": "ENG-A-01"}})
    ok("AC-1 the engine's structured resolver treats a stray 'retract' tag as unknown "
       "(dropped, never a trigger) — the exact existing unknown-verb law",
       tag == "drop", f"tag={tag} slots={slots}")


def ac1_worker_retract_ingest_is_a_silent_unknown_tag_never_a_crash():
    """Even if something upstream still hands the engine the literal `worker.retract`
    tag (e.g. a stale queued line), `_ingest` must not crash or dispatch anything —
    it's simply not in `self.tags` (routing.yaml) anymore, so it logs 'unknown tag'
    and returns, the same fate every other retired/foreign tag gets."""
    eng = _eng()
    sent = _capture(eng)
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        eng._ingest("worker.retract", {}, {"kind": "worker", "id": "ENG-A-01"})
    finally:
        eng.dry = True
    ok("AC-1 a literal worker.retract ingest is inert: no page, no worker message, "
       "no case opened, no crash",
       not sent and not tw and not eng.st.pending_cases,
       f"sent={sent} tw={tw} cases={eng.st.pending_cases}")


def t2_own_wall_stamp_is_gone_but_the_wall_trigger_still_fires():
    """T2: the `_own_wall` provenance stamp on `worker.wall`'s ingested slots is gone —
    but the KEPT `self._emit(...)` line right after it must still fire the SAME
    `wall:raised:<block>` trigger, unconditionally, exactly as it did with the stamp
    (the stamp was pure provenance plumbing for `_h_retract`'s same-tick cancel; it
    never gated whether the trigger itself fired)."""
    eng = _eng()
    wid = "ENG-A-01"
    eng._tq = []
    eng._ingest("worker.wall", {"block": "A-01", "detail": "genuinely stuck"},
               {"kind": "worker", "id": wid})
    ok("T2 worker.wall still queues its wall:raised:<block> trigger with no _own_wall "
       "stamp anywhere on its slots",
       len(eng._tq) == 1 and eng._tq[0][0] == "wall:raised:A-01"
       and "_own_wall" not in (eng._tq[0][1] or {}),
       f"tq={eng._tq}")
    eng._drain_triggers()
    ok("T2 the drained wall opens a live case exactly as before (trigger unaffected "
       "by the stamp's removal)",
       any(c.get("kind") == "wall" and c.get("worker_id") == wid
           and c.get("decision") is None for c in eng.st.pending_cases.values()),
       f"cases={eng.st.pending_cases}")


def t2_no_other_caller_of_own_wall_remains():
    # Belt-and-suspenders on top of AC-2's grep: confirm no live Engine attribute or
    # method carries the literal name either.
    ok("T2 no Engine attribute/method is literally named _own_wall",
       not any("_own_wall" in n for n in dir(Engine)))


# ══════════════════════════════════════════════════════════════════════════════════
# AC-3: F-1 stays closed WITHOUT retract — the engine-observed sweep, not a verb
# ══════════════════════════════════════════════════════════════════════════════════

def ac3_f1_autoclear_fires_zero_operator_page():
    """The real F-1 protection was always `_sweep_wall_invariant` arm (a): a worker
    walled on ALREADY-DONE work whose case already carries a decision (settled by some
    other path) but was never un-held self-clears at the next sweep pass — case closed,
    worker released, queued verbs replayed — with ZERO operator page (no escalate.wall,
    no tg.escalate) anywhere across the whole episode. This is the untouched T3
    guarantee this block depends on; `_h_retract` was never load-bearing for it."""
    eng = _eng()
    eng.st.row("A-01")["status"] = "done"       # already-done work
    # A live gate (close-out still pending on trunk) — the realistic shape of "done
    # work" mid-close, and keeps _all_settled() from cascading into an unrelated
    # session-end teardown of the still-walled worker (block_01_27_test's own note on
    # this exact seam: never let an unrelated session-lifecycle concern into a sweep test).
    eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="stale wall on already-done work")
    sent = _capture(eng)
    # The case settles via some other path (operator/architect/anything) but nothing
    # ever un-held the worker — the exact inconsistency the sweep exists to repair.
    eng.st.pending_cases[cid]["decision"] = "resume"
    eng.dry = False
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    try:
        eng._sweep()                       # anchors wall_bad_since; too soon to repair
        w = next(x for x in eng.st.workers if x["id"] == wid)
        ok("AC-3 setup: the sweep does not act inside one silence window",
           w.get("status") == "walled", f"w={w}")
        clock["t"] += 6 * 60 + 1           # past silence_ping_min (default 6)
        eng._sweep()                       # cap fires -> arm (a) repairs
    finally:
        eng.dry = True
    ok("AC-3 the case is closed", cid not in eng.st.pending_cases,
       f"cases={eng.st.pending_cases}")
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("AC-3 the worker is un-held", w.get("status") != "walled", f"w={w}")
    ok("AC-3 ZERO operator page across the whole episode (no escalate.wall / "
       "tg.escalate — engine-observed, never a page)",
       not any(tid in ("escalate.wall", "tg.escalate") for tid, _ in sent), f"sent={sent}")


def ac3_undecided_wall_on_done_work_still_waits_never_a_false_autoclear():
    """Regression guard: a wall whose case is still UNDECIDED must never auto-clear just
    because the underlying block happens to be 'done' — arm (a) keys strictly on
    case-decision state, never block status."""
    eng = _eng()
    eng.st.row("A-01")["status"] = "done"
    eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    wid = "ENG-A-01"
    _wall(eng, "A-01", wid, detail="a real, still-undecided wall")
    eng.dry = False
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    try:
        eng._sweep()
        clock["t"] += 6 * 60 + 1
        eng._sweep()
    finally:
        eng.dry = True
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("AC-3 regression: a still-UNDECIDED wall on done work stays walled "
       "(never a false autoclear)", w.get("status") == "walled", f"w={w}")


# ══════════════════════════════════════════════════════════════════════════════════
# AC-4: no net behavior change to settle/wall lifecycle beyond retract removal
# (light canaries — full depth lives in block_01_24/20/27_test.py, untouched)
# ══════════════════════════════════════════════════════════════════════════════════

def ac4_report_sh_grammar_intact():
    d = tempfile.mkdtemp(prefix="tron-0129-grammar-")
    scripts = os.path.join(d, "scripts")
    os.makedirs(scripts)
    dst = os.path.join(scripts, "report.sh")
    shutil.copy(os.path.join(ROOT, "scripts", "report.sh"), dst)
    os.chmod(dst, os.stat(dst).st_mode | stat.S_IEXEC)
    try:
        bad = subprocess.run(["bash", dst, "ENG-A", "declaring", "--tag", "wall"],
                             capture_output=True, text=True, timeout=20)
        ok("AC-4 flags-after-message is still a hard error (grammar untouched)",
           bad.returncode != 0 and "flags must come before" in bad.stderr.lower(),
           f"rc={bad.returncode} stderr={bad.stderr!r}")
        good = subprocess.run(["bash", dst, "ENG-A", "--tag", "wall", "still stuck"],
                              capture_output=True, text=True, timeout=20)
        ok("AC-4 structured --tag wall (flags before message) still succeeds",
           good.returncode == 0, f"rc={good.returncode} stderr={good.stderr!r}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ac4_content_carrying_settle_still_reaches_the_walled_worker():
    eng = _eng()
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="approach A or B?")
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        eng._h_apply_decision({"case": cid, "decision": "resume", "block": "A-01",
                               "detail": "use approach B"})
    finally:
        eng.dry = True
    ok("AC-4 content-carrying settle still delivers the payload on release",
       any(wid_ == wid and "use approach B" in txt for wid_, txt, _ in tw), f"tw={tw}")
    ok("AC-4 the case closed / worker un-held (raise-and-resolve, unaffected)",
       cid not in eng.st.pending_cases, f"cases={eng.st.pending_cases}")


def ac4_kind_routing_still_sends_spec_ownable_walls_to_the_architect():
    eng = _eng()
    wid = "ENG-A-01"
    arch = _arch_idle(eng)
    sent = _capture(eng)
    cid = _wall(eng, "A-01", wid, detail="v1 or v2?", kind="scope")
    ok("AC-4 a spec-ownable --kind wall still routes to the architect, never pages "
       "the operator directly",
       not any(tid in ("escalate.wall", "tg.escalate") for tid, _ in sent)
       and (arch.get("current_job") or {}).get("case") == cid,
       f"sent={sent} arch={arch}")
    ok("AC-4 SPEC_OWNABLE_KINDS vocabulary is unchanged",
       set(SPEC_OWNABLE_KINDS) == {"scope", "blueprint", "design"})


def ac4_negation_detection_still_fail_closes():
    eng = _eng()
    out = eng._settle_regex("don't approve CASE-7")
    ok("AC-4 negation-detection is untouched: a negated settle never affirms",
       isinstance(out, dict) and out.get("negated") is True, f"out={out}")


def ac4_fleet_hold_predicate_still_present_and_gates_dispatch():
    eng = _eng()
    ok("AC-4 fleet-hold is disengaged by default", eng._dispatch_held() is False)
    eng.st.data["refusal_hold"] = {"deaths": [], "active": True}
    ok("AC-4 fleet-hold: _dispatch_held() still reflects the engaged hold "
       "(untouched by this block)", eng._dispatch_held() is True)


def ac4_f4_gate_close_idle_cap_still_a_named_split_code():
    ok("AC-4 F-4's 'gate-close-idle-cap' is still one of the named split codes",
       "gate-close-idle-cap" in GATE_GIVEUP_SPLIT_CODES)
    ok("AC-4 F-4's code is still covered by WALL_KINDS",
       "gate-close-idle-cap" in WALL_KINDS)


def main():
    for fn in sorted(k for k in globals()
                     if k.startswith("ac1_") or k.startswith("ac2_")
                     or k.startswith("ac3_") or k.startswith("ac4_")
                     or k.startswith("t2_")):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
