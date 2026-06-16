#!/usr/bin/env node
// Lens — build step
// Parses pipeline.md / pipeline-archive.md / backlog.md → static HTML.
// Output: dist/index.html with embedded JSON.

import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync, cpSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { marked } from "marked";

// ---------- Project (single source of truth for branding) ----------
// Set this for the project. Rendered in <title> and the page <h1>.
const PROJECT_NAME = "PROJECT";

const __dirname = dirname(fileURLToPath(import.meta.url));
const META_DIR = resolve(__dirname, "..");
const DIST_DIR = resolve(__dirname, "dist");

const SOURCES = {
  pipeline: join(META_DIR, "pipeline.md"),
  archive: join(META_DIR, "pipeline-archive.md"),
  backlog: join(META_DIR, "backlog.md"),
};

// ---------- Status normalization ----------

const STATUS_DEFS = [
  { key: "done",        emoji: "✅", label: "Done" },
  { key: "in_progress", emoji: "🔄", label: "In progress" },
  { key: "todo",        emoji: "📋", label: "To do" },
  { key: "deferred",    emoji: "📌", label: "Deferred" },
  { key: "debt",        emoji: "🔧", label: "Open debt" },
  { key: "cut",         emoji: "❌", label: "Cut / Superseded" },
  { key: "folded",      emoji: "📦", label: "Folded" },
  { key: "split",       emoji: "✂️", label: "Split" },
];

const EMOJI_TO_KEY = Object.fromEntries(STATUS_DEFS.map(s => [s.emoji, s.key]));

// Aliases — emojis that should map to canonical statuses (synonyms in the source corpus).
const STATUS_ALIASES = [
  { emoji: "⏳", key: "deferred", labelHint: "Parked" },
];

function classifyStatus(raw) {
  if (!raw) return { key: "unknown", emoji: "·", label: "Unknown", raw: "" };
  const trimmed = raw.trim();
  for (const def of STATUS_DEFS) {
    if (trimmed.startsWith(def.emoji)) {
      const tail = trimmed.slice(def.emoji.length).trim();
      return {
        key: def.key,
        emoji: def.emoji,
        label: tail ? `${def.label} — ${tail}` : def.label,
        raw: trimmed,
      };
    }
  }
  for (const alias of STATUS_ALIASES) {
    if (trimmed.startsWith(alias.emoji)) {
      const def = STATUS_DEFS.find(d => d.key === alias.key);
      const tail = trimmed.slice(alias.emoji.length).trim();
      return {
        key: alias.key,
        emoji: def.emoji,
        label: tail ? `${def.label} — ${tail}` : def.label,
        raw: trimmed,
      };
    }
  }
  return { key: "unknown", emoji: trimmed.slice(0, 2), label: trimmed, raw: trimmed };
}

// ---------- Markdown table parsing ----------

// Parses pipe-delimited markdown rows. Returns array of cell-arrays.
// Skips header + separator rows. Handles cells with embedded `|` inside `[](...)` or backticks.
function parseTableSection(lines, startIdx) {
  const out = [];
  let i = startIdx;
  // header
  if (!lines[i] || !lines[i].trim().startsWith("|")) return { rows: [], end: startIdx };
  i++; // skip header
  // separator: `| :-- | :-- ...`
  if (lines[i] && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i])) i++;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim().startsWith("|")) break;
    // smart split — respects `[]()` brackets and `` ` `` backticks
    const cells = splitPipes(line);
    if (cells.length) out.push(cells);
    i++;
  }
  return { rows: out, end: i };
}

function splitPipes(line) {
  // strip leading/trailing pipe
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  const cells = [];
  let buf = "";
  let depthBracket = 0;
  let depthParen = 0;
  let inCode = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === "`") inCode = !inCode;
    if (!inCode) {
      if (c === "[") depthBracket++;
      else if (c === "]") depthBracket = Math.max(0, depthBracket - 1);
      else if (c === "(") depthParen++;
      else if (c === ")") depthParen = Math.max(0, depthParen - 1);
    }
    if (c === "|" && depthBracket === 0 && depthParen === 0 && !inCode) {
      cells.push(buf.trim());
      buf = "";
    } else {
      buf += c;
    }
  }
  cells.push(buf.trim());
  return cells;
}

// ---------- Pipeline parser ----------
// Structure: # <Project> Pipeline → ## sections → ### Phase blocks
// Each phase: "### Phase N: Title" then optional status/blurb paras then a table.

function parsePipelineFile(content) {
  const lines = content.split("\n");
  const phases = [];
  let i = 0;
  let currentPhase = null;
  let phaseContextLines = [];

  // collect file-level header content for "Last Updated" etc.
  let fileHeader = { title: "", blurb: [] };
  while (i < lines.length && !lines[i].startsWith("### Phase")) {
    if (lines[i].startsWith("# ")) fileHeader.title = lines[i].slice(2).trim();
    i++;
  }

  while (i < lines.length) {
    const line = lines[i];
    // phase boundary
    const phaseMatch = line.match(/^###\s+Phase\s+([\d.]+):\s+(.+?)\s*$/);
    if (phaseMatch) {
      if (currentPhase) phases.push(currentPhase);
      currentPhase = {
        id: phaseMatch[1],
        title: phaseMatch[2].trim(),
        status_line: "",
        blurb: "",
        blocks: [],
      };
      phaseContextLines = [];
      i++;
      // collect any prose / status lines until we hit a table or another phase
      while (i < lines.length && !lines[i].startsWith("### Phase") && !lines[i].startsWith("## ")) {
        if (lines[i].trim().startsWith("|")) break;
        phaseContextLines.push(lines[i]);
        i++;
      }
      // synthesize status_line + blurb (cheap heuristic — first non-empty line that mentions Status, then first non-empty para after)
      const ctx = phaseContextLines.map(l => l.trim()).filter(Boolean);
      const statusIdx = ctx.findIndex(l => /\*\*Status:?\*\*/i.test(l));
      if (statusIdx >= 0) {
        currentPhase.status_line = ctx[statusIdx]
          .replace(/\*\*/g, "")
          .replace(/^Status:?\s*/i, "")
          .trim();
        // blurb = next non-empty line
        const after = ctx.slice(statusIdx + 1).filter(l => !l.startsWith(">"));
        currentPhase.blurb = after[0] || "";
      } else {
        currentPhase.blurb = ctx[0] || "";
      }
      continue;
    }

    // section break (## level-2 heading) — close current phase so subsequent tables don't bleed in
    if (line.startsWith("## ") && currentPhase) {
      phases.push(currentPhase);
      currentPhase = null;
      i++;
      continue;
    }

    // table?
    if (currentPhase && line.trim().startsWith("|")) {
      const { rows, end } = parseTableSection(lines, i);
      // header rows shape: ID | Task | Status | Notes  OR  Block | Description | Status | Notes
      for (const row of rows) {
        if (row.length < 4) continue;
        const id = stripBackticks(row[0]);
        const titleRaw = row[1];
        const statusRaw = row[2];
        const notesMd = row[3];
        // skip header-like leftovers (defensive — already handled, but cheap)
        if (/^[\s:-]+$/.test(id) || /^Block|ID|Item|Issue$/i.test(id)) continue;
        currentPhase.blocks.push({
          id,
          title: stripStrike(titleRaw),
          title_raw: titleRaw,
          striked: /~~.+~~/.test(titleRaw),
          status: classifyStatus(statusRaw),
          notes_md: notesMd,
        });
      }
      i = end;
      continue;
    }

    i++;
  }
  if (currentPhase) phases.push(currentPhase);

  return { fileHeader, phases };
}

function stripBackticks(s) {
  return s.replace(/^`(.+)`$/, "$1").trim();
}
function stripStrike(s) {
  return s.replace(/~~(.+?)~~/g, "$1").trim();
}

// ---------- Tech Debt + Backlog (flat tables in pipeline.md) ----------

function extractFlatSection(content, h2Title) {
  // find "## <h2Title>" then first table after it, until next "## " or "---"
  const lines = content.split("\n");
  const startRe = new RegExp(`^##\\s+${h2Title}\\s*$`, "i");
  let i = lines.findIndex(l => startRe.test(l));
  if (i < 0) return { rows: [], blurb: "" };
  i++;
  let blurb = "";
  while (i < lines.length && !lines[i].trim().startsWith("|") && !lines[i].startsWith("## ")) {
    if (lines[i].trim() && !blurb) blurb = lines[i].trim();
    i++;
  }
  if (i >= lines.length) return { rows: [], blurb };
  const { rows } = parseTableSection(lines, i);
  return { rows, blurb };
}

function rowsToFlatItems(rows, schema) {
  // schema: array of column meanings: "id" | "title" | "status" | "notes" | "origin" | "ignore"
  return rows.map(row => {
    const item = {};
    schema.forEach((meaning, idx) => {
      const cell = row[idx] ?? "";
      if (meaning === "status") item.status = classifyStatus(cell);
      else if (meaning === "title") {
        item.title = stripStrike(cell);
        item.striked = /~~.+~~/.test(cell);
        item.title_raw = cell;
      }
      else if (meaning === "id") item.id = stripBackticks(cell);
      else item[meaning] = cell;
    });
    return item;
  }).filter(item => {
    // drop separator-like rows
    const id = item.id || item.title || "";
    if (!id) return false;
    if (/^[\s:-]+$/.test(id)) return false;
    return true;
  });
}

// ---------- Archive parser (similar to pipeline) ----------

function parseArchiveFile(content) {
  // archive uses same Phase structure + a "Resolved Technical Debt" flat table
  const phases = parsePipelineFile(content).phases;
  const td = extractFlatSection(content, "Resolved Technical Debt");
  // archive TD table schema: ID | Issue | Status | Notes
  const tdItems = rowsToFlatItems(td.rows, ["id", "title", "status", "notes"]);
  return { phases, resolved_td: tdItems };
}

// ---------- Backlog parser ----------

function parseBacklogFile(content) {
  // backlog.md has multiple ### sections, each with one table: Item | Description | Origin
  const lines = content.split("\n");
  const sections = [];
  let i = 0;
  let current = null;
  while (i < lines.length) {
    const line = lines[i];
    const h3 = line.match(/^###\s+(.+?)\s*$/);
    if (h3) {
      if (current) sections.push(current);
      current = { title: h3[1].trim(), items: [] };
      i++;
      continue;
    }
    if (current && line.trim().startsWith("|")) {
      const { rows, end } = parseTableSection(lines, i);
      // Schema: title | description | origin   (no status column)
      const items = rows
        .map(r => {
          if (r.length < 3) return null;
          return {
            id: r[0] ? stripBackticks(r[0]).slice(0, 40) : "",
            title: stripStrike(r[0]),
            title_raw: r[0],
            striked: /~~.+~~/.test(r[0]),
            description: r[1],
            origin: r[2],
            // backlog rows have no status; treat all as "todo" (📋)
            status: classifyStatus("📋"),
            notes_md: r[1] + (r[2] ? `\n\n**Origin:** ${r[2]}` : ""),
          };
        })
        .filter(Boolean)
        .filter(item => item.title);
      current.items.push(...items);
      i = end;
      continue;
    }
    i++;
  }
  if (current) sections.push(current);
  return sections.filter(s => s.items.length);
}

// ---------- Pipeline.md secondary tables: Backlog + TD + Ad-hoc ----------

function parsePipelineSecondaryTables(content) {
  const td = extractFlatSection(content, "Technical Debt");
  // Schema: ID | Issue | Status | Notes
  const techDebt = rowsToFlatItems(td.rows, ["id", "title", "status", "notes"]);

  const adhoc = extractFlatSection(content, "Ad-hoc Blocks");
  // Schema: ID | Title | Status | Notes
  const adhocItems = rowsToFlatItems(adhoc.rows, ["id", "title", "status", "notes"]);

  // pipeline.md "## Backlog" — Schema: Item | Description | Origin (no status, no ID)
  const backlogInPipeline = extractFlatSection(content, "Backlog");
  const backlogItems = backlogInPipeline.rows
    .map(r => {
      if (r.length < 3) return null;
      return {
        id: "",
        title: stripStrike(r[0]),
        title_raw: r[0],
        striked: /~~.+~~/.test(r[0]),
        description: r[1],
        origin: r[2],
        status: classifyStatus("📋"),
        notes_md: r[1] + (r[2] ? `\n\n**Origin:** ${r[2]}` : ""),
      };
    })
    .filter(Boolean)
    .filter(item => item.title);

  return { techDebt, adhocItems, backlogItems };
}

// ---------- Build payload ----------

function build() {
  const pipelineSrc = readFileSync(SOURCES.pipeline, "utf8");
  const archiveSrc = readFileSync(SOURCES.archive, "utf8");
  const backlogSrc = readFileSync(SOURCES.backlog, "utf8");

  // Pipeline phases — only those with at least one non-archived phase row
  const { phases: pipelinePhases } = parsePipelineFile(pipelineSrc);
  const { techDebt, adhocItems, backlogItems: pipelineBacklog } = parsePipelineSecondaryTables(pipelineSrc);
  const { phases: archivePhases, resolved_td } = parseArchiveFile(archiveSrc);
  const backlogSections = parseBacklogFile(backlogSrc);

  // Filter phases to only those with at least one block (defensive)
  const activePhases = pipelinePhases.filter(p => p.blocks.length);
  const archivedPhases = archivePhases.filter(p => p.blocks.length);

  // Render notes_md → notes_html for every block / item — once at build time.
  marked.setOptions({ gfm: true, breaks: false });
  const renderNotes = obj => {
    if (obj.notes_md) obj.notes_html = marked.parse(obj.notes_md);
    if (obj.description && !obj.notes_html) obj.notes_html = marked.parseInline(obj.description);
  };
  for (const phase of activePhases.concat(archivedPhases)) {
    for (const block of phase.blocks) renderNotes(block);
  }
  for (const td of techDebt.concat(resolved_td, adhocItems)) renderNotes(td);
  for (const item of pipelineBacklog) renderNotes(item);
  for (const sec of backlogSections) for (const it of sec.items) renderNotes(it);

  // Combine pipeline backlog + dedicated backlog.md sections
  const backlog = {
    pipeline_backlog: pipelineBacklog,
    sections: backlogSections,
  };

  // Stats — pipeline tab also includes ad-hoc blocks
  const allBlocks = activePhases.flatMap(p => p.blocks);
  const archivedBlocks = archivedPhases.flatMap(p => p.blocks);
  const stats = {
    pipeline: tallyByStatus(allBlocks.concat(adhocItems)),
    tech_debt: tallyByStatus(techDebt),
    backlog: tallyByStatus(pipelineBacklog.concat(backlogSections.flatMap(s => s.items))),
    archive: tallyByStatus(archivedBlocks.concat(resolved_td)),
  };

  return {
    project: PROJECT_NAME,
    generated_at: new Date().toISOString(),
    statuses: STATUS_DEFS,
    pipeline: { phases: activePhases, adhoc: adhocItems },
    tech_debt: { items: techDebt },
    backlog,
    archive: { phases: archivedPhases, resolved_td },
    stats,
  };
}

function tallyByStatus(items) {
  const t = Object.fromEntries(STATUS_DEFS.map(s => [s.key, 0]));
  t.unknown = 0;
  t.total = items.length;
  for (const it of items) {
    const k = it.status?.key || "unknown";
    t[k] = (t[k] || 0) + 1;
  }
  return t;
}

// ---------- Emit ----------

function emit(payload) {
  if (!existsSync(DIST_DIR)) mkdirSync(DIST_DIR, { recursive: true });
  // Copy static assets (favicons, etc.) into dist/
  const assetsSrc = join(__dirname, "assets");
  if (existsSync(assetsSrc)) {
    cpSync(assetsSrc, join(DIST_DIR, "assets"), { recursive: true });
  }
  const tplPath = join(__dirname, "index.html");
  const tpl = readFileSync(tplPath, "utf8");
  // Embed JSON in a <script type="application/json"> tag — avoids JS-source escaping pitfalls
  // (U+2028/U+2029, lone backslashes, etc). Then parse it at runtime.
  const json = JSON.stringify(payload).replace(/<\/script/gi, "<\\/script");
  const dataBlock = `<script type="application/json" id="__lens_data__">${json}</script>`;
  // Function-form replacement: prevents JS String.replace from interpreting $\`, $&, $', $1 etc.
  // as backreferences in the data block. (Pipeline content contains `US$` triggering $\` expansion.)
  const out = tpl
    .replace(/__PROJECT_NAME__/g, PROJECT_NAME)
    .replace("<!--__LENS_DATA__-->", () => dataBlock);
  writeFileSync(join(DIST_DIR, "index.html"), out);
  console.log(`✓ Built lens → dist/index.html (${(out.length / 1024).toFixed(1)} kB)`);
  console.log(`  pipeline: ${payload.pipeline.phases.length} phases, ${payload.pipeline.phases.reduce((n,p)=>n+p.blocks.length,0)} blocks`);
  console.log(`  tech debt: ${payload.tech_debt.items.length}`);
  console.log(`  ad-hoc: ${payload.pipeline.adhoc.length}`);
  console.log(`  backlog: ${payload.backlog.pipeline_backlog.length} (pipeline) + ${payload.backlog.sections.reduce((n,s)=>n+s.items.length,0)} (backlog.md)`);
  console.log(`  archive: ${payload.archive.phases.length} phases, ${payload.archive.phases.reduce((n,p)=>n+p.blocks.length,0)} blocks, ${payload.archive.resolved_td.length} resolved TD`);
}

emit(build());
