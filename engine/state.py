"""state — load / mutate / atomically persist manifest.yaml.

The FSM cursor, counters, active workers, the architect queue, and the disposable
trunk-read caches. Every tick loads it, mutates in memory, and persists once at
the end (contracts §5): state is written only after the bounded pass completes,
so a crashed tick leaves the pre-tick state intact and the next wake safely
re-runs.

TRON owns no pipeline (realign §A): the `pipeline` here is a READ-ONLY cache of
the project's canon trunk (pipeline.md + blocks/*.md), rebuilt every wake. Status
lives on trunk and only agents write it (via PR). TRON never sets it.

World-mutating actions are state-guarded here so a retried tick can't double-fire.
"""
import util

# Per-session merge control — one knob, "ask before merging" (01-08 T8). The worker gate ends at
# trunk: merging to trunk is the single gated step (CI auto-deploys staging from there); prod
# promotion is operator-only and never a worker stage. APPROVED -> TRON instructs the merge
# unprompted; ASK -> the trunk-merge step parks one operator case (four outcomes via
# _h_apply_decision). The default is APPROVED; the bootup question / ask_before_merging knob flips
# it to ASK. The single source for the fresh-start reset (fsm._reset_session_runtime) + the runtime
# default below; templates/manifest.yaml seeds the same for a hand-read instance.
DEFAULT_APPROVALS = {"merge": "APPROVED"}


class State:
    def __init__(self, ctx):
        self.ctx = ctx
        self.data = util.load_yaml(ctx.state)

    # ── persistence ──
    def save(self):
        util.save_yaml(self.ctx.state, self.data)

    # ── convenience accessors ──
    @property
    def fsm(self):
        return self.data.setdefault("fsm", {})

    @property
    def counters(self):
        return self.data.setdefault("counters", {})

    @property
    def workers(self):
        return self.data.setdefault("active_workers", [])

    @property
    def pipeline(self):
        """Read-only cache of the merged trunk view (reader.load). Rebuilt each wake
        from trunk; never authority. Rows: id, task, status, phase, section, order,
        depends_on, reviewer_class, merge, deploy, has_block_file."""
        return self.data.setdefault("pipeline", [])

    @property
    def live_config(self):
        return self.data.setdefault("live_config", {})

    @property
    def scope(self):
        """Run scoping chosen at bootup (session.scope). {mode: all|phase|range, value}.
        TRON dispatches only in-scope, still-open blocks; done (✅) stays invisible."""
        return self.data.setdefault("scope", {"mode": "all"})

    @property
    def architect_queue(self):
        """FIFO of architect jobs ({kind: forward|log, block, type}). No slot limit."""
        return self.data.setdefault("architect_queue", [])

    @property
    def cadence(self):
        """Per-type pull counter: <type> -> merged-✅ blocks seen since its last review."""
        return self.data.setdefault("cadence", {})

    @property
    def seen_done(self):
        """Block IDs already counted toward cadence (dedup against trunk re-reads)."""
        return self.data.setdefault("seen_done", [])

    @property
    def gate(self):
        """DONE-gate progress per block: {block_id: {stage, pr, detail}}. Runtime only —
        the gate drives an agent through the canon 6-stage flow; trunk-✅ is the verdict."""
        return self.data.setdefault("gate", {})

    @property
    def open_prs(self):
        """Last-read in-flight PRs keyed by head branch (trunk.open_prs cache)."""
        return self.data.setdefault("open_prs", {})

    @property
    def blocked(self):
        """Blocks parked on an operator decision (runtime escalation state, never git)."""
        return self.data.setdefault("blocked", [])

    @property
    def approvals(self):
        """Per-session merge control (01-08 T8). merge: APPROVED|ASK — ASK parks one operator case
        at the trunk-merge step. Held in runtime, reset each session; TRON never writes it to git."""
        return self.data.setdefault("approvals", dict(DEFAULT_APPROVALS))

    @property
    def run_control(self):
        """Operator run-control flag PULSE checks each tick (R-HALT, 01-03 T10):
        None/'running' | 'pause' (freeze dispatch, resumable) | 'drain' (finish in-flight,
        start nothing new, resumable) | 'halt' (terminate, no resume)."""
        return self.data.get("run_control")

    @run_control.setter
    def run_control(self, value):
        if value in (None, "running"):
            self.data.pop("run_control", None)
        else:
            self.data["run_control"] = value

    @property
    def pending_cases(self):
        """Open operator escalations keyed by correlation id (02-10 stamps it; the reply
        carries it back; 02-08 Settle applies it ≤1 tick later). {case_id: {block, kind,
        worker_id, detail, raised_at, decision}}."""
        return self.data.setdefault("pending_cases", {})

    @property
    def reconciled(self):
        """Block ids the architect has reconciled forward (re-checked against a just-finished
        block's drift) — readiness gate for dispatch once a predecessor has landed (M-05)."""
        return self.data.setdefault("reconciled", [])

    @property
    def branches(self):
        """block id -> the branch the worker NAMED for it (the agent owns the name; TRON never
        guesses it — 01-05 T2). Recorded from the worker's self-report (worker.branch); the DONE
        gate resolves the block's PR/CI on trunk via this name, never a computed `feat/<block>`."""
        return self.data.setdefault("branches", {})

    @property
    def review_markers(self):
        """Per-reviewer-type last-review marker: <type> -> the trunk commit at that type's
        previous review (T6). The reviewer's assignment is the commit range since this marker,
        so nothing slips between reviews; reset to HEAD when a review of that type dispatches."""
        return self.data.setdefault("review_markers", {})

    @property
    def trunk_sha_observed(self):
        """N1 (01-32 review round 2, ADR-0002 D2): the trunk sha the engine last OBSERVED,
        persisted here (not a plain Engine instance attr) because production constructs a
        FRESH `Engine(ctx)` every tick (wake.py's `locked_tick` + daemon loop — deliberate
        "stateless rebuild-from-trunk", ADR-0002 D1). An instance attr reset in `__init__`
        never survives that reconstruction, so `_trunk_sha_prev` was ALWAYS "" at the start
        of every tick — the observed-advance window `_refresh_from_trunk` computes never
        actually spanned a tick boundary, which made `_grant_matches_landed_range`'s
        fail-closed branch (no window -> False) fire on EVERY tick, turning every
        legitimate crash-window land into a false gate-bypass violation. Persisting the
        value here (`self.data`, written by the same `self.st.save()` every tick already
        calls) makes it survive both the next tick's fresh Engine AND a process restart.
        '' means never observed: either a genuine first tick, or a state file saved before
        this field existed (legacy upgrade) — `_refresh_from_trunk` treats that as "adopt
        the current tip as baseline" (an empty window this tick, never a violation storm),
        never as a huge/unbounded window against all of history."""
        return self.data.get("trunk_sha_observed", "")

    @trunk_sha_observed.setter
    def trunk_sha_observed(self, value):
        self.data["trunk_sha_observed"] = value

    def next_case_id(self, block):
        """A monotonic correlation id for an escalation (stable across a retried tick by the
        counter, not the clock)."""
        n = self.counters.get("case_seq", 0) + 1
        self.counters["case_seq"] = n
        return f"CASE-{n:03d}"

    # ── idempotency guards (contracts §5) ──
    def has_active_worker_for_block(self, block_id, role=None):
        for w in self.workers:
            if w.get("block") == block_id and w.get("status") not in ("released",):
                if role is None or w.get("role") == role:
                    return True
        return False

    def record_dispatch(self, worker_id, session_id, block_id, branch, attempt):
        line = (f"{util.now_iso()} | spawn | {worker_id} | {session_id} | "
                f"block={block_id} attempt={attempt} branch={branch}\n")
        with open(self.ctx.dispatched_log, "a") as fh:
            fh.write(line)

    # ── trunk-read cache (set by the engine's _refresh_from_trunk; never authority) ──
    def set_pipeline(self, view):
        self.data["pipeline"] = view

    def row(self, block_id):
        return next((r for r in self.pipeline if r.get("id") == block_id), None)

    def mark_counted(self, block_id):
        """Count a freshly-✅ block toward cadence exactly once."""
        if block_id in self.seen_done:
            return False
        self.seen_done.append(block_id)
        return True
