# The worker contract — how you and TRON work together

CANON, copied verbatim at seed. This is the INTERFACE between you (a worker) and TRON (the
supervising process). It is not your persona and not your project's method — your project's
own docs govern HOW you build; this governs how we talk and hand off. Read it fully at
spawn; TRON's orders assume you have.

## 1. The channel
Every reply to TRON goes through the report command your spawn message named
(`report.sh <your worker id> "<message>"`). A reply that is not on the channel does not
exist to TRON — turn output is never read.

## 2. One message, one act — tagged
A gate reply carries its verb as data, so nothing is guessed:
`report.sh <id> --tag <verb> [--block <id>] [--branch <name>] "<message>"`
Verbs: `done` · `recorded` · `wall` · `review-done` · `clean`.
One VERB per message — never two. Modifiers ride freely on any message: `--branch <name>`
declares a branch, `--block <id>` names your block; a done-report carrying `--branch` is
the normal way to declare-and-report in one line.

## 3. The DONE ladder
You never decide when work is finished — you report, TRON orders each step, one at a time:
- `done <block> — local:` + per-criterion evidence (commands + results, never "it passes")
- TRON owns the trunk merge; you never merge code. Besides the record commit, the one
  trunk-adjacent act a gate order can authorize is a REBASE of your own branch in your own
  worktree — a rebase on order is not a merge; do it and report, never wall on it
- `done <block> — trunk:` + re-validated evidence on trunk
- `recorded <block>` after you land the gate-ordered ✅ status commit (one file, one field)
- `clean <block>:` + what you verified at close
Reviewers: your coverage confirmation opens `review done <type>:`.
A bare "done" moves nothing. Reply to the step you were ordered, in its prescribed opening.
Finishing a step and WAITING for the next order is not a pause — report `done` and stand
by; signal a pause only when you cannot proceed without an answer. If TRON repeats an
order, it has not SEEN what it needs — re-send your report in the prescribed opening;
do not redo the work. A repeat is the SAME step re-asked, nothing else: an order naming
an act you have not yet answered (the record commit, the close-out) is always new work —
do it, never re-send a previous report in its place. Re-send that step's report ONCE;
if the repeat continues, stand by — do not answer every copy.

## 4. Branch duty
Name the branch you build on the moment you create it (`--branch <name>`), BEFORE any
done-report. TRON gates on the branch it knows about; an undeclared branch is invisible and
will stall your own gate. While your merge waits on approval, do not commit to that branch —
a moved tip voids the approval and re-parks it. The one exception is a rebase TRON itself
orders (§3): that rebase is gate-authorized and is not a merge — TRON verifies the rebased
tip carries the same content, so it never voids the approval.

## 5. Paperwork
Whatever paperwork your project's method produces (session logs, doc sync, archival, …) —
commit it on your branch, remove your worktree, sync local, and LEAVE THE BRANCH IN PLACE. TRON lands paperwork on trunk itself (content-checked)
and removes the branch. You merge nothing at close. Code is never paperwork: unmerged code
at close is a wall to report, not a cleanup.

## 6. Walls
A wall is anything you cannot clear yourself after consulting your peers: an operator-only
task, an external blocker, a true impasse. Report it (`--tag wall`, say exactly what blocks
you) and stop — never work around it, never guess. TRON routes it; the operator decides.
