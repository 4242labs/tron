"""core.landing_rig — real-git GREEN rig proving `core.landing`'s content-bound
case-id fix actually lands v2 on trunk: the exact collision
`engine/land_paperwork_rig.py` forensically confirms RED on the old
`engine/land.py` path (same-named branch, re-authored content, deterministic
role+branch case-id -> stale consumed receipt short-circuits "landed" while
v2 never reaches trunk).

REAL surface only, exactly like the diagnostic rig it's modeled on:
  - a real `git init` repo copied from the SAME scaffold
    (`tron-meta/sims/_sources/trivial-tip-converter`, real `meta/scripts/land.sh`);
  - `meta/scripts/land.sh` run for real via `subprocess` — never faked, never
    monkeypatched;
  - a minimal duck-typed `eng` context, `eng.dry = False` throughout, backed
    by the REAL `grants.py`/`trunk.py` + a real grants dir on disk.

This rig does NOT boot the full `Engine` (only `core.landing`'s own
primitive needs driving, per the wave-1 spec) — the duck-typed `MiniEng`
below supplies exactly the attributes `core/landing.py` touches: `.paths`,
`.dry`, `.ctx.grants_dir`, `.events`, `.log`, `._truth_ref()`,
`._to_worker`, `._grant_ttl()`. The ONE thing this rig plays instead of a
real OS process is the WORKER itself — same convention as
`engine/land_paperwork_rig.py`'s `jobs.spawn_runner` stub: the rig, having
been "ordered" by the primitive, runs the real `land.sh` itself. The trunk
is never faked.
"""
import os
import sys
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # grants.py / trunk.py live here
sys.path.insert(0, HERE)                                 # core/landing.py itself

import grants     # noqa: E402 — respected contract, real, unmodified
import trunk       # noqa: E402 — respected contract, real, unmodified
import landing       # noqa: E402 — core/landing.py, the module under test

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
BRANCH = "arch/01-03-forward"     # same branch naming the diagnostic rig / live SIM use
ROLE = "architect"
BLOCK = "01-03"
MAIN = "main"
WID = "architect-worker"

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers (identical convention to engine/land_paperwork_rig.py) ──
def _git(args, cwd, check=True):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}) rc={r.returncode}\n"
                           f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return r


def _git_out(args, cwd):
    return _git(args, cwd).stdout.strip()


def is_ancestor(root, sha, ref=MAIN):
    r = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", sha, ref])
    return r.returncode == 0


def build_root():
    """Copy the REAL scaffold into a throwaway tempdir with a fresh, real git
    history on `main`, then detach — local no-remote mode requires the root
    checkout stay DETACHED (ADR-0002 D1) so `land.sh`'s own `update-ref`
    never races a working-tree checkout. Same shape as
    `engine/land_paperwork_rig.py::build_root`."""
    d = tempfile.mkdtemp(prefix="tron-core-landrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-landing-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


def make_paperwork_commit(root, branch, filename, content):
    """`git checkout -B <branch> main` -> write `meta/<filename>` -> commit ->
    capture tip -> re-detach root back onto main. Returns the new tip sha.
    Re-using this for BOTH v1 and v2 (same branch name) is exactly the
    collision scenario under test: v2 is built fresh off CURRENT main (which,
    by Phase B, already contains v1), so it is a real, ff-able, genuinely
    NEW-content branch — not a hand-edited fixture."""
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, "meta", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"paperwork: add {filename}"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def run_land(root, grants_dir, case_id):
    """Run the REAL `meta/scripts/land.sh` via subprocess — exactly the way
    the scripted worker (this rig, standing in for one) would, per the
    ADR-0002 D2 protocol."""
    r = subprocess.run(
        ["bash", os.path.join(root, "meta", "scripts", "land.sh"), case_id,
         "--main", MAIN, "--grants-dir", grants_dir],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "LAND_MAIN_BRANCH": MAIN})
    return r.returncode, r.stdout, r.stderr


class _Events:
    """Tiny real-enough events stub — `core.landing` only ever calls
    `.event(type_, **payload)` on it (never reads it back)."""
    def __init__(self):
        self.log = []

    def event(self, type_, **payload):
        self.log.append({"type": type_, "payload": payload})


class _Ctx:
    def __init__(self, grants_dir):
        self.grants_dir = grants_dir


class MiniEng:
    """The minimal duck-typed `eng` `core.landing.land_via_grant` needs — NOT
    the full `Engine` (this rig proves the PRIMITIVE, per the wave-1 spec).
    `.paths["root"]` / `._truth_ref()` are real, git-backed; `.ctx.grants_dir`
    is a real on-disk grants folder written through the real `grants.py`.
    The ONLY stub is `_to_worker` — there is no real worker OS process in
    this rig; the rig plays that role itself (real `land.sh` runs), same
    convention as `engine/land_paperwork_rig.py`'s `jobs.spawn_runner` stub."""
    def __init__(self, root, grants_dir):
        self.paths = {"root": root}
        self.dry = False                 # HARD RULE: real trunk observation throughout
        self.ctx = _Ctx(grants_dir)
        self.events = _Events()
        self.log_lines = []
        self.orders = []

    def log(self, channel, msg):
        self.log_lines.append((channel, msg))

    def _truth_ref(self):
        return MAIN

    def _to_worker(self, wid, msg, kind):
        self.orders.append((wid, msg, kind))

    def _grant_ttl(self):
        return 60


def main():
    root = build_root()
    grants_dir = os.path.join(root, "meta", "agents", "tron", "grants")
    eng = MiniEng(root, grants_dir)
    real_landings = 0     # count of REAL main-advancing land.sh runs (I3 regression check)

    # ══ Phase A — clean first land (baseline, must be GREEN) ══
    v1_tip = make_paperwork_commit(root, BRANCH, "paperwork-v1.md",
                                    "# paperwork v1\nforward close-out, first pass.\n")
    p1 = trunk.patch_id(root, BRANCH, MAIN, False)
    case_id_a = landing.paperwork_case_id(ROLE, BRANCH, p1)
    ok("A0: paperwork_case_id derives a CONTENT-BOUND case-id (embeds p1's suffix, "
       "differs from the OLD role+branch-only naming)",
       case_id_a.endswith(p1[:12]) and case_id_a != f"paperwork-{ROLE}-{BRANCH}",
       f"case_id_a={case_id_a} p1={p1}")

    orders0 = len(eng.orders)
    res_a1 = landing.land_via_grant(eng, case_id_a, BLOCK, BRANCH, WID, "gate.land", "phase-a")
    ok("A1: primitive mints a fresh grant + orders the worker on first drive (pending)",
       res_a1 == "pending" and len(eng.orders) - orders0 == 1,
       f"res={res_a1} orders_delta={len(eng.orders) - orders0}")

    main_before_a = _git_out(["rev-parse", MAIN], root)
    rc_a, out_a, err_a = run_land(root, grants_dir, case_id_a)
    main_after_a = _git_out(["rev-parse", MAIN], root)
    if main_after_a != main_before_a:
        real_landings += 1
    landed_v1 = is_ancestor(root, v1_tip, MAIN)
    ok("A2: land.sh lands v1 for real (rc==0, main CAS-advanced to v1's real tip)",
       rc_a == 0 and landed_v1 and main_after_a == v1_tip,
       f"rc={rc_a} out={out_a!r} err={err_a!r} landed_v1={landed_v1} "
       f"main_after={main_after_a} v1_tip={v1_tip}")

    res_a2 = landing.land_via_grant(eng, case_id_a, BLOCK, BRANCH, WID, "gate.land", "phase-a-observe")
    ok("A3: primitive observes the real land -> returns landed",
       res_a2 == "landed", f"res={res_a2}")

    # ══ Phase B — THE KILLER: SAME branch re-created with NEW content v2 ══
    v2_tip = make_paperwork_commit(root, BRANCH, "paperwork-v2.md",
                                    "# paperwork v2\na LATER reconcile/forward re-authors "
                                    "the SAME branch with different content.\n")
    p2 = trunk.patch_id(root, BRANCH, MAIN, False)
    ok("B setup: v2 is genuinely different content from v1 (different patch-id)",
       p2 != p1 and p2 != "", f"p1={p1} p2={p2}")
    ok("B setup: v2's tip is NOT yet an ancestor of main (nothing landed it yet)",
       not is_ancestor(root, v2_tip, MAIN), f"v2_tip={v2_tip}")

    case_id_b = landing.paperwork_case_id(ROLE, BRANCH, p2)
    ok("B0: v2's case-id DIFFERS from v1's (content-bound identity — the actual fix: "
       "new content structurally cannot collide with the old consumed receipt)",
       case_id_b != case_id_a, f"case_id_a={case_id_a} case_id_b={case_id_b}")

    # Defensive-invariant probe (module docstring layer 2, land_via_grant's belt-
    # and-suspenders): drive the primitive with the OLD, collision-prone case-id
    # (case_id_a) — which has a REAL consumed receipt on file bound to p1 — against
    # the branch's CURRENT content (now p2). This recreates, live, exactly the
    # original bug's precondition (a case-id whose consumed receipt is stale for
    # current content). The fix must NOT short-circuit "landed" on it.
    orders_probe0 = len(eng.orders)
    res_stale = landing.land_via_grant(eng, case_id_a, BLOCK, BRANCH, WID, "gate.land",
                                       "phase-b-stale-receipt-probe")
    ok("B1 (defensive-invariant probe, AC in spec item 1): case_id_a's consumed "
       "receipt (patch_id=p1) is STALE for the branch's current content (p2) — the "
       "primitive does NOT trust it and does NOT short-circuit 'landed'; it falls "
       "through to mint/order for the real content instead",
       res_stale != "landed" and len(eng.orders) - orders_probe0 == 1,
       f"res_stale={res_stale} orders_delta={len(eng.orders) - orders_probe0}")
    ok("B1b: the stale-receipt probe did NOT cause anything to actually land "
       "(main still v1-only — v2's tip still not an ancestor)",
       not is_ancestor(root, v2_tip, MAIN), f"v2_tip={v2_tip}")

    orders_b0 = len(eng.orders)
    res_b1 = landing.land_via_grant(eng, case_id_b, BLOCK, BRANCH, WID, "gate.land", "phase-b")
    ok("B2: primitive mints a FRESH grant + orders the worker under v2's new, "
       "content-bound case-id",
       res_b1 == "pending" and len(eng.orders) - orders_b0 == 1,
       f"res={res_b1} orders_delta={len(eng.orders) - orders_b0}")

    main_before_b = _git_out(["rev-parse", MAIN], root)
    rc_b, out_b, err_b = run_land(root, grants_dir, case_id_b)
    main_after_b = _git_out(["rev-parse", MAIN], root)
    if main_after_b != main_before_b:
        real_landings += 1
    landed_v2 = is_ancestor(root, v2_tip, MAIN)
    ok("B3 (THE KILLER — must be GREEN): main NOW CONTAINS v2 — the REAL land.sh "
       "actually advanced trunk to v2's tip "
       "(git merge-base --is-ancestor v2_tip main == TRUE)",
       rc_b == 0 and landed_v2 and main_after_b == v2_tip,
       f"rc={rc_b} out={out_b!r} err={err_b!r} landed_v2={landed_v2} "
       f"main_after={main_after_b} v2_tip={v2_tip}")

    res_b2 = landing.land_via_grant(eng, case_id_b, BLOCK, BRANCH, WID, "gate.land", "phase-b-observe")
    ok("B4: primitive observes v2's real land -> returns landed",
       res_b2 == "landed", f"res={res_b2}")

    # ══ Phase C — idempotency: drive AGAIN for v2's SAME content/case-id ══
    orders_c0 = len(eng.orders)
    res_c1 = landing.land_via_grant(eng, case_id_b, BLOCK, BRANCH, WID, "gate.land", "phase-c")
    ok("C1: re-driving the primitive for v2's already-consumed case-id is a correct "
       "no-op (landed, no new grant minted, no new worker order)",
       res_c1 == "landed" and len(eng.orders) - orders_c0 == 0,
       f"res={res_c1} orders_delta={len(eng.orders) - orders_c0}")

    main_before_c = _git_out(["rev-parse", MAIN], root)
    rc_c, out_c, err_c = run_land(root, grants_dir, case_id_b)
    main_after_c = _git_out(["rev-parse", MAIN], root)
    if main_after_c != main_before_c:
        real_landings += 1
    ok("C2: re-running land.sh for v2's case-id is a correct no-op (rc==0, "
       "'already consumed', main UNCHANGED, no double-advance, no error)",
       rc_c == 0 and main_after_c == main_before_c and "already consumed" in (out_c or ""),
       f"rc={rc_c} out={out_c!r} err={err_c!r} "
       f"main_before={main_before_c} main_after={main_after_c}")

    # ── I3 regression: real (main-advancing) landings == distinct content versions (2) ──
    ok("I3 (regression, cf. engine/land_paperwork_rig.py's I3): the number of REAL, "
       "main-advancing land.sh runs equals the number of distinct content versions "
       "(2: v1 once, v2 once) — the v2 re-run in Phase C was a genuine no-op, never "
       "a false extra advance",
       real_landings == 2, f"real_landings={real_landings}")

    final_main = _git_out(["rev-parse", MAIN], root)
    ok("final: main's tip == v2's tip (the fix's whole point: v2 genuinely, "
       "verifiably reached trunk through the real land.sh)",
       final_main == v2_tip, f"final_main={final_main} v2_tip={v2_tip}")

    # ══ stage_case_id — the ONE per-stage case-id resolver (T2-17 single-source
    #    lock, shared by all six land_via_grant callers). Pure function, no git. ══
    P1 = "1111111111111111111111111111111111111111"   # patch-id shape
    P2 = "2222222222222222222222222222222222222222"
    id_p1 = landing.paperwork_case_id("close", "feat/x", P1)
    id_p2 = landing.paperwork_case_id("close", "feat/x", P2)
    ok("S1 (T2-17 KILLER — must be GREEN): with a resolvable patch-id, stage_case_id "
       "content-binds to the CURRENT patch-id and IGNORES a stale `prev` — a "
       "re-authored branch (new patch-id) NEVER reuses the cached, already-consumed "
       "id (the exact defect: an unconditional `prev or ...` cache returned the stale "
       "id and land.sh no-op'd the new commit)",
       landing.stage_case_id(id_p1, "close", "feat/x", P2) == id_p2 and id_p1 != id_p2,
       f"prev={id_p1} got={landing.stage_case_id(id_p1, 'close', 'feat/x', P2)} want={id_p2}")
    ok("S2: with the SAME patch-id (a pure rebase — same diff), stage_case_id returns "
       "the SAME id, stable across churn (no second grant)",
       landing.stage_case_id(id_p1, "close", "feat/x", P1) == id_p1,
       f"got={landing.stage_case_id(id_p1, 'close', 'feat/x', P1)} want={id_p1}")
    ok("S3: a momentarily UNRESOLVABLE patch-id ('' — fully-landed empty diff / "
       "mid-churn read) KEEPS the last-good `prev` id rather than overwrite it with a "
       "malformed empty-suffix id (this is why unconditional recompute broke the "
       "churn rigs)",
       landing.stage_case_id(id_p1, "close", "feat/x", "") == id_p1,
       f"got={landing.stage_case_id(id_p1, 'close', 'feat/x', '')} want={id_p1}")
    ok("S4: '' patch-id with NO prev falls back to the (fail-closed-downstream) "
       "empty-suffix id — grants.mint refuses it, never a false pass",
       landing.stage_case_id(None, "close", "feat/x", "") == landing.paperwork_case_id(
           "close", "feat/x", ""),
       f"got={landing.stage_case_id(None, 'close', 'feat/x', '')}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.landing_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"v1_tip={v1_tip}")
    print(f"v2_tip={v2_tip}")
    print(f"main tip (final)={final_main}")
    print(f"ancestor-check: git -C {root} merge-base --is-ancestor {v2_tip} {MAIN} "
          f"-> {'TRUE' if is_ancestor(root, v2_tip, MAIN) else 'FALSE'}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
