"""core.counters_rig — mutation-proof lock for `core/counters.py`, the R4
counter partition (block 01-38 T9, AC-5a/5b).

  P1  the declared partition matches the pinned must-be-zero name set today
      (no `may_fire` counter is live yet — see `core/counters.py`'s own
      docstring for why).
  P2  `evaluate([])` — a clean run — ACCEPTs, every must-be-zero counter
      printed at 0, no reasons.
  P3  a real must-be-zero counter firing (via its REAL `core/emit.py` call
      shape, not a hand-built event dict) REJECTs, naming the counter.
  P4  DISCRIMINATOR SPECIFICITY (non-vacuity): the generic `must_be_zero`
      effect carrying an UNRELATED `counter=` value trips NEITHER of the two
      named counters that multiplex it — proves the discriminator actually
      filters, never a blanket "the effect fired" match.

  test:<counter_partition> (AC-5a) — P1-P4 combined: the partition is
      declared correctly, a clean run ACCEPTs with every counter printed,
      a seeded must-be-zero firing REJECTs by name, and the multiplexed
      effect's discriminator is genuinely specific.

  A1  `check_append_only()` is GREEN today (the live table is a superset of
      the pin).
  A2  MUTATION PROOF: with a pinned name removed from the live table
      (`counters.COUNTERS`, restored in `finally`), the pin FAILS and names
      exactly the removed counter — proving A1 is the pin actually checking,
      not vacuously true.

  test:<counter_append_only_pinned> (AC-5b) — A1+A2 combined.

  M1-M4  PER-COUNTER MUTATION PROOF: for each of the four real must-be-zero
      counters, firing its REAL emit call shape (`emit.put`/`emit.record`/
      `emit.record_to`, the exact shapes `core/engine.py`/`core/router.py`/
      `core/vocab.py`/`core/casestate.py` use) moves ONLY that counter's
      tally by exactly +1 — every other declared counter stays at 0.

  test:<per_counter_mutation_proof> (AC-5b) — M1-M4 combined.

  E1-E4  the MAY-FIRE ceiling arm, mechanism-proven with a TEMPORARY
      synthetic probe counter (same idiom `core/emit_rig.py`'s own R2b uses
      to temporarily register `_probe_state_effect` — added then removed in
      `finally`, never left in the live table): under-ceiling ACCEPTs and is
      printed; AT the ceiling still ACCEPTs (boundary, not off-by-one); one
      past the ceiling REJECTs by name; the may-fire line is printed on
      EVERY call, not only on breach.

  I1  INTEGRATION: `core/sim/live.py::_acceptance_verdict` — the real live
      acceptance gate — REJECTs a result carrying a must-be-zero-firing
      event in `result["events"]`, and ACCEPTs a result with an empty
      stream (the wiring is real, not just the standalone module).

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on fail.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
_SIM_DIR = os.path.join(_HERE, "sim")
sys.path.insert(0, os.path.join(_APP_ROOT, "engine"))
sys.path.insert(0, _HERE)
sys.path.insert(0, _SIM_DIR)

import emit        # noqa: E402 — core/emit.py, the effect registry counters rides on
import counters     # noqa: E402 — core/counters.py, the unit under test

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


class _Sink:
    """The `.event(type, **payload)` shape every emit-routed sink shares
    (identical to `core/emit_rig.py`'s own `_Sink` — the established idiom
    for a token-free duck `eng.events`)."""
    def __init__(self):
        self.log = []

    def event(self, type_, **payload):
        self.log.append({"type": type_, "payload": payload})


class _Eng:
    def __init__(self, sink=None):
        self.events = sink or _Sink()


def main():
    # ── P1: the declared partition matches the pin (no may_fire live yet) ──
    p1 = (counters.must_be_zero_names() == counters.MUST_BE_ZERO_PINNED
          and counters.may_fire_names() == frozenset())
    ok("P1: must_be_zero_names() == the pinned set; may_fire_names() is empty "
       "(no designed-rare backstop is classified yet — T10-T12's job)", p1,
       f"must_be_zero={counters.must_be_zero_names()} may_fire={counters.may_fire_names()}")

    # ── P2: a clean run ACCEPTs, every must-be-zero counter printed at 0 ──
    ok_p2, lines_p2, reasons_p2 = counters.evaluate([])
    p2 = (ok_p2 and not reasons_p2
          and all(f"must-be-zero: {n}=0" in lines_p2 for n in counters.MUST_BE_ZERO_PINNED))
    ok("P2: evaluate([]) ACCEPTs, no reasons, every must-be-zero counter "
       "printed at 0", p2, f"lines={lines_p2} reasons={reasons_p2}")

    # ── P3: a REAL must-be-zero firing REJECTs, naming the counter ──
    eng = _Eng()
    m = {}
    emit.put(eng, m, "router_catch_all_counted", ("counters",), "router_catch_all", 1,
             tag="bogus.tag", worker_id="w1", count=1)
    ok_p3, lines_p3, reasons_p3 = counters.evaluate(eng.events.log)
    p3 = (not ok_p3 and any("router_catch_all" in r for r in reasons_p3)
          and "must-be-zero: router_catch_all=1" in lines_p3)
    ok("P3: a real router_catch_all_counted firing (real emit.put shape) "
       "REJECTs and names the counter", p3, f"lines={lines_p3} reasons={reasons_p3}")

    # ── P4: discriminator specificity — an unrelated `counter=` value on the
    #     multiplexed `must_be_zero` effect trips NEITHER named counter ──
    eng = _Eng()
    emit.record(eng, "must_be_zero", counter="some_other_backstop_entirely", detail="x")
    tallied = counters.tally(eng.events.log)
    p4 = (tallied["vocab_version_handshake_failed"] == 0
          and tallied["operator_page_permanent_fail"] == 0)
    ok("P4 (non-vacuity): an UNRELATED counter= value on the multiplexed "
       "must_be_zero effect trips neither vocab_version_handshake_failed nor "
       "operator_page_permanent_fail — the discriminator genuinely filters",
       p4, f"tallied={tallied}")

    ok("test:<counter_partition> (AC-5a): partition declared correctly, a "
       "clean run ACCEPTs with every counter printed, a seeded must-be-zero "
       "firing REJECTs by name, discriminator is genuinely specific",
       p1 and p2 and p3 and p4)

    # ── A1: the pin is green today ──
    a1_ok, a1_missing = counters.check_append_only()
    ok("A1: check_append_only() is GREEN today (live set is a superset of "
       "the pin)", a1_ok and not a1_missing, f"missing={a1_missing}")

    # ── A2: MUTATION PROOF — remove a pinned name from the live table,
    #     the pin FAILS and names exactly that counter; restored after ──
    victim = "router_catch_all"
    saved = counters.COUNTERS.pop(victim)
    try:
        a2_ok, a2_missing = counters.check_append_only()
        p_a2 = (not a2_ok) and a2_missing == frozenset({victim})
        ok("A2 (MUTATION PROOF): removing a pinned counter from the live "
           "table FAILS the pin and names exactly the removed counter — "
           "proves A1 is a real check, not vacuously true",
           p_a2, f"a2_ok={a2_ok} missing={a2_missing}")
    finally:
        counters.COUNTERS[victim] = saved
    # restoration itself verified — a silently-unrestored fixture would
    # poison every later assertion in this file
    ok("A2b: the removed counter was genuinely restored (fixture hygiene)",
       victim in counters.COUNTERS and counters.check_append_only() == (True, frozenset()))

    ok("test:<counter_append_only_pinned> (AC-5b): the pin is green today "
       "AND mutation-proven (a removal is caught, named, and the fixture "
       "self-restores)", a1_ok and not a1_missing and p_a2)

    # ── M1-M4: per-counter mutation proof — the REAL call shape for each of
    #     the four live must-be-zero counters moves ONLY that counter ──
    def _only(name, counts):
        return counts.get(name) == 1 and all(
            v == 0 for n, v in counts.items() if n != name)

    eng = _Eng()
    m = {}
    emit.put(eng, m, "engine_emit_missing_template_counted", ("counters",),
             "emit_missing_template", 1, template_id="tpl.x", count=1)
    m1 = _only("emit_missing_template", counters.tally(eng.events.log))
    ok("M1: engine_emit_missing_template_counted (real emit.put shape) moves "
       "ONLY emit_missing_template", m1, f"tally={counters.tally(eng.events.log)}")

    eng = _Eng()
    m = {}
    emit.put(eng, m, "router_catch_all_counted", ("counters",),
             "router_catch_all", 1, tag="bogus", worker_id="w1", count=1)
    m2 = _only("router_catch_all", counters.tally(eng.events.log))
    ok("M2: router_catch_all_counted (real emit.put shape) moves ONLY "
       "router_catch_all", m2, f"tally={counters.tally(eng.events.log)}")

    sink = _Sink()
    emit.record_to(sink, "must_be_zero", counter="vocab_version_handshake_failed",
                   engine_version="1", instance_version="0", schema_path="/x")
    m3 = _only("vocab_version_handshake_failed", counters.tally(sink.log))
    ok("M3: vocab_version_handshake_failed (real emit.record_to shape, "
       "core/vocab.py::check_handshake's own pre-engine entry) moves ONLY "
       "vocab_version_handshake_failed", m3, f"tally={counters.tally(sink.log)}")

    eng = _Eng()
    emit.record(eng, "must_be_zero", counter="operator_page_permanent_fail",
               case_id="CASE-1", block="01-02", consecutive_fail=5)
    m4 = _only("operator_page_permanent_fail", counters.tally(eng.events.log))
    ok("M4: operator_page_permanent_fail (real emit.record shape, "
       "core/casestate.py's own SAFE-PARK-AND-HALT site) moves ONLY "
       "operator_page_permanent_fail", m4, f"tally={counters.tally(eng.events.log)}")

    ok("test:<per_counter_mutation_proof> (AC-5b): every declared "
       "must-be-zero counter's REAL call shape moves that counter, and only "
       "that counter", m1 and m2 and m3 and m4)

    # ── E1-E4: the may-fire ceiling arm, mechanism-proven with a TEMPORARY
    #     synthetic probe (added and removed here, never left live) ──
    PROBE_EFFECT = "_probe_may_fire_effect"
    PROBE_COUNTER = "_probe_may_fire_counter"
    emit.EFFECTS[PROBE_EFFECT] = emit._Effect(PROBE_EFFECT, "forensic",
                                              counter_class="may_fire")
    counters.COUNTERS[PROBE_COUNTER] = counters._Counter(
        PROBE_COUNTER, counters.MAY_FIRE, PROBE_EFFECT, ceiling=2)
    try:
        # E1: 0 fires -> under ceiling, ACCEPT, printed
        ok_e1, lines_e1, reasons_e1 = counters.evaluate([])
        e1 = (ok_e1 and f"may-fire: {PROBE_COUNTER}=0 (ceiling=2)" in lines_e1)
        ok("E1: a may-fire counter at 0 ACCEPTs and is printed with its "
           "ceiling", e1, f"lines={lines_e1}")

        # E2: exactly AT the ceiling -> still ACCEPT (boundary, not off-by-one)
        eng = _Eng()
        for _ in range(2):
            emit.record(eng, PROBE_EFFECT)
        ok_e2, lines_e2, reasons_e2 = counters.evaluate(eng.events.log)
        e2 = (ok_e2 and not reasons_e2
              and f"may-fire: {PROBE_COUNTER}=2 (ceiling=2)" in lines_e2)
        ok("E2: a may-fire counter AT its declared ceiling (2/2) still "
           "ACCEPTs (boundary correctness, never off-by-one)", e2,
           f"lines={lines_e2} reasons={reasons_e2}")

        # E3: ONE PAST the ceiling -> REJECT, named
        eng = _Eng()
        for _ in range(3):
            emit.record(eng, PROBE_EFFECT)
        ok_e3, lines_e3, reasons_e3 = counters.evaluate(eng.events.log)
        e3 = (not ok_e3 and any(PROBE_COUNTER in r for r in reasons_e3)
              and f"may-fire: {PROBE_COUNTER}=3 (ceiling=2)" in lines_e3)
        ok("E3 (MUTATION PROOF): one past the declared ceiling (3/2) REJECTs "
           "by name — the ceiling arm genuinely enforces, not just prints",
           e3, f"lines={lines_e3} reasons={reasons_e3}")

        # E4: the may-fire line is printed on EVERY call, breach or not —
        # already demonstrated by E1/E2/E3 all asserting the line's presence;
        # this is the explicit aggregate check for the AC's own wording.
        e4 = e1 and e2 and e3
        ok("E4: the may-fire count is printed on every evaluate() call "
           "(pass or fail) — R4's own 'prints every may-fire count' clause",
           e4)
    finally:
        del emit.EFFECTS[PROBE_EFFECT]
        del counters.COUNTERS[PROBE_COUNTER]
    ok("E5: the temporary probe was fully removed (fixture hygiene, never "
       "left classifying a real effect)",
       PROBE_EFFECT not in emit.EFFECTS and PROBE_COUNTER not in counters.COUNTERS)

    # ── I1: INTEGRATION — the real core/sim/live.py acceptance gate wiring ──
    sys.path.insert(0, _SIM_DIR)
    import live   # noqa: E402 — core/sim/live.py, the real live acceptance gate

    def _clean_result(**over):
        r = {
            "outcome": "session_end", "orphans": [], "cases": {},
            "operator_pages": {}, "escalations": [], "escalated_kills": [],
            "abandoned_blocks": [], "events": [],
        }
        r.update(over)
        return r

    okv_clean, reasons_clean = live._acceptance_verdict(_clean_result(), expect_pages=0)
    eng = _Eng()
    m = {}
    emit.put(eng, m, "router_catch_all_counted", ("counters",),
             "router_catch_all", 1, tag="bogus", worker_id="w1", count=1)
    okv_dirty, reasons_dirty = live._acceptance_verdict(
        _clean_result(events=eng.events.log), expect_pages=0)
    i1 = (okv_clean and not reasons_clean
          and not okv_dirty and any("router_catch_all" in r for r in reasons_dirty))
    ok("I1 (INTEGRATION): core/sim/live.py::_acceptance_verdict — the REAL "
       "live acceptance gate — ACCEPTs an empty event stream and REJECTs a "
       "result whose events carry a must-be-zero firing, naming the counter",
       i1, f"reasons_clean={reasons_clean} reasons_dirty={reasons_dirty}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.counters_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
