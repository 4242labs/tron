"""hostpipe — the pipeline I/O for both pipeline modes (contracts §7, §8).

mode: host    — the operator's own Markdown table. Parsed ONCE at session start
                into the normalized state mirror; written back ONLY on status-change
                events (done/blocked/review), never a free-form rewrite per tick.
mode: internal— TRON owns pipeline.md (gitignored). Same normalized shape.

The rails never parse free-form prose: a host doc that deviates from the accepted
shape is rejected here, and the seeder offers reformat or switch to internal.
"""
import os
import re

import util

STATUSES = {"todo", "in-progress", "blocked", "review", "done"}
COL_ALIASES = {
    "order": "order", "seq": "order", "sequence": "order", "#": "order",
    "id": "id", "spec": "id", "block": "id",
    "owner": "owner", "role": "owner",
    "status": "status", "state": "status",
    "notes": "notes", "note": "notes",
}


class PipelineError(Exception):
    pass


def _split_row(line):
    line = line.strip().strip("|")
    return [c.strip() for c in line.split("|")]


def parse(path):
    """Parse a Markdown pipeline table into the normalized pipeline. Raises on bad shape."""
    if not os.path.isfile(path):
        raise PipelineError(f"pipeline file not found: {path}")
    rows = []
    header = None
    with open(path) as fh:
        for line in fh:
            if "|" not in line:
                continue
            cells = _split_row(line)
            if header is None:
                header = [COL_ALIASES.get(c.lower()) for c in cells]
                if "id" not in header or "status" not in header:
                    raise PipelineError("table needs ID and Status columns")
                continue
            if all(set(c) <= set("-: ") for c in cells):
                continue  # separator row
            row = {}
            for col, val in zip(header, cells):
                if col:
                    row[col] = val
            if not row.get("id"):
                continue
            st = (row.get("status") or "").lower()
            if st not in STATUSES:
                raise PipelineError(f"row '{row.get('id')}' has bad status '{st}'")
            rows.append({
                "order": int(row["order"]) if row.get("order", "").isdigit() else None,
                "id": row["id"],
                "owner": row.get("owner", ""),
                "status": st,
                "notes": row.get("notes", ""),
            })
    if not rows:
        raise PipelineError("no block rows found")
    return rows


def _render_table(pipeline):
    out = ["| Order | ID | Owner | Status | Notes |",
           "|:------|:---|:------|:-------|:------|"]
    for r in sorted(pipeline, key=lambda x: (x.get("order") or 1e9)):
        out.append(f"| {r.get('order','') or ''} | {r['id']} | {r.get('owner','')} "
                   f"| {r['status']} | {r.get('notes','')} |")
    return "\n".join(out) + "\n"


def write_back(path, pipeline, title=None):
    """Rewrite the pipeline table atomically. Called only on status-change events."""
    body = _render_table(pipeline)
    if title:
        body = f"{title}\n\n{body}"
    util.atomic_write(path, body)


def write_internal(ctx, pipeline):
    write_back(ctx.pipeline_internal, pipeline,
               title="# pipeline.md — Internal pipeline (runtime; gitignored)")
