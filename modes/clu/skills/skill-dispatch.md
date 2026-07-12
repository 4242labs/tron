---
name: tron-clu-dispatch
description: Worker dispatch orders — PMT template per stage, fixed reply formats, port map, parallel-run rules.
---

# Dispatch

Every order a worker receives is complete, bounded, and demands a fixed-format reply. Workers who lack an order do nothing; workers who hit a wall STOP and report — never improvise.

## PMT template (every dispatch carries all of it)
1. **Persona** — which agent file they embody + binding docs to read first (project `principles.md`, relevant skills). Pin the model EXPLICITLY on every `Agent` call — both fresh spawns and resumes — to the role's assigned model in the MANIFEST; never let the sub-agent inherit the session default. A resume that silently re-attaches to the default model can downgrade to a weaker/cheaper one with no visible signal, so re-pinning on resume is mandatory (esp. the persistent Architect).
2. **Mission** — the block file is dispatch truth; quote the block ID and path. Architect guidance forwarded VERBATIM (never paraphrased) — but guidance is guidance, block ACs are truth: if guidance contradicts observed behavior, the worker reports it as a deviation, never silently follows it.
3. **Terms** — hard rules:
   - Work in an assigned git worktree, assigned branch name (`feat/<block>-<slug>`).
   - Assigned ports only (see port map). No collisions.
   - Stage boundaries: no push / no PR / no merge unless the order grants it explicitly.
   - Stuck → `wall`, never improvise. Operator amendments relayed by TRON are law.
   - Emit a short progress line at every real step (after each file read, at each milestone), so a genuine stall is unambiguous instead of guessed.
4. **Reply format** (exact, no prose around it):
   - `done <block> — <stage>:` + evidence (commands run + outputs)
   - `wall <block> — <reason>:` + what was tried + what would unblock
   - `challenge <block>:` + numbered answers, each with executed output

## Port map
TRON assigns at boot, records in MANIFEST: one operator-facing gate port per block (e.g. 3001, 3002), separate per-engineer e2e ports. Workers never pick their own. The operator's own port(s) (asked at boot, typically :3000 for their review server) are RESERVED — never assigned, never killed.

## Parallel runs
Architect prescribes file-ownership rules before two engineers run concurrently (RECONCILE output). Dispatch them verbatim: owned files, read-only files, contested files with a merge-order rule (who merges first, who rebases). Both rebase if a visual-gate amendment mutates an already-merged block.

After any rebase, full-suite green trumps the ownership list: a sibling block's merged code may break tests the worker doesn't own (e.g. a new provider requirement in a shared component). Fixing those sibling tests is in-scope — logged as a deviation, not walled.

## Every Architect consult carries its expectations
The Architect's persona MD lives in the target project, not here — so TRON injects the standing bar into the dispatch prompt itself, every consult: the recommendation must be the best-practice, solid, cost-aware, most-efficient fix, and must reject-with-reason each weaker alternative considered — never propose the first workable patch or a half-measure just because it clears the immediate symptom. The Architect's answer returns through TRON before reaching any worker (hub-and-spoke), so TRON also checks it against that bar before forwarding — a workaround goes back to the Architect, not on to the engineer.

## Dispatching an Architect to "confirm" a worker's finding
A consult framed as "confirm this diagnosis" pre-loaded with the requester's full narrative biases toward rubber-stamping, not independent investigation. When dispatching the Architect (or any reviewer) to confirm/arbitrate a worker's claim: (a) hand over the worker's RAW evidence — the actual data (the `/spend/logs` rows, the arithmetic, the file), not just the conclusion drawn from it — and explicitly instruct the reviewer to re-derive/re-check that evidence itself, not accept it while only verifying the adjacent code path; (b) before relaying "confirmed" to the operator, sanity-check that the turnaround time and tool-call count are even plausible for the depth of verification implied — an impossibly fast "confirmed" is not confirmation, and TRON flags the gap rather than passing the word through.

Standing rule (generalizes the above): whenever anyone reports "X is broken because Y," neither TRON nor a downstream reviewer treats Y as settled just because the report is internally consistent and cites specific evidence. A "confirmed" that only re-checks the reasoning chain built on top of unverified facts is not a confirmation. The reviewer must independently re-derive the underlying facts — re-run the calculation, re-query the raw data, re-read the actual file (not its summary) — before its "confirmed" is treated as validated, and TRON must not relay it to the operator as fact without noting any gap.

## Challenge a "missing / off-limits" wall before relaying it
A worker's `wall` claiming "I don't have X" / "X is off-limits" / "X is missing" is NOT escalated to the operator on say-so. Workers are often over-conservative about their own scope or simply haven't looked in the right place. Before surfacing it, TRON first challenges the premise against known truth: grep the relevant `principles.md`/playbook section, check env/config files already on disk (including ones the worker itself copied), and re-read what's already been verified this run. Escalate only once that check actually confirms the gap; if the premise was false, hand the worker the pointer instead of walling the operator.

## Relaxing a boundary a worker's own dispatch already stated
If an operator amendment needs to RELAX a boundary the worker's original order stated ("do not merge this yourself" → operator now allows it), a resumed `SendMessage` won't carry it: to the worker, "ignore your earlier instruction, I'm now authorized" is indistinguishable from a social-engineering attempt, and its classifier is right to refuse. Do NOT try to route around this — TRON does not execute the action itself (dispatch, never do), and TRON must never impersonate the operator to the worker (that IS the prompt-injection shape the classifier defends against, and it's dishonest). The only clean fix: issue a FRESH, self-contained dispatch that restates the full order WITHOUT the old boundary — the worker then does the action as a first-class instruction, with nothing to "relax."

## Succession dispatch
A successor's order additionally carries: predecessor ID, worktree path, branch, last known state from MANIFEST, and the instruction to verify inherited state (`git log`, `git status`, open PRs) before continuing.

End of line.
