"""fsm — the deterministic spine: PULSE + SWITCHBOARD + the event table.

The engine that owns the flow. Two layers, both deterministic code (NEVER an LLM
call):

  PULSE       the dispatch loop. Re-runs on every `pulse` control signal (bootup,
              slot free, *:clear, review done, recovered, decision applied) and
              drives SWITCHBOARD.
  SWITCHBOARD the per-pulse work selector: FILL SLOTS -> CLEAR AHEAD -> WAIT ->
              SESSION END.

The reactive layer is the event TABLE (`trigger -> handler`, where a handler's
on-complete is itself a trigger; a closed loop). The table mirrors
plans/tron-workflow-v2-skills.csv. The engine emits trigger strings and routes
them most-specific-wins; inbound worker/operator messages become triggers via
routing.yaml's tag map (classify_message is the only inbound LLM call).

The architect is a PERSISTENT agent, EXCLUDED from the worker pool, draining a
FIFO queue serially (forward-only). Engineers + reviewers share the worker pool.

One wake = one bounded tick: sweep liveness, drain inboxes into triggers, drain
the trigger queue to quiescence, persist atomically, exit (contracts §5).
"""
import os
import json

import util
import jobs
import judge
from state import State
from render import Renderer

# ── the event TABLE (mirrors plans/tron-workflow-v2-skills.csv) ──
# pattern -> handler method name; None = worker-activity row (no engine action).
# Module-level so blueprint-lint can validate it against the grammar without
# instantiating the Engine (contracts §9).
TABLE = [
    ("tron:start",                 "_h_bootup"),
    ("build:block:next",           "_h_dispatch_engineer"),
    ("block:next:build",           None),               # engineer building
    ("block:next:done",            "_h_release_engineer"),
    ("review:next:<block>",        "_h_forward_review"),
    ("block:*:clear",              "_h_checkpoint"),
    ("cadence:<type>",             "_h_dispatch_reviewer"),
    ("review:<type>",              None),               # reviewer reviewing
    ("review:<type>:done",         "_h_release_reviewer"),
    ("wall:raised:<block>",        "_h_escalate"),
    ("operator:decision:<block>",  "_h_apply_decision"),
    ("worker:stalled",             "_h_recover"),
    ("session:end",                "_h_session_end"),
    ("*",                          "_h_scripts"),
]


class Engine:
    def __init__(self, ctx):
        self.ctx = ctx
        self.routing = ctx.load_routing()
        self.workflow = ctx.load_workflow()
        self.project = ctx.load_project()
        self.renderer = Renderer(ctx)
        self.st = State(ctx)
        self.tags = self.routing.get("tags", {})
        self.knobs = self.workflow.get("knobs", {})
        self.cadence_cfg = self.workflow.get("cadence", {}) or {}
        self._max_retries = int((self.routing.get("invalid_output") or {}).get("max_retries", 2))
        self.ended = False
        self.dry = bool(os.environ.get("TRON_DRY"))
        self._tq = []   # the trigger queue, drained within one tick
        self.table = TABLE

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
        # No session has started -> nothing to do. The heartbeat may fire (cron is
        # installed at start), but a tick before `tron start` must never sweep,
        # classify, or consume inbox messages into a phantom session.
        if not (self.st.data.get("session") or {}).get("started_at"):
            return self.ended
        self._tq = []
        self._sweep()                                   # engine liveness -> worker:stalled
        consumed, msgs = self._read_inboxes()           # read, but DON'T truncate yet
        for msg in msgs:
            # One malformed message must not abort the tick: that would leave it in the inbox
            # (consume runs only after a clean save) and re-fire it every sweep — a poison pill.
            # Drop the offender, keep going; the rest of the batch still gets processed.
            try:
                tag, slots = self._classify(msg)
                self._ingest(tag, slots, msg.get("sender", {}))
            except Exception as e:
                self.log("flow", f"ingest dropped a message: {e}")
        self._drain_triggers()
        last = self.st.data.setdefault("last_sweep", {})
        last["at"] = util.now_iso()
        last["sweeps_this_session"] = last.get("sweeps_this_session", 0) + 1
        self._pipeline_writeback()                       # mirror status changes back to the pipeline doc
        self.st.save()                                  # persist effects FIRST
        self._consume_inboxes(consumed)                 # then drop consumed lines (at-least-once)
        return self.ended

    def _pipeline_writeback(self):
        """Mirror status changes back to the pipeline doc — the operator's host file or our
        internal pipeline.md — but only when a block status actually changed (contracts §7, §8:
        never a per-tick rewrite)."""
        pl = self.project.get("pipeline") or {}
        mode = pl.get("mode", "internal")
        if mode == "host" and not pl.get("path"):
            return
        sig = [(r.get("id"), r.get("status")) for r in self.st.pipeline]
        if sig == self.st.data.get("_pipe_sig"):
            return
        import hostpipe
        try:
            if mode == "host":
                hostpipe.write_back(os.path.expanduser(pl["path"]), self.st.pipeline)
            else:
                hostpipe.write_internal(self.ctx, self.st.pipeline)
            self.st.data["_pipe_sig"] = sig
        except Exception as e:
            self.log("pipeline", f"{mode} write-back failed: {e}")

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
            # A handler that raises must not abort the whole tick (see tick(): that strands the
            # triggering message in the inbox and re-fires it forever). Log and move on.
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
        return "_h_scripts", {}           # the `*` SCRIPTS catch-all

    # ── PULSE / SWITCHBOARD (the dispatch loop) ──
    def _switchboard(self):
        """One pulse: FILL SLOTS -> CLEAR AHEAD -> WAIT -> SESSION END."""
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
        # 2. CLEAR AHEAD — enqueue the architect for every pending block not queued.
        for row in self.st.pipeline:
            if row.get("status") == "pending":
                self._forward_review(row["id"])
        # 3. WAIT — implicit: nothing dispatchable, re-enter on the next pulse.
        # 4. SESSION END — only when the whole pipeline is settled.
        if self._all_settled():
            self._emit("session:end")

    def _select_work(self):
        """Priority: (a) oldest cleared adhoc · (b) due cadence · (c) next cleared block."""
        adhoc = sorted((r for r in self.st.pipeline
                        if r.get("status") == "cleared" and r.get("kind") == "adhoc"),
                       key=lambda r: str(r.get("id")))
        if adhoc:
            return ("block", adhoc[0]["id"])
        due = self._due_cadence()
        if due:
            return ("cadence", due)
        blocks = sorted((r for r in self.st.pipeline
                         if r.get("status") == "cleared" and r.get("kind") != "adhoc"),
                        key=lambda r: (r.get("order") or 1e9))
        if blocks:
            return ("block", blocks[0]["id"])
        return None

    def _due_cadence(self):
        for typ, thresh in self.cadence_cfg.items():
            if thresh and self.st.cadence.get(typ, 0) >= thresh:
                if not any(w.get("role") == "reviewer" and w.get("rtype") == typ
                           for w in self._pool()):
                    return typ
        return None

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
        live = {"pending", "cleared", "in-progress", "blocked"}
        if any(r.get("status") in live for r in self.st.pipeline):
            return False
        if self.st.architect_queue:
            return False
        arch = self._architect()
        if arch and arch.get("status") == "busy":      # a review/log still in flight
            return False
        if self._due_cadence():
            return False
        return not self._pool()

    # ── dispatch handlers (spawn == dispatch) ──
    def _reserve(self, worker):
        """Commit a worker record (status 'spawning') + persist BEFORE the spawn side-effect.
        A crash after this leaves a durable in-progress reservation — the next tick won't
        re-dispatch (has_active_worker), and the liveness sweep recovers the dead reservation."""
        self.st.workers.append(worker)
        self.st.save()

    def _dispatch_engineer(self, block):
        row = next((r for r in self.st.pipeline if r.get("id") == block), None)
        if not row or row.get("status") != "cleared":
            return
        if self.st.has_active_worker_for_block(block, "engineer"):
            return
        self.st.set_block_status(block, "in-progress")
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
        self.emit("terminal.dispatched", {"worker_id": wid, "block": block})
        self.log("flow", f"build:block:next -> dispatch {wid} on {block}")

    def _dispatch_reviewer(self, typ):
        self.st.cadence[typ] = 0                       # consume the counter on dispatch
        wid = self._worker_id("reviewer", typ)
        thresh = self.cadence_cfg.get(typ, 0)
        w = {"id": wid, "role": "reviewer", "rtype": typ, "session_id": "", "shortid": "",
             "spawned_at": util.now_iso(), "status": "spawning", "block": f"review:{typ}"}
        self._reserve(w)                               # durable intent before spawn
        session, short = self._spawn(
            wid, "spawn.reviewer", {"worker_id": wid, "count": thresh}, role="reviewer")
        w["session_id"], w["shortid"], w["status"] = session, short, "working"
        self.emit("terminal.review", {"count": thresh})
        self.log("flow", f"cadence:{typ} -> review:{typ}")

    def _spawn(self, wid, template_id, slots, role=None, block=None):
        prompt = self.renderer.render(template_id, slots)
        if role:
            prompt = prompt + "\n\n" + self._handover(role, block)
        if self.dry:
            return "dry", "dry"
        rec = jobs.spawn_detached(wid, prompt, cwd=self._repo_root())
        return rec.get("session_id", ""), rec.get("shortid", "")

    def _handover(self, role, block):
        """Technical kickoff appended to the persona spawn line (kept out of messages.yaml)."""
        skill = self.ctx.p("skills", f"{role}.md")
        report = self.ctx.p("scripts", "report.sh")
        lines = [f"Method: read {skill} and follow it exactly.",
                 f'Report to TRON: bash {report} <your-id> "<message>"']
        if block and not str(block).startswith("review:"):
            lines.append(f"Block {block} on branch {self._branch(block)} is yours alone.")
        return "\n".join(lines)

    # ── table handlers (trigger -> step) ──
    def _h_bootup(self, m):
        # tron:start: the deterministic part of protocol:bootup, then pulse.
        if (self.workflow.get("session", {}).get("persistent_architect")
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

    def _h_release_engineer(self, m):
        # block:next:done — Wrap + release engineer: block done, slot freed, cadence ticks.
        # Idempotent: only a real in-progress -> done transition counts (a replayed/duplicate
        # worker.done for an already-done block must NOT re-tick cadence or re-release).
        block = m.get("block")
        row = next((r for r in self.st.pipeline if r.get("id") == block), None)
        if not row or row.get("status") != "in-progress":
            self.log("flow", f"ignored stale block:next:done for {block}")
            return
        self.st.set_block_status(block, "done")
        for w in list(self.st.workers):
            if w.get("role") == "engineer" and w.get("block") == block:
                self._release_worker(w)
        for typ in self.cadence_cfg:                    # every type counter +1 per completed block
            self.st.cadence[typ] = self.st.cadence.get(typ, 0) + 1
        self.emit("terminal.block_done", {"block": block})
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

    def _h_checkpoint(self, m):
        # block:*:clear — Inform TRON: a forward-review or log-review finished.
        block = m.get("block")
        if block == "adhoc":
            specs = m.get("adhoc") or []
            if specs:
                self.st.insert_adhoc_blocks(specs)
        elif block:
            self.st.clear_block(block)                  # pending -> cleared
        self._architect_advance()
        self._emit("pulse")

    def _h_escalate(self, m):
        # wall:raised:<block> — Escalate: free the slot, park the block, contact the operator.
        block = m.get("block")
        worker_id = m.get("worker_id")
        row = next((r for r in self.st.pipeline if r.get("id") == block), None)
        if row and row.get("status") == "blocked":
            return                                      # already escalated — idempotent
        # Free the walled worker: by block (engineer) OR by id (reviewer, whose block is review:<type>).
        freed = worker_id
        for w in list(self.st.workers):
            if w.get("role") not in ("engineer", "reviewer"):
                continue
            if (block and w.get("block") == block) or (worker_id and w.get("id") == worker_id):
                freed = w.get("id")
                self._release_worker(w, notify=False)
        # Park only an engineer's in-progress block; never reopen a done block a reviewer cited.
        if row and row.get("status") == "in-progress":
            self.st.set_block_status(block, "blocked")
        detail = m.get("detail", "wall")
        self.emit("escalate.wall", {"worker_id": freed or "?", "block": block or "?", "detail": detail})
        if self._tg_on():                            # an away operator gets the wall via Telegram too
            self.emit("tg.escalate", {"worker_id": freed or "?", "detail": detail})
        self._emit("pulse")

    def _h_apply_decision(self, m):
        # operator:decision:<block> — resume | amend | abandon.
        block = m.get("block")
        decision = (m.get("decision") or "").lower()
        row = next((r for r in self.st.pipeline if r.get("id") == block), None)
        cur = row.get("status") if row else None
        if row:
            # Guarded so a replayed decision (at-least-once) is a no-op, not a status flip.
            if decision == "resume" and cur == "blocked":
                self.st.set_block_status(block, "cleared")
            elif decision == "amend" and cur == "blocked":
                self.st.set_block_status(block, "pending")   # re-cleared by architect
            elif decision == "abandon" and cur not in ("done", "abandoned"):
                self.st.set_block_status(block, "abandoned")
        self.log("flow", f"operator:decision:{block} -> {decision} (was {cur})")
        self._emit("pulse")

    def _h_recover(self, m):
        # worker:stalled — Recover: free the slot, then re-arm the lost work.
        wid = m.get("worker_id")
        for w in list(self.st.workers):
            if not wid or w.get("id") == wid:
                block, role, rtype = w.get("block"), w.get("role"), w.get("rtype")
                self._release_worker(w, notify=False)
                if role == "reviewer" and rtype:
                    # the cadence was consumed at dispatch — re-arm so SWITCHBOARD re-runs it.
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
                        self.st.set_block_status(block, "cleared")
        self._emit("pulse")

    def _h_session_end(self, m):
        self._end_session()

    def _h_scripts(self, m):
        # `*` catch-all: log the unexpected input; ask assess_wall if it needs the operator.
        raw = m.get("_trigger", "*")
        text = m.get("detail", "")
        self.log("scripts", f"unmatched trigger '{raw}': {text[:160]}")
        ok, verdict, _ = judge.call(
            "assess_wall",
            {"situation": text, "block_ctx": self.st.fsm, "project_operator_only": []},
            self.ctx, self._max_retries)
        if ok and verdict.get("wall"):
            self.emit("escalate.unclassified", {"detail": text[:120] or raw})
        self._emit("pulse")

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
        # CLEAR AHEAD: enqueue iff not already queued or being reviewed for this block.
        if any(j.get("kind") == "forward" and j.get("block") == block
               for j in self.st.architect_queue):
            return
        arch = self._architect()
        cur = arch.get("current_job") if arch else None
        if cur and cur.get("kind") == "forward" and cur.get("block") == block:
            return
        self.st.architect_queue.append({"kind": "forward", "block": block})
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
        if job["kind"] == "forward":
            self.emit("arch.forward", {"block": job["block"]}, worker_session=sess)
        else:
            # A review is a milestone over the cleared range, not a single block — the copy
            # names no block, so don't pass one (it would only ever render as a placeholder).
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
        # The reporting worker's id rides on the message sender (report.sh), not in the
        # classifier's slots — surface it so handlers (escalate/recover) can match by id.
        if sender.get("id") and not slots.get("worker_id"):
            slots = {**slots, "worker_id": sender["id"]}
        if "trigger" in action:
            self._emit(self._fill_trigger(action["trigger"], slots), slots)
        elif "side" in action:
            self._side(action["side"], slots, sender)
        # tick: handled by the sweep, nothing here.

    def _fill_trigger(self, trigger, slots):
        return (trigger.replace("<block>", str(slots.get("block", "")))
                       .replace("<type>", str(slots.get("type", ""))))

    def _side(self, handler, slots, sender):
        if handler == "reply_digest":
            self.emit("tg.status_digest", {"detail": self._digest()})
        elif handler == "answer_from_context":
            self.log("side", f"question_tron: {slots.get('detail', '')}")
        elif handler in ("edit_self", "best_effort"):
            self.log("side", f"{handler}: {slots}")
        # observe / none: deliberately nothing.

    def _tg_on(self):
        return str((self.project.get("notifications") or {}).get("telegram") or "").lower() == "on"

    def _digest(self):
        running = [w["id"] for w in self._pool() if w.get("status") == "working"]
        done = sum(1 for r in self.st.pipeline if r.get("status") == "done")
        return f"{len(running)} running, {done} done"

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
            # A worker is live only with a confirmed, alive session. An empty session is a
            # stale 'spawning' reservation (crashed tick / failed spawn) — treat it as dead.
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
                w["pinged_at"] = util.now_iso()       # one nudge before escalating (silence_ping_min)
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

    def _read_inboxes(self):
        """Return (consumed, msgs): consumed = [(path, n_lines_read)] to truncate post-save."""
        consumed, msgs = [], []
        for path, kind in self._inbox_paths():
            raw = self._raw_lines(path)
            if not raw:
                continue
            consumed.append((path, len(raw)))
            for line in raw:
                line = line.strip()
                if not line:
                    continue
                try:
                    msgs.append(self._normalize(json.loads(line), kind))
                except json.JSONDecodeError:
                    continue
        return consumed, msgs

    def _consume_inboxes(self, consumed):
        """Drop the first N lines we processed; lines appended during the tick survive."""
        for path, n in consumed:
            rest = self._raw_lines(path)[n:]
            util.atomic_write(path, "".join(rest))

    def _normalize(self, m, kind):
        if "text" in m and "sender" in m:
            return m
        text = m.get("text") or (m.get("message", {}) or {}).get("text", "") or str(m)
        return {"text": text, "sender": {"kind": kind, "id": m.get("id")}}

    def _classify(self, msg):
        payload = {"text": msg.get("text", ""), "sender": msg.get("sender", {})}
        ok, out, attempts = judge.call("classify_message", payload, self.ctx, self._max_retries)
        if not ok:
            self.log("invalid-output",
                     f"classify exhausted: {attempts[-1][:200] if attempts else ''}")
            return "unclassified", {"detail": msg.get("text", "")[:120]}
        return out["tag"], out.get("slots", {})

    # ── lifecycle ──
    def start(self, worker_count):
        self.st.data.setdefault("session", {})["started_at"] = util.now_iso()
        self.st.live_config["worker_count"] = worker_count
        self.knobs["worker_count"] = worker_count
        self._load_pipeline()
        self._tq = []
        self.emit("session.start", {})
        self._emit("tron:start")
        self._drain_triggers()
        self.st.save()

    def stop(self, force=False):
        active = [w for w in self._pool()
                  if not str(w.get("block", "")).startswith("review:")]
        in_progress = [r for r in self.st.pipeline if r.get("status") == "in-progress"]
        if (active or in_progress) and not force:
            return False, (f"unfinished: {len(active)} worker(s), "
                           f"{len(in_progress)} in-progress block(s)")
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
        self.emit("session.end", {"count": done})
        self.ended = True
        sess = self.st.data.setdefault("session", {})
        sess["ended_at"] = util.now_iso()
        sess["started_at"] = None            # so the next `tron start` bootstraps fresh, not reconnect
        if os.path.exists(self.ctx.current_id):
            os.remove(self.ctx.current_id)

    def recover(self):
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
                    self.st.set_block_status(blk, "cleared")  # re-dispatchable
        self.st.data["active_workers"] = rebuilt
        if (self.workflow.get("session", {}).get("persistent_architect")
                and not any(w.get("role") == "architect" for w in rebuilt)):
            self._spawn_architect()
        self.log("recover", f"recovered={alive} purged={purged}")
        self.st.save()
        return alive, purged

    # ── small helpers ──
    def _load_pipeline(self):
        # Seed the state mirror from the pipeline doc at session start (contracts §7, §8).
        # host: the operator owns the doc and may hand-edit it between sessions -> always
        #   reparse. internal: TRON owns pipeline.md, but the mirror is saved BEFORE write-back
        #   each tick (see tick()), so a populated mirror is the crash-authority -> only seed
        #   from pipeline.md when the mirror is empty (first start after a seed). Skipping
        #   internal mode entirely left the mirror empty, so a by-the-book internal seed ended
        #   instantly — this is the H1 fix.
        pl = self.project.get("pipeline") or {}
        mode = pl.get("mode", "internal")
        if mode != "host" and self.st.data.get("pipeline"):
            return
        path = pl.get("path") if mode == "host" else self.ctx.pipeline_internal
        if not path:
            self.log("pipeline", f"{mode} pipeline: no path")
            return
        import hostpipe
        try:
            self.st.data["pipeline"] = hostpipe.parse(os.path.expanduser(path))
        except Exception as e:
            self.log("pipeline", f"{mode} parse failed: {e}")

    def _worker_id(self, role, ref):
        ref = (ref or "").replace("block-", "")
        pfx = {"engineer": "ENG", "architect": "ARCH", "reviewer": "REV"}.get(role, role.upper())
        return f"{pfx}-{ref}" if ref else f"{pfx}-PERSIST"

    def _branch(self, block):
        return f"feat/{block}" if block else "main"

    def _repo_root(self):
        return os.path.expanduser((self.project.get("repo") or {}).get("root", self.ctx.dir))
