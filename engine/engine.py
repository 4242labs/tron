#!/usr/bin/env python3
"""engine — the TRON CLI the console and WAKE daemon drive (B3, ADR-002).

Entry points exposed as a callable the front (B7) builds on:
  start --max N [--dry]   cold start: load pipeline, spawn architect + first block, start WAKE
  tick                    one bounded sweep+advance+persist (single-flight; daemon / console)
  wake                    the WAKE daemon loop (ND-08): the in-process tick scheduler
  msg "<text>"            queue an operator line and run a tick (immediate, atomic)
  stop [--force]          guard unfinished work, release the fleet, end the session
  recover                 reattach: rebuild live workers from ~/.claude/jobs
  validate [--project P]  blueprint-lint (L1-L13); nonzero exit on any failure
  doctor                  validate + environment checks
  log [filters]           query the forensic event/failure log (01-06): why did TRON fail

Thin by design: all flow lives here in Python (watch-item R-1); bash only does
TG/spawn glue. Run from anywhere — this file puts its own dir on sys.path.
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
    # Default to the instance's own project.yaml so role-consistency (L13) is checked;
    # --project overrides (e.g. linting a candidate file). Absent project -> L13 skips.
    pf = _arg("--project")
    if pf:
        project = util.load_yaml(pf)
    else:
        project = ctx.load_project() or None
    ok, results = lint.run(ctx, project)
    print("blueprint-lint:")
    for r in results:
        print(r)
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


def cmd_doctor(ctx):
    import shutil
    from jobs import RUNTIME
    print("doctor — environment:")
    # (binary, label) — label never names the host runtime in operator-facing output.
    for binary, label in ((RUNTIME, "agent runtime"), ("jq", "jq"), ("python3", "python3")):
        print(f"  [{'PASS' if shutil.which(binary) else 'FAIL'}] {label} on PATH")
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
        tpl = os.path.join(ctx.dir, "templates", "manifest.yaml")
        if os.path.exists(tpl):
            util.atomic_write(ctx.state, open(tpl).read())
    max_c = _arg("--max")
    if max_c is None:
        print("start: --max <N> required (worker_count: engineers + reviewers; no default)")
        return 2
    eng = Engine(ctx)
    # start() resets disposable runtime — refuse on a live session so a stray internal
    # invocation can't clobber it (the console guards the same way via reconnect).
    if (eng.st.data.get("session") or {}).get("started_at"):
        print("start: a session is already live — reconnect via the console, or stop it first")
        return 3
    eng.start(int(max_c))
    # Start the WAKE daemon — start owns it, so the engine never ticks before a session
    # exists. It is the only tick-source while the session is live (ND-08); skipped under
    # TRON_DRY (tests drive ticks directly) and if the bootup gateway ended the session.
    if not os.environ.get("TRON_DRY") and (eng.st.data.get("session") or {}).get("started_at"):
        import wake
        wake.spawn(ctx)
    return 0


def cmd_tick(ctx):
    import wake
    wake.locked_tick(ctx)         # single-flight: never overlaps a daemon-fired tick
    return 0


def cmd_wake(ctx):
    import wake
    wake.run(ctx)                 # blocks: the daemon loop, until the session ends
    return 0


def cmd_msg(ctx):
    import wake
    text = sys.argv[2] if len(sys.argv) > 2 else ""
    util.append_jsonl(ctx.operator_inbox,
                      {"text": text, "sender": {"kind": "operator"}})
    # Single-flight: if a daemon tick holds the lock, the line still landed on the inbox
    # and the daemon's event-wake picks it up on its next tick — never lost.
    wake.locked_tick(ctx)
    return 0


def cmd_stop(ctx):
    from fsm import Engine
    import wake
    ok, detail = Engine(ctx).stop(force="--force" in sys.argv)
    if ok:
        wake.stop(ctx)            # tear down the daemon only once the session actually ended
    print(detail)
    return 0 if ok else 3


def cmd_recover(ctx):
    from fsm import Engine
    alive, purged = Engine(ctx).recover()
    print(f"recovered={alive} purged={purged}")
    return 0


def cmd_console(ctx):
    from console import Console
    if not os.path.exists(ctx.state):
        tpl = os.path.join(ctx.dir, "templates", "manifest.yaml")
        if os.path.exists(tpl):
            util.atomic_write(ctx.state, open(tpl).read())
    Console(ctx).run()
    return 0


def cmd_log(ctx):
    """Query the structured forensic log (01-06). Defaults to failures, newest-first —
    the operator-facing answer to *why did TRON fail*.
      log [--all] [--run R] [--block B] [--class C] [--limit N] [--full]
    --all includes non-failure events; --full prints every field (else a one-line digest)."""
    import json
    import eventlog
    failures_only = "--all" not in sys.argv
    recs = eventlog.query(
        ctx, run=_arg("--run"), block=_arg("--block"), fclass=_arg("--class"),
        failures_only=failures_only, limit=_arg("--limit"))
    if "--full" in sys.argv:
        for r in recs:
            print(json.dumps(r, indent=2))
    else:
        for r in recs:
            if r.get("kind") == "failure":
                print(f"{r.get('at')}  [{r.get('fclass')}/{r.get('code')}]  "
                      f"block={r.get('block')} run={r.get('run')} tick={r.get('tick')} "
                      f"next={r.get('next')}  {r.get('cause')}")
            else:
                print(f"{r.get('at')}  {r.get('kind')}:{r.get('type')}  "
                      f"actor={r.get('actor')} block={r.get('block')} cid={r.get('cid')}")
    if not recs:
        print("(no matching records)")
    return 0


COMMANDS = {
    "start": cmd_start, "tick": cmd_tick, "wake": cmd_wake, "msg": cmd_msg,
    "stop": cmd_stop, "recover": cmd_recover, "validate": cmd_validate,
    "doctor": cmd_doctor, "console": cmd_console, "log": cmd_log,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: engine.py <{'|'.join(COMMANDS)}> [opts]")
        return 2
    ctx = Ctx(_tron_dir())
    return COMMANDS[sys.argv[1]](ctx)


if __name__ == "__main__":
    sys.exit(main())
