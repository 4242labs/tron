"""reader — parse the project's canon pipeline + block files (read-only).

TRON owns no pipeline. The 42labs canon does: a git-tracked living doc
(`pipeline.md`) plus one file per work unit (`blocks/<id>.md`), written by agents
via PR. This module is the deterministic reader over that canon (NEVER an LLM):

  parse_pipeline(path)   the living doc: ## sections, ### Phase headers, the
                         `ID | Task | Status | Notes` tables, emoji status, and
                         the block-file ref (Block `blocks/<id>.md`) out of Notes.
  parse_block(path)      one block file's fixed `**Key:** value` headers
                         (Status, Depends on, Reviewer class, Merge approval, Deploy, Phase),
                         plus the two OPTIONAL headers roles.yaml's selector reads
                         (ADR-0002 D4/T2): Role, Tags — absent means default binding match.
  load(pipeline, blocks) the merged dispatch view: each pipeline row enriched
                         with its block file's headers. Dispatch truth is the
                         block file (canon §3); the living doc gives order only.

Format contract (canon `new-project-template/templates/meta/pipeline.md`):
phases are `### Phase N: <Title>`; every table is `ID | Task | Status | Notes`;
the Status cell is exactly one emoji; a row with a block file names it in Notes.
"""
import os
import re

# Emoji status -> normalized status. Only `to-do` is dispatchable (gated on deps).
EMOJI = {
    "📋": "to-do",
    "🔄": "in-progress",
    "✅": "done",
    "📌": "deferred",
    "🔧": "debt",
    "❌": "cut",
    "📦": "folded",
    "✂️": "split",
}
DISPATCHABLE_STATUS = "to-do"

_BLOCK_REF = re.compile(r"blocks/([^`\s)]+\.md)")
_KEY = re.compile(r"^\*\*([^:*]+):\*\*\s*(.*?)\s*$")


def normalize_status(cell):
    """Map a Status cell (an emoji, optionally with trailing prose) to a status."""
    for glyph, name in EMOJI.items():
        if glyph in cell:
            return name
    return "unknown"


def _split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(cells):
    return all(set(c) <= set("-: ") for c in cells)


def parse_pipeline(path):
    """Parse the living doc into ordered rows. Returns [] if the file is absent.

    Each row: {section, phase, id, task, status, notes, block_file, order}.
    `order` is the row's global appearance index (the living doc *is* the order).
    """
    if not os.path.isfile(path):
        return []
    rows, order = [], 0
    section, phase = None, None
    header = None
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("## "):
                section, phase, header = s[3:].strip(), None, None
                continue
            m = re.match(r"^###\s*Phase\s+([^:]+):\s*(.*)$", s)
            if m:
                phase = f"Phase {m.group(1).strip()}: {m.group(2).strip()}".rstrip(": ")
                header = None
                continue
            if "|" not in line:
                continue
            cells = _split_row(line)
            if header is None:
                header = [c.lower() for c in cells]
                continue
            if _is_separator(cells):
                continue
            cell = dict(zip(header, cells))
            bid = cell.get("id", "")
            if not bid or bid.startswith("<"):
                continue
            status_cell = cell.get("status", "")
            notes = cell.get("notes", "")
            ref = _BLOCK_REF.search(notes) or _BLOCK_REF.search(status_cell)
            order += 1
            rows.append({
                "section": section,
                "phase": phase,
                "id": bid,
                # column 2 is "Task" in most tables, "Issue" in Technical Debt
                "task": cell.get("task") or cell.get("issue") or "",
                "status": normalize_status(status_cell),
                "notes": notes,
                "block_file": ref.group(1) if ref else None,
                "order": order,
            })
    return rows


def parse_block(path):
    """Parse one block file's fixed headers. Returns {} if absent.

    Keys: id, title, phase, status, depends_on (list), reviewer_class, merge_approval, deploy,
    role_hdr, tags (list). Header lines are `**Key:** value`; a trailing `← comment`
    annotation is dropped. `Role:`/`Tags:` (ADR-0002 D4/T2) are OPTIONAL — absent on
    (nearly) every block, they feed roles.yaml's deterministic selector (block_tag
    matches, or an explicit role override); their absence means "default binding
    match" (today's behavior, unchanged)."""
    if not os.path.isfile(path):
        return {}
    out = {"id": None, "title": None, "phase": None, "status": "unknown",
           "depends_on": [], "reviewer_class": None, "merge_approval": "auto", "deploy": None,
           "role_hdr": None, "tags": []}
    with open(path) as fh:
        in_headers = True
        for line in fh:
            s = line.rstrip()
            if s.startswith("# "):
                m = re.match(r"^#\s+Block\s+([^:]+):\s*(.*)$", s)
                if m:
                    out["id"] = m.group(1).strip()
                    out["title"] = m.group(2).strip()
                continue
            if s.startswith("---") or s.startswith("## "):
                in_headers = False
                continue
            if not in_headers:
                continue
            m = _KEY.match(s)
            if not m:
                continue
            key, val = m.group(1).strip().lower(), m.group(2)
            val = val.split("←")[0].strip()           # drop template annotation
            if key == "phase":
                out["phase"] = val
            elif key == "status":
                out["status"] = normalize_status(val)
            elif key in ("depends on", "depends-on"):
                out["depends_on"] = _id_list(val)
            elif key == "reviewer class":
                out["reviewer_class"] = _none_or(val)
            elif key == "merge approval":
                out["merge_approval"] = (val or "auto").lower()
            elif key == "deploy":
                out["deploy"] = _none_or(val)
            elif key == "role":
                out["role_hdr"] = _none_or(val)
            elif key == "tags":
                out["tags"] = _id_list(val)
    return out


def _id_list(val):
    if not val or val.lower() in ("none", "n/a", "-"):
        return []
    return [p.strip() for p in re.split(r"[,;]", val) if p.strip() and not p.strip().startswith("<")]


def _none_or(val):
    if not val or val.lower() in ("none", "n/a", "-"):
        return None
    return val


def load_blocks(blocks_dir):
    """Parse every block file under blocks_dir (skips the template and any archive/).
    Returns {block_id: parsed_block}. Filenames are also keyed for ref resolution."""
    out, by_file = {}, {}
    if not os.path.isdir(blocks_dir):
        return out, by_file
    for name in sorted(os.listdir(blocks_dir)):
        if not name.endswith(".md") or name == "block-template.md":
            continue
        b = parse_block(os.path.join(blocks_dir, name))
        by_file[name] = b
        if b.get("id"):
            out[b["id"]] = b
    return out, by_file


def load_archived_blocks(blocks_dir):
    """Parse block files under `blocks_dir/archive/` — the blocks a worker's
    session-end close-out git-mv'd out of the live dir. Returns {id: block}.

    These are deliberately OUT of `load_blocks` (they must never re-enter the
    dispatch view), but their STATUS must still resolve: a block is archived
    only AFTER it lands ✅ done, and any block that `Depends on` it reads that
    dep's status through `load` below. An unreadable archived dep resolves to
    None, which is neither `done` (so the dependent never becomes
    dispatchable) nor an in-scope wait (so `core/session.py` flags it a stuck
    gap) — the confirmed T2-01-05 root: block 01-03 wedged 'to-do, depends_on
    01-02, dep_statuses {01-02: None}' the instant 01-02 was archived."""
    out = {}
    archive_dir = os.path.join(blocks_dir, "archive")
    if not os.path.isdir(archive_dir):
        return out
    for name in sorted(os.listdir(archive_dir)):
        if not name.endswith(".md") or name == "block-template.md":
            continue
        b = parse_block(os.path.join(archive_dir, name))
        if b.get("id"):
            out[b["id"]] = b
    return out


def load(pipeline_path, blocks_dir):
    """The merged dispatch view: living-doc order + block-file truth.

    Returns a list of rows (living-doc order) each enriched with its block file's
    headers when present. Block file is authoritative for status/deps/gates (§3);
    the living-doc row supplies order, section, and task text. A block whose file
    has been archived at close is resolved from the archive for STATUS/deps only
    (`archived=True`, `has_block_file=False`) so dependents still read it as done
    while it stays permanently out of the dispatch view.
    """
    rows = parse_pipeline(pipeline_path)
    by_id, by_file = load_blocks(blocks_dir)
    archived = load_archived_blocks(blocks_dir)
    view = []
    for r in rows:
        b = None
        if r.get("block_file") and r["block_file"] in by_file:
            b = by_file[r["block_file"]]
        elif r["id"] in by_id:
            b = by_id[r["id"]]
        row = dict(r)
        if b:
            row["status"] = b.get("status", row["status"])     # block file wins
            row["depends_on"] = b.get("depends_on", [])
            row["reviewer_class"] = b.get("reviewer_class")
            row["merge_approval"] = b.get("merge_approval", "auto")
            row["deploy"] = b.get("deploy")
            row["role_hdr"] = b.get("role_hdr")
            row["tags"] = b.get("tags") or []
            row["has_block_file"] = True
            row["archived"] = False
        elif r["id"] in archived:
            a = archived[r["id"]]
            # Archived: status/deps resolve from the archived file (so a
            # dependent reads this dep as done), but has_block_file stays
            # False — `dispatchable()` never re-picks it and `session.py`
            # skips it, exactly as for any row with no live block file.
            row["status"] = a.get("status", row["status"])
            row["depends_on"] = a.get("depends_on", [])
            row["reviewer_class"] = a.get("reviewer_class")
            row["merge_approval"] = a.get("merge_approval", "auto")
            row["deploy"] = a.get("deploy")
            row["role_hdr"] = a.get("role_hdr")
            row["tags"] = a.get("tags") or []
            row["has_block_file"] = False
            row["archived"] = True
        else:
            row["depends_on"] = []
            row["reviewer_class"] = None
            row["merge_approval"] = "auto"
            row["deploy"] = None
            row["role_hdr"] = None
            row["tags"] = []
            row["has_block_file"] = False
            row["archived"] = False
        view.append(row)
    return view


def status_index(view):
    """block_id -> normalized status, for dependency resolution."""
    return {r["id"]: r["status"] for r in view}


def is_adhoc(row):
    return (row.get("section") or "").lower().startswith("ad-hoc") \
        or (row.get("section") or "").lower().startswith("adhoc")


def dispatchable(row, idx):
    """Canon §C gate: block file present, status to-do, every dep ✅ on trunk."""
    if not row.get("has_block_file"):
        return False
    if row.get("status") != DISPATCHABLE_STATUS:
        return False
    return all(idx.get(dep) == "done" for dep in row.get("depends_on", []))
