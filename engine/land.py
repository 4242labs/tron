"""land — T1 (01-34, ADR-0003 D-B): the ONE landing primitive.

Past cycles fixed landing CASES, not the landing ROOT: each patch hand-rolled a NEW
copy of the same `mint -> order -> observe` orchestration, one per call site —
code-merge, record-redrive, record-paperwork, `_drain_landings` (architect +
reviewer paperwork), close-confirm, violation-repair (seven counting the merge-gate
base) — divergent and buggy (the record-stage arm had NO grant path at all per
`SIM-WAVE-HARD-FAIL`; the merge gate mis-advanced per CASE-008). This module
collapses all of them into one sequence, `land_via_grant()`, called from exactly
one seam in `fsm.py` (`Engine._land_via_grant`). Every former call site is now a
thin scope-supplying shim: it decides WHETHER a landing is content-safe (a pure
ff-ability check for code, a paperwork-restricted `trunk.verify_docs` for docs, a
content-pinned `trunk.land_ordered_merge` for an approved violation range) and WHAT
case-id names it — then hands off here for the mechanics, exactly once: mint
(patch-id-bound, fail-closed on an unresolvable/off-token id) -> order (the worker
runs `land.sh`) -> observe (trunk-ancestry) -> consume.

**Structural single-source (AC-1):** the sub-primitives below (`_mint_or_reuse_grant`
/ `_order_land` / `_observe_landed` / `_consume_grant_administratively`) are private
to THIS module and called only from `land_via_grant`, in this same file — no other
module names them (`fsm.py` imports and calls only `land_via_grant`, via its own
`_land_via_grant` seam). A "no second caller" test is a backstop here, never the
guarantee — the guarantee is that nothing outside this file can even see them.

The bar is CORRECT, not parity with the seven copies this replaces (ADR-0003 D-B) —
in particular the RECORD-stage paperwork arm, which had no grant path at all before
01-32/33's emergency patch, lands through this exact sequence like every other site
now (AC-2)."""
import grants
import trunk


def _mint_or_reuse_grant(eng, case_id, block, branch, patch_id):
    """Idempotent per-tick mint: a LIVE grant whose patch-id already matches this
    branch's CURRENT content is left untouched (already ordered — nothing to
    resend); anything else (missing, expired, or content-changed — a rebase that
    altered the diff) gets a fresh grant. Fail-closed on `patch_id == ""` or a
    case-id outside `land.sh`'s safe-token alphabet — both `grants.mint`'s own
    contract. Returns `(grant_or_None, freshly_minted)` — the caller (re)orders the
    worker iff `freshly_minted`, never on a bare reuse (that would spam the same
    order every tick for a still-pending, unchanged grant)."""
    if not case_id or not patch_id:
        return None, False
    live = grants.read_live(eng.ctx.grants_dir, case_id)
    if live and live.get("patch_id") == patch_id:
        return live, False
    g = grants.mint(eng.ctx.grants_dir, case_id, block, branch, patch_id,
                    ttl_min=eng._grant_ttl())
    if g:
        eng.events.event("grant_minted", block=block, case=case_id,
                         branch=branch, patch_id=patch_id)
        eng.log("flow", f"grant[{case_id}] minted for {block} ({branch} "
                        f"@ patch-id {patch_id[:12]})")
    return g, bool(g)


def _order_land(eng, wid, block, case_id, branch, kind="gate.land"):
    """Order the responsible agent to run the scaffold's `land.sh` — the ONLY
    sanctioned way trunk advances (ADR-0002 D2). Engine-composed, dry-safe (never
    sends under dry, same convention as every other `_to_worker` line)."""
    if not wid or eng.dry:
        return
    eng._to_worker(wid, f"[TRON]  {wid} — grant approved (case {case_id}): run "
                        f"`meta/scripts/land.sh {case_id}` to land {branch} onto "
                        f"trunk yourself. I observe trunk and pick it up the "
                        f"moment it lands — no separate report needed.", kind)


def _observe_landed(eng, branch, truth_ref):
    """Has `branch`'s tip already reached trunk — land.sh actually ran (or, dry /
    best-effort test fixtures, the mode's own vacuous-pass convention every other
    ratchet predicate here already uses)? Committed-ref read only, never a
    working-tree/say-so check — the same discipline `is_ancestor` always applies."""
    tip = trunk.tip_sha(eng.paths["root"], branch, eng.dry)
    return trunk.is_ancestor(eng.paths["root"], tip, truth_ref, eng.dry)


def _consume_grant_administratively(eng, case_id, result="engine-observed"):
    """The crash-window arm (ADR-0002 D2, "administrative consume"): a live grant
    whose landing the ENGINE observed (rather than `land.sh`'s own happy-path
    consume) is consumed here — idempotent (a no-op if already consumed), a WRITE
    strictly inside TRON's own folder (the grants dir), never a project write."""
    if eng.dry or not case_id:
        return
    grants.consume(eng.ctx.grants_dir, case_id, result=result)


def land_via_grant(eng, case_id, block, branch, wid, kind, scope):
    """T1 (01-34, ADR-0003 D-B): the ONE sequence every landing site now drives
    through — `eng` is the live `Engine` (duck-typed: `.paths`, `.dry`, `.ctx`,
    `.events`, `.log`, `._truth_ref()`, `._to_worker`, `._grant_ttl()`).

    Returns one of:
      "landed"      observed landed — either freshly consumed THIS call, or an
                    already-consumed receipt was on file (the idempotent
                    already-landed short-circuit, AC-2's "incl. consumed-grant
                    +receipt" — the ONLY proof that survives a since-deleted
                    branch, where a live ancestry read can no longer resolve a
                    tip at all).
      "pending"     a grant is live (freshly minted or reused unchanged) and the
                    worker has been ordered (once, on the mint, never re-spammed
                    for an unchanged live grant); not yet observed landed. The
                    caller re-evaluates on a later tick/report. Grant EXPIRY is
                    the caller's own concern (`_grant_expired_reopen` — the
                    re-park bookkeeping it pops differs by scope, so it stays a
                    per-shim decision, not this primitive's).
      "fail-closed" the branch's patch-id is unresolvable ("") or the case-id
                    falls outside `land.sh`'s safe-token alphabet — no grant
                    minted (`grants.mint`'s own fail-closed rider); the caller
                    holds exactly as if nothing had been attempted.

    Never decides WHETHER the content is safe to land — that precondition (a pure
    ff-ability check for code, a paperwork-restricted `verify_docs`, a
    content-pinned `land_ordered_merge` for an approved violation range) is the
    caller's, checked BEFORE this is called (the "thin scope-supplying shim")."""
    if not case_id or not branch:
        return "fail-closed"
    truth_ref = eng._truth_ref()
    # Observation-first (AC-2): an already-consumed receipt is authoritative and
    # free — never re-mint/re-order/re-observe a case already settled.
    if grants.read_consumed(eng.ctx.grants_dir, case_id):
        return "landed"
    if _observe_landed(eng, branch, truth_ref):
        _consume_grant_administratively(eng, case_id)
        eng.log("flow", f"land[{case_id}] {scope}: observed landed -> consumed")
        return "landed"
    pid = trunk.patch_id(eng.paths["root"], branch, truth_ref, eng.dry)
    grant, fresh = _mint_or_reuse_grant(eng, case_id, block, branch, pid)
    if not grant:
        if not eng.dry:
            eng.log("flow", f"land[{case_id}] {scope}: unresolvable patch-id — "
                            f"no grant minted (fail-closed)")
        return "fail-closed"
    if fresh:
        _order_land(eng, wid, block, case_id, branch, kind=kind or "gate.land")
    if _observe_landed(eng, branch, truth_ref):
        _consume_grant_administratively(eng, case_id)
        eng.log("flow", f"land[{case_id}] {scope}: landed same-tick -> consumed")
        return "landed"
    return "pending"
