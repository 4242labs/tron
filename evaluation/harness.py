#!/usr/bin/env python3
"""tron-reborn — the SIM harness: run one SIM many times, measure it.

A PROJECT template (sims/templates/project-NN/ — plain files, no git;
01 smallest, 03 largest) is seeded into a FRESH git project per SIM; the
real engine runs it end to end; the SIM's typed event log + prose
transcript are collected under sims/<batch>/sim-NN/ and aggregated into
ONE stats.md — the measurement source for scale steps, ablations, and
the paper's runs.

The harness drives, it never reaches into the engine: each SIM is the
stock `python3 tron.py` on a stock project. Aggregation reads ONLY
runs/<run>.events.jsonl (events.tally) — never the prose. TRON_QUIET=1
is set for the children so batch narration stays off Telegram; PAGES ARE
NEVER QUIETED — a walled SIM still reaches the operator's phone, and the
harness waits like any terminal would.

    python3 harness.py project-01 3          # 3 SIMs of PROJECT-01
    python3 harness.py project-01 3 --timeout 900  # per-SIM wall-clock cap
    python3 harness.py project-01 3 --parallel 4   # seed the engine flow
                                             #   with [limits]
                                             #   max_parallel = 4
    python3 harness.py project-01 3 --ablate truth_gate  # EXPERIMENT ARM:
                                             #   run the engine with one
                                             #   invariant disabled
"""

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine modules live at repo root
import events
from gate import git

ROOT = Path(__file__).resolve().parent   # evaluation/
RUNS = ROOT / "runs"                      # runtime output (gitignored)
SIMS = ROOT / "sims"                      # runtime output (gitignored)
TEMPLATES = ROOT / "templates"            # the SIM scaffold (tracked)
ENGINE = [sys.executable, str(ROOT.parent / "tron.py")]  # engine at repo root; selftests substitute a fake
TIMEOUT_S = 45 * 60                      # per-SIM wall-clock cap


def seed(template, dest, parallel=None):
    """A fresh project from the template: copied, git-init'd, committed.
    The template stays plain files — every SIM starts from the same sha-
    less truth, so repetitions are comparable. With `parallel`, the
    project gets its OWN workflow.toml (the proven override mechanism):
    the engine's current flow with only the max_parallel line changed —
    the same lint bar applies at boot."""
    shutil.copytree(template, dest)
    if parallel is not None:
        flow, n = re.subn(r"(?m)^max_parallel = \d+",
                          f"max_parallel = {parallel}",
                          (ROOT / "workflow.toml").read_text())
        if n != 1:
            sys.exit("engine workflow.toml has no single max_parallel line")
        (dest / "workflow.toml").write_text(flow)
    git(dest, "init", "-qb", "main")
    git(dest, "config", "user.email", "sim@tron-reborn")
    git(dest, "config", "user.name", "sim-seed")
    git(dest, "add", ".")
    git(dest, "commit", "-qm", "seed: sim template")
    return dest


def run_once(project, timeout_s, ablate=None):
    """One engine run on the project. Returns (exit, new run stamps).
    A SIM that overruns is killed as a whole process group (the engine's
    seats die with it) and reported as 'timeout' — never hung forever."""
    before = {p.name for p in RUNS.glob("run-*")} if RUNS.exists() else set()
    env = {**os.environ, "TRON_QUIET": "1"}
    if ablate:
        env["TRON_ABLATE"] = ablate    # EXPERIMENT ARM — engine validates
    proc = subprocess.Popen(ENGINE, cwd=ROOT, env=env, text=True,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        proc.communicate(input=f"{project}\n", timeout=timeout_s)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()
        code = "timeout"
    stamps = sorted({p.name.split(".")[0] for p in RUNS.glob("run-*")
                     if p.name not in before})
    return code, stamps


def collect(sim_dir, stamps):
    """The SIM's evidence, moved next to its verdict: every runs/ artifact
    of the SIM's stamps (events, transcript, manifest, report, flow)."""
    sim_dir.mkdir(parents=True, exist_ok=True)
    for s in stamps:
        for f in RUNS.glob(f"{s}*"):
            shutil.copy(f, sim_dir / f.name)
    ev = sorted(sim_dir.glob("*.events.jsonl"))
    return ev[-1] if ev else None


def tally_sim(sim, code, evfile):
    row = {"sim": sim, "exit": code, "events": 0, "blocks_done": 0,
           "walls": 0, "pages": 0, "gate_bounces": 0, "rejections": 0,
           "probes": 0, "landings": 0, "duration_s": 0.0, "todo": None}
    if evfile and evfile.exists():
        rec = events.load(evfile)
        row.update({k: v for k, v in events.tally(rec).items()
                    if k in row})
        row["todo"] = next((r.get("todo") for r in rec
                            if r["t"] == "run_start"), None)
    row["clean"] = (code == 0 and row["walls"] == 0 and row["pages"] == 0
                    and row["todo"] is not None
                    and row["blocks_done"] == row["todo"])
    return row


COLS = ("sim", "exit", "blocks_done", "walls", "pages", "gate_bounces",
        "rejections", "probes", "duration_s", "clean")


def stats_render(name, sims, rows):
    clean = sum(r["clean"] for r in rows)
    lines = [
        f"# SIM batch — {name}",
        "",
        "> GENERATED by harness.py from the SIMs' typed event logs",
        "> (events.tally) — the prose transcripts beside each SIM are the",
        "> debugging companion, never the measurement source.",
        "",
        f"**{clean}/{sims} clean** (clean = exit 0, zero walls, zero pages,",
        "every register block done).",
        "",
        "| " + " | ".join(COLS) + " |",
        "|" + "|".join([":--"] * len(COLS)) + "|",
    ]
    lines += ["| " + " | ".join(str(r[c]) for c in COLS) + " |"
              for r in rows]
    return "\n".join(lines) + "\n"


def batch(name, sims, timeout_s=TIMEOUT_S, parallel=None, ablate=None):
    template = TEMPLATES / name
    if not template.is_dir():
        sys.exit(f"no template sims/templates/{name}")
    tag = (f"-p{parallel}" if parallel is not None else "") + \
          (f"-a-{ablate.replace(',', '+')}" if ablate else "")
    bdir = SIMS / f"{time.strftime('%y%m%d-%H%M%S')}-{name}-x{sims}{tag}"
    work = bdir / "projects"
    rows = []
    print(f"[HARNESS] batch {bdir.name}: {sims} SIM(s), "
          f"cap {timeout_s}s each", flush=True)
    for i in range(1, sims + 1):
        project = seed(template, work / f"sim-{i:02d}", parallel)
        t0 = time.time()
        code, stamps = run_once(project, timeout_s, ablate)
        evfile = collect(bdir / f"sim-{i:02d}", stamps)
        row = tally_sim(i, code, evfile)
        rows.append(row)
        print(f"[HARNESS] SIM-{i:02d}: exit={code} "
              f"blocks={row['blocks_done']}/{row['todo']} "
              f"walls={row['walls']} pages={row['pages']} "
              f"{'CLEAN' if row['clean'] else 'NOT CLEAN'} "
              f"({round(time.time() - t0)}s)", flush=True)
    (bdir / "stats.md").write_text(stats_render(bdir.name, sims, rows))
    print(f"[HARNESS] {sum(r['clean'] for r in rows)}/{sims} clean — "
          f"{bdir / 'stats.md'}", flush=True)
    return bdir, rows


# -------------------------------------------------------------- selftest
def selftest():
    import json
    import tempfile
    global RUNS, SIMS, TEMPLATES, ENGINE, ROOT
    saved = (RUNS, SIMS, TEMPLATES, ENGINE, ROOT)
    d = Path(tempfile.mkdtemp(prefix="harness-selftest-"))
    ROOT, RUNS, SIMS = d, d / "runs", d / "sims"
    TEMPLATES = SIMS / "templates"
    RUNS.mkdir()
    (TEMPLATES / "t1" / "blocks").mkdir(parents=True)
    (TEMPLATES / "t1" / "context.md").write_text("ctx")
    (TEMPLATES / "t1" / "pipeline.md").write_text(
        "| id | block | depends on | status | branch |\n"
        "|:--|:--|:--|:--|:--|\n| 01 | block-01 | — | todo | — |\n")
    (TEMPLATES / "t1" / "blocks" / "block-01.md").write_text("# b\ntask")
    (d / "workflow.toml").write_text("[limits]\nmax_parallel = 2\n")

    # the fake engine: reads the project path from stdin exactly like the
    # real one, drops a synthetic typed run, exits clean
    eng = d / "fake-engine.py"
    eng.write_text(f"""#!/usr/bin/env python3
import json, sys, time, pathlib
p = sys.stdin.readline().strip()
assert pathlib.Path(p, "pipeline.md").exists()
n = len(list(pathlib.Path("{RUNS}").glob("run-*.events.jsonl")))
f = pathlib.Path("{RUNS}") / f"run-fake-{{n:02d}}.events.jsonl"
ts = time.time()
rows = [dict(ts=ts, t="run_start", project="t1", todo=1),
        dict(ts=ts + 1, t="dispatch", block="block-01"),
        dict(ts=ts + 2, t="gate", block="block-01", ok=False, fails=1),
        dict(ts=ts + 3, t="gate", block="block-01", ok=True),
        dict(ts=ts + 4, t="land", block="block-01", sha="abc"),
        dict(ts=ts + 5, t="block_done", block="block-01", done=1, total=1),
        dict(ts=ts + 6, t="run_done", delivered=1)]
f.write_text("".join(json.dumps(r) + "\\n" for r in rows))
(pathlib.Path("{RUNS}") / f"run-fake-{{n:02d}}.log").write_text("prose")
""")
    ENGINE = [sys.executable, str(eng)]
    bdir, rows = batch("t1", 2, timeout_s=30)
    seeded = bdir / "projects" / "sim-01"
    stats = (bdir / "stats.md").read_text()
    ok = [
        len(rows) == 2,
        all(r["clean"] for r in rows),                # exit 0, done == todo
        rows[0]["gate_bounces"] == 1,                 # tallied from events
        rows[0]["blocks_done"] == 1 and rows[0]["todo"] == 1,
        # each SIM seeded fresh: its own git repo, template content, commit
        git(seeded, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        == "main",
        "seed: sim template" in git(seeded, "log", "-1",
                                    "--format=%s").stdout,
        (bdir / "projects" / "sim-02" / "blocks" / "block-01.md").exists(),
        # evidence collected beside the verdict; measured from events only
        (bdir / "sim-01").glob("*.events.jsonl") is not None,
        len(list((bdir / "sim-02").glob("*.log"))) == 1,
        "2/2 clean" in stats,
        stats.count("| 1 |") >= 1 and "GENERATED by harness.py" in stats,
    ]
    # --parallel seeds a project-owned flow: only the cap line changes,
    # the engine's own file stays untouched, no override -> no flow file
    par = seed(TEMPLATES / "t1", d / "seed-par", parallel=4)
    ok += [
        "max_parallel = 4" in (par / "workflow.toml").read_text(),
        "max_parallel = 2" in (d / "workflow.toml").read_text(),
        not (bdir / "projects" / "sim-01" / "workflow.toml").exists(),
        "-p4" in batch("t1", 1, timeout_s=30, parallel=4)[0].name,
    ]
    # --ablate reaches the child engine as TRON_ABLATE and tags the batch
    echo = d / "echo-env.py"
    echo.write_text(f"""#!/usr/bin/env python3
import os, sys
sys.stdin.readline()
(__import__('pathlib').Path("{RUNS}") / "run-abl.events.jsonl").write_text(
    '{{"ts": 1.0, "t": "run_start", "todo": 0, "ablate": "'
    + os.environ.get("TRON_ABLATE", "") + '"}}\\n')
""")
    ENGINE = [sys.executable, str(echo)]
    bdir3, _ = batch("t1", 1, timeout_s=30, ablate="truth_gate")
    seen = next((bdir3 / "sim-01").glob("*.events.jsonl")).read_text()
    ok += ["-a-truth_gate" in bdir3.name, '"truth_gate"' in seen]
    # a hanging engine is killed as a group and reported, never waited out
    hang = d / "hang.py"
    hang.write_text("import sys, time\nsys.stdin.readline()\n"
                    "time.sleep(60)\n")
    ENGINE = [sys.executable, str(hang)]
    t0 = time.time()
    bdir2, rows2 = batch("t1", 1, timeout_s=2)
    ok += [rows2[0]["exit"] == "timeout",
           not rows2[0]["clean"],
           time.time() - t0 < 15,
           "0/1 clean" in (bdir2 / "stats.md").read_text()]
    # the LIVE templates carry the BINDING names: the three canonical
    # project-01/02/03 (small -> large) are always present; alongside them the
    # scale rung (project-04) and the causal experiment fixtures (exp-*) are
    # legitimate additions — every template still follows the naming convention.
    live = sorted(p.name for p in (saved[2]).iterdir() if p.is_dir())
    ok += [{"project-01", "project-02", "project-03"}.issubset(live),
           all(n.startswith(("project-", "exp-")) for n in live)]
    ROOT, RUNS, SIMS, TEMPLATES, ENGINE = (saved[4], saved[0], saved[1],
                                           saved[2], saved[3])
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif len(sys.argv) >= 2:
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        cap = (int(sys.argv[sys.argv.index("--timeout") + 1])
               if "--timeout" in sys.argv else TIMEOUT_S)
        par = (int(sys.argv[sys.argv.index("--parallel") + 1])
               if "--parallel" in sys.argv else None)
        abl = (sys.argv[sys.argv.index("--ablate") + 1]
               if "--ablate" in sys.argv else None)
        batch(sys.argv[1], n, cap, par, abl)
    else:
        print(__doc__)
