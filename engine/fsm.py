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
import re
import json
import uuid
import hashlib

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
    ("worker:online",              "_h_worker_online"),  # spawned worker checked in -> emit its pending assignment (01-07)
    ("block:next:build",           None),               # engineer building
    ("block:next:done",            "_h_worker_done"),   # done is a trigger -> DONE gate (§F)
    ("block:next:recorded",        "_h_worker_recorded"),  # record receipt (tron-07 W6a) — never a close confirmation
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
# S-1 (tron-07 review cycle): one pacing law. All silence/idle machinery compares WALL-CLOCK
# spans — never tick counts (event ticks arrive in bursts and, under sustained traffic, timer
# ticks may never come at all — R-1). The counter knobs keep their names and their operator
# intuition: they are multipliers of the wake ceiling ("N ticks' worth of time").
# R-2(ii): a presumed-suspended runner (past its own turn ceiling) gets SIGTERM via release,
# then SIGKILL after this grace — never on ordinary release paths.
KILL_GRACE_S = 60.0
# The runner's single-turn wall-clock ceiling — the SAME env the spawned runner reads
# (worker_runner.TURN_TIMEOUT_S), so the sweep's working-turn exemption (tron-07 W8) and
# the runner's own hang protection share one clock.
TURN_CEILING_S = float(os.environ.get("TRON_TURN_TIMEOUT_S", "1800"))
# T3 (D-15-3): the deterministic operator-settle regex — a CASE-<n> id plus a settling verb
# ANYWHERE in the message, in either order (`resume CASE-007` and `CASE-007: resume` both
# hit). Zero-padding-agnostic (`CASE-7` normalizes the same as `CASE-007`, State.next_case_id's
# actual format) since the operator types it by hand.
CASE_ID_RE = re.compile(r"case-0*(\d+)", re.IGNORECASE)
SETTLE_VERB_RE = re.compile(r"\b(approve|resume|abandon)\b", re.IGNORECASE)


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
        self._snapshot_hash = ""                      # hash of the rebuilt trunk-read snapshot (per-tick provenance)
        self._trunk_fault = False                     # T3 (01-16): this tick's trunk read came back blank
        self.events = eventlog.EventLog(ctx, self._log_env)
        jobs.configure(ctx.workers_dir)               # point the worker store at this instance (01-10)

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
    def emit(self, template_id, slots=None, worker_id=None):
        # 01-11 FX-1: every reply-expecting PMT ends in the shared reply line, which renders
        # {report} + {worker_id} — inject both here so every send can carry the channel
        # instruction (str.format ignores what a template doesn't use).
        slots = dict(slots or {})
        if worker_id is not None:
            slots.setdefault("worker_id", worker_id)
        slots.setdefault("report", self.ctx.p("scripts", "report.sh"))
        slots.setdefault("contract", self.ctx.worker_contract)
        line = self.renderer.render(template_id, slots)
        channel = self.renderer.channel(template_id)
        util.append_jsonl(self.ctx.home_log,
                          {"at": util.now_iso(), "channel": channel, "text": line})
        if channel == "worker" and worker_id and not self.dry:
            self._to_worker(worker_id, line, template_id)
        elif channel == "tg" and not self.dry:
            self._tg_send(line)
        else:
            print(line)
        return line

    def _to_worker(self, worker_id, text, kind):
        """Engine -> worker delivery (01-10): append one seq'd line to the worker's mailbox
        (jobs.send), keyed by the STABLE worker id — never the session id. The seq is a per-worker
        monotonic counter on the durable worker record; it is bumped in memory here and persisted
        only at the tick's save(), so an at-least-once re-emit (crash before save) recomputes the
        SAME seq and the runner dedupes it by high-water. No delivery re-opens a session (finding #5).
        `kind` is forensic metadata on the mailbox line (the message's template id / intent)."""
        if self.dry:
            return
        w = next((x for x in self.st.workers if x.get("id") == worker_id), None)
        if not w:
            return
        seq = int(w.get("mbox_seq", 0)) + 1
        w["mbox_seq"] = seq
        jobs.send(self.ctx.worker_dir(worker_id), seq, kind, text)

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
    def tick(self, trigger_source="timer"):
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
        # Per-tick forensic record (01-09): run · tick_seq · trigger_source · trunk_sha ·
        # snapshot_hash · ts. Emitted after refresh so trunk + snapshot are the ones this tick
        # decides on. trigger_source is timer|event|manual — recorded honestly, never inferred.
        self.events.event("tick", trigger_source=trigger_source,
                          snapshot_hash=self._snapshot_hash)
        rc = self.st.run_control
        if rc != "pause":                                # PAUSE freezes liveness pings + gate nudges; DRAIN keeps them
            self._sweep()                                # engine liveness -> worker:stalled
        claimed, msgs = self._claim_inboxes()            # rotate each inbox to a .proc sidecar, read it
        live = {w.get("id") for w in self.st.workers if w.get("status") != "released"}
        for msg in msgs:
            # R-2(i): released is not dead — a stall-recovered or long-turn runner can still
            # write into the shared inbox after release (observed live in tron-10). A report
            # from a worker id not on the live roster is QUARANTINED: logged for forensics,
            # never classified into a trigger — a zombie 'done' must not gate its
            # replacement's block.
            snd = msg.get("sender") or {}
            if snd.get("kind") == "worker" and snd.get("id") and snd["id"] not in live:
                self.log("flow", f"quarantined report from off-roster worker '{snd['id']}'")
                self.events.unclassified(msg.get("text", "")[:200],
                                         f"off-roster sender {snd['id']} (quarantined)", sender=snd)
                continue
            # One malformed message must not abort the tick: that would leave it in the sidecar
            # (released only after a clean save) and re-fire it every sweep — a poison pill.
            try:
                tag, slots = self._classify(msg)
                # Carry the raw text alongside the pulled slots — deterministic guards (the
                # close-confirmation prefix check, tron-07 peer risk 2) read the message
                # itself, never re-judge it.
                slots = {**slots, "_raw": msg.get("text", "")}
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
            self._drive_gates()          # S-1: pacing is wall-clock inside the gate machinery
            self._drive_cases()          # F-4/R-7: parked-case re-ping ladder -> safe-park
            self._drive_landings()       # D1: architect paperwork FIFO, job-queue-independent
            self._drive_architect_liveness()   # 01-13: the job queue gets the same idle law
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
        ok, detail = trunk.refresh(self.paths["root"], self.paths["main_branch"], self.dry,
                                   remote=self.paths.get("remote"))   # F1: thread the remote (absent/none -> local mode)
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
        # T3 (01-16, D-17-1 supporting defect): a trunk sha that comes back blank — whether
        # `ok` or not — is never a valid view to read or reconcile against. The old fallthrough
        # (skip the snapshot pin, fall back to reading the live working-tree paths directly)
        # is exactly what regressed a done block's gate close -> local and re-created phantom
        # gate state on a transient `trunk: ""` tick (observed twice in tron-17, self-healed by
        # luck). Treat it as a FAULT for this tick alone: reuse the last good pipeline/gate
        # view untouched, skip the read/reconcile, and let the caller (tick -> _drive_gates)
        # skip gate re-evaluation too. The A-2 dead-trunk halt above already owns the
        # PERSISTENT case; this is the transient one. A genuinely-first load (no prior
        # snapshot to reuse) still attempts the live read below — there is nothing to reuse.
        self._trunk_fault = bool(not self._trunk_sha and self.st.pipeline)
        if self._trunk_fault:
            self.log("trunk", "empty trunk read this tick (blank sha) -> fault, "
                              "reusing the last snapshot untouched")
            return
        try:
            ppath, bpath = self.paths["pipeline"], self.paths["blocks"]
            if not self.dry and self._trunk_sha:
                # W9 (tron-13): read the PINNED tree, never the working tree — a worker
                # mid-commit in the root checkout (the record commit is one, by our own
                # order) must be invisible until its commit lands. Snapshot failure is a
                # read failure: reuse the last good view, never a dirty read.
                pipe_rel = self.paths.get("pipeline_rel") or "meta/pipeline.md"
                blocks_rel = (self.paths.get("blocks_rel") or "meta/blocks/").rstrip("/")
                oks, errs = trunk.snapshot_tree(
                    self.paths["root"], self._trunk_sha, [pipe_rel, blocks_rel],
                    self.ctx.trunk_snapshot_dir)
                if not oks:
                    raise RuntimeError(f"trunk snapshot failed: {errs}")
                ppath = os.path.join(self.ctx.trunk_snapshot_dir, pipe_rel)
                bpath = os.path.join(self.ctx.trunk_snapshot_dir, blocks_rel)
            view = reader.load(ppath, bpath)
            self.st.set_pipeline(view)
        except Exception as e:
            self.log("trunk", f"read failed (reusing snapshot): {e}")
        self.st.data["open_prs"] = trunk.open_prs(self.paths["root"], self.dry)
        # Per-tick provenance (01-09): a stable hash over the canonical serialization of the
        # rebuilt trunk-read snapshot (pipeline view + PR cache + trunk sha). Lets a trace pin
        # exactly which state a tick decided on, and feeds E1 determinism (same snapshot -> same
        # decisions). Recomputed every refresh; a reused stale snapshot keeps its prior hash.
        snap = {"trunk": self._trunk_sha,
                "pipeline": self.st.pipeline,
                "open_prs": self.st.data.get("open_prs") or {}}
        self._snapshot_hash = hashlib.sha256(
            json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()
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
        """A block reached ✅ on trunk (the only done-truth). Tick cadence, announce, reconcile
        ahead. The engineer is NOT released here (T7): ✅ opens the CLOSE stage — fire CLOSE and
        HOLD the slot until the worker confirms a clean exit. No live engineer -> nothing to close,
        so clear the gate directly."""
        for typ in self.cadence_cfg:
            self.st.cadence[typ] = self.st.cadence.get(typ, 0) + 1
        if block in self.st.blocked:
            self.st.blocked.remove(block)
        self.events.event("block_done", block=block)
        self.emit("terminal.block_done", {"block": block})
        if self._worker_id_for_block(block):
            g = self.st.gate.setdefault(block, {"stage": None, "pr": None})
            self._drive_close(block, g, self._worker_id("engineer", block))
            self.log("flow", f"{block} ✅ on trunk -> CLOSE (slot held), cadence++")
        else:
            self.st.gate.pop(block, None)                # no engineer to close out
            self.log("flow", f"{block} ✅ on trunk -> done (no live engineer), cadence++")
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
        """The next in-scope, not-done, DISPATCHABLE block (by pipeline order) after `done_block`
        that already has a block file — the one a just-finished block's drift could invalidate.
        Must be not-yet-dispatched: a block already mid-execution (🔄 with a live worker/PR, or in
        a DONE gate) is never reconcile-targeted — only a clean, not-yet-started block is (T3)."""
        rows = sorted(self._in_scope_rows(), key=lambda r: r.get("order") or 1e9)
        seen = False
        for r in rows:
            if r["id"] == done_block:
                seen = True
                continue
            if not seen:
                continue
            bid = r["id"]
            if (r.get("status") in OPEN_STATUSES and r.get("has_block_file")
                    and bid not in self._dropped() and bid not in self.st.blocked
                    and not self.st.has_active_worker_for_block(bid)
                    and self._block_branch(bid) not in (self.st.open_prs or {})
                    and bid not in self.st.gate):
                return bid
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
        # T2 (D-15-2): a walled worker is HELD, not released, but it must not occupy a
        # worker_count slot while parked — excluded from work-selection same as "released"
        # (un-held on operator resume, _h_apply_decision).
        return [w for w in self.st.workers
                if w.get("role") in ("engineer", "reviewer")
                and w.get("status") not in ("released", "walled")]

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
        # Pending assignment recorded on the durable worker record (01-07): the SPAWN brings the
        # engineer online; the block is delivered (assign.engineer) on its `online` report. A crash
        # between spawn and assign survives — the pending assignment persists in the MANIFEST.
        w = {"id": wid, "role": "engineer", "session_id": "", "shortid": "",
             "spawned_at": util.now_iso(), "status": "spawning", "block": block,
             "pending_assign": {"kind": "engineer", "block": block,
                                "assignment": self._engineer_assignment(block)}}
        self._reserve(w)                               # durable intent before spawn
        session, short = self._spawn(wid, "spawn.engineer", "engineer", block=block)
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
             "spawned_at": util.now_iso(), "status": "spawning", "block": block,
             "pending_assign": {"kind": "engineer", "block": block,
                                "assignment": self._engineer_assignment(block)}}
        self._reserve(w)
        session, short = self._spawn(wid, "spawn.engineer", "engineer", block=block)
        w["session_id"], w["shortid"], w["status"] = session, short, "working"
        self.st.record_dispatch(wid, session, block, self._branch(block), 2)
        self.events.event("dispatch", actor=wid, block=block, role="engineer",
                          session=session, attempt=2, recovery=True)
        self.log("flow", f"recover -> re-dispatch {wid} on {block}")

    def _dispatch_reviewer(self, typ):
        self.st.cadence[typ] = 0                       # consume the counter on dispatch
        wid = self._worker_id("reviewer", typ)
        thresh = self.cadence_cfg.get(typ, 0)
        assignment = self._reviewer_assignment(typ)    # since-last-review range, then reset the marker (T6)
        w = {"id": wid, "role": "reviewer", "rtype": typ, "session_id": "", "shortid": "",
             "spawned_at": util.now_iso(), "status": "spawning", "block": f"review:{typ}",
             "pending_assign": {"kind": "reviewer", "assignment": assignment}}
        self._reserve(w)                               # durable intent before spawn
        session, short = self._spawn(wid, "spawn.reviewer", "reviewer", rtype=typ)
        w["session_id"], w["shortid"], w["status"] = session, short, "working"
        self.events.event("dispatch", actor=wid, block=f"review:{typ}", role="reviewer",
                          session=session, rtype=typ)
        self.emit("terminal.review", {"count": thresh})
        self.log("flow", f"cadence:{typ} -> review:{typ}")

    def _spawn(self, wid, template_id, role, block=None, rtype=None):
        """Identity-only spawn (01-07 two-step): fill PMT-SPAWN's slots and bring the worker
        online — no assignment. The persona prompt is delivered as the worker's FIRST mailbox
        message (seq 1 -> the runner's turn 1); the work follows on its `online` report (assign.*).
        `persona` (the project's agent file) and `report` (report.sh) ride the SPAWN copy itself
        (delta-only over the project's persona). Returns (session_id, shortid) — the session id is
        engine-minted and stable for the worker's whole life; the shortid is the worker id."""
        persona = self._agent_file(rtype and f"reviewer-{rtype}" or role) or self._agent_file(role)
        slots = {"worker_id": wid, "role": role, "persona": persona}
        if self.dry:
            return "dry", "dry"
        session_id = str(uuid.uuid4())                 # engine-minted; stable identity, never re-minted
        try:
            # 01-13 (tron-14 F7): retire a predecessor's dir BEFORE the first mailbox
            # write — the persona message must land in the FRESH dir, not the one about
            # to be archived (and never under a stale high-water seq).
            jobs.retire_stale_dir(self.ctx.worker_dir(wid))
            # turn 1: the persona/onboarding, via the mailbox — through emit() (S-4/W4:
            # every worker send goes through the one slot-injecting sender).
            self.emit(template_id, slots, worker_id=wid)
            jobs.spawn_runner(wid, self.ctx.worker_dir(wid), session_id, cwd=self.paths["root"])
        except Exception as e:
            self.events.failure(                          # forensic record (AC-2/AC-6)
                "dispatch-fail", "spawn-failed", "spawn a worker process",
                f"{type(e).__name__}: {e}", actor=wid, block=block,
                inputs={"template": template_id, "role": role, "rtype": rtype},
                node="SWITCHBOARD dispatch", next_action="crash (reservation recovered next sweep)")
            raise
        return session_id, wid

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

    def _h_worker_online(self, m):
        # worker:online (01-07 two-step) — a spawned worker checked in. Deliver its pending
        # assignment (assign.engineer / assign.reviewer) to its session, then clear it. Mirrors the
        # architect idle-pump: spawn is identity-only; the work follows on `online`. Crash-safe —
        # the pending assignment is durable on the worker record (set at reserve), so a crash
        # between spawn and assign re-emits cleanly (at-least-once; deduped by the worker already
        # being online). No pending (architect, or already assigned) -> nothing to do.
        wid = m.get("worker_id")
        w = next((x for x in self.st.workers if x.get("id") == wid), None)
        if not w:
            return
        pend = w.get("pending_assign")
        if not pend:
            return
        # ASSIGN is role-neutral (PMT-ASSIGN); the per-role {assignment} was composed at dispatch.
        assignment = pend.get("assignment", "")
        slots = {"worker_id": wid, "assignment": assignment,
                 "merge_path": self._merge_path(pend.get("kind") or "engineer")}   # mode-/role-true (01-11 FX-4)
        if pend.get("kind") == "reviewer":
            self.emit("assign.reviewer", slots, worker_id=wid)
        else:
            self.emit("assign.engineer", slots, worker_id=wid)
        w["pending_assign"] = None
        self.log("flow", f"{wid} online -> assign ({pend.get('kind')})")

    def _engineer_assignment(self, block):
        """The engineer's work string (T2): the block it owns + its spec path. PMT-ASSIGN is
        role-neutral; the engine fills the concrete work here."""
        row = self.st.row(block) or {}
        spec = row.get("block_file") or f"blocks/{block}.md"
        return (f"You own block {block}. Read its spec at {spec}, build it end to end, "
                f"and report when it's ready for the done gate.")

    def _reviewer_assignment(self, typ):
        """The reviewer's work string (T6): the commit range SINCE this type's last review, never
        a block count — so nothing slips between reviews. Read the old marker, compose the range to
        the current trunk HEAD, then reset the marker to HEAD (the reset-on-dispatch)."""
        head = trunk.head_sha(self.paths["root"], self.dry) or ""
        prev = self.st.review_markers.get(typ)
        self.st.review_markers[typ] = head           # reset on dispatch
        if prev and head and prev != head:
            rng = f"{prev}..{head}"
        elif head:
            rng = f"the full history up to {head} (no prior {typ} review)"
        else:
            rng = "all changes since your last review"
        return (f"Run a {typ} review over {rng}. Cover every applicable change in that range — "
                f"all of it, not a sample. Deliver your findings log when done, and open that "
                f"hand-back reply `review done {typ}:` then the log path.")

    def _h_worker_done(self, m):
        # block:next:done — the worker SAYS it's done. Not truth: open/advance the DONE gate.
        # The block is done only when it shows ✅ on trunk (_on_block_done, via refresh).
        block = m.get("block")
        if not block:
            return
        row = self.st.row(block)
        if row is None:
            return                                       # admission (S-2-lite) already refused these
        if row and row.get("status") == "done":
            # ✅ already landed -> this report is the CLOSE clean-confirmation (T7); at stage
            # record it still drives the content-check + close (a done-claim with ✅ visible).
            # Admission (S-2-lite/_admit) has already enforced the `clean` prefix and routed
            # record receipts away — no re-checks here (rider 4).
            g = self.st.gate.get(block)
            if g and g.get("stage") == "close":
                self._confirm_close(block, g)
            elif g and g.get("stage") == "record":
                self._drive_close(block, g, self._worker_id("engineer", block))
            return
        g = self.st.gate.setdefault(block, {"stage": None, "pr": None})
        g.pop("awaiting_rework", None)                # a fresh report -> rework done; re-challenge merge
        before = g.get("stage")
        self._drive_gate(block, g, reason="worker reported done", on_report=True)
        if block in self.st.gate and before is not None and self.st.gate[block].get("stage") == before:
            # No advance on a repeat report = a failed attempt at this step (T9). Cap at N=2.
            n = g.get("stall_attempts", 0) + 1
            g["stall_attempts"] = n
            if n > int(self.knobs.get("gate_step_cap", 2)):
                self._gate_giveup(block, g, self._worker_id("engineer", block),
                                  f"stuck at {before} after {n} attempts",
                                  "gate-step-cap", f"advance DONE gate stage '{before}'")
        else:
            g["stall_attempts"] = 0
        self._emit("pulse")

    def _h_worker_recorded(self, m):
        # block:next:recorded — the record RECEIPT ("recorded <block>"), split from
        # block:next:done (tron-07 W6a): the receipt arriving in the same tick that opened
        # CLOSE was read as the clean-confirmation, ran _confirm_close against a replica the
        # worker had not begun to clean, and burned a close nudge on a spurious rejection.
        # The gate reads trunk truth: ✅ at stage record -> advance to CLOSE; anything else
        # is a receipt to note, never a step.
        block = m.get("block")
        if not block:
            return
        row = self.st.row(block)
        g = self.st.gate.get(block)
        # Admission (S-2-lite) only lets a receipt through while the gate is AT record;
        # trunk truth (row status) still gates the close drive.
        if row and g and g.get("stage") == "record" and row.get("status") == "done":
            self._drive_close(block, g, self._worker_id("engineer", block))
        else:
            self.log("flow", f"record receipt for {block} noted (stage={(g or {}).get('stage')})")
        self._emit("pulse")

    def _h_release_reviewer(self, m):
        # review:<type>:done — the reviewer hands back. First report -> open the DONE-REVIEW gate
        # (attest full coverage since last review; T5), HOLD release. The confirmation report ->
        # release the reviewer + queue the architect remediation (log-review).
        typ = m.get("type")
        block = m.get("block")
        gkey = f"review:{typ}"
        rev = next((w for w in self.st.workers
                    if w.get("role") == "reviewer" and w.get("rtype") == typ), None)
        if self.st.gate.get(gkey) is None:
            self.st.gate[gkey] = {"stage": "review"}
            self.events.event("gate_advance", block=gkey,
                              **{"from": None, "to": "review", "detail": "attest coverage"})
            wid = rev.get("id") if rev else self._worker_id("reviewer", typ)
            if rev:
                self.emit("gate.review", {"worker_id": wid}, worker_id=wid)
            self.log("flow", f"review:{typ} -> DONE-REVIEW gate (attest coverage)")
            self._emit("pulse")
            return
        # 01-13: the attest report arrived — clear any stall machinery it outran (a parked
        # attest case settles itself the moment the report lands; the operator owes nothing).
        g0 = self.st.gate[gkey]
        if g0.get("attest_case"):
            self._close_case(g0.pop("attest_case"), None)
        g0.pop("attest_idle_since", None)
        g0.pop("attest_nudged_at", None)
        # Confirmation -> land declared paperwork BEFORE release (tron-13 D1 point 2):
        # the findings log parked on the reviewer's named branch is landed by the ENGINE
        # (content-checked, ff-only, branch deleted) — say-so provenance ends here. A
        # branch that won't land holds the gate at `landing` (a stage that exists only
        # when a branch was declared — paperwork-less reviews release exactly as before);
        # the wall-clock driver (_drive_review_landing) paces it from here.
        if rev and rev.get("pending_landings"):
            code, detail = self._drain_landings(rev, "reviewer")
            if code == "blocked":
                g = self.st.gate[gkey]
                prev = g.get("stage")
                g["stage"] = "landing"
                g["block"] = block
                self.events.event("gate_advance", block=gkey,
                                  **{"from": prev, "to": "landing", "detail": detail})
                self.log("flow", f"{gkey} paperwork won't land ({detail}) -> hold at landing")
                self._land_nudge(rev.get("id"), detail)
                return
        self._finish_review(typ, block)

    def _finish_review(self, typ, block):
        # Release + remediation — the single exit for a completed review cycle.
        self.st.gate.pop(f"review:{typ}", None)
        for w in list(self.st.workers):
            if w.get("role") == "reviewer" and w.get("rtype") == typ:
                self._release_worker(w, reason="review-complete")
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
        if self._is_checkpoint(block, m):                                   # rung (a)
            case_id = self._open_case(block, "await", worker_id, detail)
            self.emit("escalate.await",
                      {"worker_id": worker_id or "?", "block": block or "?",
                       "detail": detail, "case": case_id})
            if self._tg_on():
                self.emit("tg.escalate", {"worker_id": worker_id or "?", "detail": detail})
        elif kind in ("scope", "blueprint", "design") or (self._architect() and kind != "trivial"):
            self._triage_to_architect(f"await[{block or '?'}]: {detail}",     # rung (b)
                                      sender=worker_id, block=block)
        else:                                                               # rung (c)
            if worker_id and not self.dry:
                self._to_worker(worker_id,
                                "Proceed — no checkpoint registered here and nothing to escalate.",
                                "await.proceed")
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

    def _open_case(self, block, kind, worker_id, detail):
        """Stamp a correlation id on a parked operator case (02-10). The reply carries it back and
        02-08 Settle applies it ≤1 tick later (_h_apply_decision)."""
        case_id = self.st.next_case_id(block or kind)
        self.st.pending_cases[case_id] = {
            "block": block, "kind": kind, "worker_id": worker_id,
            "detail": detail, "raised_at": util.now_iso(), "decision": None}
        return case_id

    def _h_escalate(self, m):
        # wall:raised:<block> — Escalate: HOLD the slot (T2, D-15-2), park the block
        # (runtime), contact operator.
        block = m.get("block")
        worker_id = m.get("worker_id")
        if block and block in self.st.blocked:
            return                                      # already escalated — idempotent
        detail = m.get("detail", "wall")
        freed = worker_id
        for w in list(self.st.workers):
            if w.get("role") not in ("engineer", "reviewer"):
                continue
            if (block and w.get("block") == block) or (worker_id and w.get("id") == worker_id):
                freed = w.get("id")
                self._hold_worker(w)
                # T3 (01-17, tron-23): stash the detail ON the worker, not just the case —
                # the sweep's invariant (b) repair (walled, no pending case) reuses this if
                # the case is the thing that went missing.
                w["wall_detail"] = detail
        if block:
            if block not in self.st.blocked:
                self.st.blocked.append(block)
            # T2 (01-15 D-16-1 seam 2): raising a wall must never pop the block's gate —
            # gate lifecycle is owned exclusively by _confirm_close (release) and
            # _gate_giveup (escalation). Popping it here left a live CLOSE gate's
            # clean-confirmation with nothing to advance against (g is None ->
            # the done-handler's `if g and g.get("stage") == "close"` silently no-ops).
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
        if decision:                                     # forensic record (01-09): disposition applied
            self.events.event("settle", block=block, cid=m.get("case"),
                              **{"disposition": decision})
        if case is not None and case.get("kind") == "merge":
            # Ask-before-merging (T8): the operator's call on the trunk-merge step. Four outcomes,
            # all resolved here (no new flow). The engineer never left; nothing to un-park.
            g = self.st.gate.get(block)
            if g is None:
                self._close_case(m.get("case"), case)
                self._emit("pulse"); return
            g.pop("case_merge", None)
            if decision in ("resume", "approve"):                 # 1. approve -> agent merges
                g["approved_merge"] = True
                # T1 (D-15-1): the order this approval carries is now IN FLIGHT — a tip that
                # moves before it lands gets the content-identity check (patch-id), never a
                # blind re-pin (_drive_gate). Cleared on landing or a content-divergent re-pin.
                g["merge_in_flight"] = True
                self._close_case(m.get("case"), case)
                self._drive_gate(block, g, reason="merge approved")
            elif decision in ("self", "self_merge", "merge_self"):  # 2. operator merges it -> resume at trunk
                g["self_merge"] = True
                self._close_case(m.get("case"), case)
                self._drive_gate(block, g, reason="operator self-merge")
            elif decision in ("changes", "amend"):                # 3. changes requested -> relay + rework
                note = m.get("detail") or "Changes requested before merge."
                twid = self._worker_id_for_block(block)
                if twid and not self.dry:
                    self._to_worker(twid, f"[TRON] Operator requested changes before merge: {note}",
                                    "gate.changes")
                g["awaiting_rework"] = True
                g["stall_attempts"] = 0
                self._close_case(m.get("case"), case)
            elif decision in ("abandon", "drop"):                 # 4. drop the block at the merge moment
                self.st.gate.pop(block, None)
                if block not in self._dropped():
                    self._dropped().append(block)
                self._force_release_block(block)
                self._close_case(m.get("case"), case)
            else:
                self._close_case(m.get("case"), case)             # unknown reply — drop case, hold
            self.log("flow", f"merge-gate[{block}] -> {decision}")
            self._emit("pulse"); return
        if not block:
            # T3 (D-15-3): a settle that resolves NO pending case is never a silent no-op —
            # this is the `resume CASE-007` no-op's exact shape (classify mangled the case
            # id/block, nothing was ever touched). Name the pending set back to the
            # operator so a mis-resolved settle is visibly wrong, not silently nothing.
            if m.get("case") or decision:
                pending = sorted(self._undecided_cases())
                self.emit("escalate.unclassified",
                          {"detail": f"settle '{m.get('case') or '?'}: {decision or '?'}' "
                                     f"matches no pending case"
                                     + (f" — still parked: {', '.join(pending)}"
                                        if pending else " — nothing is parked")})
            self._close_case(m.get("case"), case)
            self._emit("pulse"); return
        vg = self.st.gate.get(block)
        violation_reopen = False
        if decision == "approve" and vg and vg.get("violation_pending"):
            # T6 (01-15): `approve` on a close-time violation wall = land it — the ordered
            # merge of the exact range the wall named. No new verb, no new case kind: this
            # IS what `approve` means everywhere else (the merge-ask branch above).
            if block in self.st.blocked:
                self.st.blocked.remove(block)
            landed = self._land_violation_range(block, vg, self._worker_id_for_block(block))
            if not landed:
                # T2 (01-17, D-22-1): the land didn't complete (git-layer failure, or a
                # moved tip re-pinned for a fresh approve) — never spend the case that is
                # this parked gate's ONLY reachable handle. Put the block back on the wall
                # (violation_pending's own invariant: a live wall keeps its block blocked)
                # and reopen the SAME case (decision back to None, same correlation id)
                # instead of closing it into an operator-unreachable violation_pending gate.
                violation_reopen = True
                if block not in self.st.blocked:
                    self.st.blocked.append(block)
        elif decision == "resume" and block in self.st.blocked:
            self.st.blocked.remove(block)                 # back in the dispatch pool (still 📋 on trunk)
            unheld = False
            for w in list(self.st.workers):                # T4: a wall-held worker un-holds on resume
                if w.get("block") == block and w.get("status") == "walled":
                    unheld = True
                    self._unhold_worker(w)
                    # T1 (01-15 D-16-1 seam 1): replay whatever queued whole while held, in
                    # arrival order — this is the exact `clean` confirmation the wall used
                    # to swallow (tron-16 D-16-1: it arrived 15s after its own wall held it).
                    queued = w.pop("held_verbs", None) or []
                    for item in queued:
                        self._ingest(item["tag"], item["slots"],
                                    {"kind": "worker", "id": w.get("id")})
                    if not queued:
                        # 01-16 addendum (tron-19/20): un-holding with an EMPTY replay
                        # queue used to leave a MUTUAL WAIT — the live runner idles
                        # awaiting a mailbox message while the engine waits for the worker
                        # to speak, and the restored idle entry consumes its slot forever
                        # (dispatch starves with no gate for any net to key on). Every
                        # un-hold now ends with the worker's state-appropriate next
                        # message — never two parties waiting on each other.
                        self._post_unhold_nudge(w, block)
            vg2 = self.st.gate.get(block)
            if vg2 and vg2.get("violation_pending"):
                # T6 (01-15): resume means the worker resolves its own branch — clear the
                # park so a fresh confirm re-checks land_docs from scratch, never stays
                # silently held at close forever (_drive_close's violation_pending guard).
                vg2.pop("violation_pending", None)
                vg2.pop("violation_branch", None)
                vg2.pop("violation_tip", None)
            elif not unheld and vg2 is not None:
                # T2 (01-16, D-17-1): resume expects to find the walled worker it un-holds —
                # tron-17's CASE-006 gap was exactly this: the worker died and was purged out
                # from under its own wall, so this loop matched nothing and resume silently
                # no-op'd, leaving the block's DONE gate stranded with nobody left to confirm
                # it. A worker gone by the time resume settles routes to the same
                # workerless-gate resolution as every other "gate outlived its worker" path —
                # never a silent no-op.
                self._resolve_workerless_gate(block, vg2)
            elif not unheld:
                # 01-16 addendum: no worker to un-hold AND no gate — the block would sit
                # unowned until something re-armed it. Re-arm via the ordinary recovery
                # dispatch (its own guards skip done/parked/gated/in-flight blocks); a 📋
                # row also redispatches via the closing pulse's switchboard as always.
                self._redispatch(block)
        elif decision == "amend" and block in self.st.blocked:
            self.st.blocked.remove(block)
            self._forward_review(block)                   # architect re-scopes the block file
        elif decision == "abandon":
            if block not in self._dropped():
                self._dropped().append(block)             # runtime skip; TRON never writes ❌
            if block in self.st.blocked:
                self.st.blocked.remove(block)
            # T2 (01-15 D-16-1 seam 2): settling a wall never pops the gate either — the
            # DONE ladder's own dropped-block check (_drive_gate) clears it on its next
            # pass, so a give-up-in-progress never reads the gate as vanished mid-decision.
            # T2 (D-15-2): abandon/release-shaped settles RELEASE as today — the wall now
            # holds its sender (status 'walled'), so the drop must free that held worker
            # here, not leave it parked with a live idle session until session end.
            self._force_release_block(block)
        if violation_reopen and case is not None:
            case["decision"] = None            # T2: reachable again, never a spent case
        else:
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
                self._release_worker(w, notify=False, reason="stall-recover")
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
        self._triage_to_architect(text[:160] or raw,
                                  sender=m.get("worker_id"), block=m.get("block"))
        self._emit("pulse")

    # ── the DONE gate (realign §F): one stage-specific prompt per state, advanced on EVIDENCE ──
    def _now_s(self):
        """Wall-clock seconds (monkeypatch point for the pacing tests)."""
        import time as _t
        return _t.time()

    def _pace(self, mult_knob, default):
        """A knob expressed as a multiplier of the wake ceiling -> a wall-clock span (S-1)."""
        ceiling = float(self.knobs.get("wake_ceiling_sec", 30))
        return float(self.knobs.get(mult_knob, default)) * ceiling

    def _drive_gates(self):
        if self._trunk_fault:
            # T3 (01-16): this tick's trunk read came back blank — never re-evaluate gate
            # state against it (that's exactly what regressed a done block's gate
            # close -> local on tron-17's transient `trunk: ""` ticks). Hold everything
            # untouched; the next good read resumes driving normally.
            return
        for block in list(self.st.gate.keys()):
            g = self.st.gate.get(block)
            if g is None:
                continue
            if str(block).startswith("review:"):
                # tron-13 D1 rider (b): review gates are event-driven EXCEPT the landing
                # stage — a reviewer silent after a failed paperwork landing would
                # otherwise be a W6c-class stall no clock ever catches.
                # 01-13 (tron-14 F9): ...and except the ATTEST stage, for the same reason —
                # a hand-back that never reached the channel left `review` as the one
                # stage no clock watched (15 silent minutes until the operator re-delivered).
                if g.get("stage") == "landing":
                    self._drive_review_landing(block, g)
                elif g.get("stage") == "review":
                    self._drive_review_attest(block, g)
                continue
            self._drive_gate(block, g)

    def _drive_gate(self, block, g, reason=None, on_report=False):
        """Drive a worker through the DONE gate one stage-specific prompt at a time (T5), on
        EVIDENCE — never a bare `✅`, never a multi-step dump. Stages:
          ENGINEER  LOCAL -> MERGE -> TRUNK -> CLOSE
                    local: validate the acceptance suite locally, evidence each (DONE-LOCAL);
                    merge: merge to trunk + CI green (CI auto-deploys staging) — ASK-gated (T8);
                    trunk: re-validate every applicable check on trunk (DONE-TRUNK);
                    close: ✅ landed -> hold the slot until a clean exit is confirmed (T7).
          REVIEWER  REVIEW (attest full coverage since last review; loop-until-clean — _h_release_reviewer).
        Prod promotion is NOT a worker stage (operator-only). Finalization (cadence, reconcile-ahead)
        happens in _on_block_done when ✅ appears on trunk; release happens on the CLOSE confirm."""
        if str(block).startswith("review:"):
            return                                       # reviewer gate is event-driven (review_done), not ticked
        row = self.st.row(block)
        if block in self._dropped():
            self.st.gate.pop(block, None)
            return
        wid = self._worker_id("engineer", block)
        if row and row.get("status") == "done":          # ✅ on trunk -> CLOSE (slot held, T7)
            self._drive_close(block, g, wid)
            return
        branch = self._block_branch(block)               # the worker-named branch (T2), never a guess
        pr = (self.st.open_prs or {}).get(branch)
        renudge = False
        stage, msg = None, None

        if on_report and g.get("stage") == "trunk":
            # 01-11 FX-3: the worker's trunk-stage evidence report is ACCEPTED -> order the
            # ✅ record. The flip is ordered only after this acceptance — never before.
            stage, msg = "record", "gate.record"
        elif g.get("stage") in ("trunk", "record"):
            # A-5 (tron-13, generalizes tron-07 W1 + R-3): the DONE ladder is MONOTONIC past
            # the merge. The git predicates below go stale the moment the worker parks
            # paperwork commits on its branch, and recomputing from them once regressed the
            # gate trunk -> local — a duplicate DONE-LOCAL, then a second un-asked merge.
            # Held rungs never recompute downward; instead the held stage's OWN predicate is
            # re-verified each tick: the merged sha's ancestry (survives paperwork commits
            # AND `git revert` — only history surgery breaks it) and, in remote mode, the
            # merged PR staying closed. A contradicted predicate is a NAMED escalation —
            # a trunk regression must never read as a worker stall. ACCEPTED RESIDUAL
            # (delta review): a local-mode plain `git revert` keeps ancestry AND has no PR
            # to reopen — the ratchet holds quietly and the regression surfaces at trunk
            # re-validation, not here. A record-PR still never parks on the operator
            # (R2-3): identification is stage==record + the content check at close, never
            # a branch/title convention.
            held = g["stage"]
            contra = None
            if pr:
                contra = (f"PR #{pr.get('number')} is open again after the merge "
                          f"(revert + reopen?)")
            elif g.get("merged_sha") and not trunk.is_ancestor(
                    self.paths["root"], g["merged_sha"],
                    self.paths.get("main_branch", "main"), self.dry):
                contra = (f"merged sha {str(g['merged_sha'])[:7]} no longer in trunk "
                          f"history (force-push or reset?)")
            if contra:
                self._gate_giveup(block, g, wid,
                                  f"gate-contradiction at '{held}': {contra}",
                                  "gate-contradiction",
                                  "audit trunk history; re-validate or reassign")
                return
            stage = held
        elif not pr:
            if not g.get("pr"):
                # MG-01: trunk is the only done-truth. Before parking at local, check whether
                # the block's branch already reached trunk with no PR for the gate to have
                # seen (an out-of-gate merge) — never silently accept it.
                if trunk.branch_merged(self.paths["root"], branch,
                                       self.paths.get("main_branch", "main"), self.dry):
                    # T1 (D-15-1): a block whose own ordered merge is IN FLIGHT is exempt —
                    # merge_in_flight is true only while approved_merge/self_merge holds
                    # (set at approval, cleared the moment it lands or the grant is voided),
                    # so this is already covered by the existing exemption below; named
                    # explicitly per the tron-15 fix spec (bypass detection must SKIP an
                    # in-flight block, never just happen to miss it).
                    if g.get("case_merge") and not (g.get("approved_merge") or g.get("self_merge")
                                                     or g.get("merge_in_flight")):
                        self._gate_giveup(block, g, wid,
                                          "merged to trunk outside the gate (bypassed a pending merge hold)",
                                          "gate-bypass", "audit the out-of-gate merge; re-validate on trunk")
                        return
                    stage, msg = "trunk", "gate.trunk"   # already merged -> skip local, re-validate on trunk
                    g["merged_sha"] = trunk.tip_sha(self.paths["root"], branch, self.dry)  # A-5 predicate anchor
                    g.pop("merge_in_flight", None)       # T1: landed -> in-flight window closed
                else:
                    # No PR, not yet on trunk. REMOTE mode: the worker opens a PR and the merge
                    # lands via the pr path below. LOCAL mode (no remote): there is no PR to wait
                    # on, so once local validation is back the ENGINE performs the merge itself —
                    # ff-only, ASK-gated — exactly as the remote merge step does (MG-01: the engine
                    # owns the trunk merge, never the worker).
                    local_mode = self._local_mode()
                    # `branch` is the worker-declared name, else the convention (_block_branch). In local
                    # mode we merge it only when it REALLY exists in git — the verified local analog of
                    # "a PR exists" in remote mode (never a blind guess).
                    have_branch = trunk.branch_exists(self.paths["root"], branch, self.dry)
                    if local_mode and have_branch and g.get("stage") == "local":
                        g.pop("branch_gap", None)         # W12: the branch is visible again
                        if g.get("self_merge"):
                            stage, msg = "trunk", "gate.trunk"        # operator merged it themselves
                            g["merged_sha"] = trunk.tip_sha(self.paths["root"], branch, self.dry)
                        elif on_report or g.get("approved_merge"):
                            # A-3: the grant binds the exact sha the operator saw at park. A tip
                            # that moved between park and execution voids the grant and re-parks
                            # NAMING the new tip (rider 2) — unseen commits never ride an old yes.
                            # T1 (D-15-1, tron-15 race): UNLESS the order is already IN FLIGHT
                            # (merge_in_flight — set at approval in _h_apply_decision) — then a
                            # moved tip is as likely the worker completing THIS SAME order (e.g.
                            # the rebase this gate itself asked for on a non-ff below) as an
                            # unseen change. Verify with content identity (git patch-id --stable)
                            # before voiding anything: identical -> the grant carries to the new
                            # tip (rider 2 never fires, gate-bypass never misfires on the ordered
                            # merge landing under a rebased sha); divergent -> the original
                            # void-and-re-pin (AC-2). The PRE-order case (tip moves before any
                            # approval, e.g. tron-15 CASE-005->006) never sets merge_in_flight,
                            # so it keeps today's unconditional void.
                            cur_tip = trunk.tip_sha(self.paths["root"], branch, self.dry)
                            if (g.get("approved_merge") and g.get("case_tip") and cur_tip
                                    and cur_tip != g.get("case_tip")):
                                if g.get("merge_in_flight") and trunk.patch_id_matches(
                                        self.paths["root"], g["case_tip"], cur_tip,
                                        self.paths.get("main_branch", "main"), self.dry):
                                    self.log("flow", f"gate[{block}] approved tip "
                                                     f"{str(g.get('case_tip'))[:7]} moved to "
                                                     f"{cur_tip[:7]} -> patch-id match, grant carries")
                                    g["case_tip"] = cur_tip
                                else:
                                    self.log("flow", f"gate[{block}] approved tip {str(g.get('case_tip'))[:7]} "
                                                     f"moved to {cur_tip[:7]} -> grant void, re-park")
                                    g.pop("approved_merge", None)
                                    g.pop("case_merge", None)
                                    g.pop("case_tip", None)
                                    g.pop("merge_in_flight", None)   # T1: the old order's authority ends here
                            if self._merge_gated(block, g, wid):
                                return                                # ASK: parked on the operator, hold
                            ok, err = trunk.merge_ff_only(
                                self.paths["root"], branch,
                                self.paths.get("main_branch", "main"), self.dry)
                            if ok:
                                # A-5: anchor the held-stage predicate to the EXACT sha this
                                # merge landed — paperwork commits after this never touch it.
                                g["merged_sha"] = cur_tip or trunk.tip_sha(
                                    self.paths["root"], branch, self.dry)
                                # tron-07 W2: one approval = one EXECUTED merge. Consume the
                                # grant here (not on the order) so a non-ff retry — the same
                                # unexecuted merge — keeps it, but nothing after execution can
                                # ride it into a second un-asked merge.
                                g.pop("approved_merge", None)
                                g.pop("merge_in_flight", None)    # T1: landed -> in-flight window closed
                                stage, msg = "trunk", "gate.trunk"    # merged -> re-validate on trunk
                            else:
                                self.log("flow", f"gate[{block}] local ff-merge non-ff: {err.strip()}")
                                stage, msg, renudge = "local", "gate.merge", True  # trunk moved -> rebase + retry
                        elif g.get("case_merge"):
                            return                                    # tick while parked on operator -> hold quietly
                        else:
                            stage, msg = "local", "gate.local"        # tick while worker still validating locally
                    elif local_mode and not have_branch and g.get("stage") == "local" and on_report:
                        # W12 (tron-13 attempt 1): the worker says done but NO branch is
                        # visible under the name the gate would merge (declared or the
                        # convention placeholder) — re-ordering validation is the WRONG
                        # remedy (it walked a worker through three re-validations into
                        # the idle cap). Name the actual gap; the W10 hoist makes the
                        # one-message remedy real (a done re-report can carry --branch).
                        # The idle machinery keeps re-sending THIS line (branch_gap flag
                        # flips the nudge template) and its cap stays the backstop.
                        g["branch_gap"] = True
                        if wid and not self.dry:
                            self._to_worker(wid, self._branch_gap_line(wid, block),
                                            "gate.branch-gap")
                        self.log("flow", f"gate[{block}] done reported but no visible "
                                         f"branch -> ask for the declaration")
                        stage, msg = "local", None
                    else:
                        stage, msg = "local", "gate.local"   # remote: no PR yet -> validate locally first
            else:
                # PR gone, not ✅ yet -> merged; re-validate on trunk (DONE-TRUNK). The wall-clock
                # idle machinery below owns stalls from here (S-5: the per-tick trunk_nudges cap
                # was unreachable once W1 made the trunk stage monotonic — removed).
                stage, msg = "trunk", "gate.trunk"
                # A-5: best-effort anchor — a remote-merged branch may be unresolvable locally;
                # an empty sha just skips the ancestry predicate (quiet hold, R-3 detail at cap).
                g["merged_sha"] = trunk.tip_sha(self.paths["root"], branch, self.dry)
                g.pop("merge_in_flight", None)   # T1: landed (PR merged/closed) -> flight over
        elif pr.get("checks") == "failing":
            stage, msg = "ci", "gate.merge"              # CI red -> re-nudge the merge step (get CI green)
            renudge = True
        elif pr.get("checks") == "pending":
            stage, msg = "ci-wait", None                 # wait for CI; no nudge
        else:
            # PR + green CI -> merge to trunk (DONE-MERGE), ASK-gated (T8).
            if self._merge_gated(block, g, wid):
                return                                    # parked on the operator; hold quietly
            if g.get("self_merge"):
                stage, msg = "trunk", "gate.trunk"        # operator merges; agent re-validates on trunk
            else:
                stage, msg = "merge", "gate.merge"

        # 01-11 FX-2 + S-1 (one pacing law): idle-at-gate is a WALL-CLOCK span of the runner's
        # own `state: idle` — never a tick count (event bursts and event-starved timers both lie
        # about time; R-1/W7b). A busy worker (runner `working`) never accrues; `ci-wait` is
        # excluded — the PR machinery owns that wait. Nudge once per idle episode at
        # gate_nudge_after x ceiling; give up at gate_idle_cap x ceiling.
        if stage == g.get("stage") and not renudge and stage != "ci-wait":
            if not jobs.runner_idle(wid):
                g.pop("idle_since", None)
                g.pop("nudged_at", None)
            else:
                now = self._now_s()
                since = g.setdefault("idle_since", now)
                idle_s = now - since
                if idle_s >= self._pace("gate_idle_cap", 3):
                    detail = f"gate stalled at '{stage}' — worker idle {int(idle_s)}s"
                    if stage == "trunk" and not trunk.branch_merged(
                            self.paths["root"], branch,
                            self.paths.get("main_branch", "main"), self.dry):
                        # R-3: a held trunk whose predicates now contradict it (revert /
                        # force-push) must read as a trunk regression, not a worker stall.
                        detail += ("; predicate contradiction: the block branch is no longer "
                                   "on trunk (revert or force-push?)")
                    self._gate_giveup(block, g, wid, detail,
                                      "gate-idle-cap", "check worker liveness; resume or reassign")
                    return
                if (idle_s >= self._pace("gate_nudge_after", 2)
                        and not g.get("nudged_at") and wid):
                    # Re-send the pending stage prompt — a deliberate duplicate on a FRESH
                    # mailbox seq (_to_worker bumps it), so the runner's seq-keyed dedupe
                    # delivers it (R1-4). One nudge per idle episode. W12: while the gap
                    # is a missing branch, the nudge names THAT — never "validate again".
                    nudge = self._stage_template(stage)
                    if nudge:
                        g["nudged_at"] = now
                        if g.get("branch_gap") and stage == "local":
                            self._to_worker(wid, self._branch_gap_line(wid, block),
                                            "gate.branch-gap")
                        else:
                            self.emit(nudge, self._stage_slots(stage, wid, block),
                                      worker_id=wid)
                        self.log("flow", f"gate[{block}] idle at '{stage}' -> re-nudge")
        else:
            g.pop("idle_since", None)
            g.pop("nudged_at", None)

        if stage != g.get("stage") or renudge:
            prev = g.get("stage")
            g["stage"], g["pr"] = stage, ((pr or {}).get("number") or g.get("pr"))
            if msg and wid:
                self.emit(msg, self._stage_slots(stage, wid, block), worker_id=wid)
            self.log("flow", f"gate[{block}] -> {stage}" + (f" ({reason})" if reason else ""))
            if stage != prev:                            # a real stage advance (01-09), not a re-nudge
                self.events.event("gate_advance", block=block,
                                  **{"from": prev, "to": stage, "detail": reason})

    def _local_mode(self):
        """No remote declared -> the root checkout IS the authority (local mode, #89)."""
        return not self.paths.get("remote") or self.paths.get("remote") == "none"

    def _record_path(self):
        """The {record_path} slot of PMT-DONE-RECORD (01-11 FX-3, operator decision: PR for
        remote) — the mode-specific landing instruction, one PMT body, no fork."""
        if self._local_mode():
            return "land it on trunk yourself, now"
        return ("push it on a side branch, open a PR, and merge that PR yourself, now — "
                "it needs no approval hold")

    def _merge_path(self, kind="engineer"):
        """The {merge_path} slot of PMT-ASSIGN (01-11 FX-4): the mode-true merge instruction —
        local mode must never tell a worker to open a PR (tron-05 F2), and a reviewer must
        never receive merge instructions at all (review is a milestone, not a merge)."""
        if kind == "reviewer":
            return "you review and report; you never merge — deliver your findings log and report done"
        if self._local_mode():
            return ("build on your branch and report done — there is no PR here; "
                    "I run the trunk merge at the gate")
        return "build on your branch, open a PR, report done — I authorize the merge at the gate"

    def _stage_template(self, stage):
        """Gate stage -> its worker prompt template (for the first send and the idle re-nudge)."""
        return {"local": "gate.local", "merge": "gate.merge", "ci": "gate.merge",
                "trunk": "gate.trunk", "record": "gate.record", "close": "close.worker"}.get(stage)

    def _block_relpath(self, block):
        """The block doc's repo-relative path — reader stores the basename; git pathspecs and
        the record content check need the full path under the project's blocks dir."""
        row = self.st.row(block) or {}
        fname = os.path.basename(row.get("block_file") or f"{block}.md")
        return os.path.relpath(os.path.join(self.paths["blocks"], fname), self.paths["root"])

    def _stage_slots(self, stage, wid, block):
        slots = {"worker_id": wid, "block": block}
        if stage == "record":
            slots["record_path"] = self._record_path()
        return slots

    def _drive_close(self, block, g, wid):
        """CLOSE stage (T7): ✅ landed. Fire CLOSE once and HOLD the slot — the worker wraps up
        (nothing unmerged, no loose worktree, local synced). The slot frees only on its clean
        confirmation (_confirm_close). Re-nudge up to a cap, then force-release so a silent worker
        can't strand the slot forever."""
        if g.get("violation_pending"):
            return           # T6 (01-15): parked on the operator's wall settle; hold quietly
        # 01-11 FX-3 (R2-1/R2-3): leaving RECORD -> verify the record commit's OWN diff before
        # accepting the ✅ — exactly one file (the block doc), exactly the Status field. Never a
        # trunk range (another block's merge landing in between must not false-positive under
        # worker_count > 1), never branch name / message / say-so. Non-conforming = an
        # out-of-gate change wearing the record's clothes -> escalate, don't close.
        if g.get("stage") == "record" and not g.get("record_checked"):
            okc, detail = trunk.record_commit_ok(
                self.paths["root"], self._block_relpath(block), self.dry)
            if not okc:
                self._gate_giveup(block, g, wid,
                                  f"record commit non-conforming: {detail}",
                                  "gate-record-bypass",
                                  "audit the record commit (one file, Status field only)")
                return
            g["record_checked"] = True
        if g.get("stage") != "close":
            prev = g.get("stage")
            g["stage"] = "close"
            if wid:
                self.emit("close.worker", {"worker_id": wid}, worker_id=wid)
            self.events.event("gate_advance", block=block,
                              **{"from": prev, "to": "close", "detail": "✅ on trunk"})
            self.log("flow", f"gate[{block}] -> close (slot held)")
            return
        # T2 (01-16, D-17-1): a workerless gate never waits on stale runner liveness. The
        # pacing below reads jobs.runner_idle(wid) off the ON-DISK runner record — a runner
        # that died mid-turn leaves that record reading `working` forever (nobody's left to
        # ever update it), which is exactly what stranded tron-17's CASE-006 gate at `close`
        # for ~28 silent minutes: no bound worker on the roster, yet the disk record never
        # aged into "idle" so close_idle_since never even started. The ROSTER (not the disk
        # record) is the authority on whether anyone is left to wait on — no bound worker ->
        # attempt the evidence-gated close right now instead of pacing against a ghost.
        if self._worker_id_for_block(block) is None:
            self._confirm_close(block, g)
            return
        # tron-07 W6b + S-1: close pacing is the same wall-clock law as the gate's — a worker
        # mid-close-out (runner `working`) never accrues (per-tick accrual once capped a working
        # engineer out of its own paperwork in 74s and force-released with no cleanliness check).
        # An idle close re-nudges once per ceiling span; at gate_close_cap x ceiling of
        # continuous idle it force-releases.
        if wid and not jobs.runner_idle(wid):
            g.pop("close_idle_since", None)
            g.pop("close_nudged_at", None)
            return
        now = self._now_s()
        since = g.setdefault("close_idle_since", now)
        if now - since >= self._pace("gate_close_cap", 3):
            self._force_release_block(block)
            self.st.gate.pop(block, None)
            self.log("flow", f"gate[{block}] close cap -> force release")
            # tron-07 W6c: a freed slot without a pulse leaves the SWITCHBOARD asleep — the
            # due reviewer never dispatches and session-end never evaluates. Every
            # slot-freeing path pulses.
            self._emit("pulse")
            return
        last = g.get("close_nudged_at")
        ceiling = float(self.knobs.get("wake_ceiling_sec", 30))
        if wid and (last is None or now - last >= ceiling):
            g["close_nudged_at"] = now
            self.emit("close.worker", {"worker_id": wid}, worker_id=wid)

    # ── the unified paperwork lander (F-1/S-3+R-6, tron-13 D1) ──
    def _paperwork_rules(self, role, block=None):
        """Per-role paperwork rules -> (allow, deny, line_scoped). The project declares
        the paperwork area (`paperwork_paths`, seeder-authored; default the meta dir).
        Pipeline content is carved OUT for engineer/reviewer — the pipeline's shape is
        the architect's product — with two mechanically-scoped exceptions for the
        engineer's own close-out (co-signed ask-2 fix): its OWN block doc + archive path
        (the archive move + Completed line), and pipeline edits whose every changed line
        names its own block id. The architect gets the explicit UNION — a config where
        blocks_dir isn't under a paperwork path must not silently exclude it."""
        base = list(self.paths.get("paperwork") or [])
        pipe = self.paths.get("pipeline_rel") or "meta/pipeline.md"
        blocks = self.paths.get("blocks_rel") or "meta/blocks/"
        if role == "architect":
            return base + [blocks, pipe], None, None
        deny = [blocks, pipe]
        if role == "engineer" and block:
            rel = self._block_relpath(block)
            archive_rel = os.path.relpath(
                os.path.join(self.paths["archive"], os.path.basename(rel)),
                self.paths["root"])
            return base + [rel, archive_rel], deny, {pipe: str(block)}
        return base, deny, None

    def _drain_landings(self, w, role):
        """FS-1: land the worker's declared paperwork branches FIFO head-first — a second
        declaration never orphans a parked first. Returns ("ok", detail) when the FIFO is
        empty(ied), ("blocked", detail) when the head won't land — it STAYS queued; the
        caller paces nudges and caps into a named escalation."""
        fifo = w.setdefault("pending_landings", [])
        while fifo:
            branch = fifo[0]
            allow, deny, scoped = self._paperwork_rules(role)
            code, detail = trunk.land_docs(self.paths["root"], branch, allow,
                                           self.paths.get("main_branch", "main"),
                                           self.dry, denylist=deny, line_scoped=scoped)
            if code in ("landed", "none"):
                fifo.pop(0)
                if code == "landed":
                    self.events.event("docs_landed", actor=w.get("id"),
                                      **{"role": role, "branch": branch,
                                         "detail": detail})
                    self.log("flow", f"paperwork[{w.get('id')}] landed {branch}: {detail}")
                continue
            return "blocked", f"{branch}: {code}: {detail}"
        return "ok", "nothing pending"

    def _fail_landing(self, w, role, detail):
        """The bounded rung capped: move the head branch aside as NAMED residue (the
        session-end sweep re-names it), record the failure, park a case on the operator."""
        wid = w.get("id")
        fifo = w.get("pending_landings") or []
        branch = fifo.pop(0) if fifo else "?"
        self.st.data.setdefault("failed_landings", []).append(
            {"worker": wid, "role": role, "branch": branch, "detail": detail})
        self.events.failure("gate-stuck", "paperwork-unlandable",
                            f"land {role} paperwork branch", detail, actor=wid,
                            node="paperwork lander", next_action="escalate")
        cid = self._open_case(None, "paperwork", wid,
                              f"{role} paperwork unlandable — {detail}")
        self.emit("escalate.wall", {"worker_id": wid or "?", "block": "?",
                                    "detail": f"{role} paperwork unlandable — {detail}",
                                    "case": cid})

    def _branch_gap_line(self, wid, block):
        """W12: the missing-branch remedy names the actual gap and prescribes the
        ONE-message recovery — the W10 hoist carries `--branch` on any verb, so the
        re-reported done and the declaration ride together (peer rider 1)."""
        return (f"[TRON]  {wid} — I can't see a branch for {block}: you've reported "
                f"done, but nothing exists under the name I have (or you never named "
                f"one). Report done again and carry your branch with it — add "
                f"`--branch <your branch name>` to the report command.")

    def _land_nudge(self, wid, detail):
        # Engine-composed (gate.changes precedent): the PMT surface stays untouched.
        self._to_worker(wid, f"[TRON]  {wid} — your paperwork branch won't land: "
                             f"{detail}. Move anything that isn't paperwork off it, "
                             f"rebase onto the trunk if it moved, and leave the branch "
                             f"in place — I land it.", "land.nudge")

    def _drive_landings(self):
        """D1 landing point 3 (architect, each tick — independent of the job queue,
        FS-1): a stuck landing nudges its owner on the close pacing law and caps into a
        named escalation + residue, so the queue keeps draining and a stuck landing
        never deadlocks the architect."""
        arch = self._architect()
        if not arch or not arch.get("pending_landings"):
            return
        code, detail = self._drain_landings(arch, "architect")
        if code != "blocked":
            arch.pop("land_since", None)
            arch.pop("land_nudged_at", None)
            return
        now = self._now_s()
        since = arch.setdefault("land_since", now)
        if now - since >= self._pace("gate_close_cap", 3):
            arch.pop("land_since", None)
            arch.pop("land_nudged_at", None)
            self._fail_landing(arch, "architect", detail)
            return
        last = arch.get("land_nudged_at")
        ceiling = float(self.knobs.get("wake_ceiling_sec", 30))
        if last is None or now - last >= ceiling:
            arch["land_nudged_at"] = now
            self._land_nudge(arch.get("id"), detail)

    def _drive_review_landing(self, gkey, g):
        """D1 rider (b): a review gate holds at `landing` ONLY when the reviewer declared
        a paperwork branch that wouldn't land — same wall-clock idle law as close: retry
        each tick (trunk may move back into ff reach), re-nudge once per ceiling while
        idle, cap -> named escalation + release (the branch becomes named residue the
        session-end sweep re-surfaces)."""
        typ = gkey.split(":", 1)[1]
        rev = next((w for w in self.st.workers
                    if w.get("role") == "reviewer" and w.get("rtype") == typ), None)
        if rev is None:
            self.st.gate.pop(gkey, None)
            return
        code, detail = self._drain_landings(rev, "reviewer")
        if code != "blocked":
            self.log("flow", f"{gkey} paperwork landed -> release")
            self._finish_review(typ, g.get("block"))
            return
        wid = rev.get("id")
        if wid and not jobs.runner_idle(wid):
            g.pop("landing_idle_since", None)
            g.pop("landing_nudged_at", None)
            return
        now = self._now_s()
        since = g.setdefault("landing_idle_since", now)
        if now - since >= self._pace("gate_close_cap", 3):
            self._fail_landing(rev, "reviewer", detail)
            self._finish_review(typ, g.get("block"))
            return
        last = g.get("landing_nudged_at")
        ceiling = float(self.knobs.get("wake_ceiling_sec", 30))
        if wid and (last is None or now - last >= ceiling):
            g["landing_nudged_at"] = now
            self._land_nudge(wid, detail)

    def _drive_review_attest(self, gkey, g):
        """01-13 (tron-14 F9): the DONE-REVIEW gate at `review` (attest coverage) was the
        one stage no clock watched — a hand-back that never reached the channel stalled it
        silently until the operator re-delivered it by hand. Same wall-clock idle law as
        the block gate: reviewer runner idle -> re-send gate.review once per episode; at
        the cap -> a parked case. The reviewer stays alive and the gate holds — the
        operator's usual remedy is re-delivering the report, exactly tron-14's manual
        recovery, now with the engine asking for it instead of hiding it."""
        typ = gkey.split(":", 1)[1]
        rev = next((w for w in self.st.workers
                    if w.get("role") == "reviewer" and w.get("rtype") == typ), None)
        if rev is None:
            self.st.gate.pop(gkey, None)
            return
        if g.get("attest_case"):
            return                                   # parked on the operator; hold quietly
        wid = rev.get("id")
        if wid and not jobs.runner_idle(wid):
            g.pop("attest_idle_since", None)
            g.pop("attest_nudged_at", None)
            return
        now = self._now_s()
        since = g.setdefault("attest_idle_since", now)
        idle_s = now - since
        if idle_s >= self._pace("gate_idle_cap", 3):
            cid = self._open_case(gkey, "review", wid,
                                  f"review:{typ} stalled at attest — reviewer idle "
                                  f"{int(idle_s)}s; its hand-back may never have reached "
                                  f"the channel")
            g["attest_case"] = cid
            self.events.failure("gate-stuck", "review-attest-idle",
                                f"attest {typ} review coverage", f"idle {int(idle_s)}s",
                                actor=wid, node="DONE-REVIEW gate", next_action="escalate")
            self.emit("escalate.wall", {"worker_id": wid or "?", "block": gkey,
                                        "detail": f"review:{typ} stalled at attest "
                                                  f"(reviewer idle, report likely "
                                                  f"off-channel)", "case": cid})
            return
        if idle_s >= self._pace("gate_nudge_after", 2) and not g.get("attest_nudged_at"):
            g["attest_nudged_at"] = now
            if wid:
                self.emit("gate.review", {"worker_id": wid}, worker_id=wid)
            self.log("flow", f"{gkey} idle at attest -> re-send the coverage order")

    def _confirm_close(self, block, g):
        """The worker confirmed a clean exit -> land its parked paperwork, verify, then
        free the slot (T7 + 01-11 FX-9 + tron-13 D1). The close contract: the worker
        parks paperwork commits on its OWN block branch, removes its worktree, syncs
        local, confirms — the ENGINE lands (content-checked per role, ff-only, branch
        deleted on success; serialized inside the tick lock, which is what kills the
        multi-worker close race). The "clean" claim is a say-so — the engine checks the
        replica itself before releasing. Unlandable/dirty -> name it and re-hold; at the
        cap -> escalate, never a silent trust-release."""
        wid = self._worker_id_for_block(block)
        branch = self._block_branch(block)
        allow, deny, scoped = self._paperwork_rules("engineer", block)
        code, ldetail = trunk.land_docs(self.paths["root"], branch, allow,
                                        self.paths.get("main_branch", "main"), self.dry,
                                        denylist=deny, line_scoped=scoped)
        if code == "landed":
            self.events.event("docs_landed", actor=wid, block=block,
                              **{"role": "engineer", "branch": branch,
                                 "detail": ldetail})
            self.log("flow", f"paperwork[{block}] landed: {ldetail}")
        elif code == "violation":
            # T6 (01-15, tron-16 CASE-003 residue): a close-time violation names REAL code
            # left on the branch — land_docs's paperwork-only allowlist can never accept
            # it, so re-nudging the worker toward the same confirm is a dead end (the old
            # cap eventually gate-gave-up with no landing path at all). Park it as an
            # ordinary wall instead — same case kind, same settle verbs, no new mechanism:
            # `approve` lands the named range (ordered merge, same sha-pinned content check
            # as a merge ASK, same lander cleanup after); `resume` means the worker resolves
            # its own branch (a fresh confirm re-checks land_docs from scratch); `abandon`
            # drops the block as always. Idempotent — branch/tip pin once, at park.
            if not g.get("violation_pending"):
                g["violation_pending"] = True
                g["violation_branch"] = branch
                tip = trunk.tip_sha(self.paths["root"], branch, self.dry)
                if tip:
                    g["violation_tip"] = tip
                self._emit("wall:raised:" + block,
                          {"block": block, "worker_id": wid,
                           "detail": f"close-time violation on {branch}: {ldetail} — "
                                     f"approve lands this range, resume if you'll fix "
                                     f"the branch yourself, abandon to drop the block"})
            return
        elif code in ("non-ff", "error"):
            reason = {
                "non-ff": "trunk moved under your parked paperwork — rebase your branch "
                          "onto the trunk, leave it in place, then confirm again",
                "error": f"paperwork landing failed: {ldetail}",
            }[code]
            n = g.get("close_nudges", 0) + 1
            g["close_nudges"] = n
            if n >= int(self.knobs.get("gate_close_cap", 3)):
                self._gate_giveup(block, g, wid,
                                  f"close confirmed but paperwork won't land "
                                  f"({code}): {ldetail}",
                                  "gate-close-dirty",
                                  "resolve the paperwork branch, then confirm")
                return
            if wid:
                self.emit("close.dirty", {"worker_id": wid, "detail": reason},
                          worker_id=wid)
            self.log("flow", f"gate[{block}] paperwork landing {code}: {ldetail}")
            return
        clean, detail = trunk.replica_clean(self.paths["root"], branch,
                                            self.paths.get("main_branch", "main"), self.dry)
        if not clean:
            n = g.get("close_nudges", 0) + 1
            g["close_nudges"] = n
            if n >= int(self.knobs.get("gate_close_cap", 3)):
                self._gate_giveup(block, g, wid,
                                  f"close confirmed but the replica is not clean: {detail}",
                                  "gate-close-dirty",
                                  "clean up the leftover worktree/branch/changes, then confirm")
                return
            if wid:
                self.emit("close.dirty", {"worker_id": wid, "detail": detail}, worker_id=wid)
            self.log("flow", f"gate[{block}] close claim rejected: {detail}")
            return
        for w in list(self.st.workers):
            if w.get("role") == "engineer" and w.get("block") == block:
                self._release_worker(w, notify=False, reason="close-confirmed")  # CLOSE already sent
        self.st.gate.pop(block, None)
        self.log("flow", f"{block} close confirmed -> worker released")
        self._emit("pulse")

    def _land_violation_range(self, block, g, wid):
        """T6 (01-15): the violation-wall `approve` settle IS 'land it' — an ordered merge
        of the exact branch the wall named, content-pinned exactly like a merge ASK (A-3:
        the grant binds the sha the operator saw at park; a moved tip voids it UNLESS the
        move carries an IDENTICAL diff, T1's patch-id rider — never landed blind), then the
        same lander cleanup `land_docs` runs on success (worktree gone, branch deleted). No
        new verb, no new case kind: `approve` here means exactly what it means at the
        ordinary merge gate.

        T2 (01-17, D-22-1): returns True iff the range actually landed (release + gate-pop
        happened). EVERY other outcome — the re-pin (tip moved, divergent diff) and the
        git-layer land failure alike — returns False, and the caller (_h_apply_decision)
        must never spend the case that got it here on a False: a parked `violation_pending`
        gate with a closed case was unreachable by any settle (re-settling a spent case is
        a no-op; the sweep skips violation-parked gates outright). Never silent, never a
        dead end."""
        branch = g.get("violation_branch")
        pinned = g.get("violation_tip")
        cur = trunk.tip_sha(self.paths["root"], branch, self.dry) if branch else ""
        if pinned and cur and cur != pinned and not trunk.patch_id_matches(
                self.paths["root"], pinned, cur, self.paths.get("main_branch", "main"), self.dry):
            g["violation_tip"] = cur          # A-3 rider 2: re-pin, never land a tip unseen
            self.log("flow", f"gate[{block}] violation-approve re-pinned: {branch} moved "
                             f"{str(pinned)[:7]} -> {cur[:7]} with a divergent diff")
            if wid and not self.dry:
                self._to_worker(wid, f"[TRON]  {wid} — {branch} moved since I was asked to "
                                     f"land it; approve again to land the new tip.",
                                "gate.changes")
            return False
        okm, detail = trunk.land_ordered_merge(self.paths["root"], branch,
                                               self.paths.get("main_branch", "main"), self.dry)
        if not okm:
            self.log("flow", f"gate[{block}] violation-approve failed: {detail}")
            if wid and not self.dry:
                self._to_worker(wid, f"[TRON]  {wid} — landing {branch} failed: {detail}. "
                                     f"Resolve it; I retry on your next confirm.",
                                "gate.changes")
            return False
        self.events.event("docs_landed", actor=wid, block=block,
                          **{"role": "engineer", "branch": branch, "detail": detail,
                             "via": "violation-approved"})
        self.log("flow", f"gate[{block}] violation range landed: {detail}")
        g.pop("violation_pending", None)
        g.pop("violation_branch", None)
        g.pop("violation_tip", None)
        for w in list(self.st.workers):
            if w.get("role") == "engineer" and w.get("block") == block:
                self._release_worker(w, notify=False, reason="close-confirmed")
        self.st.gate.pop(block, None)
        self.log("flow", f"{block} close confirmed (violation range landed) -> worker released")
        self._emit("pulse")
        return True

    def _force_release_block(self, block):
        for w in list(self.st.workers):
            if w.get("role") == "engineer" and w.get("block") == block:
                self._release_worker(w, notify=False, reason="force-release")

    def _gate_giveup(self, block, g, wid, detail, code, action):
        """No-silent-stuck: drop the gate + escalate to the operator (forensic record)."""
        self.st.gate.pop(block, None)
        self.events.failure("gate-stuck", code, action, detail, block=block,
                            inputs={"stall_attempts": g.get("stall_attempts"),
                                    "idle_since": g.get("idle_since")},
                            node="DONE gate", next_action="escalate")
        self._emit("wall:raised:" + block,
                   {"block": block, "worker_id": wid, "detail": detail})

    def _worker_id_for_block(self, block):
        w = next((w for w in self.st.workers
                  if w.get("role") == "engineer" and w.get("block") == block), None)
        return w.get("id") if w else None

    def _resolve_workerless_gate(self, block, g):
        """T2 (01-16, D-17-1): a workerless gate is never a wait state. Every path that
        finds a block's gate outliving its bound worker converges here — a dead-runner
        purge (recover), a `resume` that finds nobody left to un-hold, the sweep's
        silence backstop. Reuses the DONE ladder, never a new mechanism: block ✅ on
        trunk gets the ladder's own evidence-gated close a chance to confirm on trunk
        evidence alone (paperwork landed + a clean replica — never the dead worker's
        say-so, exactly what the ladder always required, never trusting the report or
        the commit); anything short of that (not done yet, or the evidence genuinely
        isn't there and nobody's left to fix it) never waits on a worker that's gone —
        give up NAMED, the existing `gate-orphaned` code (worker id may be gone; name
        the block)."""
        row = self.st.row(block)
        if row and row.get("status") == "done":
            if (block in self.st.gate and not g.get("violation_pending")
                    and g.get("stage") != "close"):
                self._drive_close(block, g, None)      # record-check + stage-flip to close
            if block in self.st.gate and not g.get("violation_pending"):
                self._drive_close(block, g, None)       # at close now -> attempt the confirm
            if block not in self.st.gate or g.get("violation_pending"):
                return       # closed on trunk evidence, or parked as an ordinary wall (already escalated)
        self._gate_giveup(block, g, None,
                          f"{block}'s gate has no live bound worker to resolve it (released/"
                          f"purged/gone)"
                          + (" — the close-confirm evidence (paperwork landed, clean replica) "
                             "wasn't there" if row and row.get("status") == "done"
                             else " — the block is not done on trunk"),
                          "gate-orphaned",
                          "check the worker/block binding; resume or reassign")

    def _block_merge_approval(self, block):
        """The block's own `Merge approval:` header (MG-01) — 'auto' or 'needs-user'."""
        row = next((r for r in self.st.pipeline if r.get("id") == block), None)
        return (row or {}).get("merge_approval", "auto")

    def _merge_gated(self, block, g, wid):
        """Ask-before-merging (T8) + per-block merge approval (MG-01). Returns True = HOLD (park
        ONE operator case at the trunk-merge step), False = proceed. A block stamped
        `Merge approval: needs-user` always holds, regardless of the global ask-before-merging knob.
        Otherwise: APPROVED (or a prior grant on this gate) proceeds; ASK parks once and holds
        quietly each tick. While reworking after a 'changes requested', holds without re-asking.
        The four operator outcomes (approve / self-merge / changes / drop) resolve via
        _h_apply_decision. Prod promotion is operator-only and never reaches this gate."""
        if g.get("approved_merge") or g.get("self_merge"):
            return False
        if g.get("awaiting_rework"):
            return True                                  # agent reworking; don't re-ask until it re-reports
        needs_user = self._block_merge_approval(block) == "needs-user"
        if self.st.approvals.get("merge", "APPROVED") == "APPROVED" and not needs_user:
            return False
        if not g.get("case_merge"):                      # escalate once; then hold quietly each tick
            tip = trunk.tip_sha(self.paths["root"], self._block_branch(block), self.dry)
            if tip:
                g["case_tip"] = tip                      # A-3: the grant binds THIS sha
            case = self._open_case(block, "merge", wid,
                                   f"merge {block} to trunk @ {(tip or 'unknown')[:7]}")
            g["case_merge"] = case
            self.emit("escalate.gate", {"worker_id": wid, "block": block,
                                        "detail": f"merge {block} to trunk", "case": case})
        return True

    # ── the architect (persistent, queued, forward-only) ──
    def _architect(self):
        return next((w for w in self.st.workers if w.get("role") == "architect"), None)

    def _spawn_architect(self):
        w = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "", "shortid": "",
             "spawned_at": util.now_iso(), "status": "idle", "current_job": None, "block": None}
        self._reserve(w)                               # durable intent before spawn
        session, short = self._spawn("ARCH-PERSIST", "spawn.architect", "architect")
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

    def _triage_to_architect(self, detail, sender=None, block=None):
        # Hand an unclassifiable input (or a peer question) to the architect to sort. It carries
        # the originating sender + block so the architect can answer-and-relay or escalate (T4/T10).
        # No architect online -> nobody can steer it but the operator, so escalate directly.
        if any(j.get("kind") == "triage" and j.get("detail") == detail
               for j in self.st.architect_queue):
            return
        if not self._architect():
            self.emit("escalate.unclassified", {"detail": detail})
            return
        self.st.architect_queue.append({"kind": "triage", "detail": detail,
                                        "sender": sender, "block": block})
        self._pump_architect()

    def _pump_architect(self):
        arch = self._architect()
        if not arch or arch.get("status") == "busy":
            return
        if not self.st.architect_queue:
            return
        job = self.st.architect_queue.pop(0)
        arch["status"], arch["current_job"] = "busy", job
        self._emit_arch_job(job, arch.get("id"))
        self.log("architect", f"dispatch {job}")

    def _emit_arch_job(self, job, awid):
        """Deliver (or 01-13: re-deliver, on the idle nudge) an architect job order —
        the one place a job kind maps to its PMT."""
        if job["kind"] == "forward":                      # author a missing block file (PMT-SCOPE)
            self.emit("arch.forward", {"block": job["block"]}, worker_id=awid)
        elif job["kind"] == "reconcile":                  # re-check an existing block vs a landed one
            self.emit("arch.reconcile", {"block": job["block"], "after": job.get("after", "")},
                      worker_id=awid)
        elif job["kind"] == "triage":
            self.emit("arch.triage",
                      {"detail": self._triage_detail(job),
                       "sender": job.get("sender") or "the sender"},
                      worker_id=awid)
        else:                                             # log-review -> remediation blocks
            self.emit("arch.remediation", {"type": job.get("type", "code")}, worker_id=awid)

    def _drive_architect_liveness(self):
        """01-13 (tron-14 F2/F4): the architect's job queue gets the SAME wall-clock idle
        law as every gate — `busy` on a job while its runner sits idle is a stall, not
        patience (two of tron-14's stalls held the queue 34 and 48 minutes with zero
        pings). Nudge = re-deliver the job order on a fresh seq; cap = a parked case.
        Backstop only: sender-truth resolution (_resolve_by_sender) completes jobs off
        the architect's own report — this catches the report that never arrived."""
        arch = self._architect()
        if not arch or arch.get("status") != "busy" or not arch.get("current_job"):
            return
        if not jobs.runner_idle(arch.get("id")):
            arch.pop("job_idle_since", None)
            arch.pop("job_nudged_at", None)
            return
        if arch.get("job_case"):
            return                                   # parked on the operator; hold quietly
        now = self._now_s()
        since = arch.setdefault("job_idle_since", now)
        idle_s = now - since
        job = arch.get("current_job") or {}
        if idle_s >= self._pace("gate_idle_cap", 3):
            cid = self._open_case(job.get("block"), "architect", arch.get("id"),
                                  f"architect stalled on job '{job.get('kind')}' "
                                  f"({job.get('block') or job.get('type') or '?'}) — "
                                  f"idle {int(idle_s)}s with no completion report")
            arch["job_case"] = cid
            self.events.failure("gate-stuck", "architect-idle-cap",
                                f"complete architect job '{job.get('kind')}'",
                                f"idle {int(idle_s)}s", actor=arch.get("id"),
                                block=job.get("block"),
                                node="architect queue", next_action="escalate")
            self.emit("escalate.wall", {"worker_id": arch.get("id") or "?",
                                        "block": job.get("block") or "?",
                                        "detail": f"architect job '{job.get('kind')}' "
                                                  f"stalled (idle, no completion report)",
                                        "case": cid})
            return
        if idle_s >= self._pace("gate_nudge_after", 2) and not arch.get("job_nudged_at"):
            arch["job_nudged_at"] = now
            self._emit_arch_job(job, arch.get("id"))
            self.log("flow", f"architect idle on '{job.get('kind')}' -> re-deliver the order")

    def _triage_detail(self, job):
        """Build the TRIAGE {detail} (T4). Prepend `"{sender}, on block {block}: "` ONLY when
        the sender is a worker on a real pipeline block — omit it for review:* senders and when
        there is no block; the raw text passes through otherwise."""
        raw = job.get("detail", "")
        sender = job.get("sender") or ""
        block = job.get("block") or ""
        if sender and block and not str(block).startswith("review:"):
            return f"{sender}, on block {block}: {raw}"
        return raw

    def _architect_advance(self):
        arch = self._architect()
        if arch:
            arch["status"], arch["current_job"] = "idle", None
            # 01-13: a completed job settles its own stall machinery — a parked
            # architect case closes itself the moment the completion lands.
            if arch.get("job_case"):
                self._close_case(arch.pop("job_case"), None)
            arch.pop("job_idle_since", None)
            arch.pop("job_nudged_at", None)
        self._pump_architect()

    # ── worker hold (T2, D-15-2) ──
    def _hold_worker(self, w):
        """A wall PARKS the case but never releases the sender (D-15-2: a mistagged `wall`
        used to free the worker instantly, no challenge, on CASE-007's model). The worker
        stays on the roster (status 'walled') — excluded from work-selection (_pool, so a
        fresh worker can take up its slot's budget while this one waits) but still resolvable
        by id, so its follow-up messages process on-roster instead of falling to the
        off-roster/ghost path. Its session is left running (no jobs.release) — operator
        `resume` un-holds it via _h_apply_decision and it continues; a still-walled worker
        is released same as every other worker at session end (_end_session, no special
        case)."""
        # T3 (01-17, tron-23 root cause): a SECOND hold on an already-walled worker (a
        # repeated-stall wall, a second gate-giveup racing the first) must never overwrite
        # the TRUE pre-hold status with 'walled' itself — that corrupts held_status so
        # _unhold_worker's restore is a no-op (status stays 'walled' forever, the exact
        # tron-23 signature: settled case, worker still walled). Idempotent: only the FIRST
        # hold ever stamps held_status.
        if w.get("status") != "walled":
            w["held_status"] = w.get("status")
        w["status"] = "walled"

    def _unhold_worker(self, w):
        """T4 (01-15 D-16-2): the un-hold counterpart to _hold_worker — ONE primitive pair,
        used by every wall settle that lifts a hold without releasing the worker outright
        (abandon still goes through _release_worker/_force_release_block as before). Restores
        the pre-hold status rather than a bare literal at each call site, so an engine-raised
        gate-stuck hold (_gate_giveup -> wall:raised -> _hold_worker) un-holds exactly like a
        worker-declared `--tag wall` hold does — tron-16's CASE-006 gap (resume cleared the
        case but left the worker walled) was two un-hold call sites free to drift apart;
        now there is one."""
        w["status"] = w.pop("held_status", None) or "working"
        w.pop("wall_detail", None)         # T3 (01-17): stale detail never survives an un-hold

    def _post_unhold_nudge(self, w, block):
        """01-16 addendum (tron-19/20 mutual wait): the state-appropriate next message after
        an un-hold whose replay queue was empty — restoring `held_status` (often `idle`) with
        nothing queued re-created two parties waiting on each other: the live runner idling
        on its mailbox, the engine waiting for the worker to speak, the idle roster entry
        starving every slot. Deterministic, existing vocabulary only:
          gate open            -> re-send the gate's own pending stage prompt (the same
                                  message the stage's idle re-nudge would eventually send);
          block done, gateless -> nothing remains for this worker — release it through the
                                  ordinary event-logged chokepoint, free the slot;
          block open, gateless -> heartbeat ping (the sweep's own vocabulary) — the worker
                                  re-reports and the flow resumes."""
        wid = w.get("id")
        g = self.st.gate.get(block)
        row = self.st.row(block)
        if g is not None:
            stage = g.get("stage")
            nudge = self._stage_template(stage)
            if nudge:
                self.emit(nudge, self._stage_slots(stage, wid, block), worker_id=wid)
            else:
                self.emit("heartbeat.ping", {"worker_id": wid}, worker_id=wid)
            self.log("flow", f"resume[{block}] -> re-nudge {wid} at '{stage}' "
                             f"(empty replay queue)")
        elif row and row.get("status") == "done":
            self._release_worker(w, notify=False, reason="force-release")
            self.log("flow", f"resume[{block}] -> {wid} released (block done, nothing gated)")
            self._emit("pulse")
        else:
            self.emit("heartbeat.ping", {"worker_id": wid}, worker_id=wid)
            self.log("flow", f"resume[{block}] -> heartbeat ping {wid} "
                             f"(no gate; the worker re-reports)")

    # ── worker release ──
    def _release_worker(self, w, notify=True, reason="released"):
        wid = w.get("id")
        if notify and not self.dry:
            # tron-07 W4 (same class as _end_session): emit(), never a bare renderer.render —
            # the missing universal reply slots crashed this render, and this is the reviewer's
            # release path (the crash would strand every review loop at hand-back).
            self.emit("close.worker", {"worker_id": wid}, worker_id=wid)
        # D1 delta-review fix: a released worker leaves the roster, so any paperwork it
        # declared but never landed would escape EVERY net (no cap fired, st.branches is
        # engineer-only) — the exact lost-output defect D1 kills, back through a side door
        # (stall-recover releases here too). Preserve the FIFO as durable named residue at
        # this single chokepoint; the session-end sweep re-surfaces it.
        for br in (w.get("pending_landings") or []):
            self.st.data.setdefault("failed_landings", []).append(
                {"worker": wid, "role": w.get("role"), "branch": br,
                 "detail": f"released ({reason}) with the branch unlanded"})
            self.log("flow", f"release[{wid}] preserves unlanded paperwork {br}")
        if not self.dry:
            jobs.release(wid)
        if w in self.st.workers:
            self.st.workers.remove(w)
        # Forensic record (01-09): a worker slot was freed. Single chokepoint — every release
        # site (close-confirm, reviewer-complete, stall-recover, force-release) funnels here.
        self.events.event("release", actor=w.get("id"), block=w.get("block"),
                          **{"role": w.get("role"), "reason": reason})

    # ── inbound classification + side handlers ──
    # S-2-full (tron-13 D2): the declarative tag x stage ADMISSION table — the DATA the
    # single checkpoint interprets; no per-tag conditionals live in code anymore.
    #   block:  the tag must resolve to a REAL canon block, sender-first (A-1/W3). This
    #           means "resolves to a canon block", never "a gate is open" — a worker.wall
    #           raised before any gate exists must still fire.
    #   stages: admissible only while the block's gate is AT one of these stages; anywhere
    #           else it is a receipt to note, never an action (W6a).
    #   close_confirm_at: at this stage only a reply opening the registry clean-prefix —
    #           or the structured `clean` verb (A-2 `clean_confirm` slot) — confirms.
    # Lint L22 pins this table against routing.yaml's gate-facing tags and asserts _admit
    # stays the only admission checkpoint (rider 4).
    ADMISSION = {
        "worker.done":     {"block": True, "stages": None, "close_confirm_at": "close"},
        "worker.recorded": {"block": True, "stages": ("record",)},
        "worker.wall":     {"block": True, "stages": None},
    }
    GATING_TAGS = tuple(ADMISSION)

    # A-2 (tron-13 D2): the closed worker-facing verb map for STRUCTURED reports
    # (report.sh --tag <verb>). A structured line resolves deterministically — zero LLM
    # for the whole gate ladder; free text keeps the classify path (prefixes remain the
    # fallback discriminator, W7a). `clean` is worker.done + a slot, never its own tag:
    # the distinction is _admit's to enforce at one choke point, and a new tag would
    # re-train the free-text classify vocabulary for nothing.
    REPORT_VERBS = {
        "done":        ("worker.done", {}),
        "recorded":    ("worker.recorded", {}),
        "wall":        ("worker.wall", {}),
        "review-done": ("worker.review_done", {}),
        "clean":       ("worker.done", {"clean_confirm": True}),
    }

    def _structured(self, msg):
        """Resolve a structured report (A-2) without the model. Returns (tag, slots) or
        (None, None) when the line carries no verb (-> classify). An unknown verb is
        recorded (with its sender — forensics at scale) and DROPPED: never a trigger,
        never a guess; the gate's own pacing re-prompts the worker.
        W10 (tron-13 attempt 1): `branch` is NOT a terminal verb — a branch declaration
        is a MODIFIER that rides other work (the architect's one-message
        declare-and-complete deadlocked its own job queue when `branch` swallowed the
        completion act). Record the declaration from the slot deterministically
        (non-engineer FIFO; engineers keep the classify+_admit path so the assignment
        backfills the block), then fall the TEXT through to classify: a dual-act reply
        loses neither act, a pure declaration re-classifies to worker.branch
        (idempotent), and a missing --branch never silently no-ops."""
        verb = str(msg.get("tag") or "").strip().lower()
        if not verb:
            return None, None
        sender = msg.get("sender") or {}
        if verb == "branch":
            # The declaration itself was hoisted to _classify (any verb records it);
            # nothing terminal remains — the text classifies.
            if not (msg.get("slots") or {}).get("branch"):
                self.log("flow", f"--tag branch without --branch from "
                                 f"{sender.get('id')} -> text classifies")
            return None, None
        hit = self.REPORT_VERBS.get(verb)
        if not hit:
            self.log("flow", f"unknown structured verb '{verb}' from "
                             f"{sender.get('id')} -> dropped")
            self.events.unclassified(msg.get("text", "")[:200],
                                     f"unknown structured verb '{verb}'", sender=sender)
            self._bounce(sender, f"'{verb}' is not a verb I know")
            return "drop", None
        tag, extra = hit
        slots = {**(msg.get("slots") or {}), **extra}
        if tag == "worker.review_done" and not slots.get("type"):
            # Sender-first (A-1 spirit): the reviewer's own record knows its type.
            w = next((x for x in self.st.workers
                      if x.get("id") == sender.get("id")), None)
            if w and w.get("rtype"):
                slots["type"] = w["rtype"]
        return tag, slots

    def _admit(self, tag, slots, sender):
        """The SINGLE admission checkpoint at the classify->trigger boundary (S-2, rider 4).
        Everything that decides whether a message may act on a gate lives here — nowhere
        else. The RULES are the declarative ADMISSION table above; this method only
        interprets it:
          A-1  the sender's ASSIGNED block is authoritative for its gate-facing reports;
               the extracted text ref is a cross-check (workers are single-block today —
               R-5: load-bearing; a multi-block worker design must revisit this);
          W3   a text ref resolves exact-then-unique-prefix; an id the canon has no row
               for never opens a gate.
        Returns the (possibly adjusted) slots, or None to refuse the trigger (SENTRY-logged)."""
        w = next((x for x in self.st.workers if x.get("id") == (sender or {}).get("id")), None)
        assigned = (w or {}).get("block")
        if assigned and str(assigned).startswith("review:"):
            assigned = None                              # reviewers gate by <type>, not block
        ref = slots.get("block")
        canon = self._resolve_block_ref(str(ref)) if ref else None
        if ref and canon and canon != ref:
            self.log("flow", f"block ref '{ref}' -> '{canon}' (canonicalized)")
        block = canon
        if assigned:
            if block and block != assigned:
                self.log("flow", f"{sender.get('id')}: text ref '{block}' != assigned "
                                 f"'{assigned}' -> sender's assignment wins (A-1)")
            block = assigned
        if block:
            slots = {**slots, "block": block}
        rule = self.ADMISSION.get(tag)
        if rule:
            if rule.get("block") and (not block or self.st.row(block) is None):
                self.log("flow", f"{tag} for unknown block '{ref}' -> refused (no canon row)")
                self.events.unclassified(f"{tag} block ref: {ref}",
                                         "unknown block id (no canon row)", sender=sender)
                self._bounce(sender, f"'{tag}' names no block the canon knows"
                                     + (f" (ref '{ref}')" if ref else " (no --block)"))
                return None
            g = self.st.gate.get(block)
            stages = rule.get("stages")
            if stages is not None and not (g and g.get("stage") in stages):
                self.log("flow", f"{tag} for {block} noted "
                                 f"(stage={(g or {}).get('stage')}) -> no action")
                return None
            cca = rule.get("close_confirm_at")
            if (cca and g and g.get("stage") == cca
                    and not slots.get("clean_confirm")):
                raw = (slots.get("_raw") or "").strip().lower()
                pfx = (self.renderer.prompts.close_confirm_prefix() or "clean").lower()
                if raw and not raw.startswith(pfx):
                    self.log("flow", f"gate[{block}] {cca}: reply doesn't open "
                                     f"'{pfx}' -> not a confirmation")
                    return None
        return slots

    def _resolve_by_sender(self, tag, slots, sender):
        """Sender-truth resolution (01-13): completes A-1/W11's sender-first rule for the
        two roles the block-shaped vocabulary never fit. tron-14 F1/F4/F8/F10: architect
        and reviewer protocol acts rode the classify path hoping for their exact tag; a
        `worker.done` misfire hit the block-admission wall ('unknown block id') and the
        job/gate stalled until the operator hand-cranked the report back in. The sender's
        own engine-side state names the only thing its 'done' CAN mean — resolve there,
        deterministically, never from prose. Returns (tag, slots), or (None, None) to
        note-and-drop (an architect residue line after its job already advanced)."""
        sid = (sender or {}).get("id")
        w = next((x for x in self.st.workers if x.get("id") == sid), None) if sid else None
        if w is None:
            return tag, slots
        if w.get("role") == "architect" and tag in ("worker.done", "worker.recorded"):
            job = w.get("current_job") or {}
            kind = job.get("kind")
            if w.get("status") != "busy" or not kind:
                # Post-completion residue (the job already advanced) — a receipt to
                # note, never a refusal and never a bounce (tron-14 F3's class).
                self.log("flow", "architect report with no live job -> noted")
                return None, None
            if kind in ("forward", "reconcile"):
                return "architect.reconciled", {**slots, "block": job.get("block")}
            if kind == "log":
                return "architect.logged", {**slots, "block": "adhoc"}
            # triage: its 'done' IS the answer -> relay to the original asker (T10).
            return "architect.relay", {**slots,
                                       "detail": slots.get("detail")
                                       or slots.get("_raw", "")}
        if w.get("role") == "reviewer" and tag == "worker.done":
            return "worker.review_done", {**slots,
                                          "type": w.get("rtype") or slots.get("type")}
        return tag, slots

    def _bounce(self, sender, why):
        """01-13: a refused or unreadable report is NEVER a silent discard — the sender
        gets one line naming why and the exact re-send shape (the mechanized form of
        tron-14's six manual operator re-deliveries). Live roster only; rate-limited to
        one bounce per wake-ceiling span per worker so a confused worker is corrected,
        not flooded."""
        sid = (sender or {}).get("id")
        w = next((x for x in self.st.workers if x.get("id") == sid), None) if sid else None
        if w is None:
            return
        now = self._now_s()
        last = w.get("bounced_at")
        if last is not None and now - last < float(self.knobs.get("wake_ceiling_sec", 30)):
            return
        w["bounced_at"] = now
        self._to_worker(sid,
                        f"[TRON]  {sid} — I could not act on your last report ({why}). "
                        f"Re-send it through the report command with its verb as data: "
                        f"add `--tag <verb>` (done | recorded | wall | review-done | "
                        f"clean) and `--block <your block id>` when the act concerns "
                        f"your block. Say the same thing; carry the tags.",
                        "report.bounce")
        self.log("flow", f"bounced {sid}: {why}")

    def _ingest(self, tag, slots, sender):
        if tag == "drop":                                # A-2: invalid structured line, already recorded
            return
        tag, slots = self._resolve_by_sender(tag, slots, sender)   # 01-13: sender-truth first
        if tag is None:
            return
        # T1 (01-15 D-16-1 seam 1): a held (walled) sender's VERB is queued whole, never
        # processed and never dropped — its modifiers (--branch, --block) already
        # registered above in _classify, independent of hold state. Durable on the worker
        # record (manifest state, survives a restart); replayed in arrival order the
        # instant the worker un-holds (_h_apply_decision's resume); discarded whole on
        # abandon (the worker record itself goes with it, _force_release_block).
        sid = (sender or {}).get("id")
        hw = next((x for x in self.st.workers if x.get("id") == sid), None) if sid else None
        if hw is not None and hw.get("status") == "walled":
            hw.setdefault("held_verbs", []).append({"tag": tag, "slots": slots})
            self.log("flow", f"{sid} is walled -> verb '{tag}' queued "
                             f"({len(hw['held_verbs'])} pending)")
            return
        action = self.tags.get(tag)
        if not isinstance(action, dict):
            self.log("flow", f"unknown tag '{tag}'")
            return
        if sender.get("id") and not slots.get("worker_id"):
            slots = {**slots, "worker_id": sender["id"]}
        slots = self._admit(tag, slots, sender)          # the ONLY admission checkpoint
        if slots is None:
            return
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
        elif handler == "triage_peer":                   # T10: a peer question -> the architect sorts it
            self._triage_to_architect(slots.get("detail", "") or "(peer question)",
                                      sender=slots.get("worker_id"), block=slots.get("block"))
            self._emit("pulse")
        elif handler == "relay_to_worker":               # T10: architect's answer -> the original asker
            self._relay_architect_answer(slots)
        elif handler == "escalate_to_operator":          # T10: "operator's call" -> raise it (wall edge)
            self._escalate_from_architect(slots)
        elif handler in ("edit_self", "best_effort"):
            self.log("side", f"{handler}: {slots}")
        # observe / none: deliberately nothing.

    def _relay_architect_answer(self, slots):
        """T10: the architect answered a triaged peer question — relay its reply to the original
        asker (the triage job carries the sender), then advance the architect's queue. Closes the
        silent dead-end where a peer question was logged and never answered."""
        arch = self._architect()
        cur = arch.get("current_job") if arch else None
        target = (cur or {}).get("sender") or slots.get("worker_id")
        answer = slots.get("detail", "")
        if target and not self.dry:
            self._to_worker(target, f"[TRON] Architect: {answer}", "architect.relay")
        self.log("flow", f"relay architect answer -> {target or '?'}")
        self._architect_advance()
        self._emit("pulse")

    def _escalate_from_architect(self, slots):
        """T10: the architect judged a triaged question to be the operator's call — advance its
        queue and raise it to the operator on the existing wall edge."""
        arch = self._architect()
        cur = arch.get("current_job") if arch else None
        block = (cur or {}).get("block") or slots.get("block") or ""
        sender = (cur or {}).get("sender") or slots.get("worker_id")
        detail = slots.get("detail", "") or "architect raised to operator"
        self._architect_advance()
        if block:
            self._emit("wall:raised:" + block,
                       {"block": block, "worker_id": sender, "detail": detail})
        else:
            self.emit("escalate.unclassified", {"detail": detail})
        self._emit("pulse")

    def _record_branch(self, slots):
        """The worker reported the branch it NAMED for its block (T2). Record it so the DONE gate
        resolves the block's PR/CI by the real name — TRON never guesses `feat/<block>`.
        tron-13 D1/FS-1/FS-3: a blockless declaration from a non-engineer (reviewer /
        architect) names a PAPERWORK branch — keyed purely on the sender's worker record
        (never `st.branches`, which is block-gate territory and R-4-guarded), FIFO so a
        second declaration never orphans a parked first."""
        block, branch = slots.get("block"), slots.get("branch")
        if not branch:
            return
        wid = slots.get("worker_id")
        w = next((x for x in self.st.workers if x.get("id") == wid), None)
        # W11 (tron-13 attempt 1): st.branches is OWNER-ONLY — a block's branch is
        # writable only by the ENGINEER ASSIGNED to it (A-1 sender-first, now for
        # declarations too). The architect's reconcile report named a block in prose;
        # classify handed that ref to this recorder and the architect's PAPERWORK branch
        # became the block's registered branch — the gate then chased a deleted ref and
        # walled the block's own engineer. A non-owner's block ref is DISCARDED here;
        # its branch routes to the sender's paperwork FIFO, which is what a non-owner's
        # branch always is.
        owner = (w is not None and w.get("role") == "engineer"
                 and block and w.get("block") == block)
        if not owner:
            if w is None or w.get("role") == "engineer":
                # Unknown sender, or an engineer naming someone else's block: never record.
                self.log("flow", f"branch declaration from {wid} for '{block}' refused "
                                 f"(not the owner) -> dropped")
                return
            fifo = w.setdefault("pending_landings", [])
            if branch not in fifo:
                fifo.append(branch)
            self.log("flow", f"paperwork branch[{wid}] += {branch}"
                             + (f" (block ref '{block}' discarded — W11: non-owners "
                                f"never claim a block)" if block else ""))
            return
        if not block or not branch:
            return
        # R-4: one live gate per branch name. A second block declaring an already-claimed
        # branch would make branch_merged read block A's merge as block B's — and the W1
        # ratchet would lock the wrong conclusion in. Refuse + escalate, never record.
        claimed = next((b for b, br in self.st.branches.items()
                        if br == branch and b != block and b in self.st.gate), None)
        if claimed:
            self.emit("escalate.gate", {"worker_id": slots.get("worker_id") or "?",
                                        "block": block,
                                        "detail": f"branch '{branch}' already claimed by live "
                                                  f"gate {claimed} — refuse duplicate claim",
                                        "case": self._open_case(block, "branch",
                                                                slots.get("worker_id"),
                                                                f"duplicate branch claim: {branch}")})
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
        base = f"{len(running)} running, {done} done on trunk"
        # F-4/R-7: parked calls lead the digest — the clock is pull; the park notice sits
        # where the operator's next pull lands, never behind a separate question.
        parked = sorted(cid for cid, c in self.st.pending_cases.items()
                        if c.get("decision") is None)
        if parked:
            safe = [cid for cid in parked
                    if self.st.pending_cases[cid].get("parked") == "safe"]
            note = f" (safe-parked: {', '.join(safe)})" if safe else ""
            return f"your call first — parked on you: {', '.join(parked)}{note}. {base}"
        return base

    def _undecided_cases(self):
        return {cid: c for cid, c in sorted(self.st.pending_cases.items())
                if c.get("decision") is None}

    def _drive_cases(self):
        """F-4/R-7 (tron-13 D4): a parked operator case re-pings on a wall-clock ladder,
        then caps into a NAMED, resumable safe-park — an AFK operator costs latency,
        never a silently stalled session (P-1's class, closed at the engine, not the
        monitor). One pacing law (S-1): re-ping every case_reping_after x wake_ceiling_sec
        of wall-clock; after case_reping_max unanswered re-pings the next span posts the
        safe-park notice and goes quiet. A safe-parked case stays in pending_cases
        (MANIFEST) and settles through _h_apply_decision exactly like a fresh one —
        resuming costs the operator one reply, nothing else.
        Derived latencies at defaults (ceiling 30s, R-8): re-pings at 10/20/30 min,
        safe-parked at 40 min."""
        now = self._now_s()
        for cid, case in self._undecided_cases().items():
            if case.get("parked") == "safe":
                continue
            anchor = case.setdefault("ping_anchor_s", now)
            if now - anchor < self._pace("case_reping_after", 20):
                continue
            case["ping_anchor_s"] = now
            slots = {"worker_id": case.get("worker_id") or "?",
                     "block": case.get("block") or "?", "case": cid}
            n = case.get("repings", 0)
            if n >= int(self.knobs.get("case_reping_max", 3)):
                case["parked"] = "safe"
                self.events.event("case_safe_parked", block=case.get("block"), cid=cid,
                                  **{"repings": n, "detail": case.get("detail")})
                self.emit("escalate.wall", {**slots, "detail":
                          f"{case.get('detail')} — safe-parked after {n} unanswered "
                          f"pings; the session runs on and this resumes the moment "
                          f"you reply"})
                self.log("flow", f"case {cid} safe-parked after {n} pings")
                continue
            case["repings"] = n + 1
            self.events.event("case_reping", block=case.get("block"), cid=cid,
                              **{"n": n + 1})
            self.emit("escalate.wall", {**slots, "detail":
                      f"{case.get('detail')} — still parked, {n + 1} unanswered "
                      f"ping(s)"})
            if self._tg_on():
                self.emit("tg.escalate", {"worker_id": slots["worker_id"],
                                          "detail": f"{cid} still parked: "
                                                    f"{case.get('detail')}"})

    # ── wall/hold invariants (T3, 01-17, tron-23) ──
    def _sweep_wall_invariant(self, w, ping_min):
        """A `walled` worker is only ever consistent while it is parked ON a live wall
        case (D-15-2's whole model). Either half of that pairing missing is an
        inconsistency, named after one silence window (the same wall-clock law, and the
        same `since` idiom, as the gate-orphaned net just below) — never silent, never
        indefinite:
          (a) settled case -> un-held worker: the case for this worker/block already
              carries a decision (settled) but the worker is still walled — un-hold it via
              the ordinary _unhold_worker + the 01-16 post-unhold nudge, exactly as an
              operator `resume` would;
          (b) walled worker -> pending case: no case at all exists for this worker/block —
              re-raise one (the wall_detail recorded at hold time if it's still there, else
              name the inconsistency itself) so the operator can always reach it.
        A live, still-undecided case is the ordinary wall state — never touched."""
        block = w.get("block")
        wid = w.get("id")
        case = next((c for c in self.st.pending_cases.values()
                    if c.get("kind") == "wall"
                    and (c.get("worker_id") == wid or (block and c.get("block") == block))),
                   None)
        if case is not None and case.get("decision") is None:
            w.pop("wall_bad_since", None)      # a live pending case is the normal wall state
            return
        since = w.setdefault("wall_bad_since", self._now_s())
        if self._now_s() - since < ping_min * 60:
            return
        w.pop("wall_bad_since", None)
        if case is not None:
            # (a): the case settled but nothing un-held this worker. Close the case too
            # (parity with an ordinary `resume` settle, which always closes what it acts
            # on) — a decided case has nothing left for any settle to do with it.
            self._unhold_worker(w)
            self._close_case(None, case)
            self.log("flow", f"sweep: {wid} walled with a settled case -> un-held")
            self._post_unhold_nudge(w, block)
            self._emit("pulse")
        else:
            # (b): no case at all — this worker is unreachable. Re-raise one.
            detail = w.pop("wall_detail", None) or (
                f"{wid} is walled with no pending case"
                + (f" for {block}" if block else "") + " — invariant repair")
            self._reraise_wall(block, wid, detail)

    def _reraise_wall(self, block, wid, detail):
        """T3(b): repair a caseless wall the same way every OTHER wall parks — a fresh
        case, the ordinary escalate.wall notice. Never routed through _h_escalate: its
        `block in st.blocked` idempotency guard exists to stop a LIVE wall being
        double-parked, which would wrongly swallow this repair (there is no live case
        here); the worker is already held (never re-hold it — that's the T3 root-cause fix
        in _hold_worker) and the block never left st.blocked."""
        if block and block not in self.st.blocked:
            self.st.blocked.append(block)
        case_id = self._open_case(block, "wall", wid, detail)
        self.events.event("escalate", actor=wid or "?", block=block, cid=case_id,
                          tag="worker.wall", detail=detail)
        self.emit("escalate.wall", {"worker_id": wid or "?", "block": block or "?",
                                    "detail": detail, "case": case_id})
        if self._tg_on():
            self.emit("tg.escalate", {"worker_id": wid or "?", "detail": detail})
        self.log("flow", f"sweep: {wid} walled with no case -> reopened ({block or '?'})")

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
            # T2 (D-15-2): a walled worker is deliberately idle (parked on the operator) —
            # the silence/stall machinery must never treat that as a hang and force a
            # second, unintended release out from under the hold.
            if w.get("status") == "walled":
                # T3 (01-17, tron-23): the hold ITSELF must stay a valid pairing — a walled
                # worker is only ever consistent while a wall case owns it. Checked here,
                # not skipped like "released".
                self._sweep_wall_invariant(w, ping)
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
            # Deterministic two-step online handshake (01-10 return-path fix): a spawned worker is
            # "online" once its runner has completed the identity/spawn turn (turns >= 1) — a runner
            # liveness FACT, not a classified message. Deliver its pending assignment off that
            # signal; no report.sh dependency, no turn-forwarding, no classify. Idempotent: the
            # handler clears pending_assign, so a later report.sh "online" is a harmless no-op.
            if w.get("pending_assign") and (jobs.find(w.get("id"), idx) or {}).get("turns", 0) >= 1:
                self._h_worker_online({"worker_id": w.get("id")})
            # 01-11 FX-2 (tron-06 P2): the MANIFEST mirrors the runner's own state — an idle
            # worker must never read `working`. Deterministic file read, reconciled every tick.
            rstate = (jobs.find(w.get("id"), idx) or {}).get("state")
            if w.get("status") in ("working", "idle") and rstate in ("working", "idle"):
                w["status"] = rstate
            sig = jobs.activity_signals(w.get("id"), since_iso=last, idx=idx)
            delta = sig.get("last_activity_delta_s")
            # tron-07 W8 + A-4: a runner mid-turn is WORKING, not silent — it writes
            # `working` once at turn start (now WITH its own declared turn deadline) and
            # nothing more until the turn ends, so to the silence machinery a long turn is
            # indistinguishable from death (an 8-minute review turn was stall-recovered at
            # 8m05s -> infinite reviewer churn). Exempt a working runner until ITS OWN
            # deadline (+grace) — heterogeneous per-role ceilings for free; the engine-env
            # mirror is only the fallback for pre-A-4 runner records. Past the deadline the
            # runner is presumed suspended (SIGSTOP/host freeze — its own TURN_TIMEOUT_S
            # loop isn't executing): escalate, and R-2(ii) follows the release SIGTERM with
            # SIGKILL after a grace — on THIS path only, never on ordinary releases.
            if rstate == "working":
                rec = jobs.find(w.get("id"), idx) or {}
                ddl = rec.get("deadline")
                now_s = self._now_s()
                within = (now_s <= float(ddl) + KILL_GRACE_S) if ddl else (
                    delta is not None and delta <= TURN_CEILING_S + 120)
                if within:
                    w.pop("pinged_at", None)  # a working turn ends the silence episode
                    w.pop("kill_at", None)
                    w.pop("orphan_since", None)  # a working turn ends any orphan suspicion too
                    continue
                # past the runner's own deadline: presumed suspended
                if not w.get("kill_at"):
                    w["kill_at"] = now_s + KILL_GRACE_S
                    self._emit("worker:stalled", {"worker_id": w.get("id")})
                elif now_s >= float(w["kill_at"]):
                    jobs.kill_hard(w.get("id"), idx)
                    w.pop("kill_at", None)
                continue
            if jobs.has_positive_activity(sig):
                # T3 (01-15 D-16-1 seam 3): the runner's own idle-poll keeps `updated_at`
                # fresh even doing nothing — positive activity forever, so a merely-idle
                # worker NEVER reaches the silent-stall check below. That is exactly how
                # an idle-bound orphan "escapes every net" (tron-16, worker_count=1,
                # deadlocked ~30 min with no escalation raised): an engineer idle, BOUND to
                # a block, whose gate is orphaned — the block already shows done, or no
                # gate object exists for it at all — is an INCONSISTENT state, never a
                # silent wait. Named, never silent, after one full silence window (S-1
                # wall-clock law). Naturally one-shot: _gate_giveup raises a wall, which
                # HOLDS this worker (walled) — and this loop skips walled workers up top —
                # so it never re-fires on the same orphan.
                if w.get("role") == "engineer" and rstate == "idle" and w.get("block"):
                    blk = w.get("block")
                    row = self.st.row(blk)
                    g = self.st.gate.get(blk)
                    done = bool(row and row.get("status") == "done")
                    if g is None:
                        # 01-16 addendum (tron-19/20): the 01-15 clock (`delta > ping*60`)
                        # keys on the runner record's own freshness — which the idle-poll
                        # REFRESHES on every poll, so for a LIVE idle runner the predicate
                        # could never fire (the exact trap the comment above names, one
                        # layer down; observed 20+ silent minutes on both tron-19 and
                        # tron-20). Fire on EITHER clock: a stale record (the dead/frozen
                        # runner arm, unchanged), or one full silence window of
                        # continuously OBSERVED inconsistency (idle + bound + gateless) on
                        # the engine's own wall clock — which no idle-poll can refresh.
                        since = w.setdefault("orphan_since", self._now_s())
                        due = ((delta is not None and delta > ping * 60)
                               or self._now_s() - since >= ping * 60)
                        if due and done:
                            # arm (a), tron-20: the block is ✅ with nothing left to gate —
                            # nothing remains for this worker at all. Release it (the
                            # ordinary event-logged chokepoint) and free the slot; an
                            # operator case here is pure noise — there is no decision to
                            # make (supersedes the 01-15 escalate-on-done arm, whose wall
                            # needed a manual `tron recover` anyway).
                            self._release_worker(w, notify=False, reason="force-release")
                            self.log("flow", f"sweep: {w.get('id')} idle on done+gateless "
                                             f"{blk} -> released (slot freed)")
                            self._emit("pulse")
                        elif due:
                            # arm (b), tron-19: idle + bound + open block + no gate is a
                            # MUTUAL WAIT (the runner awaits a mailbox message; the engine
                            # awaits the worker's report) — never a silent wait state.
                            self._gate_giveup(
                                blk, {}, w.get("id"),
                                f"{w.get('id')} idle, bound to {blk}, but no gate exists "
                                f"for it (mutual wait — the runner idles awaiting a "
                                f"message)",
                                "gate-orphaned",
                                "check the worker/block binding; resume or reassign")
                        continue
                    w.pop("orphan_since", None)   # a live gate owns this worker's pacing
                continue
            if delta is None:
                continue
            if delta > esc * 60:
                self._emit("worker:stalled", {"worker_id": w.get("id")})
            elif delta > ping * 60 and not w.get("pinged_at"):
                w["pinged_at"] = util.now_iso()
                self.emit("heartbeat.ping", {"worker_id": w.get("id")}, worker_id=w.get("id"))
        # T2 (01-16, D-17-1): the gate-orphaned predicate above requires an idle WORKER to
        # exist to fire — a gate whose block has NO live bound worker AT ALL (purged,
        # force-released, or any other path that outlives the roster entry) escapes it
        # entirely, exactly tron-17's live-lock: every net here keys on a worker, and there
        # was no worker. This extends the same one-silence-window law to that case, using
        # the gate's own clock (there's no runner left to read activity from). Never fires
        # under a blank trunk read (T3) — a fault tick touches no gate state at all.
        if not self._trunk_fault:
            now = self._now_s()
            for block, g in list(self.st.gate.items()):
                if str(block).startswith("review:") or g.get("violation_pending"):
                    continue
                if self._worker_id_for_block(block) is not None:
                    g.pop("orphan_since", None)
                    continue
                since = g.setdefault("orphan_since", now)
                if now - since >= ping * 60:
                    self._resolve_workerless_gate(block, g)

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

    def _settle_regex(self, text):
        """T3 (D-15-3): deterministic operator settle — a CASE-<n> id plus a settling verb
        (approve|resume|abandon) anywhere in the text resolves to `operator.decision` slots
        with zero model calls. Returns None (no match -> classify) when either half is
        missing; `_h_apply_decision` resolves the case (and its block) by the id itself, so
        no `block` slot is needed here."""
        m = CASE_ID_RE.search(text or "")
        v = SETTLE_VERB_RE.search(text or "")
        if not m or not v:
            return None
        return {"case": f"CASE-{int(m.group(1)):03d}", "decision": v.group(1).lower()}

    def _classify(self, msg):
        # A-2 (tron-13 D2): a structured report resolves deterministically — the model is
        # never consulted for a line that already carries its verb as data.
        # W10 (co-signed shape): `--branch` is a MODIFIER honored on ANY report — the
        # reply_line promises it, so it records HERE, verb or no verb (non-engineers ->
        # the FIFO; an engineer's declaration keeps the classify+_admit path so its
        # assignment pins the block). Structured slots then MERGE OVER the classify
        # result (data over prose) so a terse declaration can never silently no-op.
        data_slots = dict(msg.get("slots") or {})
        if data_slots.get("branch"):
            # 01-13 (tron-14 F6): the hoist must carry the SENDER'S assigned block for an
            # engineer — hoisted declarations arrived blockless, _record_branch's owner
            # check (W11) refused them, and a structured `done --branch X` (which never
            # reaches classify, the path the W10 comment assumed would backfill the
            # block) left `branches: {}` through three declarations and walled the gate.
            snd_id = (msg.get("sender") or {}).get("id")
            sw = next((x for x in self.st.workers if x.get("id") == snd_id), None)
            blk = (sw or {}).get("block") if (sw or {}).get("role") == "engineer" else None
            self._record_branch({"branch": data_slots["branch"],
                                 "worker_id": snd_id,
                                 "block": blk or data_slots.get("block")})
        stag, sslots = self._structured(msg)
        if stag == "drop":
            return "drop", {}
        if stag:
            return stag, sslots
        sender = msg.get("sender", {})
        raw = msg.get("text", "")
        # T3 (D-15-3): the operator inbox is trusted input — before any classify/LLM call,
        # a CASE-<n> id plus a settling verb ANYWHERE in the message settles that case
        # deterministically (zero model calls; `resume CASE-007` and `CASE-007: resume`
        # both hit). No match falls through to classify exactly as today.
        if sender.get("kind") == "operator":
            settled = self._settle_regex(raw)
            if settled:
                return "operator.decision", {**settled, **data_slots}
        payload = {"text": raw, "sender": sender}
        ok, out, attempts = judge.call("classify_message", payload, self.ctx, self._max_retries,
                                       elog=self.events)
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
            self._bounce(sender, "I could not read it")           # 01-13: never a silent discard
            return "unclassified", {"detail": raw[:120]}
        tag = out["tag"]
        if tag == "unclassified":                         # the model itself found no matching tag (T3)
            self.events.unclassified(raw, "model returned unclassified (no tag matched)", sender=sender)
            self._bounce(sender, "it fits no tag I know")         # 01-13: correct the sender too
        return tag, {**out.get("slots", {}), **data_slots}   # W10: data over prose

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
        self.st.data["review_markers"] = {}      # since-last-review markers don't carry across sessions (T6)
        self.st.data["checkpoints"] = []
        self.st.data["branches"] = {}            # worker-named branches don't carry across sessions (T2)
        self.st.data["approvals"] = dict(DEFAULT_APPROVALS)
        # Ask-before-merging (T8): the bootup question (live_config) or the knob flips the trunk-merge
        # step to ASK. Default APPROVED — TRON instructs the merge unprompted.
        if bool(self.st.live_config.get("ask_before_merging")
                or self.knobs.get("ask_before_merging")):
            self.st.data["approvals"]["merge"] = "ASK"
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
            self._to_worker(w.get("id"), line, "broadcast")

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

    def _residue_sweep(self):
        """D1 landing point 4: session-end residue — NAMED, never silent, and NEVER
        auto-landed (nobody is left to rebase or answer a violation; the operator
        decides). One failure record naming every leftover + one parked case that rides
        the session-end park surfacing (F-4/R-7)."""
        residue = []
        for w in self.st.workers:
            for br in (w.get("pending_landings") or []):
                residue.append(f"{w.get('id')}: unlanded paperwork branch {br}")
        for f in (self.st.data.get("failed_landings") or []):
            residue.append(f"{f.get('worker')}: failed landing {f.get('branch')} "
                           f"({f.get('detail')})")
        for block, br in (self.st.branches or {}).items():
            if trunk.branch_exists(self.paths["root"], br, self.dry):
                residue.append(f"{block}: branch {br} still exists")
        for path, br in trunk.list_worktrees(self.paths["root"], self.dry):
            residue.append(f"leftover worktree {path} (on {br or '?'})")
        if not residue:
            return
        detail = "; ".join(residue)
        self.events.failure("session-residue", "unlanded-paperwork",
                            "session-end residue sweep", detail,
                            node="_end_session", next_action="escalate")
        self._open_case(None, "residue", None, f"session-end residue: {detail}")
        self.log("flow", f"session residue: {detail}")

    def _end_session(self):
        if self.ended:
            return
        self._residue_sweep()                # D1: leftovers become a named parked case first
        for w in self.st.workers:
            wid = w.get("id")
            if not self.dry:
                # tron-07 W4: through emit(), never a bare renderer.render — emit injects the
                # universal reply slots ({report}, {worker_id}) every PMT body now renders;
                # the direct render made `tron stop --force` crash on the missing slot.
                self.emit("close.worker", {"worker_id": wid}, worker_id=wid)
                jobs.release(wid)
            w["status"] = "released"
        done = sum(1 for r in self.st.pipeline if r.get("status") == "done")
        # F-4/R-7 rider: a call still parked at session end is surfaced HERE — the manifest
        # archives on a clean end, so an unsurfaced case would vanish from view entirely.
        parked = self._undecided_cases()
        for cid, case in parked.items():
            self.emit("escalate.wall",
                      {"worker_id": case.get("worker_id") or "?",
                       "block": case.get("block") or "?", "case": cid,
                       "detail": f"{case.get('detail')} — session is ending with this "
                                 f"still parked on you; it goes to the archive unresolved"})
        self.events.event("session_end", done=done,
                          **({"parked_cases": sorted(parked)} if parked else {}))
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
        """Reattach: rebuild live workers from the TRON worker store (runner.json per worker),
        re-arm lost work, and re-read the canon trunk. No status writes (TRON owns none).
        T1 (01-16, D-17-1): a dead-runner purge is a RELEASE like every other worker exit —
        never a silent pool removal. tron-17's CASE-006 died mid-hold with its block already
        ✅ on trunk: the old purge just dropped it from the roster with no release event and
        no gate handling (`_redispatch` no-ops on a done block), so the DONE gate stranded at
        `close` with nobody visibly accountable for it and the operator's later `resume` found
        nothing to un-hold. Every purge now emits `release` (reason `stall-recover`, the same
        vocabulary `_h_recover` already uses for a live-detected stall) and hands any gate the
        worker held to T2's workerless-gate resolution."""
        self._refresh_from_trunk()
        idx = jobs.index()
        alive, purged, rebuilt = 0, 0, []
        for w in list(self.st.workers):           # a copy: _release_worker mutates the roster
            if jobs.is_alive(w.get("id"), idx):
                rec = jobs.find(w.get("id"), idx) or {}
                w["session_id"] = rec.get("session_id", w.get("session_id"))
                rebuilt.append(w)
                alive += 1
            else:
                purged += 1
                blk, role = w.get("block"), w.get("role")
                self._release_worker(w, notify=False, reason="stall-recover")
                if blk and not str(blk).startswith("review:") and role != "architect":
                    g = self.st.gate.get(blk)
                    if g is not None:
                        self._resolve_workerless_gate(blk, g)   # T2: hand the orphaned gate off
                    else:
                        self._redispatch(blk)          # no gate yet -> the ordinary lost-work re-arm
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

    def _resolve_block_ref(self, ref):
        """Canonicalize a worker-mentioned block ref against the pipeline (tron-07 W3):
        the exact id, else the single id the ref prefixes (worker shorthand '01-02' for
        '01-02-logic'), else None — TRON never gates on an id the canon doesn't know."""
        ids = [r.get("id") for r in self.st.pipeline if r.get("id")]
        if ref in ids:
            return ref
        hits = [i for i in ids if i.startswith(ref)]
        return hits[0] if len(hits) == 1 else None
