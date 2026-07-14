#!/usr/bin/env python3
"""r3_honesty_lint_check.py — AC-2 (block 01-40 T1) CI proof.

`core/r3_lint.py` is the R3 honesty lint: a harness may not fabricate a
sender kind the real door (scripts/report.sh) could never produce, nor
mutate `manifest[...]` state directly. Proves, live:

  RED        a seeded direct-write fixture trips BOTH illegal shapes named
             in the block ("manifest[...] / ctx inboxes"): a fabricated
             non-worker sender written to the inbox file, and a
             manifest[...][...] direct assignment.
  GREEN      a door-only fixture (the real report.sh shape: worker sender,
             or no sender key at all) is clean.
  GREEN/tree the real `core/` proof-harness tree is clean except the
             explicit, visible KNOWN_RED list (core/sim/operator_proxy.py
             at minimum) — every KNOWN_RED entry is re-verified genuinely
             red on THIS run, never a silent whitelist.
  MECHANISM  the lint's own stale/unlisted detectors fire correctly — a
             known-red entry that has gone clean is caught, and a red file
             missing from KNOWN_RED is caught — proven with synthetic
             KNOWN_RED overrides, never by editing the real list.

Exit 0 only if every one of the above holds.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "core"))

import r3_lint  # noqa: E402

DIRECT_WRITE_FIXTURE = '''
import json


def inject(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "proxy"}}
    with open(eng.ctx.worker_inbox, "a") as ib:
        ib.write(json.dumps(rep) + "\\n")


def mutate(manifest, case_id, verb):
    manifest["cases"][case_id]["decision"] = {"verb": verb}
'''

DOOR_ONLY_FIXTURE = '''
from util import append_jsonl


def report_online(tron_ctx, agent_id, branch):
    append_jsonl(tron_ctx.worker_inbox,
                 {"tag": "worker.online", "agent_id": agent_id, "slots": {"branch": branch}})
'''


def main():
    failed = False

    # ── RED: the direct-write fixture must trip BOTH named illegal shapes ──
    violations = r3_lint.lint_source(DIRECT_WRITE_FIXTURE, path="<direct-write-fixture>")
    rules_hit = {v.rule for v in violations}
    if {"INBOX_FABRICATED_SENDER", "MANIFEST_DIRECT_WRITE"} <= rules_hit:
        print(f"RED proof confirmed: {[str(v) for v in violations]}")
    else:
        print("AC-2 REGRESSION: the direct-write fixture was NOT fully caught "
              f"(expected both illegal shapes, got {rules_hit}).", file=sys.stderr)
        failed = True

    # ── control: a door-only fixture (real report.sh shape) must be clean ──
    clean_violations = r3_lint.lint_source(DOOR_ONLY_FIXTURE, path="<door-only-fixture>")
    if clean_violations:
        print("AC-2 REGRESSION: a door-only fixture (worker sender, matches "
              f"report.sh's own real shape) was flagged: {[str(v) for v in clean_violations]}",
              file=sys.stderr)
        failed = True
    else:
        print("GREEN proof (fixture) confirmed: a door-only report is clean.")

    # ── GREEN on tree, modulo the explicit KNOWN_RED list ──
    result = r3_lint.run()
    if result.stale_known_red:
        print(f"AC-2 FAILURE: KNOWN_RED entries came back CLEAN (stale — "
              f"remove them, or a real regression hid behind a silent "
              f"whitelist): {result.stale_known_red}", file=sys.stderr)
        failed = True
    if result.unlisted_offenders:
        print(f"AC-2 FAILURE: dishonest harness(es) NOT in the explicit "
              f"KNOWN_RED list: {result.unlisted_offenders}", file=sys.stderr)
        failed = True
    if not result.stale_known_red and not result.unlisted_offenders:
        print("GREEN proof (tree) confirmed: the proof-harness tree is clean "
              f"except the tracked KNOWN_RED set: {sorted(r3_lint.KNOWN_RED)}")

    # ── the named offender is, concretely, red ──
    op_proxy = "core/sim/operator_proxy.py"
    if op_proxy not in result.violations_by_file:
        print(f"AC-2 FAILURE: {op_proxy} (the ADR's named offender) is NOT "
              "flagged red.", file=sys.stderr)
        failed = True
    else:
        print(f"Previously-dishonest rig confirmed RED: {op_proxy} -> "
              f"{[str(v) for v in result.violations_by_file[op_proxy]]}")

    # ── mechanism self-test: stale-entry detection (synthetic KNOWN_RED,
    #     never touches the real list) ──
    orig_known_red = r3_lint.KNOWN_RED
    try:
        r3_lint.KNOWN_RED = dict(orig_known_red)
        r3_lint.KNOWN_RED["core/does_not_exist_rig.py"] = {
            "owning_block": "none", "reason": "synthetic stale-entry self-test"}
        stale_check = r3_lint.run()
        if "core/does_not_exist_rig.py" not in stale_check.stale_known_red:
            print("AC-2 REGRESSION: stale-known-red detection did not fire "
                  "for a synthetic clean-but-listed entry.", file=sys.stderr)
            failed = True
        else:
            print("Mechanism proof confirmed: a stale KNOWN_RED entry is caught.")
    finally:
        r3_lint.KNOWN_RED = orig_known_red

    # ── mechanism self-test: unlisted-offender detection (synthetic) ──
    try:
        r3_lint.KNOWN_RED = {}
        unlisted_check = r3_lint.run()
        if "core/sim/operator_proxy.py" not in unlisted_check.unlisted_offenders:
            print("AC-2 REGRESSION: unlisted-offender detection did not fire "
                  "when KNOWN_RED was emptied.", file=sys.stderr)
            failed = True
        else:
            print("Mechanism proof confirmed: an unlisted offender is caught.")
    finally:
        r3_lint.KNOWN_RED = orig_known_red

    print(f"\nAC-2: {'PASS' if not failed else 'FAIL'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
