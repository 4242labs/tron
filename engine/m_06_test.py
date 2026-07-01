"""m_06_test — blueprint versioning acceptance (M-06 AC-4).

Covers the code-testable criterion: version drift between the instance's stamped
`project.yaml.tron_version` and its own copied canon `VERSION` hard-fails both
`tron validate` (lint L18) and `tron start` (the boot precheck), each naming both
versions; an unstamped instance (pre-M-06 seed) fails the same way; a matching
stamp passes; canon self-lint (no project.yaml) skips L18 entirely.

AC-1/2/3/5/6/7 are file-existence, CI-observation, live-seed, cmd, and screenshot
checks — not unit-testable here; see blocks/m-06-blueprint-versioning.md.
"""
import os
import sys
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import lint             # noqa: E402
import engine as engine_cli  # noqa: E402
from ctx import Ctx     # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _l18(results):
    return next(r for r in results if r.rule.startswith("L18"))


def t_canon_self_lint_skips_without_project():
    ctx = Ctx(ROOT)   # the real canon root — no project.yaml here
    _, results = lint.run(ctx, None)
    r = _l18(results)
    ok("canon self-lint: L18 skipped (no project.yaml)", r.ok)


def t_matching_stamp_passes():
    ctx = Ctx(ROOT)
    canon_v = ctx.load_version()
    ok("canon VERSION file present", canon_v)
    _, results = lint.run(ctx, {"tron_version": canon_v})
    ok("matching stamp: L18 passes", _l18(results).ok)


def t_drift_fails():
    ctx = Ctx(ROOT)
    _, results = lint.run(ctx, {"tron_version": "0.0.0-not-canon"})
    r = _l18(results)
    ok("drift: L18 fails", not r.ok)
    ok("drift: names both versions", "0.0.0-not-canon" in r.detail and ctx.load_version() in r.detail)


def t_unstamped_fails():
    ctx = Ctx(ROOT)
    _, results = lint.run(ctx, {"agents": []})   # a project.yaml with no tron_version key
    r = _l18(results)
    ok("unstamped: L18 fails", not r.ok)
    ok("unstamped: names re-seed", "re-seed" in r.detail)


def _instance(version, project_tron_version):
    d = tempfile.mkdtemp(prefix="tron-m06-")
    if version is not None:
        with open(os.path.join(d, "VERSION"), "w") as fh:
            fh.write(version)
    if project_tron_version is not None:
        with open(os.path.join(d, "project.yaml"), "w") as fh:
            fh.write(f"tron_version: {project_tron_version}\n")
    return d


def t_start_refuses_on_drift():
    d = _instance("0.4.2-dev", "0.3.0")
    try:
        rc = engine_cli.cmd_start(Ctx(d))
        ok("start: refuses on drift (nonzero exit)", rc == 4)
        ok("start: no manifest written on refusal", not os.path.exists(os.path.join(d, "manifest.yaml")))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_start_refuses_on_missing_stamp():
    d = _instance("0.4.2-dev", None)
    try:
        rc = engine_cli.cmd_start(Ctx(d))
        ok("start: refuses on missing stamp (pre-M-06 instance)", rc == 4)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    for t in (t_canon_self_lint_skips_without_project, t_matching_stamp_passes,
              t_drift_fails, t_unstamped_fails, t_start_refuses_on_drift,
              t_start_refuses_on_missing_stamp):
        try:
            t()
        except Exception as e:
            ok(f"{t.__name__} raised", False, repr(e))
    passed = sum(1 for _, c, _ in _results if c)
    print(f"m_06_test: {'PASS' if passed == len(_results) else 'FAIL'} ({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
