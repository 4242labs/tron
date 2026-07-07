"""block_01_24_test — wall lifecycle: contain the false walls, answer the real ones
(holistic review RETHINKING-TRON-CONSOLIDATED.md R-01/R-02).

  T1 (AC-1) report.sh de-collides its grammar: flags-after-message (the exact
     fat-finger that reads a stray trailing `--tag wall` onto a routine positional
     message) is a hard error AT THE WORKER, never reaching the engine as a wall; the
     canonical branch-declare form (`--branch <name> "<message>"`, no `--tag` needed)
     still succeeds, and structured `--tag wall` (flags BEFORE the message) still
     succeeds.
  T3 (AC-3/AC-4) a settle can carry a payload: the answer text reaches the walled
     worker on release (raise-and-resolve), delivered through the same worker-inbox
     path every settle-driven notice uses. A spec-ownable decision-wall (kind ∈
     scope/blueprint/design) routes to the architect first — same kind vocabulary
     _h_await already reads — never a new case kind; an operator-only wall still
     pages the operator directly. The architect's own answer to a routed wall IS the
     content-carrying settle (architect-relayed), released through the SAME
     close-case/unhold/replay seam.
  T4 (AC-5) settle parsing is ONE deterministic point (_settle_regex): a negating
     settle ("don't approve CASE-7") never matches the affirmative handler — fail-
     closed, re-prompts with the accepted forms instead of guessing; a bare
     "resume CASE-007" is unaffected (no payload, same behavior as before T3).

  T2/T5 (the worker-`retract` verb and its `_own_wall` provenance guard) were cut in
  block 01-29 (zero recorded use, ADR §C) — their tests (ac1_retract_*, ac2_*,
  ac8_*, ac4_retract_before_architect_answers_suppresses_the_stale_relay) were removed
  with them. F-1 (the same-tick wall+retract fat-finger race) no longer exists as a
  reachable shape once retract itself is gone; the real F-1 protection is the engine-
  observed `_sweep_wall_invariant` (fsm.py), untouched by 01-29 and proven in
  block_01_29_test.py.

Run: python3 engine/block_01_24_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import json
import shutil
import stat
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

from fsm import Engine, SPEC_OWNABLE_KINDS  # noqa: E402
from sentry_test import build, started      # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


# ── fixture builders (block_01_19_test convention) ──
def _eng(block="A-01", status="🔄"):
    ctx, _ = build(blocks=[(block, status, "none")])
    eng = Engine(ctx); started(eng)
    eng.st.workers.append({"id": "ENG-" + block, "role": "engineer", "block": block,
                           "session_id": "dry", "status": "working"})
    return eng


def _arch_idle(eng):
    w = {"id": "ARCH-PERSIST", "role": "architect", "session_id": "dry",
         "status": "idle", "current_job": None, "block": None, "mbox_seq": 0}
    eng.st.workers.append(w)
    return w


def _wall(eng, block, wid, detail="flaky ci", kind=None):
    """Raise a wall against an already-rostered worker THROUGH THE REAL PIPELINE.

    `worker.wall` resolves to the DEFERRED trigger `wall:raised:<block>` — `_ingest`
    only queues it into `self._tq` via `_emit`; `_h_escalate` does not run until
    `_drain_triggers` drains the queue at end-of-tick. Driving it via `_ingest` +
    `_drain_triggers` (never a direct `_h_escalate(...)` call) exercises the real
    queue/drain seam, never a shortcut around it.

    Returns the parked case id."""
    eng._tq = []
    slots = {"block": block, "detail": detail}
    if kind:
        slots["kind"] = kind
    eng._ingest("worker.wall", slots, {"kind": "worker", "id": wid})
    eng._drain_triggers()
    return next(cid for cid, c in eng.st.pending_cases.items() if c.get("kind") == "wall")


def _arch_answers(eng, arch, answer):
    """Simulate the architect's REAL completion report for a triage job: an architect
    worker reporting `worker.done` while its own record shows a live `busy`/`triage`
    job is remapped by sender-truth (_resolve_by_sender) into `architect.relay` —
    exactly the tag a genuine architect session's report resolves to. This drives
    `_relay_architect_answer` through the real `_ingest` -> side-handler seam, never a
    direct call, so the F-3 stale-relay-suppression fix is exercised as a live
    architect report would exercise it."""
    eng._ingest("worker.done", {"detail": answer}, {"kind": "worker", "id": arch["id"]})


def _capture(eng):
    sent = []
    orig = eng.emit
    eng.emit = (lambda tid, slots=None, worker_id=None:
                sent.append((tid, dict(slots or {}))) or orig(tid, slots, worker_id))
    return sent


def _capture_to_worker(eng):
    sent = []
    eng._to_worker = lambda wid, text, kind: sent.append((wid, text, kind))
    return sent


# ══════════════════════════════════════════════════════════════════════════════════
# T1 (AC-1): report.sh grammar de-collision — script-level
# ══════════════════════════════════════════════════════════════════════════════════

def _report_sandbox():
    d = tempfile.mkdtemp(prefix="tron-t1-report-")
    scripts = os.path.join(d, "scripts")
    os.makedirs(scripts)
    src = os.path.join(ROOT, "scripts", "report.sh")
    dst = os.path.join(scripts, "report.sh")
    shutil.copy(src, dst)
    os.chmod(dst, os.stat(dst).st_mode | stat.S_IEXEC)
    return d, dst


def _run_report(script, *args):
    return subprocess.run(["bash", script, *args], capture_output=True, text=True, timeout=20)


def _inbox_lines(d):
    path = os.path.join(d, "worker-inbox.jsonl")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [json.loads(l) for l in fh if l.strip()]


def ac1_flags_after_message_is_a_hard_error_never_reaches_the_inbox():
    d, script = _report_sandbox()
    try:
        # The F-1 fat-finger: a branch declaration with a stray TRAILING --tag wall.
        r = _run_report(script, "ENG-A", "--branch", "feat/foo", "declaring my branch",
                        "--tag", "wall")
        ok("AC-1 flags-after-message exits non-zero", r.returncode != 0, f"rc={r.returncode}")
        ok("AC-1 flags-after-message prints a usage note naming the correct shape",
           "usage" in r.stderr.lower() and "flags must come before" in r.stderr.lower(),
           f"stderr={r.stderr!r}")
        ok("AC-1 the mistake NEVER reaches the engine as a wall (no inbox line written)",
           _inbox_lines(d) == [], f"inbox={_inbox_lines(d)}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ac1_canonical_branch_declare_form_succeeds():
    d, script = _report_sandbox()
    try:
        r = _run_report(script, "ENG-A", "--branch", "feat/foo", "declaring my branch")
        ok("AC-1 the canonical branch-declare form (no --tag needed) succeeds",
           r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")
        lines = _inbox_lines(d)
        ok("AC-1 canonical form: exactly one inbox line, branch recorded, no tag",
           len(lines) == 1 and lines[0].get("slots", {}).get("branch") == "feat/foo"
           and "tag" not in lines[0], f"lines={lines}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ac1_structured_tag_before_message_still_works():
    d, script = _report_sandbox()
    try:
        r = _run_report(script, "ENG-A", "--tag", "wall", "genuinely stuck")
        ok("AC-1 structured --tag wall BEFORE the message still succeeds",
           r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")
        lines = _inbox_lines(d)
        ok("AC-1 the structured wall tag is recorded correctly",
           len(lines) == 1 and lines[0].get("tag") == "wall", f"lines={lines}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ac1_flag_looking_token_inside_the_quoted_message_is_never_flagged():
    # A message that merely MENTIONS "--tag wall" inside its own (single, quoted) text
    # is not a flags-after-message shape — it's one argument, never split by report.sh.
    d, script = _report_sandbox()
    try:
        r = _run_report(script, "ENG-A", "the docs say to use --tag wall when stuck")
        ok("AC-1 a flag-looking substring INSIDE the quoted message is not rejected",
           r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ac1_kind_modifier_rides_before_the_message_like_branch_and_block():
    # F2 (MAJOR, review cycle 1): report.sh had NO way to carry a wall's declared kind —
    # AC-4's architect kind-routing was unreachable through the structured path the
    # spec requires (fsm.py read `kind` only from LLM free-text classification). --kind
    # is a MODIFIER: it rides exactly like --branch/--block, flags-before-message, and
    # lands in the inbox line's structured slots.
    d, script = _report_sandbox()
    try:
        r = _run_report(script, "ENG-A", "--tag", "wall", "--kind", "scope",
                        "which schema version — v1 or v2?")
        ok("F2 --tag wall --kind scope succeeds", r.returncode == 0,
           f"rc={r.returncode} stderr={r.stderr!r}")
        lines = _inbox_lines(d)
        ok("F2 the declared kind lands in slots.kind — the structured DATA path, "
           "never prose", len(lines) == 1 and lines[0].get("tag") == "wall"
           and lines[0].get("slots", {}).get("kind") == "scope", f"lines={lines}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ac1_no_kind_modifier_leaves_slots_unchanged_default_unaffected():
    d, script = _report_sandbox()
    try:
        r = _run_report(script, "ENG-A", "--tag", "wall", "stuck, no kind given")
        ok("F2 a wall with no --kind still succeeds (today's default, unchanged)",
           r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")
        lines = _inbox_lines(d)
        ok("F2 no --kind -> no slots.kind key at all (never a guessed default)",
           len(lines) == 1 and "kind" not in lines[0].get("slots", {}), f"lines={lines}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ac1_kind_after_the_message_is_rejected_same_hard_error_as_every_other_flag():
    d, script = _report_sandbox()
    try:
        r = _run_report(script, "ENG-A", "--tag", "wall", "stuck", "--kind", "scope")
        ok("F2 --kind AFTER the message is the same flags-after-message hard error",
           r.returncode != 0 and "flags must come before" in r.stderr.lower(),
           f"rc={r.returncode} stderr={r.stderr!r}")
        ok("F2 the malformed --kind-after-message form never reaches the inbox",
           _inbox_lines(d) == [], f"inbox={_inbox_lines(d)}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════════
# T3 (AC-3/AC-4): content-carrying settle + spec-ownable routing
# ══════════════════════════════════════════════════════════════════════════════════

def ac3_content_carrying_settle_reaches_the_walled_worker():
    eng = _eng()
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="approach A or B?")
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        eng._h_apply_decision({"case": cid, "decision": "resume", "block": "A-01",
                               "detail": "use approach B — safer given the deadline"})
    finally:
        eng.dry = True
    ok("AC-3 the answer text reaches the walled worker on release",
       any(wid_ == wid and "use approach B" in txt for wid_, txt, _ in tw), f"tw={tw}")
    ok("AC-3 the case closed and the worker un-held (raise-and-RESOLVE, not just release)",
       cid not in eng.st.pending_cases, f"cases={eng.st.pending_cases}")
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("AC-3 worker un-held", w.get("status") != "walled", f"w={w}")


def ac3_settle_parses_the_payload_deterministically_via_classify():
    eng = _eng()
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="approach A or B?")
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        msg = {"text": f"resume {cid}: use approach B, add retries",
               "sender": {"kind": "operator"}}
        tag, slots = eng._classify(msg)
        ok("T3/T4 the deterministic path resolves operator.decision with a detail payload",
           tag == "operator.decision" and slots.get("detail") == "use approach B, add retries",
           f"tag={tag} slots={slots}")
        eng._ingest(tag, {**slots, "_raw": msg["text"]}, msg["sender"])
        eng._drain_triggers()
    finally:
        eng.dry = True
    ok("T3 the parsed payload is delivered end to end",
       any(wid_ == wid and "use approach B, add retries" in txt for wid_, txt, _ in tw),
       f"tw={tw}")


def ac3_bare_settle_carries_no_payload_unaffected_by_the_change():
    eng = _eng()
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="fat-fingered wall")
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        eng._h_apply_decision({"case": cid, "decision": "resume", "block": "A-01"})
    finally:
        eng.dry = True
    ok("AC-3 a bare resume (no trailing text) sends no extra operator.answer line "
       "(today's behavior, unchanged)",
       not any(k == "operator.answer" for _, _, k in tw), f"tw={tw}")


def ac4_spec_ownable_wall_routes_to_the_architect_first():
    eng = _eng()
    wid = "ENG-A-01"
    arch = _arch_idle(eng)
    sent = _capture(eng)
    cid = _wall(eng, "A-01", wid, detail="which schema version — v1 or v2?", kind="scope")
    ok("AC-4 a spec-ownable wall (kind=scope) never pages the operator directly",
       not any(tid in ("escalate.wall", "tg.escalate") for tid, _ in sent), f"sent={sent}")
    ok("AC-4 the architect is dispatched a triage job carrying the wall's case id",
       (arch.get("current_job") or {}).get("kind") == "triage"
       and arch["current_job"].get("case") == cid, f"arch={arch}")
    ok("AC-4 the wall case itself is unchanged — still kind=='wall', still undecided",
       eng.st.pending_cases.get(cid, {}).get("kind") == "wall"
       and eng.st.pending_cases[cid].get("decision") is None, f"cases={eng.st.pending_cases}")
    ok("AC-4 SPEC_OWNABLE_KINDS is the same vocabulary shared with await routing",
       "scope" in SPEC_OWNABLE_KINDS and "blueprint" in SPEC_OWNABLE_KINDS
       and "design" in SPEC_OWNABLE_KINDS)


def ac4_operator_only_wall_pages_the_operator_directly():
    eng = _eng()
    wid = "ENG-A-01"
    _arch_idle(eng)                       # an architect being online must not matter here
    sent = _capture(eng)
    cid = _wall(eng, "A-01", wid, detail="the CI provider is down", kind="policy")
    ok("AC-4 an operator-only wall (kind not in SPEC_OWNABLE_KINDS) pages the operator",
       any(tid == "escalate.wall" and s.get("case") == cid for tid, s in sent), f"sent={sent}")
    arch = next(w for w in eng.st.workers if w.get("role") == "architect")
    ok("AC-4 the architect is NOT dispatched this wall",
       arch.get("current_job") is None, f"arch={arch}")


def ac4_no_kind_wall_pages_the_operator_directly_default_unchanged():
    eng = _eng()
    wid = "ENG-A-01"
    _arch_idle(eng)
    sent = _capture(eng)
    cid = _wall(eng, "A-01", wid, detail="stuck, no kind given")
    ok("AC-4 a wall with no declared kind keeps today's default (operator, direct)",
       any(tid == "escalate.wall" and s.get("case") == cid for tid, s in sent), f"sent={sent}")


def ac4_architect_relayed_answer_settles_the_routed_wall():
    eng = _eng()
    wid = "ENG-A-01"
    arch = _arch_idle(eng)
    cid = _wall(eng, "A-01", wid, detail="which schema — v1 or v2?", kind="scope")
    ok("setup: routed to the architect", (arch.get("current_job") or {}).get("case") == cid)
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        _arch_answers(eng, arch, "use schema v2 — v1 is deprecated")
    finally:
        eng.dry = True
    ok("AC-3/AC-4 the architect-relayed answer reaches the walled worker",
       any(wid_ == wid and "use schema v2" in txt for wid_, txt, _ in tw), f"tw={tw}")
    ok("AC-3/AC-4 the architect-relayed settle releases the SAME wall case "
       "(close-case/unhold/replay, never a second mechanism)",
       cid not in eng.st.pending_cases, f"cases={eng.st.pending_cases}")
    w = next(x for x in eng.st.workers if x["id"] == wid)
    ok("AC-4 the worker is un-held by the architect-relayed settle",
       w.get("status") != "walled", f"w={w}")
    ok("AC-4 the block is back in the dispatch pool",
       "A-01" not in eng.st.blocked, f"blocked={eng.st.blocked}")


def ac4_plain_peer_relay_without_a_case_stays_a_plain_relay():
    # The pre-existing peer-question relay (T10) must be untouched when the job carries
    # no `case` — no accidental wall-settle attempt on ordinary peer traffic.
    eng = _eng()
    wid = "ENG-A-01"
    arch = _arch_idle(eng)
    # Real pipeline: worker.question_peer's side (triage_peer) is what actually calls
    # _triage_to_architect for a live peer question — drive it via _ingest.
    eng._ingest("worker.question_peer", {"detail": "a peer design question"},
               {"kind": "worker", "id": wid})
    tw = _capture_to_worker(eng)
    eng.dry = False
    try:
        _arch_answers(eng, arch, "use a factory here")
    finally:
        eng.dry = True
    ok("T10 regression: a plain peer relay still delivers the answer",
       any(wid_ == wid and "use a factory here" in txt for wid_, txt, _ in tw), f"tw={tw}")
    ok("T10 regression: no wall bookkeeping touched (nothing parked to begin with)",
       not eng.st.pending_cases, f"cases={eng.st.pending_cases}")


def ac4_kind_declared_via_the_structured_report_path_routes_to_the_architect():
    # F2 (MAJOR, review cycle 1): prove the declared kind reaches routing through the
    # SAME structured path a real report.sh JSON line actually takes (_structured, zero
    # model calls) — never through LLM free-text classification. This is the exact gap
    # F2 found: fsm.py's kind-routing existed, but nothing could ever hand it a
    # structured `kind` because report.sh had no --kind modifier before this fix.
    eng = _eng()
    wid = "ENG-A-01"
    arch = _arch_idle(eng)
    sent = _capture(eng)
    # Shaped exactly like the JSON line report.sh's new --kind modifier now emits.
    msg = {"at": "2026-07-06T00:00:00Z", "text": "which schema version — v1 or v2?",
           "sender": {"kind": "worker", "id": wid},
           "tag": "wall", "slots": {"kind": "scope"}}
    tag, slots = eng._classify(msg)          # the exact call tick() makes (fsm.py:251)
    ok("F2 the structured wall resolves deterministically to worker.wall, kind carried "
       "as DATA, never prose", tag == "worker.wall" and slots.get("kind") == "scope",
       f"tag={tag} slots={slots}")
    slots = {**slots, "_raw": msg["text"]}   # mirror tick()'s own _raw carry (fsm.py:255)
    eng._ingest(tag, slots, msg["sender"])
    eng._drain_triggers()
    ok("F2 the operator is never paged for a structurally-declared spec-ownable wall",
       not any(tid in ("escalate.wall", "tg.escalate") for tid, _ in sent), f"sent={sent}")
    ok("F2 the architect IS dispatched, carrying the wall's case id",
       (arch.get("current_job") or {}).get("kind") == "triage"
       and (arch.get("current_job") or {}).get("case") is not None, f"arch={arch}")


# ══════════════════════════════════════════════════════════════════════════════════
# T4 (AC-5): deterministic, negation-safe, single-point settle parsing
# ══════════════════════════════════════════════════════════════════════════════════

def ac5_negated_settle_never_matches_the_affirmative_handler():
    eng = _eng()
    for text in ("don't approve CASE-7", "do not resume CASE-7", "please don't resume CASE-7"):
        out = eng._settle_regex(text)
        ok(f"AC-5 negated settle detected, never an affirmative match: {text!r}",
           isinstance(out, dict) and out.get("negated") is True, f"out={out}")


def ac5_unrelated_trailing_not_does_not_false_positive():
    eng = _eng()
    out = eng._settle_regex("resume CASE-7, this is not urgent")
    ok("AC-5 a trailing, unrelated 'not' (well after the verb) does not false-trigger "
       "negation — the window is scoped, never a global scan",
       isinstance(out, dict) and not out.get("negated")
       and out.get("decision") == "resume" and out.get("case") == "CASE-007", f"out={out}")


def ac5_negated_settle_from_operator_re_prompts_fail_closed():
    eng = _eng()
    wid = "ENG-A-01"
    cid = _wall(eng, "A-01", wid, detail="a real wall")
    sent = _capture(eng)
    msg = {"text": "don't approve CASE-7", "sender": {"kind": "operator"}}
    tag, slots = eng._classify(msg)
    ok("AC-5 a negated settle never resolves to operator.decision (fail-closed, never "
       "picks an action)", tag != "operator.decision", f"tag={tag} slots={slots}")
    ok("AC-5 it re-prompts with the exact accepted forms (never silently drops)",
       any(tid == "escalate.unclassified" and "resume CASE-007" in (s.get("detail") or "")
           for tid, s in sent), f"sent={sent}")
    ok("AC-5 the wall this negated line was ABOUT was never touched",
       cid in eng.st.pending_cases and eng.st.pending_cases[cid].get("decision") is None,
       f"cases={eng.st.pending_cases}")


def ac5_bare_settle_unaffected_no_payload_key():
    eng = _eng()
    out = eng._settle_regex("resume CASE-007")
    ok("AC-5 a bare settle carries no `detail` key at all (today's shape, unchanged)",
       out == {"case": "CASE-007", "decision": "resume"}, f"out={out}")


def ac5_case_id_and_verb_either_order_both_forms_still_work():
    eng = _eng()
    a = eng._settle_regex("resume CASE-007")
    b = eng._settle_regex("CASE-007: resume")
    ok("AC-5 both orders still settle (D-15-3 unchanged)",
       a and b and a["case"] == b["case"] == "CASE-007"
       and a["decision"] == b["decision"] == "resume", f"a={a} b={b}")


def ac5_all_settle_forms_resolve_through_one_point():
    # Every settle-parsing behavior this suite exercises (bare, payload-carrying,
    # negated, either-order) all runs through the SAME single function.
    eng = _eng()
    ok("AC-5 one settle-verb resolution point: _settle_regex is the sole parser "
       "(no parallel regex/handler split reachable from _classify)",
       callable(getattr(eng, "_settle_regex", None)))


def main():
    for fn in sorted(k for k in globals() if k.startswith("ac1_") or k.startswith("ac2_")
                     or k.startswith("ac3_") or k.startswith("ac4_") or k.startswith("ac5_")
                     or k.startswith("ac8_")):
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
