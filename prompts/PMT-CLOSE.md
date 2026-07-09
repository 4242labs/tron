[TRON]  {worker_id} — you're done here. Close it out.

Run your session-end skill: wrap up, leave nothing loose. Whatever paperwork your close-out produces — session logs, doc sync, the block archival — commit it on your branch. Keep your worktree for now — you land from it. Code is not paperwork: unmerged code at close is a wall to report, never a cleanup.

Then open a reply `clean <your block id>:` — paperwork committed on your branch, ready to land. That reply is the signal that mints your land grant: I mint it and order the land the moment I read your `clean`. Never wait on a pre-existing grant and never page for one — your `clean` is what creates it. Once it's minted, run `meta/scripts/land.sh <case>` yourself (paperwork lands the same way as code — no fast lane; I never land or merge, that's yours), then remove your worktree + branch and sync local.

Reply `clean <your block id>:` once more when it's on trunk and your replica reads clean — worktree gone, local synced — then stand down. I close your process only once your paperwork lands and the replica reads clean.
