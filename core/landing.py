"""core.landing — ADR-0004 rewrite, brick 1: the ONE landing primitive, re-cut
with CONTENT-BOUND case-id identity.

CONFIRMED ROOT (engine/land_paperwork_rig.py, real-git, committed on
feat/l1-harness-landing-fix): the old primitive (`engine/land.py::land_via_grant`)
keys a paperwork case-id PURELY off role + branch name
(`paperwork-<role>-<branch>`, fsm.py's `_drain_landings`). When the SAME branch
is re-enqueued with NEW content (a later reconcile/forward re-authors it — a
different patch-id), the deterministic case-id collides with the ALREADY-
CONSUMED grant from the FIRST landing:

  - `land.py` (land.py:121-122) checks `grants.read_consumed(case_id)` FIRST,
    before anything else, and short-circuits `"landed"` on a hit — never
    re-deriving the branch's CURRENT patch-id, never even looking at content.
  - `land.sh` (~line 86) has the identical shape: `consumed/<case_id>.grant`
    exists -> "already consumed ... exit 0", checked BEFORE the live grant
    file or the branch's patch-id are read at all.

Net effect: the Nth re-authoring of a same-named branch is reported LANDED —
a false `docs_landed` fires — while its content never reaches trunk. Silent
loss, not a wedge; the worst shape a landing primitive can take.

THE FIX (this module): landing identity is CONTENT-BOUND — ONE invariant,
constructed at one place and enforced at one place:

  - CONSTRUCTED by `paperwork_case_id` below: the case-id embeds the branch's
    patch-id, so new content -> new case-id -> a receipt from stale content
    can never even be LOOKED UP under the new case-id in the first place.
    This also means `land.sh` (UNCHANGED, a respected contract) never sees a
    stale consumed receipt for genuinely new content, because the case-id
    it's invoked with is itself new.

  - ENFORCED at the single landing seam, `land_via_grant` below, regardless
    of what case-id scheme a caller uses: before trusting a consumed receipt
    found under `case_id`, re-derive the branch's CURRENT patch-id and
    compare it to the receipt's own `patch_id` field. A receipt only
    short-circuits `"landed"` when its content still matches what's on the
    branch RIGHT NOW (or when the branch's current content is unresolvable —
    e.g. a since-deleted branch post-land, the one case a live ancestry read
    can no longer see at all, where the receipt is the ONLY surviving proof
    and must still be trusted). A receipt whose patch-id has diverged is
    STALE for this content: never short-circuit on it — fall through to
    observe/mint/order exactly as if no receipt existed, so the new content
    gets a real grant and a real land.

  This is one invariant, not a hedge: construction makes the stale-receipt
  path structurally unreachable for a well-behaved caller (this module's own
  `gate.py` caller included); enforcement is the SAME invariant's single
  checkpoint, so even a caller that (mis)reuses a colliding case-id can never
  have unlanded content masked by an old receipt. There is exactly one
  content-bound-identity mechanism here, expressed twice — construct, then
  enforce — never two independent mechanisms.

Otherwise this ports `engine/land.py::land_via_grant`'s sequence faithfully:
observe-first (real ancestry), patch-id fail-closed (`grants.mint`'s own
contract), mint-or-reuse (reuse only when the live grant's patch-id matches
current content), order the worker only on a fresh mint (never re-spam an
unchanged live grant), observe-and-consume.

Duck-types the engine context exactly like `land.py` does: `eng.paths`,
`eng.dry`, `eng.ctx.grants_dir`, `eng.events`, `eng.log`, `eng._truth_ref()`,
`eng._to_worker`, `eng._grant_ttl()`. Trunk reads (`tip_sha`, `patch_id`,
`is_ancestor`) go through `core.gitobs` — the new stack's single
git-observation seam — never a direct `import trunk` here. Reuses `grants.py`
as-is (imported, never forked; a clean library, not git observation — may be
vendored into `core/` in a later pass) — a respected contract this module
does not and must not modify.
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)
_ENGINE_DIR = os.path.join(_APP_ROOT, "engine")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import grants   # noqa: E402  — respected contract, imported as-is (never forked)
import gitobs   # noqa: E402  — core/gitobs.py, the ONE git-observation seam

# Mirrors grants.CASE_ID_TOKEN's safe-token alphabet (land.sh's own
# pre-interpolation guard) — used here only to SANITIZE a branch name into a
# case-id component, never to relax the contract grants.py/land.sh already
# enforce on the case-id as a whole.
_UNSAFE_TOKEN_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def paperwork_case_id(role, branch, patch_id):
    """The content-binding fix, in one function: a paperwork case-id that
    embeds the branch's CURRENT patch-id, so a same-named branch re-authored
    with new content derives a DIFFERENT case-id — a stale receipt from the
    old content can never even be looked up under the new one.

    `"paperwork-{role}-{sanitized_branch}-{patch_id[:12]}"` — branch is
    sanitized to the safe-token alphabet `[A-Za-z0-9._-]+` (grants.py's
    `CASE_ID_TOKEN` / land.sh's own guard), 12 hex chars of patch-id is ample
    collision resistance for a single project's paperwork lane while keeping
    the case-id readable. `patch_id` unresolvable (`""`) still produces a
    (fail-closed-downstream) case-id — `grants.mint` itself refuses to mint
    against an empty patch-id, so this never becomes a false pass; it just
    means the caller gets a stable "no content yet" case-id rather than this
    helper raising."""
    safe_branch = _UNSAFE_TOKEN_CHARS.sub("-", branch or "")
    return f"paperwork-{role}-{safe_branch}-{(patch_id or '')[:12]}"


def _mint_or_reuse_grant(eng, case_id, block, branch, patch_id):
    """Ported verbatim from `land.py::_mint_or_reuse_grant` (private to this
    module, same contract): a LIVE grant whose patch-id already matches this
    branch's CURRENT content is reused untouched; anything else (missing,
    expired, or content-changed) gets a fresh grant. Fail-closed on
    `patch_id == ""` or an off-alphabet case-id — `grants.mint`'s own
    contract. Returns `(grant_or_None, freshly_minted)`."""
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
    """Ported verbatim from `land.py::_order_land`: order the responsible
    agent to run the scaffold's `land.sh` — the ONLY sanctioned way trunk
    advances (ADR-0002 D2). Engine-composed, dry-safe."""
    if not wid or eng.dry:
        return
    eng._to_worker(wid, f"[TRON]  {wid} — grant approved (case {case_id}): run "
                        f"`meta/scripts/land.sh {case_id}` to land {branch} onto "
                        f"trunk yourself. I observe trunk and pick it up the "
                        f"moment it lands — no separate report needed.", kind)


def _observe_landed(eng, branch, truth_ref):
    """Ported verbatim from `land.py::_observe_landed`: has `branch`'s tip
    already reached trunk? Committed-ref read only, never working-tree/say-so."""
    tip = gitobs.tip_sha(eng.paths["root"], branch, eng.dry)
    return gitobs.is_ancestor(eng.paths["root"], tip, truth_ref, eng.dry)


def _consume_grant_administratively(eng, case_id, result="engine-observed"):
    """Ported verbatim from `land.py::_consume_grant_administratively`: the
    crash-window arm — a live grant whose landing the ENGINE observed is
    consumed here, idempotent, a write strictly inside TRON's own grants dir."""
    if eng.dry or not case_id:
        return
    grants.consume(eng.ctx.grants_dir, case_id, result=result)


def land_via_grant(eng, case_id, block, branch, wid, kind, scope):
    """The ONE landing sequence — CORRECTED per the confirmed root above.
    `eng` is the live Engine (duck-typed, see module docstring).

    Returns one of:
      "landed"      observed landed — freshly consumed this call, or an
                    already-consumed receipt was on file WHOSE PATCH-ID
                    STILL MATCHES the branch's current content (or whose
                    content is unresolvable, e.g. a since-deleted branch —
                    the receipt is the only surviving proof there).
      "pending"     a grant is live (freshly minted or reused unchanged) and
                    the worker has been ordered (once, on the mint); not yet
                    observed landed. The caller re-evaluates on a later tick.
      "fail-closed" the branch's patch-id is unresolvable ("") or the
                    case-id falls outside land.sh's safe-token alphabet — no
                    grant minted (`grants.mint`'s own fail-closed rider).

    Never decides WHETHER content is safe to land — that precondition is the
    caller's, exactly as in `land.py`."""
    if not case_id or not branch:
        return "fail-closed"
    truth_ref = eng._truth_ref()

    # THE FIX, enforced (the same content-bound-identity invariant
    # `paperwork_case_id` CONSTRUCTS — see module docstring — makes this arm
    # structurally unreachable for a caller that content-binds its own
    # case-ids, but this is the invariant's one enforcement point, so the
    # primitive stays honest even if a caller doesn't): a consumed receipt is
    # trusted ONLY when its patch_id still matches the branch's CURRENT
    # content, or when current content is unresolvable (a since-deleted
    # branch — the receipt is the only proof left, same rationale land.py's
    # original short-circuit relied on). A receipt whose patch-id has
    # DIVERGED is stale for this content and must never mask it — fall
    # through to observe/mint/order for the real thing.
    consumed = grants.read_consumed(eng.ctx.grants_dir, case_id)
    if consumed:
        cur_pid_for_receipt = gitobs.patch_id(eng.paths["root"], branch, truth_ref, eng.dry)
        if not cur_pid_for_receipt or consumed.get("patch_id") == cur_pid_for_receipt:
            return "landed"
        eng.log("flow", f"land[{case_id}] {scope}: consumed receipt is STALE for "
                        f"current content (receipt patch_id="
                        f"{(consumed.get('patch_id') or '')[:12]} != branch's current "
                        f"{cur_pid_for_receipt[:12]}) — NOT short-circuiting; falling "
                        f"through as if unlanded (confirmed root: land.py:121-122 / "
                        f"land.sh's identical consumed-receipt arm)")

    if _observe_landed(eng, branch, truth_ref):
        _consume_grant_administratively(eng, case_id)
        eng.log("flow", f"land[{case_id}] {scope}: observed landed -> consumed")
        return "landed"

    pid = gitobs.patch_id(eng.paths["root"], branch, truth_ref, eng.dry)
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
