"""core.bootup_rig — real-git, real-`RolesConfig` rig proving `core.bootup.
Bootup` (block 01-38 T23, ADR-0003 D-D) restores the FROZEN operator
bootup journey into `core/*`, byte-for-byte, against the real
`core.engine.Engine`; AND (block 01-38 T24, ADR-0003 D-J) that AIDE is a
REAL LLM lane — never a heuristic — at the bootup nodes (ND-01-08 SET
SCOPE / ND-01-09 SET COUNTS), the runtime case-brief-at-escalation node
(ND-02-10, `core/casestate.py::architect_resolve`), and the directly-
callable answer-an-`ask` primitive (ND-09) — fail-open throughout,
including on a raising/erroring AIDE call at the escalation site (CLU
hardening: the page must still fire promptly with the raw text intact).

Fixture: a real git trunk with TWO phases (`Phase 1`: 01-01, 01-02
[depends on 01-01]; `Phase 2`: 02-01) — phase/range scope resolution needs
more than one phase to prove anything. `meta/tron/roles.yaml` declares
three roles covering every capability class:
  architect   TRIAGE, spec_owner+persistent, NO declared model
              (proves the "architect" tier recommendation, and — with an
              empty session override — the fail-closed path)
  engineer    BUILD+CLOSE, model: claude-declared-x
              (proves "roles.yaml's own declared model wins over the
              tier default")
  reviewer-code  REVIEW (selector reviewer_class: code), NO declared model
              (proves the "other" tier recommendation)

`engine.jobs.spawn_runner` is the ONE seam stubbed (never a real `claude`
process — the established `core/*_rig.py` convention); every other
`Engine`/`RolesConfig`/git/manifest seam runs for real. Every AIDE call
routes through `engine/judge.py`'s own sanctioned offline-testability hook
(`TRON_JUDGE_STUB` — the REAL `judge.call`/`call_aide` code path: real
validation, real `aide_invocation` emission, zero tokens/network — the
SAME convention `core/aide_invocation_rig.py` already established);
`test:<aide_fail_open_unaided>` instead uses `TRON_DRY` with NO stub —
`judge.py`'s own documented genuine-unavailable path (`engine/block_01_36_
test.py`'s own precedent: "no monkeypatch — TRON_DRY's own aide-down..."),
never a monkeypatch standing in for a heuristic. Each scenario that calls
`Engine.start`/`Bootup.bootup` gets its OWN fresh scaffold+instance (a live
session, once started, refuses to re-boot — `BootupError` — so scenarios
can never share one manifest).

`ok(name, cond, detail)` collector; `main()` prints `PASS (n/m)` and every
line, exits non-zero on any fail.
"""
import builtins
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "engine"))
sys.path.insert(0, HERE)

import jobs                          # noqa: E402 — engine/jobs.py, the ONE seam this rig stubs
import judge                          # noqa: E402 — engine/judge.py, the real AIDE lane (TRON_JUDGE_STUB)
from ctx import Ctx                    # noqa: E402 — engine/ctx.py
from roles import RolesError            # noqa: E402 — engine/roles.py, the fail-closed error T23 wires
import state                             # noqa: E402 — core/state.py
import architect                          # noqa: E402 — core/architect.py, ARCHITECT_WID
import casestate                          # noqa: E402 — core/casestate.py, T24's ND-02-10 live trigger
from engine import Engine                  # noqa: E402 — core/engine.py, THE MODULE T23 FRONTS
from bootup import Bootup, ROLE_MODEL_RECOMMENDED   # noqa: E402 — core/bootup.py, MODULE UNDER TEST


@contextlib.contextmanager
def aide_stub(mapping):
    """Route every `judge.call_aide` call inside the `with` block through
    the sanctioned `TRON_JUDGE_STUB` offline hook (real `judge.call`/
    `call_aide` code path — real validation, real `aide_invocation`
    emission — zero tokens/network), restoring the prior env + resetting
    `judge`'s module-level stub cache/cursor on exit either way."""
    fh = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(mapping, fh)
    fh.close()
    old = os.environ.get("TRON_JUDGE_STUB")
    os.environ["TRON_JUDGE_STUB"] = fh.name
    judge._stub_cache = None
    judge._stub_idx = {}
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("TRON_JUDGE_STUB", None)
        else:
            os.environ["TRON_JUDGE_STUB"] = old
        os.remove(fh.name)
        judge._stub_cache = None
        judge._stub_idx = {}

import scaffold_src                # noqa: E402 — core/scaffold_src.py
import emit                         # noqa: E402 — core/emit.py, the bootup_scope_fallback effect

SCAFFOLD_SRC = scaffold_src.resolve()
MAIN = "main"
PIPELINE_REL = "meta/pipeline.md"
BLOCKS_REL = "meta/blocks"
ROLES_REL = "meta/tron/roles.yaml"
PERSONAS_REL = "meta/tron/personas"

BLOCK_A, BLOCK_B, BLOCK_C = "01-01", "01-02", "02-01"
ORDER = [BLOCK_A, BLOCK_B, BLOCK_C]   # living-doc order: phase 1 (A, B depends-on A), phase 2 (C)

ENGINEER_DECLARED_MODEL = "claude-declared-x"
REVIEWER_CUSTOM_MODEL = "custom-review-model"

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def _git(args, cwd, check=True):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}) rc={r.returncode}\n"
                           f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return r


PIPELINE_TEMPLATE = """# Pipeline

## Roadmap

### Phase 1: bootup_rig fixture

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {a} | bootup_rig fixture block A (no deps) | 📋 To do | Block `blocks/{a}.md` |
| {b} | bootup_rig fixture block B (depends on {a}) | 📋 To do | Block `blocks/{b}.md` |

### Phase 2: bootup_rig fixture phase two

| ID | Task | Status | Notes |
|:---|:---|:---|:---|
| {c} | bootup_rig fixture block C (no deps, phase 2) | 📋 To do | Block `blocks/{c}.md` |
"""

BLOCK_DOC_TEMPLATE = """# Block {block}: bootup_rig fixture

**Phase:** {phase} — bootup_rig
**Status:** 📋 To do
**Depends on:** {depends_on}
**Blocks:** none
**Reviewer class:** none
**Merge approval:** auto
**Deploy:** none
**Created:** 2026-07-14

---

## Context

Synthetic block doc for `core.bootup_rig` — proves the restored bootup
journey (`core/bootup.py`) drives a real `core.engine.Engine.start(...)`
through real scope/worker_count/ask-before-merging/model resolution.
"""

PERSONA_TEMPLATE = """# {role} persona (core.bootup_rig fixture)

Synthetic persona — `RolesConfig`'s fail-closed boot validation requires
every declared role's persona to exist on disk; content is never read
(this rig's workers are entirely stubbed — no real `claude` process)."""

ROLES_YAML_TEMPLATE = f"""roles:
  architect:
    persona: {PERSONAS_REL}/architect.md
    binds: [TRIAGE]
    spec_owner: true
    persistent: true
  engineer:
    persona: {PERSONAS_REL}/engineer.md
    model: {ENGINEER_DECLARED_MODEL}
    binds: [BUILD, CLOSE]
  reviewer-code:
    persona: {PERSONAS_REL}/reviewer-code.md
    binds: [REVIEW]
    selector:
      reviewer_class: code
"""


def build_instance(tag):
    """A fresh scaffold + git trunk + roles.yaml + project/knobs, returning
    a real `engine.ctx.Ctx` — every scenario that calls `Engine.start`/
    `Bootup.bootup` needs its OWN (a live session refuses to re-boot)."""
    d = tempfile.mkdtemp(prefix=f"tron-core-bootuprig-{tag}-")
    root = os.path.join(d, "scaffold")
    shutil.copytree(SCAFFOLD_SRC, root, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "node_modules"))
    script = os.path.join(root, "meta", "scripts", "land.sh")
    os.chmod(script, os.stat(script).st_mode | 0o111)
    _git(["init", "-b", MAIN], root)
    _git(["config", "user.email", "rig@test.local"], root)
    _git(["config", "user.name", "core-bootup-rig"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: trivial-tip-converter scaffold"], root)

    ppath = os.path.join(root, PIPELINE_REL)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w") as f:
        f.write(PIPELINE_TEMPLATE.format(a=BLOCK_A, b=BLOCK_B, c=BLOCK_C))
    specs = {BLOCK_A: ("1", "none"), BLOCK_B: ("1", BLOCK_A), BLOCK_C: ("2", "none")}
    for block, (phase, dep) in specs.items():
        bpath = os.path.join(root, BLOCKS_REL, f"{block}.md")
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        with open(bpath, "w") as f:
            f.write(BLOCK_DOC_TEMPLATE.format(block=block, phase=phase, depends_on=dep))

    roles_path = os.path.join(root, ROLES_REL)
    os.makedirs(os.path.dirname(roles_path), exist_ok=True)
    with open(roles_path, "w") as f:
        f.write(ROLES_YAML_TEMPLATE)
    personas_dir = os.path.join(root, PERSONAS_REL)
    os.makedirs(personas_dir, exist_ok=True)
    for role in ("architect", "engineer", "reviewer-code"):
        with open(os.path.join(personas_dir, f"{role}.md"), "w") as f:
            f.write(PERSONA_TEMPLATE.format(role=role))

    _git(["add", "-A"], root)
    _git(["commit", "-m", "seed: pipeline (2 phases) + roles.yaml (architect/engineer/reviewer-code)"], root)
    _git(["checkout", "--detach", MAIN], root)

    inst = os.path.join(root, "meta", "agents", "tron")
    os.makedirs(inst, exist_ok=True)
    with open(os.path.join(inst, "project.yaml"), "w") as f:
        yaml.safe_dump({"repo": {"root": root, "main_branch": MAIN, "remote": "none",
                                 "staging": "none"},
                        "test": {"command": "true"}}, f, sort_keys=False)
    with open(os.path.join(inst, "knobs.yaml"), "w") as f:
        yaml.safe_dump({"knobs": {"worker_count": 1, "silence_ping_min": 80,
                                  "silence_escalate_min": 160, "grant_ttl": 60},
                        "cadence": {}}, f, sort_keys=False)
    return Ctx(inst)


def stub_spawn():
    """Monkeypatch `jobs.spawn_runner` to a no-op recorder — the ONE
    process-spawn seam every `core.engine.Engine` scenario touches (both
    `_spawn_worker`/engineers-reviewers and `_spawn_architect`)."""
    calls = []

    def fake(worker_id, worker_dir, session_id, cwd=None, runtime=None,
            adapter=None, model=None, settle_s=2.0):
        calls.append({"worker_id": worker_id, "model": model})
        return {}
    real = jobs.spawn_runner
    jobs.spawn_runner = fake
    return calls, real


def restore_spawn(real):
    jobs.spawn_runner = real


def seeded_input(answers, prompts_seen):
    """A `builtins.input` stub that pops the next canned answer and records
    the EXACT prompt string it was called with — the sequence+wording
    proof for `test:<bootup_journey_sequence_frozen>`."""
    def _input(prompt=""):
        prompts_seen.append(prompt)
        if not answers:
            raise AssertionError(f"bootup_rig: seeded answers exhausted at prompt: {prompt!r}")
        return answers.pop(0)
    return _input


# ── T1: the frozen sequence, byte-for-byte wording, interactive throughout ──
def scenario_sequence_frozen():
    ctx = build_instance("seq")
    calls, real_spawn = stub_spawn()
    real_input = builtins.input
    try:
        prompts = []
        aide_default = judge.TIER.get("aide", judge.AIDE_DEFAULT_MODEL)
        answers = [
            "",                         # AIDE model -> blank, fail-open default (D-J, T24)
            "1",                        # [1] all
            "2",                        # worker_count
            "y",                        # ask-before-merging
            "",                         # architect model -> blank, recommended default
            "",                         # engineer model -> blank, roles.yaml declared wins
            REVIEWER_CUSTOM_MODEL,      # reviewer-code model -> explicit override
        ]
        builtins.input = seeded_input(answers, prompts)
        with aide_stub({"aide": [{"advice": "seq-scenario aide advice"}]}):
            b = Bootup(ctx)
            eng, spawned = b.bootup()

        EXPECTED_PROMPTS = [
            f"Model for AIDE (the operator's LLM advisor) [{aide_default}]? ",
            "  [1] all  ·  [2] a phase  ·  [3] a range of blocks  → ",
            "worker_count (build + review workers; the persistent spec-owner "
            "role is extra)? ",
            "Inform you before each merge to trunk? [y/N] ",
            f"Model for architect (the persistent architect/spec-owner) "
            f"[{ROLE_MODEL_RECOMMENDED['architect']}]? ",
            f"Model for engineer (engineers/reviewers) [{ENGINEER_DECLARED_MODEL}]? ",
            f"Model for reviewer-code (engineers/reviewers) "
            f"[{ROLE_MODEL_RECOMMENDED['other']}]? ",
        ]
        ok("SEQ1: the FROZEN journey asked exactly the legacy sequence, "
           "byte-for-byte wording, in order (AIDE model -> ND-01-08 advise "
           "[no prompt] -> scope -> ND-01-09 advise [no prompt] -> "
           "worker_count -> ask-before-merging -> model x3, roles sorted)",
           prompts == EXPECTED_PROMPTS,
           f"got={prompts!r}")

        manifest = state.load(ctx)
        ok("SEQ2: scope 'all' resolved to every trunk block id",
           sorted((manifest.get("scope") or {}).get("ids") or []) == sorted(ORDER),
           f"scope={manifest.get('scope')}")
        ok("SEQ3: worker_count resolved to the answered 2",
           (manifest.get("counts") or {}).get("worker_count") == 2,
           f"counts={manifest.get('counts')}")
        ok("SEQ4: ask-before-merging answer captured on the Bootup instance (True)",
           b.ask_before_merging is True, f"ask_before_merging={b.ask_before_merging}")
        ok("SEQ5: blank architect answer resolved to the recommended (opus) tier default",
           b.worker_models.get("architect") == ROLE_MODEL_RECOMMENDED["architect"],
           f"worker_models={b.worker_models}")
        ok("SEQ6: blank engineer answer resolved to roles.yaml's OWN declared model "
           "(declared wins over the 'other' tier default)",
           b.worker_models.get("engineer") == ENGINEER_DECLARED_MODEL,
           f"worker_models={b.worker_models}")
        ok("SEQ7: explicit reviewer-code override honored verbatim",
           b.worker_models.get("reviewer-code") == REVIEWER_CUSTOM_MODEL,
           f"worker_models={b.worker_models}")
        arch_call = next((c for c in calls if c["worker_id"] == architect.ARCHITECT_WID), None)
        ok("SEQ8: the REAL jobs.spawn_runner call for the architect used the "
           "session-answered (recommended) model — the answer actually reached spawn",
           arch_call is not None and arch_call["model"] == ROLE_MODEL_RECOMMENDED["architect"],
           f"arch_call={arch_call}")
        ok("SEQ9: bootup returned the first-dispatch spawn ids (Engine.start's own "
           "return — the architect is spawned separately at A8, tracked via "
           "spawn_calls/SEQ8 above, not part of this SWITCHBOARD-fill list)",
           set(spawned) == {"engineer-01-01", "engineer-02-01"}, f"spawned={spawned}")
    finally:
        builtins.input = real_input
        restore_spawn(real_spawn)


# ── T2: recommendation logic (tier default vs. declared-wins), no boot needed ──
def scenario_model_recommendation():
    ctx = build_instance("reco")
    eng = Engine(ctx)
    b = Bootup(ctx)
    ok("REC1: architect (spec_owner, no declared model) recommends the "
       "'architect' tier default",
       b._recommended_model(eng, "architect") == ROLE_MODEL_RECOMMENDED["architect"],
       f"got={b._recommended_model(eng, 'architect')!r}")
    ok("REC2: engineer (declared model in roles.yaml) recommends its OWN "
       "declared model, not the 'other' tier default",
       b._recommended_model(eng, "engineer") == ENGINEER_DECLARED_MODEL,
       f"got={b._recommended_model(eng, 'engineer')!r}")
    ok("REC3: reviewer-code (no declared model, not spec_owner/persistent) "
       "recommends the 'other' tier default",
       b._recommended_model(eng, "reviewer-code") == ROLE_MODEL_RECOMMENDED["other"],
       f"got={b._recommended_model(eng, 'reviewer-code')!r}")
    ok("REC4: role label ties architect to the spec-owner tier label",
       b._role_label("architect", eng._roles_config().roles["architect"])
       == "architect (the persistent architect/spec-owner)")
    ok("REC5: role label ties engineer to the engineers/reviewers tier label",
       b._role_label("engineer", eng._roles_config().roles["engineer"])
       == "engineer (engineers/reviewers)")


# ── T3: fail-closed — the SAME root check on the headless `eng.start()` path,
#     with NO Bootup/console involved at all (the harness's own documented shape) ──
def scenario_model_unresolved_fails_closed():
    ctx = build_instance("failclosed")
    calls, real_spawn = stub_spawn()
    try:
        raised = None
        try:
            Engine(ctx).start(scope="all", worker_count=1, models={})
        except RolesError as e:
            raised = e
        ok("FC1: a headless eng.start() with NO session model override and a role "
           "(architect) with no roles.yaml-declared model raises RolesError — "
           "fail-closed, never a silent default",
           raised is not None, f"raised={raised!r}")
        ok("FC2: the fail-closed raise names the unresolved role",
           raised is not None and "architect" in str(raised), f"raised={raised}")
        ok("FC3: NO spawn was attempted before the fail-closed raise — the check "
           "runs BEFORE any process/manifest mutation",
           calls == [], f"calls={calls}")
        manifest = state.load(ctx)
        ok("FC4: NO session was started (manifest carries no session marker) — "
           "the raise happened before ANY durable state was written",
           not (manifest.get("session") or {}).get("started_at"),
           f"session={manifest.get('session')}")

        # Positive control: the SAME roles resolve once a session override
        # supplies every role this fixture leaves undeclared (architect AND
        # reviewer-code both decline a roles.yaml model) — proving FC1 is a
        # real gate, not a broken fixture.
        Engine(ctx).start(scope="all", worker_count=1,
                          models={"architect": "override-model",
                                  "reviewer-code": "override-model-2"})
        manifest2 = state.load(ctx)
        ok("FC5 (positive control): the identical roles.yaml now boots clean once "
           "a session model override supplies the missing role",
           bool((manifest2.get("session") or {}).get("started_at")),
           f"session={manifest2.get('session')}")
    finally:
        restore_spawn(real_spawn)


# ── T4: staged-answer path — the model question never calls input() at all ──
def scenario_staged_answer():
    ctx = build_instance("staged")
    calls, real_spawn = stub_spawn()
    real_input = builtins.input
    try:
        prompts = []
        answers = ["1", "1", "n"]   # scope=all, worker_count=1, ask-before-merging=n
        builtins.input = seeded_input(answers, prompts)
        staged = {"architect": "staged-opus-x", "engineer": "", "reviewer-code": "staged-sonnet-y"}
        with aide_stub({"aide": [{"advice": "staged-scenario aide advice"}]}):
            b = Bootup(ctx)
            eng, spawned = b.bootup(staged_model=staged)

        ok("ST1: staged bootup consumed EXACTLY the non-model prompts (3) — "
           "NEITHER the AIDE model question NOR the per-role model question "
           "called input() at all (staged_model with no 'aide' key still "
           "never prompts — never hangs headless)",
           len(prompts) == 3, f"prompts={prompts!r}")
        ok("ST2: architect resolved to the staged answer verbatim",
           b.worker_models.get("architect") == "staged-opus-x", f"{b.worker_models}")
        ok("ST3: engineer's BLANK staged answer left it unresolved by THIS method "
           "(never silently given the recommended default) — but roles.yaml's own "
           "declared model still resolves it at validate_models, so boot succeeds",
           b.worker_models.get("engineer") is None, f"{b.worker_models}")
        ok("ST4: reviewer-code resolved to the staged answer verbatim",
           b.worker_models.get("reviewer-code") == "staged-sonnet-y", f"{b.worker_models}")
        manifest = state.load(ctx)
        ok("ST5: the staged bootup reached a real, durable session start",
           bool((manifest.get("session") or {}).get("started_at")), f"{manifest.get('session')}")
        arch_call = next((c for c in calls if c["worker_id"] == architect.ARCHITECT_WID), None)
        ok("ST6: the real spawn call for the architect used the STAGED model, "
           "not the recommended default",
           arch_call is not None and arch_call["model"] == "staged-opus-x", f"{arch_call}")
    finally:
        builtins.input = real_input
        restore_spawn(real_spawn)


# ── T5: scope phase/range resolution + the observable (never-silent) fallback ──
def scenario_scope_resolution():
    ctx = build_instance("scope")
    eng = Engine(ctx)
    b = Bootup(ctx)

    ok("SC1: phase 'Phase 2' resolves to exactly the phase-2 block",
       b._resolve_phase_scope(eng, "Phase 2") == [BLOCK_C],
       f"got={b._resolve_phase_scope(eng, 'Phase 2')!r}")
    ok("SC2: phase '1' (substring match) resolves to both phase-1 blocks, in "
       "living-doc order",
       b._resolve_phase_scope(eng, "1") == [BLOCK_A, BLOCK_B],
       f"got={b._resolve_phase_scope(eng, '1')!r}")
    ok("SC3: range 01-01..02-01 resolves to the full inclusive slice (all 3, "
       "living-doc order)",
       b._resolve_range_scope(eng, BLOCK_A, BLOCK_C) == ORDER,
       f"got={b._resolve_range_scope(eng, BLOCK_A, BLOCK_C)!r}")
    ok("SC4: range given backwards (hi, lo) still resolves the same inclusive "
       "slice, order-normalized",
       b._resolve_range_scope(eng, BLOCK_C, BLOCK_A) == ORDER,
       f"got={b._resolve_range_scope(eng, BLOCK_C, BLOCK_A)!r}")

    # ── the never-silent fallback: an unresolvable phase/range answer widens
    #    to "all", OBSERVABLY (a forensic event + an operator-visible print),
    #    never a quiet swallow (CLU ruling, T23) ──
    class _Sink:
        def __init__(self):
            self.log = []

        def event(self, type_, **payload):
            self.log.append({"type": type_, "payload": payload})

    eng2 = Engine(ctx)
    eng2.events = _Sink()
    resolved_phase = b._resolve_phase_scope(eng2, "no-such-phase-anywhere")
    ok("SC5: an unmatched phase answer widens to 'all' (never an empty/dead scope)",
       resolved_phase == "all", f"got={resolved_phase!r}")
    fallback_events = [e for e in eng2.events.log if e["type"] == "bootup_scope_fallback"]
    ok("SC6 (never-silent-default): the phase fallback wrote a forensic "
       "bootup_scope_fallback event naming the requested mode/value — the "
       "widening is OBSERVABLE in events.jsonl, never a quiet swallow",
       len(fallback_events) == 1
       and fallback_events[0]["payload"].get("requested_mode") == "phase"
       and fallback_events[0]["payload"].get("requested_value") == "no-such-phase-anywhere"
       and fallback_events[0]["payload"].get("resolved") == "all",
       f"events={fallback_events}")

    eng3 = Engine(ctx)
    eng3.events = _Sink()
    resolved_range = b._resolve_range_scope(eng3, "no-such-block", BLOCK_C)
    ok("SC7: an unresolvable range endpoint widens to 'all' (never an "
       "exception, never a dead/empty scope)",
       resolved_range == "all", f"got={resolved_range!r}")
    range_fallback = [e for e in eng3.events.log if e["type"] == "bootup_scope_fallback"]
    ok("SC8 (never-silent-default): the range fallback is ALSO observable — one "
       "forensic event, requested mode 'range'",
       len(range_fallback) == 1 and range_fallback[0]["payload"].get("requested_mode") == "range",
       f"events={range_fallback}")


# ── T6 (block 01-38 T24, AC-20): AIDE at the two BOOTUP nodes — a REAL LLM
#     call (never a heuristic), advisory only ──
def scenario_aide_bootup_advises():
    ctx = build_instance("aide-bootup")
    calls, real_spawn = stub_spawn()
    real_input = builtins.input
    buf = io.StringIO()
    try:
        answers = ["", "1", "1", "n", "", "", ""]
        prompts = []
        builtins.input = seeded_input(answers, prompts)
        with aide_stub({"aide": [{"advice": "AIDE-MARKER-SCOPE-COUNTS",
                                  "recommended_block": BLOCK_A}]}):
            b = Bootup(ctx)
            with contextlib.redirect_stdout(buf):
                eng, spawned = b.bootup()
        output = buf.getvalue()

        ok("AIDE1 (test:<aide_is_llm_advises_scope_counts>): ND-01-08 SET "
           "SCOPE printed the REAL AIDE advisory text (the stub's own "
           "distinctive marker — proves the real judge.call_aide render "
           "path executed, never a hardcoded string) BEFORE the scope "
           "question fired",
           "AIDE-MARKER-SCOPE-COUNTS" in output, f"output={output!r}")
        ok("AIDE2: ND-01-08's recommended_block advisory also printed",
           f"AIDE recommends: block {BLOCK_A}" in output, f"output={output!r}")
        aide_events = [e for e in eng.events.log if e["type"] == "aide_invocation"]
        modes = [e["payload"].get("mode") for e in aide_events]
        oks = [e["payload"].get("ok") for e in aide_events]
        ok("AIDE3: BOTH bootup AIDE nodes genuinely fired through the ONE "
           "real judge chokepoint — aide_invocation for mode='scope' "
           "(ND-01-08) AND mode='counts' (ND-01-09), ok=True — never "
           "skipped, never a heuristic stand-in",
           modes.count("scope") == 1 and modes.count("counts") == 1
           and all(o is True for o in oks), f"aide_events={aide_events}")
    finally:
        builtins.input = real_input
        restore_spawn(real_spawn)


# ── T7 (block 01-38 T24, AC-20): AIDE fail-open — genuinely unavailable
#     (TRON_DRY, no stub — judge.py's own real path, no monkeypatch) never
#     blocks boot, and STILL genuinely invokes (ok=False, never skipped) ──
def scenario_aide_fail_open_unaided():
    ctx = build_instance("aide-failopen")
    calls, real_spawn = stub_spawn()
    real_input = builtins.input
    buf = io.StringIO()
    old_dry = os.environ.get("TRON_DRY")
    old_stub = os.environ.pop("TRON_JUDGE_STUB", None)
    os.environ["TRON_DRY"] = "1"
    judge._stub_cache = None
    judge._stub_idx = {}
    try:
        answers = ["", "1", "1", "n", "", "", ""]
        prompts = []
        builtins.input = seeded_input(answers, prompts)
        b = Bootup(ctx)
        with contextlib.redirect_stdout(buf):
            eng, spawned = b.bootup()
        output = buf.getvalue()

        ok("FO1 (test:<aide_fail_open_unaided>): AIDE genuinely unavailable "
           "(TRON_DRY, no stub, no monkeypatch — judge.py's own documented "
           "real fail-open path) -> bootup proceeds unaided, prints the "
           "documented fallback line, NEVER hangs/crashes",
           "AIDE: unavailable — proceeding unaided" in output, f"output={output!r}")
        manifest = state.load(ctx)
        ok("FO2: the run still reached a real, durable session start despite "
           "AIDE being unavailable at BOTH bootup nodes — fail-open never "
           "blocks boot (D-J reconciliation (e))",
           bool((manifest.get("session") or {}).get("started_at")), f"{manifest.get('session')}")
        aide_events = [e for e in eng.events.log if e["type"] == "aide_invocation"]
        modes = [e["payload"].get("mode") for e in aide_events]
        oks = [e["payload"].get("ok") for e in aide_events]
        ok("FO3: BOTH AIDE attempts were STILL genuinely invoked (a real "
           "attempt was made and recorded — aide_invocation fires for "
           "every real call, ok or not, never a silent skip) with ok=False",
           modes.count("scope") == 1 and modes.count("counts") == 1
           and all(o is False for o in oks), f"aide_events={aide_events}")
    finally:
        builtins.input = real_input
        restore_spawn(real_spawn)
        if old_dry is None:
            os.environ.pop("TRON_DRY", None)
        else:
            os.environ["TRON_DRY"] = old_dry
        if old_stub is not None:
            os.environ["TRON_JUDGE_STUB"] = old_stub
        judge._stub_cache = None
        judge._stub_idx = {}


# ── T8 (block 01-38 T24, AC-20): AIDE at the RUNTIME nodes — the case-brief
#     at escalation (ND-02-10, core/casestate.py's REAL live trigger) and
#     the directly-callable answer-an-ask primitive (ND-09) ──
def scenario_aide_runtime_escalation_nodes():
    ctx = build_instance("aide-runtime")
    eng = Engine(ctx)   # a REAL core.engine.Engine — .ctx/.paths/.aide_model()/.events all real

    # (a) case-brief at escalation: architect_resolve's REAL live trigger.
    with aide_stub({"aide": [{"advice": "AIDE-BRIEF-MARKER-RUNTIME"}]}):
        manifest = {"cases": {"case-1": {"decision": None, "owner": "architect",
                                         "block": None, "detail": "RAW-DETAIL-XYZ",
                                         "worker_id": None, "source": "worker.wall"}}}
        result = casestate.architect_resolve(eng, manifest, "case-1", "operator")
        ok("RT1: architect_resolve(verdict='operator') — the REAL live "
           "trigger for ND-02-10 — succeeded",
           result is True)
        outbox_path = eng.ctx.p("operator-outbox.jsonl")
        with open(outbox_path) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        last = lines[-1]
        ok("RT2 (test:<aide_llm_runtime_escalation_nodes>): the REAL AIDE "
           "brief (the stub's own distinctive marker, never hardcoded) is "
           "present in the paged detail",
           "AIDE-BRIEF-MARKER-RUNTIME" in last["detail"], f"paged={last['detail']!r}")
        ok("RT3 (T21 content-integrity): the RAW detail is STILL preserved "
           "byte-for-byte inside the paged text — a brief augments, never "
           "replaces",
           "RAW-DETAIL-XYZ" in last["detail"], f"paged={last['detail']!r}")
        aide_events = [e for e in eng.events.log if e["type"] == "aide_invocation"]
        ok("RT4: the case-brief call is a REAL aide_invocation, mode='resolve' "
           "(ND-02-10's own mode, shared with the bootup RESOLVE node)",
           any(e["payload"].get("mode") == "resolve" for e in aide_events), f"{aide_events}")

    # (b) CLU HARDENING: AIDE call RAISES -> the page STILL fires promptly,
    #     raw text intact, byte-for-byte.
    real_call_aide = judge.call_aide
    judge.call_aide = lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("simulated AIDE transport failure"))
    try:
        eng2 = Engine(ctx)
        manifest2 = {"cases": {"case-2": {"decision": None, "owner": "architect",
                                          "block": None, "detail": "RAW-DETAIL-CASE2",
                                          "worker_id": None, "source": "worker.wall"}}}
        result2 = casestate.architect_resolve(eng2, manifest2, "case-2", "operator")
        ok("RT5 (CLU HARDENING — must be GREEN): a RAISING AIDE call at the "
           "case-brief site does NOT prevent the page — architect_resolve "
           "still succeeds",
           result2 is True)
        outbox_path2 = eng2.ctx.p("operator-outbox.jsonl")
        with open(outbox_path2) as f:
            lines2 = [json.loads(l) for l in f if l.strip()]
        last2 = lines2[-1]
        ok("RT6 (CLU HARDENING — must be GREEN): the page fired with the RAW "
           "detail intact, byte-for-byte, despite the AIDE call raising — "
           "never held up, never lost content",
           last2["detail"] == "RAW-DETAIL-CASE2", f"paged={last2['detail']!r}")
    finally:
        judge.call_aide = real_call_aide

    # (c) the ask-answering primitive (ND-09): real, directly-callable, real
    #     LLM — no live in-tick trigger required (disclosed T24 scope note).
    with aide_stub({"aide": [{"advice": "the answer is 42", "answered": True}]}):
        b = Bootup(ctx)
        answered, advice = b._aide_answer_ask(eng, "what is the answer?")
        ok("RT7: _aide_answer_ask (ND-09 PARLEY open ask) is a real, "
           "directly-callable AIDE-LLM primitive — answered=True, real "
           "advice returned through the SAME judge.call_aide chokepoint",
           answered is True and advice == "the answer is 42",
           f"answered={answered} advice={advice!r}")
        aide_events2 = [e for e in eng.events.log if e["type"] == "aide_invocation"]
        ok("RT8: the ask-mode call ALSO genuinely invoked (aide_invocation, "
           "mode='ask')",
           any(e["payload"].get("mode") == "ask" for e in aide_events2),
           f"{aide_events2}")


# ── T25 (block 01-38, AC-21): journey answers persist ONLY to the TRON-owned
#     session store (never roles.yaml); a LATER fresh Engine resolves the
#     session model choice, layered over roles.yaml ──
def scenario_journey_persist_session_store():
    ctx = build_instance("persist")
    calls, real_spawn = stub_spawn()
    real_input = builtins.input
    roles_path = os.path.join(ctx.dir if hasattr(ctx, "dir") else "", "")
    # roles.yaml lives at the instance's own repo_paths — resolve via Engine.
    probe = Engine(ctx)
    roles_yaml_path = probe.paths["roles_path"]
    roles_bytes_before = open(roles_yaml_path, "rb").read()
    try:
        prompts = []
        # AIDE model, scope=all, worker_count=1, ask-before-merging=y,
        # architect="" (recommended), engineer=SESSION override (DIFFERS from
        # the roles.yaml declared model — proves session wins), reviewer-code
        # explicit.
        answers = ["", "1", "1", "y", "", "session-eng-override", "session-rev-override"]
        builtins.input = seeded_input(answers, prompts)
        with aide_stub({"aide": [{"advice": "persist-scenario"}]}):
            b = Bootup(ctx)
            eng, spawned = b.bootup()

        manifest = state.load(ctx)
        sm = manifest.get("session_models") or {}
        ok("PS1 (test:<journey_persist_session_store_only>): the per-role model "
           "answers persisted to the SESSION STORE (manifest['session_models'], "
           "under meta/agents/tron/) — architect=recommended, engineer=the "
           "session override, reviewer-code=the explicit override",
           sm.get("architect") == ROLE_MODEL_RECOMMENDED["architect"]
           and sm.get("engineer") == "session-eng-override"
           and sm.get("reviewer-code") == "session-rev-override",
           f"session_models={sm}")
        ok("PS2: the ask-before-merging answer persisted to the SAME session "
           "store (manifest['live_config']['ask_before_merging']=True)",
           (manifest.get("live_config") or {}).get("ask_before_merging") is True,
           f"live_config={manifest.get('live_config')}")
        roles_bytes_after = open(roles_yaml_path, "rb").read()
        ok("PS3 (THE WRITE-BOUNDARY KILLER — must be GREEN): the project-authored "
           "roles.yaml is BYTE-FOR-BYTE UNCHANGED — the journey answers went "
           "ONLY to the TRON-owned session store, NEVER the project config "
           "(BL-1 write boundary)",
           roles_bytes_after == roles_bytes_before,
           f"roles.yaml changed: {roles_bytes_before!r} -> {roles_bytes_after!r}")

        # THE CROSS-PROCESS KILLER: a FRESH Engine(ctx) — a new process's wake
        # tick — with an EMPTY in-memory _models override still resolves the
        # operator's session model choice off the persisted session store.
        fresh = Engine(ctx)
        ok("PS4: a fresh Engine's in-memory session override is empty (the "
           "durability gap the session store closes)",
           fresh._models == {}, f"_models={fresh._models}")
        fresh._manifest = state.load(ctx)   # what core.tick.tick sets each pass before spawn
        ok("PS5 (CROSS-PROCESS KILLER — must be GREEN): the fresh Engine "
           "resolves engineer to the SESSION override 'session-eng-override' — "
           "the session store WINS over roles.yaml's own declared "
           f"'{ENGINEER_DECLARED_MODEL}' (session answer survives the process "
           "boundary, layered by _model_for_role)",
           fresh._model_for_role("engineer") == "session-eng-override",
           f"got={fresh._model_for_role('engineer')!r}")
        ok("PS6: the fresh Engine resolves architect off the session store too "
           "(roles.yaml declares no architect model — session store is the "
           "ONLY source, and it has the recommended default the operator "
           "confirmed)",
           fresh._model_for_role("architect") == ROLE_MODEL_RECOMMENDED["architect"],
           f"got={fresh._model_for_role('architect')!r}")
    finally:
        builtins.input = real_input
        restore_spawn(real_spawn)


def scenario_model_resolution_layering():
    """Directly exercise `_model_for_role`'s three-source layering with
    hand-built manifests — the precise 'session wins, else roles.yaml, else
    None' contract, isolated from the whole bootup."""
    ctx = build_instance("layering")
    # (a) in-memory override (start(models=...)) wins over everything.
    eng = Engine(ctx)
    eng._models = {"engineer": "in-mem-override"}
    eng._manifest = {"session_models": {"engineer": "session-store-val"}}
    ok("ML1: the in-memory session override (this process's own start(models=)) "
       "wins over BOTH the session store and roles.yaml",
       eng._model_for_role("engineer") == "in-mem-override",
       f"got={eng._model_for_role('engineer')!r}")

    # (b) session store wins over roles.yaml when in-memory is empty.
    eng2 = Engine(ctx)
    eng2._manifest = {"session_models": {"engineer": "session-store-val"}}
    ok("ML2: with an empty in-memory override, the SESSION STORE wins over "
       "roles.yaml's declared engineer model",
       eng2._model_for_role("engineer") == "session-store-val",
       f"got={eng2._model_for_role('engineer')!r}")

    # (c) roles.yaml is the fallback when neither session source resolves.
    eng3 = Engine(ctx)
    eng3._manifest = {"session_models": {}}   # a persisted store that names NO engineer
    ok("ML3: with neither in-memory nor session-store an answer for it, the "
       "role falls back to roles.yaml's own declared model (the project "
       "default) — the session layer is additive, never destructive",
       eng3._model_for_role("engineer") == ENGINEER_DECLARED_MODEL,
       f"got={eng3._model_for_role('engineer')!r}")

    # (d) None when no source resolves at all (roles.yaml declares no model
    #     for architect either) — the fail-closed input validate_models guards.
    eng4 = Engine(ctx)
    eng4._manifest = {"session_models": {}}
    ok("ML4: a role with NO model in any of the three sources resolves to None "
       "(architect declares none in roles.yaml, none in either session layer) "
       "— exactly what validate_models fail-closes on at start",
       eng4._model_for_role("architect") is None,
       f"got={eng4._model_for_role('architect')!r}")


def main():
    scenario_sequence_frozen()
    scenario_model_recommendation()
    scenario_model_unresolved_fails_closed()
    scenario_staged_answer()
    scenario_scope_resolution()
    scenario_aide_bootup_advises()
    scenario_aide_fail_open_unaided()
    scenario_aide_runtime_escalation_nodes()
    scenario_journey_persist_session_store()
    scenario_model_resolution_layering()

    fails = [n for n, c, _ in _results if not c]
    for name, cond, detail in _results:
        mark = "PASS" if cond else "FAIL"
        line = f"[{mark}] {name}"
        if detail and not cond:
            line += f" :: {detail}"
        print(line)
    print(f"PASS ({len(_results) - len(fails)}/{len(_results)})")
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
