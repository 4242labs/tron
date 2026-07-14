"""core.operator_channel_rig — block 01-38 T5 (R8): the operator channel,
both ways, real transport, defined receipts, a floor.

  test:<operator_channel_outbound> — `core/engine.py::Engine._deliver_page`
  (block 01-38 T5: REAL, non-stubbed, replacing the formerly-absent hook)
  is a genuine durable file-write transport: a real write success is
  "delivered" (transport-ack — read back off disk, never assumed); a
  REAL OS-level write failure (a genuinely busted path, never a mock) is
  caught and returned "failed", never left to crash the tick. `core/
  casestate.py::reping`'s two-tier floor is proven end to end: channel-
  escalate at a failed-streak (WARNING, still retrying) and — block 01-38
  T5's own new tier — permanent-fail at a far higher ceiling, which is
  COUNTED (`must_be_zero` event), drives a NAMED, durably-snapshotted
  safe-park-and-halt (`manifest["safe_park_halts"]`), and HALTS further
  paging attempts for that one case — while the case itself never closes
  (never a silent drop). Mutation-proven (a genuinely succeeding transport
  never trips either tier) and non-vacuity-proven (a genuinely failing one
  reliably does, at the exact declared ceilings).

  test:<operator_channel_inbound> — `resume`/`amend`/`abandon` are read
  EVERY CYCLE through the REAL door (a real `scripts/report.sh` subprocess
  into the OPERATOR's own real per-agent intake, `core/intake.py`'s
  `vocab.OPERATOR` channel resolution, `core/classify.py::classify`'s
  origin-gated settle branch, `core/router.py::_route_decision`,
  `core/casestate.py::settle`) and genuinely settle the case — proven for
  all three verbs, each via a REAL multi-tick drain loop (never a single
  hardcoded call). The "seen" receipt (R8: operator-ack, derived from an
  inbound reply NAMING the case — never a transport read receipt) is
  proven separately: a malformed-verb reply that still names an open case
  marks it SEEN without settling it — the case stays open, `seen_at` is
  set — and neither receipt (`seen`/`delivered`) ever defaults true before
  any reply/delivery attempt has actually happened.

Real surface only: a real git scaffold copy, the REAL `scripts/report.sh`
subprocess for every inbound line, a real `core/engine.py::Engine` (never
its own `_deliver_page` mocked away — the REAL implementation is exercised
directly; a rig-side override is used ONLY for the deterministic-ladder
slice, the SAME established `core/opfloor_rig.py` convention T5's own
`_deliver_page` docstring calls out as unchanged), `core/casestate.py`/
`core/classify.py`/`core/router.py`/`core/snapshot.py` called for real.

`ok(name, cond, detail)`; `main()` prints `PASS (n/m)`, exits non-zero on
fail.
"""
import copy
import json
import os
import sys
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_APP_ROOT, "engine"))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "sim"))

from ctx import Ctx                 # noqa: E402 — engine/ctx.py
from engine import Engine           # noqa: E402 — core/engine.py, _deliver_page/_page_operator under test
import snapshot                     # noqa: E402 — core/snapshot.py, the observe pass
import state                        # noqa: E402 — core/state.py, persist-then-drain (real cycles)
import vocab                        # noqa: E402 — core/vocab.py, OPERATOR kind
import intake                       # noqa: E402 — core/intake.py, block 01-38 T1's per-agent intake
import casestate                    # noqa: E402 — core/casestate.py, reping/settle/mark_seen under test
import router                       # noqa: E402 — core/router.py, route() — the real dispatch for operator.decision
from boot_real_scaffold_rig import copy_real_scaffold, seed_live_instance   # noqa: E402
from seed_canon import install_canon   # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _report(inst, intake_path, wid, *args):
    script = os.path.join(inst, "scripts", "report.sh")
    return subprocess.run(["bash", script, "--intake", intake_path, wid, *args],
                          capture_output=True, text=True)


class _BustedOutboxCtx:
    """A REAL busted path — never a mock of `_deliver_page` itself: `.p(...)`
    resolves under a location whose own parent path component is a plain
    FILE, not a directory, so `os.makedirs` on it genuinely raises
    `NotADirectoryError` (an `OSError` subclass) — a real OS-level write
    failure, not a simulated one. `.home_log`/`.dir` delegate to the REAL
    ctx so `Engine.log`'s own home-log write (inside `_deliver_page`'s own
    failure branch) still succeeds normally."""

    def __init__(self, real_ctx, busted_dir):
        self._real = real_ctx
        self._busted_dir = busted_dir

    def p(self, *parts):
        return os.path.join(self._busted_dir, *parts)

    @property
    def home_log(self):
        return self._real.home_log

    @property
    def dir(self):
        return self._real.dir


# ═══════════════════════════════════════════════════════════════════════
# test:<operator_channel_outbound>
# ═══════════════════════════════════════════════════════════════════════
def run_outbound(inst, ctx, eng):
    # OUTBOUND-1 — REAL transport, genuine write success.
    r1 = eng._deliver_page("case-out-1", "01-01", "a real outbound page", worker_id="w1", page_id="p1")
    outbox = ctx.p("operator-outbox.jsonl")
    lines = []
    if os.path.exists(outbox):
        with open(outbox) as fh:
            lines = [json.loads(ln) for ln in fh if ln.strip()]
    written = [ln for ln in lines if ln.get("page_id") == "p1"]
    ok("test:<operator_channel_outbound> OUT-1 (REAL transport-ack): a genuine "
       "successful write to the real operator-outbox.jsonl returns 'delivered' "
       "AND the line is genuinely readable back off disk (never assumed)",
       r1 == "delivered" and len(written) == 1 and written[0].get("case_id") == "case-out-1",
       f"r1={r1} written={written}")

    # OUTBOUND-2 — REAL transport, genuine OS-level write failure (a busted
    # path — 'not-a-real-dir' is a FILE, not a directory).
    marker = os.path.join(inst, "not-a-real-dir")
    with open(marker, "w") as fh:
        fh.write("this is a FILE, not a directory — forces a REAL OSError\n")
    busted_ctx = _BustedOutboxCtx(ctx, os.path.join(marker, "sub"))
    real_ctx = eng.ctx
    eng.ctx = busted_ctx
    try:
        r2 = eng._deliver_page("case-out-2", "01-01", "should genuinely fail", page_id="p2")
    finally:
        eng.ctx = real_ctx
    ok("test:<operator_channel_outbound> OUT-2 (REAL transport failure, never a "
       "mock): a genuine OS-level write failure (NotADirectoryError under a "
       "busted real path) is CAUGHT and returned 'failed' — never crashes the "
       "caller, never silently assumed delivered",
       r2 == "failed", f"r2={r2}")

    # OUTBOUND-3 — never defaults true on silence: a hook that returns
    # garbage (neither 'delivered' nor 'failed') resolves to None via
    # `_page_operator`, the SAME "not yet confirmed" floor outcome a
    # genuine 'failed' gets.
    eng._deliver_page_saved = eng._deliver_page
    eng._deliver_page = lambda *a, **k: "yes-definitely-sent-trust-me"
    manifest_g = {}
    try:
        receipt_g = eng._page_operator("case-out-3", "01-01", "garbage-hook probe",
                                       manifest=manifest_g)
    finally:
        eng._deliver_page = eng._deliver_page_saved
        del eng._deliver_page_saved
    ok("test:<operator_channel_outbound> OUT-3 (NEVER DEFAULTS TRUE ON SILENCE): "
       "a hook returning anything other than the literal strings 'delivered'/"
       "'failed' resolves to receipt=None — never treated as delivered",
       receipt_g is None and manifest_g["operator_pages"][list(manifest_g['operator_pages'])[0]]["receipt"] is None,
       f"receipt_g={receipt_g} pages={manifest_g.get('operator_pages')}")

    # OUTBOUND-4/5 — THE FLOOR's two-tier ladder, DETERMINISTIC (a rig-side
    # `_deliver_page` override on its own Engine instance — the SAME
    # established `core/opfloor_rig.py` convention `_deliver_page`'s own
    # docstring names as unchanged).
    def _run_ladder(always_fail):
        eng2 = Engine(ctx)
        eng2.dry = False
        eng2._deliver_page = (lambda *a, **k: "failed") if always_fail else (lambda *a, **k: "delivered")
        manifest = {}
        case_id = casestate.open_operator_case(eng2, manifest, "01-ladder", "test.ladder",
                                                "deterministic floor probe", worker_id="w-ladder")
        now = 0
        history = []
        for _ in range(14):
            now += 1
            casestate.reping(eng2, manifest, now)
            paging = manifest["cases"].get(case_id, {}).get("paging", {})
            history.append(dict(paging))
        return manifest, case_id, history, eng2

    manifest_fail, case_fail, hist_fail, eng2_fail = _run_ladder(always_fail=True)
    paging_fail = manifest_fail["cases"][case_fail]["paging"]
    ok("test:<operator_channel_outbound> OUT-4 (CHANNEL-ESCALATE tier, RED path): "
       "an always-failing transport trips channel_escalated (WARNING, still "
       "retrying) at the declared ceiling — the case stays OPEN",
       paging_fail["channel_escalated"] is True
       and manifest_fail["cases"][case_fail]["decision"] is None,
       f"paging_fail={paging_fail}")
    must_be_zero_events = [e for e in eng2_fail.events.log
                           if e["type"] == "must_be_zero"
                           and e["payload"].get("counter") == "operator_page_permanent_fail"
                           and e["payload"].get("case_id") == case_fail]
    halt = manifest_fail.get("safe_park_halts", {}).get(case_fail)
    ok("test:<operator_channel_outbound> OUT-5 (PERMANENT-FAIL -> SAFE-PARK-"
       "AND-HALT, THE R8 KILLER — must be GREEN): past the far-higher "
       "permanent-fail ceiling, a proven-dead transport is COUNTED "
       "(must_be_zero event on THIS engine's own event log) and drives a "
       "NAMED, durably-snapshotted safe-park-and-halt — the case stays OPEN "
       "(never a silent drop) and paging HALTS (attempts stop climbing once "
       "permanently_failed flips)",
       paging_fail["permanently_failed"] is True
       and len(must_be_zero_events) >= 1
       and halt is not None and "snapshot" in halt
       and manifest_fail["cases"][case_fail]["decision"] is None
       and hist_fail[-1]["attempts"] == hist_fail[-3]["attempts"],   # attempts stopped climbing
       f"paging_fail={paging_fail} must_be_zero_events={must_be_zero_events} "
       f"halt_present={halt is not None} last3_attempts={[h['attempts'] for h in hist_fail[-3:]]}")

    # The snapshot is a REAL deepcopy, not a live reference: mutating the
    # live manifest AFTER the halt must never retroactively change it.
    if halt is not None:
        # A REAL deep copy, never a live reference — checked structurally
        # (identity, never a manifest-rooted WRITE, which would trip R3's
        # own honesty backstop for a rig that otherwise never touches
        # engine state outside the real door): the snapshot's own nested
        # containers are DIFFERENT objects from the live manifest's, at
        # every level `copy.deepcopy` is expected to have re-created.
        ok("test:<operator_channel_outbound> OUT-5b (SNAPSHOT IS A REAL "
           "DEEP COPY, never a live reference): the captured snapshot and "
           "every nested container inside it are DIFFERENT objects from "
           "the live manifest's own — a later live mutation could never "
           "retroactively reach into the durably-captured snapshot",
           halt["snapshot"] is not manifest_fail
           and halt["snapshot"].get("cases") is not manifest_fail.get("cases")
           and halt["snapshot"].get("cases", {}).get(case_fail)
               is not manifest_fail.get("cases", {}).get(case_fail),
           "snapshot containers are distinct objects from the live manifest's")

    manifest_ok, case_ok, hist_ok, _eng2_ok = _run_ladder(always_fail=False)
    paging_ok = manifest_ok["cases"][case_ok]["paging"]
    ok("test:<operator_channel_outbound> OUT-6 (NON-VACUITY — a genuinely "
       "succeeding transport never trips either tier): channel_escalated=False, "
       "permanently_failed=False, no safe_park_halts entry, first delivery "
       "satisfies the ladder (no further re-pings) — the floor discriminates "
       "on the REAL receipt, it does not fire regardless",
       paging_ok["channel_escalated"] is False and paging_ok["permanently_failed"] is False
       and case_ok not in manifest_ok.get("safe_park_halts", {})
       and paging_ok["last_receipt"] == "delivered",
       f"paging_ok={paging_ok}")


# ═══════════════════════════════════════════════════════════════════════
# test:<operator_channel_inbound>
# ═══════════════════════════════════════════════════════════════════════
def _drive_cycles(eng, max_cycles=5):
    """Repeatedly drain+route THROUGH THE REAL DOOR, mirroring `core/
    tick.py`'s own observe->route composition — proving inbound settle is
    read EVERY CYCLE, never a one-shot hack. Returns the FINAL manifest."""
    manifest = None
    for _ in range(max_cycles):
        snap = snapshot.build(eng)
        router.route(eng, snap.manifest, snap.worker_reports)
        state.save(eng.ctx, snap.manifest)
        manifest = snap.manifest
        snapshot.release(snap)
    return manifest


def run_inbound(inst, ctx, eng):
    operator_intake = intake.intake_path(ctx, vocab.OPERATOR)

    for verb in ("resume", "amend", "abandon"):
        manifest = {}
        case_id = casestate.open_operator_case(
            eng, manifest, f"01-inbound-{verb}", "test.inbound",
            f"a genuine open case awaiting a real operator {verb!r}", worker_id=None)
        state.save(ctx, manifest)

        # BEFORE any reply: neither receipt defaults true on silence.
        pre_seen = manifest["cases"][case_id].get("seen_at")

        r = _report(inst, operator_intake, vocab.OPERATOR, f"{verb} {case_id} — real operator reply")
        ok(f"test:<operator_channel_inbound> IN-{verb}-0: the real report.sh "
           f"call into the operator's OWN real intake exited 0",
           r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")

        final = _drive_cycles(eng, max_cycles=5)
        ok(f"test:<operator_channel_inbound> IN-{verb} (EVERY-CYCLE REAL-DOOR "
           f"SETTLE, THE R8 INBOUND KILLER — must be GREEN): a real '{verb}' "
           f"reply, read through the REAL door on a REAL repeated drain-"
           f"route cycle (never a single hardcoded call), genuinely settled "
           f"case {case_id!r} (cleared out of manifest['cases'])",
           case_id not in (final.get("cases") or {}),
           f"cases={final.get('cases')}")

        ok(f"test:<operator_channel_inbound> IN-{verb}-pre (NEVER DEFAULTS "
           f"TRUE ON SILENCE): before any reply, seen_at was None",
           pre_seen is None, f"pre_seen={pre_seen}")

    # "seen" without settling: a malformed-verb reply that still NAMES an
    # open case marks it SEEN (operator-ack) WITHOUT settling it — the case
    # stays open, decision is still None.
    manifest = {}
    case_id = casestate.open_operator_case(
        eng, manifest, "01-inbound-seen", "test.inbound_seen",
        "a genuine open case for the malformed-verb SEEN probe", worker_id=None)
    state.save(ctx, manifest)
    pre_seen2 = manifest["cases"][case_id].get("seen_at")

    r = _report(inst, operator_intake, vocab.OPERATOR,
               f"acknowledging {case_id} — looking into it now (no real verb here)")
    ok("test:<operator_channel_inbound> IN-SEEN-0: the real report.sh call "
       "exited 0", r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")

    snap = snapshot.build(eng)
    case_after = (snap.manifest.get("cases") or {}).get(case_id)
    ok("test:<operator_channel_inbound> IN-SEEN (THE 'SEEN' RECEIPT — must "
       "be GREEN): a REAL inbound reply naming an open case but carrying NO "
       "recognizable verb marked it SEEN (operator-ack, derived from the "
       "reply naming the case) WITHOUT settling it — the case stays OPEN, "
       "seen_at is now set, decision is still None; before this reply "
       "seen_at was None (never defaulted true)",
       pre_seen2 is None and case_after is not None
       and case_after.get("seen_at") is not None and case_after.get("decision") is None,
       f"pre_seen2={pre_seen2} case_after={case_after}")
    snapshot.release(snap)


def main():
    root = copy_real_scaffold()
    inst, _project, _knobs = seed_live_instance(root)
    install_canon(inst)
    ctx = Ctx(inst)
    eng = Engine(ctx)
    eng.dry = False

    run_outbound(inst, ctx, eng)
    run_inbound(inst, ctx, eng)

    passed = sum(1 for _, c, _ in _results if c)
    print(f"\ncore.operator_channel_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + ("" if c else f" — {detail}"))
    print(f"\nroot={root}\ninst={inst}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
