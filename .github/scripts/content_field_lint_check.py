#!/usr/bin/env python3
"""content_field_lint_check.py — AC-6 (block 01-31, ADR-0002 D5) CI proof.

Runs the no-default content-field lint (engine/lint.py:content_field_lint) two ways in
one script, each a hard gate:

  RED   a seeded `.get(<content-field>, default)` violation, in a throwaway fixture
        file, MUST be caught. If it isn't, the lint itself has regressed — fail loud.
  GREEN the real engine source tree (fsm.py, jobs.py) MUST currently be clean. If it
        isn't, a content-field violation has landed — fail loud.

Exit 0 only if both checks land as expected (RED catches; GREEN is clean).
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "engine"))

import lint  # noqa: E402


def main():
    failed = False

    with tempfile.TemporaryDirectory(prefix="tron-ci-content-lint-") as d:
        fixture = os.path.join(d, "fixture.py")
        with open(fixture, "w", encoding="utf-8") as fh:
            fh.write('detail = m.get("detail", "wall")\n')
        red_ok, red_violations = lint.content_field_lint([fixture])
        if red_ok:
            print("AC-6 REGRESSION: the seeded content-field violation was NOT caught "
                  "(expected RED, got GREEN).", file=sys.stderr)
            failed = True
        else:
            print(f"RED proof confirmed: {red_violations}")

    green_ok, green_violations = lint.content_field_lint(lint._engine_source_files())
    if not green_ok:
        print(f"AC-6 FAILURE: the real engine tree has content-field violations: "
              f"{green_violations}", file=sys.stderr)
        failed = True
    else:
        print("GREEN proof confirmed: the engine tree is clean.")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
