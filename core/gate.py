"""core.gate — ADR-0004 rewrite, brick 3: the FULL DONE-ladder state machine,
`gate.local -> gate.merge -> gate.trunk -> gate.record -> close`.

Brick 2 (below, unmodified in substance) covered only the TAIL (`gate.record`
-> `close`), the exact path the engine has never reached a clean close
through (0 clean terminal closes in ~50 forensic runs) — it took a block that
had ALREADY passed gate.trunk (every applicable AC re-run green on trunk) as
a given. Brick 3 adds the HEAD three stages so a block can be driven through
the ENTIRE ladder from scratch, on real git, via `new_state_full` (below);
`new_state` (unchanged) still starts a state directly at `gate.record`, so
existing tail-only callers (`core/gate_rig.py`) keep working unmodified.

Local mode (no remote — blueprint-contracts.md §5's "one gated merge"): with
no PR to wait on, the single gated merge IS the worker landing its feature
branch onto trunk via `meta/scripts/land.sh` under a grant — the SAME
content-bound landing primitive `core/landing.py` already provides for the
record stage, reused verbatim for the code merge too (a different, freshly
content-bound case-id: `role="merge"` vs `role="record"`, `landing.
paperwork_case_id`'s own branch+patch-id embedding making the two
structurally distinct, never name-only).

  gate.local — the worker reports it ran the block's acceptance suite
            locally. The gate judges the report ON EVIDENCE, never a bare
            "done": a well-formed `{"verdict": "pass", "evidence": <str>}`
            dict (passed into `advance`'s `local_report` kwarg — the ONE
            piece of the DONE ladder that isn't purely git-observable, by
            construction: local validation happens on the worker's own
            machine, before anything has a git artifact to observe) advances
            to `gate.merge`; a bare/absent/malformed report holds at
            `gate.local` and is asked again — never advances, never
            escalates (a worker still validating locally is not a
            violation).

  gate.merge — land the worker's OWN feature branch onto trunk via
            `core.landing.land_via_grant`, under a content-bound case-id
            (`landing.paperwork_case_id("merge", branch, patch_id)` — never
            name-only, so a same-named branch re-authored with new content
            after a prior merge attempt can never short-circuit on a stale
            receipt, the exact Wave-1 confirmed root). Advances to
            `gate.trunk` only once the merge is OBSERVED on trunk by real
            ancestry (`land_via_grant`'s own observe-first contract) —
            captures the merged sha for the next stage.

  gate.trunk — re-validate the block's applicable ACs ON TRUNK, at the
            merged sha, by running the project's declared test command
            (`eng.paths["test_command"]`/`["test_env"]`/`["ci_check_name"]`,
            the same duck-typed shape `engine/fsm.py`'s own
            `_test_stage_verdict` reads) in a clean detached worktree
            (`core.gitobs.validate_trunk`, delegating to
            `engine/trunk.py`'s existing trunk-validation — the single git/
            test observation seam, never a raw subprocess in this module).
            `"pass"` advances to `gate.record` (brick 2's tail, below);
            `"fail"` (a genuinely observed red) HOLDS at `gate.trunk` —
            never advances, never silently escalates either, so a worker
            that fixes the code and re-merges gets re-validated on the new
            sha; `"unconfirmed"` (nothing trustworthy could be read) holds
            the same way. Verdicts are cached per merged-sha (`trunk_verdict
            _sha`) so a re-tick before the sha changes doesn't re-run the
            suite.

Scope of the TAIL (T4 of contracts/rebuild-spec.md, Section 5 of
blueprint-contracts.md): a block that has ALREADY passed gate.trunk (every
applicable AC re-run green on trunk) drives exactly the two remaining
stages:

  record  — order the worker to flip the block doc's Status field to ✅ (and
            add the `**Completed:**` date the session-end skill §6 prescribes)
            on its OWN branch (TRON reads status, never writes it). Once a new
            commit touches the block file, content-check its OWN diff
            (`gitobs.record_commit_ok`). Conforming = the block doc's Status/
            Completed flip, ALONE or bundled with exactly the §6 close-out
            paperwork the frozen skill prescribes as one commit — the block
            doc's rename to `blocks/archive/` and the worker's OWN-row
            `pipeline.md` edit (line-scoped to this block id), nothing else.
            The engine conforms to the frozen skill's bundled close-out rather
            than forcing a split (ADR-0005 R5). Any OTHER file/line (code, prose,
            another block's row) is an out-of-gate change wearing the record's
            clothes and returns a distinct `("escalate", detail)` outcome — never
            landed. Whatever the worker bundled here, `close` then finds the
            close-out already on trunk (idempotent) and just releases the slot. A
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
            unclean replica never force-releases here: this module holds
            (`close_holding`) FOREVER on its own — it never counts attempts,
            never caps itself. Capping is `core/sentry.py`'s job now, the ONE
            pacing ladder wrapping every stage of this gate (never a
            silent trust-release, never an infinite silent hang either —
            sentry nudges then escalates, off the SAME law every other
            stage's idle time is judged by).

Substrate calls (learned by READING, never copying, `engine/fsm.py`'s
`_drive_gate` / `_test_stage_verdict` / `_drive_close` / `_confirm_close` /
`_drive_record_paperwork_landing` — re-expressed here without their wall-kind
taxonomy, role/PR machinery, or violation-repair machinery, which stay out of
scope for this module; the ONE piece of `fsm.py`'s pacing ladder this stack
DOES carry forward — re-expressed clean, never copied — is `core/sentry.py`,
wave 7, which wraps every stage of THIS module from the outside; this module
itself stays a pure predicate-driven state machine, never self-capping). ALL
git/test
observation comes from `core.gitobs` — the single seam, never a raw `git`
call or `import trunk` in this module:
  - `gitobs.validate_trunk`     — the gate.trunk declared-test verdict.
  - `gitobs.record_commit_ok`   — the record-diff content check.
  - `gitobs.replica_clean`      — the close-time cleanliness check.
  - `gitobs.tip_sha` / `gitobs.patch_id` / `gitobs.last_touching_sha` —
    branch-state reads.
  - `core.landing.land_via_grant` / `core.landing.paperwork_case_id` — the
    Wave-1 landing primitive, imported and reused verbatim, never forked,
    for BOTH the code merge (`gate.merge`) and the paperwork record
    (`gate.record`) — two different, independently content-bound case-ids
    (`role="merge"` vs `role="record"`), never the same landing call reused
    for two different pieces of content.

Duck-typed `eng` contract — everything `core/landing.py` already needs
(`eng.paths`, `eng.dry`, `eng.ctx.grants_dir`, `eng.events`, `eng.log`,
`eng._truth_ref()`, `eng._to_worker`, `eng._grant_ttl()`) PLUS the additions
this module needs:

  `eng._release_worker(wid, reason=str)` — marks `wid`'s slot free in
  whatever worker/slot state `eng` owns (a list, a dict, a roster — this
  module never touches it directly, exactly like `_to_worker` never touches
  the real transport). Called exactly once, only after `gitobs.replica_clean`
  observes a clean replica.

  `eng.paths.get("test_command")` / `.get("test_env")` /
  `.get("ci_check_name")` — the project's declared trunk-validation command
  (project.yaml `test:`), the exact shape `engine/fsm.py`'s own
  `_test_stage_verdict` already reads off `eng.paths`; `gate.trunk` reads
  these, never a value the block/worker supplies.

  `eng.ctx.scratch_dir` — the scratch-worktree-admin root
  (`meta/agents/tron/scratch/`) `gitobs.validate_trunk`'s clean detached
  checkout is carved under (mirrors `engine/ctx.py`'s own `scratch_dir`
  property).

`gate_state` (caller-owned, one per in-flight block) carries the immutable
block context (`block`, `block_file`, `branch`, `wid`) plus this module's
own mutable progress fields. Two constructors:
  - `new_state(...)` — unchanged, starts a state directly at `gate.record`
    (the tail-only entry point `core/gate_rig.py` still drives).
  - `new_state_full(...)` — starts a state at `gate.local`, the FULL ladder.

`advance(eng, block, gate_state, local_report=None)` drives a state forward
by exactly one observable step per call (`local_report` is read only while
`gate_state["stage"] == STAGE_LOCAL`, the one stage whose predicate isn't
purely git-observable); call it again (a tick loop, or a rig standing in for
one) until the outcome is `"closed"` or `"escalate"`.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gitobs   # noqa: E402 — core/gitobs.py, the ONE git-observation seam
import landing  # noqa: E402 — core/landing.py, Wave-1's ONE landing primitive

# NOTE (wave 7 consolidation): there is deliberately NO per-stage attempt cap
# in this module — not here, not anywhere below. This gate is a PURE
# predicate-driven state machine: every stage either advances on an observed
# predicate or HOLDS, forever, on its own. Capping (nudge -> escalate, off
# ONE shared wall-clock-agnostic law, identical for every stage) lives
# exclusively in `core/sentry.py`, which wraps this module from the outside
# (`core/tick.py` calls `sentry.pace` right after driving gates, before
# persist). The close stage used to be the one exception (`CLOSE_ATTEMPT_CAP`,
# a private per-stage counter) — removed; `_advance_close` below now returns
# `close_holding` unconditionally while the replica isn't clean, exactly like
# every other holding outcome in this module.

STAGE_LOCAL = "local"
STAGE_MERGE = "merge"
STAGE_TRUNK = "trunk"
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
        "close_case_id": None,
        "escalation": None,
    }


def new_state_full(eng, block, block_file, branch, wid):
    """Construct a `gate_state` that starts at `gate.local` — the FULL
    ladder (`gate.local -> gate.merge -> gate.trunk -> gate.record ->
    close`). Built on top of `new_state` (unchanged) so the tail's own
    baseline capture (`record_base_sha`, resolved the SAME way, at
    construction time — the record stage's baseline is a property of
    `block_file` on `branch`, independent of when the earlier stages run)
    stays exactly as trustworthy for a full-ladder state as it already is
    for a tail-only one."""
    st = new_state(eng, block, block_file, branch, wid)
    st["stage"] = STAGE_LOCAL
    st["local_ordered"] = False
    st["local_report"] = None
    st["merge_ordered"] = False
    st["merge_case_id"] = None
    st["merged_sha"] = None
    st["trunk_verdict_sha"] = None
    st["trunk_verdict"] = None
    st["trunk_verdict_detail"] = None
    return st


def advance(eng, block, gate_state, local_report=None):
    """Advance `gate_state` by exactly one observable step. Returns
    `(outcome, detail)`. Never advances two STAGES in one call (record's
    own order+check+land sequence is the substance of the one 'record'
    step, not multiple stages); never trusts anything but a real
    git-observed or grant-observed predicate — `local_report` is the ONE
    exception (gate.local's predicate is inherently not git-observable) and
    is only ever consulted while `gate_state["stage"] == STAGE_LOCAL`."""
    stage = gate_state.get("stage")
    if stage == STAGE_LOCAL:
        return _advance_local(eng, block, gate_state, local_report)
    if stage == STAGE_MERGE:
        return _advance_merge(eng, block, gate_state)
    if stage == STAGE_TRUNK:
        return _advance_trunk(eng, block, gate_state)
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


def _merge_still_landed(eng, gate_state):
    """ADR-0009 §5 (H2 — the engine's own false-advance root, Defect 3):
    'a block occupies `record` only while its merged commit is currently a
    trunk ancestor.' Re-checked at EACH `gate.trunk`/`gate.record` call
    against a FRESHLY-read `eng._truth_ref()` — never a value cached at
    merge time. `land_via_grant`'s receipt short-circuit can otherwise
    return 'landed' for a `merged_sha` that trunk churn (a force-push/
    rebase after `gate.merge` genuinely observed it) has since dropped —
    the engine would then advance `gate.trunk`/`gate.record` on content
    current ancestry no longer corroborates: a real false-green, not a
    dependent of Defect 1. Extends ADR-0008's `stale_landing_wall`
    machinery (the ANALOGOUS already-landed-wall dual) to this
    not-yet-landed dual: illegal-state fix — a churn-invalidated
    `merged_sha` re-drives merge, never reads as landed.

    A `gate_state` with no `merged_sha` recorded yet (the tail-only
    `new_state()` shape, `core/gate_rig.py`/`core/landing_rig.py`'s own
    fixtures — record driven directly, never through `gate.merge`) reads
    True — nothing to invalidate, the caller's own no-merged_sha branch
    (`_advance_trunk`'s `_escalate` arm) still owns that case."""
    sha = gate_state.get("merged_sha")
    if not sha:
        return True
    truth_ref = eng._truth_ref()
    return gitobs.is_ancestor(eng.paths["root"], sha, truth_ref, eng.dry)


def _churn_redrive_to_merge(eng, block, gate_state, stage_name):
    """H2's illegal-state fix, applied: `merged_sha` is no longer a CURRENT
    trunk ancestor — trunk churned it away after `gate.merge` observed it.
    Re-drive from `gate.merge` (never trust the stale sha as 'landed'):
    clear the merge/trunk-verdict bookkeeping so the NEXT `_advance_merge`
    call re-derives a fresh case-id off the branch's CURRENT patch-id
    (`landing.stage_case_id`'s own content-bound discipline) and re-lands
    for real. `merge_ordered` stays True (the worker was already told once;
    a stale grant/receipt is harmless — `land_via_grant`'s own content-bound
    enforcement, §5's sibling fix) so this never re-spams a fresh order."""
    detail = (f"gate[{block}] {stage_name}: merged_sha "
             f"{str(gate_state.get('merged_sha'))[:8]} is NO LONGER a "
             f"current trunk ancestor (churn — a force-push/rebase dropped "
             f"it after gate.merge observed it) — re-driving from gate.merge, "
             f"never reading stale content as landed (ADR-0009 §5 H2)")
    gate_state["stage"] = STAGE_MERGE
    gate_state["merged_sha"] = None
    gate_state["trunk_verdict_sha"] = None
    gate_state["trunk_verdict"] = None
    gate_state["trunk_verdict_detail"] = None
    eng.log("flow", detail)
    return "merge_churned", detail


def _advance_local(eng, block, gate_state, local_report):
    """One local-stage step: order once (side effect, idempotent), then
    judge whatever `local_report` THIS call was handed. A well-formed
    local-pass report (`{"verdict": "pass", "evidence": <non-empty str>}`)
    advances to `gate.merge`; a bare/absent/malformed report (`None`, `{}`,
    a wrong verdict, empty evidence) holds at `gate.local` — never
    advances, never escalates. Nothing is trusted from a PRIOR call's
    report implicitly re-supplied — a report only counts the tick it's
    actually handed to `advance`, so a caller can't accidentally wedge a
    stale/malformed report into a later, unrelated call."""
    branch = gate_state["branch"]
    wid = gate_state.get("wid")

    if not gate_state["local_ordered"]:
        if wid and not eng.dry:
            eng.emit(
                "gate.local",
                f"[TRON]  {wid} — gate.local: run the block's acceptance "
                f"suite locally on {branch} and report a structured "
                f"local-pass verdict (evidence, not a bare 'done').",
                slots={"block": block},
                worker_id=wid,
                kind="gate.local")
        gate_state["local_ordered"] = True
        eng.log("flow", f"gate[{block}] local: ordered local validation on {branch}")

    report = local_report if isinstance(local_report, dict) else None
    verdict = report.get("verdict") if report else None
    evidence = report.get("evidence") if report else None
    if verdict != "pass" or not evidence:
        return "local_waiting", "no well-formed local-pass report this call (bare/absent never advances)"

    gate_state["local_report"] = report
    gate_state["stage"] = STAGE_MERGE
    eng.log("flow", f"gate[{block}] local: accepted local-pass evidence on {branch} -> merge")
    return "local_passed", f"local evidence accepted: {evidence}"


def _advance_merge(eng, block, gate_state):
    """One merge-stage step: land the worker's OWN feature branch onto
    trunk via the Wave-1 landing primitive, under a case-id content-bound
    to THIS branch's current patch-id (`role='merge'` — distinct from the
    record stage's `role='record'` case-id for the SAME branch later, so
    the two landings can never collide on each other's receipts). Advances
    to `gate.trunk` only once `land_via_grant` itself reports `"landed"`
    (real ancestry observed) — captures the merged sha for the trunk
    stage's re-validation."""
    branch = gate_state["branch"]
    wid = gate_state.get("wid")
    truth_ref = eng._truth_ref()

    patch_id = gitobs.patch_id(eng.paths["root"], branch, truth_ref, eng.dry)
    # Content-bound to the CURRENT patch-id, never a stale cached id (T2-17 fix;
    # single-source in landing.stage_case_id, shared by all six landing callers).
    case_id = landing.stage_case_id(gate_state.get("merge_case_id"), "merge",
                                    branch, patch_id)
    gate_state["merge_case_id"] = case_id
    gate_state["merge_ordered"] = True

    outcome = landing.land_via_grant(eng, case_id, block, branch, wid,
                                     "gate.merge", "gate-merge")
    if outcome == "landed":
        gate_state["merged_sha"] = gitobs.tip_sha(eng.paths["root"], branch, eng.dry)
        gate_state["stage"] = STAGE_TRUNK
        eng.log("flow", f"gate[{block}] merge: {branch} observed on trunk "
                        f"({str(gate_state['merged_sha'])[:8]}) -> trunk")
        return "merge_landed", f"{branch} observed on trunk @ {gate_state['merged_sha']}"
    if outcome == "pending":
        return "merge_pending", f"grant live for {case_id}; awaiting land.sh"
    return "merge_fail_closed", f"unresolvable patch-id for {branch} (case {case_id})"


def _advance_trunk(eng, block, gate_state):
    """One trunk-stage step: re-validate the block's applicable ACs ON
    TRUNK, at the merged sha, via `gitobs.validate_trunk` (the single git/
    test observation seam — never a raw subprocess here). `"pass"`
    advances to `gate.record`; `"fail"` (a genuinely observed red) HOLDS at
    `gate.trunk` — never advances, since a real failure is not the same
    thing as a violation to escalate; a worker that fixes the code and
    re-merges (a new `gate.merge` cycle a caller may re-drive this state
    through) gets re-validated on the new sha. `"unconfirmed"` (nothing
    trustworthy could be read) holds the same way. Verdicts are cached per
    merged-sha so a re-tick before the sha changes never re-runs the
    suite."""
    sha = gate_state.get("merged_sha")
    if not sha:
        return _escalate(gate_state,
                         "gate.trunk reached with no merged_sha recorded — "
                         "gate.merge never observed a landing")

    if not _merge_still_landed(eng, gate_state):
        # ADR-0009 §5 H2: `sha` is no longer a CURRENT trunk ancestor —
        # never re-validate/advance on stale content. Re-drive from
        # gate.merge instead of trusting a cached trunk_verdict for a sha
        # churn has since dropped off trunk.
        return _churn_redrive_to_merge(eng, block, gate_state, "trunk")

    if gate_state.get("trunk_verdict_sha") == sha and gate_state.get("trunk_verdict") in ("pass", "fail"):
        status = gate_state["trunk_verdict"]
        detail = gate_state.get("trunk_verdict_detail", "")
    else:
        status, detail = gitobs.validate_trunk(
            eng.paths["root"], sha, eng.paths.get("test_command"),
            eng.paths.get("test_env"), eng.paths.get("ci_check_name"),
            eng.dry, scratch_root=eng.ctx.scratch_dir)
        if status in ("pass", "fail"):
            gate_state["trunk_verdict_sha"] = sha
            gate_state["trunk_verdict"] = status
            gate_state["trunk_verdict_detail"] = detail
        eng.log("flow", f"gate[{block}] trunk: declared test on {str(sha)[:8]} -> "
                        f"{status}: {detail}")

    if status == "pass":
        gate_state["stage"] = STAGE_RECORD
        return "trunk_passed", detail
    if status == "fail":
        return "trunk_failed", detail
    return "trunk_unconfirmed", detail


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

    if not _merge_still_landed(eng, gate_state):
        # ADR-0009 §5 H2: a block occupies `gate.record` only while its
        # merged commit is STILL a current trunk ancestor — re-checked here
        # too (record's own baseline is derived off `branch`/`truth_ref`,
        # not `merged_sha` directly, but the block has no business being at
        # `record` at all once the merge that got it there has churned off
        # trunk). Re-drive from gate.merge, never treat this stage's own
        # progress as still valid on stale content.
        return _churn_redrive_to_merge(eng, block, gate_state, "record")

    if not gate_state["record_ordered"]:
        # Re-anchor the record baseline to the block doc's last-touching commit
        # ALREADY ON TRUNK (truth_ref) at order time. The construction-time
        # baseline (`new_state`) is captured BEFORE the ladder runs, but the
        # worker's own merge/code commit may itself have touched the block doc
        # (e.g. folding a completion note into it — observed live in T2-01-07)
        # and then LANDED it at gate.merge. That already-on-trunk commit is
        # `!= record_base_sha` and touches more than the Status field, so
        # without this re-anchor `_advance_record` reads it as the record commit
        # and escalates it out-of-gate before the worker has even made the real
        # single-file flip. Anchoring to the on-TRUNK last-toucher (never the
        # branch tip — a flip a worker committed eagerly, pre-order, is NOT yet
        # on trunk and must still be detectable as the record commit) means only
        # a block-doc commit BEYOND trunk counts as the flip.
        gate_state["record_base_sha"] = gitobs.last_touching_sha(
            eng.paths["root"], truth_ref, block_file)
        if wid and not eng.dry:
            eng.emit(
                "gate.record",
                f"[TRON]  {wid} — gate.record: commit your block-doc completion on "
                f"{branch} per your session-end skill (§6): flip {block_file} to "
                f"`**Status:** ✅ Done` and add the `**Completed:**` date. Your §6 "
                f"close-out archival (`git mv` to blocks/archive/) and your OWN "
                f"pipeline.md row may ride in that same commit or come at close — "
                f"either lands. Nothing outside your block's own close-out paperwork.",
                slots={"block": block, "record_path": block_file},
                worker_id=wid,
                kind="gate.record")
        gate_state["record_ordered"] = True
        eng.log("flow", f"gate[{block}] record: ordered ✅ status-flip on {branch}")

    cur_sha = gitobs.last_touching_sha(eng.paths["root"], branch, block_file)
    if not cur_sha or cur_sha == gate_state["record_base_sha"]:
        return "record_waiting", f"no record commit on {branch} yet"

    # R5 (ADR-0005): accept the frozen skill §6 close-out bundle (block-doc
    # Status/Completed + its archival rename + this block's OWN pipeline row);
    # pass the pipeline path + block id so the check can lane-verify a bundled
    # pipeline edit, exactly as `verify_docs` does at land.
    ok, detail = gitobs.record_commit_ok(eng.paths["root"], block_file, eng.dry,
                                         truth_ref=branch,
                                         pipeline_file=eng.paths.get("pipeline_rel"),
                                         block_id=block,
                                         archive_dir=eng.paths.get("archive_rel"))
    if not ok:
        return _escalate(gate_state,
                         f"record commit on {branch} is out-of-gate: {detail}")

    patch_id = gitobs.patch_id(eng.paths["root"], branch, truth_ref, eng.dry)
    # Content-bound to the CURRENT patch-id, never a stale cached id (T2-17 fix;
    # single-source in landing.stage_case_id).
    case_id = landing.stage_case_id(gate_state.get("record_case_id"), "record",
                                    branch, patch_id)
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
    """One close-stage step. The close-out is a REAL landing, not a bare
    teardown: a worker's session-end skill commits close-out paperwork —
    block archival, the session log, pipeline sync — as its OWN commit on
    the branch (deliberately split from the single-file `gate.record` Status
    flip so record stays minimally verifiable). That commit must reach trunk
    exactly like the record commit did, through the ONE landing primitive
    under a content-bound `close`-scoped case-id — this is the grant
    `PMT-CLOSE` promises the worker ('I mint your land grant and order the
    land the moment I read your clean'). WITHOUT it the worker (correctly,
    per its contract) commits paperwork, reports `clean`, and blocks forever
    waiting on a grant that never comes — the confirmed 'no clean terminal
    close' root, reproduced live in T2-01-05.

    Sequence, all idempotent, none self-escalating (`core/sentry.py` is the
    ONE idle cap): order close once; land the close-out paperwork while the
    branch tip is still off trunk (`land_via_grant`, the SAME primitive
    record uses — stage-agnostic); once it's on trunk (or the worker made no
    close-out commit at all), release the slot only when the REAL replica is
    clean (`gitobs.replica_clean` — branch gone, no worktree), never on a
    worker's say-so."""
    branch = gate_state["branch"]
    wid = gate_state.get("wid")
    truth_ref = eng._truth_ref()

    if not gate_state["close_ordered"]:
        if wid and not eng.dry:
            eng.emit(
                "close.worker",
                f"[TRON]  {wid} — ✅ on trunk. Session-end: commit your close-out "
                f"paperwork on {branch} and reply `clean {block}:`. I mint your land "
                f"grant and order the land the moment I read it; then run land.sh, "
                f"remove your worktree + {branch}, and sync local.",
                slots={"block": block},
                worker_id=wid,
                kind="close.worker")
        gate_state["close_ordered"] = True
        eng.log("flow", f"gate[{block}] -> close (slot held)")
        return "close_ordered", f"ordered {wid or '(no worker)'} to close out"

    # Land the close-out paperwork whenever the branch still carries unlanded
    # commits (its tip is not yet an ancestor of trunk). land_via_grant is
    # stage-agnostic — the SAME content-bound primitive record uses, under a
    # `close`-scoped case-id. If the worker made no close-out commit (tip
    # already == trunk) or the branch is already gone, this arm is skipped and
    # we fall straight through to the teardown check.
    tip = gitobs.tip_sha(eng.paths["root"], branch, eng.dry)
    if tip and not gitobs.is_ancestor(eng.paths["root"], tip, truth_ref, eng.dry):
        pid = gitobs.patch_id(eng.paths["root"], branch, truth_ref, eng.dry)
        # Content-bound to the CURRENT patch-id, never a stale cached id (T2-17
        # fix; single-source in landing.stage_case_id).
        case_id = landing.stage_case_id(gate_state.get("close_case_id"), "close",
                                        branch, pid)
        gate_state["close_case_id"] = case_id
        outcome = landing.land_via_grant(eng, case_id, block, branch, wid,
                                         "close.worker", "gate-close")
        if outcome == "pending":
            return "close_pending", f"grant live for {case_id}; awaiting land.sh"
        if outcome == "fail-closed":
            return "close_holding", f"close-out patch-id unresolvable for {branch}"
        eng.log("flow", f"gate[{block}] close: paperwork landed on trunk ({case_id})")

    main_branch = eng.paths.get("main_branch", "main")
    clean, detail = gitobs.replica_clean(eng.paths["root"], branch, main_branch, eng.dry)
    if not clean:
        # HOLDS until the worker's teardown is git-observable — no attempt
        # count, no self-cap. `core/sentry.py` is the ONE place an idle close
        # (like an idle ANY other stage) gets nudged then escalated.
        return "close_holding", detail or "replica not yet clean"

    if wid:
        eng._release_worker(wid, reason="close-confirmed")
    gate_state["stage"] = STAGE_CLOSED
    eng.log("flow", f"gate[{block}] close confirmed -> worker released")
    return "closed", f"replica clean on {branch}; {wid or '(no worker)'} released"
