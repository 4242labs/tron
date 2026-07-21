# Crash-resume validation — kill the engine mid-flight, restart, reconverge

Deliberate end-to-end validation of the paper's crash-recovery claim (§8:
"a killed and restarted engine reconverges to trunk with nothing lost,
doubled, or dropped"). Prior to this the property was unit-tested
(`pipeline`/`gate` selftests) and exercised only *negatively* in the
campaign (crashes that left stale-arena poison → the crash-safe sweep fix
`42398b7`). These are the first deliberate *positive* live trials.

Method: run the real engine on a seeded project in an isolated worktree,
`kill -9` the whole engine session mid-flight, then restart the engine on
the SAME project and observe boot recovery + reconvergence. Pin v0.0.30.
Only fresh run files are measured (tracked history baselined).

## Trial 1 — PROJECT-01 (single block), crash mid-build

Killed while block-01 was `doing` (0 blocks landed). On restart:
- `recover doing_requeued block-01 → orphan/feat/block-01` — the unverified
  in-flight branch preserved as an orphan (nothing lost);
- `recover arena_swept block-01`;
- block-01 rebuilt, landed, `run_done`; product suite green (11 tests).

Validates the **interrupted-build** path: work in flight at the crash is
preserved as an orphan and cleanly re-queued.

## Trial 2 — PROJECT-02 (6 blocks, diamond), crash after 3 landed

Killed with blocks 01/02/03 `done` and 04/05 `doing` (mid-build), 06 `todo`.
On restart:
- **Preservation:** every pre-crash land commit for 01/02/03 remained an
  ancestor of `main` after resume — the landed blocks were NOT rebuilt
  (verified by `git merge-base --is-ancestor`).
- **Recovery:** `doing_requeued block-04 → orphan/feat/block-04` and
  `doing_requeued block-05 → orphan/feat/block-05`; both arenas swept; the
  three `done` blocks were NOT requeued.
- **Reconvergence:** run-2 delivered exactly the 3 remaining blocks
  (`run_done delivered=3`), pipeline reached 6/6 `done`, product suite green
  (48 tests).

Validates the **landed-preservation + interrupted-recovery** path together:
committed work survives the crash untouched, in-flight work is orphaned and
re-queued, and the restarted engine reconverges to full delivery with
nothing lost, doubled, or dropped.

## Trial 3 — PROJECT-03 (8 blocks, depth-5 graph), crash after 3 landed

Killed with blocks 01/02/03 `done`, 04/06 `doing` (mid-build), 05/07/08 `todo`
— a deeper graph than Trial 2, so recovery had to re-queue two independent
in-flight branches while preserving three landed ones. On restart:
- **Preservation:** all six pre-crash `land:` commits for 01/02/03 stayed
  ancestors of `main` (`merge-base --is-ancestor` OK on every one) — no landed
  block rebuilt.
- **Recovery:** `doing_requeued block-04 → orphan/feat/block-04` and
  `doing_requeued block-06 → orphan/feat/block-06`; both arenas swept; the
  three `done` blocks NOT requeued.
- **Reconvergence:** run-2 delivered the 5 remaining blocks
  (`run_done delivered=5`), pipeline reached 8/8 `done`, product suite green
  (71 tests).

Extends Trial 2 to a **deeper dependency graph with two simultaneous
in-flight orphans**, both cleanly re-queued.

## Trial 4 — PROJECT-02, crash with two workers dispatched in parallel

The parallel-orphan path: killed the moment **two workers were in flight at
once** (dispatches=3, blocks 02+03 both `doing`) with only block-01 landed —
targeting the concurrency corner Trials 1–3 don't hit (they orphan blocks
that were dispatched sequentially). On restart:
- **Preservation:** block-01's land commits stayed ancestors of `main`.
- **Recovery:** `doing_requeued block-02 → orphan/feat/block-02` and
  `doing_requeued block-03 → orphan/feat/block-03` — **both** parallel
  in-flight branches orphaned, both arenas swept, no double-count.
- **Reconvergence:** run-2 delivered 5 remaining blocks
  (`run_done delivered=5`), pipeline reached 6/6 `done`, product suite green
  (48 tests).

Validates that **concurrent** in-flight work (not just sequential) is
orphaned and re-queued correctly — each parallel arena swept independently,
nothing double-landed.

## Verdict

Crash-resume **VALIDATED** across four live trials spanning the full matrix:
single-block interrupted build (T1), multi-block post-landing crash (T2),
deeper depth-5 graph with two sequential orphans (T3), and **concurrent
two-worker parallel orphan** (T4). In every case committed work survived the
`kill -9` untouched, in-flight work — sequential or parallel — was orphaned
and re-queued, and the restarted engine reconverged to full delivery with
nothing lost, doubled, or dropped. The paper's §8 crash-recovery claim is now
backed by deliberate live trials, not just unit tests and negative campaign
evidence.
