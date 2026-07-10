"""land_paperwork_rig — L1 seam rig: architect close-out paperwork landing.

Isolates the bug behind a live HEAD SIM wedge: the architect's close-out paperwork
branch (`arch/<block>-forward`) lands through the ONE landing primitive
(`land.land_via_grant`, engine/land.py), keyed by a case-id derived PURELY from
role + branch name (fsm.py `_drain_landings`, ~line 3295):

    paperwork-architect-arch-<block>-forward

When the SAME branch is re-enqueued with NEW content (a later reconcile/forward
re-authors it — a different patch-id each time), the deterministic case-id
collides with the ALREADY-CONSUMED grant from the FIRST landing:

  - `land_via_grant` (land.py:121-122) checks `grants.read_consumed(case_id)`
    FIRST, before anything else, and short-circuits `"landed"` on a hit — never
    re-deriving the branch's CURRENT patch-id, never even looking at its content.
  - `land.sh` (line ~86) has the identical shape: `consumed/<case_id>.grant`
    exists -> "already consumed ... exit 0", checked BEFORE the live grant file
    or the branch's patch-id are read at all.

Net effect: the second (or Nth) re-authoring of the same-named paperwork branch
is reported LANDED — a `docs_landed` event fires — while its content never
reaches trunk. This is the root of the SIM's "awaiting land.sh" / unlanded-
paperwork session residue.

HARD RULE — real surface only. `engine/e2e_test.py` fakes `trunk.refresh`/
`trunk.open_prs` and therefore can never see this: the wedge lives in the real
grant/patch-id/land.sh interaction. This rig instead:
  - copies the REAL scaffold (`tron-meta/sims/_sources/trivial-tip-converter`,
    which ships a real `meta/scripts/land.sh` + `meta/tron/roles.yaml`) into a
    throwaway git repo (real `git init`, real commits, real branches);
  - drives the real `Engine` with `eng.dry = False` — every trunk/patch-id/
    is_ancestor/land read genuinely shells out to `git`;
  - runs `meta/scripts/land.sh` for real via `subprocess`, exactly the way the
    scripted worker would.

The ONE thing faked is the WORKER PROCESS: `jobs.spawn_runner` is stubbed to a
no-op so `eng.start(1)` doesn't launch a real `claude -p` architect subprocess
(fsm.py's `_spawn` still runs its full real bookkeeping path — mailbox write,
scratch dir, roster entry — only the actual OS process launch is skipped). The
rig itself plays that scripted worker: real git commits, real `land.sh` runs.
That is the ADR-0002 D2 protocol's "worker runs land.sh" step, stood in for
deterministically — never a fake trunk.

DO NOT FIX THE ENGINE. This rig's only job is to prove the RED on current HEAD.
"""
import os
import re
import sys
import json
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import util             # noqa: E402
import jobs              # noqa: E402
import trunk              # noqa: E402
import grants              # noqa: E402
from ctx import Ctx         # noqa: E402
from fsm import Engine       # noqa: E402

SCAFFOLD_SRC = "/home/anderson/42labs/tron/tron-meta/sims/_sources/trivial-tip-converter"
BRANCH = "arch/01-03-forward"          # matches the live SIM's own branch naming

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers ──
def _git(args, cwd, check=True):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}) rc={r.returncode}\n"
                           f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return r


def _git_out(args, cwd):
    return _git(args, cwd).stdout.strip()


def is_ancestor(root, sha, ref="main"):
    r = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", sha, ref])
    return r.returncode == 0


def build_root():
    """Copy the REAL scaffold into a throwaway tempdir and give it a fresh, real
    git history on `main`. Local no-remote mode structurally requires the ROOT
    checkout to stay DETACHED (ADR-0002 D1 / `trunk.root_head_detached` /
    `would_ff(require_detached=True)`) — an attached root fails every landing
    check with an UNRELATED "write-boundary violation" verdict that would drown
    out the actual wedge under test. So: detach immediately after the seed
    commit, and `make_paperwork_commit` below always re-detaches afterward
    (never leaves the root checked out on a branch, unlike the spec sketch's
    literal `git checkout main` — that's the one deliberate deviation from the
    spec's helper sketch, made to keep the RIG honest rather than the ENGINE)."""
    d = tempfile.mkdtemp(prefix="tron-landrig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", "main"], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "land-paperwork-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", "main"], root)
    return root


def build_inst(root):
    """The TRON instance dir, modeled on sentry_test.build(): canon copied from
    tron-app root, `roles.yaml` reused straight from the scaffold copy (already
    inside ROOT/meta/tron/roles.yaml — nothing bespoke needed), project.yaml
    pointed at ROOT as the real repo."""
    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    for f in ("routing.yaml", "messages.yaml", "knobs.yaml", "tron.md"):
        shutil.copy(os.path.join(APP_ROOT, f), os.path.join(inst, f))
    shutil.copytree(os.path.join(APP_ROOT, "prompts"), os.path.join(inst, "prompts"))
    util.save_yaml(os.path.join(inst, "project.yaml"), {
        "repo": {"root": root, "main_branch": "main", "remote": "none", "staging": "none"},
        "pipeline_path": "meta/pipeline.md",
        "roles_path": "meta/tron/roles.yaml",
    })
    util.atomic_write(os.path.join(inst, "manifest.yaml"), "{}\n")
    return Ctx(inst)


def make_paperwork_commit(root, branch, filename, content):
    """git checkout -B <branch> main -> write meta/<filename> -> add -> commit ->
    capture the tip -> re-detach the root back onto main. Returns the new tip sha."""
    _git(["checkout", "-B", branch, "main"], root)
    path = os.path.join(root, "meta", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"paperwork: add {filename}"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", "main"], root)
    return tip


def enqueue_paperwork(eng, branch):
    arch = eng._architect()
    arch.setdefault("pending_landings", []).append(branch)
    return arch


def run_land(root, ctx, case_id):
    r = subprocess.run(
        ["bash", os.path.join(root, "meta", "scripts", "land.sh"), case_id,
         "--main", "main", "--grants-dir", ctx.grants_dir],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "LAND_MAIN_BRANCH": "main"})
    return r.returncode, r.stdout, r.stderr


def events_of(ctx, type_, branch=None):
    out = []
    for e in util.read_jsonl(ctx.event_log):
        if e.get("type") != type_:
            continue
        if branch is not None and (e.get("payload") or {}).get("branch") != branch:
            continue
        out.append(e)
    return out


def main():
    root = build_root()
    ctx = build_inst(root)

    orig_spawn_runner = jobs.spawn_runner

    def fake_spawn_runner(worker_id, worker_dir, session_id, cwd=None, **kw):
        """The ONE thing faked (never the trunk): no real worker OS process — no
        `subprocess.Popen(... claude ...)`. `fsm._spawn` still runs its full real
        bookkeeping (mailbox write, scratch dir, roster entry) around this call;
        this stub only skips the actual process launch.

        It DOES write a real `runner.json` heartbeat, pid-pinned to THIS rig
        process (alive for the rig's whole lifetime) — omitting it left the
        persistent architect reading as "no runner state -> dead"
        (`jobs.is_alive`), which `fsm._sweep` (called every `eng.tick()`) then
        "restored" by silently REMOVING and RE-SPAWNING the architect worker
        record every single tick — wiping our just-enqueued `pending_landings`
        before `_drive_landings` ever saw it and producing an entirely FAKE
        green (nothing ever got queued, so nothing ever looked broken). That was
        a rig bug, not an engine fact — confirmed by the object-identity trace
        (the architect dict's `id()`/`session_id` changed across a single
        `eng.tick()` with no code path in this rig doing that itself)."""
        os.makedirs(worker_dir, exist_ok=True)
        state = {"worker_id": worker_id, "session_id": session_id, "pid": os.getpid(),
                 "state": "idle", "updated_at": util.now_iso(), "turns": 1}
        util.atomic_write(os.path.join(worker_dir, jobs.RUNNER_STATE), json.dumps(state))
        return {"session_id": session_id, "worker_id": worker_id}

    jobs.spawn_runner = fake_spawn_runner
    try:
        eng = Engine(ctx)
        eng.dry = False          # REAL trunk/patch-id/is_ancestor/land.sh observation.
        # worker_count=0: the persistent architect (spec_owner, cardinality:1, EXCLUDED
        # from the worker_count pool per knobs.yaml's own contract) still boots — but
        # the SWITCHBOARD's engineer/reviewer pool gets zero capacity, so it never
        # dispatches an engineer onto the (unrelated) dependency-chain block 01-02 that
        # the scaffold's own pipeline.md declares. That dispatch is real noise here: with
        # jobs.spawn_runner stubbed (no real carve), it synchronously wedges/escalates on
        # its own carve-bootstrap timeout and pollutes the run with an unrelated wall —
        # confirmed by first running this rig with start(1) and observing exactly that.
        # This isolates the ONE seam under test: the architect paperwork FIFO.
        eng.start(0)

        arch = eng._architect()
        ok("setup: architect worker is live on the roster after eng.start(1)",
           arch is not None and arch.get("role") == eng.roles.spec_owner
           and any(w is arch for w in eng.st.workers),
           f"arch={arch}")
        if arch is None:
            raise RuntimeError("no live architect worker — cannot proceed")

        clock = [1_700_000_000.0]
        eng._now_s = lambda: clock[0]
        eng.knobs["wake_ceiling_sec"] = 1     # small ceiling -> gate_close_cap
                                               # (knob default x3) = 3s, fast to exceed

        case_id = "paperwork-{}-{}".format(
            eng.roles.spec_owner, re.sub(r"[^A-Za-z0-9._-]", "-", BRANCH))
        ok("setup: derived case-id matches the SIM's own naming",
           case_id == "paperwork-architect-arch-01-03-forward", f"case_id={case_id}")

        # ══ Phase A — clean first land (baseline, must be GREEN) ══
        v1_tip = make_paperwork_commit(root, BRANCH, "paperwork-v1.md",
                                       "# paperwork v1\nforward close-out, first pass.\n")
        enqueue_paperwork(eng, BRANCH)
        eng.tick()
        g1 = grants.read_raw(ctx.grants_dir, case_id)
        p1 = trunk.patch_id(root, BRANCH, "main", False)
        ok("A1: engine minted a live grant for v1 with the correct patch-id",
           g1 is not None and g1.get("patch_id") == p1,
           f"grant={g1} expected_patch_id={p1}")

        rc_a, out_a, err_a = run_land(root, ctx, case_id)
        landed_v1 = is_ancestor(root, v1_tip, "main")
        ok("A2: land.sh lands v1 cleanly (rc==0, main CAS-advanced to contain v1's real tip)",
           rc_a == 0 and landed_v1,
           f"rc={rc_a} out={out_a!r} err={err_a!r} landed_v1={landed_v1}")

        eng.tick()
        arch_after_a = eng._architect()
        ok("A3: engine observes the real land -> pending_landings drains for v1",
           not (arch_after_a.get("pending_landings") or []),
           f"pending_landings={arch_after_a.get('pending_landings')}")

        docs_landed_after_a = events_of(ctx, "docs_landed", BRANCH)
        ok("A4: exactly one genuine docs_landed emitted for v1's real landing",
           len(docs_landed_after_a) == 1, f"events={docs_landed_after_a}")

        # ══ Phase B — re-enqueue the SAME branch with NEW content (the collision) ══
        v2_tip = make_paperwork_commit(root, BRANCH, "paperwork-v2.md",
                                       "# paperwork v2\na LATER reconcile/forward re-authors "
                                       "the SAME branch with different content.\n")
        p2 = trunk.patch_id(root, BRANCH, "main", False)
        ok("B setup: v2 is genuinely different content from v1 (different patch-id)",
           p2 != p1 and p2 != "", f"p1={p1} p2={p2}")
        ok("B setup: v2's tip is NOT yet an ancestor of main (nothing landed it yet)",
           not is_ancestor(root, v2_tip, "main"), f"v2_tip={v2_tip}")

        enqueue_paperwork(eng, BRANCH)
        eng.tick()

        # If the engine actually ordered a fresh land (it structurally can't once
        # read_consumed short-circuits it — captured either way), the scripted
        # worker plays its part and runs land.sh for the SAME case-id.
        rc_b, out_b, err_b = run_land(root, ctx, case_id)

        wedged = False
        for _ in range(20):
            arch_now = eng._architect()
            if BRANCH not in (arch_now.get("pending_landings") or []):
                break
            clock[0] += 2.0
            eng.tick()
            arch_now = eng._architect()
            if BRANCH in (arch_now.get("pending_landings") or []):
                run_land(root, ctx, case_id)
        else:
            wedged = BRANCH in (eng._architect().get("pending_landings") or [])
        clock[0] += 200.0   # push well past gate_close_cap regardless
        eng.tick()
        wedged = wedged or BRANCH in (eng._architect().get("pending_landings") or [])

        landed_v2 = is_ancestor(root, v2_tip, "main")
        main_tip = _git_out(["rev-parse", "main"], root)
        docs_landed_all = events_of(ctx, "docs_landed", BRANCH)
        arch_final = eng._architect()

        # ── I1 — no silent content loss ──
        ok("I1 (RED expected on HEAD): main actually contains v2's content "
           "(main is a real descendant of v2's tip)",
           landed_v2,
           f"v2_tip={v2_tip} main_tip={main_tip} landed_v2={landed_v2} "
           f"land.sh(2nd run) rc={rc_b} out={out_b!r} err={err_b!r}")

        # ── I2 — bounded convergence (captured either way: false-complete vs wedge) ──
        ok("I2 (captured, not asserted RED/GREEN a priori): bounded convergence — "
           "pending_landings empty and not stuck 'awaiting land.sh'",
           not (arch_final.get("pending_landings") or []) and not wedged,
           f"pending_landings={arch_final.get('pending_landings')} wedged={wedged}")

        # ── I3 — no false docs_landed ──
        false_docs_landed = len(docs_landed_all) > 1 and not landed_v2
        ok("I3 (RED expected on HEAD): the engine did not emit a second docs_landed "
           "for this branch unless v2 actually reached trunk",
           not false_docs_landed,
           f"docs_landed_events={docs_landed_all} landed_v2={landed_v2}")

    finally:
        jobs.spawn_runner = orig_spawn_runner

    passed = sum(1 for _, c, _ in _results if c)
    print(f"land_paperwork_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail and not c else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
