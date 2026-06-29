"""fsm — the deterministic spine: PULSE + SWITCHBOARD + the event table.

The engine that drives the canon flow. Two layers, both deterministic code
(NEVER an LLM call):

  PULSE       the dispatch loop. Re-runs on every `pulse` control signal (bootup,
              slot free, block authored, review done, recovered, decision applied)
              and drives SWITCHBOARD.
  SWITCHBOARD the per-pulse work selector: FILL SLOTS -> CLEAR AHEAD -> WAIT ->
              SESSION END.

Truth is the project's canon trunk, not TRON (realign §A): each wake rebuilds the
pipeline view from `git` trunk (pipeline.md + blocks/*.md) plus in-flight PRs plus
alive workers. TRON reads; agents write. TRON writes nothing to git — its only
durable state is the gitignored runtime cache. A worker's "done" is a trigger, not
truth: it launches the canon DONE gate (§F), and a block is done only when it shows
`✅` on trunk (merged, re-validated, deployed-clean — agents land all of it via PR).

The reactive layer is the event TABLE (`trigger -> handler`). The engine emits
trigger strings and routes them most-specific-wins; inbound worker/operator
messages become triggers via routing.yaml's tag map (classify_message is the only
inbound LLM call).

The architect is a PERSISTENT agent, EXCLUDED from the worker pool, draining a
FIFO queue serially (forward-only). Engineers + reviewers share the worker pool.

One wake = one bounded tick: refresh from trunk, sweep liveness, drain inboxes
into triggers, drain the trigger queue to quiescence, persist atomically, exit.
"""
import os
import json

import util
import jobs
import judge
import reader
import trunk
import eventlog
from state import State, DEFAULT_APPROVALS
from render import Renderer

# ── the event TABLE ──
# pattern -> handler method name; None = worker-activity row (no engine action).
# Module-level so blueprint-lint validates it against the grammar without
# instantiating the Engine (contracts §9).
# SWITCHBOARD dispatches engineers/reviewers/forward-reviews by calling the methods
# directly, so build:block:next, cadence:<type>, and review:next:<block> are not emitted
# in normal flow; their rows declare the grammar edges (so lint L7/L9 see complete
# coverage) and handle the trigger form if one ever arrives generically.
TABLE = [
    ("tron:start",                 "_h_bootup"),
    ("build:block:next",           "_h_dispatch_engineer"),  # see note above: not emitted in normal flow
    ("block:next:build",           None),               # engineer building
    ("block:next:done",            "_h_worker_done"),   # done is a trigger -> DONE gate (§F)
    ("review:next:<block>",        "_h_forward_review"),     # not emitted in normal flow (SWITCHBOARD calls directly)
    ("block:<block>:reconciled",   "_h_reconcile"),     # architect re-checked/authored the path ahead (M-05)
    ("worker:await:<block>",       "_h_await"),         # worker paused for go-ahead -> await ladder (R-AWAIT)
    ("cadence:<type>",             "_h_dispatch_reviewer"),   # not emitted in normal flow (SWITCHBOARD calls directly)
    ("review:<type>",              None),               # reviewer reviewing
    ("review:<type>:done",         "_h_release_reviewer"),
    ("wall:raised:<block>",        "_h_escalate"),
    ("operator:decision:<block>",  "_h_apply_decision"),
    ("worker:stalled",             "_h_recover"),
    ("session:end",                "_h_session_end"),
    ("*",                          "_h_sentry"),        # SENTRY: the reactive catch-all (the `*` row)
]

OPEN_STATUSES = ("to-do", "in-progress")   # work that still counts as not-done


class Engine:
    def __init__(self, ctx):
        self.ctx = ctx
        self.routing = ctx.load_routing()
        self.comp = ctx.load_knobs()
        self.project = ctx.load_project()
        self.renderer = Renderer(ctx)
        self.st = State(ctx)
        self.tags = self.routing.get("tags", {})
        self.knobs = self.comp.get("knobs", {})
        self.cadence_cfg = self.comp.get("cadence", {}) or {}
        self._max_retries = int((self.routing.get("invalid_output") or {}).get("max_retries", 2))
        self.ended = False
        self.dry = bool(os.environ.get("TRON_DRY"))
        self._tq = []   # the trigger queue, drained within one tick
        self.table = TABLE
        self.paths = ctx.repo_paths(self.project)
        self._trunk_sha = ""                          # last-known trunk HEAD (forensic state context)
        self.events = eventlog.EventLog(ctx, self._log_env)

    def _log_env(self):
        """Live forensic context stamped on every structured record (01-06): the run handle,
        the tick number, and the trunk sha the engine is currently reading. `tick` is the
        IN-PROGRESS tick (1-based; bumped at tick start) — 0 for records emitted before the
        first tick (e.g. session_start)."""
        sess = self.st.data.get("session", {}) or {}
        last = self.st.data.get("last_sweep", {}) or {}
        return {"run": sess.get("started_at"),
                "tick": last.get("sweeps_this_session", 0),
                "trunk": self._trunk_sha}

    # ── emit: every human-visible line comes from messages.yaml ──
    def emit(self, template_id, slots=None, worker_session=None):
        line = self.renderer.render(template_id, slots or {})
        channel = self.renderer.channel(template_id)
        util.append_jsonl(self.ctx.home_log,
                          {"at": util.now_iso(), "channel": channel, "text": line})
        if channel == "worker" and worker_session and not self.dry:
            jobs.send(worker_session, line)
        elif channel == "tg" and not self.dry:
            self._tg_send(line)
        else:
            print(line)
        return line

    def _tg_send(self, line):
        import subprocess
        script = os.path.join(self.ctx.scripts_dir, "tg-send.sh")
        if os.path.exists(script):
            try:
                subprocess.run(["bash", script, line], timeout=20,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def log(self, name, text):
        util.log_line(self.ctx.logs_dir, name, text)

    # ── the tick (contracts §5) ──
    def tick(self):
        # No session has started -> nothing to do. A stray tick (a manual `tron tick`
        # before `tron start`) must never sweep, classify, or consume inbox messages
        # into a phantom session — the WAKE daemon only runs once a session is live.
        if not (self.st.data.get("session") or {}).get("started_at"):
            return self.ended
        self._tq = []
        # Bump the tick counter up front so every forensic record this pass carries the
        # IN-PROGRESS tick number (1-based), not last-completed (01-06 review #2).
        last = self.st.data.setdefault("last_sweep", {})
        last["sweeps_this_session"] = last.get("sweeps_this_session", 0) + 1
        self._refresh_from_trunk()                       # canon is truth — rebuild the read cache
        if self.ended:                                   # refresh hit the trunk-fail death-cap -> halted loud (T6)
            self.st.save()
            return self.ended
        rc = self.st.run_control
        if rc != "pause":                                # PAUSE freezes liveness pings + gate nudges; DRAIN keeps them
            self._sweep()                                # engine liveness -> worker:stalled
        claimed, msgs = self._claim_inboxes()            # rotate each inbox to a .proc sidecar, read it
        for msg in msgs:
            # One malformed message must not abort the tick: that would leave it in the sidecar
            # (released only after a clean save) and re-fire it every sweep — a poison pill.
            try:
                tag, slots = self._classify(msg)
                self._ingest(tag, slots, msg.get("sender", {}))
            except Exception as e:
                self.log("flow", f"ingest dropped a message: {e}")
                sender = msg.get("sender", {})
                self.events.failure(                      # forensic record (AC-2/AC-6): the poison-pill guard
                    "ingest-drop", "ingest-exception", "classify + ingest one inbound message",
                    f"{type(e).__name__}: {e}",
                    actor=sender.get("id") or sender.get("kind") or "unknown",
                    inputs={"text": msg.get("text", "")[:200]},
                    node="§5 tick drain", next_action="drop (re-read next tick at-least-once)")
        if rc != "pause":
            self._drive_gates()                          # advance in-flight DONE gates on fresh evidence
        self._drain_triggers()
        self.st.data.setdefault("last_sweep", {})["at"] = util.now_iso()  # count bumped at tick start
        self.st.save()                                   # persist effects FIRST
        self._release_claimed(claimed)                   # then drop the claimed sidecars (at-least-once)
        return self.ended

    # ── trunk read (realign §5): canon is truth; TRON reads, agents write ──
    def _refresh_from_trunk(self, count=True):
        """Fast-forward the trunk checkout, rebuild the pipeline view + PR cache, and
        recognise newly-✅ blocks (count cadence, release their workers). Best-effort:
        a failed fetch reuses the last on-disk snapshot — never block the loop.
        `count=False` (the initial load at start) skips the done-counting so pre-existing
        ✅ history is NOT mistaken for fresh completions — _seed_seen_done primes it instead."""
        ok, detail = trunk.refresh(self.paths["root"], self.paths["main_branch"], self.dry)
        if ok:
            self.st.counters["refresh_fail"] = 0
            self._trunk_sha = trunk.head_sha(self.paths["root"], self.dry)  # pin the tree we're reading
        else:
            # Fail LOUD, never silent (T6/S1-10): a swallowed ff-failure leaves a stale snapshot
            # -> duplicate dispatch. Count consecutive failures; bootup (count=False) has no
            # MANIFEST yet (A2) so a single failure halts synchronously; ticks tolerate a flaky
            # network up to the death-cap, then halt loud.
            fails = self.st.counters.get("refresh_fail", 0) + 1
            self.st.counters["refresh_fail"] = fails
            cap = int(self.knobs.get("trunk_refresh_deathcap", 3))
            self.log("trunk", f"refresh FAILED ({fails}/{cap}): {detail}")
            halting = (not count) or fails >= cap
            self.events.failure(                          # forensic record (AC-2/AC-6): never silent
                "refresh-fail", "trunk-ff-failed", "fast-forward trunk checkout", detail,
                inputs={"root": self.paths["root"], "main_branch": self.paths["main_branch"]},
                node="T6/S1-10 trunk-refresh", attempt=f"{fails}/{cap}",
                next_action="halt" if halting else "retry", bootup=not count)
            if halting:
                self._halt_loud(f"trunk refresh failed: {detail}", bootup=not count)
                return
        try:
            view = reader.load(self.paths["pipeline"], self.paths["blocks"])
            self.st.set_pipeline(view)
        except Exception as e:
            self.log("trunk", f"read failed (reusing snapshot): {e}")
        self.st.data["open_prs"] = trunk.open_prs(self.paths["root"], self.dry)
        if not count:
            return
        # Newly-done blocks: count toward cadence once, finalize any worker still on them.
        for r in self.st.pipeline:
            if r.get("status") == "done" and self.st.mark_counted(r["id"]):
                self._on_block_done(r["id"])

    def _seed_seen_done(self):
        """At session start, mark all already-✅ blocks as counted WITHOUT bumping cadence —
        only blocks completed during this run should ever trigger a review."""
        for r in self.st.pipeline:
            if r.get("status") == "done":
                self.st.mark_counted(r["id"])

    def _on_block_done(self, block):
        """A block reached ✅ on trunk (the only done-truth). Tick cadence, release the
        engineer that drove it, clear its gate, announce, pulse."""
        for typ in self.cadence_cfg:
            self.st.cadence[typ] = self.st.cadence.get(typ, 0) + 1
        for w in list(self.st.workers):
            if w.get("role") == "engineer" and w.get("block") == block:
                self._release_worker(w)
        self.st.gate.pop(block, None)
        if block in self.st.blocked:
            self.st.blocked.remove(block)
        self.events.event("block_done", block=block)
        self.emit("terminal.block_done", {"block": block})
        self.log("flow", f"{block} ✅ on trunk -> done, cadence++")
        self._reconcile_ahead(block)                     # re-check the next scoped block vs this one's drift (M-05)
        self._emit("pulse")

    def _reconcile_ahead(self, done_block):
        """A block landed ✅. The next already-scoped, not-yet-done block downstream must be
        RE-checked against this one's learnings/drift before it dispatches (M-05) — a reconcile,
        a DISTINCT architect job from `forward` (which authors a missing file). Enqueue it and
        gate that block's readiness (`_available`) on the reconcile completing. No architect ->
        no reconcile gate (nothing can re-check it), so the block stays directly dispatchable."""
        if not self._architect():
            return
        nxt = self._next_reconcile_target(done_block)
        if not nxt or nxt in self.st.reconciled:
            return
        if any(j.get("kind") == "reconcile" and j.get("block") == nxt
               for j in self.st.architect_queue):
            return
        arch = self._architect()
        cur = arch.get("current_job") if arch else None
        if cur and cur.get("kind") == "reconcile" and cur.get("block") == nxt:
            return
        self.st.architect_queue.append({"kind": "reconcile", "block": nxt, "after": done_block})
        self._pump_architect()

    def _next_reconcile_target(self, done_block):
        """The next in-scope, not-done block (by pipeline order) after `done_block` that already
        has a block file — the one a just-finished block's drift could invalidate."""
        rows = sorted(self._in_scope_rows(), key=lambda r: r.get("order") or 1e9)
        seen = False
        for r in rows:
            if r["id"] == done_block:
                seen = True
                continue
            if not seen:
                continue
            if (r.get("status") in OPEN_STATUSES and r.get("has_block_file")
                    and r["id"] not in self._dropped() and r["id"] not in self.st.blocked):
                return r["id"]
        return None

    # ── trigger queue + routing ──
    def _emit(self, trigger, slots=None):
        self._tq.append((trigger, slots or {}))

    def _drain_triggers(self):
        guard = 0
        while self._tq and guard < 512:
            guard += 1
            trig, slots = self._tq.pop(0)
            if trig in (None, "-"):
                continue
            if trig == "end":
                self._end_session()
                continue
            if trig == "pulse":
                self._switchboard()
                continue
            # A handler that raises must not abort the whole tick (see tick()): that strands the
            # triggering message in the inbox and re-fires it forever. Log and move on.
            try:
                self._route(trig, slots)
            except Exception as e:
                self.log("flow", f"handler for '{trig}' raised: {e}")

    def _route(self, trig, slots):
        handler, caps = self._match(trig)
        if handler is None:               # worker-activity row: engine does nothing
            return
        m = dict(slots)
        m.update(caps)
        m["_trigger"] = trig
        getattr(self, handler)(m)

    def _match(self, trig):
        """Most-specific-wins: literal > <block>/<type>/* > catch-all (contracts §1)."""
        segs = trig.split(":")
        best = None  # (handler, caps, score)
        for pat, handler in self.table:
            if pat == "*":
                continue
            ps = pat.split(":")
            if len(ps) != len(segs):
                continue
            score, caps, ok = 0, {}, True
            for pseg, cseg in zip(ps, segs):
                if pseg == cseg:
                    score += 2
                elif pseg in ("<block>", "*"):
                    score += 1
                    caps["block"] = cseg
                elif pseg == "<type>":
                    if cseg == "next":          # grammar: <type> never binds the reserved 'next'
                        ok = False
                        break
                    score += 1
                    caps["type"] = cseg
                else:
                    ok = False
                    break
            if ok and (best is None or score > best[2]):
                best = (handler, caps, score)
        if best:
            return best[0], best[1]
        return "_h_sentry", {}            # the `*` SENTRY catch-all

    # ── PULSE / SWITCHBOARD (the dispatch loop) ──
    def _switchboard(self):
        """One pulse: FILL SLOTS -> CLEAR AHEAD -> WAIT -> SESSION END."""
        # 0. RUN-CONTROL (R-HALT / T10) — the operator flag PULSE checks every pulse.
        #    PAUSE freezes all dispatch (hard, resumable); DRAIN starts nothing new but lets
        #    in-flight finish (soft, resumable). Neither ends the run — only RESUME or HALT do,
        #    so a drained-to-empty fleet idles awaiting the operator rather than auto-closing.
        if self.st.run_control in ("pause", "drain"):
            return
        # 1. FILL SLOTS — one dispatch per free worker slot, in priority order.
        while self._free_slots() > 0:
            pick = self._select_work()
            if pick is None:
                break
            kind, ref = pick
            if kind == "cadence":
                self._dispatch_reviewer(ref)
            else:
                self._dispatch_engineer(ref)
        # 2. CLEAR AHEAD — for every in-scope roadmap row that has no block file yet,
        #    enqueue the architect to author it (canon: "clearing" = authoring the block).
        for row in self._in_scope_rows():
            if (row.get("section") or "").lower().startswith("roadmap-na"):
                continue
            if (row.get("status") in OPEN_STATUSES and not row.get("has_block_file")
                    and self._is_roadmap(row) and row["id"] not in self.st.blocked):
                self._forward_review(row["id"])
        # 3. WAIT — implicit: nothing dispatchable, re-enter on the next pulse.
        # 4. SESSION END — only when the whole run is settled.
        if self._all_settled():
            self._emit("session:end")

    def _is_roadmap(self, row):
        return (row.get("section") or "").lower().startswith("roadmap") or bool(row.get("phase"))

    def _select_work(self):
        """Priority: (a) oldest available adhoc · (b) due cadence · (c) next available block.
        Available = dispatchable (block file, 📋, deps ✅) AND in scope AND not already
        in flight (no worker, no open PR, no active gate) AND not parked/dropped."""
        idx = reader.status_index(self.st.pipeline)
        avail = [r for r in self._in_scope_rows() if self._available(r, idx)]
        adhoc = sorted((r for r in avail if reader.is_adhoc(r)),
                       key=lambda r: r.get("order") or 1e9)
        if adhoc:
            return ("block", adhoc[0]["id"])
        due = self._due_cadence()
        if due:
            return ("cadence", due)
        blocks = sorted((r for r in avail if not reader.is_adhoc(r)),
                        key=lambda r: r.get("order") or 1e9)
        if blocks:
            return ("block", blocks[0]["id"])
        return None

    def _available(self, row, idx):
        if not reader.dispatchable(row, idx):
            return False
        bid = row["id"]
        if bid in self.st.blocked or bid in self.st.gate:
            return False
        if self.st.has_active_worker_for_block(bid):
            return False
        if self._block_branch(bid) in (self.st.open_prs or {}):
            return False
        if self._reconcile_pending(bid):                 # gated until the architect reconciles it (M-05)
            return False
        return True

    def _reconcile_pending(self, bid):
        """True while a reconcile job for this block is queued/in-flight and not yet completed
        (the readiness gate a predecessor's ✅ raised). Cleared when `_h_reconcile` records it."""
        if bid in self.st.reconciled:
            return False
        if any(j.get("kind") == "reconcile" and j.get("block") == bid
               for j in self.st.architect_queue):
            return True
        arch = self._architect()
        cur = arch.get("current_job") if arch else None
        return bool(cur and cur.get("kind") == "reconcile" and cur.get("block") == bid)

    def _due_cadence(self):
        for typ, thresh in self.cadence_cfg.items():
            if thresh and self.st.cadence.get(typ, 0) >= thresh:
                if not any(w.get("role") == "reviewer" and w.get("rtype") == typ
                           for w in self._pool()):
                    return typ
        return None

    # ── scope (set at bootup via session.scope; never status edits) ──
    def _in_scope_rows(self):
        sc = self.st.scope or {}
        mode = sc.get("mode", "all")
        rows = self.st.pipeline
        if mode == "phase":
            want = str(sc.get("value") or "").strip().lower()
            return [r for r in rows if want and want in str(r.get("phase") or "").lower()]
        if mode == "range":
            val = sc.get("value") or []
            ids = [r["id"] for r in rows]
            try:
                lo, hi = ids.index(val[0]), ids.index(val[1])
                lo, hi = min(lo, hi), max(lo, hi)
                return rows[lo:hi + 1]
            except (ValueError, IndexError, TypeError):
                return rows
        return rows

    # ── worker-pool accounting (architect EXCLUDED) ──
    def _pool(self):
        return [w for w in self.st.workers
                if w.get("role") in ("engineer", "reviewer")
                and w.get("status") not in ("released",)]

    def _worker_count(self):
        return int(self.st.live_config.get("worker_count")
                   or self.knobs.get("worker_count") or 0)

    def _free_slots(self):
        return max(0, self._worker_count() - len(self._pool()))

    def _all_settled(self):
        # Open in-scope work (incl. unscoped roadmap rows + parked blocks) keeps the run alive.
        for r in self._in_scope_rows():
            if r.get("status") in OPEN_STATUSES and r["id"] not in self._dropped():
                return False
        if self.st.gate:
            return False
        if self.st.architect_queue:
            return False
        arch = self._architect()
        if arch and arch.get("status") == "busy":
            return False
        if self._due_cadence():
            return False
        return not self._pool()

    def _dropped(self):
        return self.st.data.setdefault("dropped", [])

    # ── dispatch handlers (spawn == dispatch) ──
    def _reserve(self, worker):
        """Commit a worker record (status 'spawning') + persist BEFORE the spawn side-effect.
        A crash after this leaves a durable in-progress reservation — the next tick won't
        re-dispatch (has_active_worker), and the liveness sweep recovers the dead reservation."""
        self.st.workers.append(worker)
        self.st.save()

    def _dispatch_engineer(self, block):
        # No status write — TRON owns no pipeline. The active worker record IS the in-flight
        # marker; the agent moves the block to 🔄 on trunk itself.
        idx = reader.status_index(self.st.pipeline)
        row = self.st.row(block)
        if not row or not self._available(row, idx):
            return
        wid = self._worker_id("engineer", block)
        w = {"id": wid, "role": "engineer", "session_id": "", "shortid": "",
             "spawned_at": util.now_iso(), "status": "spawning", "block": block}
        self._reserve(w)                               # durable intent before spawn
        session, short = self._spawn(
            wid, "spawn.engineer",
            {"worker_id": wid, "block": block, "branch": self._branch(block)},
            role="engineer", block=block)
        w["session_id"], w["shortid"], w["status"] = session, short, "working"
        self.st.record_dispatch(wid, session, block, self._branch(block), 1)
        self.events.event("dispatch", actor=wid, block=block, role="engineer",
                          session=session, attempt=1)
        self.emit("terminal.dispatched", {"worker_id": wid, "block": block})
        self.log("flow", f"build:block:next -> dispatch {wid} on {block}")

    def _redispatch(self, block):
        """Recovery: re-spawn an engineer on a block whose prior worker died, even if the
        agent had already moved it to 🔄 on trunk (TRON's worker/PR tracking is the real
        in-flight authority). Skips if it's done, parked, has a live PR, or deps unmet."""
        row = self.st.row(block)
        if not row or row.get("status") not in OPEN_STATUSES:
            return
        idx = reader.status_index(self.st.pipeline)
        if not all(idx.get(d) == "done" for d in row.get("depends_on", [])):
            return
        if (block in self.st.blocked or block in self._dropped()
                or block in self.st.gate
                or self._block_branch(block) in (self.st.open_prs or {})
                or self.st.has_active_worker_for_block(block)):
            return
        wid = self._worker_id("engineer", block)
        w = {"id": wid, "role": "engineer", "session_id": "", "shortid": "",
             "spawned_at": util.now_iso(), "status": "spawning", "block": block}
        self._reserve(w)
        session, short = self._spawn(
            wid, "spawn.engineer",
            {"worker_id": wid, "block": block, "branch": self._branch(block)},
            role="engineer", block=block)
        w["session_id"], w["shortid"], w["status"] = session, short, "working"
        self.st.record_dispatch(wid, session, block, self._branch(block), 2)
        self.events.event("dispatch", actor=wid, block=block, role="engineer",
                          session=session, attempt=2, recovery=True)
        self.log("flow", f"recover -> re-dispatch {wid} on {block}")

    def _dispatch_reviewer(self, typ):
        self.st.cadence[typ] = 0                       # consume the counter on dispatch
        wid = self._worker_id("reviewer", typ)
        thresh = self.cadence_cfg.get(typ, 0)
        w = {"id": wid, "role": "reviewer", "rtype": typ, "session_id": "", "shortid": "",
             "spawned_at": util.now_iso(), "status": "spawning", "block": f"review:{typ}"}
        self._reserve(w)                               # durable intent before spawn
        session, short = self._spawn(
            wid, "spawn.reviewer", {"worker_id": wid, "count": thresh}, role="reviewer", rtype=typ)
        w["session_id"], w["shortid"], w["status"] = session, short, "working"
        self.events.event("dispatch", actor=wid, block=f"review:{typ}", role="reviewer",
                          session=session, rtype=typ)
        self.emit("terminal.review", {"count": thresh})
        self.log("flow", f"cadence:{typ} -> review:{typ}")

    def _spawn(self, wid, template_id, slots, role=None, block=None, rtype=None):
        prompt = self.renderer.render(template_id, slots)
        if role:
            prompt = prompt + "\n\n" + self._handover(role, block, rtype)
        if self.dry:
            return "dry", "dry"
        try:
            rec = jobs.spawn_detached(wid, prompt, cwd=self.paths["root"])
        except Exception as e:
            self.events.failure(                          # forensic record (AC-2/AC-6)
                "dispatch-fail", "spawn-failed", "spawn a worker process",
                f"{type(e).__name__}: {e}", actor=wid, block=block,
                inputs={"template": template_id, "role": role, "rtype": rtype},
                node="SWITCHBOARD dispatch", next_action="crash (reservation recovered next sweep)")
            raise
        return rec.get("session_id", ""), rec.get("shortid", "")

    def _handover(self, role, block, rtype=None):
        """Technical kickoff appended to the spawn line. TRON ships no persona — it points
        the worker at the PROJECT's agent file and adds only its thin dispatch/report
        protocol (decision #11). Kept out of messages.yaml."""
        agent_file = self._agent_file(rtype and f"reviewer-{rtype}" or role) or self._agent_file(role)
        report = self.ctx.p("scripts", "report.sh")
        lines = [f"Method: read {agent_file} (your persona) and follow it.",
                 f'Report to TRON: bash {report} <your-id> "<message>"']
        if block and not str(block).startswith("review:"):
            lines.append(f"Block {block} is yours alone. Create + name your own branch+worktree off "
                         f"trunk (per the project's convention) and report the name to me — I track "
                         f"your PR/CI by the name you choose, I never assume one.")
            lines.append("Drive it to DONE per its Block Completion Gate. Report DONE only "
                         "with a clean Completion Report — TRON gates on the evidence on trunk, "
                         "not your word: merge, re-validate, deploy-clean, then flip ✅ + archive.")
        return "\n".join(lines)

    def _agent_file(self, role):
        for a in (self.project.get("agents") or []):
            if a.get("role") == role and a.get("file"):
                return os.path.join(self.paths["root"], a["file"])
        ptr = (self.project.get("pointers") or {}).get("agents", "")
        return os.path.join(self.paths["root"], ptr, f"{role}.md") if role else ""

    # ── table handlers (trigger -> step) ──
    def _h_bootup(self, m):
        # tron:start: the deterministic part of protocol:bootup, then pulse.
        if (self.comp.get("session", {}).get("persistent_architect")
                and not self._architect()):
            self._spawn_architect()
        self._emit("pulse")

    def _h_dispatch_engineer(self, m):
        # Reached only if a build:block:next trigger arrives generically; SWITCHBOARD
        # normally calls _dispatch_engineer with a resolved block. Resolve "next".
        block = m.get("block")
        if not block:
            sel = self._select_work()
            block = sel[1] if sel and sel[0] != "cadence" else None
        if block:
            self._dispatch_engineer(block)

    def _h_dispatch_reviewer(self, m):
        if m.get("type"):
            self._dispatch_reviewer(m["type"])

    def _h_worker_done(self, m):
        # block:next:done — the worker SAYS it's done. Not truth: open/advance the DONE gate.
        # The block is done only when it shows ✅ on trunk (_on_block_done, via refresh).
        block = m.get("block")
        if not block:
            return
        row = self.st.row(block)
        if row and row.get("status") == "done":          # already landed — finalize is idempotent
            return
        g = self.st.gate.setdefault(block, {"stage": None, "pr": None})
        self._drive_gate(block, g, reason="worker reported done")
        self._emit("pulse")

    def _h_release_reviewer(self, m):
        # review:<type>:done fans out: Release reviewer (-> pulse) AND architect Log Review.
        typ = m.get("type")
        block = m.get("block")
        for w in list(self.st.workers):
            if w.get("role") == "reviewer" and w.get("rtype") == typ:
                self._release_worker(w)
        if self._architect():                       # no architect -> nothing drains a log job
            self.st.architect_queue.append({"kind": "log", "type": typ, "block": block})
            self._pump_architect()
        self._emit("pulse")

    def _h_forward_review(self, m):
        if m.get("block"):
            self._forward_review(m["block"])

    def _h_reconcile(self, m):
        # block:<block>:reconciled — the architect finished clearing the path ahead (M-05):
        # `forward` authored a missing block file, `reconcile` re-checked an existing one against
        # a just-finished block's drift, `logged` shaped adhoc blocks. No status write: the file
        # lands on trunk via the architect's PR, seen on the next refresh. Record the block as
        # reconciled (lifts its readiness gate, _reconcile_pending), advance the queue, pulse.
        arch = self._architect()
        cur = arch.get("current_job") if arch else None
        blk = m.get("block") or (cur or {}).get("block")
        if blk and blk != "adhoc" and blk not in self.st.reconciled:
            self.st.reconciled.append(blk)
        self._architect_advance()
        self._emit("pulse")

    def _h_await(self, m):
        # worker:await:<block> — a worker paused mid-block for go-ahead (R-AWAIT / TD-03). The
        # rung is chosen DETERMINISTICALLY (no second LLM judgment); classify only tagged + pulled
        # slots. Three rungs, and rung (a) NEVER auto-clears:
        #   (a) operator pre-registered a checkpoint here  -> operator (parked case);
        #   (b) a scope/blueprint judgement                -> the architect;
        #   (c) nothing substantive                        -> deterministic auto-ack (proceed).
        block = m.get("block")
        worker_id = m.get("worker_id")
        detail = m.get("detail", "")
        kind = (m.get("kind") or "").lower()
        sess = self._session_for_worker(worker_id) or self._session_for_block(block)
        if self._is_checkpoint(block, m):                                   # rung (a)
            case_id = self._open_case(block, "await", worker_id, detail)
            self.emit("escalate.await",
                      {"worker_id": worker_id or "?", "block": block or "?",
                       "detail": detail, "case": case_id})
            if self._tg_on():
                self.emit("tg.escalate", {"worker_id": worker_id or "?", "detail": detail})
        elif kind in ("scope", "blueprint", "design") or (self._architect() and kind != "trivial"):
            self._triage_to_architect(f"await[{block or '?'}]: {detail}")    # rung (b)
        else:                                                               # rung (c)
            if sess and sess != "dry" and not self.dry:
                jobs.send(sess, "Proceed — no checkpoint registered here and nothing to escalate.")
            self.log("await", f"auto-ack {worker_id or '?'} on {block or '?'}")
        self._emit("pulse")

    def _is_checkpoint(self, block, m):
        """Rung (a): an operator-pre-registered checkpoint. Registered out-of-band (a project/
        block declaration or an operator `checkpoint <block>` command -> st.checkpoints), or the
        classifier pulled an explicit `checkpoint` flag. Deterministic state lookup, never a model
        call. This rung always reaches the operator — it must never auto-clear."""
        if m.get("checkpoint") is True:
            return True
        return bool(block) and block in (self.st.data.get("checkpoints") or [])

    def _session_for_worker(self, worker_id):
        w = next((w for w in self.st.workers if w.get("id") == worker_id), None)
        return w.get("session_id") if w else None

    def _open_case(self, block, kind, worker_id, detail):
        """Stamp a correlation id on a parked operator case (02-10). The reply carries it back and
        02-08 Settle applies it ≤1 tick later (_h_apply_decision)."""
        case_id = self.st.next_case_id(block or kind)
        self.st.pending_cases[case_id] = {
            "block": block, "kind": kind, "worker_id": worker_id,
            "detail": detail, "raised_at": util.now_iso(), "decision": None}
        return case_id

    def _h_escalate(self, m):
        # wall:raised:<block> — Escalate: free the slot, park the block (runtime), contact operator.
        block = m.get("block")
        worker_id = m.get("worker_id")
        if block and block in self.st.blocked:
            return                                      # already escalated — idempotent
        freed = worker_id
        for w in list(self.st.workers):
            if w.get("role") not in ("engineer", "reviewer"):
                continue
            if (block and w.get("block") == block) or (worker_id and w.get("id") == worker_id):
                freed = w.get("id")
                self._release_worker(w, notify=False)
        if block:
            if block not in self.st.blocked:
                self.st.blocked.append(block)
            self.st.gate.pop(block, None)
        detail = m.get("detail", "wall")
        case_id = self._open_case(block, "wall", freed, detail)   # correlation id (02-10) for the reply
        self.events.event("escalate", actor=freed or "?", block=block, cid=case_id,
                          tag="worker.wall", detail=detail)
        self.emit("escalate.wall", {"worker_id": freed or "?", "block": block or "?",
                                    "detail": detail, "case": case_id})
        if self._tg_on():
            self.emit("tg.escalate", {"worker_id": freed or "?", "detail": detail})
        self._emit("pulse")

    def _h_apply_decision(self, m):
        # operator:decision:<block> — 02-08 SETTLE: apply the operator's reply to a parked case.
        # The reply carries the correlation id stamped at escalation (02-10); resolve the case by
        # it (or by block), write the decision onto the record, then act — in THIS tick (≤1 tick
        # after the reply landed in the hopper). resume | amend | abandon. (No merge sign-off
        # decision: the operator-approves-before-merge model is removed — D5/TD-02.)
        decision = (m.get("decision") or "").lower()
        case = self._resolve_case(m.get("case"), m.get("block"))
        block = (case or {}).get("block") or m.get("block")
        if case is not None:
            case["decision"] = decision                  # Settle writes the reply onto the pending record
        if case is not None and case.get("kind") in ("merge_staging", "promote_main"):
            # A two-gate merge-gate go-ahead (T1) — not a block park. Grant the gate and re-drive
            # (resume), or drop the block (abandon). The engineer never left; nothing to un-park.
            kind = case["kind"]
            g = self.st.gate.get(block)
            if g is not None and decision in ("resume", "approve"):
                g["approved_" + kind] = True
                g.pop("case_" + kind, None)
                self._close_case(m.get("case"), case)
                self._drive_gate(block, g, reason=f"{kind} approved")
            elif decision == "abandon":
                self.st.gate.pop(block, None)
                if block not in self._dropped():
                    self._dropped().append(block)
                self._close_case(m.get("case"), case)
            else:
                self._close_case(m.get("case"), case)    # unknown reply — drop the case, leave the hold
            self.log("flow", f"merge-gate {kind}[{block}] -> {decision}")
            self._emit("pulse"); return
        if not block:
            self._close_case(m.get("case"), case)
            self._emit("pulse"); return
        if decision == "resume" and block in self.st.blocked:
            self.st.blocked.remove(block)                 # back in the dispatch pool (still 📋 on trunk)
        elif decision == "amend" and block in self.st.blocked:
            self.st.blocked.remove(block)
            self._forward_review(block)                   # architect re-scopes the block file
        elif decision == "abandon":
            if block not in self._dropped():
                self._dropped().append(block)             # runtime skip; TRON never writes ❌
            if block in self.st.blocked:
                self.st.blocked.remove(block)
            self.st.gate.pop(block, None)
        self._close_case(m.get("case"), case)
        self.log("flow", f"operator:decision:{block} -> {decision}")
        self._emit("pulse")

    def _resolve_case(self, case_id, block):
        """Find the parked case the reply settles — by correlation id (preferred) or by block."""
        if case_id and case_id in self.st.pending_cases:
            return self.st.pending_cases[case_id]
        if block:
            for c in self.st.pending_cases.values():
                if c.get("block") == block and c.get("decision") is None:
                    return c
        return None

    def _close_case(self, case_id, case):
        if case_id and case_id in self.st.pending_cases:
            self.st.pending_cases.pop(case_id, None)
            return
        for cid, c in list(self.st.pending_cases.items()):
            if c is case:
                self.st.pending_cases.pop(cid, None)
                return

    def _h_recover(self, m):
        # worker:stalled — Recover: free the slot, then re-arm the lost work.
        wid = m.get("worker_id")
        for w in list(self.st.workers):
            if not wid or w.get("id") == wid:
                block, role, rtype = w.get("block"), w.get("role"), w.get("rtype")
                self._release_worker(w, notify=False)
                if role == "reviewer" and rtype:
                    self.st.cadence[rtype] = max(self.st.cadence.get(rtype, 0),
                                                 self.cadence_cfg.get(rtype, 0))
                elif block and not str(block).startswith("review:"):
                    stalls = self.st.counters.setdefault("stalls", {})
                    stalls[block] = stalls.get(block, 0) + 1
                    if stalls[block] > 2:
                        self._emit("wall:raised:" + block,
                                   {"block": block, "worker_id": wid,
                                    "detail": "repeated stall"})
                    else:
                        self._redispatch(block)
        self._emit("pulse")

    def _h_session_end(self, m):
        self._end_session()

    def _h_sentry(self, m):
        # SENTRY — the `*` reactive catch-all. Log the unexpected input and hand it to the architect
        # to sort (solvable -> architect handles it; truly the operator's -> architect escalates).
        # TRON makes NO flow-steering LLM judgment here (the old second-judgment tool was retired);
        # the architect, with project context, is the only thing that steers it.
        raw = m.get("_trigger", "*")
        text = m.get("detail", "")
        self.log("sentry", f"unmatched trigger '{raw}': {text[:160]}")
        self._triage_to_architect(text[:160] or raw)
        self._emit("pulse")

    # ── the DONE gate (realign §F): drive an agent through the canon 6-stage flow on EVIDENCE ──
    def _drive_gates(self):
        for block in list(self.st.gate.keys()):
            self._drive_gate(block, self.st.gate[block])

    def _drive_gate(self, block, g, reason=None):
        """Drive the worker through the DONE gate (T4) on EVIDENCE — never its `✅`, never bare
        trunk presence: validate-local -> authorize-push (PR open) -> CI green on trunk ->
        deploy-if-declared -> ✅. Re-prompt the specific gap on each stage change (gate.step /
        PMT-GATE-DONE). PULSE never merges; the engineer lands it all via PR. Finalization (cadence,
        release) happens in _on_block_done when ✅ actually appears on trunk."""
        row = self.st.row(block)
        if row and row.get("status") == "done":
            return                                       # refresh finalizes; nothing to drive
        if block in self._dropped():
            self.st.gate.pop(block, None)
            return
        branch = self._block_branch(block)               # the worker-named branch (T2), never a guess
        pr = (self.st.open_prs or {}).get(branch)
        sess = self._session_for_block(block)
        deploy = (row or {}).get("deploy")               # honour the block's Deploy: (T2)
        deploy_tail = (f"run the declared deploy ({deploy}) and verify it, then " if deploy else "")
        staging = self.paths.get("staging") or "none"    # two-gate iff a staging branch is declared
        two_gate = staging != "none"
        main = self.paths.get("main_branch", "main")
        renudge = False
        instr = None

        if not pr:
            if not g.get("pr"):
                stage, instr = "validate-local", (
                    f"Validate the block's acceptance suite locally and show the evidence "
                    f"(not just a claim). Then create + name your own branch+worktree off trunk, push, "
                    f"open the PR" + (f" into {staging}" if two_gate else "")
                    + " and tell me the branch name — CI must be green.")
            elif two_gate:
                # First gate cleared: the feature PR merged to staging. Open the SECOND gate (T1) —
                # promote staging -> main, ASK-gated by default. Not "stuck": a distinct gate follows.
                g["staged"] = True
                stage = "promote-main"
                if self._gate_approved(block, g, "promote_main", sess):
                    n = g.get("promote_nudges", 0)
                    if n >= int(self.knobs.get("gate_post_merge_cap", 3)):
                        self.st.gate.pop(block, None)
                        detail = "merged to staging but not promoted to main (✅ pending)"
                        self.events.failure(             # forensic record (AC-2/AC-6): no-silent-stuck wall
                            "gate-stuck", "gate-promote-cap", "promote staging -> main", detail,
                            block=block, inputs={"staging": staging, "main": main, "nudges": n},
                            node="T1/S1-05 promote-gate", attempt=n, next_action="escalate")
                        self._emit("wall:raised:" + block,
                                   {"block": block, "worker_id": self._worker_id("engineer", block),
                                    "detail": detail})
                        return
                    g["promote_nudges"] = n + 1
                    renudge = True
                    instr = (f"{block} is on {staging}. Open the promotion PR {staging} -> {main}, "
                             f"get CI green, merge, {deploy_tail}flip ✅ and archive — all via PR.")
            else:
                # Single-gate no-silent-stuck (T7/S1-05): PR gone, block not ✅ — merged-but-not-landed.
                # Keep a driver, never go quiet; after a cap of unheeded re-nudges, escalate.
                n = g.get("post_merge_nudges", 0)
                if n >= int(self.knobs.get("gate_post_merge_cap", 3)):
                    self.st.gate.pop(block, None)
                    detail = "merged but not landed on trunk (deploy/✅ pending)"
                    self.events.failure(                 # forensic record (AC-2/AC-6): no-silent-stuck wall
                        "gate-stuck", "gate-postmerge-cap", "land merged PR on trunk (✅)", detail,
                        block=block, inputs={"pr": g.get("pr"), "nudges": n},
                        node="T7/S1-05 post-merge-gate", attempt=n, next_action="escalate")
                    self._emit("wall:raised:" + block,
                               {"block": block, "worker_id": self._worker_id("engineer", block),
                                "detail": detail})
                    return
                g["post_merge_nudges"] = n + 1
                renudge = True                           # re-nudge each tick until it lands or escalates
                stage = "post-merge"
                instr = (f"PR #{g.get('pr')} merged but {block} isn't ✅ on trunk yet — "
                         f"{deploy_tail}flip ✅ and archive the block, all via PR.")
        elif pr.get("checks") == "failing":
            stage, instr = "ci", f"CI is RED on PR #{pr.get('number')}. Fix it, push, keep me posted."
        elif pr.get("checks") == "pending":
            stage, instr = "ci-wait", None               # wait for CI; no nudge
        elif two_gate:
            # First gate: feature -> staging, APPROVED by default (TRON instructs the merge unprompted).
            stage = "merge-staging"
            if self._gate_approved(block, g, "merge_staging", sess):
                instr = (f"CI green on PR #{pr.get('number')}. Merge {branch} -> {staging} and "
                         f"re-validate on staging. I'll gate the promotion to {main} next.")
        else:
            stage = "merge"
            instr = (f"CI green on PR #{pr.get('number')}. Merge, re-validate on trunk, "
                     f"{deploy_tail}flip ✅ and archive the block — all via PR."
                     + ("" if deploy else " (No deploy declared.)"))

        if stage != g.get("stage") or renudge:           # nudge on change, or each tick while post-merge
            g["stage"], g["pr"] = stage, ((pr or {}).get("number") or g.get("pr"))
            if instr and sess:
                self.emit("gate.step", {"worker_id": self._worker_id("engineer", block),
                                        "block": block, "detail": instr}, worker_session=sess)
            self.log("flow", f"gate[{block}] -> {stage}" + (f" ({reason})" if reason else ""))

    def _session_for_block(self, block):
        w = next((w for w in self.st.workers
                  if w.get("role") == "engineer" and w.get("block") == block), None)
        return w.get("session_id") if w else None

    def _gate_approved(self, block, g, gate_name, sess):
        """Two-gate approval (T1). APPROVED -> TRON instructs the merge now (returns True). ASK ->
        park ONE operator case and hold (returns False); the engineer waits until the operator
        resumes it (_h_apply_decision). This is the per-project two-gate knob (staging APPROVED ->
        promote ASK by default), NOT a sign-off on every merge — that blanket model is removed
        (D5/TD-02); only an ASK gate stops here, via the standard escalate/decision path."""
        if g.get("approved_" + gate_name):
            return True
        if self.st.approvals.get(gate_name, "APPROVED") == "APPROVED":
            return True
        if not g.get("case_" + gate_name):               # escalate once; then hold quietly each tick
            human = ("promote to " + self.paths.get("main_branch", "main")
                     if gate_name == "promote_main"
                     else "merge to " + (self.paths.get("staging") or "staging"))
            case = self._open_case(block, gate_name, self._worker_id("engineer", block),
                                   f"{human} ({block})")
            g["case_" + gate_name] = case
            self.emit("escalate.gate", {"worker_id": self._worker_id("engineer", block),
                                        "block": block, "detail": human, "case": case})
        return False

    # ── the architect (persistent, queued, forward-only) ──
    def _architect(self):
        return next((w for w in self.st.workers if w.get("role") == "architect"), None)

    def _spawn_architect(self):
        w = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "", "shortid": "",
             "spawned_at": util.now_iso(), "status": "idle", "current_job": None, "block": None}
        self._reserve(w)                               # durable intent before spawn
        session, short = self._spawn("ARCH-PERSIST", "spawn.architect", {}, role="architect")
        w["session_id"], w["shortid"] = session, short

    def _forward_review(self, block):
        # CLEAR AHEAD: enqueue iff not already queued or being authored for this block.
        if any(j.get("kind") == "forward" and j.get("block") == block
               for j in self.st.architect_queue):
            return
        arch = self._architect()
        cur = arch.get("current_job") if arch else None
        if cur and cur.get("kind") == "forward" and cur.get("block") == block:
            return
        self.st.architect_queue.append({"kind": "forward", "block": block})
        self._pump_architect()

    def _triage_to_architect(self, detail):
        # Hand an unclassifiable input to the architect to sort. No architect online
        # -> nobody can steer it but the operator, so escalate directly.
        if any(j.get("kind") == "triage" and j.get("detail") == detail
               for j in self.st.architect_queue):
            return
        if not self._architect():
            self.emit("escalate.unclassified", {"detail": detail})
            return
        self.st.architect_queue.append({"kind": "triage", "detail": detail})
        self._pump_architect()

    def _pump_architect(self):
        arch = self._architect()
        if not arch or arch.get("status") == "busy":
            return
        if not self.st.architect_queue:
            return
        job = self.st.architect_queue.pop(0)
        arch["status"], arch["current_job"] = "busy", job
        sess = arch.get("session_id")
        if job["kind"] in ("forward", "reconcile"):      # both re-check/clear the path ahead (PMT-ARCH-FORWARD)
            self.emit("arch.forward", {"block": job["block"]}, worker_session=sess)
        elif job["kind"] == "triage":
            self.emit("arch.triage", {"detail": job.get("detail", "")}, worker_session=sess)
        else:
            self.emit("arch.log", {"type": job.get("type", "code")}, worker_session=sess)
        self.log("architect", f"dispatch {job}")

    def _architect_advance(self):
        arch = self._architect()
        if arch:
            arch["status"], arch["current_job"] = "idle", None
        self._pump_architect()

    # ── worker release ──
    def _release_worker(self, w, notify=True):
        sess = w.get("session_id")
        if notify and sess and sess != "dry" and not self.dry:
            jobs.send(sess, self.renderer.render("release.worker", {"worker_id": w["id"]}))
        if sess and sess != "dry" and not self.dry:
            jobs.release(sess)
        if w in self.st.workers:
            self.st.workers.remove(w)

    # ── inbound classification + side handlers ──
    def _ingest(self, tag, slots, sender):
        action = self.tags.get(tag)
        if not isinstance(action, dict):
            self.log("flow", f"unknown tag '{tag}'")
            return
        if sender.get("id") and not slots.get("worker_id"):
            slots = {**slots, "worker_id": sender["id"]}
        if "trigger" in action:
            self._emit(self._fill_trigger(action["trigger"], slots), slots)
        elif "side" in action:
            self._side(action["side"], slots, sender)

    def _fill_trigger(self, trigger, slots):
        return (trigger.replace("<block>", str(slots.get("block", "")))
                       .replace("<type>", str(slots.get("type", ""))))

    def _side(self, handler, slots, sender):
        if handler == "reply_digest":
            self.emit("tg.status_digest", {"detail": self._digest()})
        elif handler == "answer_from_context":
            self.log("side", f"question_tron: {slots.get('detail', '')}")
        elif handler == "record_branch":
            self._record_branch(slots)
        elif handler in ("edit_self", "best_effort"):
            self.log("side", f"{handler}: {slots}")
        # observe / none: deliberately nothing.

    def _record_branch(self, slots):
        """The worker reported the branch it NAMED for its block (T2). Record it so the DONE gate
        resolves the block's PR/CI by the real name — TRON never guesses `feat/<block>`."""
        block, branch = slots.get("block"), slots.get("branch")
        if not block or not branch:
            return
        self.st.branches[block] = branch
        for w in self.st.workers:                      # stamp it on the owner record too
            if w.get("block") == block and w.get("role") == "engineer":
                w["branch"] = branch
        self.log("flow", f"branch[{block}] = {branch} (worker-named)")

    def _tg_on(self):
        return str((self.project.get("notifications") or {}).get("telegram") or "").lower() == "on"

    def _digest(self):
        running = [w["id"] for w in self._pool() if w.get("status") == "working"]
        done = sum(1 for r in self.st.pipeline if r.get("status") == "done")
        return f"{len(running)} running, {done} done on trunk"

    # ── liveness sweep (engine side-system, deterministic — no LLM) ──
    def _sweep(self):
        if self.dry:
            return
        idx = jobs.index()
        last = (self.st.data.get("last_sweep") or {}).get("at")
        ping = int(self.knobs.get("silence_ping_min", 6))
        esc = int(self.knobs.get("silence_escalate_min", 8))
        for w in list(self.st.workers):
            if w.get("status") == "released":
                continue
            sess = w.get("session_id")
            alive = bool(sess) and sess != "dry" and jobs.is_alive(w.get("id"), idx)
            if w.get("role") == "architect":
                if not alive:                    # persistent: died or never confirmed -> restore
                    self.st.workers.remove(w)
                    self._spawn_architect()
                continue
            if not alive:
                self._emit("worker:stalled", {"worker_id": w.get("id")})
                continue
            sig = jobs.activity_signals(w.get("id"), since_iso=last, idx=idx)
            if jobs.has_positive_activity(sig):
                continue
            delta = sig.get("last_activity_delta_s")
            if delta is None:
                continue
            if delta > esc * 60:
                self._emit("worker:stalled", {"worker_id": w.get("id")})
            elif delta > ping * 60 and not w.get("pinged_at"):
                w["pinged_at"] = util.now_iso()
                self.emit("heartbeat.ping", {"worker_id": w.get("id")}, worker_session=sess)

    # ── inbound channels (at-least-once: read now, truncate only after a clean save) ──
    def _inbox_paths(self):
        return ((self.ctx.worker_inbox, "worker"),
                (self.ctx.operator_inbox, "operator"),
                (self.ctx.tg_inbox, "operator"))

    def _raw_lines(self, path):
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            return fh.readlines()

    def _claim_inboxes(self):
        """Rotate each inbox to a `.proc` sidecar (an atomic rename), then read the sidecar.
        Workers append via `report.sh >>` (open-write-close per line, O_CREAT): an append that
        lands after the rename creates/extends a fresh inbox and is read next tick — never lost
        to a full-file rewrite (the old #6 race, whose window spanned the classify LLM call).
        A `.proc` left by a crashed tick is read again (at-least-once; idempotency guards make
        replay safe). Returns (claimed_sidecars, msgs)."""
        claimed, msgs = [], []
        for path, kind in self._inbox_paths():
            proc = path + ".proc"
            if not os.path.exists(proc):           # no crash residue -> claim the live inbox
                if not os.path.exists(path):
                    continue
                try:
                    os.rename(path, proc)          # atomic; new appends go to a fresh inbox
                except OSError:
                    continue
            claimed.append(proc)
            for line in self._raw_lines(proc):
                line = line.strip()
                if not line:
                    continue
                try:
                    msgs.append(self._normalize(json.loads(line), kind))
                except json.JSONDecodeError:
                    continue
        return claimed, msgs

    def _release_claimed(self, claimed):
        # Drop the sidecars only after state is saved (at-least-once): a crash before this
        # leaves them for the next tick to reprocess.
        for proc in claimed:
            try:
                os.remove(proc)
            except OSError:
                pass

    def _normalize(self, m, kind):
        if "text" in m and "sender" in m:
            return m
        text = m.get("text") or (m.get("message", {}) or {}).get("text", "") or str(m)
        return {"text": text, "sender": {"kind": kind, "id": m.get("id")}}

    def _classify(self, msg):
        payload = {"text": msg.get("text", ""), "sender": msg.get("sender", {})}
        sender = msg.get("sender", {})
        raw = msg.get("text", "")
        ok, out, attempts = judge.call("classify_message", payload, self.ctx, self._max_retries)
        if not ok:
            # By design, an exhausted classify is double-recorded: a `classify-fail` failure
            # (the deterministic step that failed) AND an `unclassified` record (the message still
            # routes to the architect via the `*` catch-all, and feeds the grammar-learning set, T3).
            last = str(attempts[-1])[:200] if attempts else ""
            self.log("invalid-output", f"classify exhausted: {last}")
            self.events.failure(                          # forensic record (AC-2/AC-6)
                "classify-fail", "classify-exhausted", "classify inbound message",
                f"invalid-output budget exhausted; last: {last}",
                actor=sender.get("id") or sender.get("kind") or "unknown",
                inputs={"text": raw[:200], "attempts": len(attempts)},
                node="§4 classify", attempt=len(attempts), next_action="auto-ack -> unclassified")
            self.events.unclassified(raw, "classify exhausted (invalid-output budget)", sender=sender)  # T3
            return "unclassified", {"detail": raw[:120]}
        tag = out["tag"]
        if tag == "unclassified":                         # the model itself found no matching tag (T3)
            self.events.unclassified(raw, "model returned unclassified (no tag matched)", sender=sender)
        return tag, out.get("slots", {})

    # ── lifecycle ──
    def _reset_session_runtime(self):
        """A fresh `tron start` (started_at was None — not a reconnect) begins a clean run:
        drop the disposable per-session state (stale worker records from the prior run, gates,
        parks, drops, approvals, cadence, counters, parked cases, reconcile gates, run-control)
        and keep only `seen_done`, so already-✅ blocks never re-trigger a review. The pipeline
        cache is rebuilt by the refresh that follows."""
        self.st.data["active_workers"] = []
        self.st.data["architect_queue"] = []
        self.st.data["gate"] = {}
        self.st.data["blocked"] = []
        self.st.data["dropped"] = []
        self.st.data["cadence"] = {}
        self.st.data["counters"] = {}            # T9/S1-12: stall-count (+ case-seq, refresh-fail) must not leak across sessions
        self.st.data["pending_cases"] = {}
        self.st.data["reconciled"] = []
        self.st.data["checkpoints"] = []
        self.st.data["branches"] = {}            # worker-named branches don't carry across sessions (T2)
        self.st.data["approvals"] = dict(DEFAULT_APPROVALS)
        self.st.run_control = None

    def start(self, worker_count):
        self.st.data.setdefault("session", {})["started_at"] = util.now_iso()
        self.st.live_config["worker_count"] = worker_count
        self.knobs["worker_count"] = worker_count
        self._reset_session_runtime()        # clean slate; no stale architect/approvals carry over
        self._refresh_from_trunk(count=False)  # load the view + PRs WITHOUT counting ✅ history
        if self.ended:                       # bootup refresh hit a dead trunk (A2) -> halted loud
            self.st.save()
            return
        # ── first-run gateway (ND-01): is there anything to supervise? ──
        gate = self._bootup_gateway()
        if gate is not None:                 # empty-pipeline | scope-typo -> clean end, spawn no agents
            self.emit("terminal.plan_first" if gate == "empty-pipeline" else "terminal.scope_unknown",
                      {"detail": self._scope_detail()})
            self._end_session()              # archives the barely-born MANIFEST, resets started_at
            self.st.save()
            return
        self._seed_seen_done()               # pre-existing ✅ are already-counted, never re-reviewed
        self._tq = []
        self.events.event("session_start", scope=self._scope_detail(),
                          worker_count=worker_count)
        self.emit("session.start", {})
        self._emit("tron:start")             # _h_bootup now spawns a live architect (no stale record)
        self._drain_triggers()
        self.st.save()

    # ── bootup gateway + clean-end archive (ND-01 / T3) ──
    def _bootup_gateway(self):
        """First-run gateway. Returns a reason NOT to start, or None to proceed:
          'empty-pipeline' — no canon work exists yet (no block files) -> operator must plan first;
          'scope-typo'     — a range/phase scope names something the pipeline doesn't contain.
        An *empty but valid* scope (e.g. everything in range already ✅) is legitimate on a first
        run (A3) -> None; the run starts, idles, and ends cleanly."""
        rows = self.st.pipeline
        if not rows or not any(r.get("has_block_file") for r in rows):
            return "empty-pipeline"
        sc = self.st.scope or {}
        mode, val = sc.get("mode", "all"), sc.get("value")
        if mode == "phase":
            want = str(val or "").strip().lower()
            if want and not any(want in str(r.get("phase") or "").lower() for r in rows):
                return "scope-typo"
        elif mode == "range":
            ids = [r["id"] for r in rows]
            for end in (val or [])[:2]:
                if end and end not in ids:
                    return "scope-typo"
        return None

    def _scope_detail(self):
        sc = self.st.scope or {}
        return f"{sc.get('mode', 'all')}:{sc.get('value')}" if sc.get("value") else sc.get("mode", "all")

    def _is_first_run(self):
        """Empty-archive signal: no prior MANIFEST archived -> this is a first run, not a resume."""
        adir = self.ctx.p("archive")
        return not (os.path.isdir(adir) and any(n.startswith("manifest-") for n in os.listdir(adir)))

    def _archive_manifest(self):
        """Clean-end / halt archive step (ND-01-14-08 / H4): snapshot the MANIFEST into the archive
        dir before the run closes — a forensic record, and the empty-archive signal for the next run."""
        try:
            if not os.path.exists(self.ctx.state):
                return
            adir = self.ctx.p("archive")
            os.makedirs(adir, exist_ok=True)
            stamp = util.now_iso().replace(":", "").replace("-", "").replace(".", "")
            with open(self.ctx.state) as src, open(os.path.join(adir, f"manifest-{stamp}.yaml"), "w") as out:
                out.write(src.read())
        except OSError as e:
            self.log("flow", f"manifest archive skipped: {e}")

    def _halt_loud(self, detail, bootup=False):
        """Loud, synchronous halt (A2/T6): never a silent death. Emit the operator line in-band
        (no MANIFEST may exist yet at bootup), archive what state there is, terminate the run."""
        self.emit("terminal.halt_bootup" if bootup else "terminal.halt_trunk", {"detail": detail})
        if self._tg_on():
            self.emit("tg.escalate", {"worker_id": "TRON", "detail": detail})
        self.events.event("halt", detail=detail, bootup=bootup)   # terminal marker on the timeline
        self._archive_manifest()
        self.ended = True
        sess = self.st.data.setdefault("session", {})
        sess["ended_at"] = util.now_iso()
        sess["started_at"] = None
        self.st.run_control = "halt"

    # ── operator run-control (PARLEY ND-09 / R-HALT / T10) ──
    def pause(self):
        """Hard freeze (F1): broadcast pause to every agent, stop all dispatch. Resumable."""
        self.st.run_control = "pause"
        self._broadcast("Pause as soon as you safely can — hold for go-ahead. (TRON)")
        self.emit("terminal.run_control", {"detail": "PAUSED — dispatch frozen; resume to continue."})
        self.st.save()
        return "paused"

    def drain(self):
        """Soft stop (F2): dispatch nothing new; in-flight finishes. Resumable."""
        self.st.run_control = "drain"
        self.emit("terminal.run_control", {"detail": "DRAINING — finishing in-flight, starting nothing new."})
        self.st.save()
        return "draining"

    def resume(self):
        """Lift pause/drain (F3): dispatch restarts on the next tick."""
        self.st.run_control = None
        self._broadcast("Resume. (TRON)")
        self.emit("terminal.run_control", {"detail": "RESUMED — back to normal dispatch."})
        self.st.save()
        return "resumed"

    def halt(self):
        """Terminal stop (F4): end the run, archive the MANIFEST, no resume."""
        self.emit("terminal.run_control", {"detail": "HALT — stopping everything. End of line."})
        self._end_session()
        self.st.save()
        return "halted"

    def rescope(self, mode, value=None):
        """Change the in-scope range mid-run (F5)."""
        self.set_scope(mode, value)
        self.emit("terminal.run_control", {"detail": f"RESCOPED to {mode}:{value}."})
        return "rescoped"

    def _broadcast(self, line):
        if self.dry:
            return
        for w in self._pool():
            sess = w.get("session_id")
            if sess and sess != "dry":
                jobs.send(sess, line)

    def set_scope(self, mode, value=None):
        self.st.data["scope"] = {"mode": mode, "value": value}
        self.st.save()

    def stop(self, force=False):
        active = [w for w in self._pool()
                  if not str(w.get("block", "")).startswith("review:")]
        if (active or self.st.gate) and not force:
            return False, (f"unfinished: {len(active)} worker(s), "
                           f"{len(self.st.gate)} block(s) mid-DONE-gate")
        self._end_session()
        self.st.save()
        return True, "stopped"

    def _end_session(self):
        if self.ended:
            return
        for w in self.st.workers:
            sess = w.get("session_id")
            if sess and sess != "dry" and not self.dry:
                jobs.send(sess, self.renderer.render("release.worker", {"worker_id": w["id"]}))
                jobs.release(sess)
            w["status"] = "released"
        done = sum(1 for r in self.st.pipeline if r.get("status") == "done")
        self.events.event("session_end", done=done)
        self.emit("session.end", {"count": done})
        self.ended = True
        sess = self.st.data.setdefault("session", {})
        sess["ended_at"] = util.now_iso()
        sess["started_at"] = None            # so the next `tron start` bootstraps fresh, not reconnect
        if os.path.exists(self.ctx.current_id):
            os.remove(self.ctx.current_id)
        self.st.save()                       # persist the closing state, then snapshot it
        self._archive_manifest()             # clean-end archive (H4) + empty-archive signal for next run

    def recover(self):
        """Reattach: rebuild live workers from the host job store, re-arm lost work, and
        re-read the canon trunk. No status writes (TRON owns none)."""
        self._refresh_from_trunk()
        idx = jobs.index()
        alive, purged, rebuilt = 0, 0, []
        for w in self.st.workers:
            if jobs.is_alive(w.get("id"), idx):
                rec = jobs.find(w.get("id"), idx) or {}
                w["session_id"] = rec.get("session_id", w.get("session_id"))
                rebuilt.append(w)
                alive += 1
            else:
                purged += 1
                blk = w.get("block")
                if blk and not str(blk).startswith("review:") and w.get("role") != "architect":
                    self._redispatch(blk)              # re-arm the lost block (recovery override)
        self.st.data["active_workers"] = [w for w in self.st.workers
                                          if w in rebuilt or w.get("status") == "spawning"]
        if (self.comp.get("session", {}).get("persistent_architect")
                and not any(w.get("role") == "architect" for w in self.st.workers)):
            self._spawn_architect()
        self.log("recover", f"recovered={alive} purged={purged}")
        self.st.save()
        return alive, purged

    # ── small helpers ──
    def _worker_id(self, role, ref):
        ref = (ref or "").replace("block-", "")
        pfx = {"engineer": "ENG", "architect": "ARCH", "reviewer": "REV"}.get(role, role.upper())
        return f"{pfx}-{ref}" if ref else f"{pfx}-PERSIST"

    def _branch(self, block):
        # The convention SUGGESTION only — the agent owns the real name (T2). Never used to
        # resolve a PR; that goes through _block_branch (the worker-reported name).
        return f"feat/{block}" if block else self.paths.get("main_branch", "main")

    def _block_branch(self, block):
        """The branch TRON resolves the block's PR/CI by: the name the worker REPORTED (it owns
        the name — T2), falling back to the convention only before the worker has reported (no PR
        can exist on trunk yet). TRON never guesses a name it then gates on."""
        return self.st.branches.get(block) or self._branch(block)
