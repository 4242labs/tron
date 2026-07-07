"""block_01_27_test — outage resilience proven (block 01-27).

T3/F-4 (found by the 02-05 review): `_drive_close`'s `gate_close_cap` IDLE path
(fsm.py, the `_cap` closure under the close-ladder's `_pace_ladder` call) used to
`_force_release_block` a stuck engineer directly — no `events.failure`, no wall, a
SILENT paperwork discard. The sibling ATTEMPTS-COUNT path a few hundred lines down
(`_confirm_close`'s `close_nudges` cap, code `gate-close-dirty`) already escalates via
`_gate_giveup`. This block routes the idle path through the SAME machinery, with its
own named code (`gate-close-idle-cap`, in `GATE_GIVEUP_SPLIT_CODES`/`WALL_KINDS`) since
an idle timeout is a different cause than a confirmed paperwork/replica defect — never
the generic 'wall'. NET-ZERO: no new knob, no new stage, the existing escalation
machinery only.

AC-6 here proves: the stuck close now raises `events.failure` + a wall whose processed
case carries a DISTINCT kind (`gate-close-idle-cap`, not `wall`, not `gate-close-dirty`)
and the worker is held (walled), never silently vanished from the roster. Fail-before:
reverting the fsm.py fix (restoring the direct `_force_release_block` call) makes this
fail, since no wall/failure record is ever raised and the worker is removed outright.

The 01-27 T1 fault-injection drill (fleet-wide outage self-release, discharging 01-23
AC-6) lives in block_01_20_test.py, alongside the rest of the fleet-hold/canary
machinery it extends — not duplicated here.

Run: python3 engine/block_01_27_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import jobs                              # noqa: E402
import util                               # noqa: E402
from fsm import Engine, GATE_GIVEUP_SPLIT_CODES, WALL_KINDS  # noqa: E402
from sentry_test import build, started    # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _events(eng):
    return util.read_jsonl(eng.ctx.event_log)


def _eng(block="A-01"):
    ctx, _ = build(blocks=[(block, "🔄", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def t3_gate_close_idle_cap_is_a_named_split_code():
    """The new code is wired into the SAME 01-26 vocabulary as its six siblings — naming
    only, no new mechanism."""
    ok("F-4 'gate-close-idle-cap' is one of _gate_giveup's named split codes",
       "gate-close-idle-cap" in GATE_GIVEUP_SPLIT_CODES)
    ok("F-4 'gate-close-idle-cap' is covered by WALL_KINDS (hold/settle/retract unchanged)",
       "gate-close-idle-cap" in WALL_KINDS)


def t3_stuck_close_idle_cap_escalates_not_silent():
    """AC-6: a stuck-close force-release now raises a NAMED escalation (events.failure +
    a distinct case-kind), never a silent _force_release_block."""
    eng = _eng()
    eng.st.row("A-01")["status"] = "done"
    g = eng.st.gate.setdefault("A-01", {"stage": "close", "pr": None})
    clock = {"t": 1000.0}
    eng._now_s = lambda: clock["t"]
    orig_idle = jobs.runner_idle
    jobs.runner_idle = lambda wid, idx=None: True   # idle -> wall-clock to the cap
    try:
        eng._tq = []
        eng._drive_close("A-01", g, "ENG-A-01")             # anchors close_idle_since
        clock["t"] += eng._pace("gate_close_cap", 3) + 1
        eng._drive_close("A-01", eng.st.gate["A-01"], "ENG-A-01")   # cap fires

        ok("AC-6 the gate is dropped (no longer waited on)",
           "A-01" not in eng.st.gate, f"gate={eng.st.gate}")
        ok("AC-6 a NAMED wall is raised (never silent) with the distinct close-idle code",
           any(t == "wall:raised:A-01" and s.get("code") == "gate-close-idle-cap"
               for t, s in eng._tq),
           f"tq={eng._tq}")
        ok("AC-6 events.failure recorded the stuck close-out (gate-stuck / "
           "gate-close-idle-cap) — reconstructable offline, never a bare release",
           any(e.get("kind") == "failure" and e.get("fclass") == "gate-stuck"
               and e.get("code") == "gate-close-idle-cap" for e in _events(eng)),
           f"events={_events(eng)}")
        ok("AC-6 the worker is STILL on the roster (held, not silently discarded)",
           any(w.get("id") == "ENG-A-01" for w in eng.st.workers),
           f"workers={eng.st.workers}")

        # Route (never the full _drain_triggers -- with only one block in play,
        # draining the wall's own trailing 'pulse' cascades into _switchboard's
        # _all_settled -> _end_session, an unrelated session-lifecycle concern this
        # test has no business exercising): _h_escalate turns the wall into a pending,
        # DECIDABLE case whose OWN kind is the distinct code (01-26's split, never the
        # generic 'wall'), and holds (walls) the worker rather than releasing it.
        trig, slots = next(t for t in eng._tq if t[0].startswith("wall:raised:"))
        eng._route(trig, slots)
        cases = eng.st.pending_cases
        ok("AC-6 the drained wall opens a pending case with a DISTINCT case-kind (not "
           "the generic 'wall', not 'gate-close-dirty' — a different cause)",
           any(c.get("kind") == "gate-close-idle-cap" for c in cases.values()),
           f"cases={cases}")
        ok("AC-6 the worker is HELD (walled) — pages the operator, never vanishes",
           any(w.get("id") == "ENG-A-01" and w.get("status") == "walled"
               for w in eng.st.workers),
           f"workers={eng.st.workers}")
    finally:
        jobs.runner_idle = orig_idle


def main():
    for fn in sorted(k for k in globals() if k.startswith("t3_")):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
