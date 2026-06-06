# TRON ↔ 42labs Canon Realign

Status: design, pre-implementation. Source of decisions: brainstorm 2026-06-05/06.

The root finding: TRON kept its **own** pipeline (5-col table, statuses `pending·cleared·in-progress·blocked·done·abandoned`, gitignored, TRON sole writer). The 42labs canon (`new-project-template/templates/meta/`) already owns the pipeline — a git-tracked living doc + `blocks/*.md`, written by **agents via PR**, emoji statuses, user-triggered done. TRON was a parallel tracker. It must become a **driver of the canon flow**, owning zero pipeline state.

Guiding rule: **canon is truth; TRON reads, agents write.** Anything TRON needs from canon must be **additive and inert** to a project that runs without TRON.

---

## Decisions locked

1. **TRON owns no pipeline.** It reads the project's canon `pipeline.md` + `blocks/*.md`.
2. **TRON writes nothing to git.** All its writes stay in gitignored runtime state.
3. **Dispatch truth = the block file.** `blocks/{id}.md` headers (Status, Depends-on, Reviewer class, Merge, Deploy) drive decisions. `pipeline.md` = roadmap/ordering only.
4. **Runtime state is disposable.** Each wake rebuilds from trunk + open PRs + alive workers. `workflow-state.yaml` is a within-session cache, never authority.
5. **Read mechanism: local read-only trunk checkout.** `git fetch` + `pull --ff-only` each tick (tolerate failure → reuse last snapshot) + `gh pr list` for in-flight. Never block the loop on network.
6. **Agent "DONE" is a trigger, not truth.** TRON runs the canon DoD gate on evidence, bouncing the agent until each stage passes.
7. **DONE includes deploy.** Merged ≠ done. Deployed-clean + post-deploy verification = done. A merged branch that fails to deploy is **not-done → fix**.
8. **Merge: per-session knob, per-gate, block can raise.**
   - `merge_staging: APPROVED|ASK` (default **APPROVED**), `promote_main: ASK|APPROVED` (default **ASK**). Runtime only; resets each session.
   - Architect stamps sensitive blocks `Merge: needs-user` → forces ASK even when the session is APPROVED (**raise-only**, never lowers).
   - Approval state held in TRON runtime; TRON never writes it to git.
9. **Reviews: both layers.** Canon per-block critic (block `Reviewer class` → critic at stage 5, PASS required in the gate) **plus** TRON's cadence sweep (every N merged-✅ blocks, counted from trunk and deduped, TRON dispatches a reviewer over the batch; findings → architect → adhoc blocks via PR).
10. **Branch model: detect at seed, adapt.** `repo.staging: staging|none`. Single-branch → only the `merge_main` knob; two-gate → `merge_staging` + `promote_main`.
11. **TRON owns zero agents.** No personas ship inside TRON. It adapts to whatever agents the project defines (canon `agents/*.md`). When TRON later gains a scaffolding step, any agents it creates are written **into the project structure**, never bundled in TRON. → delete `skills/{architect,engineer,reviewer}.md`.
12. **TRON owns no work-unit format.** The "spec" abstraction is retired — the canon **block** (`blocks/*.md`) is the only work unit, and it already carries every field TRON's spec invented (Goal/Tasks, Acceptance Criteria, Depends-on, Out-of-scope, owner role via `Reviewer class`/assignment). → delete `spec.example.md`, the `specs` pointer, and all "spec ID" language.

**Naming rule (applies to every rename below):** names are as **descriptive** as possible — no collisions with canon terms, no ambiguous shorthand.

---

## Part 1 — Everything that must change in TRON

### A. Truth & state model
- Replace "mirror is authority" with **trunk is authority**. `workflow-state.yaml` demotes to a disposable cache.
- **Wake = rebuild:** read `blocks/*.md` (status, deps, gates) + `pipeline.md` (order) + `gh pr list` (in-flight) + scan alive worker processes → reconstruct `active_workers`, cadence, queue. Handles crash, off-session, and tron→no-tron→tron with no drift.
- Drop `_pipe_sig`, the internal/host reseed logic, and the N1/N2 problems entirely (they vanish with write-back).

### B. Reader — `engine/hostpipe.py` (rewrite)
- Parse the canon **living doc**: sections (Roadmap phases, Technical Debt, Ad-hoc, Backlog), pipe tables `ID|Task|Status|Notes`, block-file ref from Notes, `### Phase` headers.
- Parse **block headers**: `**Status:**`, `**Depends on:**`, `**Reviewer class:**`, `**Merge:**`, `**Deploy:**`, `**Phase:**` — fixed `**Key:** value` lines, deterministic regex. No LLM.
- **Emoji map:** `📋`→to-do · `🔄`→in-progress · `✅`→done · `📌/🔧/❌/📦/✂️`→not-dispatchable.
- **Delete** `write_back`, `write_internal`, `_render_table`.

### C. Dispatch gate — replaces `cleared`
- `dispatchable = block file in blocks/ (not archive) AND Status == 📋 AND every Depends-on is ✅ on trunk`.
- **`cleared` retired.** Architect "clearing" = architect **authoring the block file** (PR merged → file on trunk at 📋). `pending` = a roadmap/backlog row with **no block file yet** → an architect scoping job.

### D. `engine/fsm.py`
- Delete `_pipeline_writeback`, `_pipe_sig`, the write-back call in `tick()`. Replace `_load_pipeline` with `_refresh_from_trunk` (fetch/read each tick, cache, tolerate failure).
- Delete status-write paths `set_block_status` / `clear_block` / `insert_adhoc_blocks` (status is read-only from trunk).
- **`worker.done` handler:** no status flip. It launches the **DONE gate** (§F). Liveness only.
- **`worker.wall` → blocked:** runtime escalation state, not git.
- **architect forward/clear:** "block file authored," confirmed on trunk — not a message-driven flip.
- **architect.logged/adhoc:** architect authors the adhoc block file + pipeline row via PR; TRON sees it on next refresh.
- **`recover()`:** rebuild from trunk + `gh pr list`; no status re-writes.
- **`_all_settled()`:** end when no block is 📋/🔄 open on trunk, no open fleet PRs, architect queue empty, no due cadence, no active workers.

### E. `engine/state.py`
- Drop pipeline write helpers. `pipeline` → trunk-read cache. Add: `seen_done` set (cadence dedup), in-flight PR tracking, `approvals` (runtime). Keep `active_workers`, `cadence`, `architect_queue`, session cursor, `live_config`.

### F. DONE gate (new core enforcement)
On worker "done", TRON drives the canon 6-stage flow, bouncing on missing evidence:
1. **Local ACs validated** (stage 2) — require a clean Completion Report; else → "go validate."
2. **PR open + CI green** — monitor; failures → fix.
3. **Merge** — per §8: session knob + block `Merge: needs-user` (raise-only). ASK/needs-user → escalate to operator; agent merges when approved.
4. **Post-merge** — clean up worktree/branch, update locals, **re-run ALL tests on trunk** (stage 5); regression → back to work.
5. **Deploy** (if applicable; §G) — agent confirms actually merged **and** deployed; deploy fail = not-done → fix.
6. **Flip + archive** — agent sets `✅`, `git mv` to `blocks/archive/`, updates pipeline row, via PR. TRON sees `✅` on trunk → counts done, cadence++.

TRON gates on **evidence** (test output, CI status, trunk state, deploy check), never the agent's word.

### G. Deploy gate config
- **Project default + per-block override.** Project declares the deploy-success check; a block may override (`Deploy: none` to opt out, or a custom check). DONE step 5 enforces it when applicable.

### H. Reviewers (both)
- **Per-block critic:** block `Reviewer class` → critic at stage 5, PASS required to flip `✅`.
- **Cadence sweep (TRON-only):** every N merged-✅ (from trunk, deduped via `seen_done`) → reviewer over the batch → findings → architect → adhoc blocks via PR.

### I. Config / paths
- `ctx.py` / `project.yaml`: add `blocks_dir`, `archive_dir`, `pipeline_path`, `repo.staging: staging|none`. `repo.main_branch` already exists.
- **`.gitignore`:** un-ignore `pipeline.md` (now tracked). Keep `workflow-state.yaml` ignored.

### J. Seeder & contracts
- `tron-seed.md` Step 5 + contracts **§7 (host table format)** and **§8 (gitignored, no-history trade-off)**: **delete** the host/internal choice and the no-history claim — both now false. Pipeline = the project's canon `pipeline.md` (tracked); TRON reads block files for dispatch. Detect the repo gate model (staging?).
- **Drop** `templates/pipeline.md` (TRON's 5-col) and `pipeline.example.md`. Reference the canon pipeline shape instead.

### K. Agents — TRON ships none (decision #11)
- **Delete** `skills/{architect,engineer,reviewer}.md`. These are personas, not procedures (mis-filed under `skills/` — canon puts personas in `agents/`), and they encode the retired model (`cleared`, "spec ID", a single generic reviewer).
- TRON reads the **project's** `agents/*.md` (path from `project.yaml`). It adds only its thin dispatch/report protocol on top — never a persona.
- Future scaffolding that creates agents writes them **into the project**, outside TRON.

### K2. Spec abstraction — retired (decision #12)
- **Delete** `spec.example.md`. Work unit = the canon **block** (`blocks/*.md`); TRON reads it for dispatch (§B, §C).
- `project.example.yaml`: drop the `specs` pointer, the bundled `agents:` list, and `pipeline.mode/path` (all retired model). Keep the rest (repo facts, conventions, operator-only tasks, validation gaps, notifications, ci/deploy).
- Purge "spec" / "spec ID" language from `tron-seed.md`, `tron.md`, routing, messages — everywhere it means "block."

### L. Console, protocols & diagram
- `console.py`: run-scoping at bootup is a three-way prompt (msg `session.scope`, TRON voice): **(1) all open phases and blocks · (2) a specific phase · (3) a range of blocks** — never status edits. TRON dispatches only in-scope, still-open (📋, deps ✅) blocks; ✅ stays invisible. `show_pipeline` reads the cache.
- **Rename `protocols/session-end.md` → `protocols/run-teardown.md`.** It's how **TRON** ends its supervision *run* (settle → release the fleet → tear down), distinct from canon `skill-session-end-*` (how an *agent* closes its session) — the shared name is a collision. Keep the logic; shed the retired statuses (`pending/cleared/in-progress/blocked` → trunk-read gate: 📋/🔄 open, PRs, workers).
- README workflow diagram: **swimlanes (Agent / TRON / Trunk)** so the gate layer is visible — "DONE" sits in Agent; TRON's interrogation steps gate between agent and trunk; merge + `✅` land in Trunk.

---

## Part 0 — The deliverable: a new `new-project-template` version

The canon-side work is **not a patch** — it ships as a **new version of `new-project-template`**, a clean general-purpose template that any 42labs project adopts whether or not it ever runs TRON. TRON support is folded in as **additive, inert structure**: a project that never seeds TRON sees only good hygiene (a precise pipeline format, two optional block fields, a sharper DoD). A project that does seed TRON finds every hook it reads already present and standardized.

Principles for the new version:
- **TRON-agnostic on its face.** No file, field, or wording names TRON or assumes a supervisor. Reads as plain project hygiene.
- **Deterministic-readable.** The pipeline + block formats are tight enough for a non-LLM reader (TRON) to parse, without constraining a human author.
- **Inert additions only.** New fields default to the no-op value; new wording extends existing DoD, never replaces it.
- Versioned + changelog'd as a canon release.

Part 2 below is the concrete change-list for this version.

---

## Part 2 — Canon (`new-project-template`) adjustments

All additive; all inert to a project running without TRON. Together they constitute the new version (Part 0).

1. **Pipeline format contract.** State the deterministic shape `pipeline.md` already mostly follows: phase headers `### Phase N:`, tables `ID|Task|Status|Notes`, **emoji-only** status from the fixed set. Makes the deterministic reader safe. (Humans already follow it.)

2. **Block header fields** (`blocks/block-template.md`):
   - `**Merge:** self | needs-user` (default `self`) — architect stamps the genuinely risky ones. Reads as plain guidance to a human.
   - `**Deploy:** none | <check>` (optional; overrides the project deploy default).

3. **DoD wording** (`principles*` / DoD flow): make explicit that **merged ≠ done; deployed-clean + post-deploy verification = done; a deploy failure is not-done and must be fixed.** Extends the existing "PR-merged ≠ Done." Good practice with or without TRON.

4. **Project deploy default** (project config): `deploy.enabled` + a success check, overridable per block (pairs with field #2).

---

## Open / to confirm before build
- *(none — all confirmed.)*

*(Resolved: TRON ships no agents → #11; spec retired → #12; cadence already per-type/per-project via seeder (only the counting source moves to trunk-✅, §H/§D); run-scoping = `session.scope` three-way prompt, §L.)*
