# BPMN diagram — authoring & publishing

The interactive BPMN flow lives in **`tron-app/workflow/`** and is published to the public site.
This doc owns both halves: **how to draw it** (authoring guidelines) and **how to ship it** (publishing).
Applies to **every** diagram — the core map and each drill-down sub, retrofits included.

## Files & ownership

- **`workflow/workflow.html`** — the core map + every drill-down sub-process (one generator).
- **`workflow/flow-description.html`** — per-node annotations (loaded by `workflow.html`'s panel).
- Assets (favicons, `nyan-cat.gif`) live beside them in `workflow/`; this doc stays in `docs/`.

These are the **single source of truth**. Governing companions in `tron-meta/`: `pipeline.md` (committed
work + status), `backlog.md` (open requirements). Read them before
changing the flow.

---

# Authoring guidelines

## 0. Principles (override everything below)

- **One source per concern.** Each value lives once — a `TOK` token (geometry), a CSS class (chrome), a
  JS component (markup). Things that must match share the source; never set the same size/label/colour twice.
- **Token-driven geometry.** Every size, gap, margin, clearance comes from `TOK` — no hardcoded literals.
  Missing value → add a token. Changing a shared token → **flag the operator first** (tokens are global).
- **Verify in the browser.** Render, screenshot, check against these rules before calling a change done.
  Describing intent is not verifying it.

## 1. Geometry — the track grid

Both engines (`subXML` for subs, `layoutCore()` for the core) place nodes on a **track grid** by the
*same* rule — a sub must look spaced exactly like the core; if it doesn't, the engine is wrong, not the node.

- **Uniform cell.** Width = the widest element (a task), height = the tallest (a sub-process), floored at
  `colMin`/`rowMin`. Every column gets that width, every row that height, laid edge-to-edge with one
  `colGap`/`rowGap`. A gateway/event sits **centred in its full-size cell** — no per-column tightening.
- **Integer positions.** `(col,row)` are whole numbers — no fractional nudges. Two nodes align by sharing
  an integer col/row, never a `0.2` offset.
- **Centres snap to the shared line** — same column → same centre-X, same row → same centre-Y.
- Nodes hold only `(col,row)` + size; x/y is derived. Lay tracks **both** directions from col 0 / row 0
  (cover a start event at column −1 or coordinates go NaN).

**Padding is one symmetric value** (`TOK.pad`): outer pool margin on all sides; the gap *between* lanes is
`2·pad`, *within* a lane it stays `rowGap`. Lanes sit flush with the pool; the owner-name strip
(`TOK.laneBand`) lives inside each lane. Leftmost track inset = `laneBand + pad`; top/right/bottom = `pad`.

**Data objects sit on grid lines too, never in a gutter.** A `SNAPSHOT`/`MANIFEST` box centres on a
column/row line like any node: `above`/`below` → the node's own column; `left`/`right` → the neighbouring
column's centre (past the first/last column it extends one grid pitch, so two boxes off the same edge share
a column). Clear the pool border by `pad`. A box `above` a top-row element (or `left` of the leftmost) gets
room the engine **reserves** (the row/column shifts inward by `dataGap + dataH (+ label)`; the pool grows to
enclose it).

## 2. Layout

- **Single-actor flow → grid** (`pos:[col,row]`): a balanced block, never a long thin strip; a fork is a
  vertical diamond, not a horizontal spread.
- **Multi-actor flow → swimlanes** (row = actor lane) with **explicit columns** (`col:`) so related nodes
  stack in one column (answer → gateway → validate).
- **Align a node with its predecessor's row/column** so the feed enters a clean side straight.
- **Split an overloaded gateway** into two simple ones rather than fanning many angled edges from one.

## 3. Connectors / routing

- **Dock anchors** — fixed points per side **¼ · center · ¾** (`TOK.dock`); a side carries up to 3
  non-overlapping edges, and a node + its data object may share a side at different anchors.
- **Straightest, fewest-turns path (hard rule)** — pure horizontal/vertical when possible; else one bend:
  run straight until aligned with the target's row/column, then turn in (approach side = arrival side).
- **Lines live in the grid gaps, not the tracks** — an orthogonal segment runs down a `colGap`/`rowGap`
  channel *between* tracks; a line passing a track turns into the gutter first. So: **no line crosses a
  node, no two lines share a track, every waypoint stays inside the pool.**
- **Siblings to stacked targets share one trunk** — exits from a gateway dropping to stacked nodes reuse one
  channel, branching at each target's row (never twin near-parallel lines).
- **Edge-entry** — a back-edge enters the side facing the loop (never the top the forward edge uses); an
  up-edge enters the target's top; fan-out exits are staggered.
- **Conversation loops stay in their lanes** — the AIDE↔OPERATOR loop resolves before crossing to
  TRON-RELAY; loop-backs run in a lane's top margin, never over the pool top.

## 4. Labels

- **Off the line, on its own segment** — never overlapping a line, node, or label, never stacked at a shared
  anchor. Horizontal run → label above; vertical run → label beside.
- **Node label = ID on top, verb-led name below** (`ND-NN` / `ND-NN-NN`); all IDs visible, no detail (that
  lives in `flow-description.html`). Link events show only their link name.
- **Gateway label to a clear side** (no edge there). A 4-way hub gets a free diagonal corner; a line grazing
  it is acceptable only when unavoidable.
- **Edge labels are implicit** — no sequence-flow labels render; the named throw/catch + node names carry the
  semantics, arm meaning lives in `flow-description.html`.

## 5. IDs

Hierarchical, expanding the parent: `ND-NN`, sub-steps `ND-NN-NN`, deeper `ND-NN-NN-NN`. Same ID = same node
across diagram and description. **Authored, not positional** — each step carries an explicit id; data stores
carry none (they aren't flow nodes). A load-time lint asserts per-sub ids are unique and contiguous `01..N`.

**TRON-AIDE nodes carry an `LLM`-prefixed id** mirroring their ND-path — any node that invokes the LLM shows
`LLM-…` (same numbering, so it still names its parent process) with its descriptive name. Core nodes are
`LLM-NN`, a sub keeps the full path (e.g. `LLM-02-14`). This spans the whole flow so token-costing steps are
countable at a glance. The diagram is the live roster — don't duplicate it here.

## 6. Header & chrome

- **Fixed top bar** (`.topbar`, height `--head-h`): white, full-bleed, elements vertically centred; same bar
  on the core page and every overlay, canvas fills below. Content sits in the site container
  (`.topbar__inner`: 1280px max, centred).
- **One header component** (`headBar()` + `LOGO_SVG`): `[back?] [TRON logo] | [id badge?] [name]`. Names
  uppercased by class (`.nname`). Logo → `tron.42labs.io` (`_self`). No per-page header markup.
- **Controls right** (`.topctl`): zoom `+ − ⤢`, then the context action (`ANNOTATIONS` on core, `×` on an
  overlay; back lives header-left).
- **No pool vertical title band** — lane-owner bars only.
- **Annotations** = `flow-description` notes in a slide-in right panel (copper toggle); it **covers** the
  header/controls, never pushes them.
- **Bounded** pan/zoom; full-bleed `canvas-warm`; drill-down via clickable collapsed sub-nodes, nested
  overlays with a consistent back button.

## 7. Semantics

- **Gateways always carry a symbol** (X exclusive, O inclusive, …) — never blank.
- **Link throw/catch across a drill-down** pair by an **identical name** (BPMN's only rule for links). Name
  the pair for the **transition** it represents, not its target (`repair`, `restart`) — a target-named link
  (`→ 01-11`) hides which throw feeds the catch and breaks traceability. The shared name carries the branch,
  so a gateway arm into a named throw needs no extra edge label.
- **Message throws are named for the recipient's inbox.** Keep directions distinct: **`… INTAKE` = TRON
  receiving from an actor** (inbound catch: `FLEET INTAKE`, `OPERATOR INTAKE`); **`… INBOX` = an actor's own
  inbox, TRON sending to them** (outbound throw target: `AGENT INBOX`, `OPERATOR INBOX`). A throw to the
  operator is `OPERATOR INBOX`, never `OPERATOR INTAKE`.
- **Data objects vs stores.** A transient **data object** (folded-doc — `SNAPSHOT`, `MANIFEST`) and a durable
  **data store** (cylinder — `Project Docs`, via `store:true`) attach by a dotted association to every node
  that produces or reads them (placement → §1). Conversing AIDE nodes read the shared **Project Docs** store
  (the project's git-tracked core files) to ground each dialogue.
- **Association direction follows the action.** A **write** is directed — an arrow *into* the target
  (`MSG → FLEET HOPPER`). A **store read** is **undirected — a plain line** (`FLEET HOPPER → PULSE`, every
  `Project Docs → AIDE`): the read is the node's action, the store is passive. (A data-object *consume* keeps
  its arrow into the node — only stores go arrowless on read.)
- **A store can live in its own lane.** When the store belongs to a different actor than the node touching it
  (e.g. an `OPERATOR INBOX` throw in the AIDE lane writing the Operator Inbox store in the OPERATOR lane), tag
  the data spec `lane:'op'`: the engine opens that lane band and drops the store in, same column as the node,
  the directed write running straight down. Mirrors the core's lane-resident store (`FLEET HOPPER`).
- A node's body is mechanical **TRON-RELAY** steps; conversation/escalation lives in sub-processes with their
  own RELAY/AIDE/OPERATOR lanes.

## 8. Scope discipline

Diagrams keep **all** elements (the map). Detail docs + drill-downs cover **validated** nodes only, one at a
time.

## 9. Semantic validation (bpmnlint)

Layout is governed by §1–§7; **semantics** (graph connectivity, gateway logic) by **bpmnlint** — wired in
`tron-app/.sandbox/bpmnlint/` (gitignored). After a structural change, extract the XML from the running page
(`coreXML()` / `subXML(FLOW[k])` → `diagrams/*.bpmn`), then `./lint.sh`.

- **Export must be spec-complete** — every node carries `<incoming>/<outgoing>` (both generators do); without
  them bpmnlint false-reports "disconnected".
- **Curated ruleset** (`.bpmnlintrc`) — off where TRON's model deliberately trips them: `label-required`
  (pools unnamed; the header titles the diagram), `start/end-event-required` + `link-event` (drill-down
  content and link partners live in separate overlays), `no-implicit-start/end`. On: `no-implicit-split`,
  `fake-join`, `superfluous-gateway`.
- **The linter advises; the operator decides** — findings are never auto-applied.
- **Blind spot** — it checks graph shape, not flow *logic*; it won't catch a mis-placed node. Complements the
  walk-through, never replaces it.

---

# Publishing

The site serves a **generated copy** at **`tron.42labs.io/workflow/`**, stored in `tron-www` at
`public/workflow/` (`index.html` = `workflow.html`, plus `flow-description.html` + assets), each carrying a
`GENERATED — do not edit` banner. **Never hand-edit it** — it's overwritten on every sync. One owner (this
repo), one derived copy (the site).

**The rule:** any change to `workflow/` MUST be published — a diagram change isn't "done" until the public
copy matches.

- **Automated (fully hands-free):** the CI Action `.github/workflows/publish-diagram.yml` runs on a push to
  `main` touching `workflow/**`, opens a sync PR on `tron-www`, and **auto-merges it** — Pages then deploys.
  No manual step. Triggering publish = pushing **tron-app**, not meta. (The Action authenticates the
  cross-repo sync + auto-merge with a repository secret.)
- **Manual fallback** (only if the Action is disabled/broken): copy `workflow/`'s files into
  `tron-www/public/workflow/` (`workflow.html` → `index.html`, plus `flow-description.html` + favicons +
  `nyan-cat.gif`), keep the banner, push `main`. Verify live.

**Asset paths are relative** (`favicon-…`, `nyan-cat.gif`) so `workflow/` is self-contained and portable —
it works served from its own directory locally and at `/workflow/` on the site. `workflow.html` references
`flow-description.html` and its assets relatively; they stay co-located, which is why the publish step copies
the whole set.
