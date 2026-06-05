"""console — the operator's interactive front to a running TRON (B7 / D6).

A thin front over the real engine: it runs the bootup Q&A (protocols/bootup.md
steps 1–2), starts the engine, then drops into a bounded REPL. It NEVER decides
flow — free text is handed to the engine, classified by the real judgment tool,
and routed deterministically; commands are a fixed set. The fleet view and event
log read live state (the same files cron ticks write), so the console can be
closed and reattached without losing the run.

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
            print(f"  │  {DIM}architect queue: {len(q)} pending{RST}")
        print(f"  {BOLD}└────────────────────────────────────────────────────{RST}")

    def show_pipeline(self):
        st = self._state()
        rows = sorted(st.pipeline, key=lambda r: (r.get("order") or 1e9))
        print(f"  {BOLD}┌─ PIPELINE ────────────────────────────────────────{RST}")
        if not rows:
            print("  │  (empty)")
        for r in rows:
            kind = r.get("kind", "block")
            mark = "★" if kind == "adhoc" else " "
            print(f"  │ {mark} {str(r.get('id','')):<12} {r.get('status',''):<14} "
                  f"{r.get('owner','')}")
        cad = st.cadence
        if cad:
            print(f"  │  {DIM}cadence: " +
                  ", ".join(f"{k}={v}" for k, v in cad.items()) + RST)
        print(f"  {BOLD}└────────────────────────────────────────────────────{RST}")

    # ── bootup (protocols/bootup.md steps 1–2) ──
    def _already_running(self):
        st = self._state()
        return bool(st.data.get("session", {}).get("started_at")) and bool(st.pipeline)

    def bootup(self):
        print(f"{BOLD}== TRON bootup =={RST}")
        st = self._state()
        n_blocks = len([r for r in st.pipeline
                        if r.get("status") not in ("done", "abandoned")])
        # 1. start point — default whole pipeline.
        ans = input(f"Start the whole pipeline ({n_blocks} open blocks)? [Y/n] ").strip().lower()
        if ans in ("n", "no"):
            print(f"{DIM}  (subset/resume scoping is operator-driven; edit pipeline statuses "
                  f"to pending/done before start, then re-run){RST}")
        # 2. worker_count.
        worker_count = None
        while worker_count is None:
            v = input("worker_count (engineers + reviewers; architect is extra)? ").strip()
            if v.isdigit() and int(v) > 0:
                worker_count = int(v)
            else:
                print(f"{DIM}  (a positive integer){RST}")
        print()
        Engine(self.ctx).start(worker_count)        # 3–4: spawn architect + first pulse (emits live)
        self._install_cron()                         # autonomous heartbeat (idempotent; skipped in dry)
        print()
        self._banner()

    def _install_cron(self):
        if os.environ.get("TRON_DRY"):
            return
        ci = os.path.join(self.ctx.scripts_dir, "cron-install.sh")
        if os.path.exists(ci):
            os.system(f"bash {ci} >/dev/null 2>&1 || true")

    def reconnect(self):
        print(f"{BOLD}== TRON (reattached) =={RST}  {DIM}replaying recent events{RST}")
        for ev in self._events()[-8:]:
            print(f"{DIM}{ev.get('text','')}{RST}")
        print()
        self._banner()

    def _banner(self):
        print(f"{DIM}  TRON is live (cron ticks it on its own). "
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
            elif c == "help":
                print(f"{DIM}  status · pipeline · tick · attach <id> · log · stop [--force] · "
                      f"help · or talk to TRON{RST}")
            else:
                self._say(line)

    def _tick(self):
        ended = Engine(self.ctx).tick()       # emits live to stdout
        if ended:
            print(f"{DIM}  session ended.{RST}")
            return True
        return False

    def _say(self, line):
        """Free text -> operator inbox -> one engine tick (real classify + route)."""
        util.append_jsonl(self.ctx.operator_inbox,
                          {"text": line, "sender": {"kind": "operator"}})
        before = len(self._events())
        Engine(self.ctx).tick()               # emits live to stdout
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
        ok, detail = Engine(self.ctx).stop(force=force)
        if not ok:
            print(f"[TRON]  {detail}")
            ans = input("        Release anyway? [y/N] ").strip().lower()
            if ans != "y":
                print(f"{DIM}  stop cancelled.{RST}")
                return False
            Engine(self.ctx).stop(force=True)
        # stop() already emitted the session.end line live.
        return True

    def run(self):
        if self._already_running():
            self.reconnect()
        else:
            self.bootup()
        self.repl()
