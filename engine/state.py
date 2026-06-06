"""state — load / mutate / atomically persist workflow-state.yaml.

The FSM cursor, counters, active workers and the pipeline mirror. Every tick
loads it, mutates in memory, and persists once at the end (contracts §5):
state is written only after the bounded pass completes, so a crashed tick
leaves the pre-tick state intact and the next wake safely re-runs.

World-mutating actions are state-guarded here so a retried tick can't double-fire.
"""
import os

import util

# pending  = needs clearing (the architect has not cleared it yet)
# cleared  = architect-cleared, ready to dispatch (the ONLY dispatchable status)
# in-progress = a worker is building it
# blocked  = walled, parked awaiting an operator:decision
# done     = built + released
# abandoned = operator dropped it (out of the sequence)
PIPELINE_STATUSES = {"pending", "cleared", "in-progress", "blocked", "done", "abandoned"}


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
        return self.data.setdefault("pipeline", [])

    @property
    def live_config(self):
        return self.data.setdefault("live_config", {})

    @property
    def architect_queue(self):
        """FIFO of architect jobs ({kind: forward|log, block, type}). No slot limit."""
        return self.data.setdefault("architect_queue", [])

    @property
    def cadence(self):
        """Per-type pull counter: <type> -> blocks completed since its last review."""
        return self.data.setdefault("cadence", {})

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

    # ── pipeline helpers ──
    def set_block_status(self, block_id, status):
        for row in self.pipeline:
            if row.get("id") == block_id:
                row["status"] = status
                return True
        return False

    def clear_block(self, block_id):
        """Architect forward-review result: pending -> cleared (dispatchable)."""
        for row in self.pipeline:
            if row.get("id") == block_id and row.get("status") == "pending":
                row["status"] = "cleared"
                return True
        return False

    def insert_adhoc_blocks(self, blocks):
        """Append adhoc fix blocks (architect log-review). Born `cleared` — ready to dispatch."""
        base = max((r.get("order") or 0) for r in self.pipeline) if self.pipeline else 0
        adhoc = [b for b in blocks if b.get("id")]   # an entry with no id can't be tracked — skip it
        for i, b in enumerate(adhoc, 1):
            self.pipeline.append({
                "order": base + i,
                "id": b["id"],
                "owner": b.get("owner_role", "engineer"),
                "status": "cleared",
                "kind": "adhoc",
                "notes": b.get("goal", ""),
            })
