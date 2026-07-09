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
import judge
import reader
import roles as roles_mod
from fsm import Engine
from state import State
from render import Renderer

DIM, RST, BOLD = "\033[2m", "\033[0m", "\033[1m"

# ADR-0003 D-D (T1): the bootup model question's RECOMMENDED fallback tier when
# roles.yaml itself declares no model for a role — a strong tier for the persistent
# spec-owner role, a fast tier for everyone else. Shown as a confirm/override
# suggestion ONLY; it is never a silent fallback — the fail-closed resolution lives at
# fsm._model_for_role / roles.RolesConfig.validate_models (called from Engine.start()),
# never here. Restored surface (01-30 parity); generalized past the old hardcoded
# {"architect", "other"} role-name split (ADR-0002 D4/01-33 made role names
# project-declared, not engine-hardcoded) by keying the TIER off each role's own
# spec_owner/persistent flag instead of its literal name.
ROLE_MODEL_RECOMMENDED = {"architect": "claude-opus-4-8", "other": "claude-sonnet-4-5"}
ROLE_MODEL_LABEL = {"architect": "the persistent architect/spec-owner", "other": "engineers/reviewers"}


class Console:
    def __init__(self, ctx):
        self.ctx = ctx
        self.renderer = Renderer(ctx)
        jobs.configure(ctx.workers_dir)   # point the worker store at this instance (01-10)
        # ADR-0002 D4: the fleet view below needs to recognize the persistent spec_owner
        # worker without a hardcoded "architect" literal — load the same fail-closed
        # roles.yaml Engine(ctx) will (construction here is cheap; the real validation
        # already ran the moment ANY Engine touched this instance).
        paths = ctx.repo_paths(ctx.load_project())
        self.roles = roles_mod.RolesConfig.load(paths["roles_path"], paths["root"])

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
            if w.get("role") == self.roles.spec_owner and w.get("current_job"):
                cj = w["current_job"]
                job = f"{cj.get('kind')}:{cj.get('block') or cj.get('type')}"
            block = job or w.get("block") or "—"
            print(f"  │  {w.get('id',''):<16} {w.get('role',''):<10} "
                  f"{w.get('status',''):<14} {block}")
        q = st.architect_queue
        if q:
            print(f"  │  {DIM}architect queue: {len(q)} queued{RST}")
        parked = {cid: c for cid, c in sorted(st.pending_cases.items())
                  if c.get("decision") is None}
        for cid, c in parked.items():                # F-4/R-7: parked calls in every status pull
            flag = " [safe-parked]" if c.get("parked") == "safe" else ""
            print(f"  │  {BOLD}YOUR CALL{RST}  [{cid}] {c.get('detail','')}{flag}")
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

    def bootup(self, staged_model=None):
        """ADR-0003 D-D+D-J (explicit amendment of ADR-0002 D4; restores the 01-30
        bootup model question 01-33 removed, and AIDE as a real LLM at its bootup
        nodes): steps 1–3 (scope, worker_count, ask-before-merging) are BYTE-FOR-BYTE
        unchanged (frozen journey) — only step 4 (the model question) and the AIDE-LLM
        advisories (ND-01-08/ND-01-09) are restored/new.

        `staged_model` (01-30 T3 parity): an optional {role: model} the caller supplies
        programmatically (harness/tests) so the model question never calls input() at
        all — a non-interactive bootup must not hang on a prompt. Interactive callers
        (the normal `tron start`) pass nothing and get asked, per role, exactly as
        01-30 behaved."""
        print(f"{BOLD}== TRON bootup =={RST}")
        eng = Engine(self.ctx)
        # 0. AIDE's own model (ADR-0003 D-J (a)): a session knob, fail-open to judge's
        # built-in default — resolved BEFORE any aide call below so the very first
        # advisory already rides the operator's choice. Never boot-fatal (unlike the
        # per-role model question, T1 below): a headless/staged caller with no "aide"
        # answer silently keeps the built-in default.
        self._ask_aide_model(eng, staged=staged_model)
        # ND-01-08 SET SCOPE (ADR-0003 D-J): AIDE — a REAL LLM (judge.call("aide"),
        # NEVER a heuristic) — advises on scope, including which block to pick, over
        # the LAST-KNOWN pipeline snapshot (this instance's own prior tick, if any
        # survives in the MANIFEST) — never a fresh trunk read of its own (the scope
        # step right after this stays the SAME single _refresh_from_trunk inside
        # eng.start() drives; frozen journey). Advisory only — never sets scope itself;
        # runtime-unavailable -> bootup proceeds unaided (D-J reconciliation (e)).
        self._aide_advise_scope(eng)
        # 1. run scoping — the session.scope three-way prompt (TRON voice; never status edits).
        print(self.renderer.render("session.scope", {}))
        self._ask_scope(eng)
        # ND-01-09 SET COUNTS (ADR-0003 D-J): AIDE advises on worker_count only
        # (unusual-but-valid / below-floor) — #architects is fixed at 1 this version,
        # no count to advise (ADR-0003 D-D/D-J, BLOCKER-2 resolved).
        self._aide_advise_counts(eng)
        # 2. worker_count.
        worker_count = None
        while worker_count is None:
            v = input("worker_count (build + review workers; the persistent spec-owner "
                      "role is extra)? ").strip()
            if v.isdigit() and int(v) > 0:
                worker_count = int(v)
            else:
                print(f"{DIM}  (a positive integer){RST}")
        # 3. ask-before-merging (T8): ON pauses the trunk-merge step for your go-ahead.
        ans = input("Inform you before each merge to trunk? [y/N] ").strip().lower()
        eng.st.live_config["ask_before_merging"] = ans in ("y", "yes")
        # 4. worker model, PER ROLE (ADR-0003 D-D — the sole restored question, 01-30
        # parity). Write-boundary-safe (T2/BL-1): the answer is written ONLY into
        # eng.st.live_config — this instance's own MANIFEST under meta/agents/tron/
        # (TRON's sealed folder) — NEVER into roles.yaml, which stays project-authored
        # and untouched. fsm._model_for_role layers it over roles.yaml's `role.model`
        # at resolution time; roles.RolesConfig.validate_models (below, via
        # eng.start()) is the one fail-closed guard if NEITHER source resolves.
        self._ask_role_models(eng, staged=staged_model)
        print()
        eng.start(worker_count)                      # 5–6: read trunk, spawn spec_owner + first pulse
        self._start_daemon()                         # the WAKE heartbeat (idempotent; skipped in dry)
        print()
        self._banner()

    # ── AIDE (ADR-0003 D-J): a real judge.call("aide") LLM lane at the bootup nodes —
    # NEVER a deterministic/heuristic stand-in. The shared `judge.call_aide` infra
    # (Project-Docs context builder + the "aide" tool) is reused verbatim here and by
    # 01-36's later nodes — no per-caller copy of the context-building or call shape.
    def _ask_aide_model(self, eng, staged=None):
        """ADR-0003 D-J reconciliation (a): AIDE's own model — an engine-builtin LLM
        lane, NOT a roles.yaml capability class (BUILD/REVIEW/TRIAGE/CLOSE stay
        sealed). Overridable here, same write-boundary-safe store as `_ask_role_models`
        (eng.st.live_config, under meta/agents/tron/ — never roles.yaml). FAIL-OPEN
        (exempt from D-D's boot-fatal law): a blank/absent answer here NEVER blocks
        boot — it silently keeps judge's built-in default."""
        default = judge.TIER.get("aide", judge.AIDE_DEFAULT_MODEL)
        if staged is not None:
            v = (staged.get("aide") or "").strip()
        else:
            v = input(f"Model for AIDE (the operator's LLM advisor) [{default}]? ").strip()
        eng.st.live_config["aide_model"] = v or default

    def _aide_advise_scope(self, eng):
        """ND-01-08 SET SCOPE (ADR-0003 D-J): AIDE advises on scope, INCLUDING which
        block to pick, via a real `judge.call_aide` — Project Docs context
        (context.md+pipeline.md+the top dispatchable block docs), never a heuristic.
        Advisory only: the operator's own scope answer right after this always wins.
        Fail-safe (D-J reconciliation (e)): AIDE unavailable -> bootup proceeds
        unaided, never a deterministic substitute."""
        idx = reader.status_index(eng.st.pipeline)
        candidates = [r for r in sorted(eng.st.pipeline, key=lambda r: (r.get("order") or 1e9))
                      if reader.dispatchable(r, idx)]
        block_files = [r["block_file"] for r in candidates[:5] if r.get("block_file")]
        ok, out, _ = judge.call_aide(
            eng.ctx, eng.paths, "scope",
            extra={"candidate_blocks": [r["id"] for r in candidates[:5]]},
            block_files=block_files, model=eng.aide_model(), elog=eng.events)
        if ok and out and out.get("advice"):
            print(f"{DIM}  AIDE: {out['advice']}{RST}")
            if out.get("recommended_block"):
                print(f"{DIM}  AIDE recommends: block {out['recommended_block']}{RST}")
        else:
            print(f"{DIM}  AIDE: unavailable — proceeding unaided; your scope choice "
                  f"below decides.{RST}")

    def _aide_advise_counts(self, eng):
        """ND-01-09 SET COUNTS (ADR-0003 D-J): AIDE advises on `worker_count` only
        (#architects is fixed at 1 this version — no count to advise, BLOCKER-2
        resolved) via a real `judge.call_aide`. Fail-safe: unavailable -> proceeds
        unaided."""
        ok, out, _ = judge.call_aide(
            eng.ctx, eng.paths, "counts", extra={"scope": eng.st.scope},
            model=eng.aide_model(), elog=eng.events)
        if ok and out and out.get("advice"):
            print(f"{DIM}  AIDE: {out['advice']}{RST}")
        else:
            print(f"{DIM}  AIDE: unavailable — proceeding unaided.{RST}")

    def _aide_resolve(self, eng, detail):
        """ND-01-14 RESOLVE (ADR-0003 D-J): reached when a resumed run's MANIFEST can't
        be reconciled — AIDE briefs the operator and offers three choices (repair /
        restart / halt) via a real `judge.call_aide`. Exposed as a directly-callable,
        testable primitive (the same shape 01-36 reuses at ND-02-10) even though this
        block's frozen journey (Hard rule) does not itself wire a live resume-conflict
        TRIGGER — that MANIFEST-reconciliation detection is future work; this is the
        advisory half ready for it to call. Fail-safe: AIDE unavailable -> the raw,
        un-briefed detail is returned instead of a heuristic brief (D-J
        reconciliation (e))."""
        ok, out, _ = judge.call_aide(
            eng.ctx, eng.paths, "resolve", extra={"detail": detail},
            model=eng.aide_model(), elog=eng.events)
        if ok and out and out.get("advice"):
            return out["advice"], out.get("choices") or ["repair", "restart", "halt"]
        return detail, ["repair", "restart", "halt"]

    def _role_label(self, role, cfg):
        tier = "architect" if (cfg.get("spec_owner") or cfg.get("persistent")) else "other"
        return f"{role} ({ROLE_MODEL_LABEL[tier]})"

    def _recommended_model(self, eng, role):
        """01-30 parity (T1/T2), restored per ADR-0003 D-D: the default OFFERED at the
        bootup model prompt for `role` — never itself the resolution path (fsm.
        _model_for_role / roles.RolesConfig.validate_models own that — T2). Prefers the
        role's OWN declared roles.yaml `model:` (today's config value, ADR-0002 D4) as
        the recommended default; falls back to a built-in per-tier suggestion (the
        persistent spec-owner role vs. everyone else) only when roles.yaml itself
        declares none for this role."""
        cfg = eng.roles.roles.get(role) or {}
        declared = eng.roles.model_for(role)
        if declared:
            return declared
        tier = "architect" if (cfg.get("spec_owner") or cfg.get("persistent")) else "other"
        return ROLE_MODEL_RECOMMENDED[tier]

    def _ask_role_models(self, eng, staged=None):
        """01-30 parity (T1/T2/T3), restored per ADR-0003 D-D: ask the worker model PER
        ROLE — every role roles.yaml declares gets its own question (ADR-0002 D4/01-33
        generalized role identity past the old hardcoded {architect, other} split; this
        restore follows suit rather than reintroducing that hardcoding). Each question
        shows a recommended default (_recommended_model) the operator confirms (Enter)
        or overrides. `staged` (T3) supplies the answers programmatically with NO
        prompt at all — a non-interactive call must never block on input(). A staged
        role with no answer (missing/blank) is left UNRESOLVED here (never silently
        given the recommended default) — RolesConfig.validate_models (via eng.start())
        is the fail-closed guard for that; this method's own job is only to WRITE
        whatever was actually decided, never to paper over an absent one.

        Write-boundary-safe (T2/BL-1): writes ONLY into eng.st.live_config (this
        instance's own MANIFEST, under meta/agents/tron/) — never roles.yaml."""
        answers = {}
        for role in sorted(eng.roles.roles.keys()):
            if staged is not None:
                answers[role] = (staged.get(role) or "").strip() or None
                continue
            cfg = eng.roles.roles.get(role) or {}
            default = self._recommended_model(eng, role)
            label = self._role_label(role, cfg)
            v = input(f"Model for {label} [{default}]? ").strip() or default
            answers[role] = v or None
        eng.st.live_config["worker_model"] = answers

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
        self._show_parked()                          # F-4/R-7: parked calls meet the returning operator
        print()
        self._banner()

    def _show_parked(self):
        # F-4/R-7 rider: park visibility never depends on the operator ASKING — every
        # attach surface leads with the calls parked on them (safe-parked flagged).
        cases = {cid: c for cid, c in sorted(self._state().pending_cases.items())
                 if c.get("decision") is None}
        for cid, c in cases.items():
            flag = "  [safe-parked]" if c.get("parked") == "safe" else ""
            print(f"  {BOLD}YOUR CALL{RST}  [{cid}] {c.get('detail','')}{flag}")

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
        ran, ended = wake.locked_tick(self.ctx, "manual")  # operator-forced tick; emits live to stdout
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
        wake.locked_tick(self.ctx, "event")   # a fresh operator message drove it; emits live to stdout
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
