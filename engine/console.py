"""console — the operator's interactive front to a running TRON (B7 / D6).

A thin front over the real engine: it runs the bootup Q&A (protocols/bootup.md
steps 1–2), starts the engine, then drops into a bounded REPL. It NEVER decides
flow — free text is handed to the engine, classified by the real judgment tool,
and routed deterministically; commands are a fixed set. The fleet view and event
log read live state (the same files the WAKE daemon ticks write), so the console
can be closed and reattached without losing the run — the daemon keeps ticking.

  bootup  -> confirm start point -> worker_count -> Engine.start()
  repl    -> status · pipeline · tick · attach <id> · log · <free text> · stop · help

Run:  tron start   (internally: engine.py console)
"""
import os

import util
import jobs
from fsm import Engine
from state import State
from render import Renderer

DIM, RST, BOLD = "\033[2m", "\033[0m", "\033[1m"


class Console:
    def __init__(self, ctx):
        self.ctx = ctx
        self.renderer = Renderer(ctx)

    # ── event log (the engine's home-events.jsonl is the shared transcript) ──
    def _events(self):
        return util.read_jsonl(self.ctx.home_log)

    def _show_new_events(self, since):
        for ev in self._events()[since:]:
            print(ev.get("text", ""))

    # ── views ──
    def _state(self):
        return State(self.ctx)

    def show_fleet(self):
        st = self._state()
        print(f"  {BOLD}┌─ FLEET ───────────────────────────────────────────{RST}")
        ws = st.workers
        if not ws:
            print("  │  (no workers)")
        for w in ws:
            job = ""
            if w.get("role") == "architect" and w.get("current_job"):
                cj = w["current_job"]
                job = f"{cj.get('kind')}:{cj.get('block') or cj.get('type')}"
            block = job or w.get("block") or "—"
            print(f"  │  {w.get('id',''):<16} {w.get('role',''):<10} "
                  f"{w.get('status',''):<14} {block}")
        q = st.architect_queue
        if q:
            print(f"  │  {DIM}architect queue: {len(q)} queued{RST}")
        print(f"  {BOLD}└────────────────────────────────────────────────────{RST}")

    def show_pipeline(self):
        # Reads the trunk cache the engine rebuilt last tick — TRON owns no pipeline,
        # so this is a view of the project's canon (pipeline.md + blocks/*.md), not state.
        st = self._state()
        rows = sorted(st.pipeline, key=lambda r: (r.get("order") or 1e9))
        print(f"  {BOLD}┌─ PIPELINE (trunk) ────────────────────────────────{RST}")
        if not rows:
            print("  │  (empty — no canon pipeline read yet)")
        for r in rows:
            mark = "★" if r.get("section", "").lower().startswith("ad") else " "
            flag = "" if r.get("has_block_file") else f" {DIM}(unscoped){RST}"
            print(f"  │ {mark} {str(r.get('id','')):<12} {r.get('status',''):<13} "
                  f"{(r.get('phase') or r.get('section') or ''):<22}{flag}")
        cad = st.cadence
        if cad:
            print(f"  │  {DIM}cadence: " +
                  ", ".join(f"{k}={v}" for k, v in cad.items()) + RST)
        print(f"  {BOLD}└────────────────────────────────────────────────────{RST}")

    # ── bootup (protocols/bootup.md steps 1–2) ──
    def _already_running(self):
        return bool(self._state().data.get("session", {}).get("started_at"))

    def bootup(self):
        print(f"{BOLD}== TRON bootup =={RST}")
        eng = Engine(self.ctx)
        # 1. run scoping — the session.scope three-way prompt (TRON voice; never status edits).
        print(self.renderer.render("session.scope", {}))
        self._ask_scope(eng)
        # 2. worker_count.
        worker_count = None
        while worker_count is None:
            v = input("worker_count (engineers + reviewers; architect is extra)? ").strip()
            if v.isdigit() and int(v) > 0:
                worker_count = int(v)
            else:
                print(f"{DIM}  (a positive integer){RST}")
        print()
        eng.start(worker_count)                      # 3–4: read trunk, spawn architect + first pulse
        self._start_daemon()                         # the WAKE heartbeat (idempotent; skipped in dry)
        print()
        self._banner()

    def _ask_scope(self, eng):
        """Resolve the operator's run scope into state. TRON then dispatches only in-scope,
        still-open blocks (done stays invisible). It NEVER edits status to scope a run."""
        choice = input("  [1] all  ·  [2] a phase  ·  [3] a range of blocks  → ").strip()
        if choice == "2":
            phase = input("  Which phase (name or number, e.g. 'Phase 2' or '2')? ").strip()
            eng.set_scope("phase", phase)
        elif choice == "3":
            lo = input("  First block ID? ").strip()
            hi = input("  Last block ID? ").strip()
            eng.set_scope("range", [lo, hi])
        else:
            eng.set_scope("all")

    def _start_daemon(self):
        # The WAKE daemon is the only tick-source while a session is live (ND-08); it
        # outlives this console, so closing + reattaching never stops the run. Skipped
        # under dry (tests drive ticks directly). Idempotent: a live daemon is left alone.
        if os.environ.get("TRON_DRY") or not self._already_running():
            return
        import wake
        wake.spawn(self.ctx)

    def reconnect(self):
        print(f"{BOLD}== TRON (reattached) =={RST}  {DIM}replaying recent events{RST}")
        self._start_daemon()                         # re-arm the heartbeat if it died while away
        for ev in self._events()[-8:]:
            print(f"{DIM}{ev.get('text','')}{RST}")
        print()
        self._banner()

    def _banner(self):
        print(f"{DIM}  TRON is live (the WAKE daemon ticks it on its own). "
              f"Commands: status · pipeline · tick · attach <id> · log · stop · help{RST}")
        print(f"{DIM}  Or just talk — your line is classified and routed; out-of-grammar is refused.{RST}\n")

    # ── REPL ──
    def repl(self):
        while True:
            try:
                line = input("tron> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                if self._stop():
                    break
                continue
            if not line:
                continue
            cmd, _, arg = line.partition(" ")
            c = cmd.lower()
            if c in ("quit", "exit", "stop"):
                if self._stop(force=(arg.strip() == "--force")):
                    break
            elif c in ("status", "fleet"):
                self.show_fleet()
            elif c == "pipeline":
                self.show_pipeline()
            elif c == "tick":
                self._tick()
            elif c == "attach":
                self._attach(arg.strip())
            elif c == "log":
                for ev in self._events()[-15:]:
                    print(f"{DIM}{ev.get('at','')}{RST}  {ev.get('text','')}")
            elif c in ("pause", "drain", "resume", "halt"):
                self._run_control(c)
                if c == "halt":
                    break
            elif c == "rescope":
                self._rescope(arg.strip())
            elif c == "checkpoint":
                self._checkpoint(arg.strip())
            elif c == "help":
                print(f"{DIM}  status · pipeline · tick · attach <id> · log · "
                      f"pause · drain · resume · halt · rescope · checkpoint <block> · "
                      f"stop [--force] · help · or talk to TRON{RST}")
            else:
                self._say(line)

    # ── run-control (PARLEY ND-09 / R-HALT) — commands, not classified messages ──
    def _run_control(self, verb):
        getattr(Engine(self.ctx), verb)()     # pause | drain | resume | halt — emits live
        if verb == "halt":                    # halt ends the session; tear the daemon down too
            import wake
            wake.stop(self.ctx)

    def _rescope(self, arg):
        parts = arg.split()
        if not parts:
            print(f"{DIM}  rescope all | rescope phase <name> | rescope range <lo> <hi>{RST}")
            return
        mode = parts[0].lower()
        if mode == "phase" and len(parts) >= 2:
            Engine(self.ctx).rescope("phase", " ".join(parts[1:]))
        elif mode == "range" and len(parts) >= 3:
            Engine(self.ctx).rescope("range", [parts[1], parts[2]])
        else:
            Engine(self.ctx).rescope("all")

    def _checkpoint(self, block):
        """Pre-register an operator checkpoint (await ladder rung a): a worker pausing on this
        block reaches the operator, never an auto-ack."""
        if not block:
            print(f"{DIM}  checkpoint <block-id>{RST}")
            return
        st = self._state()
        cps = st.data.setdefault("checkpoints", [])
        if block not in cps:
            cps.append(block)
            st.save()
        print(f"{DIM}  checkpoint registered: {block}{RST}")

    def _tick(self):
        import wake
        ran, ended = wake.locked_tick(self.ctx)   # single-flight; emits live to stdout
        if not ran:
            print(f"{DIM}  (a tick is already running — the daemon has it){RST}")
            return False
        if ended:
            print(f"{DIM}  session ended.{RST}")
            return True
        return False

    def _say(self, line):
        """Free text -> operator inbox -> one engine tick (real classify + route).
        Single-flight: if the daemon holds the tick, the line still landed on the inbox
        and its event-wake picks it up next tick — never lost."""
        import wake
        util.append_jsonl(self.ctx.operator_inbox,
                          {"text": line, "sender": {"kind": "operator"}})
        before = len(self._events())
        wake.locked_tick(self.ctx)            # emits live to stdout
        if len(self._events()) == before:
            print(f"{DIM}  (noted){RST}")

    def _attach(self, wid):
        st = self._state()
        w = next((x for x in st.workers if x.get("id", "").lower() == wid.lower()), None)
        if not w:
            print(f"{DIM}  no such worker: {wid}{RST}")
            return
        print(f"{DIM}  ── {w['id']}  role={w.get('role')}  status={w.get('status')}  "
              f"block={w.get('block')} ──{RST}")
        tail = jobs.timeline_tail(w["id"]) if not os.environ.get("TRON_DRY") else ""
        for ln in (tail.splitlines()[-6:] if tail else ["(no recent activity)"]):
            print(f"  [{w['id']}] {ln}")

    def _stop(self, force=False):
        import wake
        ok, detail = Engine(self.ctx).stop(force=force)
        if not ok:
            print(f"[TRON]  {detail}")
            ans = input("        Release anyway? [y/N] ").strip().lower()
            if ans != "y":
                print(f"{DIM}  stop cancelled.{RST}")
                return False
            Engine(self.ctx).stop(force=True)
        wake.stop(self.ctx)                    # tear down the daemon once the session ended
        # stop() already emitted the session.end line live.
        return True

    def run(self):
        if self._already_running():
            self.reconnect()
        else:
            self.bootup()
        self.repl()
