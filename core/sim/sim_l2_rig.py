"""core.sim.sim_l2_rig — the wave-14 L2 graded proof (ADR-0004 §11.5): runs
`core.sim.run.run_sim` (the reusable L2 driver) over a realistic mockup — a
few small REAL functions, a real declared test command that actually runs
and exits 0/1 for real (never a bare `true`) — and asserts the WHOLE flow:
every block ✅ on trunk, the cadence reviewer fired + held + attested, its
log-review finding's adhoc block landed AND closed, a clean session-end, 0
orphans, an idempotent re-tick.

PLUS a second, independent drive — a deliberately BROKEN function on the
mockup's declared test — proving the SIM apparatus exercises the
NON-happy path too: `gate.trunk` holds (a genuinely observed red never
advances, never silently escalates itself — `core/gate.py`'s own pure
predicate-driven design), `core/sentry.py`'s pacing ladder nudges then caps
the idle gate, and `core/casestate.py` opens a parked operator case
(`source == "sentry.cap"`) — never a silent hang.

Both drives are `core.sim.run.run_sim` calls — no bespoke wiring of this
rig's own; this file's OWN job is authoring the two scenarios (block lists +
`core.sim.worker.Transcript` overrides) and asserting the result, same
"scenario author, not re-implementer" role every other `core/*_rig.py`
already keeps relative to the module(s) it proves.

Real git reads in THIS file are verification-only (a final `git show`/
`git status` confirming what already happened, the SAME "rig double-checks
its own drive" convention every prior `core/*_rig.py` closes with) — never
control-plane observation, which `core.engine.Engine` (via `core.gitobs`)
already owns throughout the drive itself.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # core/sim
CORE_DIR = os.path.dirname(HERE)                             # core
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gate                          # noqa: E402 — core/gate.py, stage constants for assertions
import run as sim_run                 # noqa: E402 — core/sim/run.py, THE MODULE UNDER TEST
import worker as sim_worker            # noqa: E402 — core/sim/worker.py, the Transcript seam

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _git_out(args, cwd):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}) rc={r.returncode}\n{r.stderr}")
    return r.stdout.strip()


# ══════════════════════════════════════════════════════════════════════════
# Scenario 1 — happy path: 3 real blocks (one real dependency), a real
# cadence-reviewer, its log-review finding's adhoc block, a clean
# session-end, idempotent, 0 orphans.
# ══════════════════════════════════════════════════════════════════════════
BLOCK_A, BLOCK_B, BLOCK_C = "01-01", "01-02", "01-03"
HAPPY_BLOCKS = [
    {"id": BLOCK_A, "depends_on": [], "reviewer_class": "code",
     "title": "double(x): a small real function"},
    {"id": BLOCK_B, "depends_on": [BLOCK_A], "reviewer_class": "code",
     "title": "is_even(x): depends on 01-01"},
    {"id": BLOCK_C, "depends_on": [], "reviewer_class": "code",
     "title": "square(x): a small real function"},
]
CADENCE_TYPE = "code"
CADENCE_THRESHOLD = 2
HAPPY_MAX_TICKS = 300

_DOUBLE_BODY = (
    '"""app/lib/01-01.py — double(x), a small real function."""\n\n'
    "def double(x):\n"
    "    return x * 2\n\n\n"
    "def check():\n"
    "    return double(21) == 42 and double(0) == 0 and double(-3) == -6\n"
)
_IS_EVEN_BODY = (
    '"""app/lib/01-02.py — is_even(x), depends (thematically) on 01-01."""\n\n'
    "def is_even(x):\n"
    "    return x % 2 == 0\n\n\n"
    "def check():\n"
    "    return is_even(4) and not is_even(7) and is_even(0)\n"
)
_SQUARE_BODY = (
    '"""app/lib/01-03.py — square(x), a small real function."""\n\n'
    "def square(x):\n"
    "    return x * x\n\n\n"
    "def check():\n"
    "    return square(5) == 25 and square(0) == 0 and square(-4) == 16\n"
)


def _happy_transcript():
    return sim_worker.default_transcript(overrides={
        BLOCK_A: ("app/lib/01-01.py", _DOUBLE_BODY),
        BLOCK_B: ("app/lib/01-02.py", _IS_EVEN_BODY),
        BLOCK_C: ("app/lib/01-03.py", _SQUARE_BODY),
    })


def run_happy_path():
    result = sim_run.run_sim(
        HAPPY_BLOCKS, knobs={"cadence": {CADENCE_TYPE: CADENCE_THRESHOLD}},
        worker_count=1, max_ticks=HAPPY_MAX_TICKS, transcript=_happy_transcript())

    root = result["root"]
    driver = result["driver"]
    gates = result["final_manifest"].get("gates") or {}
    adhoc_blocks = sorted(driver.adhoc_authored)
    all_block_ids = [BLOCK_A, BLOCK_B, BLOCK_C] + adhoc_blocks

    ok("H0 (WHOLE-SIM CONVERGENCE — must be GREEN): 3 real blocks + a real "
       "dependency + a real cadence review + its log-review adhoc block "
       "converged to a clean session-end via run_sim, inside "
       f"{HAPPY_MAX_TICKS} ticks (used {result['ticks_used']})",
       result["session_ended_tick"] is not None and result["ticks_used"] < HAPPY_MAX_TICKS,
       f"ticks_used={result['ticks_used']} session_ended_tick={result['session_ended_tick']}")

    for block in (BLOCK_A, BLOCK_B, BLOCK_C):
        block_file_rel = f"meta/blocks/{block}.md"
        doc_on_main = _git_out(["show", f"main:{block_file_rel}"], root)
        g = gates.get(block, {})
        ok(f"H1[{block}] (ALL BLOCKS ✅ ON TRUNK — must be GREEN): the block "
           "doc as read FROM main shows ✅, gate CLOSED",
           "**Status:** ✅ Done" in doc_on_main and g.get("stage") == gate.STAGE_CLOSED,
           f"doc head={doc_on_main.splitlines()[:4]} stage={g.get('stage')}")

    ok("H2 (DEP-ORDERING — must be GREEN): 01-02 was not spawned until "
       "01-01 was observed record_landed on trunk",
       BLOCK_A in driver.done_tick and BLOCK_B in driver.spawn_tick
       and driver.spawn_tick[BLOCK_B] > driver.done_tick[BLOCK_A],
       f"done_tick[{BLOCK_A}]={driver.done_tick.get(BLOCK_A)} "
       f"spawn_tick[{BLOCK_B}]={driver.spawn_tick.get(BLOCK_B)}")

    reviewer_ids = [a for a in driver.reviewer_seen if a.startswith(f"reviewer-{CADENCE_TYPE}-")]
    ok("H3 (CADENCE-REVIEWER KILLER — must be GREEN): a reviewer-code fired "
       "on cadence, HELD on the first hand-back, and was genuinely RELEASED "
       "on the second (attest) — popped off manifest['workers']",
       len(reviewer_ids) >= 1
       and all(rid in driver.review_hold_tick for rid in reviewer_ids)
       and all(rid in driver.review_release_tick for rid in reviewer_ids)
       and all(rid not in (result["final_manifest"].get("workers") or {}) for rid in reviewer_ids),
       f"reviewer_ids={reviewer_ids} hold={driver.review_hold_tick} "
       f"release={driver.review_release_tick}")

    ok("H4 (ADHOC CLOSED — must be GREEN): at least one attested review's "
       "finding queued a real architect log job that authored + REAL-landed "
       "a genuinely NEW block, and EVERY adhoc block authored was landed "
       "AND closed (✅ on trunk, gate CLOSED) — never just landed",
       len(adhoc_blocks) >= 1
       and all(b in driver.adhoc_landed_tick for b in adhoc_blocks)
       and all(gates.get(b, {}).get("stage") == gate.STAGE_CLOSED for b in adhoc_blocks)
       and all("**Status:** ✅ Done" in _git_out(["show", f"main:meta/blocks/{b}.md"], root)
              for b in adhoc_blocks),
       f"adhoc_blocks={adhoc_blocks} adhoc_landed_tick={driver.adhoc_landed_tick} "
       f"stages={ {b: gates.get(b, {}).get('stage') for b in adhoc_blocks} }")

    ok("H5 (SESSION-END KILLER — must be GREEN): the clean terminal fired "
       "only once EVERY in-scope block (the three originals + every adhoc) "
       "was ✅ + CLOSED, and the marker is durable (re-read fresh off disk)",
       all(gates.get(b, {}).get("stage") == gate.STAGE_CLOSED for b in all_block_ids)
       and bool((result["session_end"] or {}).get("ended_at")),
       f"stages={ {b: gates.get(b, {}).get('stage') for b in all_block_ids} } "
       f"session={result['session_end']}")

    ok("H6 (IDEMPOTENT RE-TICK KILLER — must be GREEN): a further eng.tick() "
       "call AFTER session-end is a true no-op — manifest bytes AND real "
       "git both byte-identical before/after, nothing re-spawned",
       result["idempotent"] is not None and result["idempotent"]["ok"],
       f"idempotent={result['idempotent']}")

    ok("H7 (0 ORPHANS — must be GREEN): NO real worker process ever existed "
       "(engine.jobs.spawn_runner stubbed for the whole drive) — confirmed "
       "against the SAME production registry reader (engine.jobs.is_alive) "
       "a live deployment's own reaper would use, for every worker-id this "
       "drive spawned",
       result["orphan_count"] == 0 and len(result["spawn_calls"]) > 0,
       f"orphan_count={result['orphan_count']} spawn_calls="
       f"{[c['worker_id'] for c in result['spawn_calls']]}")

    return result


# ══════════════════════════════════════════════════════════════════════════
# Scenario 2 — the failing-test variant: gate.trunk holds -> sentry
# escalates -> a parked operator case. Proves the SIM exercises the
# NON-happy path, not just the golden one.
# ══════════════════════════════════════════════════════════════════════════
FAIL_BLOCK = "02-01"
FAIL_BLOCKS = [{"id": FAIL_BLOCK, "depends_on": [], "reviewer_class": "none",
               "title": "double(x): DELIBERATELY BROKEN (never fixed)"}]
FAIL_MAX_TICKS = 30

_BROKEN_DOUBLE_BODY = (
    '"""app/lib/02-01.py — double(x), DELIBERATELY BROKEN for '
    'core.sim.sim_l2_rig\'s failing-test variant (identity instead of *2, '
    'never fixed/re-merged) — genuinely fails the mockup\'s real declared '
    'test command on trunk."""\n\n'
    "def double(x):\n"
    "    return x   # BUG: should be x * 2 — deliberately never fixed\n\n\n"
    "def check():\n"
    "    return double(21) == 42\n"
)


def _failing_transcript():
    return sim_worker.default_transcript(overrides={
        FAIL_BLOCK: ("app/lib/02-01.py", _BROKEN_DOUBLE_BODY),
    })


def run_failing_test_variant():
    result = sim_run.run_sim(
        FAIL_BLOCKS, worker_count=1, max_ticks=FAIL_MAX_TICKS,
        transcript=_failing_transcript())

    root = result["root"]
    g = (result["final_manifest"].get("gates") or {}).get(FAIL_BLOCK, {})
    trunk_fail_ticks = [h["i"] for h in result["history"]
                       if h["outcomes"].get(FAIL_BLOCK, (None, None))[0] == "trunk_failed"]

    never_advanced_past_trunk = all(
        h["outcomes"].get(FAIL_BLOCK, (None,))[0] not in ("record_waiting", "record_landed",
                                                          "record_pending", "record_fail_closed",
                                                          "close_ordered", "close_holding", "closed")
        for h in result["history"])
    ok("F1 (THE ADVERSARIAL TRUNK KILLER — must be GREEN): gate.trunk ran "
       "the REAL declared test command against the REAL merged sha and "
       "observed a genuine FAIL (the broken function actually failed, "
       "never simulated) — held at gate.trunk on every such tick, NEVER "
       "advanced into gate.record/close",
       len(trunk_fail_ticks) >= 1 and never_advanced_past_trunk,
       f"trunk_fail_ticks={trunk_fail_ticks} "
       f"never_advanced_past_trunk={never_advanced_past_trunk}")

    ok("F2: the CODE genuinely reached trunk (gate.merge is real and "
       "correct — it is gate.trunk's re-validation that must catch the "
       "red), but the ✅ record commit NEVER landed — the block never "
       "shows Done on trunk",
       g.get("merged_sha") is not None and g.get("record_case_id") is None
       and "**Status:** ✅ Done" not in _git_out(
           ["show", f"main:meta/blocks/{FAIL_BLOCK}.md"], root),
       f"merged_sha={g.get('merged_sha')} record_case_id={g.get('record_case_id')}")

    ok("F3 (SENTRY ESCALATE KILLER — must be GREEN): the gate, held idle at "
       "gate.trunk past gate_idle_cap, was ESCALATED by core.sentry (never "
       "by core.gate itself — a real red is never the same thing as a "
       "violation to self-escalate)",
       g.get("stage") == gate.STAGE_ESCALATED
       and any(e.get("block") == FAIL_BLOCK and e.get("stage") == "trunk"
              for e in result["escalations"]),
       f"stage={g.get('stage')} escalations={result['escalations']}")

    case = next((c for c in result["cases"].values() if c.get("block") == FAIL_BLOCK), None)
    ok("F4 (PARKED CASE KILLER — must be GREEN): the SAME cap escalation "
       "opened a parked operator case (source=sentry.cap), never resumed, "
       "worker slot freed — the raise-and-defer half of the design, never "
       "a silent hang",
       case is not None and case.get("source") == "sentry.cap"
       and case.get("decision") is None and case.get("kind") == "cap",
       f"case={case}")

    ok("F5 (NEVER A FALSE SESSION-END — must be GREEN): a permanently "
       "parked/escalated block keeps the run from EVER reading as settled "
       "— no session-end marker fired across the whole drive",
       not bool((result["session_end"] or {}).get("ended_at")),
       f"session_end={result['session_end']}")

    ok("F6 (QUIESCENT-AFTER — must be GREEN): every tick after the "
       "escalation is a true no-op for this block — never re-picked "
       "(casestate.dispatch_excluded_blocks), never re-paced (terminal "
       "gates are skipped by core.sentry.pace)",
       all(FAIL_BLOCK not in h["outcomes"] and FAIL_BLOCK not in h["nudged"]
           and FAIL_BLOCK not in dict(h["escalated"])
           for h in result["history"][result["history"].index(
               next(h for h in result["history"] if FAIL_BLOCK in dict(h["escalated"]))) + 1:]),
       "checked every post-escalation tick")

    return result


# ══════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════
def main():
    happy = run_happy_path()
    failing = run_failing_test_variant()

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.sim.sim_l2_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    print(f"\n[happy] root={happy['root']}")
    print(f"[happy] ticks_used={happy['ticks_used']} (cap={HAPPY_MAX_TICKS}) "
          f"session_ended_tick={happy['session_ended_tick']}")
    print(f"[happy] session={happy['session_end']}")
    print(f"[happy] adhoc_blocks={sorted(happy['driver'].adhoc_authored)}")
    print(f"[happy] reviewer_ids={[a for a in happy['driver'].reviewer_seen]}")
    print(f"[happy] orphan_count={happy['orphan_count']} idempotent={happy['idempotent']['ok'] if happy['idempotent'] else None}")

    print(f"\n[failing] root={failing['root']}")
    print(f"[failing] ticks_used={failing['ticks_used']} (cap={FAIL_MAX_TICKS})")
    print(f"[failing] final gate={ (failing['final_manifest'].get('gates') or {}).get(FAIL_BLOCK) }")
    print(f"[failing] escalations={failing['escalations']}")
    print(f"[failing] cases={failing['cases']}")

    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
