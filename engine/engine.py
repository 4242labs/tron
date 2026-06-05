#!/usr/bin/env python3
"""engine — the TRON CLI the console and cron drive (B3, ADR-002).

Entry points exposed as a callable the front (B7) builds on:
  start --max N [--dry]   cold start: load pipeline, spawn architect + first block, install cron
  tick                    one bounded sweep+advance+persist (cron / console heartbeat)
  msg "<text>"            queue an operator line and run a tick (immediate, atomic)
  stop [--force]          guard unfinished work, release the fleet, end the session
  recover                 reattach: rebuild live workers from ~/.claude/jobs
  validate [--project P]  blueprint-lint (L1-L13); nonzero exit on any failure
  doctor                  validate + environment checks

Thin by design: all flow lives here in Python (watch-item R-1); bash only does
cron/TG/spawn glue. Run from anywhere — this file puts its own dir on sys.path.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import util            # noqa: E402
import lint            # noqa: E402
from ctx import Ctx    # noqa: E402


def _tron_dir():
    return os.environ.get("TRON_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def cmd_validate(ctx):
    project = None
    pf = _arg("--project")
    if pf:
        project = util.load_yaml(pf)
    ok, results = lint.run(ctx, project)
    print("blueprint-lint:")
    for r in results:
        print(r)
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


def cmd_doctor(ctx):
    import shutil
    print("doctor — environment:")
    for tool in ("claude", "jq", "python3"):
        print(f"  [{'PASS' if shutil.which(tool) else 'FAIL'}] {tool} on PATH")
    try:
        import yaml  # noqa: F401
        print("  [PASS] pyyaml importable")
    except ImportError:
        print("  [FAIL] pyyaml importable")
    rc = cmd_validate(ctx)
    return rc


def cmd_start(ctx):
    from fsm import Engine
    if not os.path.exists(ctx.state):
        tpl = os.path.join(ctx.dir, "templates", "workflow-state.yaml")
        if os.path.exists(tpl):
            util.atomic_write(ctx.state, open(tpl).read())
    max_c = _arg("--max")
    if max_c is None:
        print("start: --max <N> required (max_concurrent_engineers; no default)")
        return 2
    eng = Engine(ctx)
    eng.start(int(max_c))
    # install cron heartbeat (idempotent); skipped in dry runs
    if not os.environ.get("TRON_DRY"):
        ci = os.path.join(ctx.scripts_dir, "cron-install.sh")
        if os.path.exists(ci):
            os.system(f"bash {ci} >/dev/null 2>&1 || true")
    return 0


def cmd_tick(ctx):
    from fsm import Engine
    Engine(ctx).tick()
    return 0


def cmd_msg(ctx):
    from fsm import Engine
    text = sys.argv[2] if len(sys.argv) > 2 else ""
    util.append_jsonl(ctx.operator_inbox,
                      {"text": text, "sender": {"kind": "operator"}})
    Engine(ctx).tick()
    return 0


def cmd_stop(ctx):
    from fsm import Engine
    ok, detail = Engine(ctx).stop(force="--force" in sys.argv)
    print(detail)
    return 0 if ok else 3


def cmd_recover(ctx):
    from fsm import Engine
    alive, purged = Engine(ctx).recover()
    print(f"recovered={alive} purged={purged}")
    return 0


COMMANDS = {
    "start": cmd_start, "tick": cmd_tick, "msg": cmd_msg, "stop": cmd_stop,
    "recover": cmd_recover, "validate": cmd_validate, "doctor": cmd_doctor,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: engine.py <{'|'.join(COMMANDS)}> [opts]")
        return 2
    ctx = Ctx(_tron_dir())
    return COMMANDS[sys.argv[1]](ctx)


if __name__ == "__main__":
    sys.exit(main())
