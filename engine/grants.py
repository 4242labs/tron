"""grants — T3 (01-32, ADR-0002 D2): the merge/close path's authorize layer.

On gate approval TRON mints a one-time, block-scoped grant *in its own folder*
(`meta/agents/tron/grants/<case-id>.grant`) — never a project write. A grant binds a
case to a branch's CONTENT (`git patch-id --stable` over the branch's diff against
trunk, computed by the caller via `trunk.patch_id`) rather than to a commit sha: a
pure rebase (same diff, new tip) keeps the grant valid; a content-changing rebase
gets a different patch-id, the grant no longer matches, and the gate re-asks (AC-5).

**Fail-closed rider (stated in the ADR verbatim):** an empty/unresolvable patch-id
(`""`) is UNMINTABLE (`mint` refuses outright, returns None) and a `""` comparison is
ALWAYS a non-match (`matches` below) — a grant can never be minted or satisfied on
content nobody could verify.

File format: a flat `key=value` text file, one pair per line — deliberately NOT
JSON, so `land.sh` (a plain POSIX shell script with no `python3`/`jq` dependency
guaranteed on every project) and this module read/write the exact same artifact
with nothing fancier than `grep`/`cut`. Fields: `case`, `block`, `branch`,
`patch_id`, `minted_at` (unix epoch, float seconds), `ttl_min`; a consumed grant
additionally carries `consumed_at` and `result`.

Crash-safety (ADR-0002 D2, "merge-then-consume ordering"): `mint` writes the LIVE
grant; the land script (or, administratively, `consume` here) renames it into
`consumed/<case-id>.grant` with a receipt AFTER the ref has actually advanced —
never before. Every write in this module lands under TRON's own folder-absolute
writable surface (P3) — nothing here ever touches the project's git state.
"""
import os
import re
import time

# land.sh's own safe-token guard, mirrored: a case id that the landing script
# would refuse must never mint (a live-but-unlandable grant wedges the lane —
# the 260708 reset-wave-1c/2c architect-paperwork wedge). Same alphabet as
# land.sh's pre-interpolation validation.
CASE_ID_TOKEN = re.compile(r"^[A-Za-z0-9._-]+$")

_LIVE_SUFFIX = ".grant"


def _kv_path(grants_dir, case_id, consumed=False):
    base = os.path.join(grants_dir, "consumed") if consumed else grants_dir
    return os.path.join(base, f"{case_id}{_LIVE_SUFFIX}")


def grant_path(grants_dir, case_id):
    """Public seam `land.sh`'s own docs/tests reference: where a LIVE grant for
    `case_id` lives (whether or not one currently exists there)."""
    return _kv_path(grants_dir, case_id)


def consumed_path(grants_dir, case_id):
    return _kv_path(grants_dir, case_id, consumed=True)


def _write_kv(path, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for k, v in fields.items():
            f.write(f"{k}={v}\n")
    os.replace(tmp, path)   # atomic within the same filesystem — TRON's own folder


def _read_kv(path):
    if not os.path.exists(path):
        return None
    out = {}
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k] = v
    return out


def mint(grants_dir, case_id, block, branch, patch_id, ttl_min=60, now=None):
    """Mint a LIVE grant for `case_id` — fail-closed: an empty/unresolvable
    `patch_id` is never minted (returns None, no file written, no exception —
    same best-effort discipline as every other fail-closed read in this codebase).
    Overwrites any prior live grant for the same case_id (a fresh mint after a
    content-changing rebase IS a new grant for the same case — the old one's
    patch-id no longer describes the branch anyway). Returns the grant dict minted,
    or None on the fail-closed refusal. A case id outside land.sh's safe-token
    alphabet also refuses (None) — minting it would create a live grant the
    landing script structurally cannot consume."""
    if not patch_id or not case_id or not CASE_ID_TOKEN.match(case_id):
        return None
    now = now if now is not None else time.time()
    fields = {"case": case_id, "block": block or "", "branch": branch or "",
              "patch_id": patch_id, "minted_at": f"{now:.3f}",
              "ttl_min": str(ttl_min)}
    _write_kv(grant_path(grants_dir, case_id), fields)
    return fields


def read_raw(grants_dir, case_id):
    """The live grant file's fields, whether or not it's expired — None if absent."""
    return _read_kv(grant_path(grants_dir, case_id))


def is_expired(grant, now=None):
    """True iff `grant`'s wall-clock TTL has elapsed. A malformed/unreadable
    minted_at or ttl_min reads as expired (fail-closed — never treat a corrupt
    grant as eternally live)."""
    if not grant:
        return True
    now = now if now is not None else time.time()
    try:
        minted = float(grant.get("minted_at", "0"))
        ttl = float(grant.get("ttl_min", "60"))
    except (TypeError, ValueError):
        return True
    return (now - minted) > (ttl * 60.0)


def read_live(grants_dir, case_id, now=None):
    """The LIVE grant for `case_id`, or None if absent OR expired (expiry is a
    read-time judgment, never mutates the file — callers that need to ACT on an
    expiry call `read_raw` + `is_expired` themselves, e.g. to log a loud re-open
    before anything removes the stale file)."""
    g = _read_kv(grant_path(grants_dir, case_id))
    if not g or is_expired(g, now):
        return None
    return g


def read_consumed(grants_dir, case_id):
    """The receipt for an already-consumed grant, or None — the "already landed,
    receipt on file" half of the already-landed idempotent-retry arm (ADR-0002 D2)."""
    return _read_kv(consumed_path(grants_dir, case_id))


def list_live(grants_dir, now=None):
    """Every currently-LIVE grant, {case_id: fields} — expired ones excluded (same
    read-time judgment as `read_live`, never a mutation). Empty dict on a missing
    dir (nothing minted yet is an ordinary state, never an error)."""
    out = {}
    if not os.path.isdir(grants_dir):
        return out
    for name in os.listdir(grants_dir):
        if not name.endswith(_LIVE_SUFFIX):
            continue
        case_id = name[:-len(_LIVE_SUFFIX)]
        g = read_live(grants_dir, case_id, now)
        if g:
            out[case_id] = g
    return out


def matches(grant, patch_id):
    """Fail-closed content-identity compare: `""` never matches anything, not even
    another `""` — an unresolvable patch-id is never a free pass, on either side."""
    if not grant or not patch_id:
        return False
    return grant.get("patch_id") == patch_id


def consume(grants_dir, case_id, result="landed", extra=None, now=None):
    """Consume a live grant: rename it into `consumed/<case-id>.grant` with a
    result receipt stamped on. Idempotent by construction — if `case_id` is
    ALREADY consumed, returns the existing receipt untouched (never double-writes,
    never raises on a retry — the already-landed arm's "already consumed with a
    receipt on file" shape, ADR-0002 D2). Returns None only when there was never a
    live grant AND no receipt exists either (nothing to consume, nothing consumed
    — the caller's own fail-closed/violation path, never silently treated as ok)."""
    receipt = read_consumed(grants_dir, case_id)
    if receipt:
        return receipt
    g = read_raw(grants_dir, case_id)          # raw, not read_live: an EXPIRED grant is
    if not g:                                  # still consumable administratively (the
        return None                            # crash-window arm below fires post-advance,
    now = now if now is not None else time.time()
    g["consumed_at"] = f"{now:.3f}"
    g["result"] = result
    for k, v in (extra or {}).items():
        g[str(k)] = str(v)
    _write_kv(consumed_path(grants_dir, case_id), g)
    try:
        os.remove(grant_path(grants_dir, case_id))
    except OSError:
        pass
    return g
