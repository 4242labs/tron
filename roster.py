#!/usr/bin/env python3
"""tron-reborn — the roster: session manifesto + pro-active user report.

One live, engine-owned state: every agent session (role, session id, what
it is taking care of) and every block's journey. Every mutation — and
every transcript event, via transcript.SAY_HOOK — deterministically
re-renders two files next to the run transcript:

  <run>.manifest.md  the session MANIFESTO: who is who, doing what
  <run>.report.md    the user report: pipeline journey + live sessions +
                     the latest events, readable at any moment mid-run

No LLM writes here; both files are the engine's own testimony. (A later
iteration adds on-demand, LLM-written reports on top.)
"""

import threading
import time

_LOCK = threading.RLock()
_AGENTS = []      # {"agent": Agent, "care": str, "since": str}
_BLOCKS = {}      # name -> {"phase": str, "at": str}
_EVENTS = []      # newest-last "[hh:mm:ss] topic: text", tail kept
_FILES = {}       # {"manifest": Path, "report": Path} once bound
EVENT_TAIL = 12


def _now():
    return time.strftime("%H:%M:%S")


def bind(manifest, report):
    """Engine calls once per run; from here on every mutation renders."""
    with _LOCK:
        _AGENTS.clear(), _BLOCKS.clear(), _EVENTS.clear()
        _FILES.update(manifest=manifest, report=report)
        _render()


def enroll(agent, care):
    """A session exists: register who it is and what it takes care of."""
    with _LOCK:
        _AGENTS.append({"agent": agent, "care": care, "since": _now()})
        _render()


def block(name, phase):
    """The block's journey: dispatched/building/review/merge window/landed."""
    with _LOCK:
        _BLOCKS[name] = {"phase": phase, "at": _now()}
        _render()


def event(line):
    """Transcript hook: every engine event refreshes the report tail."""
    with _LOCK:
        _EVENTS.append(f"[{_now()}] {line}")
        del _EVENTS[:-EVENT_TAIL]
        _render()


def _manifest():
    lines = ["# Session manifesto", "",
             "Engine-owned registry: every agent session this run.", "",
             "| role | session id | taking care of | since |",
             "|:--|:--|:--|:--|"]
    for a in _AGENTS:
        lines.append(f"| {a['agent'].role} "
                     f"| {a['agent'].session or '(booting)'} "
                     f"| {a['care']} | {a['since']} |")
    return "\n".join(lines) + "\n"


def _report():
    lines = [f"# TRON run report — {_now()}", "",
             "Deterministic, engine-written; refreshed on every event.", "",
             "## Block journey", "",
             "| block | phase | at |", "|:--|:--|:--|"]
    for name, b in _BLOCKS.items():
        lines.append(f"| {name} | {b['phase']} | {b['at']} |")
    lines += ["", "## Sessions", ""]
    for a in _AGENTS:
        lines.append(f"- {a['agent'].role} "
                     f"`{a['agent'].session or '(booting)'}` — {a['care']} "
                     f"(since {a['since']})")
    lines += ["", f"## Last {EVENT_TAIL} events", ""]
    lines += [f"- {e}" for e in _EVENTS] or ["(none yet)"]
    return "\n".join(lines) + "\n"


def _render():
    if _FILES:
        _FILES["manifest"].write_text(_manifest())
        _FILES["report"].write_text(_report())


# -------------------------------------------------------------- selftest
def selftest():
    import sys
    import tempfile
    from pathlib import Path

    class Fake:
        def __init__(self, role, session=None):
            self.role, self.session = role, session

    d = Path(tempfile.mkdtemp(prefix="roster-selftest-"))
    bind(d / "m.md", d / "r.md")
    ok = [(d / "m.md").exists(), (d / "r.md").exists()]
    w = Fake("worker")
    enroll(w, "block-03 (build + merge)")
    enroll(Fake("architect", "sess-arch-1"), "project rulings")
    ok += ["(booting)" in (d / "m.md").read_text(),
           "sess-arch-1" in (d / "m.md").read_text(),
           "block-03 (build + merge)" in (d / "m.md").read_text()]
    w.session = "sess-w-9"                     # live id appears on next render
    block("block-03", "building")
    block("block-03", "merge window")
    event("block-03|merge: window OPEN")
    m, r = (d / "m.md").read_text(), (d / "r.md").read_text()
    ok += ["sess-w-9" in m, "sess-w-9" in r,
           "| block-03 | merge window |" in r,   # latest phase wins
           "window OPEN" in r]
    for i in range(20):
        event(f"e{i}")
    r = (d / "r.md").read_text()
    ok += ["e19" in r, "e7" not in r,           # tail bounded
           r.count("- [") == EVENT_TAIL]
    bind(d / "m.md", d / "r.md")                # rebind resets a run
    ok += ["sess-w-9" not in (d / "m.md").read_text()]
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    selftest()
