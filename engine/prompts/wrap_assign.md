Your merge landed and the engine re-validated the suite ON the trunk —
GREEN. The window is still yours: wrap the block before your arena
retires. In this working copy, on branch {branch}:

1. Update project documentation where THIS block requires it (README,
   usage docs). Never touch pipeline.md — it is engine-owned.
2. Write your session log to `logs/{name}-session.md`: what you built and
   why, rulings you received, dead ends, anything the next engineer needs.
3. Commit everything. Leave the working tree CLEAN and synced — nothing
   uncommitted survives your seat.

The engine will verify the log exists, the tree is clean, and land your
wrap commits the same mechanical way. When all three are true, reply
exactly:
>>WRAPPED branch={branch} summary=<docs touched + one-line log gist>
