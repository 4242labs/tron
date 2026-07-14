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
`report.sh <id> --tag <verb> [--block <id>] [--branch <name>] "<message>"`
Verbs: `done` · `recorded` · `wall` · `review-done` · `clean` · `flag`.
The architect additionally answers a TRIAGE order with `verdict` (§7) — no other role sends it.
One VERB per message — never two. Modifiers ride freely on any message: `--branch <name>`
declares a branch, `--block <id>` names your block; a done-report carrying `--branch` is
the normal way to declare-and-report in one line. Flags always come BEFORE the message,
never after — a trailing flag on what you meant as plain text is read as a real one.

**Reporting is structured-only.** The word on your report IS the classification — there is
no free-text fallback any more. A message with neither a recognized `--tag` nor a `--branch`
is refused: `report.sh` itself exits nonzero and prints the legal `--tag` set (run
`report.sh <id> --schema` any time to see it) — fix the flag and resend, in the same turn,
before doing anything else. A refused report is never silently dropped: the Orchestrator
records the full attempt and, if it stays unresolved, opens a case for it — but the fast
path is simply sending a legal tag the first time.

**Flag for visibility, when nothing needs a verdict.** `--tag flag` is for something worth
surfacing — a heads-up, a minor oddity, context for later — that is NOT a wall and needs NO
reply: it is never paged, never blocks you, never blocks anything else. Batches of it reach
the architect together, not one interruption per flag. Use `wall` (§6) for anything that
actually stops you; use `flag` for everything else worth a mention.

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
A wall is anything you cannot clear yourself after consulting your peers: a question about
the block spec, an operator-only task, an external blocker, a true impasse. Report it
(`--tag wall`, say exactly what blocks you) and stop — never work around it, never guess.
Every wall routes to the architect first, who either answers it directly, scopes it forward
as upcoming work, or — its own call, never yours to flag — raises it to the operator. You
never need to say which of those it is; just report the wall.

## 7. The architect's verdict wire
This section is for the architect role only. A TRIAGE order names a `triage_id` and asks for
a verdict; answer with `report.sh architect --tag verdict --triage-id <id> --verdict
<scope_forward|answer|operator> "<note>"` — `scope_forward` when it's upcoming work to scope
and land, `answer` when you can resolve it directly (say how, in `<note>`), `operator` when
it's genuinely the operator's call. Always reply with the verdict wire, never a plain-text
answer alone — a triage order that goes unanswered eventually pages the operator on its own,
never guessing at your intent.
