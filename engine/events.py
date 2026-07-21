#!/usr/bin/env python3
"""tron — the typed event log: one machine-readable truth per run.

Every engine decision lands as ONE JSON line in runs/<run>.events.jsonl
— a closed vocabulary (EVENTS below is the single source; EVENTS.md is
GENERATED from it), engine-emitted only, beside the verbatim prose
transcript. The transcript is for reading a run; the event log is for
MEASURING it: the SIM harness, the scale steps, and the paper's data
all aggregate these lines — never the prose (grepping prose for walls
is the exact trap the old engine died in).

Emission is fail-safe two ways, deliberately asymmetric:
- an UNKNOWN event type raises always — a typo'd emission is a defect
  in the engine and must die in selftests, never ship silent;
- an IO failure on a KNOWN event never takes a run down — observability
  is a witness, not a dependency.
"""

import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT.parent / "docs" / "EVENTS.md"

# The closed vocabulary — the single source. A new event type is added
# HERE (then `python3 events.py --write` regenerates EVENTS.md); emitting
# a type not in this table raises.
EVENTS = {
    "run_start":  "engine up on a project: flow, register size, todo count",
    "bootup":     "an operator bootup-journey step answered (step, value)",
    "recover":    "crash recovery at boot: strays killed / stale arena "
                  "removed / doing row re-stamped todo",
    "dispatch":   "a block leaves the register for an arena",
    "phase":      "a seat enters a phase of the flow",
    "gate":       "an engine gate ruled on a closing word (ok true/false)",
    "verdict":    "a verdict seat's word, recorded durably",
    "wall":       "an engine-detected wall routed (architect-first chain)",
    "page":       "the operator was paged (the reply is the dependency)",
    "answer":     "the operator answered a page",
    "probe":      "liveness: overrun / probe answered / silent through it",
    "land":       "a branch mechanically landed on the trunk",
    "trunk_check": "the suite re-ran ON the trunk after a landing",
    "block_done": "a block stamped done in the register",
    "run_done":   "the run ended (blocks delivered this run)",
}

_state = {"path": None, "lock": threading.Lock()}


def bind(path):
    """Point the log at this run's file; None unbinds (emit = no-op)."""
    _state["path"] = Path(path) if path else None


def emit(t, **fields):
    """One typed line. Unknown type = defect (raises); IO trouble on a
    known type = swallowed (a witness must not take the run down)."""
    if t not in EVENTS:
        raise ValueError(f"'{t}' is not an event type (see events.EVENTS)")
    if not _state["path"]:
        return False
    line = json.dumps({"ts": round(time.time(), 3), "t": t, **fields})
    try:
        with _state["lock"], open(_state["path"], "a") as fh:
            fh.write(line + "\n")
        return True
    except OSError:
        return False


def load(path):
    """Every event of a run, parsed. Bad lines are surfaced, not skipped
    — a half-written truth source must look broken."""
    return [json.loads(ln) for ln in
            Path(path).read_text().splitlines() if ln.strip()]


def tally(records):
    """Counts by type + the derived run measures the harness aggregates."""
    by = {}
    for r in records:
        by[r["t"]] = by.get(r["t"], 0) + 1
    return {
        "events": len(records),
        "blocks_done": by.get("block_done", 0),
        "walls": by.get("wall", 0),
        "pages": by.get("page", 0),
        "gate_bounces": sum(1 for r in records
                            if r["t"] == "gate" and not r.get("ok")),
        "rejections": sum(1 for r in records if r["t"] == "verdict"
                          and not r.get("passed")),
        "probes": by.get("probe", 0),
        "landings": by.get("land", 0),
        "duration_s": (round(records[-1]["ts"] - records[0]["ts"], 1)
                       if records else 0.0),
        "by_type": by,
    }


# --------------------------------------------------------------- the doc
def render():
    lines = [
        "# tron — the event vocabulary",
        "",
        "> GENERATED from `events.py` (the single source). Edit the EVENTS",
        "> table there, then run `python3 events.py --write`. Selftests",
        "> fail when this file is stale.",
        "",
        "Each run writes `runs/<run>.events.jsonl` — one JSON object per",
        "line: `ts` (epoch seconds), `t` (a type below), plus the fields",
        "named at the emission site. The engine is the only writer. An",
        "unknown type raises at emit time — the vocabulary is CLOSED.",
        "",
        "| Type | Meaning |",
        "|:--|:--|",
    ]
    lines += [f"| `{t}` | {d} |" for t, d in EVENTS.items()]
    lines += [
        "",
        "Analysis starts at `events.load(path)` + `events.tally(records)`",
        "— walls, pages, bounces, rejections, landings, duration; the SIM",
        "harness aggregates these per repetition. The prose transcript",
        "(`runs/<run>.log`) stays the debugging companion; it is never",
        "the measurement source.",
        "",
    ]
    return "\n".join(lines)


def doc_in_sync():
    return DOC.exists() and DOC.read_text() == render()


# -------------------------------------------------------------- selftest
def selftest():
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="events-selftest-"))
    saved = _state["path"]
    ok = []
    # unbound: a valid emit is a quiet no-op, an unknown type still raises
    bind(None)
    ok += [emit("run_start", project="p") is False]
    try:
        emit("no_such_event")
        ok += [False]
    except ValueError:
        ok += [True]
    # bound: typed lines land, parse, and tally
    f = d / "run.events.jsonl"
    bind(f)
    ok += [emit("run_start", project="ledger", todo=2),
           emit("dispatch", block="block-01"),
           emit("gate", block="block-01", phase="build", ok=False,
                fails=1, evidence="no commits"),
           emit("gate", block="block-01", phase="build", ok=True),
           emit("verdict", block="block-01", phase="review", word="REJECTED",
                passed=False, cycle=1),
           emit("verdict", block="block-01", phase="review", word="APPROVED",
                passed=True, cycle=2),
           emit("wall", block="block-01", wid="gate:build", n=1,
                route="architect", outcome="ruling"),
           emit("page", context="drill"), emit("answer", chars=12),
           emit("probe", role="worker", what="answered"),
           emit("land", block="block-01", sha="abc123"),
           emit("trunk_check", block="block-01", ok=True),
           emit("block_done", block="block-01", done=1, total=2),
           emit("run_done", delivered=1)]
    rec = load(f)
    t = tally(rec)
    ok += [len(rec) == 14,
           all(r["ts"] >= rec[0]["ts"] for r in rec),      # ordered
           rec[1]["block"] == "block-01",
           t["blocks_done"] == 1, t["walls"] == 1, t["pages"] == 1,
           t["gate_bounces"] == 1, t["rejections"] == 1,
           t["landings"] == 1, t["probes"] == 1, t["events"] == 14,
           t["by_type"]["verdict"] == 2, t["duration_s"] >= 0]
    # a torn line must be LOUD, never silently skipped
    with open(f, "a") as fh:
        fh.write('{"ts": 1, "t": "gate", TORN')
    try:
        load(f)
        ok += [False]
    except ValueError:
        ok += [True]
    # concurrent emitters: every line lands whole (the lock is real)
    f2 = d / "threads.events.jsonl"
    bind(f2)
    ts = [threading.Thread(
        target=lambda i=i: [emit("gate", block=f"b{i}", ok=True, n=j)
                            for j in range(50)]) for i in range(4)]
    [x.start() for x in ts]
    [x.join() for x in ts]
    ok += [len(load(f2)) == 200,
           tally(load(f2))["by_type"]["gate"] == 200]
    # the generated doc: in sync, names every type
    ok += [doc_in_sync(), all(f"`{t}`" in render() for t in EVENTS)]
    # emission completeness, both directions: every vocabulary type has a
    # real engine call site (a type nobody emits is a hole in the truth
    # source), and every literal call site uses the vocabulary
    import re
    sites = [m for p in ROOT.glob("*.py") if p.name != "events.py"
             for m in re.findall(r'emit\(\s*"([a-z_]+)"', p.read_text())]
    ok += [set(sites) == set(EVENTS),
           all(s in EVENTS for s in sites)]
    bind(saved)
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--write" in sys.argv:
        DOC.write_text(render())
        print(f"wrote {DOC}")
    else:
        print("doc in sync" if doc_in_sync()
              else "DOC STALE — run: python3 events.py --write")
        sys.exit(0 if doc_in_sync() else 1)
