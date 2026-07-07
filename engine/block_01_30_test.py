r"""block_01_30_test — re-add the bootup model startup question WITHOUT reintroducing
the 01-21 credit-drain bug, this time PER ROLE (block 01-30,
ADR-tron-post-wave1-enhancements.md §D; T2 decided: per-role, not single-global).

Covers:
  AC-1  interactive `console.bootup` asks the model PER ROLE (architect / other), each
        with a recommended default the operator can confirm (blank -> default) or
        override, and the answer resolves into `eng.knobs["worker_model"]` BEFORE
        `eng.start()` — the earliest point any real spawn could occur.
  AC-2  an unresolvable/blank model for the resolving role fails closed at the shared
        `fsm._spawn` / `jobs.spawn_runner` layer — no spawn on a default model, and no
        process is ever launched before the refusal.
  AC-3  (a) `console.bootup(staged_model=...)` accepts a pre-staged per-role answer and
        issues NO model prompt at all (the other bootup questions are untouched — they
        still prompt); a staged role left blank/absent is never silently given the
        recommended default. (b) SEPARATELY, the headless path — a caller that never
        goes through `console.bootup` at all (calls `eng._spawn`/`eng.start` directly,
        exactly what `bootstrap.py`-style harnesses do) — resolves the model from
        `knobs.yaml` alone, issues no prompt, and fails closed the same way on absence.
  AC-4  per-role resolution is independent: architect and "other" (engineer, reviewer,
        ...) each resolve from their OWN knobs key; one role being configured never
        lets a different role borrow its value, and each fails closed on its OWN
        absence regardless of the other's state.

Standalone runner convention (exit 0 = pass, no tokens, no network, no real `claude` —
every spawn below either fakes `jobs.spawn_runner`/`subprocess.Popen` or proves the
REAL fail-closed guard fires before either would ever be reached).

Run: python3 engine/block_01_30_test.py   (exit 0 = pass).
"""
import os
import sys
import types
import builtins

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import jobs                    # noqa: E402
import console                 # noqa: E402
from fsm import Engine         # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── a minimal Engine stand-in for console.bootup() (AC-1/AC-3a): proves CONSOLE's own
# ── ordering/prompting logic without needing a full working trunk/pipeline fixture ──
def _fake_engine_class():
    class FakeEngine:
        instances = []

        def __init__(self, ctx):
            self.ctx = ctx
            self.knobs = {}
            self.project = {}
            self.st = types.SimpleNamespace(live_config={})
            self.scope_calls = []
            self.model_at_start = "UNSET"     # sentinel: start() never called if still this
            FakeEngine.instances.append(self)

        def set_scope(self, mode, value=None):
            self.scope_calls.append((mode, value))

        def start(self, worker_count):
            # AC-1: snapshot worker_model AT THE MOMENT start() (the earliest a real
            # spawn could occur, per fsm.start -> _h_bootup -> _spawn_architect -> _spawn)
            # is invoked — proves resolution happened strictly BEFORE any spawn.
            self.model_at_start = dict(self.knobs.get("worker_model") or {})

    return FakeEngine


def _run_bootup_with_input(ctx, answers, staged_model=None, forbid_prefix=None):
    """Drive Console.bootup() with a canned `input()` sequence against a FakeEngine.
    `forbid_prefix`: if any prompt string starts with this, raise (proves that prompt
    was never issued). Returns (FakeEngine instance, prompts_seen)."""
    FakeEngine = _fake_engine_class()
    orig_engine, orig_input = console.Engine, builtins.input
    console.Engine = FakeEngine
    it = iter(answers)
    seen = []

    def fake_input(prompt=""):
        seen.append(prompt)
        if forbid_prefix and prompt.startswith(forbid_prefix):
            raise AssertionError(f"unexpected prompt issued: {prompt!r}")
        return next(it)

    builtins.input = fake_input
    try:
        c = console.Console(ctx)
        c.bootup(staged_model=staged_model)
    finally:
        builtins.input = orig_input
        console.Engine = orig_engine
    return FakeEngine.instances[-1], seen


# ══ AC-1: interactive bootup asks the model per role, resolves before any spawn ══

def t1_interactive_bootup_asks_model_per_role_with_default():
    ctx, _ = build()
    eng, prompts = _run_bootup_with_input(
        ctx, answers=["1", "2", "n", "", "custom-other-model"])
    ok("AC-1 bootup prompts separately for the architect role",
       any(p.startswith("Model for architect") for p in prompts), f"prompts={prompts}")
    ok("AC-1 bootup prompts separately for the other (engineer/reviewer) roles",
       any(p.startswith("Model for engineers/reviewers") for p in prompts), f"prompts={prompts}")
    ok("AC-1 a blank architect answer (Enter) takes the shown recommended default",
       eng.knobs["worker_model"]["architect"] == console.ROLE_MODEL_RECOMMENDED["architect"],
       f"knobs={eng.knobs.get('worker_model')}")
    ok("AC-1 an explicit override is taken verbatim, not the default",
       eng.knobs["worker_model"]["other"] == "custom-other-model",
       f"knobs={eng.knobs.get('worker_model')}")


def t1_model_resolves_into_knobs_before_eng_start():
    ctx, _ = build()
    eng, _ = _run_bootup_with_input(
        ctx, answers=["1", "3", "y", "opus-answer", "sonnet-answer"])
    ok("AC-1 eng.start() was reached (bootup completed)", eng.model_at_start != "UNSET")
    ok("AC-1 worker_model was ALREADY the resolved per-role map at the moment eng.start() "
       "ran (the earliest point any real spawn happens) — resolution strictly precedes it",
       eng.model_at_start == {"architect": "opus-answer", "other": "sonnet-answer"},
       f"model_at_start={eng.model_at_start}")


def t1_recommended_default_prefers_project_declared_model():
    ctx, _ = build()
    FakeEngine = _fake_engine_class()
    orig_engine = console.Engine
    console.Engine = FakeEngine
    try:
        c = console.Console(ctx)
        eng = FakeEngine(ctx)
        eng.project = {"agents": [{"role": "architect", "file": "a.md", "model": "project-opus"},
                                  {"role": "engineer", "file": "e.md", "model": "project-sonnet"}]}
        ok("AC-1/T2 the recommended default prefers the project's own declared "
           "agents[].model over the engine's built-in suggestion (architect)",
           c._recommended_model(eng, "architect") == "project-opus")
        ok("AC-1/T2 ...and for 'other' too (any non-architect role's declared model)",
           c._recommended_model(eng, "other") == "project-sonnet")
        eng.project = {}
        ok("AC-1/T2 absent a project declaration, the engine's built-in suggestion is used",
           c._recommended_model(eng, "architect") == console.ROLE_MODEL_RECOMMENDED["architect"]
           and c._recommended_model(eng, "other") == console.ROLE_MODEL_RECOMMENDED["other"])
    finally:
        console.Engine = orig_engine


# ══ AC-2: unresolvable/blank model fails closed — no spawn on a default model ══

def t2_blank_model_for_resolving_role_fails_closed_no_spawn():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.knobs["worker_model"] = {"architect": "opus-real", "other": ""}   # "other" BLANK
    had_env = "TRON_WORKER_MODEL" in os.environ
    orig_env = os.environ.pop("TRON_WORKER_MODEL", None)   # simulate the override unset too
    spawned = []
    orig_popen = jobs.subprocess.Popen
    jobs.subprocess.Popen = lambda *a, **k: spawned.append(1)
    try:
        raised = False
        try:
            eng._spawn("ENG-BLANK", "spawn.engineer", "engineer", block="A-01")
        except jobs.WorkerModelUnconfigured:
            raised = True
        ok("AC-2 a blank-string model for the resolving role fails closed (never treated "
           "as a configured value)", raised, f"raised={raised}")
        ok("AC-2 the fail-closed guard fires BEFORE any process is spawned",
           spawned == [], f"spawned={spawned}")
    finally:
        jobs.subprocess.Popen = orig_popen
        if had_env:
            os.environ["TRON_WORKER_MODEL"] = orig_env


def t2_missing_worker_model_knob_entirely_fails_closed():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.knobs.pop("worker_model", None)                    # not even declared
    had_env = "TRON_WORKER_MODEL" in os.environ
    orig_env = os.environ.pop("TRON_WORKER_MODEL", None)
    spawned = []
    orig_popen = jobs.subprocess.Popen
    jobs.subprocess.Popen = lambda *a, **k: spawned.append(1)
    try:
        raised = False
        try:
            eng._spawn("ENG-MISSING", "spawn.engineer", "engineer", block="A-01")
        except jobs.WorkerModelUnconfigured:
            raised = True
        ok("AC-2 worker_model missing from knobs entirely also fails closed (never "
           "guessed at / never a legacy-shape passthrough)", raised, f"raised={raised}")
        ok("AC-2 ...and again, before any process is spawned", spawned == [], f"spawned={spawned}")
    finally:
        jobs.subprocess.Popen = orig_popen
        if had_env:
            os.environ["TRON_WORKER_MODEL"] = orig_env


# ══ AC-3: staged answer / headless path — never a prompt, fail-closed preserved ══

def t3_staged_bootup_answer_skips_the_model_prompt_entirely():
    ctx, _ = build()
    eng, prompts = _run_bootup_with_input(
        ctx, answers=["1", "3", "y"],
        staged_model={"architect": "staged-arch-model", "other": "staged-other-model"},
        forbid_prefix="Model for")
    ok("AC-3 a staged bootup issues NO model prompt (other questions still prompt normally)",
       not any(p.startswith("Model for") for p in prompts)
       and any(p.startswith("worker_count") for p in prompts), f"prompts={prompts}")
    ok("AC-3 the pre-staged per-role answer is written into knobs verbatim",
       eng.knobs.get("worker_model") == {"architect": "staged-arch-model",
                                         "other": "staged-other-model"},
       f"knobs={eng.knobs.get('worker_model')}")


def t3_staged_bootup_missing_role_stays_unresolved_never_defaulted():
    ctx, _ = build()
    eng, _ = _run_bootup_with_input(
        ctx, answers=["1", "1", "n"],
        staged_model={"architect": "staged-arch-model"},   # "other" deliberately omitted
        forbid_prefix="Model for")
    ok("AC-2/AC-3 a staged answer missing a role is left None (never silently given the "
       "recommended default — the fail-closed guard downstream is what must catch it)",
       eng.knobs.get("worker_model") == {"architect": "staged-arch-model", "other": None},
       f"knobs={eng.knobs.get('worker_model')}")


def t3_headless_path_resolves_via_knobs_not_prompt_and_fails_closed():
    """The headless path (02-10's harness / bootstrap-style caller) never touches
    console.bootup at all — it calls eng._spawn/eng.start directly. Prove: (a) it never
    prompts (input() poisoned to fail the test if called), (b) with knobs.worker_model
    unresolved it fails closed exactly like the interactive path's downstream guard."""
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.knobs["worker_model"] = {"architect": None, "other": None}   # never populated
    had_env = "TRON_WORKER_MODEL" in os.environ
    orig_env = os.environ.pop("TRON_WORKER_MODEL", None)
    orig_input = builtins.input
    poisoned = []

    def poison_input(prompt=""):
        poisoned.append(prompt)
        raise AssertionError("the headless path must never prompt")

    builtins.input = poison_input
    spawned = []
    orig_popen = jobs.subprocess.Popen
    jobs.subprocess.Popen = lambda *a, **k: spawned.append(1)
    try:
        raised = False
        try:
            eng._spawn("ENG-HEADLESS", "spawn.engineer", "engineer", block="A-01")
        except jobs.WorkerModelUnconfigured:
            raised = True
        ok("AC-3 headless direct eng._spawn (bypassing console.bootup entirely) resolves "
           "the model from knobs alone and fails closed on absence",
           raised, f"raised={raised}")
        ok("AC-3 ...with NO prompt ever issued along that path", poisoned == [], f"poisoned={poisoned}")
        ok("AC-3 ...and no process ever spawned", spawned == [], f"spawned={spawned}")
    finally:
        builtins.input = orig_input
        jobs.subprocess.Popen = orig_popen
        if had_env:
            os.environ["TRON_WORKER_MODEL"] = orig_env


# ══ AC-4: per-role resolution is independent, each fails closed on its OWN absence ══

def t4_architect_and_other_resolve_independently():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.knobs["worker_model"] = {"architect": "opus-strong", "other": "sonnet-fast"}
    captured = []
    orig = jobs.spawn_runner

    def fake_spawn(*a, **k):
        captured.append((a[0], k.get("model")))
        return {"session_id": "s", "worker_id": a[0]}

    jobs.spawn_runner = fake_spawn
    try:
        eng._spawn_architect()
        eng._spawn("ENG-1", "spawn.engineer", "engineer", block="A-01")
        eng._spawn("REV-1", "spawn.reviewer", "reviewer", rtype="code")
    finally:
        jobs.spawn_runner = orig
    got = dict(captured)
    ok("AC-4 architect resolves its OWN tier (never 'other')",
       got.get("ARCH-PERSIST") == "opus-strong", f"got={got}")
    ok("AC-4 engineer resolves the shared 'other' tier",
       got.get("ENG-1") == "sonnet-fast", f"got={got}")
    ok("AC-4 reviewer resolves the shared 'other' tier too (same rule as engineer, "
       "independent of the architect's own tier)", got.get("REV-1") == "sonnet-fast", f"got={got}")


def t4_each_role_fails_closed_independently_of_the_other():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng.dry = False
    had_env = "TRON_WORKER_MODEL" in os.environ
    orig_env = os.environ.pop("TRON_WORKER_MODEL", None)
    spawned = []
    orig_popen = jobs.subprocess.Popen
    jobs.subprocess.Popen = lambda *a, **k: spawned.append(1)
    orig_spawn_runner = jobs.spawn_runner
    try:
        # architect configured, "other" NOT -> architect spawns fine, engineer refuses.
        eng.knobs["worker_model"] = {"architect": "opus-strong", "other": None}
        captured = {}

        def fake_spawn(*a, **k):
            captured.update(k)
            return {"session_id": "s", "worker_id": a[0]}

        jobs.spawn_runner = fake_spawn
        try:
            eng._spawn_architect()
        finally:
            jobs.spawn_runner = orig_spawn_runner
        ok("AC-4 architect configured / other unset: architect spawn succeeds on its own tier",
           captured.get("model") == "opus-strong", f"captured={captured}")

        raised = False
        try:
            eng._spawn("ENG-2", "spawn.engineer", "engineer", block="A-02")
        except jobs.WorkerModelUnconfigured:
            raised = True
        ok("AC-4 ...but engineer ('other' tier, unset) still fails closed — architect's "
           "resolved value is NEVER borrowed by a different role",
           raised, f"raised={raised}")

        # flip: "other" configured, architect NOT -> the reverse must hold too.
        eng.knobs["worker_model"] = {"architect": None, "other": "sonnet-fast"}
        captured2 = {}

        def fake_spawn2(*a, **k):
            captured2.update(k)
            return {"session_id": "s", "worker_id": a[0]}

        jobs.spawn_runner = fake_spawn2
        try:
            eng._spawn("ENG-3", "spawn.engineer", "engineer", block="A-03")
        finally:
            jobs.spawn_runner = orig_spawn_runner
        ok("AC-4 other configured / architect unset: engineer spawn succeeds on its own tier",
           captured2.get("model") == "sonnet-fast", f"captured2={captured2}")

        raised2 = False
        try:
            eng._spawn_architect()
        except jobs.WorkerModelUnconfigured:
            raised2 = True
        ok("AC-4 ...and architect fails closed when only 'other' is configured",
           raised2, f"raised2={raised2}")
        ok("AC-4 no process was ever spawned on any of the refused calls",
           spawned == [], f"spawned={spawned}")
    finally:
        jobs.spawn_runner = orig_spawn_runner
        jobs.subprocess.Popen = orig_popen
        if had_env:
            os.environ["TRON_WORKER_MODEL"] = orig_env


def main():
    for fn in sorted(k for k in globals() if k.startswith(("t1_", "t2_", "t3_", "t4_"))):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
