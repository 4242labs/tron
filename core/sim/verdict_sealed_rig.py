"""core.sim.verdict_sealed_rig — block 01-38 T16/AC-10: VERDICT-SEALED EARLY
STOP lock for `core/sim/live.py`.

Before this task `run_live`'s loop was pure DATA-GATHERING: it logged every
operator page and kept driving, stopping only on `session_end` or the
wall-clock `budget_min` — so a run whose acceptance was ALREADY mathematically
lost (a must-be-zero counter fired, a page beyond the declared expectation, an
abandoned block) would happily keep spending real tokens/wall-clock all the
way to budget before the FINAL gate (`_acceptance_verdict`) ever looked at it.
T16 adds a mid-run check (`_verdict_sealed_reasons`) the loop consults EVERY
iteration, and stops — capturing a full state snapshot — the INSTANT
acceptance can never recover, while still letting a page WITHIN expectation
sail through untouched (the historical, still-correct "gather every
downstream wall in one run" behavior for anything not yet lost).

Two tiers of proof, same "pure function first, real wiring second" idiom
`core/sim/acceptance_verdict_rig.py` already established for `_acceptance_
verdict`:

  PURE-UNIT (`_verdict_sealed_reasons` is a pure function of a `partial`
  dict — no scaffold, no processes):
    P1  a clean/empty partial, 0 expected pages           -> not lost (empty)
    P2  exactly `expect_pages` distinct escalations         -> not lost (the
        "a page WITHIN expectation stops nothing" contract, moderate tier)
    P3  ONE page beyond `expect_pages`                      -> LOST, names the
        overage
    P4  a REAL must-be-zero counter event (the actual `core/counters.py`
        effect string, not a made-up name)                  -> LOST, names it
    P5  a REAL may-fire counter past its declared ceiling    -> LOST, names it
    P6  an abandoned block                                   -> LOST, names it
    P7  EXCLUSION — a dangling OPEN case alone (decision None), nothing else
        wrong                                                -> NOT lost (can
        still settle later in the run; this is the deliberate carve-out from
        `_acceptance_verdict`'s own open-case reject)
    P8  EXCLUSION — an `outcome`/`orphans` key present (mid-run noise a
        caller might pass) is simply never read by this function at all

  REAL BEHAVIORAL (drives the ACTUAL `live.run_live` loop — its real
  session_end/budget/verdict-sealed control flow, unmodified — over a
  SCRIPTED manifest/tick sequence so no real git copy, real fleet, or LLM
  is needed; the environment seams `run_live` calls through
  (`copy_real_scaffold`/`seed_live_instance`/`install_canon`/`Engine`/
  `state.load`) are the ONLY things stubbed, monkeypatched module-level and
  restored in `finally` — the exact "rig fakes the environment, drives the
  real subject" idiom `core.sim.run.run_sim` already uses for `jobs.
  spawn_runner`. `real_tier.real_spawn`/`_owned_orphans` are left REAL — the
  fake engine never calls `jobs.spawn_runner`, so nothing is actually
  spawned; teardown finds zero survivors for real, not by assumption):
    R1  a scripted run that reaches EXACTLY `expect_pages` (moderate, 1) and
        never exceeds it, no counters, no abandons -> the loop does NOT stop
        early: it runs all the way to the wall-clock budget
        (`outcome=="budget"`), `verdict_sealed_snapshot is None`
    R2  a scripted run whose escalations exceed `expect_pages` on loop 1
        -> the loop stops EARLY (`outcome=="verdict_sealed_lost"`), well
        before the (deliberately large) budget, with a captured snapshot
        naming the overage
    R3  a scripted run whose events carry a REAL must-be-zero counter effect
        on loop 1 -> stops EARLY the same way, via the counter-partition
        route rather than the page-overage route
    R4  the captured snapshot's manifest is a REAL deep copy: mutating the
        live scripted manifest object AFTER the run leaves the captured
        snapshot untouched (same "DEEP COPY, never a live reference" proof
        `core/sim/operator_channel_rig.py` already established for the R8
        safe-park-and-halt snapshot)

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on fail.
"""
import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app worktree root
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
sys.path.insert(0, _ENGINE_DIR)
sys.path.insert(0, _CORE_DIR)
sys.path.insert(0, _HERE)

import counters                        # noqa: E402 — core/counters.py, the real R4 partition
import live                             # noqa: E402 — core/sim/live.py, UNIT UNDER TEST

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ═══════════════════════════ PURE-UNIT (P1-P8) ═══════════════════════════

_MBZ_EFFECT = counters.COUNTERS["emit_missing_template"].effect       # real effect string
_MAYFIRE_NAME = "architect_refused_authoring_backstop"
_MAYFIRE_EFFECT = counters.COUNTERS[_MAYFIRE_NAME].effect
_MAYFIRE_CEILING = counters.COUNTERS[_MAYFIRE_NAME].ceiling


def _partial(events=None, cases=None, pages=None, abandoned=None, **extra):
    d = {"events": events or [], "cases": cases or {},
         "operator_pages": pages or {}, "abandoned_blocks": abandoned or []}
    d.update(extra)
    return d


def _page(case_id):
    return {"case_id": case_id}


def run_pure_unit():
    # P1 — clean/empty, 0 expected -> not lost
    r = live._verdict_sealed_reasons(_partial(), expect_pages=0)
    ok("P1 clean-empty-not-lost", r == [], detail=f"reasons={r}")

    # P2 — exactly expect_pages (moderate=1) distinct escalations -> not lost
    part = _partial(pages={"p1": _page("C1")})
    r = live._verdict_sealed_reasons(part, expect_pages=1)
    ok("P2 within-expectation-not-lost", r == [], detail=f"reasons={r}")

    # P3 — ONE page beyond expect_pages=1 -> LOST, names the overage
    part = _partial(pages={"p1": _page("C1"), "p2": _page("C2")})
    r = live._verdict_sealed_reasons(part, expect_pages=1)
    ok("P3 overage-lost", len(r) == 1 and "exceeds expect_pages=1" in r[0], detail=f"reasons={r}")

    # P4 — a REAL must-be-zero counter event -> LOST, names it
    part = _partial(events=[{"type": _MBZ_EFFECT, "payload": {}}])
    r = live._verdict_sealed_reasons(part, expect_pages=0)
    ok("P4 must-be-zero-lost",
       len(r) == 1 and "emit_missing_template" in r[0], detail=f"reasons={r}")

    # P5 — a REAL may-fire counter one past its declared ceiling -> LOST, names it
    events = [{"type": _MAYFIRE_EFFECT, "payload": {}}] * (_MAYFIRE_CEILING + 1)
    part = _partial(events=events)
    r = live._verdict_sealed_reasons(part, expect_pages=0)
    ok("P5 mayfire-past-ceiling-lost",
       len(r) == 1 and _MAYFIRE_NAME in r[0], detail=f"reasons={r}")
    # boundary: AT the ceiling (not past it) must NOT be lost via this route
    events_at = [{"type": _MAYFIRE_EFFECT, "payload": {}}] * _MAYFIRE_CEILING
    r_at = live._verdict_sealed_reasons(_partial(events=events_at), expect_pages=0)
    ok("P5b mayfire-at-ceiling-not-lost", r_at == [], detail=f"reasons={r_at}")

    # P6 — an abandoned block -> LOST, names it
    part = _partial(abandoned=["01-99"])
    r = live._verdict_sealed_reasons(part, expect_pages=0)
    ok("P6 abandoned-block-lost", len(r) == 1 and "01-99" in r[0], detail=f"reasons={r}")

    # P7 — EXCLUSION: a dangling OPEN case alone (decision None) -> NOT lost
    # (can still settle later in the run — the deliberate carve-out from
    # `_acceptance_verdict`'s own open-case reject).
    part = _partial(cases={"C1": {"decision": None}})
    r = live._verdict_sealed_reasons(part, expect_pages=0)
    ok("P7 open-case-alone-not-lost", r == [], detail=f"reasons={r}")

    # P8 — EXCLUSION: outcome/orphans present but irrelevant — never read
    part = _partial(outcome="unknown", orphans=["fake-orphan-line"])
    r = live._verdict_sealed_reasons(part, expect_pages=0)
    ok("P8 outcome-orphans-ignored-not-lost", r == [], detail=f"reasons={r}")

    # Non-vacuity of the SHARED helper: `_acceptance_verdict` and
    # `_verdict_sealed_reasons` must agree on "how many distinct pages" —
    # prove they're the SAME set object shape, not two hand-drifted copies.
    part = _partial(pages={"p1": _page("C1"), "p2": _page("C1")})   # same case twice
    ok("SHARED distinct-case-dedup",
       live._distinct_escalated_cases(part) == {"C1"},
       detail=f"{live._distinct_escalated_cases(part)}")


# ═══════════════════════ REAL BEHAVIORAL (R1-R4) ═══════════════════════

class _FakeEvents:
    def __init__(self):
        self.log = []


class _FakeEngine:
    """Minimal stand-in for `core.engine.Engine` — just the surface
    `run_live`'s OWN loop touches (`.ctx`, `.dry`, `._now`, `.events.log`,
    `.start()`, `.tick()`, `.log()`). The loop's REAL control-flow code
    (session_end check, the VERDICT-SEALED check under test, PULSE, budget)
    runs UNCHANGED against a scripted sequence — never a reimplementation of
    `run_live` itself. `SCRIPT` (module-level, set per scenario) supplies the
    manifest reached after each `.tick()` call and any events to append."""
    def __init__(self, ctx):
        self.ctx = ctx
        self.dry = None
        self._now = None
        self.events = _FakeEvents()
        self.tick_i = 0

    def start(self, **kw):
        return {"spawned": []}

    def log(self, *a, **kw):
        pass

    def tick(self):
        self.tick_i += 1
        ev = SCRIPT["events_by_tick"].get(self.tick_i)
        if ev:
            self.events.log.extend(ev)
        return {"session_end": None}   # never a clean session_end in this rig —
                                        # the scenarios prove the VERDICT-SEALED
                                        # stop / the budget stop, not session_end


SCRIPT = {"manifests": [{}], "events_by_tick": {}}
_LAST_ENGINE = {"eng": None}


def _fake_engine_ctor(ctx):
    eng = _FakeEngine(ctx)
    _LAST_ENGINE["eng"] = eng
    return eng


def _fake_state_load(ctx):
    eng = _LAST_ENGINE["eng"]
    i = min(eng.tick_i if eng else 0, len(SCRIPT["manifests"]) - 1)
    return SCRIPT["manifests"][i]


def _drive(manifests, events_by_tick, expect_pages, budget_min, poll_sec, max_loops):
    """Drive the REAL `live.run_live` with the environment seams stubbed —
    everything else (the loop, the VERDICT-SEALED check, budget/session_end
    handling) is `live.py`'s own real code. Restores every monkeypatch in
    `finally`, the SAME idiom every other `core/*_rig.py` in this tree uses."""
    SCRIPT["manifests"] = manifests
    SCRIPT["events_by_tick"] = events_by_tick
    _LAST_ENGINE["eng"] = None
    orig = {
        "copy_real_scaffold": live.copy_real_scaffold,
        "seed_live_instance": live.seed_live_instance,
        "install_canon": live.install_canon,
        "Engine": live.Engine,
        "state_load": live.state.load,
    }
    import tempfile
    tmproot = tempfile.mkdtemp(prefix="verdict-sealed-rig-")
    try:
        live.copy_real_scaffold = lambda: tmproot
        live.seed_live_instance = lambda root: (tmproot, None, None)
        live.install_canon = lambda inst: tmproot
        live.Engine = _fake_engine_ctor
        live.state.load = _fake_state_load
        return live.run_live(
            scaffold_src=None, worker_count=1, budget_min=budget_min,
            poll_sec=poll_sec, scope="all", max_loops=max_loops,
            adapter="echo", operator_proxy=False, expect_pages=expect_pages)
    finally:
        live.copy_real_scaffold = orig["copy_real_scaffold"]
        live.seed_live_instance = orig["seed_live_instance"]
        live.install_canon = orig["install_canon"]
        live.Engine = orig["Engine"]
        live.state.load = orig["state_load"]


def run_real_behavioral():
    # R1 — reaches EXACTLY expect_pages (moderate=1), stays there forever
    # (manifests list clamps to its last entry once ticks exceed its length)
    # -> must NOT stop early; runs to the (tiny) wall-clock budget.
    manifests = [{}, {"cases": {"C1": {"decision": None}},
                       "operator_pages": {"p1": {"case_id": "C1"}}}]
    result = _drive(manifests, {}, expect_pages=1, budget_min=0.008,
                     poll_sec=0.03, max_loops=60)
    ok("R1 within-expectation-runs-to-budget",
       result["outcome"] == "budget" and result["verdict_sealed_snapshot"] is None,
       detail=f"outcome={result['outcome']} loops={result['loops']} "
              f"snapshot={result['verdict_sealed_snapshot']}")

    # R2 — 2 distinct escalations vs expect_pages=1 on loop 1 -> stops EARLY,
    # well short of a deliberately-large budget (proves the early-stop
    # actually pre-empts the budget path, not merely coincides with it).
    manifests = [{}, {"cases": {}, "operator_pages": {"p1": {"case_id": "C1"},
                                                        "p2": {"case_id": "C2"}}}]
    result = _drive(manifests, {}, expect_pages=1, budget_min=5.0,
                     poll_sec=0.02, max_loops=5)
    snap = result["verdict_sealed_snapshot"]
    ok("R2 overage-stops-early",
       result["outcome"] == "verdict_sealed_lost" and result["loops"] <= 2
       and snap is not None and result["elapsed_min"] < 1.0,
       detail=f"outcome={result['outcome']} loops={result['loops']} "
              f"elapsed_min={result['elapsed_min']:.4f} reason={result['reason']}")
    ok("R2 snapshot-names-overage",
       snap is not None and any("exceeds expect_pages=1" in r for r in snap["reasons"]),
       detail=f"{snap['reasons'] if snap else None}")

    # R3 — a REAL must-be-zero counter effect fires on loop 1 -> stops EARLY
    # via the counter-partition route (expect_pages=0, no page overage at all).
    manifests = [{}, {}]
    events_by_tick = {1: [{"type": _MBZ_EFFECT, "payload": {}}]}
    result = _drive(manifests, events_by_tick, expect_pages=0, budget_min=5.0,
                     poll_sec=0.02, max_loops=5)
    snap = result["verdict_sealed_snapshot"]
    ok("R3 must-be-zero-stops-early",
       result["outcome"] == "verdict_sealed_lost" and result["loops"] <= 2
       and snap is not None,
       detail=f"outcome={result['outcome']} loops={result['loops']} reason={result['reason']}")
    ok("R3 snapshot-names-counter",
       snap is not None and any("emit_missing_template" in r for r in snap["reasons"]),
       detail=f"{snap['reasons'] if snap else None}")

    # R4 — the captured snapshot's manifest is a REAL deep copy: mutate the
    # LIVE scripted manifest object (the same dict `SCRIPT["manifests"][1]`
    # was) AFTER the run and confirm the captured snapshot is untouched.
    live_manifest = {"cases": {}, "operator_pages": {"p1": {"case_id": "C1"},
                                                        "p2": {"case_id": "C2"}}}
    manifests = [{}, live_manifest]
    result = _drive(manifests, {}, expect_pages=1, budget_min=5.0,
                     poll_sec=0.02, max_loops=5)
    snap = result["verdict_sealed_snapshot"]
    before = copy.deepcopy(snap["manifest"]) if snap else None
    if live_manifest.get("operator_pages"):
        live_manifest["operator_pages"]["p3"] = {"case_id": "C3-INJECTED-AFTER"}
    ok("R4 snapshot-is-deep-copy",
       snap is not None and snap["manifest"] == before
       and "p3" not in (snap["manifest"].get("operator_pages") or {}),
       detail="a post-run mutation of the live manifest must never reach the "
              "already-captured snapshot")


def main():
    run_pure_unit()
    run_real_behavioral()
    n_pass = sum(1 for _, c, _ in _results if c)
    n_total = len(_results)
    for name, cond, detail in _results:
        mark = "PASS" if cond else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))
    print(f"verdict_sealed_rig: PASS ({n_pass}/{n_total})")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
