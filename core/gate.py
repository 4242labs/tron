"""core.gate — ADR-0004 rewrite, brick 2: the DONE-ladder TAIL state machine
(`gate.record` -> `close`), the exact path the engine has never reached a
clean close through (0 clean terminal closes in ~50 forensic runs).

Scope (T4 of contracts/rebuild-spec.md, Section 5 of blueprint-contracts.md):
this module does NOT own the whole DONE ladder (local -> merge -> trunk gates
land in a later wave) — it takes a block that has ALREADY passed gate.trunk
(every applicable AC re-run green on trunk) and drives exactly the two
remaining stages:

  record  — order the worker to flip the block doc's Status field to ✅ on
            its OWN branch (TRON reads status, never writes it). Once a new
            commit touches the block file, content-check its OWN diff
            (`gitobs.record_commit_ok` — exactly one file, exactly the
            `**Status:**` field). Anything else is an out-of-gate change
            wearing the record's clothes and returns a distinct
            `("escalate", detail)` outcome — it is never landed. A
            conforming record lands through `core.landing.land_via_grant`
            under a CONTENT-BOUND case-id (`core.landing.paperwork_case_id`,
            the branch's current patch-id embedded) — the Wave-1 confirmed
            root (a name-only case-id colliding across re-authored content)
            is structurally unreachable here. The stage advances to `close`
            ONLY once the ✅ is OBSERVED on trunk by real ancestry
            (`land_via_grant`'s own observe-first contract) — never on the
            worker's say-so.

  close   — order the worker to wrap up (`close.worker`), then HOLD the
            slot: every subsequent call re-checks the replica on REAL git
            (`gitobs.replica_clean` — this block's branch gone, no worktree
            checked out on it) and releases the slot ONLY once that
            predicate is true — never on a confirmation message alone. An
            unclean replica never force-releases here: it holds and re-nudges
            up to `CLOSE_ATTEMPT_CAP` checks, then escalates (never a silent
            trust-release, never an infinite silent hang either).

Substrate calls (learned by READING, never copying, `engine/fsm.py`'s
`_drive_close` / `_confirm_close` / `_drive_record_paperwork_landing` —
re-expressed here without their pacing ladders, wall-kind taxonomy, or
violation-repair machinery, which stay out of scope for this brick). ALL git
observation comes from `core.gitobs` — the single seam, never a raw `git`
call or `import trunk` in this module:
  - `gitobs.record_commit_ok`   — the record-diff content check.
  - `gitobs.replica_clean`      — the close-time cleanliness check.
  - `gitobs.tip_sha` / `gitobs.patch_id` / `gitobs.last_touching_sha` —
    branch-state reads.
  - `core.landing.land_via_grant` / `core.landing.paperwork_case_id` — the
    Wave-1 landing primitive, imported and reused verbatim, never forked.

Duck-typed `eng` contract — everything `core/landing.py` already needs
(`eng.paths`, `eng.dry`, `eng.ctx.grants_dir`, `eng.events`, `eng.log`,
`eng._truth_ref()`, `eng._to_worker`, `eng._grant_ttl()`) PLUS the one
addition this brick needs to free a worker slot:

  `eng._release_worker(wid, reason=str)` — marks `wid`'s slot free in
  whatever worker/slot state `eng` owns (a list, a dict, a roster — this
  module never touches it directly, exactly like `_to_worker` never touches
  the real transport). Called exactly once, only after `gitobs.replica_clean`
  observes a clean replica.

`gate_state` (caller-owned, one per in-flight block, built by `new_state`)
carries the immutable block context (`block`, `block_file`, `branch`, `wid`)
plus this module's own mutable progress fields. `advance(eng, block,
gate_state)` drives it forward by exactly one observable step per call;
call it again (a tick loop, or the rig standing in for one) until the
outcome is `"closed"` or `"escalate"`.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gitobs   # noqa: E402 — core/gitobs.py, the ONE git-observation seam
import landing  # noqa: E402 — core/landing.py, Wave-1's ONE landing primitive

CLOSE_ATTEMPT_CAP = 5   # real-git close checks before an unclean replica escalates

STAGE_RECORD = "record"
STAGE_CLOSE = "close"
STAGE_CLOSED = "closed"
STAGE_ESCALATED = "escalated"


def new_state(eng, block, block_file, branch, wid):
    """Construct the `gate_state` `advance` drives. `block_file` (repo-
    relative) and `branch` are resolved by the CALLER — this module never
    guesses a name it then gates on, same discipline as fsm.py's
    `_block_branch`/`_block_relpath`. Captures the RECORD baseline (the sha
    of whatever commit last touched `block_file` on `branch` BEFORE any
    record activity) so `_advance_record` can tell 'nothing new yet' apart
    from 'a new commit landed, check it' without trusting a message or a
    tip-vs-order-time diff (which breaks the instant a worker acts before
    the engine's next observation)."""
    return {
        "block": block,
        "block_file": block_file,
        "branch": branch,
        "wid": wid,
        "stage": STAGE_RECORD,
        "record_base_sha": gitobs.last_touching_sha(eng.paths["root"], branch, block_file),
        "record_ordered": False,
        "record_case_id": None,
        "record_landed_sha": None,
        "close_ordered": False,
        "close_attempts": 0,
        "escalation": None,
    }


def advance(eng, block, gate_state):
    """Advance `gate_state` by exactly one observable step. Returns
    `(outcome, detail)`. Never advances two STAGES in one call (record's
    own order+check+land sequence is the substance of the one 'record'
    step, not multiple stages); never trusts anything but a real
    git-observed or grant-observed predicate."""
    stage = gate_state.get("stage")
    if stage == STAGE_RECORD:
        return _advance_record(eng, block, gate_state)
    if stage == STAGE_CLOSE:
        return _advance_close(eng, block, gate_state)
    if stage == STAGE_CLOSED:
        return "closed", "already closed"
    if stage == STAGE_ESCALATED:
        return "escalate", gate_state.get("escalation") or "already escalated"
    raise ValueError(f"gate[{block}]: unknown stage {stage!r}")


def _escalate(gate_state, detail):
    gate_state["stage"] = STAGE_ESCALATED
    gate_state["escalation"] = detail
    return "escalate", detail


def _advance_record(eng, block, gate_state):
    """One record-stage step: order once (side effect, idempotent), then
    every call re-checks the branch for a NEW commit touching the block
    file. Nothing new yet -> wait. Something new but non-conforming ->
    escalate, never land. Conforming -> land via the Wave-1 primitive under
    a content-bound case-id; advance to `close` only once land_via_grant
    itself reports `"landed"` (real ancestry observed)."""
    branch = gate_state["branch"]
    block_file = gate_state["block_file"]
    wid = gate_state.get("wid")
    truth_ref = eng._truth_ref()

    if not gate_state["record_ordered"]:
        if wid and not eng.dry:
            eng._to_worker(
                wid,
                f"[TRON]  {wid} — gate.record: commit the ✅ Status flip on "
                f"{branch} now — exactly one file ({block_file}), exactly the "
                f"`**Status:**` field. Nothing else in that commit.",
                "gate.record")
        gate_state["record_ordered"] = True
        eng.log("flow", f"gate[{block}] record: ordered ✅ status-flip on {branch}")

    cur_sha = gitobs.last_touching_sha(eng.paths["root"], branch, block_file)
    if not cur_sha or cur_sha == gate_state["record_base_sha"]:
        return "record_waiting", f"no record commit on {branch} yet"

    ok, detail = gitobs.record_commit_ok(eng.paths["root"], block_file, eng.dry,
                                         truth_ref=branch)
    if not ok:
        return _escalate(gate_state,
                         f"record commit on {branch} is out-of-gate: {detail}")

    patch_id = gitobs.patch_id(eng.paths["root"], branch, truth_ref, eng.dry)
    case_id = gate_state.get("record_case_id") or landing.paperwork_case_id(
        "record", branch, patch_id)
    gate_state["record_case_id"] = case_id

    outcome = landing.land_via_grant(eng, case_id, block, branch, wid,
                                     "gate.record", "gate-record")
    if outcome == "landed":
        gate_state["record_landed_sha"] = gitobs.tip_sha(eng.paths["root"], branch, eng.dry)
        gate_state["stage"] = STAGE_CLOSE
        eng.log("flow", f"gate[{block}] record: ✅ observed on trunk "
                        f"({str(gate_state['record_landed_sha'])[:8]}) -> close")
        return "record_landed", f"✅ observed on trunk @ {gate_state['record_landed_sha']}"
    if outcome == "pending":
        return "record_pending", f"grant live for {case_id}; awaiting land.sh"
    return "record_fail_closed", f"unresolvable patch-id for {branch} (case {case_id})"


def _advance_close(eng, block, gate_state):
    """One close-stage step: order once (side effect, idempotent), then
    every call re-checks the REAL replica. Releasing the slot is gated on
    `gitobs.replica_clean` alone, never on a worker's confirmation message —
    belt-and-suspenders: even an unsolicited/early confirm can't force a
    release the git state doesn't back."""
    branch = gate_state["branch"]
    wid = gate_state.get("wid")

    if not gate_state["close_ordered"]:
        if wid and not eng.dry:
            eng._to_worker(
                wid,
                f"[TRON]  {wid} — ✅ is on trunk. Wrap up: delete {branch}, "
                f"remove any worktree on it, sync local, then confirm clean.",
                "close.worker")
        gate_state["close_ordered"] = True
        eng.log("flow", f"gate[{block}] -> close (slot held)")
        return "close_ordered", f"ordered {wid or '(no worker)'} to close out"

    main_branch = eng.paths.get("main_branch", "main")
    clean, detail = gitobs.replica_clean(eng.paths["root"], branch, main_branch, eng.dry)
    if not clean:
        gate_state["close_attempts"] += 1
        if gate_state["close_attempts"] >= CLOSE_ATTEMPT_CAP:
            return _escalate(gate_state,
                             f"replica not clean after {gate_state['close_attempts']} "
                             f"checks: {detail}")
        return "close_holding", detail or "replica not yet clean"

    if wid:
        eng._release_worker(wid, reason="close-confirmed")
    gate_state["stage"] = STAGE_CLOSED
    eng.log("flow", f"gate[{block}] close confirmed -> worker released")
    return "closed", f"replica clean on {branch}; {wid or '(no worker)'} released"
