#!/usr/bin/env python3
"""tron-reborn — the pipeline: the permanent block register.

`pipeline.md` in the project root is orchestration TRUTH: every block with
its id, dependencies, status (todo → doing → done; done = the engine has
landed the branch on main) and delivery branch.
Only the ENGINE ever writes it — a status is the engine's verdict (gate +
challenge + review), never an agent's claim — and the trunk stays read-only
to agents. The engine reads it at boot and dispatches the first block whose
dependencies are all done.
"""

import sys
import time

from gate import git

HEADER = ("# Pipeline — permanent block register",
          "",
          "Engine-owned: statuses are stamped by the engine's own verdict.",
          "")


def path_of(repo):
    return repo / "pipeline.md"


def load(repo):
    rows = []
    for line in path_of(repo).read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if (len(cells) >= 5 and cells[0] and cells[0] != "id"
                and not set(cells[0]) <= set(":- ")):
            rows.append({
                "id": cells[0], "block": cells[1],
                "deps": ([] if cells[2] in ("—", "-", "") else
                         [d.strip() for d in cells[2].split(",")]),
                "status": cells[3],
                "branch": cells[4] if cells[4] not in ("—", "-", "") else None,
            })
    return rows


def render(rows):
    lines = list(HEADER)
    lines += ["| id | block | depends on | status | branch |",
              "|:--|:--|:--|:--|:--|"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['block']} "
                     f"| {', '.join(r['deps']) or '—'} | {r['status']} "
                     f"| {r['branch'] or '—'} |")
    return "\n".join(lines) + "\n"


def next_dispatch(rows, scope=None):
    """First TODO row whose dependencies are all done, else None.

    'doing' rows belong to a running dispatch and are never re-issued —
    a crashed run's doing rows are re-stamped todo by boot recovery.
    `scope` (a set of ids, from the bootup journey) limits dispatch to
    in-scope rows; out-of-scope rows keep their status untouched and
    still satisfy dependencies when done."""
    done = {r["id"] for r in rows if r["status"] == "done"}
    for r in rows:
        if (r["status"] == "todo" and (scope is None or r["id"] in scope)
                and all(d in done for d in r["deps"])):
            return r
    return None


def stamp(repo, rows, block_id, status, branch=None):
    """Engine verdict -> register + commit on main. Returns the rows."""
    for r in rows:
        if r["id"] == block_id:
            r["status"] = status
            if branch:
                r["branch"] = branch
    git(repo, "checkout", "-q", "main")
    path_of(repo).write_text(render(rows))
    git(repo, "add", "pipeline.md")
    git(repo, "commit", "-qm",
        f"pipeline: {block_id} -> {status}" + (f" ({branch})" if branch else ""))
    return rows


def record_doc(repo, relpath, title, text):
    """An engine-recorded document (e.g. a seat's session log): verbatim
    content, written and committed on main by the engine — the agent
    speaks, the engine is the only writer."""
    p = repo / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# {title}\n\n{(text or '').rstrip()}\n")
    git(repo, "checkout", "-q", "main")
    git(repo, "add", relpath)
    git(repo, "commit", "-qm", f"log: {relpath}")


def record_review(repo, block, branch, cycle, verdict, text):
    """Every review verdict lands verbatim in the permanent register.

    reviews.md is engine-owned like pipeline.md: appended and committed on
    main so findings are durable, versioned history — never only chat.
    """
    p = repo / "reviews.md"
    if not p.exists():
        p.write_text("# Reviews — permanent findings register\n\n"
                     "Engine-owned: every review verdict appended verbatim; "
                     "the acceptance policy lives in policy.md.\n")
    with open(p, "a") as fh:
        fh.write(f"\n## {block} cycle {cycle} — {verdict} "
                 f"({time.strftime('%y%m%d-%H%M%S')})\n\n"
                 f"branch: {branch}\n\n{text}\n")
    git(repo, "checkout", "-q", "main")
    git(repo, "add", "reviews.md")
    git(repo, "commit", "-qm", f"review: {block} cycle {cycle} {verdict}")


# -------------------------------------------------------------- selftest
def selftest():
    import tempfile
    from pathlib import Path
    rows = [
        {"id": "01", "block": "scoping", "deps": [], "status": "done",
         "branch": None},
        {"id": "02", "block": "block-02", "deps": ["01"], "status": "todo",
         "branch": None},
        {"id": "03", "block": "block-03", "deps": ["02"], "status": "todo",
         "branch": None},
    ]
    repo = Path(tempfile.mkdtemp(prefix="pipeline-selftest-"))
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "p@selftest")
    git(repo, "config", "user.name", "p")
    path_of(repo).write_text(render(rows))
    git(repo, "add", "."); git(repo, "commit", "-qm", "seed")
    ok = [
        load(repo) == rows,                                  # round-trip
        next_dispatch(rows)["id"] == "02",                   # dep order
        next_dispatch([rows[0], dict(rows[1], status="done"),
                       rows[2]])["id"] == "03",
        next_dispatch([dict(r, status="done") for r in rows]) is None,
        # unmet dep is never dispatched
        next_dispatch([dict(rows[0], status="todo", deps=["99"])]) is None,
        # a doing row is a RUNNING dispatch — never re-issued
        next_dispatch([dict(rows[1], status="doing", deps=[])]) is None,
        # scope limits dispatch; an out-of-scope done still satisfies deps
        next_dispatch(rows, scope={"03"}) is None,
        next_dispatch([rows[0], dict(rows[1], status="done"), rows[2]],
                      scope={"03"})["id"] == "03",
    ]
    stamp(repo, load(repo), "02", "done", "feat/block-02")
    ok += [
        load(repo)[1]["status"] == "done",                   # stamped on disk
        load(repo)[1]["branch"] == "feat/block-02",
        "pipeline: 02 -> done" in git(repo, "log", "-1",
                                      "--format=%s").stdout,  # engine commit
    ]
    record_review(repo, "block-02", "feat/block-02", 1, "REJECTED",
                  "1. missing empty-case test")
    record_review(repo, "block-02", "feat/block-02", 2, "APPROVED", "clean")
    reviews = (repo / "reviews.md").read_text()
    ok += [
        "cycle 1 — REJECTED" in reviews,                    # durable verdicts
        "missing empty-case test" in reviews,
        "cycle 2 — APPROVED" in reviews,
        "review: block-02 cycle 2 APPROVED" in git(
            repo, "log", "-1", "--format=%s").stdout,        # committed on main
        git(repo, "status", "--porcelain").stdout == "",
    ]
    record_doc(repo, "logs/block-02-review.md", "block-02 review — log",
               "checked N cases; findings fixed in cycle 2")
    ok += [
        "findings fixed" in (repo / "logs/block-02-review.md").read_text(),
        "log: logs/block-02-review.md" in git(repo, "log", "-1",
                                              "--format=%s").stdout,
        git(repo, "status", "--porcelain").stdout == "",
    ]
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    selftest()
