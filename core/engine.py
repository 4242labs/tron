"""core.engine — `Engine`: the entrypoint that assembles EVERY `core/*.py`
module into a runnable whole (`contracts/rebuild-spec.md` T1-A bootup
A1-A9; `contracts/blueprint-contracts.md` §1's bootup-is-a-first-run-
gateway / SWITCHBOARD / persistent-pool-excluded-architect; `protocols/
bootup.md`). Turns the tick-driven fixtures every prior `core/*_rig.py`
drove directly (`core.tick.tick(some_MiniEng)`) into an actual whole
engine: `Engine(ctx).start(...)` boots a session, `Engine.tick()`/`.run()`
drive it to a clean session-end.

`Engine` is PURE WIRING — a thin class holding `ctx` plus the duck-typed
surface every `core/*.py` module already expects (see each module's own
docstring for its exact contract): `paths`, `dry`, `ctx`, `events`, `log`,
`_truth_ref`, `_to_worker`, `_release_worker`, `_spawn_worker`,
`_spawn_architect`, `_page_operator`, `_grant_ttl`. No module below this one
was edited to make this true (`core/gitobs.py` gained ONE additive delegate,
`refresh` — the SAME "known-good `engine/trunk.py` read, delegated straight
through" pattern its own docstring already documents for every other
function in it; nothing existing changed shape).

`paths` is built from `ctx.repo_paths(ctx.load_project())` — the SAME
resolution `engine/ctx.py`/`engine/fsm.py` already do — plus `worker_count`
(a `start()` param, never a knob: this stack's headless bootup shape,
learned from `tron-meta/sims/autopilot/bootstrap.py`'s `LAUNCHER_TEMPLATE`,
takes the frozen operator-journey answers as ARGS, never prompts, never
re-derives them from a config file this brick doesn't own).

## The two REAL process-touching seams

`_spawn_worker`/`_spawn_architect` are the ONE seam that starts a real OS
process — `engine/jobs.py::spawn_runner`, real in production, monkeypatched
to a no-op by `core/engine_rig.py` (never a real `claude` process in a rig,
exactly the established pattern every `core/*_rig.py`'s own `_spawn_worker`
already stands in for). Role/model resolution for that call is a plain
`engine/roles.py::RolesConfig` lookup (ADR-0002 D4's fleet-as-config,
respected as-is): an ordinary block resolves the project's default BUILD
role (`select_build_role()` — no `Role:`/`Tags:` header data flows through
`core/switchboard.py::fill`'s `(agent_id, block_id)` call shape at this
wave, so this brick resolves the block-agnostic default, same simplicity
every other wave-5+ module already keeps: "no LLM/classify in this brick");
a review pseudo-block (`review:<type>`) resolves via `select_review_role
(typ)`; the architect resolves via `RolesConfig.spec_owner` (falling back to
its first `persistent` role). `models` (an optional `{role: model}` dict
passed to `start()`) is the SAME session-override-wins-then-roles.yaml
layering `engine/fsm.py::_model_for_role` already uses — never required,
roles.yaml alone may supply every role's model.

Every OTHER duck-typed hook (`_to_worker`, `_release_worker`,
`_page_operator`, `_grant_ttl`, `log`) is REAL, non-stubbed, because each
touches only TRON's own folder (`engine/jobs.py::send`/`.release` — the
worker's own mailbox/runner-state dir under `ctx.workers_dir`; `ctx.
home_log`; `ctx.grants_dir`, via the knobs read) — never a project write,
never a second process.

## Bootup (`start`) — rebuild-spec.md A1-A9, mapped onto this stack

  A1/A2  `core.gitobs.refresh` — best-effort fetch (remote mode) or a
         genuine no-op read (local mode); a refresh FAILURE halts loud
         (`BootupError`, raised, never a silent death) before anything else
         runs — no manifest exists yet at this point, so there is nothing
         to leave half-written either.
  A3     `_resolve_scope` — validate the requested scope's block ids exist
         on the trunk-pinned pipeline view and every dependency resolves to
         either `done` or a status that can still reach it; a nonexistent
         id or a permanently-unsatisfiable dep is a fail-loud bootup error
         (never a silent guess). `scope="all"`/`None` (the default) is every
         roadmap row currently on trunk; an explicit, empty scope (`[]`) is
         legitimate — a fresh run with nothing yet to do.
  A4     `worker_count` — a `start()` param (floor 1, `core/switchboard.py`'s
         own floor), never re-derived from a knob this brick doesn't own.
  A5     the manifest gains `scope`/`counts`/a zeroed `cadence` seed (read
         from `knobs.yaml`'s `cadence:` map, when the project declares one —
         `core/reviewers.py::bump_cadence` would lazily `setdefault` the
         SAME zeros on the first landed block regardless; seeding it here is
         provenance, not a new invariant) — persisted via `core.state.save`,
         the ONE writer of `ctx.state` in this whole stack.
  A6/A7  a session already live (`manifest["session"]["started_at"]` on
         file) refuses to re-boot (`BootupError`, mirrors `bootstrap.py`'s
         own launcher check: "a session is already live — stop it first").
         Reconciling an INTERRUPTED prior run's scope is out of scope for
         this brick (no rig here ever seeds a leftover live manifest).
  A8     the persistent, pool-excluded architect is spawned HERE, at boot
         (`_spawn_architect`, `manifest["architect"]["spawned"] = True`) —
         never left to `core/architect.py::advance`'s own LAZY first-job
         trigger (that lazy path still exists, harmlessly idempotent, for a
         caller that drives `core.tick.tick` directly without ever calling
         `Engine.start`, exactly as `core/architect_rig.py`'s own `eng`
         stand-in does today). Then the FIRST dispatch: a `core.snapshot.
         build` + `core.switchboard.fill` pass (SWITCHBOARD's SPAWN half) —
         no other module runs (no `route`/`gate.advance`/`sentry.pace`/
         `liveness.sweep`/`architect.advance`/`session.check` — those are
         the TICK LOOP's job, which `start()` hands off to, never performs
         itself, matching "BOOTUP spawns no agents beyond the architect").
  A9     Telegram opt-in — out of scope (no TG plumbing exists anywhere in
         this `core/` stack yet); not implemented.

## The tick loop

`Engine.tick()` is a one-line delegate to `core.tick.tick(self)` — already
the whole observe -> route -> decide -> act -> architect-enqueue -> sentry
-> liveness -> fill -> architect-advance -> persist -> session-end pass
(see that module's own docstring). `Engine.run(max_ticks)` loops `tick()`
until a `session_end` marker appears (or the tick already-ended no-op
returns the SAME marker back) or the cap is hit — a plain convenience for a
headless SIM/the rig, never itself durable state.
"""
import json
import os
import sys
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import util               # noqa: E402 — engine/util.py, respected contract (now_iso only)
import jobs                # noqa: E402 — engine/jobs.py, the real process-spawn + mailbox seam
import roles as roles_mod   # noqa: E402 — engine/roles.py, roles.yaml (ADR-0002 D4 fleet-as-config)

# `state` bound FIRST, before `gitobs`'s own import transitively puts
# `engine/` onto `sys.path` — see `core/snapshot.py`/`core/tick.py`'s
# matching note; this module re-imports the same cached names for the same
# reason (both are already on `sys.path` above by the time this runs, but
# the ORDER these bare names first resolve in this PROCESS is what matters,
# and `core/tick.py`/`core/snapshot.py` are imported by the module below).
import state          # noqa: E402 — core/state.py
import gitobs          # noqa: E402 — core/gitobs.py, the ONE git-observation seam
import pipeline         # noqa: E402 — core/pipeline.py, the trunk-pinned view + dispatch read
import snapshot          # noqa: E402 — core/snapshot.py, the per-tick observe pass
import switchboard         # noqa: E402 — core/switchboard.py, SWITCHBOARD's SPAWN half
import architect            # noqa: E402 — core/architect.py, the persistent pool-excluded architect
import casestate              # noqa: E402 — core/casestate.py, wave 8's parked-case FSM (dispatch filter)
import tick as core_tick       # noqa: E402 — core/tick.py, the whole per-tick pass
import knobs as knobs_mod       # noqa: E402 — core/knobs.py, the ONE knobs.yaml seam (wave 16)


class BootupError(RuntimeError):
    """Fail-loud bootup gateway error (rebuild-spec.md A2/A3/A6-A7) — never
    a silent 'end'; propagated uncaught, exactly like every other fail-loud
    seam already established in this stack (`core.gitobs.read_pipeline_
    view`, `core.session.check`)."""


class _Events:
    """The default real events sink `Engine.__init__` hands to every module
    that calls `eng.events.event(...)` (`core.landing`'s ONE call site,
    `grant_minted`) when the caller supplies none of its own — an in-memory
    append-only list, same `{"type", "payload"}` shape every `core/*_rig.py`
    fixture's own `_Events` already uses. A caller that wants a durable
    forensic sink (`engine/eventlog.py::EventLog`, unmodified) passes
    `events=` to `Engine(...)` instead — this module never forces a choice."""

    def __init__(self):
        self.log = []

    def event(self, type_, **payload):
        self.log.append({"type": type_, "payload": payload})


class Engine:
    """The whole engine: `ctx` + the duck-typed surface every `core/*.py`
    module already expects. See module docstring for the full contract and
    the bootup (`start`)/tick-loop (`tick`/`run`) shape."""

    def __init__(self, ctx, dry=False, events=None):
        self.ctx = ctx
        self.dry = bool(dry)
        self.events = events if events is not None else _Events()
        self._mailbox_seq = {}   # wid -> next engine->worker mailbox seq (engine/jobs.py::send)
        self._models = {}        # role -> model, the session override start(models=...) layers
        self._roles = None       # engine/roles.py::RolesConfig, resolved lazily on first spawn
        project = ctx.load_project()
        self.paths = ctx.repo_paths(project)
        self.paths["worker_count"] = 1   # floor 1 (core/switchboard.py's own floor) until start()
        jobs.configure(ctx.workers_dir)   # real worker-store root (idempotent to call twice)

    # ── knobs (plain YAML file IO — no git; core/knobs.py owns the shape) ──
    def _knobs(self):
        """`core/knobs.py::Knobs`, read fresh off `self.ctx` — the ONE
        knobs.yaml seam (wave 16). Replaces this method's own pre-wave-16
        flat top-level read (`ctx.load_knobs() or {}`), which silently
        missed every knob the schema nests under `knobs:` (`grant_ttl`
        happened to coincide with its own hardcoded `.get(key, 60)`
        fallback; `cadence` happens to already live at the top level — see
        `core/knobs.py`'s own module docstring for the full story)."""
        return knobs_mod.load(self.ctx)

    # ── duck-typed surface: logging + trunk identity + grants ──
    def log(self, channel, msg):
        """Real, non-stubbed: one JSON line appended to `ctx.home_log`
        (`engine/ctx.py`'s own "console replay-on-reconnect copy" file) —
        never `print()`/stdout, so a headless run leaves the SAME durable
        trail a live console session would. TRON's own folder only."""
        if self.dry:
            return
        rec = {"at": util.now_iso(), "channel": channel, "text": msg}
        d = os.path.dirname(os.path.abspath(self.ctx.home_log)) or "."
        os.makedirs(d, exist_ok=True)
        with open(self.ctx.home_log, "a") as fh:
            fh.write(json.dumps(rec) + "\n")

    def _truth_ref(self):
        """The mode's truth ref (ADR-0002 D1, learned by reading `engine/
        fsm.py::_truth_ref` for shape only): `origin/<main>` post-fetch in
        remote mode, `<main>` read in place in local mode (no remote
        declared, or declared `"none"` — the root checkout IS the
        authority)."""
        main = self.paths.get("main_branch", "main")
        remote = self.paths.get("remote")
        local = not remote or remote == "none"
        return main if local else f"origin/{main}"

    def _grant_ttl(self):
        return self._knobs().grant_ttl

    def _worker_working(self, worker_id):
        """OPTIONAL liveness hook (`core/liveness.py::_worker_active`): True
        iff this worker's real `worker_runner.py` is provably MID-TURN — its
        runner record is alive (`engine/jobs.py::is_alive`, a live pid in a
        non-terminal state) AND its declared `state` is `"working"` (an agent
        actively executing a turn, per `engine/worker_runner.py::_write_state`
        — NOT `idle`/`online`/`error`). A build turn posts nothing to the
        engine inbox until it finishes (a single `claude -p` turn is atomic
        and can run for many minutes), so WITHOUT this the silence ladder
        would falsely stall a legitimately-working worker; WITH it, an
        actively-working runner counts as "seen" and only a truly silent-AND-
        not-working worker (dead/hung→timeout→error/idle-at-gate) accrues
        silence. Real, non-stubbed (reads TRON's own runner.json only, no
        git, no second process); under `self.dry` there is no real runner, so
        it reports not-working (the report-only ladder governs, unchanged)."""
        if self.dry:
            return False
        rec = jobs.find(worker_id)
        if rec is None or not jobs.is_alive(worker_id):
            return False
        return rec.get("state") == "working"

    # ── duck-typed surface: engine -> worker mailbox + release (real, TRON's own folder) ──
    def _to_worker(self, worker_id, text, kind):
        """Real, non-stubbed: one line appended to the worker's OWN mailbox
        (`engine/jobs.py::send` — the established engine->worker channel;
        `ctx.workers_dir/<worker_id>/tron-inbox.jsonl`, TRON's own folder,
        never a project write). `seq` is this Engine's own per-worker
        monotonic counter (mirrors `engine/fsm.py::emit`'s own counter)."""
        if self.dry:
            return
        seq = self._mailbox_seq.get(worker_id, 0) + 1
        self._mailbox_seq[worker_id] = seq
        jobs.send(self.ctx.worker_dir(worker_id), seq, kind, text)

    def _release_worker(self, worker_id, reason="released"):
        """Real, non-stubbed: writes the `.stop` sentinel + SIGTERMs the
        runner's process group (`engine/jobs.py::release`, idempotent, safe
        even against a worker dir a stubbed `_spawn_worker` never actually
        created — `jobs.release`'s own `OSError`-swallowing contract)."""
        if self.dry:
            return
        jobs.release(worker_id)
        self.log("flow", f"engine: released {worker_id} ({reason})")

    # ── duck-typed surface: operator paging (real — a durable, structured
    #     trace + THE FLOOR, wave 17/GAP-A) ──
    def _page_operator(self, case_id, block, detail, worker_id=None,
                       manifest=None, page_kind="operator_page"):
        """Real, non-stubbed: RECORDS the page durably —
        `manifest["operator_pages"][page_id]` (when a `manifest` is
        supplied; every real call site in this stack — `core/casestate.py
        ::open_case`/`reping`, wave 17 — already holds the live manifest in
        scope and passes one; an omitted manifest, never a real call site,
        still gets the event+log trace below, the SAME defensive-but-never-
        silent shape every other duck-typed hook already has) — as a
        structured event (`operator_page`, the SAME type `engine/
        eventlog.py`'s own closed vocabulary already names for this hand-
        off) plus a home-log line, THEN reads a delivery RECEIPT off the
        injected `eng._deliver_page` hook (stubbed like `_to_worker` — no
        real transport wired this wave; `core/opfloor_rig.py` is what
        actually exercises delivered vs failed on a real, deterministic
        clock). An ABSENT hook (production, this wave — a real transport is
        a LATER wave's concern) or a return value that isn't literally
        `"delivered"`/`"failed"` reads as `None` (absent) — the SAME "not
        yet confirmed, keep re-pinging" floor outcome a `"failed"` receipt
        gets; there is NO default-delivered assumption anywhere in this
        stack (GAP-A's own bug, made structurally impossible). Returns the
        receipt so the caller (`core/casestate.py`) can drive THE FLOOR."""
        page_id = None
        pages = None
        if manifest is not None:
            pages = manifest.setdefault("operator_pages", {})
            page_id = f"{case_id}-p{len(pages) + 1}"

        deliver = getattr(self, "_deliver_page", None)
        receipt = None
        if callable(deliver):
            r = deliver(case_id, block, detail, worker_id=worker_id, page_id=page_id)
            receipt = r if r in ("delivered", "failed") else None

        if pages is not None:
            pages[page_id] = {"page_id": page_id, "case_id": case_id, "block": block,
                              "detail": detail, "worker_id": worker_id, "kind": page_kind,
                              "receipt": receipt, "at": util.now_iso()}

        self.events.event("operator_page", case=case_id, block=block, detail=detail,
                          worker_id=worker_id, kind=page_kind, receipt=receipt, page_id=page_id)
        self.log("operator", f"PAGE[{page_kind}] case={case_id} block={block!r} "
                              f"worker={worker_id!r} receipt={receipt!r}: {detail}")
        return receipt

    # ── role/model resolution (engine/roles.py, ADR-0002 D4 respected as-is) ──
    def _roles_config(self):
        if self._roles is None:
            cadence_types = list(self._knobs().cadence.keys())
            self._roles = roles_mod.RolesConfig.load(
                self.paths["roles_path"], self.paths["root"], cadence_types=cadence_types)
        return self._roles

    def _model_for_role(self, role):
        """The session override (`start(models=...)`) wins for the session;
        else roles.yaml's own `model:` (mirrors `engine/fsm.py::
        _model_for_role`'s identical layering, minus the MANIFEST-persisted
        half — this brick's `models` is a plain constructor-time arg, never
        written back to the manifest itself)."""
        m = self._models.get(role)
        if isinstance(m, str) and m.strip():
            return m.strip()
        return self._roles_config().model_for(role)

    def _resolve_role_for_block(self, block):
        """No `Role:`/`Tags:` header data flows through `core/switchboard.py
        ::fill`'s `(agent_id, block_id)` spawn call at this wave (no LLM/
        classify in this brick, same simplicity every wave-5+ module already
        keeps) — an ordinary block resolves the project's default BUILD
        role; a review pseudo-block (`review:<type>`) resolves via its own
        selector."""
        if isinstance(block, str) and block.startswith("review:"):
            typ = block.split(":", 1)[1]
            return self._roles_config().select_review_role(typ)
        return self._roles_config().select_build_role()

    # ── duck-typed surface: the two real process-spawn seams ──
    def _real_spawn(self, wid, role, block):
        if not role:
            raise BootupError(f"engine: no resolvable role for spawn {wid!r} "
                              f"(block={block!r}) — roles.yaml gap, refusing to spawn blind")
        jobs.retire_stale_dir(self.ctx.worker_dir(wid))
        scratch = self.ctx.worker_scratch_dir(wid)
        os.makedirs(scratch, exist_ok=True)
        os.makedirs(self.ctx.worker_dir(wid), exist_ok=True)
        session_id = str(uuid.uuid4())
        jobs.spawn_runner(wid, self.ctx.worker_dir(wid), session_id, cwd=scratch,
                          model=self._model_for_role(role))
        self.log("flow", f"engine: spawned {wid} (role={role!r}, block={block!r})")

    def _spawn_worker(self, agent_id, block):
        """The STUBBED-in-a-rig process-spawn seam (`engine/jobs.py::
        spawn_runner`, monkeypatched to a no-op by `core/engine_rig.py` —
        never a real `claude` process in a rig). `core/switchboard.py::fill`
        has already recorded this worker's manifest entry BEFORE calling
        here (adversary §11.3's "mint + record before any process")."""
        if self.dry:
            return
        role = self._resolve_role_for_block(block)
        self._real_spawn(agent_id, role, block)

    def _spawn_architect(self):
        """Called at most once — either by `start()` (A8, this brick's own
        boot-time spawn) or, lazily, by `core/architect.py::advance` the
        first tick it actually pops a queued job (a caller that drives
        `core.tick.tick` without ever going through `Engine.start`)."""
        if self.dry:
            return
        rc = self._roles_config()
        role = rc.spec_owner or (rc.persistent_roles() or [None])[0]
        self._real_spawn(architect.ARCHITECT_WID, role, None)

    # ── A3: scope resolution ──
    def _resolve_scope(self, scope, view):
        """Validate the requested scope against the trunk-pinned view (A3):
        `"all"`/`None` (default) is every roadmap row currently on trunk —
        no restriction; an explicit iterable of block ids is validated (each
        must exist on trunk; each dependency must be `done` or a status that
        can still reach it) and returned as-is. An empty explicit scope
        (`[]`/`()`) is legitimate — a fresh run with nothing yet to do, never
        an error. A nonexistent id or a permanently-unsatisfiable dependency
        (absent from the pipeline entirely, or stuck at a status that will
        never reach `done` — `deferred`/`debt`/`cut`/`folded`/`split`) is a
        fail-loud bootup error, never a silent guess."""
        ids_on_trunk = {row["id"] for row in view}
        if scope in (None, "all"):
            return sorted(ids_on_trunk)

        requested = list(scope)
        unknown = [b for b in requested if b not in ids_on_trunk]
        if unknown:
            raise BootupError(
                f"engine: bootup A3 — scope names unknown block id(s) {unknown} "
                f"(not on the trunk-pinned pipeline view) — never a silent guess")

        status_idx = {row["id"]: row.get("status") for row in view}
        rows_by_id = {row["id"]: row for row in view}
        for bid in requested:
            for dep in (rows_by_id[bid].get("depends_on") or []):
                if dep not in status_idx:
                    raise BootupError(
                        f"engine: bootup A3 — {bid!r} depends on {dep!r}, absent "
                        f"from the pipeline entirely (a typo?) — deps unsatisfiable, "
                        f"refusing to boot into this scope")
                dep_status = status_idx[dep]
                if dep_status != "done" and dep_status not in ("to-do", "in-progress"):
                    raise BootupError(
                        f"engine: bootup A3 — {bid!r} depends on {dep!r} whose status "
                        f"{dep_status!r} can never reach done — deps unsatisfiable, "
                        f"refusing to boot into this scope")
        return requested

    # ── bootup ──
    def start(self, scope="all", worker_count=1, models=None):
        """Headless bootup (rebuild-spec.md A1-A9 — see module docstring for
        the full mapping): resolve scope, write the manifest, spawn the
        persistent pool-excluded architect, perform the first dispatch
        (SWITCHBOARD's SPAWN half), then hand off to the tick loop. Params
        are the frozen operator-journey's ALREADY-ANSWERED values (exactly
        `tron-meta/sims/autopilot/bootstrap.py`'s `LAUNCHER_TEMPLATE` shape)
        — never a prompt, never a re-derivation of a question this brick
        doesn't own. Returns the list of freshly spawned agent-ids (the
        SAME non-durable convenience `core.switchboard.fill` itself
        returns)."""
        manifest = state.load(self.ctx)
        if (manifest.get("session") or {}).get("started_at"):
            raise BootupError(
                "engine: bootup A6/A7 — a session is already live for this instance "
                "(manifest['session']['started_at'] on file) — stop it first; bootup "
                "is not re-entrant onto a live session in this brick")

        self._models = dict(models or {})
        self.paths["worker_count"] = max(1, int(worker_count or 1))

        # A1/A2: refresh trunk (remote mode) or a genuine no-op local read;
        # a refresh FAILURE halts loud, before anything durable is written.
        ok, detail = gitobs.refresh(self.paths["root"], self.paths.get("main_branch", "main"),
                                    self.dry, self.paths.get("remote"))
        if not ok:
            raise BootupError(f"engine: bootup A2 — stale trunk, refresh failed: {detail}")

        # A3: resolve + validate scope off the SAME trunk-pinned pipeline
        # read `core/tick.py`'s own dispatch/session-check machinery uses.
        view, trunk_sha = pipeline.read_view(self)
        scope_ids = self._resolve_scope(scope, view)

        # A4/A5: write the manifest — scope + counts + a zeroed cadence seed.
        cadence_cfg = self._knobs().cadence
        manifest["scope"] = {"requested": scope, "ids": scope_ids}
        manifest["counts"] = {"worker_count": self.paths["worker_count"], "architect_count": 1}
        cadence = manifest.setdefault("cadence", {})
        for typ in cadence_cfg:
            cadence.setdefault(typ, 0)

        # A8 (first half): spawn the persistent, pool-excluded architect —
        # unconditionally, at boot, never left to core/architect.py::advance's
        # own lazy first-job trigger (which stays intact for a caller that
        # drives core.tick.tick without ever going through Engine.start).
        arch = manifest.setdefault("architect", architect.new_state())
        if not arch.get("spawned"):
            self._spawn_architect()
            arch["spawned"] = True
            arch["status"] = "idle"

        manifest["session"] = {"started_at": util.now_iso(), "trunk_sha": trunk_sha}
        state.save(self.ctx, manifest)

        # A8 (second half): the first dispatch — SWITCHBOARD's SPAWN half
        # only (an observe pass + core.switchboard.fill); no route/act/
        # architect-advance/sentry/liveness/session-check here — those are
        # the tick loop's job, which this hands off to, never performs
        # itself ("BOOTUP spawns no agents beyond the architect").
        snap = snapshot.build(self)
        excluded = casestate.dispatch_excluded_blocks(snap.manifest) | architect.gated_blocks(snap.manifest)
        dispatch_view = [row for row in view if row.get("id") not in excluded] if excluded else view
        spawned = switchboard.fill(self, snap, view=dispatch_view)
        state.save(self.ctx, snap.manifest)
        snapshot.release(snap)

        self.log("flow", f"engine: bootup complete — scope={scope_ids!r} "
                         f"worker_count={self.paths['worker_count']} first dispatch={spawned}")
        return spawned

    # ── the tick loop ──
    def tick(self):
        """One bounded tick — a one-line delegate to `core.tick.tick(self)`
        (already the whole observe -> route -> decide -> act -> architect-
        enqueue -> sentry -> liveness -> fill -> architect-advance ->
        persist -> session-end pass; see that module's own docstring)."""
        return core_tick.tick(self)

    def run(self, max_ticks=1):
        """Loop `tick()` until a `session_end` marker appears (freshly, or
        the idempotent-terminal no-op re-tick handing the SAME marker back)
        or `max_ticks` is reached — a plain, non-durable convenience for a
        headless SIM/rig; the manifest (via `core.state`) stays the only
        durable record of what happened, exactly like `core.tick.tick`'s own
        return value already is."""
        results = []
        for _ in range(max(0, int(max_ticks))):
            result = self.tick()
            results.append(result)
            if result.get("session_end") is not None:
                break
        return results
