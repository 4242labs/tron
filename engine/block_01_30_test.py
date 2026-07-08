r"""block_01_30_test — SUPERSEDED by block 01-33 (ADR-0002 D4).

01-30 re-added a bootup model question, asked PER ROLE via a hardcoded two-tier
split (`architect` / `other`), with the answer written into `knobs.yaml`'s
`worker_model` map. Block 01-33 (ADR-0002 Decision 4, "fleet as config") retires
that mechanism entirely: `model = role.model` now resolves straight out of the
project-authored `meta/tron/roles.yaml` — no operator prompt, no two-tier split,
no knobs.yaml `worker_model` map, no hardcoded "architect"/"other" keys anywhere
in engine code. "Config is the answer source; ask only when config is silent" —
and since RolesConfig validates every role's model FAIL-CLOSED at construction
(missing/blank/non-string is boot-fatal, loud and named), config is never silent:
a bad roles.yaml refuses to boot at all, before the bootup Q&A even starts.

This file is kept (rather than deleted) as the historical record of what it once
covered, rewritten to assert the CURRENT reality: `console.bootup` asks no model
question at all, and `fsm._model_for_role` / `roles.RolesConfig` are the one and
only resolution + fail-closed path. Block 01-33's own suite
(block_01_33_test.py) is the authoritative coverage for the fail-closed boot
matrix (AC-3) and per-role independence (AC-1/AC-2/AC-4/AC-5); this file only
guards the narrow regression "the retired prompt never comes back."

Run: python3 engine/block_01_30_test.py   (exit 0 = pass).
"""
import os
import sys
import builtins

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import console                 # noqa: E402
from fsm import Engine          # noqa: E402
from sentry_test import build, started  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def t1_console_source_carries_no_model_question_machinery():
    """The retired prompt surface: no ROLE_MODEL_RECOMMENDED/ROLE_MODEL_LABEL constants,
    no _ask_role_models/_recommended_model methods — the model question is GONE, not
    merely unreachable."""
    ok("T1 console.py declares no ROLE_MODEL_RECOMMENDED constant",
       not hasattr(console, "ROLE_MODEL_RECOMMENDED"))
    ok("T1 console.py declares no ROLE_MODEL_LABEL constant",
       not hasattr(console, "ROLE_MODEL_LABEL"))
    ok("T1 Console has no _ask_role_models method",
       not hasattr(console.Console, "_ask_role_models"))
    ok("T1 Console has no _recommended_model method",
       not hasattr(console.Console, "_recommended_model"))


def t2_bootup_never_prompts_for_a_model():
    """Drive the real (non-staged) bootup Q&A end to end against a real Engine/roles.yaml
    fixture (sentry_test.build already seeds a valid trivial roles.yaml — see
    block_01_33_test.py's shared fixture) and prove no 'Model for' prompt is ever issued."""
    ctx, _ = build()
    seen = []
    orig_input = builtins.input

    def fake_input(prompt=""):
        seen.append(prompt)
        if prompt.startswith("Model for"):
            raise AssertionError(f"retired model prompt resurfaced: {prompt!r}")
        # worker_count / ask-before-merging / scope answers, in bootup()'s order.
        if prompt.startswith("  [1]"):
            return "1"
        if "worker_count" in prompt:
            return "1"
        if "Inform you" in prompt:
            return "n"
        return ""

    builtins.input = fake_input
    try:
        c = console.Console(ctx)
        c.bootup()
    finally:
        builtins.input = orig_input
    ok("T2 bootup never prompts for a model (config is the sole source, ADR-0002 D4)",
       not any(p.startswith("Model for") for p in seen), f"prompts={seen}")


def t3_model_for_role_resolves_from_roles_yaml():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    ok("T3 _model_for_role resolves the trivial scaffold's engineer model from roles.yaml",
       eng._model_for_role("engineer") == eng.roles.model_for("engineer")
       and eng._model_for_role("engineer"),
       f"model={eng._model_for_role('engineer')!r}")
    ok("T3 _model_for_role resolves the architect model from roles.yaml too, independently",
       eng._model_for_role("architect") == eng.roles.model_for("architect")
       and eng._model_for_role("architect"),
       f"model={eng._model_for_role('architect')!r}")
    ok("T3 an unknown role resolves to None (no default, no crash)",
       eng._model_for_role("no-such-role") is None)


def main():
    for fn in sorted(k for k in globals() if k.startswith(("t1_", "t2_", "t3_"))):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
