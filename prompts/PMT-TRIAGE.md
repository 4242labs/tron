[TRON]  Architect — I can't place this. Sort it.

  {detail}

Pick exactly one:
- Answer it now — you can resolve it directly. Say how, in your note.
- Upcoming work — scope it forward: author or queue the block, then report it.
- The operator's call — a real decision or an external blocker only you can't clear.

Reply with the verdict wire, not plain text — this is the only reply that reaches me:

  bash {report} {worker_id} --tag verdict --triage-id {triage_id} --verdict <scope_forward|answer|operator> "<note>"

`<note>` is your reasoning (or, for `answer`, the answer itself). `{triage_id}` above is
this triage's own id — copy it verbatim into `--triage-id`; it is never the case id.
