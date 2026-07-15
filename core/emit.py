"""core.emit — the SINGLE emit API + the one closed effect registry
(block 01-38 T7, ADR-0012 events-as-single-ground-truth spine).

THE INVARIANT THIS MODULE EXISTS TO MAKE UNREPRESENTABLE
--------------------------------------------------------
Every persisted state change in `core/` — every mutation of the durable
manifest (`core.state`'s payload) — routes through THIS module, and every
such change simultaneously writes ONE typed event naming the effect. The
two are inseparable by construction: you cannot apply a state change here
without the event, and you cannot (legally) apply one anywhere else at all.

Historically the manifest was a plain dict mutated raw (`manifest["cases"]
[cid]["decision"] = verb`, `gate_state["stage"] = ...`) all over `core/`,
and the forensic event stream was a SEPARATE, best-effort thing only five
call sites in the whole stack ever wrote to. The two could — and did —
drift: a state transition with no event, an event with no state behind it.
Under the operator's events-as-single-ground-truth rule (`events.jsonl` is
the sole truth source; the human flow-log is advisory) that drift is a
defect: acceptance and every proof read the event stream, so an un-emitted
transition is invisible to them (emission completeness — an un-emitted
effect is a must-be-zero-class defect).

T7 closes it by making the manifest mutation and its event ONE operation:

  - Call sites never write manifest-rooted state directly any more. They
    call `emit.put` / `emit.patch` / `emit.append` / `emit.drop` (state
    changes) or `emit.record` (a pure forensic event, no state) — each
    takes an `effect` naming a member of the closed `EFFECTS` registry, and
    each WRITES THE TYPED EVENT as part of applying the change.
  - The mutation is thus expressed as a FUNCTION CALL carrying an effect
    name, never a bare `manifest[...] = ...` subscript-store. A bypassing
    raw write is not the natural thing to type — and the completeness lint
    (block 01-38 T7's final sub-commit: a manifest-taint check over ALL of
    `core/`, whitelisting only THIS module) makes any that slip a hard
    failure. This module is the SOLE place a manifest-rooted subscript-store
    legally appears in `core/`.
  - `EFFECTS` is the ONE registry of the effect vocabulary. `emit` refuses
    an effect not in it (`UnknownEffectError`, raised — a typo fails loud at
    the call, never a silently-mis-typed event that drifts the vocabulary).

WHY A GENERIC MUTATOR, NOT ONE HAND-WRITTEN APPLIER PER EFFECT
-------------------------------------------------------------
The DECISION of what to change, and to what, stays in the domain modules
(`core/gate.py`, `core/casestate.py`, `core/architect.py`, ...) where it
belongs — this module never becomes a god-object re-implementing their
logic. It owns only the two things that must be central: (1) the single
point every manifest mutation physically happens, and (2) the paired typed
event. The verbs (`put`/`patch`/`append`/`drop`) are a small, generic,
mechanism-complete vocabulary of "what can physically change in a dict/list
manifest"; the `effect` argument carries the SEMANTICS (which is what the
event stream records and acceptance reads).

SINK-AGNOSTIC: the typed event is written to `eng.events` (the duck-typed
`.event(type, **payload)` sink `core.engine.Engine` supplies — an in-memory
`_Events` by default, a durable `engine/eventlog.py::EventLog` when a real
run passes one). Both share the `.event(type, **payload)` shape, so this
module never cares which it is. `record_to` takes a raw sink directly for
the ONE pre-engine caller that has an events sink but no `eng` yet
(`core/vocab.py::check_handshake`).

Duck-typed `eng` contract used here: `eng.events` (the `.event(...)` sink).
Nothing else — no git, no subprocess, no LLM, no file IO in this module.
"""

# ─────────────────────────── the one registry ───────────────────────────
#
# Each effect is one entry. `kind` is "state" (accompanies a manifest
# mutation) or "forensic" (a pure event, no state change). `counter_class`
# (R4, wired fully in T9) partitions the counter effects: "must_be_zero" (a
# primary path silently failing — acceptance reads these at zero) or
# "may_fire" (a designed rare backstop). A non-counter effect leaves it
# None. This registry GROWS one domain module's effects per T7 sub-commit;
# it is the single source of the effect vocabulary the completeness test
# (final sub-commit) reads.


# R4 (block 01-38 T9, `core/counters.py`): the closed set a registered
# effect's `counter_class` may be. `None` (a non-counter effect) is always
# legal and not a member of this set. Declared here (not just informally in
# prose) so a typo'd class name fails loud at registration time, never a
# silently-mis-classified counter `core/counters.py` can't find.
COUNTER_CLASSES = frozenset({"must_be_zero", "may_fire"})


class _Effect:
    __slots__ = ("name", "kind", "counter_class")

    def __init__(self, name, kind, counter_class=None):
        if counter_class is not None and counter_class not in COUNTER_CLASSES:
            raise ValueError(
                f"emit: {name!r} declared counter_class={counter_class!r}, not a "
                f"member of the closed set {sorted(COUNTER_CLASSES)} (or None)")
        self.name = name
        self.kind = kind
        self.counter_class = counter_class


def _reg(name, kind, counter_class=None):
    return name, _Effect(name, kind, counter_class)


EFFECTS = dict([
    # ── forensic events (no manifest mutation of their own) ──
    # A patch-id-bound merge/close grant was minted (`core/landing.py`).
    _reg("grant_minted", "forensic"),
    # The admission door refused a report — full text + origin recorded
    # durably (`core/door.py`, R2 "a door refusal is recorded engine-side").
    _reg("door_refusal", "forensic"),
    # A real AIDE (LLM advisor) call was made — bootup scope/counts advice or
    # a runtime escalation brief/ask (block 01-38 T7 FINAL sub-commit,
    # operator decision 260714: "a real AIDE invocation is a consequential
    # action... it must be readable from events.jsonl", so a SIM can verify
    # "AIDE fired live" without trusting a unit test as per-run evidence).
    # T24 wires the real runtime AIDE lane INTO `core/*` and will call
    # `emit.record(eng, "aide_invocation", ...)` at its own call site; TODAY
    # the only real AIDE call site is the legacy `engine/judge.py::call_aide`
    # (bootup, `engine/console.py`) — it writes this SAME event `type`
    # directly via its own pre-existing `elog.event(...)` idiom (matching
    # `_record_model_call`'s established pattern), since `engine/` is a
    # separate tree from `core/` and this block's emit-API-routing invariant
    # is `core/`-scoped only. Registered here so the vocabulary member is
    # ONE canonical name regardless of which call site (today's legacy one,
    # or T24's future `core/*` one) produces it.
    _reg("aide_invocation", "forensic"),
    # An operator page was attempted over the real transport, with its
    # delivered/failed receipt (`core/engine.py::_page_operator`, R8).
    _reg("operator_page", "forensic"),
    # A must-be-zero counter fired: a primary path silently failed where it
    # never should (`core/casestate.py` permanent page-fail, `core/vocab.py`
    # version-handshake fail). Acceptance reads the must-be-zero set at zero
    # (R4). The specific counter is named in the event's `counter` field.
    _reg("must_be_zero", "forensic", counter_class="must_be_zero"),

    # ── core/casestate.py — the parked-case FSM (T7 sub-commit 2) ──
    # The deterministic case-id counter advanced (`manifest["case_seq"]`).
    _reg("case_seq_advanced", "state"),
    # A correlation case was parked (raise-and-defer) — the case record minted.
    _reg("case_opened", "state"),
    # Opening a case moved the block's own gate to BLOCKED/parked-tagged.
    _reg("case_gate_parked", "state"),
    # A block was made re-drivable: its terminal gate and/or a worker record
    # naming it were dropped (fires once per dropped gate/worker record).
    _reg("block_redrivable", "state"),
    # The architect's triage verdict escalated a case to the operator (owner
    # flip + the FLOOR's first page bookkeeping).
    _reg("case_escalated_to_operator", "state"),
    # The architect resolved a case itself (scope_forward/answer) — decided,
    # never paged.
    _reg("case_architect_resolved", "state"),
    # T8 (block 01-38): a worker WITHDREW its OWN still-open worker.wall case
    # — self-correction. Deliberately a DISTINCT effect from
    # case_architect_resolved/case_settled so the event stream can tell "the
    # worker un-did its own wall" apart from an architect/operator decision
    # (T7's events-as-single-ground-truth spine — a SIM verifies self-retract
    # fired live off THIS event, never a unit test). Clears the case's
    # `decision` to "self_retracted"; the block is then made re-drivable
    # (`block_redrivable`) so the gate ladder RE-PROVES it on trunk — the
    # retract clears the wall, the trunk verdict closes the block. Zero
    # operator pages by construction (only fires while owner=="architect",
    # i.e. no page has gone out — a no-take-back guard, T21-consistent).
    _reg("case_self_retracted", "state"),
    # A case record was cleared from `manifest["cases"]` (settled, ≤1 tick).
    _reg("case_cleared", "state"),
    # An operator reply settled a case (decision/settled_at/note applied).
    _reg("case_settled", "state"),
    # A block was abandoned (added to `manifest["abandoned_blocks"]`).
    _reg("block_abandoned", "state"),
    # A landing wall's case auto-resolved on durable trunk truth (ADR-0008).
    _reg("case_stale_resolved", "state"),
    # THE FLOOR anchored a case's re-ping backoff clock (first sighting).
    _reg("case_page_anchored", "state"),
    # THE FLOOR forced a re-ping (attempts++/receipt/backoff reset).
    _reg("case_repinged", "state"),
    # THE FLOOR escalated the CHANNEL after a failed-delivery streak (warning,
    # still retrying — never terminal).
    _reg("case_channel_escalated", "state"),
    # An escalation was recorded in `manifest["escalations"]` (the batched,
    # operator-readable ledger).
    _reg("escalation_logged", "state"),
    # R8 SAFE-PARK-AND-HALT: a proven-dead transport — paging halts for this
    # case (paired with the `must_be_zero` counter above), full snapshot kept.
    _reg("case_page_permfailed", "state"),
    # R8 "seen" receipt: a genuine inbound reply named an open case.
    _reg("case_seen", "state"),

    # ── core/gate.py — the DONE-gate ladder (T7 sub-commit 3) ──
    # These patch the live `gate_state` (a manifest["gates"][block] sub-object
    # the gate functions hold by reference) via emit.patch_obj.
    _reg("gate_escalated", "state"),         # -> BLOCKED (out-of-gate / no merged_sha)
    _reg("gate_churn_redriven", "state"),    # H2: stale merged_sha -> re-drive from merge
    _reg("gate_local_ordered", "state"),     # local validation ordered
    _reg("gate_local_passed", "state"),      # local evidence accepted -> merge
    _reg("gate_merge_ordered", "state"),     # merge case-id bound + ordered
    _reg("gate_merged", "state"),            # branch observed on trunk -> trunk
    _reg("gate_trunk_verdict", "state"),     # trunk re-validation verdict cached
    _reg("gate_trunk_passed", "state"),      # trunk green -> record
    _reg("gate_record_rebased", "state"),    # record baseline re-anchored at order time
    _reg("gate_record_ordered", "state"),    # ✅ status-flip ordered
    _reg("gate_record_cased", "state"),      # record landing case-id bound
    _reg("gate_recorded", "state"),          # ✅ observed on trunk -> close
    _reg("gate_close_ordered", "state"),     # close-out ordered
    _reg("gate_close_cased", "state"),       # close landing case-id bound
    _reg("gate_closed", "state"),            # replica clean -> CLOSED

    # ── core/sentry.py — the idle-cap pacing ladder (T7 sub-commit 4) ──
    _reg("sentry_clock_advanced", "state"),   # the fallback pace clock ticked
    _reg("sentry_pacing_anchored", "state"),  # a gate/reviewer pacing episode (re)anchored
    _reg("sentry_pacing_cleared", "state"),   # a terminal/escalated gate's stale episode dropped
    _reg("sentry_nudged", "state"),           # a one-time re-nudge marked (nudged_at)
    _reg("sentry_escalated", "state"),        # a gate idle past the cap -> BLOCKED
    _reg("sentry_reviewer_dropped", "state"), # a capped reviewer's slot freed (workers pop)

    # ── core/engine.py — bootup + the Engine's own duck-typed surface (T7 sub-commit 5) ──
    # R-A: the per-worker engine->worker mailbox seq advanced (`manifest["mbox_seq"]`),
    # fired on every real dispatch (`_next_mbox_seq`).
    _reg("engine_mbox_seq_advanced", "state"),
    # D5/D6: a renderer-side template lookup failed for a template id `emit`
    # already validated against `vocab.EMIT_TEMPLATE_IDS` — `manifest["counters"]
    # ["emit_missing_template"]` bumped (durable, acceptance-readable per 01-39),
    # a must-be-zero-class counter (paired with the `must_be_zero` forensic event
    # family other modules already use).
    _reg("engine_emit_missing_template_counted", "state", counter_class="must_be_zero"),
    # An operator page was durably recorded (`manifest["operator_pages"][page_id]`)
    # — the STATE half of `_page_operator`; the forensic `operator_page` event
    # above is the separate, always-fired forensic half.
    _reg("engine_operator_page_recorded", "state"),
    # A5: bootup wrote the requested scope (`manifest["scope"]`).
    _reg("engine_scope_set", "state"),
    # A4/A5: bootup wrote the resolved worker/architect counts (`manifest["counts"]`).
    _reg("engine_counts_set", "state"),
    # A5: bootup seeded any not-yet-present cadence type at 0 (`manifest["cadence"]`).
    _reg("engine_cadence_seeded", "state"),
    # A8: bootup installed the architect's fresh state (`architect.new_state()`,
    # a pure local constructor) into `manifest["architect"]` — the ONE install site.
    _reg("engine_architect_installed", "state"),
    # A8: the just-installed (or already-present) architect record was marked spawned.
    _reg("engine_architect_spawned", "state"),
    # A6/A7: bootup wrote the live-session marker (`manifest["session"]`).
    _reg("engine_session_started", "state"),

    # ── core/switchboard.py — SWITCHBOARD's SPAWN half + GAP-C fleet-outage
    #     self-release (T7 sub-commit 6) ──
    # A worker record was minted into `manifest["workers"]` with status
    # "spawning", BEFORE any process (adversary §11.3 mint-then-spawn).
    _reg("worker_spawning_recorded", "state"),
    # A just-minted "spawning" worker record was reverted (`workers.pop`) after
    # a SYNCHRONOUS spawn-time failure — the slot freed for a genuine retry.
    _reg("worker_spawn_reverted", "state"),
    # GAP-C: one fleet-wide spawn-then-immediate-death event recorded
    # (`manifest["fleet"]` consecutive/total counters + the deaths ledger).
    _reg("fleet_death_recorded", "state"),
    # GAP-C: past fleet_outage_deaths, the one fleet-outage case's id was bound
    # onto `manifest["fleet"]["outage_case_id"]`.
    _reg("fleet_outage_opened", "state"),
    # GAP-C: dispatch self-paused (`manifest["paused"] = True`) — spawn nothing
    # further while a fleet-outage case is open.
    _reg("fleet_dispatch_paused", "state"),
    # GAP-C: dispatch un-paused (`manifest["paused"] = False`) once no outage
    # case blocks it.
    _reg("fleet_dispatch_resumed", "state"),
    # GAP-C: "outage clearing" — a subsequent spawn genuinely succeeded, so the
    # consecutive-death counter reset to 0.
    _reg("fleet_progress_reset", "state"),

    # ── core/router.py — the ASSIGN half + the structured-report routes
    #     (T7 sub-commit 7) ──
    # A worker was ASSIGNED (told what to build) — its record marked assigned so
    # a repeat worker.online is inert.
    _reg("worker_assigned", "state"),
    # ASSIGN opened the block's DONE-gate at gate.local, bound to the worker's
    # OWN reported branch (`manifest["gates"][block]` installed).
    _reg("gate_opened_local", "state"),
    # The just-assigned worker moved to "busy" on its declared branch.
    _reg("worker_busy", "state"),
    # A reconcile job's block was recorded reconciled (`manifest["reconciled"]`).
    _reg("block_reconciled", "state"),
    # An architect triage verdict was recorded (`manifest["triage_verdicts"]`).
    _reg("triage_verdict_recorded", "state"),
    # A worker.flag was ledgered forensically (`manifest["flag_ledger"]`).
    _reg("flag_ledgered", "state"),
    # A worker.flag was queued for the architect's batched digest
    # (`manifest["architect_flags"]`).
    _reg("flag_queued", "state"),
    # T4/AC-5: the must-be-zero router catch-all counter fired (an unroutable tag
    # reached route()) — `manifest["counters"]["router_catch_all"]` bumped.
    _reg("router_catch_all_counted", "state", counter_class="must_be_zero"),

    # ── core/reviewers.py — cadence PULL reviewers + the DONE-REVIEW gate
    #     (T7 sub-commit 8) ──
    # A landed block was counted toward cadence: recorded in
    # `manifest["cadence_seen_done"]` (dedupe) + every configured type's
    # `manifest["cadence"]` counter bumped.
    _reg("cadence_block_counted", "state"),
    # A per-type reviewer dispatch sequence advanced
    # (`manifest["reviewer_dispatch_seq"][typ]`).
    _reg("reviewer_dispatch_seq_advanced", "state"),
    # A reviewer's worker record was minted (`manifest["workers"][agent_id]`),
    # BEFORE any process (mint-then-spawn).
    _reg("reviewer_recorded", "state"),
    # A type's cadence counter was reset to 0 on dispatch (consumed on dispatch).
    _reg("cadence_reset", "state"),
    # A reviewer's slot was freed — its `manifest["workers"]` record popped.
    _reg("reviewer_released", "state"),
    # DONE-REVIEW gate: the first hand-back HELD the reviewer (status "held" +
    # findings stashed, pacing episode reset) pending its coverage attestation.
    _reg("review_held", "state"),

    # ── core/liveness.py — the worker-silence side-system (T7 sub-commit 9) ──
    # The liveness pace clock ticked (`manifest["liveness"]["clock"]`), the
    # fallback counter separate from sentry's own.
    _reg("liveness_clock_advanced", "state"),
    # A drained report marked its worker seen THIS tick (the transient
    # `_reported` flag `core/router.py::touch` sets).
    _reg("worker_reported", "state"),
    # `sweep` consumed a worker's `_reported` flag (turned into a fresh last_seen).
    _reg("worker_report_consumed", "state"),
    # A worker's liveness episode was (re)anchored: `last_seen` set to now (and
    # its ping episode cleared) — first-ever sighting or a reset on genuine activity.
    _reg("worker_last_seen_anchored", "state"),
    # A gateless stalled worker's slot was freed — its `manifest["workers"]`
    # record popped (no gate existed for open_case to flip terminal).
    _reg("worker_stall_released", "state"),
    # A silent worker was pinged once for its episode (`pinged_at` marked).
    _reg("worker_pinged", "state"),

    # ── core/tick.py — the bounded tick host (T7 sub-commit 10) ──
    # A closed block's worker record was marked `released` (the slot-freeing
    # half the real _release_worker can't do without a manifest handle).
    _reg("worker_slot_released", "state"),
    # The clean SESSION-END terminal marker was written (`manifest["session"]`).
    _reg("session_ended", "state"),

    # ── core/snapshot.py — the per-tick observe view (T7 sub-commit 11) ──
    # The manifest["gates"] section was first established (fires once per run,
    # the tick a gate is first needed) — the load-bearing alias every gate
    # write and the tick plan share.
    _reg("gates_section_seeded", "state"),

    # ── core/architect.py — the persistent coordinator (T7 sub-commit 12) ──
    # This module's OWN lazy-install site for `manifest["architect"]`
    # (`_ensure_installed`, used by all four of its entry points) — a
    # SEPARATE effect from `engine_architect_installed` (core/engine.py's
    # explicit bootup install); the two never collide, each only fires
    # while the key is still absent.
    _reg("architect_installed", "state"),
    # A clear-ahead `forward` job was queued (`architect_queue` append).
    _reg("architect_forward_job_enqueued", "state"),
    # An M-05 `reconcile` job was queued after a block landed ✅.
    _reg("architect_reconcile_job_enqueued", "state"),
    # GAP-E: a `triage` (PMT-TRIAGE) job was queued — architect-first, never
    # an immediate operator page.
    _reg("architect_triage_job_enqueued", "state"),
    # Wave 10: a `log` (log-review) job was queued off an attested review.
    _reg("architect_log_job_enqueued", "state"),
    # `manifest["triage_seq"]` advanced — the deterministic triage-job id
    # counter (`_next_triage_id`).
    _reg("architect_triage_seq_advanced", "state"),
    # `manifest["adhoc_seq"][<type>]` advanced — the deterministic adhoc
    # block-id counter shared by the triage scope_forward path and log-review.
    _reg("architect_adhoc_seq_advanced", "state"),
    # This module's OWN pluggable-clock fallback (`manifest["architect_clock"]
    # ["clock"]`) ticked — a separate counter from sentry's/liveness's own.
    _reg("architect_clock_advanced", "state"),
    # ADR-0009 R-B: a job (or one of its order-requiring sub-entries) was
    # stamped with the dispatch_seq/order-text/order-kind just used to send
    # it — optionally folding in the same-transition `ordered=True` flip.
    _reg("architect_dispatch_stamped", "state"),
    # ADR-0009 R-C/R-E: the SAME outstanding order was re-sent (respawn or
    # idle-gated re-deliver) — `last_sent_at` re-anchored.
    _reg("architect_redelivered", "state"),
    # ADR-0009 R-G: the no-progress accumulator's anchor fields were first
    # seeded (`unconsumed_since`/`last_sample`/`last_sent_at`).
    _reg("architect_delivery_anchored", "state"),
    # ADR-0009 R-G: one working-excluded integration step sampled
    # (`last_sample`/`unconsumed_work_excluded` advanced).
    _reg("architect_delivery_integrated", "state"),
    # ADR-0009 R-C: a clean respawn of the architect was counted.
    _reg("architect_respawn_recorded", "state"),
    # ADR-0009 R-G: the no-progress budget tripped — paged ONCE.
    _reg("architect_no_progress_paged", "state"),
    # ADR-0009 R-G: the no-progress accumulator + respawn count reset on a
    # genuine delivery flip (`_reset_delivery_state`).
    _reg("architect_delivery_reset", "state"),
    # T10: a settled triage turn with no routed verdict was re-ordered
    # (bounded, `_verdict_reorders` bumped) — never a silent guess.
    _reg("architect_triage_reorder_bumped", "state"),
    # T10: re-orders exhausted RESPAWN_CAP with still no structured verdict
    # — paged LOUD (verdict forced to "operator"), never fabricated.
    _reg("architect_triage_reorder_exhausted", "state"),
    # T10: a bounded re-order was armed (`ordered` reset so the next
    # `advance` call re-sends the triage order).
    _reg("architect_triage_reorder_retried", "state"),
    # A routed `architect.triage_verdict` report was applied to the job.
    _reg("architect_triage_verdict_recorded", "state"),
    # ADR-0008: a stale landing worker.wall's "operator" verdict was
    # downgraded to "answer" on durable trunk truth revalidation.
    _reg("architect_triage_verdict_downgraded_stale", "state"),
    # A triage job (case-bearing or case-less) reached its terminal
    # resolution (`answer`/`operator`/`scope_forward`-landed).
    _reg("architect_triage_resolved", "state"),
    # scope_forward: the job's own adhoc sub-entry was minted.
    _reg("architect_triage_adhoc_created", "state"),
    # scope_forward: the adhoc entry's content-bound land case-id was bound.
    _reg("architect_triage_adhoc_case_bound", "state"),
    # scope_forward: the adhoc entry's land_via_grant observed "landed".
    _reg("architect_triage_adhoc_landed", "state"),
    # A forward job's target branch was (re-)bound.
    _reg("architect_forward_branch_bound", "state"),
    # A forward job's content-bound land case-id was bound.
    _reg("architect_forward_case_bound", "state"),
    # A forward job's latest land_via_grant poll outcome was recorded (R1d
    # started-then-refused-authoring backstop reads this).
    _reg("architect_forward_outcome_recorded", "state"),
    # A forward job's block file was observed landed on trunk.
    _reg("architect_forward_landed", "state"),
    # A log-review job was ordered: its adhoc entries minted + `ordered` set
    # (folds in `landed_all=True` for a clean review with zero findings).
    _reg("architect_log_ordered", "state"),
    # A log-review adhoc entry's content-bound land case-id was bound.
    _reg("architect_log_entry_case_bound", "state"),
    # A log-review adhoc entry's land_via_grant observed "landed".
    _reg("architect_log_entry_landed", "state"),
    # A log-review job's aggregate poll outcome was recorded (`landed_all` +
    # `last_outcome`, the R1d backstop's own read).
    _reg("architect_log_poll_recorded", "state"),
    # M-05: a reconcile's target block was recorded into
    # `manifest["reconciled"]` (either a routed `architect.reconciled`
    # report via core/router.py, or this module's own no-op backstop).
    _reg("architect_reconciled_recorded", "state"),
    # The architect's own `current_job` was cleared back to idle (any job
    # kind's terminal transition — reconcile-observed, forward/log landed,
    # forward/log refused-authoring, triage resolved).
    _reg("architect_job_cleared", "state"),
    # A queued job was popped off `manifest["architect_queue"]`'s FIFO front
    # and became the architect's new `current_job`.
    _reg("architect_job_popped", "state"),
    # The architect's `current_job` was set busy with a just-popped job.
    _reg("architect_job_dispatched", "state"),
    # `eng._spawn_architect()` was called for the first time (`spawned`
    # latched true) — never a second real spawn off this same flag.
    _reg("architect_spawned_marked", "state"),
    # R5: the batched visibility-flag digest was sent and its queue drained
    # (`manifest["architect_flags"]` reset to empty).
    _reg("architect_flags_digest_sent", "state"),
])


class UnknownEffectError(KeyError):
    """A caller named an effect not in the closed `EFFECTS` registry — a
    typo or an un-registered new effect. Raised at the call (never a
    silently-mis-typed event that drifts the vocabulary); the fix is to
    register the effect in `EFFECTS` above, deliberately, or correct the
    name."""


def _spec(effect):
    try:
        return EFFECTS[effect]
    except KeyError:
        raise UnknownEffectError(
            f"emit: {effect!r} is not a registered effect. Every effect must be "
            f"declared in core.emit.EFFECTS (the one closed effect vocabulary). "
            f"Legal effects: {sorted(EFFECTS)}") from None


def _write(sink, effect, fields):
    """The ONE event-write. `sink` is a `.event(type, **payload)` sink
    (`_Events` or `EventLog`). The typed event's `type` IS the effect name —
    the registry is the closed vocabulary of those types."""
    sink.event(effect, **fields)


# ─────────────────────────── navigation ───────────────────────────
def _nav(manifest, path, create):
    """Resolve `path` (a tuple of keys) to the container it names inside
    `manifest`. With `create=True`, every missing intermediate dict is
    `setdefault`-seeded (the SAME "seed the section you need" discipline
    every `core/` module already uses on the manifest) so a first write to a
    fresh section lands. `path=()` is the manifest root itself. This is the
    ONLY manifest navigation in the mutating verbs below — a single, audited
    place, never scattered."""
    node = manifest
    for key in path:
        if create:
            node = node.setdefault(key, {})
        else:
            node = node[key]
    return node


# ─────────────────────────── the emit API ───────────────────────────
def record(eng, effect, **fields):
    """A pure forensic event — NO manifest mutation. Writes the typed
    `effect` event to `eng.events`. `effect` must be a `kind == "forensic"`
    registry member (a state-kind effect used with no mutation is a caller
    error — use the mutating verbs). The single replacement for the raw
    `eng.events.event(<type>, ...)` calls the pre-T7 stack scattered."""
    spec = _spec(effect)
    if spec.kind != "forensic":
        raise UnknownEffectError(
            f"emit.record: {effect!r} is a {spec.kind!r}-kind effect — a state "
            f"change, not a pure forensic event; use emit.put/patch/append/drop.")
    _write(eng.events, effect, fields)


def record_to(sink, effect, **fields):
    """`record`, but for the ONE pre-engine caller that holds a raw events
    sink and no `eng` yet (`core/vocab.py::check_handshake`, which runs at
    the version handshake before any `Engine` is assembled). Same closed-
    registry check, same typed write."""
    spec = _spec(effect)
    if spec.kind != "forensic":
        raise UnknownEffectError(
            f"emit.record_to: {effect!r} is a {spec.kind!r}-kind effect, not a "
            f"pure forensic event.")
    _write(sink, effect, fields)


def put(eng, manifest, effect, path, key, value, **fields):
    """Set `manifest<path>[key] = value` (creating missing intermediate
    dicts) AND write the typed `effect` event. Returns `value`. The event's
    payload is `fields` (the caller names what the stream records); the
    verb + path + key/value are the physical change. Use for a single keyed
    assignment (`manifest["cases"][cid] = case`)."""
    _spec(effect)
    _nav(manifest, path, create=True)[key] = value
    _write(eng.events, effect, fields)
    return value


def patch(eng, manifest, effect, path, updates, **fields):
    """Apply every `updates` key onto the dict at `manifest<path>` (creating
    it if missing) AND write the typed `effect` event — the natural shape
    for a state TRANSITION that sets several related fields at once (a gate
    moving stage while clearing the next stage's fields). Returns the
    patched dict."""
    _spec(effect)
    target = _nav(manifest, path, create=True)
    target.update(updates)
    _write(eng.events, effect, fields)
    return target


def patch_obj(eng, effect, target, updates, **fields):
    """Like `patch`, but the caller holds the manifest SUB-OBJECT directly
    (a `gate_state`, a `case`, ...) instead of the manifest root + a path —
    the shape for a module handed one live state record to advance
    (`core/gate.py::advance` gets `gate_state`, never `manifest`). Applies
    `updates` onto `target` in place AND writes the typed event. `target`
    MUST be the real manifest-rooted object (mutating a throwaway copy would
    not persist) — the caller's responsibility, exactly as it already was
    for the raw in-place mutation this replaces. Returns `target`."""
    _spec(effect)
    target.update(updates)
    _write(eng.events, effect, fields)
    return target


def append(eng, manifest, effect, path, value, **fields):
    """Append `value` to the list at `manifest<path>` (created empty if
    missing) AND write the typed `effect` event. `path` names the list
    itself (e.g. `("escalations",)`). Returns `value`."""
    _spec(effect)
    parent = _nav(manifest, path[:-1], create=True)
    parent.setdefault(path[-1], []).append(value)
    _write(eng.events, effect, fields)
    return value


def drop(eng, manifest, effect, path, key, **fields):
    """Remove `key` from the dict at `manifest<path>` (a `pop`, absent-safe)
    AND write the typed `effect` event — a state change is still a state
    change when it REMOVES (a case cleared, a worker slot freed). Returns the
    popped value (or None). `path` must already exist (a drop from a missing
    section is a no-op that still records the intended effect)."""
    _spec(effect)
    try:
        target = _nav(manifest, path, create=False)
    except (KeyError, TypeError):
        target = None
    popped = target.pop(key, None) if isinstance(target, dict) else None
    _write(eng.events, effect, fields)
    return popped


def pop_index(eng, manifest, effect, path, index=0, **fields):
    """Remove and return the item at `index` (default `0` — a FIFO's front)
    from the LIST at `manifest<path>` AND write the typed `effect` event —
    the list-shaped counterpart to `drop`'s dict-key pop (T7 sub-commit 12,
    `core/architect.py`'s `manifest["architect_queue"]`, the one `core/`
    FIFO this exists for). Absent/empty-safe: a missing or empty list is a
    no-op that still records the intended effect, mirroring `drop`'s own
    absent-safe discipline. Returns the popped value (or None)."""
    _spec(effect)
    try:
        target = _nav(manifest, path, create=False)
    except (KeyError, TypeError):
        target = None
    popped = target.pop(index) if isinstance(target, list) and target else None
    _write(eng.events, effect, fields)
    return popped
