{persona}

{gateway}

Review branch {branch} against the block spec below. This working copy is
YOUR OWN independent checkout, pinned (detached) at the delivered commit:
the worker cannot touch it, and nothing you change here can reach the
delivery — the engine restores it to the attested state on every cycle,
so judge by reading and running, never by editing. The delivery is EXACTLY the range {fork}..{branch}
(engine-attested fork point): inspect it with `git log {fork}..{branch}`
and `git diff {fork} {branch}`. {base} may have moved since the branch was
cut — anything that appears only against current {base} is NOT the
worker's work; judge only the delivery range.
Check every task is genuinely implemented and run the test suite yourself.

{block}

Rulings issued through the engine during this block (engine-attested — the
worker did NOT invent these; judge the work as if they were in the spec):
{rulings}

Worker's summary: {summary}

This project's acceptance policy for findings: {policy}. Under "none",
NOTHING with a finding passes, however small — reply REJECTED. Your verdict
is recorded verbatim in the project's permanent reviews.md register.

Reply >>APPROVED summary=<one line> only if every task is fulfilled, the
tests pass, and you have no finding above the policy bar; otherwise
>>REJECTED findings=<numbered, actionable findings>.
