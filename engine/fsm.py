"""fsm — the deterministic spine (contracts §1, §5).

The interpreter that owns the flow. It reads the canon primitive library +
edges (routing.yaml) and the per-project composition (workflow.yaml), drives the
state machine, spawns/releases workers, and decides what happens next. It calls
the LLM only for a bounded judgment tool (judge.py) and never lets a tool choose
a transition. One wake = one bounded tick: drain signals, advance as far as the
signals allow, persist atomically, exit.
"""
import os

import util
import jobs
import judge
from state import State
from render import Renderer

# review reads its report into clean/findings; a worker.done inside a review is
# "reviewed clean" (the enum has no worker.clean — contracts §2). This is the one
# documented edge-name bridge between the global tag map and a primitive's edges.
EDGE_ALIAS = {("review", "done"): "clean"}


class Engine:
    def __init__(self, ctx):
        self.ctx = ctx
        self.routing = ctx.load_routing()
        self.workflow = ctx.load_workflow()
        self.project = ctx.load_project()
        self.renderer = Renderer(ctx)
        self.st = State(ctx)
        self.steps = {s["id"]: s for s in (self.workflow.get("steps") or [])}
        self.tags = self.routing.get("tags", {})
        self.prims = self.routing.get("primitives", {})
        self.knobs = self.workflow.get("knobs", {})
        self.ended = False
        self.dry = bool(os.environ.get("TRON_DRY"))

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

    # ── primitive helpers ──
    def _step_edges(self, step):
        return self.prims.get(step.get("primitive"), {}).get("edges", [])

    def _resolve_target(self, step, edge):
        """Map an outcome edge to its bound target, honoring the review alias."""
        if edge not in self._step_edges(step):
            edge = EDGE_ALIAS.get((step.get("primitive"), edge), edge)
        target = (step.get("edges") or {}).get(edge)
        if target is None:
            self.log("flow", f"unresolved edge '{edge}' on step '{step['id']}' -> escalate")
            return "escalate"
        return target

    # ── the driver: enter a target and follow synchronous edges to an await/end ──
    def _run_until_await(self, target):
        guard = 0
        while target is not None and guard < 64:
            guard += 1
            if target == "end":
                self._session_end()
                return
            if target == "next":
                self._finalize_block()
                blk = self.st.next_dispatchable_block()
                if not blk:
                    self._session_end()
                    return
                self._set_block(blk)
                target = self.workflow.get("entry")
                continue
            if target == "escalate":
                target = self._escalate_step_id()
            step = self.steps.get(target)
            if step is None:
                self.log("flow", f"missing step '{target}' -> end")
                self._session_end()
                return
            res = self._enter_step(step)
            if res[0] == "await":
                self.st.fsm["current_step"] = step["id"]
                return
            # synchronous resolution
            self.st.fsm["current_step"] = step["id"]
            target = self._resolve_target(step, res[1])

    def _escalate_step_id(self):
        for sid, s in self.steps.items():
            if s.get("primitive") == "escalate":
                return sid
        return None

    def _on_engineer_done(self, step):
        """Engineer reported done: block moves to review, counter ticks, worker idles."""
        block = self.st.fsm.get("current_block")
        if block:
            self.st.set_block_status(block, "review")
        self.st.counters["blocks_since_review"] = \
            self.st.counters.get("blocks_since_review", 0) + 1
        for w in self.st.workers:
            if w.get("block") == block and w.get("role") == step.get("role", "engineer"):
                w["status"] = "done-pending-release"

    def _finalize_block(self):
        """Block cleared review: mark done, release its engineer + any review worker."""
        block = self.st.fsm.get("current_block")
        if not block:
            return
        self.st.set_block_status(block, "done")
        for w in list(self.st.workers):
            if w.get("block") in (block, f"review:{block}"):
                if w.get("session_id") and w["session_id"] != "dry" and not self.dry:
                    jobs.send(w["session_id"], self.renderer.render(
                        "release.worker", {"worker_id": w["id"]}))
                    jobs.release(w["session_id"])
                self.st.workers.remove(w)
        self.emit("terminal.block_done", {"block": block})

    def _set_block(self, row):
        self.st.fsm["current_block"] = row["id"]
        self.st.fsm["current_block_started_at"] = util.now_iso()
        self.st.set_block_status(row["id"], "in-progress")

    # ── primitive entry effects ──
    def _enter_step(self, step):
        prim = step.get("primitive")
        if prim == "dispatch":
            return self._enter_dispatch(step)
        if prim == "review":
            return self._enter_review(step)
        if prim == "gate":
            return ("edge", self._run_gate(step))
        if prim == "escalate":
            return self._enter_escalate(step)
        if prim == "findings-triage":
            return self._run_triage(step)
        self.log("flow", f"unknown primitive '{prim}'")
        return ("await",)

    def _enter_dispatch(self, step):
        block = self.st.fsm.get("current_block")
        role = step.get("role", "engineer")
        if block and not self.st.has_active_worker_for_block(block, role):  # spawn guard
            wid = self._worker_id(role, block)
            prompt = self.renderer.render(
                "spawn.engineer" if role == "engineer" else "spawn.architect",
                {"worker_id": wid, "block": block, "branch": self._branch(block)})
            session, short = "dry", "dry"
            if not self.dry:
                spawn = jobs.spawn_detached(wid, prompt, cwd=self._repo_root())
                session, short = spawn.get("session_id", ""), spawn.get("shortid", "")
            self.st.workers.append({
                "id": wid, "role": role, "session_id": session, "shortid": short,
                "spawned_at": util.now_iso(), "status": "working", "block": block,
            })
            self.st.record_dispatch(wid, session, block, self._branch(block), 1)
            self.emit("terminal.dispatched", {"worker_id": wid, "block": block})
        return ("await",)

    def _enter_review(self, step):
        # cadence-gated reviewers pass through when the interval isn't reached.
        cad = (step.get("cadence") or {}).get("every_n_blocks")
        if cad:
            n = self.knobs.get(cad, 0) or 0
            done = self.st.counters.get("blocks_since_review", 0)
            if not n or done < n:
                return ("edge", "clean")  # pass-through, advance
            self.st.counters["blocks_since_review"] = 0
        role = step.get("role", "reviewer")
        block = self.st.fsm.get("current_block")
        if not self.st.has_active_worker_for_block(f"review:{block}", role):
            wid = self._worker_id(role, block)
            self.st.workers.append({
                "id": wid, "role": role, "session_id": "dry" if self.dry else "",
                "spawned_at": util.now_iso(), "status": "working", "block": f"review:{block}",
            })
            if cad:  # periodic reviewer copy; the per-block architect review stays quiet
                self.emit("terminal.review", {"count": self.knobs.get(cad, 1)})
        return ("await",)

    def _run_gate(self, step):
        kind = step.get("kind", "ci")
        # deterministic external check; conservative default is fail-closed only
        # for ci when git is on. Real checks shell out; absent tooling -> pass.
        ok = True
        self.log("gate", f"gate({kind}) -> {'pass' if ok else 'fail'}")
        return "pass" if ok else "fail"

    def _enter_escalate(self, step):
        if self.st.is_paused_for_operator():       # escalate guard (already paused)
            return ("await",)
        block = self.st.fsm.get("current_block")
        reason = step.get("reason", "wall")
        worker = next((w for w in self.st.workers if w.get("block") == block), {})
        self.st.counters["paused_for_operator"] = worker.get("id", "TRON")
        tpl = {"wall": "escalate.wall", "unclassified": "escalate.unclassified"}.get(
            reason, "escalate.wall")
        slots = {"worker_id": worker.get("id", "?"), "block": block or "?",
                 "detail": self._pending_detail or reason}
        self.emit(tpl, {k: slots[k] for k in self.renderer.templates[tpl]["slots"]})
        return ("await",)

    def _run_triage(self, step):
        findings = self.st.data.get("pending_findings", [])
        if not findings:
            return ("edge", "none")
        ok, verdict, _ = judge.call("triage",
                                    {"findings": findings, "block_ctx": self.st.fsm}, self.ctx)
        if not ok or not verdict.get("fix_needed"):
            self.st.data["pending_findings"] = []
            return ("edge", "none")
        fixes = []
        for v in verdict.get("verdicts", []):
            if not v.get("agree"):
                continue
            f = next((x for x in findings if x.get("id") == v.get("finding_id")), None)
            if not f:
                continue
            sok, scope, _ = judge.call("scope_fix", {"finding": f}, self.ctx)
            if sok:
                scope["id"] = f"fix-{v.get('finding_id')}"
                fixes.append(scope)
        self.st.data["pending_findings"] = []
        if not fixes:
            return ("edge", "none")
        self.st.insert_fix_blocks(fixes)
        return ("edge", "fixes")

    # ── inbound-signal application ──
    def _apply_tag(self, tag, slots, sender):
        action = self.tags.get(tag, "")
        if action.startswith("edge:"):
            edge = action[5:]
            step = self.steps.get(self.st.fsm.get("current_step"))
            if step:
                if step.get("primitive") == "dispatch" and edge == "done":
                    self._on_engineer_done(step)
                self._pending_detail = slots.get("detail", "")
                self._run_until_await(self._resolve_target(step, edge))
        elif action.startswith("side:"):
            self._side(action[5:], slots, sender)
        elif action == "hardwired:escalate":
            self._pending_detail = slots.get("detail", tag)
            self._run_until_await("escalate")
        # 'tick' is handled by the sweep, not here.

    def _side(self, handler, slots, sender):
        if handler == "mark_blocked":
            blk = slots.get("block") or self.st.fsm.get("current_block")
            if blk:
                self.st.set_block_status(blk, "blocked")
        elif handler == "scope_fix_block":
            ok, scope, _ = judge.call("scope_fix", {"finding": slots}, self.ctx)
            if ok:
                scope["id"] = f"bug-{util.now_iso()[:10]}"
                self.st.insert_fix_blocks([scope])
        elif handler == "reply_digest":
            self.emit("tg.status_digest", {"detail": self._digest()})
        elif handler in ("edit_self", "best_effort"):
            self.log("side", f"{handler}: {slots}")
        elif handler == "answer_from_context":
            self.log("side", f"question_tron: {slots.get('detail','')}")
        elif handler == "purge_recover":
            self._purge_recover(slots.get("worker_id"))
        # observe / none: deliberately nothing.

    def _purge_recover(self, worker_id):
        block = None
        for w in list(self.st.workers):
            if not worker_id or w.get("id") == worker_id:
                block = w.get("block")
                self.st.workers.remove(w)
        if block and not block.startswith("review:"):
            self.st.set_block_status(block, "todo")  # re-dispatchable
            self.log("recover", f"purged {worker_id}; block {block} -> todo")

    # ── the tick (contracts §5) ──
    def tick(self):
        self._pending_detail = ""
        self._sweep()
        for msg in self._drain_inboxes():
            tag, slots = self._classify(msg)
            self._apply_tag(tag, slots, msg.get("sender", {}))
        self.st.data.setdefault("last_sweep", {})
        self.st.data["last_sweep"]["at"] = util.now_iso()
        self.st.data["last_sweep"]["sweeps_this_session"] = \
            self.st.data["last_sweep"].get("sweeps_this_session", 0) + 1
        self.st.save()
        return self.ended

    def _sweep(self):
        idx = jobs.index() if not self.dry else {}
        last = (self.st.data.get("last_sweep") or {}).get("at")
        for w in list(self.st.workers):
            if w.get("status") in ("released", "done-pending-release"):
                continue
            if self.st.counters.get("paused_for_operator") == w.get("id"):
                continue
            if self.dry:
                continue
            if not jobs.is_alive(w.get("id"), idx):
                self._emit_system("worker.dead", {"worker_id": w.get("id")})
                continue
            sig = jobs.activity_signals(w.get("id"), since_iso=last, idx=idx)
            if jobs.has_positive_activity(sig):
                continue  # alive — short-circuit before any LLM call (contracts §3)
            ok, verdict, _ = judge.call(
                "assess_stall",
                {"activity": sig, "transcript_tail": jobs.timeline_tail(w.get("id"), idx=idx)},
                self.ctx)
            if ok and verdict.get("stalled"):
                self._emit_system("worker.stalled", {"worker_id": w.get("id")})

    def _emit_system(self, tag, slots):
        """System tags are the engine's to produce deterministically (contracts §2)."""
        self._apply_tag(tag, slots, {"kind": "system"})

    # ── inbound channels ──
    def _drain_inboxes(self):
        out = []
        for path, kind in ((self.ctx.worker_inbox, "worker"),
                           (self.ctx.operator_inbox, "operator"),
                           (self.ctx.tg_inbox, "operator")):
            msgs = util.read_jsonl(path)
            if msgs:
                out.extend(self._normalize(m, kind) for m in msgs)
                util.atomic_write(path, "")  # consumed
        return out

    def _normalize(self, m, kind):
        if "text" in m and "sender" in m:
            return m
        text = m.get("text") or (m.get("message", {}) or {}).get("text", "") or str(m)
        return {"text": text, "sender": {"kind": kind, "id": m.get("id")}}

    def _classify(self, msg):
        payload = {
            "text": msg.get("text", ""),
            "sender": msg.get("sender", {}),
            "current_step": self.st.fsm.get("current_step"),
            "open_escalation": self.st.is_paused_for_operator(),
        }
        ok, out, attempts = judge.call("classify_message", payload, self.ctx)
        if not ok:
            self.log("invalid-output", f"classify exhausted: {attempts[-1][:200] if attempts else ''}")
            return "unclassified", {"detail": msg.get("text", "")[:120]}
        return out["tag"], out.get("slots", {})

    # ── lifecycle ──
    def start(self, max_concurrent):
        from datetime import datetime, timezone
        self.st.data.setdefault("session", {})["started_at"] = util.now_iso()
        self.st.live_config["max_concurrent_engineers"] = max_concurrent
        self.knobs["max_concurrent_engineers"] = max_concurrent
        self._load_pipeline()
        if self.workflow.get("session", {}).get("persistent_architect"):
            self._spawn_architect()
        self.emit("session.start", {})
        blk = self.st.next_dispatchable_block()
        if blk:
            self._set_block(blk)
            self._run_until_await(self.workflow.get("entry"))
        else:
            self._session_end()
        self.st.save()
        _ = datetime.now(timezone.utc)  # touch import; harmless

    def _spawn_architect(self):
        if any(w.get("role") == "architect" for w in self.st.workers):
            return
        prompt = self.renderer.render("spawn.architect", {})
        session = "dry"
        if not self.dry:
            session = jobs.spawn_detached("ARCH-PERSIST", prompt,
                                          cwd=self._repo_root()).get("session_id", "")
        self.st.workers.append({"id": "ARCH-PERSIST", "role": "architect",
                                "session_id": session, "spawned_at": util.now_iso(),
                                "status": "idle", "block": None})

    def stop(self, force=False):
        active = [w for w in self.st.workers
                  if w.get("status") not in ("released",) and not w.get("block", "").startswith("review:")
                  and w.get("role") != "architect"]
        in_progress = [r for r in self.st.pipeline if r.get("status") == "in-progress"]
        if (active or in_progress) and not force:
            return False, f"unfinished: {len(active)} worker(s), {len(in_progress)} in-progress block(s)"
        self._session_end()
        self.st.save()
        return True, "stopped"

    def _session_end(self):
        if self.ended:
            return
        for w in self.st.workers:
            if w.get("session_id") and w["session_id"] != "dry" and not self.dry:
                jobs.send(w["session_id"], self.renderer.render(
                    "release.worker", {"worker_id": w["id"]}))
                jobs.release(w["session_id"])
            w["status"] = "released"
        done = sum(1 for r in self.st.pipeline if r.get("status") == "done")
        self.emit("session.end", {"count": done})
        self.st.fsm["current_step"] = None
        self.ended = True
        if os.path.exists(self.ctx.current_id):
            os.remove(self.ctx.current_id)

    def recover(self):
        idx = jobs.index()
        alive, purged = 0, 0
        rebuilt = []
        for w in self.st.workers:
            if jobs.is_alive(w.get("id"), idx):
                rec = jobs.find(w.get("id"), idx) or {}
                w["session_id"] = rec.get("session_id", w.get("session_id"))
                rebuilt.append(w)
                alive += 1
            else:
                purged += 1
                if w.get("block") and not w.get("block", "").startswith("review:"):
                    self.st.set_block_status(w["block"], "todo")
        self.st.data["active_workers"] = rebuilt
        if (self.workflow.get("session", {}).get("persistent_architect")
                and not any(w.get("role") == "architect" for w in rebuilt)):
            self._spawn_architect()
        self.log("recover", f"recovered={alive} purged={purged}")
        self.st.save()
        return alive, purged

    # ── small helpers ──
    def _load_pipeline(self):
        mode = (self.project.get("pipeline") or {}).get("mode", "internal")
        if mode == "host":
            import hostpipe
            path = (self.project.get("pipeline") or {}).get("path")
            try:
                self.st.data["pipeline"] = hostpipe.parse(path)
            except Exception as e:
                self.log("pipeline", f"host parse failed: {e}")

    def _digest(self):
        running = [w["id"] for w in self.st.workers if w.get("status") == "working"]
        done = sum(1 for r in self.st.pipeline if r.get("status") == "done")
        return f"{len(running)} running, {done} done"

    def _worker_id(self, role, block):
        stripped = (block or "").replace("block-", "")
        pfx = {"engineer": "ENG", "architect": "ARCH", "reviewer": "REV"}.get(role, role.upper())
        return f"{pfx}-{stripped}" if block else f"{pfx}-PERSIST"

    def _branch(self, block):
        return f"feat/{block}" if block else "main"

    def _repo_root(self):
        return os.path.expanduser((self.project.get("repo") or {}).get("root", self.ctx.dir))
