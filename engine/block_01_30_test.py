r"""block_01_30_test — the bootup model question + recommendation (block 01-30),
RESTORED by block 01-35 per ADR-0003 D-D (explicit amendment of ADR-0002 D4).

History: 01-30 added a per-role bootup model question (hardcoded {architect, other}
two-tier split), written into knobs.yaml's `worker_model` map. Block 01-33
(ADR-0002 D4, "fleet as config") retired it entirely in favor of `model = role.model`
resolved straight from the project-authored `meta/tron/roles.yaml` — this file was
rewritten at that point to ASSERT THE QUESTION'S ABSENCE. ADR-0003 D-D explicitly
amends D4: the operator-journey step was never re-authorized to be removed, so 01-35
restores it — this file is rewritten AGAIN, this time to assert the question's
PRESENCE and correctness, generalized past the old hardcoded two-tier split (01-33
made role identity project-declared, not engine-hardcoded; this restore follows suit —
every role roles.yaml declares gets its own question, not just "architect"/"other").

Covers (01-30 parity, adapted):
  AC-1  interactive `console.bootup` asks the model PER DECLARED ROLE, each with a
        recommended default (roles.yaml's own `model:` if set, else a built-in
        per-tier suggestion) the operator can confirm (blank -> default) or override;
        the answer resolves into `eng.st.live_config["worker_model"]` (never
        roles.yaml) BEFORE `eng.start()` — the earliest point any real spawn occurs.
  AC-2  an unresolvable/blank model for a role fails closed at the shared
        `fsm._spawn` / `jobs.spawn_runner` layer — no spawn on a default model.
  AC-3  `console.bootup(staged_model=...)` accepts a pre-staged per-role answer and
        issues NO model prompt at all (the other bootup questions still prompt
        normally — frozen journey); a staged role left blank/absent is never
        silently given the recommended default.
  AC-4  per-role resolution is independent: each role resolves from its OWN entry
        (session override, else roles.yaml); one role's answer never leaks to another.

This file focuses on the RESTORED QUESTION's own mechanics (01-30 parity). The
write-boundary-safety / precedence / fail-closed / AIDE-recommendation contract this
block (01-35) itself adds is covered separately in block_01_35_test.py.

Run: python3 engine/block_01_30_test.py   (exit 0 = pass).
"""
import os
import sys
import builtins

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import jobs                    # noqa: E402
import console                 # noqa: E402
from fsm import Engine         # noqa: E402
from state import State        # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _run_bootup_with_input(ctx, answers, staged_model=None, forbid_prefix=None):
    """Drive Console.bootup() with a canned `input()` sequence against a REAL Engine
    (the trivial roles.yaml fixture — engineer/reviewer-code/architect). `forbid_prefix`:
    if any prompt string starts with this, raise (proves that prompt was never issued).
    Returns (Console, prompts_seen).

    ADR-0003 D-J (01-35) added ONE more interactive prompt ahead of this file's own
    01-30-parity surface — "Model for AIDE" (AIDE's own model, a session knob,
    resolved before ND-01-08's advisory). It auto-accepts the shown default WITHOUT
    consuming from `answers` — this file's `answers` lists stay scoped to exactly the
    01-30 surface they were written against (scope/worker_count/ask-before-merging +
    the per-declared-role model loop), never renumbered for 01-35's own addition
    (covered in its own right by block_01_35_test.py)."""
    orig_input = builtins.input
    it = iter(answers)
    seen = []

    def fake_input(prompt=""):
        seen.append(prompt)
        if forbid_prefix and prompt.startswith(forbid_prefix):
            raise AssertionError(f"unexpected prompt issued: {prompt!r}")
        if prompt.startswith("Model for AIDE"):
            return ""              # accept AIDE's own built-in default; never consumes `it`
        return next(it)

    builtins.input = fake_input
    try:
        c = console.Console(ctx)
        c.bootup(staged_model=staged_model)
    finally:
        builtins.input = orig_input
    return c, seen


# ══ AC-1: interactive bootup asks the model per role, resolves before any spawn ══

def t1_console_carries_the_restored_recommendation_surface():
    """The restored surface (T1/T4): the named constants + methods 01-30 introduced
    and 01-33 removed are back."""
    ok("AC-1 console.py declares ROLE_MODEL_RECOMMENDED",
       hasattr(console, "ROLE_MODEL_RECOMMENDED"))
    ok("AC-1 console.py declares ROLE_MODEL_LABEL",
       hasattr(console, "ROLE_MODEL_LABEL"))
    ok("AC-1 Console has _ask_role_models", hasattr(console.Console, "_ask_role_models"))
    ok("AC-1 Console has _recommended_model", hasattr(console.Console, "_recommended_model"))


def t1_interactive_bootup_asks_model_per_declared_role_with_default():
    # `_ask_role_models` iterates roles in SORTED order — the trivial fixture's roles
    # (engineer/reviewer-code/architect) ask as: architect, engineer, reviewer-code.
    ctx, _ = build()
    _, prompts = _run_bootup_with_input(
        ctx, answers=["1", "2", "n", "opus-override", "", "custom-reviewer-model"])
    ok("AC-1 bootup prompts separately for the engineer role",
       any(p.startswith("Model for engineer") for p in prompts), f"prompts={prompts}")
    ok("AC-1 bootup prompts separately for the reviewer-code role",
       any(p.startswith("Model for reviewer-code") for p in prompts), f"prompts={prompts}")
    ok("AC-1 bootup prompts separately for the architect role",
       any(p.startswith("Model for architect") for p in prompts), f"prompts={prompts}")
    answers = State(ctx).live_config.get("worker_model")
    ok("AC-1 a blank answer (Enter) takes the shown recommended default (the role's "
       "own roles.yaml model, here 'test-model')",
       answers.get("engineer") == "test-model", f"answers={answers}")
    ok("AC-1 an explicit override is taken verbatim, not the default",
       answers.get("reviewer-code") == "custom-reviewer-model", f"answers={answers}")
    ok("AC-1 ...independently for a third role too",
       answers.get("architect") == "opus-override", f"answers={answers}")


def t1_model_resolves_into_live_config_before_eng_start():
    """The write happens strictly BEFORE eng.start() — the earliest point any real
    spawn could occur (fsm.start -> _spawn_architect -> _spawn)."""
    ctx, _ = build()
    # sorted role order: architect, engineer, reviewer-code.
    _run_bootup_with_input(
        ctx, answers=["1", "3", "y", "arch-answer", "eng-answer", "rev-answer"])
    live = State(ctx).live_config
    ok("AC-1 worker_model is the resolved per-role map, written before/at eng.start()",
       live.get("worker_model") == {"engineer": "eng-answer", "reviewer-code": "rev-answer",
                                     "architect": "arch-answer"},
       f"worker_model={live.get('worker_model')}")
    ok("AC-1 ...and the session actually started (bootup reached eng.start())",
       bool(live.get("worker_count")))


def t1_recommended_default_prefers_roles_yaml_declared_model():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    c = console.Console(ctx)
    ok("AC-1/T2 the recommended default is the role's OWN roles.yaml `model:` when set",
       c._recommended_model(eng, "engineer") == "test-model")
    ok("AC-1/T2 ...for every declared role, independently",
       c._recommended_model(eng, "architect") == "test-model")
    ok("AC-1/T2 an undeclared role falls back to the built-in per-tier suggestion "
       "(the 'other' tier — no spec_owner/persistent flag)",
       c._recommended_model(eng, "some-new-role") == console.ROLE_MODEL_RECOMMENDED["other"])


# ══ AC-2: unresolvable/blank model for a role fails closed — no spawn on a default ══

def t2_blank_model_for_a_role_fails_closed_no_spawn():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng.dry = False
    eng.st.live_config["worker_model"] = {}   # no session override for anyone
    eng.roles.roles["engineer"]["model"] = ""  # roles.yaml itself now blank too
    # sentry_test's own import sets TRON_WORKER_MODEL as a suite-wide ambient stub
    # (never a real model) — pop it here so the guard under test isn't masked by it,
    # exactly as the original 01-30 suite did.
    had_env = "TRON_WORKER_MODEL" in os.environ
    orig_env = os.environ.pop("TRON_WORKER_MODEL", None)
    spawned = []
    orig_popen = jobs.subprocess.Popen
    jobs.subprocess.Popen = lambda *a, **k: spawned.append(1)
    try:
        raised = False
        try:
            eng._spawn("ENG-BLANK", "engineer", block="A-01")
        except jobs.WorkerModelUnconfigured:
            raised = True
        ok("AC-2 a blank model (roles.yaml AND no session override) fails closed",
           raised, f"raised={raised}")
        ok("AC-2 the fail-closed guard fires BEFORE any process is spawned",
           spawned == [], f"spawned={spawned}")
    finally:
        jobs.subprocess.Popen = orig_popen
        if had_env:
            os.environ["TRON_WORKER_MODEL"] = orig_env


# ══ AC-3: staged answer — never a prompt, fail-closed preserved ══

def t3_staged_bootup_answer_skips_the_model_prompt_entirely():
    ctx, _ = build()
    _, prompts = _run_bootup_with_input(
        ctx, answers=["1", "3", "y"],
        staged_model={"engineer": "staged-eng", "reviewer-code": "staged-rev",
                      "architect": "staged-arch"},
        forbid_prefix="Model for")
    ok("AC-3 a staged bootup issues NO model prompt (other questions still prompt)",
       not any(p.startswith("Model for") for p in prompts)
       and any(p.startswith("worker_count") for p in prompts), f"prompts={prompts}")
    live = State(ctx).live_config
    ok("AC-3 the pre-staged per-role answer is written verbatim",
       live.get("worker_model") == {"engineer": "staged-eng", "reviewer-code": "staged-rev",
                                    "architect": "staged-arch"},
       f"worker_model={live.get('worker_model')}")


def t3_staged_bootup_missing_role_stays_unresolved_never_defaulted():
    ctx, _ = build()
    _run_bootup_with_input(
        ctx, answers=["1", "1", "n"],
        staged_model={"engineer": "staged-eng"},   # reviewer-code/architect omitted
        forbid_prefix="Model for")
    wm = State(ctx).live_config.get("worker_model")
    ok("AC-3 a staged answer missing a role is left None (never silently given the "
       "recommended default)",
       wm == {"engineer": "staged-eng", "reviewer-code": None, "architect": None},
       f"worker_model={wm}")


# ══ AC-4: per-role resolution is independent ══

def t4_each_role_resolves_from_its_own_entry_only():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    eng.st.live_config["worker_model"] = {"engineer": "eng-session", "architect": None}
    ok("AC-4 engineer resolves its OWN session override",
       eng._model_for_role("engineer") == "eng-session")
    ok("AC-4 architect (session None) falls through to roles.yaml's own model, "
       "NEVER borrowing engineer's session answer",
       eng._model_for_role("architect") == "test-model")
    ok("AC-4 reviewer-code (no session entry at all) also falls through to roles.yaml, "
       "independent of the other two roles' state",
       eng._model_for_role("reviewer-code") == "test-model")


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
