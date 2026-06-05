"""state — load / mutate / atomically persist workflow-state.yaml.

The FSM cursor, counters, active workers and the pipeline mirror. Every tick
loads it, mutates in memory, and persists once at the end (contracts §5):
state is written only after the bounded pass completes, so a crashed tick
leaves the pre-tick state intact and the next wake safely re-runs.

World-mutating actions are state-guarded here so a retried tick can't double-fire.
"""
import os

import util

PIPELINE_STATUSES = {"todo", "in-progress", "blocked", "review", "done"}


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

    def worker(self, wid):
        for w in self.workers:
            if w.get("id", "").lower() == wid.lower():
                return w
        return None

    # ── idempotency guards (contracts §5) ──
    def has_active_worker_for_block(self, block_id, role=None):
        for w in self.workers:
            if w.get("block") == block_id and w.get("status") not in ("released",):
                if role is None or w.get("role") == role:
                    return True
        return False

    def is_paused_for_operator(self):
        return self.counters.get("paused_for_operator") not in (None, "")

    def already_dispatched(self, block_id, attempt):
        """dispatched.log keyed by block_id+attempt — spawn guard across ticks."""
        key = f"block={block_id} attempt={attempt}"
        if not os.path.exists(self.ctx.dispatched_log):
            return False
        with open(self.ctx.dispatched_log) as fh:
            return any(key in line for line in fh)

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

    def next_dispatchable_block(self):
        """Lowest-order block whose status is todo (deps are spec-enforced upstream)."""
        candidates = [r for r in self.pipeline if r.get("status") == "todo"]
        if not candidates:
            return None
        return sorted(candidates, key=lambda r: (r.get("order") or 1e9))[0]

    def insert_fix_blocks(self, blocks):
        """Append scoped fix blocks to the pipeline (findings-triage -> fixes)."""
        base = max((r.get("order") or 0) for r in self.pipeline) if self.pipeline else 0
        for i, b in enumerate(blocks, 1):
            self.pipeline.append({
                "order": base + i,
                "id": b["id"],
                "owner": b.get("owner_role", "engineer"),
                "status": "todo",
                "notes": b.get("goal", ""),
            })
