# Principles — conduct for every agent

1. Work only inside your own working copy; the trunk is read-only to you.
2. Test-first: behavior lands with its tests in the same delivery.
3. Small commits with honest messages; nothing uncommitted survives a seat.
4. When the spec is ambiguous, ASK — never invent a policy silently.
5. Judges verify by reading and running, never by editing.
6. Read `playbook.md` before building; when you learn something durable
   about this project's infrastructure, update it in your delivery.
7. Build to the canonical signatures in `context.md`; a module your block
   depends on is already landed on the trunk — import it, do not reinvent it.
