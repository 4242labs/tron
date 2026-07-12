---
name: tron-clu-gates
description: Prompted-challenge script and visual-gate procedure — say-so proves nothing; TRON challenges, workers execute evidence.
---

# Gates

TRON never verifies work itself. It challenges the worker; the worker executes and returns evidence. TRON judges the evidence.

## Gate order (fixed, per block)
challenge (ACs evidenced) → visual gate (operator) → PR → merge authorization. Never open a PR for merge before the AC confirmation is in.

## CHALLENGE (on every `done` report)
Send verbatim:
> "Challenge <block>: for EACH acceptance criterion, confirm its fixed verification method was EXECUTED, not inferred. Execute anything unexecuted now. Reply `challenge <block>:` with numbered answers — each answer names the AC, the command/method run, and pastes the output."

Accept only evidenced answers. "Covered by the test suite" without the run output = rejected, re-challenged. N/A ACs must state why they don't apply. Log verdicts in the MANIFEST gate ledger.

**ACs are hard rules — PARTIAL is a hard stop, never a decision point.** When a worker honestly reports any AC as PARTIAL / unvalidated / provable-only-later (or an agreed condition like "all ACs pass in both local and staging before merge" is known unmet), the block HOLDS automatically. TRON must NOT generate a "merge now anyway, AC fast-follows" option for the operator — no matter the time pressure or how narrow the gap. The only move on the table is wait, OR an explicit, deliberate re-scoping of the block's ACs (a separate operator action, never a silent waive of evidence on the existing ones). And TRON's own status language (chat, TG, voice) must mirror the block file's literal status field exactly — never paraphrase a `🔄 In progress` block as "closed" / "done."

Operator-only ACs (marked `manual_by:operator` or otherwise executable only by a human) are exempt from worker evidence: route them onto the visual-gate checklist instead, and record the operator's verdict as that AC's evidence in the gate ledger.

The same challenge is re-issued at CLOSE for stage-5 trunk re-validation — merging does not exempt evidence.

**A green suite does not mean correct — hunt two traps.** When challenging/reviewing evidence, TRON (and any reviewer it dispatches) must actively probe for: (1) **shortcut-path tests** — a test that calls a handler/function directly and bypasses the real input/queue/dispatch pipeline, so it's blind to ordering and integration bugs; and (2) **wrong-scope validation** — a check that verifies "something ran" or "a file landed" rather than "the *right* thing ran / actually passed." Both let a defect ship under a green suite. An AC "evidenced" by either is rejected and re-challenged against the real path.

## Gates that require a live production secret — split, never relay
A gate whose evidence needs a live production credential (master key, prod DB password, etc.) is NOT satisfied by any relay: a worker's own classifier will refuse the pull through TRON no matter how the operator authorized it — and it's right to. Do NOT route around it by pasting the raw secret (or its raw privileged output) into the worker's conversation: that leaves a production credential in the transcript (logged, compaction-summarized, sent to the provider) — a worse outcome than the block it bypasses. Best structure: SPLIT the gate. The credential-bound action is operator-owned — the operator runs it in their own environment where the secret already lives — and the worker verifies only the sanitized, non-secret RESULT (e.g. "12 team budgets synced," a diff, an exit code, a redacted status line), never the key itself. Secrets stay in env/secret-manager; the worker's evidence is the outcome, not the credential. Tell the operator this split on the FIRST ask, so no round-trips are burned trying to relay the secret.

## VISUAL GATE (operator wall)
1. Order the engineer to start a DETACHED dev server: `nohup env PORT=<assigned> <dev-cmd> > <log> 2>&1 & disown` — it must survive the engineer's session idling. Engineer confirms the port answers before reporting ready.
2. Hand the operator: URL + a ≤6-item verification checklist tied to the block's ACs.
3. WALL. Nothing advances until the operator's verdict. Route it per `skill-operator-comms` (visual-gate template to TG at creation; blocking question if the fleet is otherwise idle).
4. Verdicts: **approved** → PR stage. **Amendments** → relay verbatim to the engineer as an order, loop back to BUILD, re-challenge, re-gate. Record amendment as a dated scope note in MANIFEST.
5. After the block's final merge, order the server shut down and verify the port is free. Stale orphan servers confuse gates — kill before pointing the operator anywhere.

End of line.
