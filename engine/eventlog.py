"""eventlog — the structured, forensic event + failure log (01-06).

Every engine event, and — first-class — every failure, becomes one machine-readable
JSONL record in `events.jsonl`, queryable by any field. The failure path is complete
enough to reconstruct the exact cause with **no re-run**: class · code · operation ·
inputs · exact-cause · state (run · tick · trunk · node) · next-action.

Distinct from the two existing logs, by design:
  - `home-events.jsonl` — human-visible console copy (channel + rendered text), replayed
    on reconnect. Prose, for a person.
  - `logs/<name>-<date>.log` — operator-readable narration lines. Prose, for a person.
  - `events.jsonl` (this) — the forensic record. Records, not prose; the answer to
    *why did TRON fail*, reconstructable offline.

The failure taxonomy is closed (FAILURE_CLASSES). Two classes that the diagram shows as
failures are **agent-side**, never TRON's own deterministic step — TRON neither merges
nor deploys (agents land all of it via PR). A merge conflict or a failed deploy reaches
TRON as a worker `wall` and is recorded on the escalation path (`gate-stuck` /
`escalate`), not invented here.
"""
import util

# Closed failure taxonomy (T2). Each failure record carries exactly one fclass.
#   refresh-fail  — trunk fast-forward failed (best-effort retry, then loud halt at the death-cap)
#   classify-fail — the one classify LLM exhausted its retry budget -> auto-ack to `unclassified`
#   ingest-drop   — a single inbound message raised while being classified/ingested (poison-pill guard)
#   gate-stuck    — a supervised stage (DONE gate, review attest, architect job — 01-13)
#                   exceeded its re-nudge cap and escalated (the no-silent-stuck wall)
#   dispatch-fail — spawning a worker process failed
#   session-residue — session end found unlanded/failed paperwork or leftover branches
#                   (tron-13 D1 sweep: named + parked on the operator, never auto-landed)
#   crash         — an unhandled exception escaped a whole tick (caught by the WAKE supervised loop)
#   content-missing — a schema-marked content-bearing field arrived empty at its ingest
#                   choke point (contentless wall, contentless peer/tron question — 01-31,
#                   ADR-0002 D5): NAK'd at the door, never substituted/discarded silently.
#   handler-raised  — a routed trigger's handler raised (01-31, AC-5b): the trigger is
#                   dropped (never strands the tick) but never silently, now.
#   mailbox-send-failed — an engine->worker mailbox write failed (OSError) after retry
#                   (01-31, AC-5 HIGH): queued durable for at-least-once redelivery.
#   sealed-allowlist-violation — a handler tripped the git wrapper's sealed subcommand
#                   allowlist (review round 1, F4, ADR-0002 D1): a distinct class from
#                   `handler-raised` on purpose — this is the write-boundary audit's
#                   own tripwire, never an ordinary handler bug, and routes to the
#                   architect as a VIOLATION case rather than a dropped trigger.
#   operator-page-failed — T4 (01-36, ADR-0003 D-G engine half): a transport
#                   receipt (the minimal stub slot `_consume_page_receipt` reads)
#                   named a case's operator page as a PERMANENT delivery failure.
#                   Never a silent drop: the case's next re-ping is forced
#                   immediate (the engine's own existing escalation ladder) —
#                   this class is the forensic record of why.
FAILURE_CLASSES = {
    "refresh-fail", "classify-fail", "ingest-drop", "gate-stuck",
    "dispatch-fail", "session-residue", "crash",
    "content-missing", "handler-raised", "mailbox-send-failed",
    "sealed-allowlist-violation", "operator-page-failed",
}

# The closed vocabulary of `type` values an `event` record carries — the engine's own
# forensic record of what it did, complete enough to reconstruct a run's per-tick / per-
# decision / per-model-call trace offline (the run-trace observer reads exactly these). Not
# enforced at emit (a forensic log never blocks); the taxonomy test asserts every emit site
# stays inside this set so the vocabulary can't drift silently.
#   tick          — one per tick: trigger_source (timer|event|manual) + snapshot_hash (provenance)
#   model_call    — one per LLM call at the judge chokepoint: tool · tier · retries · ok
#   dispatch      — a worker was spawned/assigned to a block
#   gate_advance  — a DONE-gate stage transition (from -> to)
#   settle        — an operator decision / disposition was applied to a parked case or block
#   release       — a worker slot was freed
#   escalate      — a condition was raised to the operator (wall/await)
#   case_reping   — a parked operator case was re-pinged (F-4/R-7 ladder, n = ping count)
#   case_safe_parked — the re-ping ladder capped; the case is safe-parked (named, resumable)
#   docs_landed   — the engine landed a paperwork branch on trunk (D1 lander: role · branch)
#   block_done    — a block reached ✅ on trunk
#   session_start / session_end / halt — session lifecycle
#   wall_auto_settled — F-1 self-healing (01-31, ADR-0002 D3/D5): a wall case auto-settled
#                   because the block's own gate observed the milestone done, never a
#                   sweep, never silent.
#   abandon       — a case settled `abandon`: worker released, case closed, visibly (01-31,
#                   D3 third bullet) — the loud event half of the drop.
#   abandon_flag_delivered — an abandon's manifest flag rode the architect's next
#                   dispatched touchpoint (01-31, D3 third bullet).
#   triage_dedup_dropped — a triage hand-off to the architect deduped on identical
#                   pending text (01-31, AC-5b): forensic, never silent.
#   unknown_worker_send — an engine->worker send named a worker no longer on the roster
#                   (01-31, MED inventory): forensic, never a silent no-op.
#   grant_minted  — T3 (01-32, ADR-0002 D2): a patch-id-bound merge/close grant was
#                   minted in TRON's own folder (case · block · branch · patch_id) —
#                   the authorize half of grant -> land.sh -> observe.
#   grant_consumed — T3 (01-32, ADR-0002 D2): a live grant was consumed
#                   ADMINISTRATIVELY by the engine (the land.sh-crashed-before-consume
#                   window: trunk advanced, patch-id matched over the observed range) —
#                   a write in TRON's own folder, forensic, never silent.
#   operator_page — T4 (01-36, ADR-0003 D-G engine half): the abstract operator-page
#                   record every case-correlated escalation stamps (_page_operator) —
#                   cid · block · detail · whether AIDE briefed it (ND-02-10). Distinct
#                   from `escalate` (the render/notice itself): this is the receipt-
#                   contract's own forensic anchor, read back by `_consume_page_receipt`.
EVENT_TYPES = {
    "tick", "model_call", "dispatch", "gate_advance", "settle", "release",
    "escalate", "case_reping", "case_safe_parked", "docs_landed", "block_done",
    "session_start", "session_end", "halt",
    "wall_auto_settled", "abandon", "abandon_flag_delivered",
    "triage_dedup_dropped", "unknown_worker_send", "grant_minted", "grant_consumed",
    "operator_page",
}


class EventLog:
    """Append-only writer over `ctx.event_log`. `env` is a zero-arg callable returning the
    live forensic context ({run, tick, trunk}) so every record is stamped without the caller
    threading it through."""

    def __init__(self, ctx, env=None):
        self.ctx = ctx
        self._env = env or (lambda: {})

    def _stamp(self, kind, type_, actor, block, tag, cid):
        rec = {"at": util.now_iso(), "kind": kind, "type": type_,
               "actor": actor, "block": block, "tag": tag, "cid": cid}
        env = self._env() or {}
        rec["run"] = env.get("run")
        rec["tick"] = env.get("tick")
        rec["trunk"] = env.get("trunk")
        return rec

    def event(self, type_, *, actor="TRON", block=None, tag=None, cid=None, **payload):
        """A normal flow event. Carries the full common header (AC-1)."""
        rec = self._stamp("event", type_, actor, block, tag, cid)
        rec["payload"] = payload
        util.append_jsonl(self.ctx.event_log, rec)
        return rec

    def failure(self, fclass, code, operation, cause, *, actor="TRON", block=None,
                tag=None, cid=None, inputs=None, node=None, next_action=None, attempt=None,
                **payload):
        """A first-class failure record (AC-2). Complete enough to reconstruct the exact
        cause offline: class · code · operation · inputs · cause · state · next-action.
        (`next_action`, not `next`, to avoid shadowing the builtin; stored as the `next` field.)"""
        rec = self._stamp("failure", "failure", actor, block, tag, cid)
        rec["fclass"] = fclass
        rec["code"] = code
        rec["operation"] = operation
        rec["cause"] = cause
        rec["inputs"] = inputs or {}
        rec["node"] = node
        rec["next"] = next_action
        rec["attempt"] = attempt
        rec["payload"] = payload
        util.append_jsonl(self.ctx.event_log, rec)
        return rec

    def unclassified(self, raw, why, *, sender=None, cid=None):
        """Every `unclassified` message, logged with its raw body + why no tag matched (T3) —
        so the classify grammar can be learned/extended over time."""
        actor = (sender or {}).get("id") or (sender or {}).get("kind") or "unknown"
        rec = self._stamp("unclassified", "unclassified", actor, None, "unclassified", cid)
        rec["payload"] = {"raw": raw, "why": why}
        util.append_jsonl(self.ctx.event_log, rec)
        return rec


# ── query path (T4): the operator-facing answer to "why did TRON fail" ──
def query(ctx, *, run=None, block=None, fclass=None, kind=None,
          failures_only=False, limit=None, newest_first=True):
    """Pull records, filtered by any field, newest-first by default. Returns a list of dicts.

    failures_only (or any fclass filter) narrows to failure records — "every failure for
    run X / block Y / class Z, with full detail" (AC-5)."""
    recs = util.read_jsonl(ctx.event_log)
    if failures_only or fclass:
        recs = [r for r in recs if r.get("kind") == "failure"]
    if kind:
        recs = [r for r in recs if r.get("kind") == kind]
    if run:
        recs = [r for r in recs if r.get("run") == run]
    if block:
        recs = [r for r in recs if r.get("block") == block]
    if fclass:
        recs = [r for r in recs if r.get("fclass") == fclass]
    if newest_first:
        recs = list(reversed(recs))
    if limit:
        recs = recs[: int(limit)]
    return recs
