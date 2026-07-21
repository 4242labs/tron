Your delivery on {branch} is APPROVED. The engine now opens YOUR merge
window — no other landing runs until yours closes. The merge is your
responsibility, not the engine's.

In this working copy, on {branch}:
1. `git merge {base}` — bring the current trunk into your branch. Resolve
   every conflict yourself, keeping the intent of BOTH sides: work already
   landed on {base} is law, and so is your reviewed delivery. If git says
   "Already up to date", there is nothing to resolve.
2. Re-validate everything on the merged state: run `{tests}` and make the
   whole suite green — fix whatever the merge broke.
3. Commit it all on {branch} and leave the working copy clean (git status
   clean, nothing unmerged).

Then reply:
>>MERGED branch={branch} summary=<one line: what was merged/resolved>
The engine verifies your branch contains {base}, performs the landing, and
re-validates the suite on the trunk itself. If a conflict needs a decision
that is not yours to make, stop and ask: >>QUESTION text=<...>
