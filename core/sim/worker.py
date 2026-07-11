"""core.sim.worker — the SCRIPTED worker driver (wave 14, ADR-0004 §11.5):
plays engineer + reviewer + architect deterministically, off whatever the
engine's own manifest/inbox surfaces each tick — never a hand-authored
expectation of what the engine SHOULD do, only a reaction to what it
actually ordered (online+branch, local-pass, real `land.sh` on merge/
record, teardown on close). No LLM, no real process.

## The transcript-replay seam

The ONE piece of a scripted worker's behavior that is not purely a reaction
to engine-observable state is WHAT CODE a worker writes when it creates its
branch (`gate.local`'s predicate needs a local-pass report; that report's
CONTENT is fixed — see `LOCAL_PASS_REPORT` below — but the CODE COMMIT
itself is free choice). `Transcript.code_for(block) -> (rel_path, content)`
is that ONE seam: a `(block, stage)`-keyed lookup a future recorded
real-agent transcript can drive unchanged (ADR-0004 §11.5's own promotion-
rule mitigation — "drive L2 scripted workers from recorded real-agent
transcripts, not hand-authored expectations"). Everything else this module
does (branch/local-pass/land/teardown, reviewer hold/attest, architect
reconcile/log-review) is a reaction to OBSERVED manifest state, not a
scripted expectation of it — the same discipline `core/engine_rig.py`'s own
`RunHistory` already established, generalized here over an ARBITRARY block
list instead of one hardcoded fixture.

`ScriptedDriver` generalizes `core/engine_rig.py::RunHistory` verbatim in
shape (same tracking dicts, same four `react_*` passes) — it reacts to
WHATEVER `engineer-<block>`/`reviewer-<type>-<n>` worker record appears in
the real, persisted manifest, so the SAME driver plays the caller's own
block list AND any block the architect authors later (a `forward` job's
missing-file block, a `log` job's log-review adhoc block) without ever
needing to know its id up front.

Real git only where a real worker's own terminal commands would be (branch
creation, code/record commits, `land.sh`, branch teardown) — never trunk
OBSERVATION, which stays `core.engine.Engine`'s own job (via `core.gitobs`,
exercised for real by whatever rig drives this module). This mirrors every
prior `core/*_rig.py`'s own worker-standing-in convention exactly; nothing
here reads/decides off git directly, only WRITES the git state a real
worker process would have written."""
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))          # core/sim
_CORE_DIR = os.path.dirname(_HERE)                            # core
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

import gate   # noqa: E402 — core/gate.py, the DONE-ladder stage constants (read-only vocabulary)

MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"

LOCAL_PASS_REPORT = {"verdict": "pass",
                     "evidence": "python3 app/tests/test_lib.py -> green (rig-supplied local "
                                 "report, delivered via a structured worker.done inbox line)"}

DEFAULT_FINDING = {"title": "tidy inconsistent status wording across landed blocks"}


# ── real git helpers — a scripted worker's own terminal commands (never a
#    trunk OBSERVATION; see module docstring) ──
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


def append_jsonl(path, obj):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


# ── the transcript-replay seam ──
def default_code_for(block):
    """The default, generic (correct-by-construction) content a scripted
    worker writes on its OWN branch for `block` — a small REAL function
    (`value()`) plus a `check()` the mockup's declared test command asserts
    for real. Deterministic per block id, never random — a re-run of the
    SAME block list always authors byte-identical content. `Transcript`
    below is the seam a caller overrides this for (a richer, block-specific
    function; a deliberately BROKEN one, to exercise the failing-test
    path)."""
    n = sum(ord(c) for c in str(block)) % 997
    body = (
        f'"""app/lib/{block}.py — authored by core.sim\'s scripted worker '
        f'(Transcript default for block {block!r}).\"\"\"\n\n'
        f"def value():\n"
        f"    return {n}\n\n\n"
        f"def check():\n"
        f"    return value() == {n}\n"
    )
    return f"app/lib/{block}.py", body


class Transcript:
    """`(block) -> (rel_path, content)` for the ONE free-choice action a
    scripted worker's branch-creation commit makes — see module docstring.
    `code_for` falls back to `default_code_for` for any block not explicitly
    overridden (an adhoc block the architect authors mid-run included) —
    the generality `core/engine_rig.py::RunHistory` already established,
    kept here."""

    def __init__(self, overrides=None, finding=None):
        self._overrides = dict(overrides or {})
        self.finding = dict(finding or DEFAULT_FINDING)

    def code_for(self, block):
        if block in self._overrides:
            return self._overrides[block]
        return default_code_for(block)

    def override(self, block, rel_path, content):
        self._overrides[block] = (rel_path, content)
        return self


def default_transcript(overrides=None, finding=None):
    return Transcript(overrides=overrides, finding=finding)


# ── real git actions a scripted worker/architect performs ──
def make_code_commit(root, branch, rel_path, content):
    _git(["checkout", "-B", branch, MAIN], root)
    path = os.path.join(root, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"feat({branch}): author {rel_path}"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def make_record_commit(root, branch, block_file_rel):
    _git(["checkout", branch], root)
    path = os.path.join(root, block_file_rel)
    with open(path) as f:
        content = f.read()
    new_content = content.replace("**Status:** 📋 To do", "**Status:** ✅ Done")
    if new_content == content:
        raise RuntimeError(f"core.sim.worker: record commit on {branch} found no "
                           f"'**Status:** 📋 To do' line in {block_file_rel} — fixture drift")
    with open(path, "w") as f:
        f.write(new_content)
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"record: {branch} done"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


ADHOC_ROW_TEMPLATE = "| {block} | {title} | 📋 | Block `blocks/{block}.md` |\n"

ADHOC_BLOCK_DOC = """# Block {block}: {title}

**Phase:** 1 — core.sim log-review adhoc
**Status:** 📋 To do
**Depends on:** none
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** {created}

---

## Context

Authored by the SCRIPTED ARCHITECT (`core.sim.worker`, playing a real `log`
job) from a code-review finding: {title!r} — a genuinely NEW adhoc block (no
pre-existing pipeline row), landed via `core.landing.land_via_grant` under a
content-bound case-id, then dispatched and driven to ✅ + CLOSED exactly
like any ordinary block.

---

## Acceptance Criteria

| # | Criterion | Verification method | Owner |
|:--|:--|:--|:--|
| AC-1 | `app/lib/{block}.py::check()` returns `True` | `cmd:python3 app/tests/test_lib.py` | engineer |
"""


def make_adhoc_doc(root, branch, block, title, created, pipeline_rel=PIPELINE_REL, blocks_rel=BLOCKS_REL):
    """The rig-as-architect authoring a REAL, genuinely NEW pipeline row +
    block file for a log-review finding, in ONE commit, on the architect's
    own branch (mirrors `core/engine_rig.py::make_adhoc_doc` /
    `core/reviewers_rig.py::make_adhoc_doc`)."""
    _git(["checkout", "-B", branch, MAIN], root)
    ppath = os.path.join(root, pipeline_rel)
    with open(ppath) as f:
        content = f.read()
    row = ADHOC_ROW_TEMPLATE.format(block=block, title=title)
    idx = next(i for i, l in enumerate(content.splitlines(keepends=True))
              if l.strip().startswith("## Ad-hoc"))
    lines = content.splitlines(keepends=True)
    j = idx + 1
    while j < len(lines) and not lines[j].strip().startswith("|:"):
        j += 1
    lines.insert(j + 1, row)
    content = "".join(lines)
    with open(ppath, "w") as f:
        f.write(content)
    bpath = os.path.join(root, blocks_rel, f"{block}.md")
    os.makedirs(os.path.dirname(bpath), exist_ok=True)
    with open(bpath, "w") as f:
        f.write(ADHOC_BLOCK_DOC.format(block=block, title=title, created=created))
    _git(["add", "-A"], root)
    _git(["commit", "-m", f"arch(log-review): author adhoc block {block}"], root)
    tip = _git_out(["rev-parse", "HEAD"], root)
    _git(["checkout", "--detach", MAIN], root)
    return tip


def run_land(root, grants_dir, case_id):
    r = subprocess.run(
        ["bash", os.path.join(root, "meta", "scripts", "land.sh"), case_id,
         "--main", MAIN, "--grants-dir", grants_dir],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "LAND_MAIN_BRANCH": MAIN})
    return r.returncode, r.stdout, r.stderr


def rebase_onto_main(root, branch):
    """A real worker's own recovery from `land.sh`'s "not a fast-forward"
    refusal (mirrors `core/engine_rig.py`/`core/liveness_rig.py`'s own
    identical helper) — needed whenever more than one branch can land
    concurrently against the same worker_count=1 slot (the architect's own
    forward/log-review/reconcile branches, genuinely concurrent with an
    engineer's)."""
    _git(["checkout", branch], root)
    r = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", MAIN, branch])
    if r.returncode != 0:
        _git(["rebase", MAIN], root)
    _git(["checkout", "--detach", MAIN], root)


def try_land(root, grants_dir, case_id, branch):
    """Run the REAL `land.sh`; on a genuine "not a fast-forward"/CAS-failed
    refusal, rebase onto the fresh `main` and return `False` so the caller
    retries the SAME case_id on a LATER tick. Returns `True` only once
    `land.sh` itself reports success. A genuinely UNEXPECTED failure is
    fail-loud."""
    rc, out, err = run_land(root, grants_dir, case_id)
    if rc == 0:
        return True
    combined = (out or "") + (err or "")
    if "not a fast-forward" in combined or "CAS failed" in combined:
        rebase_onto_main(root, branch)
        return False
    raise RuntimeError(f"core.sim.worker: land.sh failed unexpectedly for case "
                       f"{case_id} on {branch}: rc={rc}\nstdout={out}\nstderr={err}")


def _today():
    import datetime
    return datetime.date.today().isoformat()


class ScriptedDriver:
    """Per-run mutable tracking, generalized over WHATEVER `engineer-*`/
    `reviewer-*` worker record appears in the REAL, persisted manifest — the
    same react loop drives every block `core.sim.run.run_sim` was seeded
    with AND, later, any block the architect authors mid-run, without ever
    needing to know its id up front (mirrors `core/engine_rig.py::
    RunHistory`, generalized over an arbitrary block list)."""

    def __init__(self, root, grants_dir, tron_ctx, transcript,
                pipeline_rel=PIPELINE_REL, blocks_rel=BLOCKS_REL):
        self.root = root
        self.grants_dir = grants_dir
        self.tron_ctx = tron_ctx
        self.transcript = transcript
        self.pipeline_rel = pipeline_rel
        self.blocks_rel = blocks_rel

        self.branch_created = {}
        self.local_reported = {}
        self.record_committed = {}
        self.torn_down = {}
        self.spawn_tick = {}
        self.done_tick = {}
        self.close_tick = {}
        self.landed_cases = set()

        self.reviewer_seen = {}
        self.review_first_sent = set()
        self.review_hold_tick = {}
        self.review_attest_sent = set()
        self.review_release_tick = {}

        self.adhoc_authored = set()
        self.adhoc_landed_tick = {}
        self.reconciled_reported = set()

        self.tick_history = []   # (i, outcomes, spawned, session_end) — caller-appended optionally

    def _track(self, block):
        self.branch_created.setdefault(block, False)
        self.local_reported.setdefault(block, False)
        self.record_committed.setdefault(block, False)
        self.torn_down.setdefault(block, False)

    def react_engineers(self, i, manifest):
        workers = manifest.get("workers") or {}
        gates = manifest.get("gates") or {}
        for agent_id, w in list(workers.items()):
            if not agent_id.startswith("engineer-"):
                continue
            block = w.get("block")
            if not block:
                continue
            self._track(block)
            branch = f"feat/{block}"
            if block not in self.spawn_tick:
                self.spawn_tick[block] = i
            if w.get("status") == "spawning" and not self.branch_created[block]:
                rel_path, content = self.transcript.code_for(block)
                make_code_commit(self.root, branch, rel_path, content)
                self.branch_created[block] = True
                append_jsonl(self.tron_ctx.worker_inbox,
                            {"tag": "worker.online", "agent_id": agent_id,
                             "slots": {"branch": branch}})

            g = gates.get(block)
            if not g:
                continue
            stage = g.get("stage")
            block_file_rel = f"{self.blocks_rel}/{block}.md"

            if stage == gate.STAGE_LOCAL and not self.local_reported[block]:
                append_jsonl(self.tron_ctx.worker_inbox,
                            {"tag": "worker.done", "block": block, "slots": LOCAL_PASS_REPORT})
                self.local_reported[block] = True
            elif stage == gate.STAGE_MERGE and g.get("merge_case_id"):
                case_id = g["merge_case_id"]
                if case_id not in self.landed_cases:
                    if try_land(self.root, self.grants_dir, case_id, branch):
                        self.landed_cases.add(case_id)
            elif stage == gate.STAGE_RECORD:
                if g.get("record_ordered") and not self.record_committed[block] \
                        and not g.get("record_case_id"):
                    make_record_commit(self.root, branch, block_file_rel)
                    self.record_committed[block] = True
                if g.get("record_case_id") and g["record_case_id"] not in self.landed_cases:
                    case_id = g["record_case_id"]
                    if try_land(self.root, self.grants_dir, case_id, branch):
                        self.landed_cases.add(case_id)
            elif stage == gate.STAGE_CLOSE and g.get("close_ordered") and not self.torn_down[block]:
                _git(["branch", "-D", branch], self.root)
                self.torn_down[block] = True

            if stage == gate.STAGE_CLOSED and block not in self.close_tick:
                self.close_tick[block] = i
            # NOTE: STAGE_TRUNK has no reaction of its own — a genuinely
            # FAILING declared test holds there deliberately (`core.sim.
            # sim_l2_rig`'s failing-test variant); a passing one advances on
            # its own, no worker action needed either way.

    def react_reviewer(self, i, manifest):
        workers = manifest.get("workers") or {}
        for agent_id, w in list(workers.items()):
            if not agent_id.startswith("reviewer-"):
                continue
            typ = w.get("type")
            if agent_id not in self.reviewer_seen:
                self.reviewer_seen[agent_id] = i
            status = w.get("status")
            if status == "reviewing" and agent_id not in self.review_first_sent:
                append_jsonl(self.tron_ctx.worker_inbox,
                            {"tag": "worker.review_done", "agent_id": agent_id, "type": typ,
                             "slots": {"findings": [self.transcript.finding]}})
                self.review_first_sent.add(agent_id)
            elif status == "held":
                if agent_id not in self.review_hold_tick:
                    self.review_hold_tick[agent_id] = i
                if agent_id not in self.review_attest_sent:
                    # Second hand-back carries NO findings of its own — falls
                    # back to the stashed first-hand-back finding
                    # (`core/reviewers.py::on_review_done`'s own documented
                    # fallback).
                    append_jsonl(self.tron_ctx.worker_inbox,
                                {"tag": "worker.review_done", "agent_id": agent_id, "type": typ,
                                 "slots": {}})
                    self.review_attest_sent.add(agent_id)
        for agent_id in self.reviewer_seen:
            if agent_id not in workers and agent_id not in self.review_release_tick:
                self.review_release_tick[agent_id] = i

    def react_architect_reconcile(self, i, manifest):
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if cur and cur.get("kind") == "reconcile" and cur.get("ordered") \
                and cur.get("block") not in self.reconciled_reported:
            append_jsonl(self.tron_ctx.worker_inbox,
                        {"tag": "architect.reconciled", "block": cur["block"]})
            self.reconciled_reported.add(cur["block"])

    def react_architect_log(self, i, manifest):
        arch = manifest.get("architect") or {}
        cur = arch.get("current_job")
        if not (cur and cur.get("kind") == "log" and cur.get("ordered")):
            return
        for e in cur.get("adhoc") or []:
            block, branch = e["block"], e["branch"]
            title = (e.get("finding") or {}).get("title") or f"finding for {block}"
            if block not in self.adhoc_authored:
                make_adhoc_doc(self.root, branch, block, title, _today(),
                               pipeline_rel=self.pipeline_rel, blocks_rel=self.blocks_rel)
                self.adhoc_authored.add(block)
            case_id = e.get("case_id")
            if case_id and case_id not in self.landed_cases:
                if try_land(self.root, self.grants_dir, case_id, branch):
                    self.landed_cases.add(case_id)
                    if block not in self.adhoc_landed_tick:
                        self.adhoc_landed_tick[block] = i

    def react(self, i, manifest):
        self.react_engineers(i, manifest)
        self.react_reviewer(i, manifest)
        self.react_architect_reconcile(i, manifest)
        self.react_architect_log(i, manifest)

    def record_done_ticks(self, i, outcomes):
        for block, (outcome, _detail) in outcomes.items():
            if outcome == "record_landed" and block not in self.done_tick:
                self.done_tick[block] = i
