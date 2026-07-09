[TRON]  {worker_id} — you're done here. Close it out.

Run your session-end skill: wrap up, leave nothing loose — worktree removed, local synced. Whatever paperwork your close-out produces — session logs, doc sync, the block archival — commit it on your branch, then land it on trunk yourself via the grant + `meta/scripts/land.sh` (paperwork lands the same way as code — no fast lane; I never land or merge, that's yours), and remove your own worktree + branch once it's on trunk. Code is not paperwork: unmerged code at close is a wall to report, never a cleanup.

Tell me when you're wrapped — open that reply `clean <your block id>:` then what you verified (paperwork committed on your branch, worktree gone, local synced) — then stand down. I close your process only once your paperwork lands and the replica reads clean.
