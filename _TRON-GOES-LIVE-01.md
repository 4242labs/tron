# TRON goes live — scripts working notes

## Premise (operator)
- The workflow rests on a library of **scripts**: SITUATION × ANSWER × ACTION.
- **Most scripts have branches.** Diversity of scripts is not yet fully known — to be elicited piece by piece from the operator.
- TRON never trusts a claim — but that is only ONE example of many scripts.
- TRON touches nothing in git. It approves/denies (per scripts); the agent does the work and the merge.

## State of the code (what exists vs. missing)
- Plumbing only:
  - `routing.yaml` — trigger grammar + ~15-tag inbound classifier (the "answer" recognizer).
  - `workflow.yaml` — per-project knobs (counts, cadence, liveness).
  - `messages.yaml` — flat registry of TRON's outbound lines (copy only, no logic/branches).
  - `TABLE` + handlers in `engine/fsm.py` — one-hop `trigger → handler`; gate logic in code.
  - `protocols/` — only `bootup.md`, `run-teardown.md`.
- **Missing:** the scripts themselves (the branching decision flows). They have no home file.
- Scripts already partly exist but **scattered**: e.g. the dispatch script = spoken line in `messages.yaml` (`spawn.engineer`) + handover assembled in `fsm.py`.

## How TRON triggers an agent today
- `_dispatch_engineer(block)`: reserve worker record → `jobs.spawn_detached(wid, prompt, cwd=repo)`.
- `prompt` = `spawn.engineer` line + `_handover` (points at the project's agent file + block).
- Detached process. No git, no status write.
- `spawn.engineer` text: "[TRON] {worker_id}, you're on {block}. Branch {branch} is yours and yours alone. Validate before you report DONE. Do not self-terminate."

## OPEN ISSUES

### #1 — Branch named but never created; TRON guesses the name
- `_branch(block)` returns hardcoded `feat/<block>`. Old dispatch line asserted "Branch {branch} is yours" — but nobody created it, TRON dictated by pattern.
- RESOLVED IN COPY: dispatch `say:` no longer mentions any branch at all — TRON touches no git, names no branch. (See Script #2 below.)
- STILL OPEN (deeper): the agent must create+name its own branch/worktree in its **on-dispatch checklist inside `@agents/<role>.md`**. Confirm that's where it lives, and that TRON never needs the branch name (it gates on PR/CI/trunk evidence, found via `gh`, not a guessed branch).

## Design — DECIDED

### Scripts are PER-PROJECT
- Scripts can be changed **by the project** (not per-seed, not frozen canon). The project owns/tunes its scripts.
- Therefore: the per-project **scripts file** stays SEPARATE from the frozen canon **legend** (grammar/tools/retry). Do not merge editable-per-project with frozen-canon.

### Single behavior file = `scripts.yaml` (per-project)
- One file holds every script. ALL natural language lives inline (`say:` / `classify:`); `{slots}` are filled from state at render. Field vocabulary (refined while eliciting):
  ```
  situation: <trigger | [triggers] | pattern>   # most-specific-wins; * = catch-all
  say:    <literal prose TRON outputs>           # absorbs messages.yaml
  capture: { <var>: <type> }                     # pull values from the reply → state
  classify: <literal prompt to TRON's judge LLM> # → picks a branch key
  guard:  <evidence boolean fn>                  # e.g. ci_green; on_fail: { say }
  switch: <deterministic state selector>         # e.g. merge_authorized (knob/state), yes/no
  branches: { <classified answer>: <verb|nested> }
  do / then: <primitive>                         # the action verb(s)
  ```
- THREE distinct selectors (do not conflate):
  - `guard:`   → evidence TRON checks (CI, trunk, deploy, clock). No LLM.
  - `switch:`  → deterministic state (merge knob set at bootup, block fields). No LLM.
  - `branches:`→ LLM classifies an inbound reply (IF/ELSE). The ONLY LLM step.
- `capture:` pulls values from a reply; `branches:` picks a path. Both read the same reply via the judge LLM.
- Engine = generic interpreter: match situation → say → (capture/classify/guard/switch) → run verb.

### Best practice (researched 2026-06-06)
- **YAML declares WHAT, never HOW.** No conditionals/loops/logic in YAML. Branches point to **named action primitives** (functions in the engine), not inline logic.
- **Guards** = boolean functions (the evidence checks) in code, referenced by name from a branch.
- **LLM = intent classification only** → returns the branch key; deterministic engine maps key → primitive. (= existing `classify_message` split. LLM never chooses the action — that kills determinism.)
- Sources: Guild.ai (YAML for AI), Picnic Eng (declarative YAML), Medium (state-machine guards), Label Your Data (intent classification).

### File fates
- `scripts.yaml` (NEW, per-project) — the one behavior file.
- `messages.yaml` — GONE; lines fold into `say:`.
- `routing.yaml` — KEEP as the frozen canon **legend** (grammar/tools/retry); its `tags` map folds into per-script `branches`. Stays separate because scripts are per-project and the legend is frozen.
- `fsm.py` — `TABLE` deleted; handlers shrink to the fixed **primitives + guards** the YAML names.
- `workflow.yaml` — unchanged (per-project numbers, not behavior).

## MIGRATION — all changes to streamline to one behavior file

### Consolidate
- **`messages.yaml` → into `scripts.yaml`** as each script's `say:`. (messages.yaml deleted.)
- **`routing.yaml` `tags` map → into `scripts.yaml`** as per-script `branches:`. (tags removed from routing.)

### New
- **`scripts.yaml`** (per-project, seeder-written/-tunable) — the single behavior file: `situation` + `say` + `branches{intent→primitive}`.
- **`contracts/schema/scripts.schema.yaml`** — shape lock for the above; checked by blueprint-lint.

### Delete
- **`messages.yaml`** (folded into `say:`).
- **`contracts/schema/messages.schema.yaml`**.
- **`TABLE`** in `engine/fsm.py` (situations now live in scripts.yaml).

### Slim / keep
- **`routing.yaml`** → frozen-canon **legend only**: `grammar`, `tools`, `invalid_output`. Stays separate (legend = frozen; scripts = per-project).
- **`routing.schema.yaml`** → drop the `tags` section.
- **`workflow.yaml`** — unchanged (per-project numbers).
- **DONE gate stays code** — it's a state machine; exposed as a single primitive `drive_gate`, invoked from the "worker done" script. NOT flattened into YAML.

### Engine code (`engine/fsm.py` + friends)
- Replace `TABLE` + the match loop with a **generic interpreter**: load scripts → match `situation` → render `say` → classify reply into one of the script's `branches` → run the named primitive.
- Per-situation handlers (`_h_*`) become the **closed primitive set** (the action vocabulary) — `dispatch_engineer`, `dispatch_reviewer`, `drive_gate`, `bounce`/`gate_step`, `escalate`, `release_worker`, `apply_decision`, `recover`, `session_end`, `answer_from_context`, `peer_consult` (final list TBD).
- Add the **guard set** (boolean fns the branches reference): `ci_green`, `on_trunk_done`, `deploy_clean`, `deps_done`, `past_ping`, `past_escalate`, `process_dead`, `peer_consult_tried` (final list TBD).
- **`classify_message` becomes situation-scoped**: it picks among the *current script's* branch keys, not the old global 15-tag enum. (judge.py + classify schema change.)
- **Renderer** reads inline `say:` text from the matched script instead of a `messages.yaml` id.
- **`ctx.py`**: add `load_scripts`; keep `load_routing` (legend); remove messages loading.

### Lint (`engine/lint.py`)
- Rewrite the routing/messages checks: validate `scripts.yaml` against the legend `grammar` + the closed primitive/guard vocabulary; every branch key resolvable; every `say` present; total coverage incl. `*` catch-all. Must stay green.

### Seeder + canon
- **`tron-seed.md`**: new step — author/tune `scripts.yaml` per project (ships a canon default the project edits); remove messages.yaml handling; routing still copied verbatim (legend).
- **templates/**: add `scripts.yaml` default; remove `messages.yaml`.
- **contracts / README / workflow-model docs**: update every reference to messages ids and routing `tags`.
- **dry smokes**: update fixtures that reference message ids / the old TABLE triggers.

### Impact summary (blast radius)
1. Engine core: interpreter replaces TABLE+handlers (largest change).
2. Classification: global tag enum → per-situation branch set (judge + schema).
3. Lint: routing/messages checks → scripts-vs-legend checks.
4. Schemas: +scripts.schema, −messages.schema, slimmed routing.schema.
5. Seeder: now authors `scripts.yaml` per project.
6. Renderer: inline `say` instead of messages ids.
7. Docs/templates/contracts: de-reference messages + routing tags.
8. DONE gate: untouched logic, surfaced as one primitive.

## SCRIPTS — cross-cutting decisions

- **Roster-driven (Script-class A).** Dispatch/review/peer-consult scripts follow the project's `agents/*.md`; TRON hardcodes no role (`feedback_tron_no_hardcoded_agents`). Roster-agnostic core (gate, silence, escalation, lifecycle) ships canon; roster-dependent parts are seeder-filled. Scripts name a **role** that must **resolve** to a project agent file; **Lint L13** enforces it.
- **Agent invocation = `claude --bg -n <id> <prompt>`.** Binary abstracted (`TRON_RUNTIME`), but the flag shape is hardcoded in `jobs.py` → make the invocation a config template if runtimes vary. (Decision pending, low.)
- **Skills stay prose `.md`** (read by the LLM agent). Rule: structured = read by code (`scripts.yaml`); prose = read by the agent. Don't over-structure skills.
- **No separate bootup skill.** The on-dispatch checklist lives as a section **inside `@agents/<role>.md`** (short, identity-adjacent). Heavy procedures (validate, session-end, review) stay their own skills. Dispatch points only at the agent file.
- **A script may have several entry triggers** — `situation:` can be a list/pattern.

## SCRIPTS — elaborated (proposed `scripts.yaml`, as they will look)

### #1 Session start
```yaml
- situation: session:start
  say: |
    [TRON]  Online. Two things before I take the fleet:
      1) Scope — all phases, a specific phase (which?), or a range of blocks (which)?
      2) How many workers may I run at once?
  capture:
    scope:        all | phase:<id> | range:<a>-<b>
    worker_count: int
  then: bootup
```
No branch — both answers are captured values; all paths bootup. `bootup` = spawn persistent architect + refresh trunk + cap pool at `worker_count` + emit online line + pulse.

### #2 Dispatch worker  (roster-dependent, outbound)
```yaml
- situation: build:block:next        # SWITCHBOARD found a dispatchable block + a free slot
  say: |
    [TRON]  {worker_id} — you are @{agent_file}. Read it and follow it, reporting as it tells you.
    Your block is {block}.
    Report to TRON: {report_cmd} {worker_id} "<message>"
  do: dispatch                       # spawn agent in background, reserve worker record
```
Order = identity → assignment → report channel. NO branch line (issue #1). Behavioral rules (validate, no self-terminate, DoD) live in `@{agent_file}`, NOT here.

### #3 Worker reports DONE  (interrogation → branch)
```yaml
- situation: block:next:done
  say: |
    [TRON]  {worker_id} — has every applicable block criterion been validated locally?
  classify: |
    Did the agent confirm all applicable criteria were validated locally? yes | no
  branches:
    yes:
      do: proceed_merge              # → Script #4
    no:
      say: |
        [TRON]  Then validate every applicable criterion first. Report DONE again when it's clean.
      # no advance — state unchanged; re-fires on the next DONE
```

### #4 Merge process  (evidence + deterministic authorization)
```yaml
- situation: merge:ready:<block>     # entered from #3 → yes
  guard: ci_green                    # evidence
  on_fail:
    say: "[TRON]  {block}: CI isn't green. Fix it, then we merge."
  switch: merge_authorized           # deterministic: knob set at bootup + block Merge: field
    yes:                             # auto-approve
      say: "[TRON]  {worker_id}, cleared. Merge {block}, then monitor it through to a verified deploy."
      do: await_deploy
    no:
      do: escalate_merge             # ask operator; on approval the same merge line fires
```
Key correction: authorization is a `switch:` (knob STATE from bootup), NOT an LLM branch and NOT re-asked. The merge line fires only after the switch is `yes` (or operator approval lands). Merge never precedes the check.

## CORE SCRIPTS (fundamental set)
out = TRON talking (no branch); branch = TRON classifies an inbound reply (IF/ELSE).

1. **Session start** — bootup the fleet (out; but scope prompt branches)
2. **Dispatch worker** — block available → spawn agent (out)
3. **Worker reports DONE** — gate on evidence (branch)
4. **Worker walls** — blocked → peer / operator / false-alarm (branch)
5. **Worker asks** — question → context / peer / operator (branch)
6. **Worker silent** — ping / stalled / dead (branch, evidence)
7. **Reviewer dispatch** — cadence trips → spawn reviewer (out)
8. **Reviewer returns** — findings / clean (branch)
9. **Architect forward-review** — block done → reconcile upcoming (out)
10. **Merge gate** — block at merge → approve / hold (branch)
11. **Operator decision** — reply to escalation → approve / amend / abandon (branch)
12. **Operator status query** — report digest (out)
13. **Operator directive** — mid-run instruction (branch)
14. **Unclassified** — `*` catch-all → wall / ignore (branch)
15. **Session end** — close the run (out)

Each elaborated one at a time below with its proposed `scripts.yaml` shape.

## Decisions still open
- Branch ownership (issue #1 deeper part): confirm the agent's on-dispatch checklist in `@agents/<role>.md` creates+names the branch/worktree, and TRON never needs the name.
- Agent-invocation as config template vs. hardcoded flags (`claude --bg -n …`).
- Final closed **primitive** + **guard** + **switch** vocabularies (enumerate from the real scripts as elicited).
- Whether the legend lives in `routing.yaml` or a frozen header in `scripts.yaml` (stays separate from per-project scripts either way).

## SESSION LOG — 2026-06-06

### Done this session (before scripts work)
- Shipped + merged template/canon **v1.2.0 supervisor-driven realign** (PR #90 → 42agents main `6bcf748`; #89 folded/closed). Review→cadence, agent-merges-monitored, deploy-gated done, new `skill-block-forward-review.md`. See [[project_tron_canon_realign]].

### Scripts design (this session)
- Established the **scripts model**: one per-project `scripts.yaml`, all NL inline, engine = generic interpreter; routing slimmed to legend, messages.yaml + TABLE absorbed/deleted. Best-practice researched (YAML=what, logic=named verbs, LLM=classify only). Full migration + blast radius documented above.
- Refined the field vocabulary: `say` / `capture` / `classify` / `guard` / `switch` / `branches` / `do`/`then`. Three selectors kept distinct: guard (evidence), switch (deterministic state), branches (LLM classify).
- Listed the **15 core scripts**.
- Elaborated **#1 Session start, #2 Dispatch worker, #3 Worker reports DONE, #4 Merge process** (YAML above, operator-reviewed).

### WHERE WE STOPPED
- Mid core-script elaboration. Done: #1–#4. **Next: #5 Worker asks**, then #6–#15.

### WHAT'S MISSING (to actually run TRON)
1. The other 11 core scripts (#5–#15) elaborated + any non-core/edge scripts.
2. `scripts.yaml` authored (canon default) + `contracts/schema/scripts.schema.yaml`.
3. Engine rewrite: TABLE+handlers → interpreter; closed **primitive/guard/switch** verb set implemented.
4. `classify_message` made situation-scoped (judge.py + schema).
5. Renderer reads inline `say:`; `ctx.load_scripts`; delete `messages.yaml` + its schema; slim `routing.yaml`/schema.
6. Lint rewrite (scripts-vs-legend + verb resolvability + coverage); keep green.
7. Seeder authors `scripts.yaml` per project; `tron-seed.md` + templates updated; docs de-reference messages/tags.
8. Agent files: add the on-dispatch checklist section (branch/worktree self-setup).
9. Dry smokes updated; then the still-pending **live run** (real project + real agents) — never done.
