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
from state import State
from render import Renderer

# ── the event TABLE ──
# pattern -> handler method name; None = worker-activity row (no engine action).
# Module-level so blueprint-lint validates it against the grammar without
# instantiating the Engine (contracts §9).
TABLE = [
    ("tron:start",                 "_h_bootup"),
    ("build:block:next",           "_h_dispatch_engineer"),
    ("block:next:build",           None),               # engineer building
    ("block:next:done",            "_h_worker_done"),   # done is a trigger -> DONE gate (§F)
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

OPEN_STATUSES = ("to-do", "in-progress")   # work that still counts as not-done


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
        self.paths = ctx.repo_paths(self.project)

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
        self._refresh_from_trunk()                       # canon is truth — rebuild the read cache
        self._sweep()                                    # engine liveness -> worker:stalled
        consumed, msgs = self._read_inboxes()            # read, but DON'T truncate yet
        for msg in msgs:
            # One malformed message must not abort the tick: that would leave it in the inbox
            # (consume runs only after a clean save) and re-fire it every sweep — a poison pill.
            try:
                tag, slots = self._classify(msg)
                self._ingest(tag, slots, msg.get("sender", {}))
            except Exception as e:
                self.log("flow", f"ingest dropped a message: {e}")
        self._drive_gates()                              # advance in-flight DONE gates on fresh evidence
        self._drain_triggers()
        last = self.st.data.setdefault("last_sweep", {})
        last["at"] = util.now_iso()
        last["sweeps_this_session"] = last.get("sweeps_this_session", 0) + 1
        self.st.save()                                   # persist effects FIRST
        self._consume_inboxes(consumed)                  # then drop consumed lines (at-least-once)
        return self.ended

    # ── trunk read (realign §5): canon is truth; TRON reads, agents write ──
    def _refresh_from_trunk(self):
        """Fast-forward the trunk checkout, rebuild the pipeline view + PR cache, and
        recognise newly-✅ blocks (count cadence, release their workers). Best-effort:
        a failed fetch reuses the last on-disk snapshot — never block the loop."""
        ok, detail = trunk.refresh(self.paths["root"], self.paths["main_branch"], self.dry)
        if not ok:
            self.log("trunk", f"refresh degraded: {detail}")
        try:
            view = reader.load(self.paths["pipeline"], self.paths["blocks"])
            self.st.set_pipeline(view)
        except Exception as e:
            self.log("trunk", f"read failed (reusing snapshot): {e}")
        self.st.data["open_prs"] = trunk.open_prs(self.paths["root"], self.dry)
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
        self.emit("terminal.block_done", {"block": block})
        self.log("flow", f"{block} ✅ on trunk -> done, cadence++")
        self._emit("pulse")

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
        if self._branch(bid) in (self.st.open_prs or {}):
            return False
        return True

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
                or self._branch(block) in (self.st.open_prs or {})
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
        self.emit("terminal.review", {"count": thresh})
        self.log("flow", f"cadence:{typ} -> review:{typ}")

    def _spawn(self, wid, template_id, slots, role=None, block=None, rtype=None):
        prompt = self.renderer.render(template_id, slots)
        if role:
            prompt = prompt + "\n\n" + self._handover(role, block, rtype)
        if self.dry:
            return "dry", "dry"
        rec = jobs.spawn_detached(wid, prompt, cwd=self.paths["root"])
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
            lines.append(f"Block {block} on branch {self._branch(block)} is yours alone.")
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

    def _h_checkpoint(self, m):
        # block:*:clear — the architect reports it AUTHORED a block file (forward) or shaped
        # adhoc blocks (logged). No status write: the new file lands on trunk via the
        # architect's PR and TRON sees it on the next refresh. Just advance the queue.
        self._architect_advance()
        self._emit("pulse")

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
        self.emit("escalate.wall", {"worker_id": freed or "?", "block": block or "?", "detail": detail})
        if self._tg_on():
            self.emit("tg.escalate", {"worker_id": freed or "?", "detail": detail})
        self._emit("pulse")

    def _h_apply_decision(self, m):
        # operator:decision:<block> — resume | amend | abandon | approve(merge).
        block = m.get("block")
        decision = (m.get("decision") or "").lower()
        if not block:
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
        elif decision in ("approve", "merge"):
            self.st.approvals.setdefault("granted", [])
            if block not in self.st.approvals["granted"]:
                self.st.approvals["granted"].append(block)
            if block in self.st.gate:
                self._drive_gate(block, self.st.gate[block], reason="operator approved merge")
        self.log("flow", f"operator:decision:{block} -> {decision}")
        self._emit("pulse")

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

    # ── the DONE gate (realign §F): drive an agent through the canon 6-stage flow on EVIDENCE ──
    def _drive_gates(self):
        for block in list(self.st.gate.keys()):
            self._drive_gate(block, self.st.gate[block])

    def _drive_gate(self, block, g, reason=None):
        """Bounce the worker forward until the block lands ✅ on trunk. TRON judges on
        evidence (PR existence, CI rollup, trunk state), never the agent's word. It only
        nudges when the stage changes — no per-tick spam. Finalization (cadence, release)
        happens in _on_block_done when ✅ appears on trunk."""
        row = self.st.row(block)
        if row and row.get("status") == "done":
            return                                       # refresh finalizes; nothing to drive
        if block in self._dropped():
            self.st.gate.pop(block, None)
            return
        branch = self._branch(block)
        pr = (self.st.open_prs or {}).get(branch)
        sess = self._session_for_block(block)

        if not pr:
            stage, instr = "pr", ("Local ACs validated? Open the PR for "
                                  f"{branch} (CI must be green).")
        elif pr.get("checks") == "failing":
            stage, instr = "ci", f"CI is RED on PR #{pr.get('number')}. Fix it, push, keep me posted."
        elif pr.get("checks") == "pending":
            stage, instr = "ci-wait", None               # wait for CI; no nudge
        else:
            # CI clean -> merge gate (§8): per-session knob + block Merge:needs-user (raise-only).
            if self._merge_needs_user(block) and not self._merge_granted(block):
                stage = "merge-hold"
                self.emit("escalate.merge",
                          {"block": block, "pr": str(pr.get("number") or "?"),
                           "detail": "CI green; merge needs your sign-off"})
                instr = None
            else:
                stage, instr = "merge", (
                    f"CI green on PR #{pr.get('number')}. Merge, re-validate on trunk, "
                    "deploy-clean + verify, then flip ✅ and archive the block — all via PR.")

        if stage != g.get("stage"):                      # nudge only on change
            g["stage"], g["pr"] = stage, (pr or {}).get("number")
            if instr and sess:
                self.emit("gate.step", {"worker_id": self._worker_id("engineer", block),
                                        "block": block, "detail": instr}, worker_session=sess)
            self.log("flow", f"gate[{block}] -> {stage}" + (f" ({reason})" if reason else ""))

    def _session_for_block(self, block):
        w = next((w for w in self.st.workers
                  if w.get("role") == "engineer" and w.get("block") == block), None)
        return w.get("session_id") if w else None

    def _merge_needs_user(self, block):
        """Raise-only (§8): the session gate ASKs, OR the block stamps Merge: needs-user."""
        row = self.st.row(block) or {}
        if (row.get("merge") or "self").lower() == "needs-user":
            return True
        gate_key = "promote_main" if self.paths.get("staging") == "none" else "merge_staging"
        return str(self.st.approvals.get(gate_key, "APPROVED")).upper() == "ASK"

    def _merge_granted(self, block):
        return block in (self.st.approvals.get("granted") or [])

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

    def _read_inboxes(self):
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
        self._refresh_from_trunk()           # read canon truth before the first pulse
        self._seed_seen_done()               # pre-existing ✅ must not trigger a cadence review
        self._tq = []
        self.emit("session.start", {})
        self._emit("tron:start")
        self._drain_triggers()
        self.st.save()

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
        self.emit("session.end", {"count": done})
        self.ended = True
        sess = self.st.data.setdefault("session", {})
        sess["ended_at"] = util.now_iso()
        sess["started_at"] = None            # so the next `tron start` bootstraps fresh, not reconnect
        if os.path.exists(self.ctx.current_id):
            os.remove(self.ctx.current_id)

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
        if (self.workflow.get("session", {}).get("persistent_architect")
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
        return f"feat/{block}" if block else self.paths.get("main_branch", "main")
