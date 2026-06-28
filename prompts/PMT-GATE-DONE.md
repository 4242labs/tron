[TRON]  {worker_id}, {block} isn't done till the evidence says so.

  {detail}

The gate is evidence, not assertion. I advance one step at a time:
- **Validate-local** — show me the block's acceptance suite ran clean locally. Not "it passes" — the evidence.
- **Authorize-push** — only once local validation holds.
- **PR → trunk** — the PR is in and its checks are green on trunk.
- **Deploy** — only if the block declares it; then the deploy check is clean too.

Answer the step I'm asking about. A bare "done" doesn't move the gate.
