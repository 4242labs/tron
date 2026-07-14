#!/usr/bin/env python3
"""l1_discovery_check.py — AC-1 (block 01-40 T1) CI proof.

`scripts/l1.sh` discovers rigs by glob (`core/*_rig.py`, `core/sim/*_rig.py`),
never a hand-maintained list. Proves that live: seeds a throwaway rig under
`core/` (removed after, either way), asserts l1.sh's discovery includes it,
AND that its PASS/FAIL result is genuinely reflected in l1.sh's own exit code
— non-vacuity, the same "MUTATION -> RED" discipline every rig in this repo
already uses. A seeded PASSING rig alone would only prove the glob lists more
files; it would NOT prove l1.sh actually RUNS what it discovers. The seeded
FAILING rig closes that gap.

Exit 0 only if:
  the seeded PASSING rig is discovered AND l1.sh exits 0
  the seeded FAILING rig is discovered AND l1.sh exits nonzero
  neither seeded file survives past this script
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L1 = os.path.join(ROOT, "scripts", "l1.sh")

PASS_RIG = '''"""seeded throwaway rig — AC-1 discovery proof, passing variant."""
import sys


def main():
    print("_ac1_seeded_pass_rig: PASS (1/1)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

FAIL_RIG = '''"""seeded throwaway rig — AC-1 discovery proof, failing variant (non-
vacuity: proves l1.sh actually RUNS a discovered rig, not merely counts it)."""
import sys


def main():
    print("_ac1_seeded_fail_rig: FAIL (0/1) — deliberate, proves l1.sh propagates it")
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def _seed(name, content):
    path = os.path.join(ROOT, "core", name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def _run_l1():
    return subprocess.run([L1], cwd=ROOT, capture_output=True, text=True)


def main():
    failed = False

    pass_path = _seed("_ac1_seeded_pass_rig.py", PASS_RIG)
    try:
        r = _run_l1()
        if "_ac1_seeded_pass_rig.py" not in r.stdout:
            print("AC-1 FAILURE: l1.sh did not discover the seeded passing rig.",
                  file=sys.stderr)
            print(r.stdout, file=sys.stderr)
            failed = True
        elif r.returncode != 0:
            print("AC-1 FAILURE: l1.sh failed with a seeded PASSING rig present "
                  f"(rc={r.returncode}) — unrelated regression, investigate.",
                  file=sys.stderr)
            print(r.stdout, file=sys.stderr)
            failed = True
        else:
            print("AC-1 discovery proof (pass variant) confirmed: seeded rig "
                  "discovered, l1.sh green.")
    finally:
        os.remove(pass_path)

    fail_path = _seed("_ac1_seeded_fail_rig.py", FAIL_RIG)
    try:
        r = _run_l1()
        if "_ac1_seeded_fail_rig.py" not in r.stdout:
            print("AC-1 FAILURE: l1.sh did not discover the seeded failing rig.",
                  file=sys.stderr)
            print(r.stdout, file=sys.stderr)
            failed = True
        elif r.returncode == 0:
            print("AC-1 REGRESSION: l1.sh exited 0 with a seeded FAILING rig "
                  "present — discovery is vacuous (lists but doesn't run/propagate).",
                  file=sys.stderr)
            failed = True
        else:
            print("AC-1 non-vacuity proof (fail variant) confirmed: seeded "
                  "failing rig discovered AND its failure propagated (l1.sh "
                  f"rc={r.returncode}).")
    finally:
        os.remove(fail_path)

    print(f"\nAC-1: {'PASS' if not failed else 'FAIL'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
