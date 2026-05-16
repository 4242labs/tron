# FEEDBACK — `skill-validate` + `skill-doctor`

Source: dry-run of both skills against the live `zovv` instance on 2026-05-15, in operator-requested audit-only mode. Findings are spec-level (canon docs in `~/42labs/tron/`), not project-level.

---

## TL;DR

1. Both skills are sound but redundantly re-read the same files and assume a single-repo project shape.
2. There is no first-class "audit-only" mode — operator had to verbally exclude steps 4–7 of session start.
3. **First-run auto-detect is missing** — TRON should run audit-only validate+doctor automatically on its first cold start in a project, before any operator interaction. The operator should not have to ask the first time.
4. Several checks hardcode canon assumptions (single reviewer, single git repo) that don't match real projects.

---

## Process feedback — what worked

- `skill-validate` Mode A is well-scoped: counters ↔ rules ↔ scripts cross-check produced exactly the one real warning (zovv R5 cycle review has no dedicated `scripts.md` situation entry).
- `skill-doctor` structural manifest caught everything that mattered (env keys, cron entries, tooling versions, canon agents present).
- Blocker vs warning severity tiering is the right shape — blockers halt dispatch, warnings surface once.
- Reading order in `tron.md` (6 boot files → validate → doctor) is correct: validate needs the docs loaded; doctor needs project.md parsed.

## Process feedback — friction & redundancy

### F1. Duplicate I/O across skills

`tron.md` step 1 reads all 6 boot files. `skill-validate` step 1 re-reads `workflow.md`, `workflow-state.md`, `scripts.md`, `project.md`. `skill-doctor` step 1 re-reads `project.md`. Three independent loads of the same content. Wasteful in tokens and serialization.

**Fix:** Define a single boot-context bundle loaded once at session start; both skills consume the bundle by reference.

### F2. Single-repo assumption in `skill-doctor` step 2

Skill text says "`repo_root` exists, is a git repo." zovv is multi-repo: workspace root is **not** a git repo; `zovv-meta/` and `zovv-app/` are. project.md redefines this explicitly, but the skill has no branch for the multi-repo case — I had to interpret.

**Fix:** Add `repo_shape: single|multi` to `project.md` schema. Doctor branches on it. For `multi`, validate each declared sub-repo's git state + remote separately.

### F3. Single-reviewer assumption in `skill-doctor` step 2

Skill text hardcodes `architect.md`, `engineer.md`, `reviewer.md`. zovv has three reviewer roles (`reviewer-code`, `reviewer-security`, `data-architect`) — no `reviewer.md`. The skill should derive required agents from `project.md`'s `agents:` block, not from a fixed canon list.

**Fix:** Doctor reads `agents:` from project.md and verifies each declared file exists. Drop hardcoded names.

### F4. `skill-validate` rule-vs-script granularity is ambiguous

R5 has two modes (mid-session every 2 blocks, cycle every 6 blocks). `scripts.md` covers mid-session inline under "Engineer reports DONE" step 4, but cycle review has no dedicated situation. Validate Mode A passes a loose check ("R5 mentioned") and misses this. I caught it only because I cross-read both rule modes.

**Fix:** Validate step 3 should require one situation entry **per rule sub-mode**, not per rule. Either enumerate sub-modes in `workflow.md` with anchor IDs (`R5a`, `R5b`) or require scripts.md headings to back-reference rule IDs.

### F5. Cron-cadence constraint is prose, not validated

`workflow.md` says `silence_ping_min` and `silence_escalate_min` must be multiples of cron cadence (`*/2` default). Neither validate nor doctor checks this against `cron-install.sh` or the live crontab. Easy mechanical check.

**Fix:** Add to doctor step 6: parse cron expression for `sweep.sh`, compute its tick interval in minutes, assert `silence_ping_min % tick == 0` and `silence_escalate_min % tick == 0`.

### F6. No machine-readable audit log

`skill-validate` says "log `validate: pass`" — no path. `skill-doctor` says "Warnings are logged and surfaced once per session" — no path. If TRON crashes mid-session, next start has no record that the last audit passed.

**Fix:** Both skills append a JSON line to `meta/agents/tron/logs/audits.jsonl`:
```
{"ts":"...","skill":"doctor","status":"pass","warnings":[...],"blockers":[]}
```
Subsequent sessions can read the last line to know "last audit was N minutes ago, status X."

### F7. Warnings don't persist across sessions

Doctor surfaces warnings "once per session." If operator ignores a warning, next cold start re-discovers it from scratch with no awareness that it was already raised. Operator may suppress noise; project drifts silently.

**Fix:** Persist warnings to `state.md` under `known_warnings: [{hash, first_seen_at, last_seen_at, suppressed}]`. Doctor only re-surfaces warnings whose hash is new or whose `suppressed: false`.

### F8. Interactive prompt blocks autopilot

`skill-validate` Mode A step 5 ends with a y/n prompt to the operator. Fine for interactive runs; blocks an unattended first-run audit. No `--report-only` variant.

**Fix:** Add a non-interactive mode flag to validate. Audit-only / first-run path uses `report-only`; manual mid-session invocation uses interactive.

### F9. Doctor folder manifest is duplicated in `tron-seed.md`

`skill-doctor.md` step 5 enumerates the required TRON folder structure inline. `tron-seed.md` also enumerates what the seeder creates. Two sources of truth → guaranteed drift as canon evolves.

**Fix:** Pull the manifest into a single file (e.g. `tron-manifest.md` or a YAML block inside `tron-seed.md`) and have both the seeder and doctor read from it.

### F10. Output format inconsistency

Validate writes `validate: pass` (log line). Doctor writes `TRON: doctor clean.` (operator output). Different sinks, different formats.

**Fix:** Standardize: every skill emits (a) one human-readable summary line for the operator, (b) one JSON line to the audit log. Same shape across skills.

### F11. No "audit-only" mode in `tron.md`

`tron.md` "On every session start" is one fixed sequence (steps 1–7). The operator asked for "audit-only" — I had to manually skip steps 4 (write current-id), 5 (recover), 6 (spawn architect), 7 (greet + ask knobs). Nothing in the canon authorizes that.

**Fix:** Add a documented audit-only mode that runs steps 1–3 only, produces a single report, and exits without side effects. See §First-run auto-detect below — this mode is the right primitive for that.

---

## First-run auto-detect (operator requested)

**Problem:** Today, the operator must manually invoke `claude --bg -n TRON "...validate + doctor in audit-only mode..."` the first time TRON is brought up on a project. This is exactly the moment when the human is least sure the seed is healthy — and least likely to remember the invocation.

**Proposed behavior:** On every cold start, before step 4 of "On every session start" in `tron.md`, TRON checks whether this is its first run in the project. If yes, it executes audit-only validate+doctor automatically, surfaces the report, and **only then** proceeds to the per-session knob ask (step 7).

### First-run detection heuristic

A run is "first" if all of:
1. `state.md` `total_sessions == 0`, AND
2. `dispatched.log` is empty (no spawn history), AND
3. `current-id` is empty (no prior session ever wrote it), AND
4. `logs/audits.jsonl` does not exist (or has zero lines).

Any one of these being non-empty means TRON has run here before; skip auto-audit.

### Proposed session-start sequence

```
1. Read 6 boot files (existing)
2. First-run check (NEW) → if first run, run audit-only and surface report to operator
3. Run skill-validate (existing, full mode)
4. Run skill-doctor (existing, full mode)
5. Write current-id (existing step 4)
6. skill-recover if dispatched.log non-empty (existing step 5)
7. Spawn persistent architect (existing step 6)
8. Greet + ask per-session knobs (existing step 7)
   — greeting now includes a one-line audit status: "audit clean" or "audit: N warnings, M blockers"
```

The first-run branch (step 2) and the routine branch (steps 3–4) share the same validate+doctor implementation; only side-effect scope differs (audit-only writes no current-id, does not dispatch, does not ask knobs).

### Why this matters

- The operator can't forget to run the audit on a fresh seed — the moment the seed is most likely broken is the moment it's checked.
- Subsequent starts still run validate+doctor (per existing `tron.md` steps 2–3) so no regression in coverage.
- Audit-only's contract (no current-id, no dispatch, no knob ask) is identical to what the operator improvised today — make it the documented path.

---

## Efficiency / leanness suggestions (ranked)

| # | Change | Impact | Effort |
|:--|:--|:--|:--|
| 1 | First-run auto-detect + audit-only mode (§above) | High — eliminates manual step | Low — heuristic + doc change |
| 2 | Shared boot-context bundle (kill duplicate reads, F1) | Med — fewer tokens, faster start | Low |
| 3 | Doctor reads `agents:` from project.md, not hardcoded list (F3) | High — unblocks multi-reviewer projects | Low |
| 4 | `repo_shape: single\|multi` in project.md (F2) | Med — unblocks workspace-root projects | Low |
| 5 | JSON audit log + cross-session warning persistence (F6, F7) | Med — operator sees only new noise | Med |
| 6 | Rule sub-mode IDs (R5a/R5b) + per-sub-mode script entries (F4) | Low — catches one class of real drift | Low |
| 7 | Validate cron-cadence vs silence-thresholds (F5) | Low — catches a foot-gun | Low |
| 8 | Single manifest file consumed by seeder + doctor (F9) | Low — prevents canon drift | Med |
| 9 | Standardized output format across all skills (F10) | Low — readability | Low |
| 10 | Non-interactive `report-only` mode for validate (F8) | Required for #1 | Low |

---

## What I would not change

- The two-skill split (validate = doc drift; doctor = structural). They check different surfaces; merging them would muddy responsibilities.
- Blocker/warning tiering. Right shape.
- Reading order: validate before doctor. Validate is a logical check on already-loaded content; doctor is filesystem/process I/O. Cheap-first is correct.
- The y/n prompt in validate Mode A interactive path. For mid-session invocations the human-in-the-loop is the right design.
