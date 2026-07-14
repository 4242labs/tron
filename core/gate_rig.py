"""core.gate_rig — real-git, no-LLM rig proving `core.gate`'s record -> close
DONE-ladder TAIL reaches a genuine CLEAN CLOSE on the REAL surface: a real
`git init` repo copied from the same scaffold `core/landing_rig.py` uses,
`meta/scripts/land.sh` run for real via `subprocess`, and a minimal
duck-typed `eng` — never a faked/monkeypatched trunk.

Two scenarios:

  Phase A (happy path) — block `gate-01`, worker branch `feat/gate-01`.
  The rig plays the worker: seeds the block doc (Status 🔄) on `main`, then
  makes the record commit (Status 🔄 -> ✅, exactly that one file/field) on
  the branch. Drives `core.gate.advance` in a loop: record-diff check
  passes, a content-bound grant lands the ✅ on trunk for real (asserted via
  `git rev-parse main` advancing to the record commit's own sha), then the
  rig tears down (real `git branch -D`) and close drives to a genuine clean
  close — replica verified clean on real git, worker slot released.

  Phase B (adversarial) — block `gate-02`, worker branch `feat/gate-02`.
  The rig plays a MISBEHAVING worker: the "record" commit touches the block
  doc's Status field AND a second, unrelated file in the SAME commit.
  `core.gate.advance` must return `("escalate", ...)` and must NOT call the
  landing primitive at all — asserted by `main`'s tip staying byte-for-byte
  unchanged (git rev-parse) across the drive.

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.
"""
import os
import sys
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))   # grants.py / trunk.py live here
sys.path.insert(0, HERE)                                 # core/gate.py, core/landing.py

import grants     # noqa: E402 — respected contract, real, unmodified
import trunk      # noqa: E402 — respected contract, real, unmodified
import gate       # noqa: E402 — core/gate.py, the module under test

import scaffold_src               # noqa: E402 — core/scaffold_src.py, the ONE resolver

SCAFFOLD_SRC = scaffold_src.resolve()
MAIN = "main"

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


# ── real git helpers (same convention as core/landing_rig.py) ──
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
    history on `main`, then detach (local no-remote mode keeps the root
    checkout DETACHED, ADR-0002 D1, so `land.sh`'s own `update-ref` never
    races a working-tree checkout). Same shape as `core/landing_rig.py`."""
    d = tempfile.mkdtemp(prefix="tron-core-gaterig-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-gate-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)
    _git(["checkout", "--detach", MAIN], root)
    return root


BLOCK_DOC_TEMPLATE = """# Block {block}: gate_rig fixture

**Phase:** 1 — Gate rig
**Status:** {status}
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-10

---

## Context

Synthetic block doc for `core.gate_rig` — proves the record -> close
DONE-ladder tail reaches a genuine clean close on real git + real land.sh.
"""


def seed_block_doc(root, block, block_file_rel):
    """Commit the block doc onto `main` for real (Status 🔄) — the baseline
    every worker branch forks from. Returns the block file's repo path."""
    _git(["checkout", "-B", MAIN, MAIN], root)
    path = os.path.join(root, block_file_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(BLOCK_DOC_TEMPLATE.format(block=block, status="🔄 In progress"))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"seed: block {block} (in progress)"], root)
    _git(["checkout", "--detach", MAIN], root)
    return block_file_rel


def make_record_commit(root, branch, block_file_rel):
    """Rig-as-worker: fork `branch` off current `main`, flip the block
    doc's Status field 🔄 -> ✅ — exactly that one file, exactly that one
    field — commit, capture the tip, re-detach root back onto main."""
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, block_file_rel)
    with open(path) as f:
        content = f.read()
    new_content = content.replace("**Status:** 🔄 In progress", "**Status:** ✅ Done")
    assert new_content != content, "seed status line not found — fixture drift"
    with open(path, "w") as f:
        f.write(new_content)
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"record: {branch} done"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def make_adversarial_record_commit(root, branch, block_file_rel, extra_rel):
    """Rig-as-MISBEHAVING-worker: the same Status flip, but the SAME commit
    also touches a second, unrelated file — the out-of-gate change
    `record_commit_ok` (and therefore `gate.record`) must reject."""
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, block_file_rel)
    with open(path) as f:
        content = f.read()
    new_content = content.replace("**Status:** 🔄 In progress", "**Status:** ✅ Done")
    assert new_content != content, "seed status line not found — fixture drift"
    with open(path, "w") as f:
        f.write(new_content)
    extra_path = os.path.join(root, extra_rel)
    os.makedirs(os.path.dirname(extra_path), exist_ok=True)
    with open(extra_path, "w") as f:
        f.write("# stray file\nan out-of-gate change riding along with the record flip.\n")
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"record: {branch} done (plus a stray file — BAD)"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def run_land(root, grants_dir, case_id):
    """Run the REAL `meta/scripts/land.sh` via subprocess — the rig playing
    the worker ordered to land its own grant, per ADR-0002 D2."""
    r = subprocess.run(
        ["bash", os.path.join(root, "meta", "scripts", "land.sh"), case_id,
         "--main", MAIN, "--grants-dir", grants_dir],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "LAND_MAIN_BRANCH": MAIN})
    return r.returncode, r.stdout, r.stderr


class _Events:
    def __init__(self):
        self.log = []

    def event(self, type_, **payload):
        self.log.append({"type": type_, "payload": payload})


class _Ctx:
    def __init__(self, grants_dir):
        self.grants_dir = grants_dir


class MiniEng:
    """The minimal duck-typed `eng` — everything `core/landing.py` needs
    PLUS `_release_worker` (the one addition `core/gate.py` documents).
    `.workers` is a plain dict this rig owns and asserts against; `gate.py`
    never reads it directly, only ever calls `_release_worker`."""
    def __init__(self, root, grants_dir):
        self.paths = {"root": root, "main_branch": MAIN}
        self.dry = False                 # HARD RULE: real trunk observation throughout
        self.ctx = _Ctx(grants_dir)
        self.events = _Events()
        self.log_lines = []
        self.orders = []
        self.workers = {}                # wid -> {"block":..., "status": "assigned"|"released"}

    def log(self, channel, msg):
        self.log_lines.append((channel, msg))

    def _truth_ref(self):
        return MAIN

    def _to_worker(self, wid, msg, kind):
        self.orders.append((wid, msg, kind))

    def emit(self, template_id, fallback_text, slots=None, worker_id=None, kind=None):
        # Rig fixture: no canon shipped (no messages.yaml/prompts/ on this
        # scaffold), so this mirrors core.engine.Engine.emit's FALLBACK arm
        # unconditionally — fallback_text verbatim, delivered the same way
        # _to_worker always was, so every existing rig assertion on
        # self.orders stays byte-for-byte identical.
        line = fallback_text
        if worker_id and not self.dry:
            self._to_worker(worker_id, line, kind or template_id)
        return line

    def _grant_ttl(self):
        return 60

    def _release_worker(self, wid, reason="released"):
        self.workers[wid] = {**self.workers.get(wid, {}), "status": "released", "reason": reason}


def drive_until(eng, block, gate_state, stop_outcomes, root, grants_dir, teardown_branch=None,
                max_iters=25):
    """The rig's tick-loop stand-in: repeatedly call `gate.advance`, playing
    the worker's real-OS-process actions on the outcomes that require one —
    `record_pending` -> run the REAL land.sh; `close_ordered` -> tear down
    the branch for real. Returns the full (outcome, detail) history."""
    history = []
    torn_down = False
    for _ in range(max_iters):
        outcome, detail = gate.advance(eng, block, gate_state)
        history.append((outcome, detail))
        if outcome == "record_pending":
            case_id = gate_state["record_case_id"]
            rc, out, err = run_land(root, grants_dir, case_id)
            history.append(("land.sh", f"rc={rc} out={out!r} err={err!r}"))
            continue
        if outcome == "close_ordered" and teardown_branch and not torn_down:
            _git(["branch", "-D", teardown_branch], root)
            history.append(("teardown", f"deleted branch {teardown_branch}"))
            torn_down = True
            continue
        if outcome in stop_outcomes:
            break
    return history


def main():
    root = build_root()
    grants_dir = os.path.join(root, "meta", "agents", "tron", "grants")
    eng = MiniEng(root, grants_dir)

    # ══ Phase A — happy path: record -> close -> genuine clean close ══
    BLOCK_A, BRANCH_A, WID_A = "gate-01", "feat/gate-01", "worker-gate-01"
    block_file_a = seed_block_doc(root, BLOCK_A, "meta/blocks/gate-01.md")
    eng.workers[WID_A] = {"block": BLOCK_A, "status": "assigned"}

    gstate_a = gate.new_state(eng, BLOCK_A, block_file_a, BRANCH_A, WID_A)
    record_tip_a = make_record_commit(root, BRANCH_A, block_file_a)
    ok("A0: rig-as-worker made a real record commit on the branch, off trunk",
       bool(record_tip_a) and not is_ancestor(root, record_tip_a, MAIN),
       f"record_tip_a={record_tip_a}")

    main_before_record = _git_out(["rev-parse", MAIN], root)
    history_a = drive_until(eng, BLOCK_A, gstate_a, {"record_landed"}, root, grants_dir,
                            max_iters=10)
    outcomes_a = [o for o, _ in history_a]

    ok("A1: gate.record's content check PASSES (real git: record commit is exactly "
       "one file, exactly the Status field) — no escalate anywhere in the drive",
       "escalate" not in outcomes_a, f"outcomes={outcomes_a}")

    ok("A2: a CONTENT-BOUND case-id was minted (embeds the branch's patch-id — the "
       "Wave-1 confirmed root, a name-only case-id, is structurally unreachable here)",
       bool(gstate_a.get("record_case_id"))
       and gstate_a["record_case_id"] != f"paperwork-record-{BRANCH_A}"
       and gstate_a["record_case_id"].startswith("paperwork-record-"),
       f"case_id={gstate_a.get('record_case_id')}")

    consumed_a = grants.read_consumed(grants_dir, gstate_a["record_case_id"])
    ok("A3: the grant was actually consumed on disk (a real receipt from a real land.sh run)",
       bool(consumed_a), f"consumed={consumed_a}")

    main_after_record = _git_out(["rev-parse", MAIN], root)
    landed_record = is_ancestor(root, record_tip_a, MAIN)
    ok("A4 (THE KILLER — must be GREEN): ✅ GENUINELY lands on trunk — real land.sh "
       "CAS-advanced main to the record commit's own real sha "
       "(git rev-parse main == record commit sha, merge-base --is-ancestor == TRUE)",
       landed_record and main_after_record == record_tip_a
       and main_after_record != main_before_record,
       f"main_before={main_before_record} main_after={main_after_record} "
       f"record_tip_a={record_tip_a} landed={landed_record}")

    doc_on_main = _git_out(["show", f"{MAIN}:{block_file_a}"], root)
    ok("A5: the block doc AS READ FROM main shows ✅ (real git show on trunk, never "
       "a working-tree read)",
       "**Status:** ✅ Done" in doc_on_main, f"doc_on_main head={doc_on_main.splitlines()[:4]}")

    ok("A6: gate_state advanced to the close stage", gstate_a["stage"] == gate.STAGE_CLOSE,
       f"stage={gstate_a['stage']}")

    history_a2 = drive_until(eng, BLOCK_A, gstate_a, {"closed", "escalate"}, root, grants_dir,
                             teardown_branch=BRANCH_A, max_iters=10)
    outcomes_a2 = [o for o, _ in history_a2]

    ok("A7: close drove to a genuine terminal (no escalate, real teardown happened)",
       "closed" in outcomes_a2 and "teardown" in outcomes_a2 and "escalate" not in outcomes_a2,
       f"outcomes={outcomes_a2}")

    branch_gone = not trunk.branch_exists(root, BRANCH_A, False)
    clean_now, clean_detail = trunk.replica_clean(root, BRANCH_A, MAIN, False)
    ok("A8: gate.py verified the replica clean on REAL git (branch deleted, no "
       "worktree on it) before releasing anything",
       branch_gone and clean_now, f"branch_gone={branch_gone} clean={clean_now} "
       f"detail={clean_detail}")

    ok("A9 (THE OTHER KILLER — must be GREEN): the worker slot was REALLY released "
       "(eng._release_worker was called, never a silent trust-release)",
       eng.workers.get(WID_A, {}).get("status") == "released",
       f"worker_state={eng.workers.get(WID_A)}")

    ok("A10: terminal — block on trunk shows ✅, slot freed, gate_state == closed "
       "(a genuine clean close, the tail the engine has never reached)",
       gstate_a["stage"] == gate.STAGE_CLOSED
       and eng.workers.get(WID_A, {}).get("status") == "released"
       and "**Status:** ✅ Done" in _git_out(["show", f"{MAIN}:{block_file_a}"], root),
       f"gate_stage={gstate_a['stage']} worker={eng.workers.get(WID_A)}")

    # ══ Phase B — adversarial: a second-file record commit must ESCALATE ══
    BLOCK_B, BRANCH_B, WID_B = "gate-02", "feat/gate-02", "worker-gate-02"
    block_file_b = seed_block_doc(root, BLOCK_B, "meta/blocks/gate-02.md")
    eng.workers[WID_B] = {"block": BLOCK_B, "status": "assigned"}

    gstate_b = gate.new_state(eng, BLOCK_B, block_file_b, BRANCH_B, WID_B)
    bad_tip = make_adversarial_record_commit(root, BRANCH_B, block_file_b,
                                             "meta/stray-out-of-gate.md")
    ok("B0: rig-as-misbehaving-worker made a record commit touching a SECOND file",
       bool(bad_tip) and not is_ancestor(root, bad_tip, MAIN), f"bad_tip={bad_tip}")

    main_before_bad = _git_out(["rev-parse", MAIN], root)
    history_b = drive_until(eng, BLOCK_B, gstate_b, {"escalate", "record_landed"}, root,
                            grants_dir, max_iters=10)
    outcomes_b = [o for o, _ in history_b]
    main_after_bad = _git_out(["rev-parse", MAIN], root)

    ok("B1 (ADVERSARIAL — must ESCALATE): gate.record returns a distinct "
       "('escalate', detail) outcome for the second-file record commit — never landed",
       "escalate" in outcomes_b and "record_landed" not in outcomes_b
       and "record_pending" not in outcomes_b and "land.sh" not in outcomes_b,
       f"outcomes={outcomes_b}")

    ok("B2: gate_state itself reflects the escalation (stage == escalated, "
       "escalation detail names the out-of-gate change)",
       gstate_b["stage"] == gate.STAGE_ESCALATED and "out-of-gate" in (gstate_b.get("escalation") or ""),
       f"stage={gstate_b['stage']} escalation={gstate_b.get('escalation')}")

    ok("B3 (THE ADVERSARIAL KILLER — must be GREEN): main did NOT advance — no grant "
       "minted, no land.sh run, real git proves the bad content never reached trunk "
       "(git rev-parse main unchanged; merge-base --is-ancestor bad_tip main == FALSE)",
       main_after_bad == main_before_bad and not is_ancestor(root, bad_tip, MAIN),
       f"main_before={main_before_bad} main_after={main_after_bad} "
       f"bad_tip={bad_tip} is_ancestor={is_ancestor(root, bad_tip, MAIN)}")

    ok("B4: the branch itself is untouched by any landing primitive — no case-id was "
       "ever minted for it (gate.record never even reached land_via_grant)",
       gstate_b.get("record_case_id") is None, f"record_case_id={gstate_b.get('record_case_id')}")

    passed = sum(1 for _, c, _ in _results if c)
    print(f"core.gate_rig: {'PASS' if passed == len(_results) else 'FAIL'} "
          f"({passed}/{len(_results)})")
    for name, c, detail in _results:
        print(f"  [{'PASS' if c else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\nroot={root}")
    print(f"BLOCK_A={BLOCK_A} BRANCH_A={BRANCH_A} record_tip_a={record_tip_a}")
    print(f"main tip after Phase A close={_git_out(['rev-parse', MAIN], root)}")
    print(f"BLOCK_B={BLOCK_B} BRANCH_B={BRANCH_B} bad_tip={bad_tip}")
    print(f"main tip after Phase B (must equal Phase A's)={_git_out(['rev-parse', MAIN], root)}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
