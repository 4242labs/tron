#!/usr/bin/env python3
"""r3_honesty_lint_check.py — AC-2 (block 01-40 T1) CI proof.

`core/r3_lint.py` is the R3 honesty lint: a harness may not fabricate a
sender kind the real door (scripts/report.sh) could never produce, write
`ctx.operator_inbox` at all (no real operator transport exists yet), nor
mutate `manifest[...]` state directly. This is the REBUILT version (a hostile
review proved the original pattern-matched a fingerprint of the one known
offender, not the illegal CLASS — 10/10 plain evasions defeated it). Proves,
live:

  RED (x10)  each of the 10 evasions the review demonstrated against the OLD
             lint is caught by the rebuilt one: a renamed inbox-path
             variable, a `file=` kwarg path, `json.dump` to the inbox
             handle, a bare `open()` with no `with`, a same-file helper
             function hiding the actual write, a `subprocess` shell `>>`
             append, a `manifest` alias before subscripting, a depth-1
             `manifest["cases"] = ...` wholesale overwrite, a `.update()`
             call instead of a subscript assignment, and a `sender` dict
             built via a helper call instead of an inline literal.
  GREEN      two legal shapes stay clean: a door-only report (worker sender,
             or no sender key at all — report.sh's own shape) written
             straight, AND the identical "helper indirection" MECHANISM used
             legitimately (a thin same-file wrapper whose every real call
             site sends a safe payload) — proving the lint tells indirection
             APART from a violation, rather than reddening all indirection.
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

# ─────────────────── the 10 evasions (each must stay RED) ───────────────────
# Every one of these is a DIRECT rewrite of the SAME violation the original
# lint caught (an operator-sender fabrication into worker_inbox, or a direct
# manifest mutation) — only the SYNTACTIC SHAPE changed. The old lint pattern-
# matched one shape per rule; these proved it caught none of the other nine.

EVASION_FIXTURES = {
    "1_renamed_inbox_path_variable": '''
import json

def bad(eng):
    p = eng.ctx.worker_inbox
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    with open(p, "a") as ib:
        ib.write(json.dumps(rep) + "\\n")
''',
    "2_path_as_file_kwarg": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    with open(file=eng.ctx.worker_inbox, mode="a") as ib:
        ib.write(json.dumps(rep) + "\\n")
''',
    "3_json_dump_to_inbox_handle": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    with open(eng.ctx.worker_inbox, "a") as ib:
        json.dump(rep, ib)
''',
    "4_bare_open_no_with": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    ib = open(eng.ctx.worker_inbox, "a")
    ib.write(json.dumps(rep) + "\\n")
    ib.close()
''',
    "5_helper_function_indirection": '''
import json

def _emit(eng, obj):
    with open(eng.ctx.worker_inbox, "a") as ib:
        ib.write(json.dumps(obj) + "\\n")

def bad(eng):
    _emit(eng, {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}})
''',
    "6_subprocess_shell_append": '''
import json
import subprocess

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    subprocess.run(["bash", "-c", f"echo '{json.dumps(rep)}' >> {eng.ctx.worker_inbox}"])
''',
    "7_manifest_alias": '''
def bad(manifest, case_id, verb):
    m = manifest
    m["cases"][case_id]["decision"] = {"verb": verb}
''',
    "8_depth1_wholesale_overwrite": '''
def bad(manifest, new_cases):
    manifest["cases"] = new_cases
''',
    "9_update_call": '''
def bad(manifest, case_id, decision):
    manifest["cases"][case_id].update({"decision": decision})
''',
    "10_sender_built_via_helper_call": '''
import json

def _build_sender():
    return {"kind": "operator", "id": "x"}

def bad(eng):
    rep = {"tag": "operator.decision", "sender": _build_sender()}
    with open(eng.ctx.worker_inbox, "a") as ib:
        ib.write(json.dumps(rep) + "\\n")
''',
}

# ─────────────────────── legal shapes (must stay GREEN) ───────────────────────

DOOR_ONLY_FIXTURE = '''
from util import append_jsonl


def report_online(tron_ctx, agent_id, branch):
    append_jsonl(tron_ctx.worker_inbox,
                 {"tag": "worker.online", "agent_id": agent_id, "slots": {"branch": branch}})
'''

# The SAME mechanism as evasion #5 (a same-file helper wrapping the actual
# write) — but every real call site sends a safe payload (no `sender` key at
# all, matching core/casestate_rig.py's own real `inject()` helper). Proves
# the lint judges a wrapper by what its call sites ACTUALLY send, not by
# reddening all indirection on sight.
LEGAL_HELPER_INDIRECTION_FIXTURE = '''
from util import append_jsonl


def inject(tron_ctx, obj):
    append_jsonl(tron_ctx.worker_inbox, obj)


def use_it(tron_ctx):
    inject(tron_ctx, {"tag": "operator.decision", "slots": {"case_id": "c1", "verb": "resume"}})
    inject(tron_ctx, {"tag": "operator.decision", "slots": {"case_id": "c2", "verb": "abandon"}})
'''


def main():
    failed = False

    # ── RED x10: every evasion must still be caught ──
    for name, fixture in EVASION_FIXTURES.items():
        violations = r3_lint.lint_source(fixture, path=f"<evasion:{name}>")
        if violations:
            print(f"RED proof confirmed [{name}]: {[str(v) for v in violations]}")
        else:
            print(f"AC-2 REGRESSION: evasion fixture [{name}] was NOT caught "
                  "(expected RED, got GREEN — the lint is fingerprinting a shape again, "
                  "not the illegal class).", file=sys.stderr)
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

    # ── control: legal helper indirection (same mechanism as evasion #5,
    #     safe payloads at every real call site) must ALSO be clean ──
    legal_indirection_violations = r3_lint.lint_source(
        LEGAL_HELPER_INDIRECTION_FIXTURE, path="<legal-helper-indirection-fixture>")
    if legal_indirection_violations:
        print("AC-2 REGRESSION: a legitimate same-file helper wrapper (every call site "
              f"sends a safe, sender-less payload) was flagged: "
              f"{[str(v) for v in legal_indirection_violations]}", file=sys.stderr)
        failed = True
    else:
        print("GREEN proof (fixture) confirmed: legal helper indirection (safe payload "
              "at every call site) is clean — the lint judges call sites, not the mere "
              "presence of indirection.")

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
