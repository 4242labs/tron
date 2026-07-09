r"""block_01_35_test — restore the operator bootup journey: model question + AIDE as
a REAL LLM (block 01-35, ADR-0003 D-D + D-J — an explicit amendment of ADR-0002 D4,
and the D-J correction of the in-flight `feat-01-35` deterministic stub).

Context: block 01-33 (ADR-0002 D4, "fleet as config") removed the 01-30 bootup model
question + recommendation — an operator-journey step never re-authorized removed.
ADR-0003 D-D restores it: (T1) the model question + recommendation, per role,
01-30-parity; (T2) write-boundary-safe persistence — the answer lives ONLY in a
TRON-owned session store (this instance's own MANIFEST live_config, under
meta/agents/tron/), NEVER in the project-authored meta/tron/roles.yaml — with the
session answer layered over `role.model` (session wins for the session; else
role.model; boot-fatal only if neither resolves); (T3) a SINGLE architect this
version — no `architect_count` knob/prompt is added; (T4) AIDE restored as a REAL
LLM (`judge.call("aide")`, reading Project Docs as context) at the bootup nodes
ND-01-08 SET SCOPE / ND-01-09 SET COUNTS / ND-01-14 RESOLVE — NEVER a deterministic
stand-in. The prior `feat-01-35` build's `console._aide_recommend_block` (a
deterministic, no-model-call heuristic) is DELETED along with its own test, per the
operator hard rule: AIDE is an LLM by design, never a heuristic.

Standalone runner convention (exit 0 = pass, no tokens, no network, no real `claude`
— TRON_DRY + no TRON_JUDGE_STUB makes `judge._call_llm` a fast no-op; AC-5's own
"real LLM call" assertions monkeypatch `judge._call_llm` directly instead, which
bypasses that dry guard entirely).

Covers this block's own acceptance criteria
(blocks/01-35-restore-operator-bootup-journey.md):
  AC-1 test:<bootup_model_question_restored> — interactive bootup asks the model
       question (01-30 parity); the headless path (a harness calling eng.start()
       directly, exactly cmd_start's own shape) auto-answers from staged knobs and
       never prompts / never hangs.
  AC-2 test:<model_answer_write_boundary> — the answer persists ONLY under
       meta/agents/tron/ (this instance's own MANIFEST); roles.yaml is never touched
       (byte-identical, mtime-identical) and no engine write during bootup lands
       outside TRON's own sealed instance dir.
  AC-3 test:<model_precedence_fail_closed> — session answer wins for the session over
       a stale role.model; absent a session answer, role.model resolves as before;
       absent BOTH, boot is fatal (loud, named); a session answer alone can rescue an
       otherwise-boot-fatal missing roles.yaml model.
  AC-4 test:<single_architect_no_count_knob> — the reset's `architect:
       cardinality:1, spec_owner:true` boot invariant is unchanged; bootup asks
       `worker_count` only — no `architect_count`/"#architects" prompt exists
       anywhere in console.py.
  AC-5 test:<aide_bootup_is_real_llm_not_heuristic> — AIDE is a REAL LLM at
       ND-01-08/09/14: a real `judge.call("aide")` fires (mocked at `judge._call_llm`)
       carrying Project Docs context (context.md+pipeline.md+the relevant block
       doc(s)); `_aide_recommend_block` and its own deterministic test are GONE;
       AIDE's model is fail-open (never boot-fatal); a runtime-unavailable AIDE call
       degrades to "proceed unaided", never a heuristic answer.
AC-6 (journey-frozen byte-diff of scope/worker_count/ask-before-merging) is
`manual_by:engineer`, verified in the PR body, not exercised here. AC-7 is
`manual_by:operator` (live smoke).

01-30 parity mechanics (the restored question's own per-role ask/default/override
shape) are covered in block_01_30_test.py; this file covers the NEW contract 01-35
itself adds.

Run: python3 engine/block_01_35_test.py   (exit 0 = pass).
"""
import io
import os
import sys
import copy
import contextlib
import builtins

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import util                      # noqa: E402
import judge                     # noqa: E402
import console                   # noqa: E402
import roles as roles_mod        # noqa: E402
from fsm import Engine           # noqa: E402
from state import State          # noqa: E402
from sentry_test import build, started, TRIVIAL_ROLES  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _drive_bootup(ctx, answers, staged_model=None):
    orig_input = builtins.input
    it = iter(answers)
    builtins.input = lambda prompt="": next(it)
    try:
        console.Console(ctx).bootup(staged_model=staged_model)
    finally:
        builtins.input = orig_input


# ══════════════════════════════════════════════════════════════════════════
# AC-1 test:<bootup_model_question_restored>
# ══════════════════════════════════════════════════════════════════════════

def test_bootup_model_question_restored_interactive_and_headless():
    # (a) interactive: the question IS asked, with a recommended default shown.
    ctx, _ = build()
    seen = []
    orig_input = builtins.input

    def fake_input(prompt=""):
        seen.append(prompt)
        if prompt.startswith("Model for"):
            return ""     # accept every recommended default
        if prompt.startswith("  [1]"):
            return "1"
        if "worker_count" in prompt:
            return "1"
        if "Inform you" in prompt:
            return "n"
        return ""

    builtins.input = fake_input
    try:
        console.Console(ctx).bootup()
    finally:
        builtins.input = orig_input
    ok("AC-1 the interactive bootup DOES ask a model question (01-30 parity restored)",
       any(p.startswith("Model for") for p in seen), f"seen={seen}")
    ok("AC-1 ...with a recommended default shown in the prompt (bracketed)",
       any("[test-model]" in p for p in seen), f"seen={seen}")

    # (b) headless: a harness calling eng.start() directly (bypassing console entirely
    # — exactly cmd_start's own shape) with the model pre-staged in the session store
    # never prompts and never hangs.
    ctx2, _ = build()
    eng = Engine(ctx2)
    eng.st.live_config["worker_model"] = {"engineer": "staged-engineer",
                                          "reviewer-code": "staged-reviewer",
                                          "architect": "staged-architect"}

    def poison_input(prompt=""):
        raise AssertionError(f"the headless path must never prompt: {prompt!r}")

    orig_input2 = builtins.input
    builtins.input = poison_input
    try:
        eng.start(1)
    finally:
        builtins.input = orig_input2
    ok("AC-1 the headless path (direct eng.start(), no console) auto-answers from "
       "staged knobs with ZERO prompts and does not hang",
       bool(eng.st.data.get("session", {}).get("started_at")))


# ══════════════════════════════════════════════════════════════════════════
# AC-2 test:<model_answer_write_boundary>
# ══════════════════════════════════════════════════════════════════════════

def test_model_answer_write_boundary():
    ctx, repo = build()
    roles_path = os.path.join(repo, "meta", "tron", "roles.yaml")
    with open(roles_path, "rb") as f:
        before_bytes = f.read()
    before_mtime = os.path.getmtime(roles_path)

    written_paths = []
    orig_atomic = util.atomic_write
    orig_append = util.append_jsonl

    def spy_atomic(path, text):
        written_paths.append(os.path.abspath(path))
        return orig_atomic(path, text)

    def spy_append(path, obj):
        written_paths.append(os.path.abspath(path))
        return orig_append(path, obj)

    util.atomic_write = spy_atomic
    util.append_jsonl = spy_append
    try:
        _drive_bootup(ctx, answers=["1", "2", "n"],
                      staged_model={"engineer": "override-eng", "reviewer-code": "override-rev",
                                    "architect": "override-arch"})
    finally:
        util.atomic_write = orig_atomic
        util.append_jsonl = orig_append

    with open(roles_path, "rb") as f:
        after_bytes = f.read()
    after_mtime = os.path.getmtime(roles_path)
    ok("AC-2 roles.yaml content is byte-for-byte unchanged after a full bootup + "
       "model-answer run", before_bytes == after_bytes)
    ok("AC-2 roles.yaml was never even reopened for write (mtime unchanged)",
       before_mtime == after_mtime)
    ok("AC-2 no engine write during bootup ever targeted roles.yaml's path",
       os.path.abspath(roles_path) not in written_paths, f"written={written_paths}")

    ctx_dir = os.path.abspath(ctx.dir)
    outside = [p for p in written_paths
               if not (p == ctx_dir or p.startswith(ctx_dir + os.sep))]
    ok("AC-2 every write during bootup landed under TRON's own sealed instance dir "
       "(the meta/agents/tron/ equivalent — ctx.dir), none in the project repo",
       outside == [], f"outside={outside}")

    live = State(ctx).live_config
    ok("AC-2 the session model answer DID persist — into the TRON-owned MANIFEST "
       "(ctx.state, under ctx.dir) — proving it went somewhere real, just never "
       "roles.yaml",
       live.get("worker_model") == {"engineer": "override-eng", "reviewer-code": "override-rev",
                                    "architect": "override-arch"},
       f"worker_model={live.get('worker_model')}")
    ok("AC-2 the durable store IS ctx.state (manifest.yaml) — TRON's own instance dir",
       os.path.abspath(ctx.state).startswith(ctx_dir))


# ══════════════════════════════════════════════════════════════════════════
# AC-3 test:<model_precedence_fail_closed>
# ══════════════════════════════════════════════════════════════════════════

def test_model_precedence_fail_closed():
    ctx, _ = build()
    eng = Engine(ctx); started(eng)
    # (a) session answer overrides a stale role.model, for the session.
    eng.st.live_config["worker_model"] = {"engineer": "session-wins"}
    ok("AC-3 a session answer overrides roles.yaml's role.model for the session",
       eng._model_for_role("engineer") == "session-wins")
    # (b) no session answer -> falls through to role.model, exactly as before.
    eng.st.live_config["worker_model"] = {}
    ok("AC-3 with no session answer, the dispatcher reads role.model as today",
       eng._model_for_role("engineer") == eng.roles.model_for("engineer") == "test-model")

    # (c) neither a session answer nor a config model -> boot-fatal (fail-closed).
    ctx2, repo2 = build()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["engineer"]["model"] = ""
    util.save_yaml(os.path.join(repo2, "meta", "tron", "roles.yaml"), doc)
    eng2 = Engine(ctx2)
    eng2.st.live_config["worker_count"] = 1
    raised, msg = False, ""
    try:
        eng2.start(1)
    except roles_mod.RolesError as e:
        raised, msg = True, str(e)
    ok("AC-3 neither a session answer nor a resolvable roles.yaml model is boot-fatal "
       "(D4's fail-closed preserved) — loud, named",
       raised and "engineer" in msg, f"raised={raised} msg={msg}")

    # (d) ...but a session answer alone RESCUES that same missing config — boots clean.
    ctx3, repo3 = build()
    util.save_yaml(os.path.join(repo3, "meta", "tron", "roles.yaml"), doc)
    eng3 = Engine(ctx3)
    eng3.st.live_config["worker_count"] = 1
    eng3.st.live_config["worker_model"] = {"engineer": "rescued-by-session"}
    rescued_ok = True
    try:
        eng3.start(1)
    except roles_mod.RolesError as e:
        rescued_ok = False
    ok("AC-3 a session answer rescues an otherwise-boot-fatal missing config model",
       rescued_ok)
    ok("AC-3 ...and the rescued session value is what actually resolves",
       eng3._model_for_role("engineer") == "rescued-by-session")

    # (e) sanity: RolesConfig constructed with NO session context still requires
    # roles.yaml's own model (unconditional backstop — validate_models(None)).
    rc = roles_mod.RolesConfig(doc["roles"], repo2)
    no_session_raised = False
    try:
        rc.validate_models()
    except roles_mod.RolesError:
        no_session_raised = True
    ok("AC-3 RolesConfig.validate_models with no session override matches pre-D-D "
       "behavior exactly (roles.yaml alone must supply every role's model)",
       no_session_raised)


# ══════════════════════════════════════════════════════════════════════════
# AC-4 test:<single_architect_no_count_knob>
# ══════════════════════════════════════════════════════════════════════════

def test_single_architect_no_count_knob():
    # (a) the reset's `architect: cardinality:1, spec_owner:true` boot invariant is
    # unchanged — exactly one spec_owner role is boot-enforced (roles.py, untouched
    # by this block), and it resolves via roles.spec_owner (never a hardcoded literal).
    ctx, repo = build()
    eng = Engine(ctx)
    ok("AC-4 exactly one spec_owner role is boot-enforced and resolves",
       eng.roles.spec_owner == "architect")
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["architect"]["spec_owner"] = False
    doc["roles"]["engineer"]["spec_owner"] = True
    doc["roles"]["reviewer-code"]["spec_owner"] = True
    two_owners_raised = False
    try:
        roles_mod.RolesConfig(doc["roles"], repo)   # real fixture root -> personas resolve;
        # isolates the failure to the spec_owner-count check, not a missing-persona one.
    except roles_mod.RolesError:
        two_owners_raised = True
    ok("AC-4 more than one spec_owner (a de-facto multi-architect config) is still "
       "boot-fatal — the reset's cardinality:1 invariant is untouched by this block",
       two_owners_raised)

    # (b) bootup asks worker_count only — no architect_count / "how many architects"
    # prompt exists anywhere.
    seen = []
    orig_input = builtins.input

    def fake_input(prompt=""):
        seen.append(prompt)
        if prompt.startswith("Model for"):
            return ""
        if prompt.startswith("  [1]"):
            return "1"
        if "worker_count" in prompt:
            return "1"
        if "Inform you" in prompt:
            return "n"
        return ""

    builtins.input = fake_input
    try:
        console.Console(ctx).bootup()
    finally:
        builtins.input = orig_input
    ok("AC-4 bootup never asks an architect_count/#architects question",
       not any("architect_count" in p or "how many architect" in p.lower() for p in seen),
       f"seen={seen}")
    ok("AC-4 bootup asks worker_count exactly once (the sole concurrency knob asked)",
       sum("worker_count" in p for p in seen) == 1, f"seen={seen}")

    # (c) the console source itself defines no architect_count knob/prompt at all
    # (this block must not have added one — ADR-0003 D-D+D-J, BLOCKER-2 resolved).
    with open(os.path.join(HERE, "console.py")) as fh:
        console_src = fh.read()
    ok("AC-4 console.py source contains no architect_count knob/prompt",
       "architect_count" not in console_src)


# ══════════════════════════════════════════════════════════════════════════
# AC-5 test:<aide_bootup_is_real_llm_not_heuristic>
# ══════════════════════════════════════════════════════════════════════════

def test_aide_is_a_real_llm_not_a_heuristic():
    # (a) the deterministic stub + its call site are GONE — deleted, not just unused.
    ok("AC-5 Console._aide_recommend_block no longer exists (T4: deleted)",
       not hasattr(console.Console, "_aide_recommend_block"))
    with open(os.path.join(HERE, "console.py")) as fh:
        console_src = fh.read()
    ok("AC-5 console.py source contains no _aide_recommend_block definition/call "
       "at all (the deterministic stub is fully removed, not merely dead code)",
       "_aide_recommend_block" not in console_src)

    # (b) ND-01-08 SET SCOPE: a REAL judge.call("aide") fires — mocked at the lowest
    # chokepoint (judge._call_llm) so this proves the SHAPE of the real call (tool,
    # context, model) without spending a token. The context carries Project Docs:
    # context.md + pipeline.md + the relevant (dispatchable) block doc(s).
    ctx, repo = build()   # seeds A-01/A-02/A-03, all to-do, no deps (sentry_test default)
    with open(os.path.join(repo, "meta", "context.md"), "w") as fh:
        fh.write("PROJECT CONTEXT MARKER — this project builds widgets.\n")
    eng = Engine(ctx)
    eng.st.data["pipeline"] = [
        {"id": "A-01", "status": "to-do", "depends_on": [], "order": 1,
         "has_block_file": True, "block_file": "A-01.md"},
    ]
    calls = []
    orig_call_llm = judge._call_llm

    def fake_scope(tool, payload, ctx_, correction=None, context=None, model=None):
        calls.append({"tool": tool, "payload": payload, "context": context, "model": model})
        return '{"advice": "pick A-01, deps are clear", "recommended_block": "A-01"}'

    judge._call_llm = fake_scope
    try:
        c = console.Console(ctx)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            c._aide_advise_scope(eng)
    finally:
        judge._call_llm = orig_call_llm

    ok("AC-5 a real judge.call('aide') fires at ND-01-08 SET SCOPE (mocked LLM, "
       "NEVER a heuristic)", len(calls) == 1 and calls[0]["tool"] == "aide", f"calls={calls}")
    ok("AC-5 the aide call's mode is 'scope' — it can name WHICH block to pick",
       calls[0]["payload"].get("mode") == "scope", f"payload={calls[0]['payload']}")
    ok("AC-5 the call carries Project Docs context: context.md content is present",
       "PROJECT CONTEXT MARKER" in (calls[0]["context"] or ""),
       f"context={calls[0]['context']!r}")
    ok("AC-5 the call carries Project Docs context: pipeline.md content is present",
       "Roadmap" in (calls[0]["context"] or ""), f"context={calls[0]['context']!r}")
    ok("AC-5 the call carries Project Docs context: the relevant block doc (A-01.md)",
       "Block A-01" in (calls[0]["context"] or ""), f"context={calls[0]['context']!r}")
    ok("AC-5 the operator sees AIDE's real advice, including which block to pick",
       "A-01" in buf.getvalue(), f"out={buf.getvalue()!r}")

    # (c) ND-01-09 SET COUNTS is ALSO a real LLM call, same shape, mode='counts'.
    calls2 = []

    def fake_counts(tool, payload, ctx_, correction=None, context=None, model=None):
        calls2.append({"tool": tool, "payload": payload})
        return '{"advice": "1 worker is unusually low but valid for a trivial SIM"}'

    judge._call_llm = fake_counts
    try:
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            c._aide_advise_counts(eng)
    finally:
        judge._call_llm = orig_call_llm
    ok("AC-5 a real judge.call('aide') fires at ND-01-09 SET COUNTS, mode='counts'",
       len(calls2) == 1 and calls2[0]["payload"].get("mode") == "counts", f"calls2={calls2}")
    ok("AC-5 SET COUNTS advises #workers only — no #architects field is ever sent "
       "(single architect this version, D-D+D-J BLOCKER-2)",
       "architect_count" not in calls2[0]["payload"], f"payload={calls2[0]['payload']}")

    # (d) ND-01-14 RESOLVE: briefs the operator and offers exactly three choices.
    def fake_resolve(tool, payload, ctx_, correction=None, context=None, model=None):
        ok("AC-5 RESOLVE's aide call mode is 'resolve' and carries the conflict detail",
           payload.get("mode") == "resolve" and "conflict" in payload.get("detail", ""),
           f"payload={payload}")
        return ('{"advice": "the MANIFEST scope no longer matches trunk", '
                '"choices": ["repair", "restart", "halt"]}')

    judge._call_llm = fake_resolve
    try:
        brief, choices = c._aide_resolve(eng, "manifest scope conflict")
    finally:
        judge._call_llm = orig_call_llm
    ok("AC-5 RESOLVE briefs the operator and offers exactly three choices",
       len(choices) == 3 and set(choices) == {"repair", "restart", "halt"},
       f"brief={brief!r} choices={choices}")

    # (e) fail-safe: AIDE unavailable -> proceeds UNAIDED — never a heuristic
    # substitute answer. No monkeypatch here: the real (unpatched) judge._call_llm
    # runs, and TRON_DRY + no TRON_JUDGE_STUB makes it a fast, tokenless no-op.
    ctx3, _ = build()
    eng3 = Engine(ctx3)
    eng3.st.data["pipeline"] = []
    c3 = console.Console(ctx3)
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        c3._aide_advise_scope(eng3)
    ok("AC-5 AIDE unavailable -> bootup proceeds unaided (no crash, no fabricated "
       "block-pick, no heuristic substitute)",
       "unavailable" in buf3.getvalue().lower(), f"out={buf3.getvalue()!r}")
    buf4 = io.StringIO()
    with contextlib.redirect_stdout(buf4):
        c3._aide_advise_counts(eng3)
    ok("AC-5 ...same fail-safe at ND-01-09 SET COUNTS",
       "unavailable" in buf4.getvalue().lower(), f"out={buf4.getvalue()!r}")
    brief3, choices3 = c3._aide_resolve(eng3, "a raw detail string")
    ok("AC-5 ...RESOLVE's fail-safe surfaces the RAW detail (never a fabricated "
       "brief) but still offers the three standing choices",
       brief3 == "a raw detail string" and set(choices3) == {"repair", "restart", "halt"},
       f"brief3={brief3!r} choices3={choices3}")

    # (f) AIDE's model is fail-open — never boot-fatal, unlike a dispatched fleet role
    # (D-J reconciliation (a); the model-absent=boot-fatal law governs ONLY roles.yaml
    # roles). A missing/blank session override silently keeps judge's built-in default.
    ctx4, _ = build()
    eng4 = Engine(ctx4)
    ok("AC-5 AIDE's model resolves to judge's built-in default with no session "
       "override (fail-open, never a crash)",
       eng4.aide_model() == judge.TIER.get("aide", judge.AIDE_DEFAULT_MODEL))
    eng4.st.live_config["aide_model"] = "session-picked-model"
    ok("AC-5 a session aide_model knob overrides the built-in default",
       eng4.aide_model() == "session-picked-model")

    # a staged/headless bootup with NO "aide" key at all never prompts and never
    # blocks boot (fail-open exemption from D-D's boot-fatal law — contrast with the
    # per-role model question, which DOES boot-fatal on an unresolved role, AC-3).
    ctx5, _ = build()
    c5 = console.Console(ctx5)
    eng5 = Engine(ctx5)

    def poison_input(prompt=""):
        raise AssertionError(f"headless aide-model resolution must never prompt: {prompt!r}")

    orig_input = builtins.input
    builtins.input = poison_input
    try:
        c5._ask_aide_model(eng5, staged={})   # no "aide" key present at all
    finally:
        builtins.input = orig_input
    ok("AC-5 a staged bootup with no 'aide' answer never prompts and resolves the "
       "built-in default (fail-open, not boot-fatal)",
       eng5.st.live_config.get("aide_model") == judge.TIER.get("aide", judge.AIDE_DEFAULT_MODEL))


def main():
    for fn in sorted(k for k in globals() if k.startswith("test_")):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
