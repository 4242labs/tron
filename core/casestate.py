"""core.casestate — the parked-case FSM: raise-and-defer + operator Settle
(contracts/blueprint-contracts.md §1 "wall → operator; operator.decision
resumes/amends/abandons; parked cases keyed by case id, cleared within ≤1
tick"; rebuild-spec.md B7/B8/F6 + T5's `worker.wall`/`operator.decision` tag
map). This is what turns a sentry cap escalation (wave 7, `core/sentry.py`)
or a worker's own `worker.wall` report into something the OPERATOR resolves
— never a dead-end, never a silent hang.

Shape learned by READING `engine/fsm.py`'s `_open_case`/`_drive_cases`/
`_h_apply_decision`/`_resolve_case`/`_close_case` (never copied — re-
expressed fresh for this stack's plain-manifest shape, none of that
module's role/PR/architect-queue/violation-repair machinery, which stay out
of scope here):

  **Open a case** (`open_case`, raise-and-defer) — two callers: `core/
  router.py`'s new `worker.wall` handler, and `core/sentry.py`'s cap-
  escalation path (`_escalate`, wave 7). Mints a correlation `case_id`
  (deterministic — `block`/`source` + a manifest-persisted counter, a
  "safe token", never a raw f-string of untrusted content), parks it in
  `manifest["cases"]` keyed by that id (`block`, `source`, `kind`, `detail`,
  `worker_id`, `decision=None`, `opened_at`), moves the block's gate to
  BLOCKED (see "the blocked mechanism" below — frees its slot the same
  call), pages the operator (`eng._page_operator` — a STUBBED hook, no real
  transport, exactly like `eng._to_worker`/`eng._release_worker` already
  are for `core/gate.py`), and returns. The TICK CONTINUES — this never
  raises for a well-formed wall/escalation, never blocks the caller.
  Idempotent: a SECOND `open_case` call naming a block that already has an
  OPEN case (decision still `None`) returns the EXISTING case_id rather
  than parking a second one — mirrors `engine/fsm.py::_h_escalate`'s own
  "already escalated — idempotent" guard.

  **The blocked mechanism** — this module never edits `core/gate.py` or
  `core/pipeline.py` (hard rule), so "move the block to blocked, FREE its
  slot" is built entirely out of vocabulary those TWO modules already
  understand: `core/pipeline.py::in_flight_blocks` excludes any block whose
  gate stage is in `("closed", "escalated")` — so parking a case sets the
  block's `gate_state["stage"] = gate.STAGE_ESCALATED` (the SAME terminal
  vocabulary `core/gate.py::_escalate` and `core/sentry.py::_escalate`
  already write; a `parked_case` field on the SAME `gate_state` dict is what
  tells a case-park apart from a genuine gate-driven or sentry-cap
  escalation, both of which stay exactly as they already are) — which is
  what frees the slot. What keeps a STILL-PARKED block from being
  immediately re-picked by `core/switchboard.py::fill` (its `to-do` doc
  status on trunk is untouched by a wall — TRON never writes project git
  outside `land.sh`) is `dispatch_excluded_blocks` below: `core/tick.py`
  reads it and hands `core/switchboard.py::fill` a FILTERED view (this
  module's own data, never a `core/pipeline.py`/`core/switchboard.py` edit)
  that drops any block with an open case or an abandoned flag — `core/
  session.py::check` still gets the REAL, unfiltered view (an open case's
  block must still read as "pending", never silently vanish from scope).

  **Settle** (`settle`, the operator's reply) — resolves the case named by
  `case_id` (an unknown or already-cleared id is a LOGGED NO-OP, never a
  crash, never a guess at "the" case by block) and, if still open, applies
  exactly one of three verbs:
    `resume` — clear the case, drop the block's terminal gate + any stale
      worker record naming it (`_drop_gate_and_worker`) so `core/
      pipeline.py::dispatchable` genuinely sees it as `to-do`+not-in-flight
      again next `core/switchboard.py::fill` pass — a FRESH SPAWN drives the
      block through the WHOLE ladder again from `gate.local` (never a half-
      resurrected stale gate_state; "re-drivable: fresh gate/re-dispatch",
      the design's own words).
    `amend` — the SAME drop-and-re-drive as `resume`, plus a best-effort
      relay of the operator's note to the walled worker (`eng._to_worker`,
      `operator.amend` kind) before the drop — the worker's OWN slot is
      already gone by the time this fires (freed at open-case time), so
      this is a courtesy notice, never a live conversation.
    `abandon` — clear the case, drop the block's gate/worker (same
      mechanism) AND flag the block into `manifest["abandoned_blocks"]`
      (durable, never re-dispatched by `dispatch_excluded_blocks` again,
      ever) — `core/session.py::check` reads this flag to treat an
      abandoned block as OUT of the "must reach done" scope, never a
      `RuntimeError`-raising gap.
  A case is CLEARED (popped out of `manifest["cases"]`) the same call it
  settles — "cleared within ≤1 tick" (the design's own words) is therefore
  actually "within the SAME tick `core/router.py` drains the reply", the
  tightest bound the design allows. A malformed reply (an unknown verb) or a
  DUPLICATE reply (the case_id no longer resolves — already cleared by an
  earlier settle) is LOGGED and returns `False` — never crashes, never
  clears or mutates any OTHER live case.

Duck-typed `eng` contract — everything `core/gate.py`/`core/sentry.py`
already need PLUS: `eng._page_operator(case_id, block, detail,
worker_id=None, manifest=None, page_kind="operator_page")` — no real
transport, exactly the same shape `eng._to_worker`/`eng._release_worker`
already are; `core/engine.py`'s real implementation returns the delivery
RECEIPT (`"delivered" | "failed" | None`), which is what `reping` (below,
wave 17/GAP-A) drives THE FLOOR off of.

Wave 17 (GAP-A, the #2 historical failure, 13x `operator-page-failed::
page-receipt-permanent-fail`): `open_case` (above) mints the case and sends
the FIRST page; `reping` (below), called once per `core/sentry.py::pace()`
call, re-pages every still-OPEN case forever on a bounded backoff until
EITHER a `delivered` receipt is on file OR the operator answers — there is
NO code path anywhere in this module that closes, drops, or permanently-
fails an unanswered case. See `reping`'s own docstring for the full ladder.

No git/subprocess of any kind in this module — a plain manifest mutation
only (the SAME "gates is a direct alias onto the manifest" idiom every
other `core/*.py` module already uses); `core.gate`'s stage vocabulary is
imported for its two terminal-stage constants only, never its `advance`
machinery.

Wave 18 (GAP-E, architect-first routing for ALL wall kinds — the operator's
own binding decision this engine used to violate): `open_case` (above) no
longer pages the operator itself. Every case it mints is `owner="architect"`
and immediately handed to `core/architect.py::enqueue_triage` (a NEW `triage`
job kind, PMT-TRIAGE) — the block is still parked/slot-freed exactly as
before, but nothing reaches the operator until the architect's own triage
verdict says so. Two new exports close the loop:

  `architect_resolve(eng, manifest, case_id, verdict, note=None)` — called
  ONLY by `core/architect.py::_advance_triage` once a scripted (L1)/real (L3)
  architect verdict is observed for a case `open_case` minted. `scope_forward`
  /`answer` resolve the case ENTIRELY WITHOUT the operator (same drop-and-
  redrive `settle`'s own `resume`/`amend` verbs already use) — the wall never
  reaches the operator at all. `operator` flips `case["owner"]` to
  `"operator"` and fires THE FIRST page (the SAME `eng._page_operator` call +
  paging bookkeeping `open_case` used to do directly, pre-wave-18) — the case
  STAYS open, now genuinely the real `settle()` (below)'s to resolve; GAP-A's
  `reping` floor (below) picks it up unchanged the instant its owner flips.

  `open_operator_case(eng, manifest, block, source, detail, worker_id=None,
  kind=None)` — the ONE legitimate case that is `owner="operator"` from
  birth: the architect's OWN `operator` verdict for a triage job that never
  had an existing casestate case behind it (`core/classify.py`'s unclassified
  path — free text with no block/gate to park). This is not a second bypass
  of architect-first routing — the architect has ALREADY triaged it; a
  worker.wall/sentry.cap/liveness-stall escalation never reaches here
  directly, only ever through `open_case` -> `enqueue_triage` ->
  `architect_resolve`.

`reping` (THE FLOOR, wave 17/GAP-A) and `settle` (the operator's own reply)
both now respect ownership: `reping` skips any case still `owner="architect"`
(never pings before the architect has triaged it — GAP-E's whole point);
`settle` rejects (logs, no-op, never a crash) a reply naming a case still
`owner="architect"` — the operator can never bypass the architect's own
triage, structurally.
"""
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gate   # noqa: E402 — core/gate.py, STAGE_ESCALATED/STAGE_CLOSED terminal vocabulary (read-only)
import pipeline   # noqa: E402 — core/pipeline.py, ADR-0008 stale_landing_wall (read-only; pipeline imports only gitobs — no cycle)

VERBS = ("resume", "amend", "abandon")

# ── THE FLOOR (GAP-A, wave 17) — page re-ping ladder, `reping` below.
#     Mirrors `core/sentry.py`'s `GATE_NUDGE_AFTER`/`GATE_IDLE_CAP` shape,
#     off the SAME shared clock, but the cap here NEVER turns a CASE
#     terminal the way a sentry cap turns a GATE terminal — it only ever
#     escalates the paging CHANNEL (a louder `page_kind` + a forensic,
#     WARNING-and-retry `manifest["escalations"]` record); the case itself
#     stays open, forever, exactly like before the cap. ──
PAGE_REPING_AFTER = 1             # pace units an un-delivered page holds before a forced re-ping (bounded — at most once per pace() call, never a busy-loop)
PAGE_CHANNEL_ESCALATE_AFTER = 3   # consecutive failed/absent deliveries -> escalate the CHANNEL — never terminal, never stops the ladder


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _safe_token(s):
    """A deterministic, filesystem/log-safe token for a case-id — never a
    raw f-string of untrusted content. Content-BOUND landing case-ids stay
    `core/landing.py`'s own job; a case correlation id here is allowed to be
    the simpler `block+source+counter` shape the design explicitly permits."""
    s = str(s or "case")
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in s)


def next_case_id(manifest, block, source):
    """Mint a deterministic, monotonically-numbered case id — a manifest-
    persisted counter (`manifest["case_seq"]`, incremented exactly once per
    mint), never `uuid`/`random` (adversary-safe: reproducible across a
    replay of the SAME manifest history)."""
    seq = int(manifest.get("case_seq", 0)) + 1
    manifest["case_seq"] = seq
    token = _safe_token(block or source)
    return f"case-{token}-{seq}"


def parked_blocks(manifest):
    """Blocks currently holding an OPEN (unsettled, `decision is None`)
    case — the live "raise-and-defer" set. Computed straight off `manifest
    ["cases"]`, never a separately-maintained list that could drift out of
    sync with it."""
    cases = manifest.get("cases") or {}
    return {c["block"] for c in cases.values() if c.get("block") and c.get("decision") is None}


def dispatch_excluded_blocks(manifest):
    """Blocks `core/tick.py` must hide from `core/switchboard.py::fill`'s
    dispatch view THIS tick: every still-parked block (an open case; its
    doc status on trunk is untouched by a wall, so it would otherwise read
    as genuinely `to-do`+not-in-flight the instant its gate frees the slot)
    PLUS every permanently abandoned block (never re-dispatched, ever,
    regardless of case state). `core/session.py::check` does NOT use this —
    it reads the REAL, unfiltered view; only dispatch eligibility is
    filtered here."""
    return parked_blocks(manifest) | set(manifest.get("abandoned_blocks") or [])


def _drop_gate_and_worker(manifest, block):
    """The shared 'un-block, re-drivable' mechanism `resume`/`amend`/
    `abandon` all use: drop the block's (now-terminal) gate AND any worker
    record still naming it, so `core/pipeline.py::in_flight_blocks` and
    `core/switchboard.py`'s deterministic agent-id guard both see a clean
    slate — the NEXT `core/switchboard.py::fill` pass (this same tick, if
    still under `worker_count`, per `core/tick.py`'s own act-before-fill
    ordering) mints a genuinely FRESH dispatch, never a half-resurrected
    stale `gate_state`."""
    if not block:
        return
    gates = manifest.get("gates")
    if gates is not None:
        gates.pop(block, None)
    workers = manifest.get("workers") or {}
    for wid in [w for w, rec in workers.items() if rec.get("block") == block]:
        workers.pop(wid, None)


def open_case(eng, manifest, block, source, detail, worker_id=None, kind=None):
    """Raise-and-defer: park a correlation case, move the block's gate to
    BLOCKED (see module docstring — reuses `gate.STAGE_ESCALATED`, the ONE
    terminal vocabulary `core/pipeline.py` already excludes from in-flight),
    free its slot (`eng._release_worker`), and hand it to the architect FIRST
    (`core/architect.py::enqueue_triage`, wave 18/GAP-E) — NEVER an immediate
    operator page. Returns the minted `case_id`. The tick CONTINUES — this
    never raises for a well-formed call.

    Idempotent: a block that already has an OPEN case returns that SAME
    case_id — never a second parked case for one still-open situation."""
    import architect   # lazy — casestate<->architect mutually import (see module docstring)

    # R1a (ADR-0005) defense-in-depth: the architect can never be the SOURCE of a case.
    # The router/classify call-sites already short-circuit an architect sender AHEAD of
    # here, but guarding open_case itself makes an architect-sourced case structurally
    # unrepresentable: a future caller passing the architect's id would otherwise mint an
    # orphan case (enqueue_triage's own R1a backstop then refuses to attach a triage to
    # it), which R3's terminal gate would correctly-but-permanently wedge session-end on.
    if worker_id == architect.ARCHITECT_WID:
        eng.log("flow", f"casestate: open_case refused — source is the architect itself "
                        f"(R1a self-source guard); no case minted (block={block!r}, "
                        f"source={source!r})")
        return None

    cases = manifest.setdefault("cases", {})

    if block:
        existing = next((cid for cid, c in cases.items()
                         if c.get("block") == block and c.get("decision") is None), None)
        if existing:
            eng.log("flow", f"casestate: block {block!r} already has an open case "
                            f"{existing!r} — open_case is idempotent, no second case parked "
                            f"(source={source!r} detail={detail!r} ignored)")
            return existing

    case_id = next_case_id(manifest, block, source)
    gates = manifest.get("gates") or {}
    gate_state = gates.get(block) if block else None
    prev_stage = gate_state.get("stage") if gate_state else None

    cases[case_id] = {
        "case_id": case_id,
        "block": block,
        "source": source,          # "worker.wall" | "sentry.cap" | ...
        "kind": kind or source,
        "worker_id": worker_id,
        "detail": detail,
        "decision": None,
        "opened_at": _now_iso(),
        "prev_stage": prev_stage,
        "owner": "architect",      # wave 18 (GAP-E): architect-first, always
    }

    if gate_state is not None and gate_state.get("stage") not in (gate.STAGE_CLOSED, gate.STAGE_ESCALATED):
        gate_state["stage"] = gate.STAGE_ESCALATED
        gate_state["escalation"] = detail
        gate_state["parked_case"] = case_id
    elif gate_state is not None:
        # Already terminal (e.g. `core/sentry.py`'s own cap-escalate already
        # set STAGE_ESCALATED before calling here) — just tag it with the
        # case id so a reader can tell a case-carrying escalation apart from
        # a bare one, never re-mutate the stage/escalation fields it just set.
        gate_state["parked_case"] = case_id

    # Evict the worker ONLY when THIS case actually parks the worker's OWN
    # gate (BLOCKED/CLOSED). A worker whose own gate is still IN-FLIGHT is
    # mid-ladder — a recoverable wall (e.g. a land-grant patch-id re-mint the
    # worker itself resolves, or a wall whose case block id doesn't resolve to
    # the worker's live gate) must NOT free its slot: gate.record/close still
    # need that same worker to make the ✅ status-flip and close-out commits.
    # Freeing it here strands those stages with no worker and the gate silently
    # wedges at `record` (the s1 first-honest-SIM stall root). The worker's own
    # gate is looked up by the worker, never by the (possibly mismatched) case
    # block — so the guard holds regardless of block-id correlation.
    worker_gate = None
    if worker_id:
        wrec = (manifest.get("workers") or {}).get(worker_id) or {}
        wblock = wrec.get("block")
        worker_gate = (manifest.get("gates") or {}).get(wblock) if wblock else None
    worker_parked = worker_gate is not None and worker_gate.get("stage") in (
        gate.STAGE_ESCALATED, gate.STAGE_CLOSED)
    if worker_id and not eng.dry and worker_parked:
        eng._release_worker(worker_id, reason=f"case {case_id} ({source})")

    # Wave 18 (GAP-E): architect-first, always — NEVER an immediate operator
    # page. `core/architect.py::enqueue_triage` queues a PMT-TRIAGE job for
    # THIS case_id; only the architect's own `operator` verdict
    # (`architect_resolve`, below, called from `core/architect.py::
    # _advance_triage`) ever reaches `eng._page_operator` from here on.
    # Lazy import — `architect.py` imports `casestate` (for `parked_blocks`),
    # so a module-level `import architect` here would be circular; both
    # modules are always fully loaded by the time ANY function in either is
    # actually called, so a deferred import inside the function body is safe.
    import architect  # noqa: E402 (local, deliberately deferred — see above)
    architect.enqueue_triage(eng, manifest, case_id, source, block, detail, worker_id=worker_id)
    eng.log("flow", f"casestate: opened case {case_id!r} for block={block!r} "
                    f"source={source!r} — routed ARCHITECT-FIRST (PMT-TRIAGE), "
                    f"never an immediate operator page: {detail}")
    return case_id


def architect_resolve(eng, manifest, case_id, verdict, note=None):
    """The architect's OWN settle of a case it owns (`owner="architect"`,
    `decision` still `None`) — called exclusively from `core/architect.py::
    _advance_triage` once a triage verdict is observed. `verdict` ∈
    `{"scope_forward", "answer", "operator"}` (wave 18/GAP-E's own 3-verdict
    contract):

      `scope_forward`/`answer` — resolved by the architect ENTIRELY, the
      operator is NEVER paged: clears the case (`decision` set, popped from
      `manifest["cases"]` this same call — "≤1 tick", `settle`'s own bound)
      and drops the block's terminal gate + worker record
      (`_drop_gate_and_worker`, the SAME re-drivable mechanism `settle`'s own
      `resume`/`amend` verbs already use) so a FRESH SPAWN drives it again.
      `answer` additionally relays the architect's own note to the walled
      worker first (`eng._to_worker`, `architect.answer` kind) — the SAME
      courtesy-notice shape `settle`'s own `amend` verb already has (the
      worker's slot is already gone by the time this fires).

      `operator` — NEVER resolved here: `case["owner"]` flips to
      `"operator"` and THE FLOOR fires its FIRST page (the identical
      `eng._page_operator` call + paging bookkeeping `open_case` used to do
      directly, pre-wave-18) — the case stays OPEN, now genuinely the real
      `settle()` (the operator's own reply)'s to resolve; `reping` (GAP-A's
      floor) picks it up unchanged the instant ownership flips (it re-pings
      every still-open `owner="operator"` case, forever, same as before this
      wave).

    An unknown/already-cleared `case_id`, or a case no longer open
    (`decision` already set), is a LOGGED NO-OP — never a crash, never a
    second resolution of an already-settled case, mirroring `settle`'s own
    forgiving discipline for exactly the same shapes."""
    cases = manifest.get("cases") or {}
    case = cases.get(case_id)
    if case is None:
        eng.log("flow", f"casestate: architect_resolve for unknown/already-"
                        f"cleared case_id={case_id!r} (verdict={verdict!r}) — "
                        f"logged, no-op, no case wrongly cleared")
        return False
    if case.get("decision") is not None:
        eng.log("flow", f"casestate: architect_resolve for ALREADY-SETTLED "
                        f"case {case_id!r} (verdict={verdict!r}, already "
                        f"decided {case.get('decision')!r}) — logged, no-op")
        return False

    block = case.get("block")
    worker_id = case.get("worker_id")

    if verdict == "operator":
        case["owner"] = "operator"
        case["architect_verdict"] = verdict
        # Wave 17 (GAP-A): the FIRST page for THIS case — identical shape to
        # the page `open_case` used to fire itself, pre-wave-18.
        receipt = eng._page_operator(case_id, block, case.get("detail"),
                                     worker_id=worker_id, manifest=manifest)
        case["paging"] = {
            "attempts": 1,
            "consecutive_fail": 0 if receipt == "delivered" else 1,
            "last_receipt": receipt,
            "holding_since": None,
            "channel_escalated": False,
        }
        eng.log("flow", f"casestate: architect ESCALATED case {case_id!r} to "
                        f"the OPERATOR (paged, receipt={receipt!r}): "
                        f"{case.get('detail')}")
        return True

    # scope_forward / answer — resolved by the architect ITSELF, the
    # operator is NEVER paged for this case.
    case["decision"] = verdict
    case["architect_verdict"] = verdict
    case["settled_at"] = _now_iso()
    if note:
        case["note"] = note

    if verdict == "answer" and worker_id and not eng.dry:
        eng._to_worker(
            worker_id,
            note or f"[TRON]  architect answer on case {case_id} — see "
                    f"guidance, re-drive.",
            "architect.answer")

    _drop_gate_and_worker(manifest, block)
    eng.log("flow", f"casestate: case {case_id!r} ARCHITECT-{verdict.upper()} "
                    f"— block {block!r} un-blocked, re-drivable (fresh gate/"
                    f"re-dispatch next fill), operator NEVER paged")
    cases.pop(case_id, None)   # cleared, same call — "≤1 tick"
    return True


def open_operator_case(eng, manifest, block, source, detail, worker_id=None, kind=None):
    """Mint a case `owner="operator"` from BIRTH and page immediately — a
    legitimate direct-to-operator path for an escalation the architect itself
    cannot be architect-first'd for. Three callers, all in `core/architect.py`:
    (1) the architect's OWN `operator` verdict for a triage job that never had an
    existing casestate case behind it (`core/classify.py`'s unclassified path —
    raw free text with no block/gate to park; `_advance_triage`);
    (2) ADR-0009 R-G, `_advance_delivery`'s no-progress budget (DISSOLVED from
    ADR-0006 R1c's dedicated cold-start ladder, consolidated onto the deliver-
    until-consumed invariant) — a genuinely stuck/dead architect's OWN order
    never reaching `read_hwm(ARCH) >= dispatch_seq` past a bounded budget (the
    architect cannot triage its own death, and it is pool-excluded from every
    worker liveness net);
    (3) ADR-0006 R1d, `_backstop_refused_authoring` — the architect took its
    ordered forward/log turn but authored NO branch (land grant fail-closed) and
    settled idle; its own refusal routes here so the work is never a silent wedge
    or a dropped log-review finding. None is a bypass of architect-first for WORKER
    escalations: a `worker.wall`/`sentry.cap`/liveness-stall for a worker NEVER
    reaches here directly — those always go through `open_case` ->
    `core/architect.py::enqueue_triage` -> `architect_resolve`."""
    cases = manifest.setdefault("cases", {})
    case_id = next_case_id(manifest, block, source)
    cases[case_id] = {
        "case_id": case_id,
        "block": block,
        "source": source,
        "kind": kind or source,
        "worker_id": worker_id,
        "detail": detail,
        "decision": None,
        "opened_at": _now_iso(),
        "owner": "operator",
        "architect_verdict": "operator",
    }
    receipt = eng._page_operator(case_id, block, detail, worker_id=worker_id, manifest=manifest)
    cases[case_id]["paging"] = {
        "attempts": 1,
        "consecutive_fail": 0 if receipt == "delivered" else 1,
        "last_receipt": receipt,
        "holding_since": None,
        "channel_escalated": False,
    }
    eng.log("flow", f"casestate: architect verdict=operator minted operator-"
                    f"owned case {case_id!r} (source={source!r}, "
                    f"block={block!r}) — paged (receipt={receipt!r}): {detail}")
    return case_id


def reping(eng, manifest, now):
    """THE FLOOR (GAP-A, wave 17) — the #2 historical failure
    (`operator-page-failed::page-receipt-permanent-fail`, 13x) made
    structurally impossible: every still-OPEN case (`decision is None`) is
    re-paged forever on a bounded backoff until EITHER a `delivered`
    receipt is on file OR the operator answers (`settle`, above). There is
    NO code path in this function — or anywhere else in this module — that
    closes, drops, or permanently-fails an unanswered case.

    Shape mirrors `core/sentry.py`'s own holding-clock ladder
    (`PAGE_REPING_AFTER`/`PAGE_CHANNEL_ESCALATE_AFTER` standing in for that
    module's `GATE_NUDGE_AFTER`/`GATE_IDLE_CAP`) but the cap here NEVER
    turns the CASE terminal the way a sentry cap turns a GATE terminal:
    capping a page only ever escalates the CHANNEL — a louder `page_kind`
    on every subsequent page PLUS a forensic, WARNING-and-retry `manifest
    ["escalations"]` record (keyed `target_block`/`case`, deliberately NOT
    `block` — so it can never be mistaken for, or accidentally counted
    alongside, a gate-driven or sentry-cap escalation record by a reader
    filtering on that field) — the case itself stays open, forever, exactly
    as it did before the cap tripped.

    A `delivered` receipt on file satisfies the ladder outright — no
    further re-ping, ever, for that case ("no more pings than the backoff
    dictates"). A `failed` receipt and an ABSENT one (no `eng._deliver_page`
    hook wired — production, this wave) are treated identically: the SAME
    floor outcome, forced onward the next tick this case's holding clock
    qualifies — never a silently-dropped failure.

    Called once per `core/sentry.py::pace()` call, off the SAME clock
    reading that call already minted (one shared clock for every ladder in
    this stack — gate, reviewer, and page pacing alike). Deliberately NOT
    folded into `pace()`'s own `nudged`/`escalated` return — a DIFFERENT
    ladder, paging receipts, never a gate/reviewer stage outcome; `core/
    tick.py` only ever reads those two keys off `pace()`'s result, so this
    ladder's own activity is invisible to (never breaks) any existing
    caller/rig that already asserts on them.

    Returns the list of case_ids re-pinged THIS call — a non-durable
    convenience for a caller/rig; `manifest["cases"][cid]["paging"]` +
    `manifest["operator_pages"]` are the durable record."""
    cases = manifest.get("cases") or {}
    repinged = []
    for case_id, case in cases.items():
        if case.get("decision") is not None:
            continue   # settled — pinging stops, exactly like sentry skips a terminal gate

        if case.get("owner") != "operator":
            continue   # wave 18 (GAP-E): still architect-owned (not yet
                       # triaged) — THE FLOOR only ever pings the
                       # OPERATOR-owned stage, never before the architect
                       # has had its own first look

        # ADR-0008 — a landing worker.wall that opened + paged, then HEALED
        # (its block closed out on trunk after the first page): settle it on
        # durable trunk truth rather than re-paging forever. NOT a silent drop
        # of an unanswered page — the thing paged about is provably resolved on
        # trunk (recorded as a distinct decision, loudly logged); the FLOOR's
        # invariant ("never silently drop an UNANSWERED page") holds.
        if pipeline.stale_landing_wall(manifest, case.get("source"),
                                       case.get("worker_id"), case.get("detail")):
            case["decision"] = "stale-resolved-on-trunk"
            case["settled_at"] = _now_iso()
            eng.log("flow", f"casestate: case {case_id!r} STALE-RESOLVED — landing "
                            f"worker.wall block closed on trunk; paging stops, page "
                            f"provably answered by trunk (never an unanswered drop) (ADR-0008)")
            continue

        paging = case.setdefault("paging", {
            "attempts": 0, "consecutive_fail": 0, "last_receipt": None,
            "holding_since": None, "channel_escalated": False,
        })

        if paging.get("last_receipt") == "delivered":
            continue   # satisfied — no more pings than the backoff dictates

        if paging.get("holding_since") is None:
            # First sighting of this ladder for this case (the same tick it
            # opened, or the first pace() call after) — mirrors sentry's own
            # "just advanced" episode start: anchor the clock, no re-ping
            # counted yet (open_case's own call already sent attempt #1).
            paging["holding_since"] = now
            continue

        holding = now - paging["holding_since"]
        if holding < PAGE_REPING_AFTER:
            continue

        # ── THE FLOOR: force the re-ping — a failed/absent receipt is
        #     NEVER silently dropped, NEVER a reason to close/abandon ──
        page_kind = "operator_page_failed" if paging["channel_escalated"] else "operator_page"
        receipt = eng._page_operator(case_id, case.get("block"), case.get("detail"),
                                     worker_id=case.get("worker_id"), manifest=manifest,
                                     page_kind=page_kind)
        paging["attempts"] += 1
        paging["last_receipt"] = receipt
        paging["holding_since"] = now   # reset the anchor — bounded backoff, never a busy-loop
        repinged.append(case_id)

        if receipt == "delivered":
            paging["consecutive_fail"] = 0
            continue

        paging["consecutive_fail"] += 1
        if paging["consecutive_fail"] >= PAGE_CHANNEL_ESCALATE_AFTER and not paging["channel_escalated"]:
            paging["channel_escalated"] = True
            detail = (f"case {case_id!r} (target_block={case.get('block')!r}) — "
                     f"{paging['consecutive_fail']} consecutive failed/absent operator-page "
                     f"deliveries (>= PAGE_CHANNEL_ESCALATE_AFTER={PAGE_CHANNEL_ESCALATE_AFTER}) "
                     f"— CHANNEL escalated (louder paging kind going forward); the case itself "
                     f"stays OPEN, never closed, never marked permanent-fail — WARNING-and-retry, "
                     f"never terminal")
            manifest.setdefault("escalations", []).append({
                "target_block": case.get("block"), "case": case_id,
                "kind": "operator-page-failed", "level": "warning",
                "consecutive_fail": paging["consecutive_fail"], "detail": detail, "at": now})
            eng.log("operator", f"casestate: CHANNEL ESCALATED for case {case_id!r} — {detail}")

    return repinged


def settle(eng, manifest, case_id, verb, note=None):
    """Apply the operator's reply to a parked case. Returns `True` if a case
    was genuinely settled this call, `False` for a logged no-op (unknown/
    duplicate case_id, or an unrecognized verb) — NEVER raises, NEVER
    crashes, NEVER clears/mutates a case other than the one `case_id`
    itself resolves."""
    cases = manifest.get("cases") or {}
    case = cases.get(case_id)
    if case is None:
        eng.log("flow", f"casestate: settle for unknown/already-cleared "
                        f"case_id={case_id!r} (verb={verb!r}) — logged, no-op, "
                        f"no case wrongly cleared")
        return False
    if case.get("decision") is not None:
        eng.log("flow", f"casestate: settle for ALREADY-SETTLED case "
                        f"{case_id!r} (verb={verb!r}, already decided "
                        f"{case.get('decision')!r}) — duplicate reply, logged, no-op")
        return False
    if case.get("owner") == "architect":
        # Wave 18 (GAP-E): the operator can never bypass the architect's own
        # triage — a case still `owner="architect"` (not yet escalated by
        # `architect_resolve`'s `operator` verdict) rejects an
        # `operator.decision` the same forgiving way any other malformed
        # reply does: logged, no-op, the case stays open exactly as it was.
        eng.log("flow", f"casestate: settle for case {case_id!r} (verb="
                        f"{verb!r}) rejected — still ARCHITECT-owned (not yet "
                        f"triaged to the operator) — logged, no-op, never a "
                        f"bypass of GAP-E's architect-first routing")
        return False
    if verb not in VERBS:
        eng.log("flow", f"casestate: settle for case {case_id!r} carried an "
                        f"unrecognized verb {verb!r} (must be one of {VERBS}) "
                        f"— logged, no-op, case stays open")
        return False

    case["decision"] = verb
    case["settled_at"] = _now_iso()
    if note:
        case["note"] = note

    block = case.get("block")
    worker_id = case.get("worker_id")

    if verb == "abandon":
        abandoned = manifest.setdefault("abandoned_blocks", [])
        if block and block not in abandoned:
            abandoned.append(block)
        _drop_gate_and_worker(manifest, block)
        eng.log("flow", f"casestate: case {case_id!r} ABANDONED — block "
                        f"{block!r} dropped (out of must-reach-done scope, "
                        f"never re-dispatched)")
    else:
        if verb == "amend" and worker_id and not eng.dry:
            eng._to_worker(
                worker_id,
                note or f"[TRON]  operator amendment on case {case_id} — "
                        f"see the operator's note and re-drive.",
                "operator.amend")
        _drop_gate_and_worker(manifest, block)
        eng.log("flow", f"casestate: case {case_id!r} {verb.upper()}D — block "
                        f"{block!r} un-blocked, re-drivable (fresh gate/"
                        f"re-dispatch next fill)")

    cases.pop(case_id, None)   # cleared, same call — "≤1 tick"
    return True
