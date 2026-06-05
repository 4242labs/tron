# pipeline.md — Internal pipeline (runtime; gitignored)

The status + sequence record TRON keeps when the host has no pipeline doc of its own. Seeded by interview (see `tron-seed.md` Step 5). TRON updates statuses as blocks progress; it is authoritative during a session. Joins to specs by ID.

Status ∈ `pending` · `cleared` · `in-progress` · `blocked` · `done` · `abandoned`.
(`pending` = needs architect clearing · `cleared` = ready to dispatch, the only dispatchable status · `blocked` = walled, awaiting operator · `abandoned` = operator-dropped.)

| Order | ID | Owner | Status | Notes |
|:------|:---|:------|:-------|:------|
|       |    |       |        |       |
