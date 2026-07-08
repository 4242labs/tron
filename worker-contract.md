# The worker contract — how you and the Orchestrator work together

CANON, copied verbatim at seed. This is the INTERFACE between you (a worker) and the
Orchestrator (the supervising process). It is not your persona and not your project's
method — your project's own docs govern HOW you build; this governs how we talk and hand
off. Read it fully at spawn; the Orchestrator's orders assume you have.

## 1. The channel
Every reply to the Orchestrator goes through the report command your spawn message named
(`report.sh <your worker id> "<message>"`). A reply that is not on the channel does not
exist to the Orchestrator — turn output is never read.

## 2. One message, one act — tagged
A gate reply carries its verb as data, so nothing is guessed:
`report.sh <id> --tag <verb> [--block <id>] [--branch <name>] [--kind <scope|blueprint|design>] "<message>"`
Verbs: `done` · `recorded` · `wall` · `review-done` · `clean`.
One VERB per message — never two. Modifiers ride freely on any message: `--branch <name>`
declares a branch, `--block <id>` names your block; a done-report carrying `--branch` is
the normal way to declare-and-report in one line. `--kind` is only meaningful on a
`--tag wall` — see §6. Flags always come BEFORE the message, never after — a trailing
flag on what you meant as plain text is read as a real one.

## 3. The DONE ladder
You never decide when work is finished — you report, the Orchestrator orders each step,
one at a time. You own the trunk landing; the Orchestrator never merges, rebases, or lands
anything — code or paperwork:
- `done <block> — local:` + per-criterion evidence (commands + results, never "it passes")
- On order, rebase your own branch onto current trunk in your own worktree and re-validate
  — do it and report, never wall on it. This is not a merge; you own your branch's history
  throughout
- Once your merge is authorized, the Orchestrator mints a one-time, block-scoped grant
  under a case id — it never touches git itself to do this. Run
  `meta/scripts/land.sh <case-id>` yourself: it is the ONLY sanctioned way to advance
  trunk. It validates your grant, fast-forwards trunk to your tip, and consumes the grant.
  If it refuses (expired grant, no fast-forward, changed content), fix what it tells you —
  a failed land is never a wall on its own; rebase and retry, or report what it printed if
  you're stuck
- `done <block> — trunk:` + re-validated evidence on trunk, after your own `land.sh` run
- `recorded <block>` after you land the gate-ordered ✅ status commit yourself — same
  mechanism: commit it on your branch, obtain the grant, run `land.sh`, then report
- `clean <block>:` + what you verified at close, including removing your worktree and
  deleting your own branch — branch cleanup is your close ritual, not the Orchestrator's
Reviewers: your coverage confirmation opens `review done <type>:`.
A bare "done" moves nothing. Reply to the step you were ordered, in its prescribed opening.
Finishing a step and WAITING for the next order is not a pause — report `done` and stand
by; signal a pause only when you cannot proceed without an answer. If the Orchestrator
repeats an order, it has not SEEN what it needs — re-send your report in the prescribed
opening; do not redo the work. A repeat is the SAME step re-asked, nothing else: an order
naming an act you have not yet answered (the record commit, the close-out) is always new
work — do it, never re-send a previous report in its place. Re-send that step's report
ONCE; if the repeat continues, stand by — do not answer every copy.

## 4. Branch duty
Name the branch you build on the moment you create it (`--branch <name>`), BEFORE any
done-report. The Orchestrator gates on the branch it knows about; an undeclared branch is
invisible and will stall your own gate. While your merge waits on approval, do not commit
to that branch — a moved tip voids the approval and re-parks it (a grant is bound to the
branch's diff at mint time; a pure rebase keeps it valid, but new content invalidates it).
The one exception is the order-authorized rebase (§3): that rebase is gate-authorized and
is not a merge — the Orchestrator observes the rebased tip carries the same content, so it
never voids the approval.

## 5. Paperwork
Whatever paperwork your project's method produces (session logs, doc sync, archival, …) —
commit it on your branch, obtain the grant, and land it yourself via `land.sh` exactly like
code (§3) — then remove your worktree, sync local, and delete your own branch. The
Orchestrator never lands anything on trunk, code or paperwork; it only mints the grant.
Code is never paperwork: unmerged code at close is a wall to report, not a cleanup.

## 6. Walls
A wall is anything you cannot clear yourself after consulting your peers: an operator-only
task, an external blocker, a true impasse. Report it (`--tag wall`, say exactly what blocks
you) and stop — never work around it, never guess. The Orchestrator routes it; the operator
decides.
If your either/or is a question about the BLOCK SPEC itself (scope, an acceptance-criteria
interpretation, the blueprint, a design call) — something the architect owns, not the
operator — declare it: `--tag wall --kind scope` (or `blueprint` / `design`). That routes
you to the architect first, who answers directly; a wall with no `--kind`, or one that is
genuinely the operator's call (policy, an external blocker), pages the operator as before.
