#!/usr/bin/env python3
"""tron-reborn v0.1 — a minimal deterministic supervisor: one block, full cycle.

OPERATOR runs this in a terminal. The engine spawns a worker + an architect
(and, on DONE, a reviewer) as persistent CLI agent sessions. Agents talk back
in the closed vocabulary (glossary.py / GLOSSARY.md); anything else routes
agent -> architect -> OPERATOR. Spec: SCOPE-v0.1.md.

Modules: glossary.py (the vocabulary — single source), prompts.py + prompts/
(every engine boilerplate, one file each), agents.py (CLI agent sessions),
transcript.py (verbatim run logs + terminal I/O). This file is the engine:
routing + the phase loop.
"""

import os
import queue
import shutil
import sys
import threading
import time
from pathlib import Path

import events
import glossary
import pipeline
import prompts
import roster
import bootup
import tg
import transcript
import workflow
from agents import Agent, kill_strays
from gate import (add_arena, contains_trunk, git, judge_copy, merge_to_main,
                  orphan_branch, remove_arena, run_tests, test_cmd,
                  trunk_sha, trunk_test_cmd, verify_done)
from glossary import glossary_help, parse
from prompts import prompt
from transcript import halt, operator, say

# ---------------------------------------------------------------- config
ROOT = Path(__file__).resolve().parent
DEMO = ROOT / "demo"
ARENAS = ROOT / "arenas"  # engine-owned worktrees, one per running block
WAKE_POLL_S = 10         # --watch: idle poll — both the cooldown floor and
#                          the wake ceiling; new register work wakes the
#                          engine, a STOP file in the project shuts it down
# ALL caps live in workflow.toml [limits] (turns per phase, review cycles,
# gate bounces, max_parallel) — the flow composes, the engine executes

# Ablation arms — EXPERIMENT ONLY: each disables exactly one invariant so
# the paper can measure what that invariant buys. The lint refuses flows
# that edit invariants away, so ablation deliberately does NOT ride
# workflow.toml: it is an explicit engine switch (TRON_ABLATE env), loud
# at boot and recorded in the run's typed events. Closed vocabulary —
# an unknown arm refuses to boot.
ARMS = frozenset({"truth_gate",       # accept claims unverified (no gate,
                  #                     no engine-run tests, no AC challenge)
                  "judge_isolation",  # verdict seats read the worker's own
                  #                     arena instead of a pinned copy
                  "architect_first"})  # walls page the operator directly


def ablation(value):
    """frozenset of arms from a comma-separated string; unknown = refuse."""
    arms = frozenset(a.strip() for a in value.split(",") if a.strip())
    if arms - ARMS:
        raise SystemExit(f"unknown ablation arm(s): "
                         f"{', '.join(sorted(arms - ARMS))} "
                         f"(known: {', '.join(sorted(ARMS))})")
    return arms


ABLATE = ablation(os.environ.get("TRON_ABLATE", ""))
# live run config chosen at the bootup journey (bootup.py) — the frozen
# operator questions; defaults hold for non-interactive (harness) boots
LIVE = {"ask_before_merging": False, "scope": None}
ENGINE = threading.Lock()  # every write to the primary repo + the register
MERGE = threading.Lock()   # ONE merge window at a time; main only moves
#                            inside a window or under an engine stamp that
#                            also holds it (acquire order: MERGE then ENGINE)
# branches are engine-assigned per block: feat/<block-name>


# ---------------------------------------------------------------- routing
def milestone(text):
    """Milestone narration rides Telegram unless TRON_QUIET says a
    harness batch is driving. Only the narration is quietable — pages
    (transcript.operator) always reach the operator."""
    if not os.environ.get("TRON_QUIET"):
        tg.note(text)


def interpret(agent, architect, reply, context="", tag=""):
    """Spec step 4: parse; QUESTION or unparseable -> architect; else operator.

    context = the sender's own block, attached to every routed exchange —
    the architect is INFORMED by the engine, it never reads blocks itself.
    tag = the block's transcript prefix, so parallel runs stay readable.
    """
    def say_(t, text):
        say(tag + t, text)
    msg = parse(reply, agent.role)
    if msg and msg[0] != "QUESTION":
        return msg
    if msg:  # a well-formed QUESTION
        say_("route", f"{agent.role} QUESTION -> architect")
        t = architect.turn(prompt("question_req", sender=agent.role,
                                  context=context, text=msg[1]["text"]))
    else:
        say_("route", f"uninterpretable {agent.role} message -> architect")
        t = architect.turn(prompt("translate_req", sender=agent.role,
                                  context=context,
                                  help=glossary_help(agent.role),
                                  raw=reply[:4000]))
    tm = parse(t, "architect")
    if tm and tm[0] == "TRANSLATED" and not msg:
        inner = parse(">>" + tm[1]["inner"], agent.role)
        if inner:
            say_("route", f"architect translated -> {inner[0]}")
            return inner
    if tm and tm[0] == "ANSWER":
        say_("route", f"architect ruled -> back to {agent.role}")
        return ("ARCH_ANSWER", {"answer": tm[1]["text"]})
    reason = (tm[1]["reason"] if tm and tm[0] == "ESCALATE"
              else f"architect could not resolve. Architect said: {t[:300]}")
    ans = operator(f"the {agent.role} ({tag or 'run'}) needs you.\n"
                   f"Reason: {reason}\n"
                   f"Raw {agent.role} message:\n{reply[:1500]}")
    say_("route", "operator ruling -> architect (context sync)")
    architect.turn(prompt("arch_fyi", sender=agent.role, answer=ans))
    return ("OPERATOR_ANSWER", {"answer": ans})


def wall_verdict(architect, case, block):
    """('ruling'|'escalate', text) — architect-first judgment on a wall.

    Total escalation: no engine-detected wall reaches the operator before
    the architect has judged the case. ANSWER carries guidance for the
    blocked seat; ESCALATE (or an unusable reply) carries the reason to
    the operator — content, never a bare alarm.
    """
    t = architect.turn(prompt("wall_case", case=case, block=block))
    tm = parse(t, "architect")
    if tm and tm[0] == "ANSWER":
        return "ruling", tm[1]["text"]
    return "escalate", (tm[1]["reason"] if tm and tm[0] == "ESCALATE"
                        else f"architect could not resolve: {t[:300]}")


# ------------------------------------------------------------- phase loop
def load_project(path):
    """(context, [(name, block_text), ...]) — blocks/ dir, or one block.md.

    Project core docs: context.md (OPEN project info) and principles.md
    (conduct for all agents) are committed — every agent reads them in its
    own working copy; personas point at them. decisions.md is the
    ARCHITECT-EXCLUSIVE context and must stay UNTRACKED: a worktree only
    materializes committed content, so exclusivity is physical, not a
    convention. A tracked decisions.md is an illegal state.
    """
    bdir = path / "blocks"
    if bdir.is_dir():
        blocks = [(p.stem, p.read_text()) for p in sorted(bdir.glob("*.md"))]
    else:
        blocks = [("block-01", (path / "block.md").read_text())]
    ctx = path / "context.md"
    context = ctx.read_text() if ctx.exists() else blocks[0][1]
    dec = path / "decisions.md"
    if dec.exists():
        if git(path, "ls-files", "decisions.md").stdout.strip():
            halt("decisions.md is TRACKED — architect exclusivity must be "
                 "physical: git rm --cached decisions.md, commit, retry")
        context += ("\n\n## Architect-exclusive decisions (untracked — "
                    "readable by no agent)\n\n" + dec.read_text())
    return context, blocks


def load_policy(path):
    """policy.md 'findings:' value — the operator-set acceptance bar for
    review findings. Default (and this operator's standing rule): 'none' —
    NO finding passes, however small."""
    p = path / "policy.md"
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip().lower().startswith("findings:"):
                return line.split(":", 1)[1].strip()
    return "none"


def parley(path, architect):
    """Operator-initiated channel: a parley.md dropped in the project
    root. The engine only moves the message — the ARCHITECT (the LLM)
    answers it from the project's artifacts; ESCALATE pages the
    terminal. Ask + answer are recorded durably under parley/."""
    p = path / "parley.md"
    if not p.exists():
        return
    text = p.read_text().strip()
    p.unlink()
    if not text:
        return
    say("parley", f"operator message picked up ({len(text)} chars)")
    t = architect.turn(prompt("parley_req", text=text[:4000]))
    tm = parse(t, "architect")
    if tm and tm[0] == "ANSWER":
        reply = tm[1]["text"]
        say("parley", f"architect answers: {reply[:200]}")
    else:
        reason = (tm[1]["reason"] if tm and tm[0] == "ESCALATE"
                  else f"architect could not resolve: {t[:300]}")
        reply = operator(f"PARLEY needs you.\nOperator asked: {text[:500]}\n"
                         f"Architect: {reason}")
        architect.turn(prompt("arch_fyi", sender="operator (parley)",
                              answer=reply))
    rel = f"parley/{time.strftime('%y%m%d-%H%M%S')}.md"
    with MERGE:   # the record moves main — never inside someone's window
        with ENGINE:
            pipeline.record_doc(path, rel, "parley",
                                f"## operator\n\n{text}\n\n"
                                f"## answer\n\n{reply}")
    say("parley", f"answered + recorded ({rel})")


def report_request(path, architect):
    """Ad-hoc user report: a report-request.md dropped in the project
    root. Intent is STRUCTURAL (the filename — the engine interprets
    nothing): the ARCHITECT writes the report from the artifacts, the
    engine records it VERBATIM under reports/ on main."""
    p = path / "report-request.md"
    if not p.exists():
        return
    ask = p.read_text().strip()
    p.unlink()
    if not ask:
        return
    rel = f"reports/{time.strftime('%y%m%d-%H%M%S')}-report.md"
    say("report", f"ad-hoc report requested ({len(ask)} chars)")
    body = architect.turn(prompt("report_req", text=ask[:4000], path=rel))
    with MERGE:   # the record moves main — never inside someone's window
        with ENGINE:
            pipeline.record_doc(path, rel, f"report — {ask[:80]}", body)
    say("report", f"report recorded ({rel})")


def channels(path, architect):
    """Every operator-initiated channel, one poll."""
    parley(path, architect)
    report_request(path, architect)


def gate_verify(ph, path, arena, name, branch, trunk, fields):
    """The engine's own facts behind a work phase's closing word."""
    if fields.get("branch") and fields["branch"] != branch:
        return False, (f"this phase belongs to {branch}; a claim for "
                       f"'{fields['branch']}' is not accepted")
    if ph["gate"] == "verify_done":
        with ENGINE:
            return verify_done(path, branch, trunk["sha"])
    if ph["gate"] == "verify_wrapped":
        log = f"logs/{name}-session.md"
        if git(path, "cat-file", "-e", f"{branch}:{log}").returncode != 0:
            return False, (f"{log} is not committed on {branch} — the "
                           "session log is the wrap's minimum")
        if git(arena, "status", "--porcelain").stdout.strip():
            return False, ("the working tree is NOT clean — commit or "
                           "remove everything; nothing uncommitted "
                           "survives the seat")
        return True, f"{log} committed, tree clean"
    if not contains_trunk(path, branch):        # verify_merged
        return False, (f"{branch} does not contain main — the trunk merge "
                       "is not actually in your branch; run `git merge "
                       "main`, resolve, commit")
    return True, f"{branch} contains the trunk"


def ac_exchange(agent, actor, retries, note):
    """The AC challenge as its OWN bounded exchange: the only legal reply
    is >>CONFIRMED evidence=<...>. Anything else — a re-claimed DONE, a
    bare CONFIRMED, prose — is retried with the exact expectation, and
    exhaustion returns None: the claim is withdrawn. The failed reply
    never escapes to the phase loop, where CONFIRMED is out of phase —
    that trap deadlocked CONFIRMED against DONE (260717). Returns the
    confirmed evidence, or None on exhaustion."""
    reply = agent.turn(prompt("ac_challenge"))
    for attempt in range(1, retries + 1):
        cm = parse(reply, actor)
        if cm and cm[0] == "CONFIRMED":
            return cm[1]["evidence"]
        note(attempt)
        if attempt < retries:
            reply = agent.turn(prompt("ac_retry"))
    return None


def sweep_arenas(path):
    """One engine owns arenas/ — anything still there at boot is a dead
    engine's residue (a capped or killed run never retires its arenas,
    and they are often worktrees of an EARLIER project). Left in place,
    a residue occupies the exact path this run's `git worktree add`
    needs and poisons the run at dispatch — deterministic, twice in the
    campaign (260717). Branch preservation is the register recovery's
    job; the residue itself goes unconditionally. Returns swept names."""
    if not ARENAS.exists():
        return []
    stale = sorted(p for p in ARENAS.iterdir() if p.is_dir())
    for p in stale:
        remove_arena(path, p)
    return [p.name for p in stale]


def run_block(path, arena, name, block, trunk, architect, flow):
    """One block through the FLOW — the process itself is workflow.toml.

    This driver is generic: it seats each phase's actor (fresh sessions
    per block, one per actor+persona — whatever a block needs from
    earlier blocks must come from the repository, never from an agent's
    memory), relays the generic words, and advances only on facts the
    engine derives itself. A work phase closes on its word after its
    gate (+ optional AC challenge); a verdict phase records its word
    durably in reviews.md and routes; the single landing phase runs
    inside the MERGE window — one open window engine-wide — and ends
    with the mechanical land + suite re-run ON the trunk (an arena
    physically cannot move a checked-out main; the subjective merge work
    is the LLM's, the engine only authorizes). Returns the branch, LANDED.
    """
    branch, tag, tests = f"feat/{name}", f"{name}|", test_cmd(block)
    lim = workflow.limits(flow)
    phases = {p["id"]: p for p in flow["phase"]}

    def bsay(t, text):
        say(tag + t, text)

    agents = {}

    def judge_home(ph):
        """Create-or-resync a verdict seat's OWN detached checkout, pinned
        to the branch tip the engine attests. An independent judge reads
        the delivery in a copy the worker cannot move — and one the judge
        cannot contaminate: every (re)pin force-restores the exact sha."""
        dest = ARENAS / f"{name}-judge-{workflow.persona_of(ph)}"
        sha = git(path, "rev-parse", branch).stdout.strip()
        ok, ev = judge_copy(path, sha, dest)
        if not ok:
            operator(f"cannot prepare the judge's copy for {name}: {ev}\n"
                     "'abort' to quit.")
            halt(f"judge copy failed for {name}")
        bsay("judge", f"{workflow.persona_of(ph)} copy pinned @ {sha[:12]} "
             f"({dest.name})")
        return dest

    def seat(ph):
        key = (ph["actor"], workflow.persona_of(ph))
        if key not in agents:
            pinned = (ph["kind"] == "verdict"
                      and "judge_isolation" not in ABLATE)
            if ph["kind"] == "verdict" and not pinned:
                bsay("judge", f"{key[1]} ABLATED into the worker's arena")
            home = judge_home(ph) if pinned else arena
            bsay("spawn", "fresh " + key[0]
                 + (f" as {key[1]}" if key[1] != key[0] else "")
                 + (" in own detached copy" if pinned else ""))
            agents[key] = Agent(key[0], home, budget=lim["turn_seconds"])
            roster.enroll(agents[key], f"{name}: {ph['id']} ({branch})")
        return agents[key]

    rulings = []            # engine-attested: every ruling relayed onward
    facts = {"summary": ""}  # engine-verified claims, fed to later prompts
    rejections, fails = 0, {}
    walls = {}              # wall id -> occurrences (recurrence = operator)

    def wall(wid, case, to_actor=None):
        """Route an engine-detected wall: architect first, operator last.

        First occurrence goes to the architect (ANSWER = ruling relayed
        to the seat; ESCALATE = operator, content-carrying). A recurrence
        after a ruling skips straight to the operator — an answered wall
        that comes back is above the fleet. Returns the relay prompt."""
        to_actor = to_actor or state["ph"]["actor"]
        walls[wid] = walls.get(wid, 0) + 1
        ablated = "architect_first" in ABLATE   # EXPERIMENT ARM: no triage
        # the exception spine's routing lives in workflow.ESCALATION — the
        # engine executes the architect-first decision from that one table
        # (the same table bpmn.py draws), it is not hardcoded here.
        route = workflow.escalation_route(walls[wid], ablated)
        if route[0] == "architect":            # architect-first (tier 0)
            bsay("wall", f"{wid} -> architect (architect-first)")
            kind, text = wall_verdict(architect, case, block)
            if kind == "ruling":
                bsay("wall", f"architect ruled on {wid} — relayed to seat")
                events.emit("wall", block=name, wid=wid, n=1,
                            route="architect", outcome="ruling")
                rulings.append(text)
                return prompt("arch_relay", answer=text)
            bsay("wall", f"architect ESCALATED {wid} -> operator: {text}")
            events.emit("wall", block=name, wid=wid, n=1,
                        route="architect", outcome="escalated")
            case = f"{case}\nArchitect escalated: {text}"
        elif ablated:                          # arm: straight to operator
            bsay("wall", f"{wid} -> operator (architect-first ABLATED)")
            events.emit("wall", block=name, wid=wid, n=walls[wid],
                        route="operator", outcome="ablated")
        else:                                  # recurrence: above the fleet
            bsay("wall", f"{wid} recurred after a ruling -> operator")
            events.emit("wall", block=name, wid=wid, n=walls[wid],
                        route="operator", outcome="recurrence")
        ans = operator(f"{name} walled ({wid}):\n{case}\n"
                       f"Your guidance goes to the {to_actor}.")
        architect.turn(prompt("arch_fyi", sender=to_actor, answer=ans))
        rulings.append(ans)
        return prompt("op_relay", answer=ans)

    def kwargs(ph):
        # fork = the engine-attested delivery boundary: judges must never
        # blame a moved trunk on the worker (two-dot-diff false rejects)
        fork = git(path, "merge-base", "main", branch).stdout.strip()[:12]
        return dict(role=workflow.persona_of(ph),
                    help=glossary_help(ph["actor"]), block=block,
                    branch=branch, base="main", fork=fork,
                    tests=tests or "(none declared)",
                    name=name, summary=facts["summary"],
                    policy=load_policy(path),
                    rulings="\n".join(f"- {r}" for r in rulings) or "(none)")

    state = {"ph": None, "reply": None, "turns": 0, "windowed": False}

    def enter(nid, override=None):
        """Advance to phase nid: open its window if it has one, then its
        seat speaks — the assign prompt, or the override (fix / ruling)."""
        ph = state["ph"] = phases[nid]
        state["turns"] = 0
        events.emit("phase", block=name, phase=nid,
                    window=bool(ph.get("window")))
        if ph.get("window") and not state["windowed"]:
            MERGE.acquire()     # ONE window at a time, engine-wide
            state["windowed"] = True
            roster.block(name, f"{nid} window")
            bsay("merge", f"window OPEN — {ph['actor']} owns the merge "
                 f"(trunk at {trunk['sha'][:12]})")
        else:
            roster.block(name, nid)
        if (ph["kind"] == "verdict" and "judge_isolation" not in ABLATE
                and (ph["actor"], workflow.persona_of(ph)) in agents):
            judge_home(ph)   # re-pin to the fresh tip before the seat reads
        state["reply"] = seat(ph).turn(
            override or prompt(ph["assign"], **kwargs(ph)))

    try:
        bsay("assign", f"flow '{flow['name']}' in {Path(arena).name} "
             f"(branch {branch} off main, "
             f"gate tests: {tests or 'NONE DECLARED'})")
        enter(flow["phase"][0]["id"])
        while True:
            if state["turns"] >= lim["phase_turns"]:
                wid = f"turns:{state['ph']['id']}"
                if walls.get(wid):   # walled once already — above the fleet
                    operator(f"turn cap in phase '{state['ph']['id']}' of "
                             f"{name} recurred after a wall ruling — run "
                             "halts. 'abort' to quit.")
                    halt(f"phase turn cap reached twice on {name}")
                state["reply"] = seat(state["ph"]).turn(wall(
                    wid, f"phase '{state['ph']['id']}' burned "
                         f"{lim['phase_turns']} turns without closing"))
                state["turns"] = 0
            state["turns"] += 1
            ph = state["ph"]
            agent = seat(ph)
            word, f = interpret(agent, architect, state["reply"],
                                context=block, tag=tag)
            if word == "WORKING":
                bsay(workflow.persona_of(ph), "WORKING")
                state["reply"] = agent.turn(prompt("continue"))
            elif word == "OPERATOR_ANSWER":
                rulings.append(f["answer"])
                state["reply"] = agent.turn(prompt("op_relay",
                                                   answer=f["answer"]))
            elif word == "ARCH_ANSWER":
                rulings.append(f["answer"])
                state["reply"] = agent.turn(prompt("arch_relay",
                                                   answer=f["answer"]))
            elif ph["kind"] == "work" and word == ph["word"]:
                if "truth_gate" in ABLATE:   # EXPERIMENT ARM: trust claims
                    ok, evidence = True, "ABLATED: claim accepted unverified"
                else:
                    ok, evidence = gate_verify(ph, path, arena, name, branch,
                                               trunk, f)
                    if ok and tests:
                        t_ok, out = run_tests(arena, tests)
                        bsay("gate", f"engine ran tests in the arena: "
                             f"{'GREEN' if t_ok else 'RED'} — {tests}")
                        if not t_ok:
                            ok, evidence = False, (
                                f"the engine ran `{tests}` in your arena "
                                f"itself — RED:\n{out}")
                if not ok:
                    fails[ph["id"]] = fails.get(ph["id"], 0) + 1
                    bsay("gate", f"{word} bounced "
                         f"({fails[ph['id']]}/{lim['gate_fails']}) — "
                         f"{evidence}")
                    events.emit("gate", block=name, phase=ph["id"], ok=False,
                                fails=fails[ph["id"]],
                                evidence=evidence.splitlines()[0][:200])
                    if fails[ph["id"]] > lim["gate_fails"]:
                        state["reply"] = agent.turn(wall(
                            f"gate:{ph['id']}",
                            f"the {ph['actor']} claimed {word} "
                            f"{fails[ph['id']]}x but the repository "
                            f"disagrees: {evidence}"))
                    else:
                        state["reply"] = agent.turn(prompt(
                            ph["bounce"], reason=evidence, branch=branch))
                    continue
                bsay("gate", f"{word} verified — {evidence.splitlines()[0]}")
                events.emit("gate", block=name, phase=ph["id"], ok=True,
                            evidence=evidence.splitlines()[0][:200])
                if ph.get("challenge") and "truth_gate" not in ABLATE:
                    def ac_note(n):
                        bsay("gate", f"AC confirmation not given "
                             f"({n}/{lim['gate_fails']}) — the challenge "
                             "accepts only >>CONFIRMED evidence=<...>")
                        events.emit("gate", block=name, phase=ph["id"],
                                    ok=False, check="ac", fails=n)
                    ev = ac_exchange(agent, ph["actor"],
                                     lim["gate_fails"], ac_note)
                    if ev is None:
                        bsay("gate", f"AC challenge exhausted — {word} "
                             "withdrawn, back to work")
                        state["reply"] = agent.turn(prompt(
                            ph["bounce"], branch=branch,
                            reason="the AC challenge went unanswered — "
                                   ">>CONFIRMED evidence=<...> never "
                                   "arrived, so the claim is withdrawn"))
                        continue
                    bsay("gate", f"ACs CONFIRMED — {ev[:200]}")
                facts["summary"] = f.get("summary", facts["summary"])
                bsay(workflow.persona_of(ph), f"{word} branch={branch} — "
                     f"{facts['summary']}")
                if ph.get("land"):
                    if LIVE["ask_before_merging"]:   # bootup step 3: ON
                        operator(f"{name}: {branch} is ready to land on "
                                 "main — your go-ahead.")
                    with ENGINE:
                        okL, ev = merge_to_main(path, branch)
                        if okL:
                            trunk["sha"] = ev
                    if not okL:  # unreachable once branch contains main
                        operator(f"landing {branch} FAILED despite "
                                 f"containing the trunk:\n{ev}\n"
                                 "'abort' to quit.")
                        halt(f"impossible landing failure on {name}")
                    bsay("merge", f"{branch} landed on main ({ev[:12]})")
                    events.emit("land", block=name, phase=ph["id"],
                                sha=ev[:12])
                    roster.block(name, f"landed ({ev[:12]})")
                    if tests:
                        t_ok, out = run_tests(path, tests)
                        bsay("merge", f"engine re-validated ON TRUNK: "
                             f"{'GREEN' if t_ok else 'RED'} — {tests}")
                        events.emit("trunk_check", block=name, ok=t_ok,
                                    cmd=tests)
                        if not t_ok:
                            operator(f"trunk is RED after landing "
                                     f"{branch}:\n{out}\n'abort' to quit.")
                            halt(f"trunk red after landing {name}")
                    if ph["next"] == workflow.END:
                        # trunk-only validation: some checks can only pass
                        # on the landed trunk — final landing, ON the trunk
                        tcmd = trunk_test_cmd(block)
                        if tcmd:
                            t_ok, out = run_tests(path, tcmd)
                            bsay("merge", f"trunk-only validation: "
                                 f"{'GREEN' if t_ok else 'RED'} — {tcmd}")
                            events.emit("trunk_check", block=name, ok=t_ok,
                                        cmd=tcmd, kind="trunk-only")
                            if not t_ok:
                                operator(f"trunk-only validation RED for "
                                         f"{name}:\n{out}\n'abort' to quit.")
                                halt(f"trunk-only validation red on {name}")
                        return branch
                enter(ph["next"])
            elif ph["kind"] == "verdict" and word in (ph["pass_word"],
                                                      ph["reject_word"]):
                text = f.get("summary") or f.get("findings") or ""
                with MERGE:   # verdict commits move main — never inside
                    with ENGINE:   # someone's window
                        pipeline.record_review(path, f"{name}/{ph['id']}",
                                               branch, rejections + 1,
                                               word, text)
                        trunk["sha"] = trunk_sha(path)
                events.emit("verdict", block=name, phase=ph["id"], word=word,
                            passed=word == ph["pass_word"],
                            cycle=rejections + 1)
                if word == ph["pass_word"]:
                    bsay(workflow.persona_of(ph), f"{word} — {text}")
                    # the seat closes on its pass — it logs its session,
                    # the engine records it (agents never write the trunk)
                    logp = f"logs/{name}-{ph['id']}.md"
                    body = agent.turn(prompt("seat_log", path=logp))
                    with MERGE:
                        with ENGINE:
                            pipeline.record_doc(
                                path, logp,
                                f"{name} {ph['id']} — "
                                f"{workflow.persona_of(ph)} session log",
                                body)
                            trunk["sha"] = trunk_sha(path)
                    bsay(ph["id"], f"seat log recorded ({logp})")
                    enter(ph["next"])
                else:
                    rejections += 1
                    bsay(workflow.persona_of(ph), f"{word} ({rejections}/"
                         f"{lim['review_cycles']}) — {text[:300]}")
                    if rejections > lim["review_cycles"]:
                        enter(ph["on_reject"], override=wall(
                            f"reject:{ph['id']}",
                            f"{ph['id']} rejected the delivery "
                            f"{rejections}x. Latest findings:\n{text}",
                            to_actor=phases[ph["on_reject"]]["actor"]))
                    else:
                        enter(ph["on_reject"],
                              override=prompt(ph["fix"], findings=text,
                                              branch=branch))
            else:   # a legal word, wrong phase — remind, do not route
                exp = (f">>{ph['word']}" if ph["kind"] == "work"
                       else f">>{ph['pass_word']} or >>{ph['reject_word']}")
                bsay(ph["id"], f"{word} is out of phase — reminded ({exp})")
                state["reply"] = agent.turn(prompt("phase_reminder",
                                                   word=word, expected=exp))
    finally:
        if state["windowed"]:
            MERGE.release()


def main():
    # `tron start` is the terminal entry (see the ./tron launcher): it runs on
    # the local folder/repo — the current directory. An explicit path still
    # works (`tron start <project>`). With neither `start` nor a path — the
    # harness feeds the project on stdin — fall back to the interactive prompt.
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    started = bool(argv) and argv[0] == "start"
    if started:
        argv = argv[1:]
    if argv:
        path = Path(argv[0])
    elif started:
        path = Path.cwd()          # `tron start` → this folder/repo
    else:
        path = Path(input(f"Project [{DEMO}] (Enter = demo): ").strip()
                    or DEMO)
    flow_file = workflow.file_for(path)   # the project's own flow, or the
    flow = workflow.parse_file(flow_file)  # engine default — same lint bar
    problems = workflow.lint(flow)
    if problems:   # an unsound process must never run
        halt(f"{flow_file} is unsound — the engine refuses to boot:\n  - "
             + "\n  - ".join(problems))
    context, blocks = load_project(path)
    blockmap = dict(blocks)
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    stamp = time.strftime("run-%y%m%d-%H%M%S")
    transcript.set_log(runs / f"{stamp}.log")
    events.bind(runs / f"{stamp}.events.jsonl")
    roster.bind(runs / f"{stamp}.manifest.md", runs / f"{stamp}.report.md")
    transcript.SAY_HOOK = roster.event
    say("roster", f"manifesto + user report live in runs/{stamp}.*.md")
    shutil.copy(flow_file, runs / f"{stamp}.workflow.toml")
    say("workflow", f"flow '{flow['name']}' from {flow_file} — copied "
        f"to runs/{stamp}.workflow.toml")

    # bootup: read the register FIRST; without one, all blocks in file order
    has_pipe = pipeline.path_of(path).exists()
    rows = pipeline.load(path) if has_pipe else [
        {"id": n, "block": n, "deps": [], "status": "todo", "branch": None}
        for n, _ in blocks]
    say("pipeline", "  ".join(
        f"{r['id']}:{r['status']}" for r in rows) or "(empty)")
    if ABLATE:
        say("ablate", "EXPERIMENT ARM — invariant(s) DISABLED: "
            + ", ".join(sorted(ABLATE)))
    boot = bootup.journey(path, rows)   # the FROZEN operator journey;
    LIVE["ask_before_merging"] = boot["ask_before_merging"]  # non-tty
    scope = LIVE["scope"] = boot["scope"]                    # -> defaults
    in_scope = (lambda r: scope is None or r["id"] in scope)
    events.emit("run_start", project=path.name, flow=flow["name"],
                total=len(rows),
                todo=sum(r["status"] != "done" for r in rows
                         if in_scope(r)),
                ablate=sorted(ABLATE))
    # crash recovery: one engine owns a project — agent processes still in
    # the project or its arenas at boot are a dead engine's strays
    strays = kill_strays(path, ARENAS) if ARENAS.exists() else kill_strays(path)
    if strays:
        say("recover", f"killed stray agent process(es): {strays}")
        events.emit("recover", what="strays_killed", pids=strays)
    # a 'doing' row at boot means a previous engine died mid-block — its
    # branch is unverified testimony: preserve the branch as an orphan,
    # re-stamp todo; normal dispatch re-runs it fresh (the arena sweep
    # below drops its working copy along with every other residue)
    if has_pipe:
        for r in [x for x in rows if x["status"] == "doing"]:
            kept = orphan_branch(path, f"feat/{r['block']}")
            rows = pipeline.stamp(path, rows, r["id"], "todo")
            say("recover", f"{r['id']} was doing at boot -> todo"
                + (f"; branch preserved as {kept}" if kept else ""))
            events.emit("recover", what="doing_requeued", block=r["block"],
                        orphan=kept or "")
    # crash-safe arena sweep: whatever a dead engine left — this
    # project's, or an earlier one's — retires before dispatch
    for gone in sweep_arenas(path):
        say("recover", f"swept stale arena {gone}")
        events.emit("recover", what="arena_swept", arena=gone)
    watch = "--watch" in sys.argv   # long-running: idle instead of exit
    if all(r["status"] == "done" for r in rows) and not watch:
        events.emit("run_done", delivered=0)
        print("\n[TRON -> OPERATOR] DONE — pipeline complete "
              "(nothing left to dispatch).")
        return

    todo = sum(r["status"] != "done" for r in rows)
    milestone(f"[TRON] Run up on {path.name}: {todo} block(s) to deliver, "
              f"flow '{flow['name']}'. You'll hear from me at milestones.")
    say("spawn", "architect")
    architect = Agent("architect", path)
    roster.enroll(architect, "project rulings (architect-first)")
    architect.turn(prompt("arch_boot", role="architect",
                          help=glossary_help("architect"), project=context))
    ARENAS.mkdir(exist_ok=True)
    trunk = {"sha": trunk_sha(path)}  # the engine's live ledger of main
    landed = queue.Queue()            # finished blocks: (entry, branch|exc)
    active = {}                       # block id -> Thread
    delivered = []

    def launch(entry):
        name = entry["block"]
        arena = ARENAS / name
        with ENGINE:
            okA, ev = add_arena(path, f"feat/{name}", arena)
        if not okA:
            operator(f"cannot create arena for {name}: {ev}\n'abort' to quit.")
            halt(f"arena creation failed for {name}")

        def job():
            try:
                landed.put((entry, run_block(path, arena, name,
                                             blockmap[name], trunk,
                                             architect, flow)))
            except BaseException as e:   # a dead block must never be silent
                landed.put((entry, e))
        active[entry["id"]] = threading.Thread(target=job, daemon=True)
        active[entry["id"]].start()

    cap = boot["max_parallel"] or workflow.limits(flow)["max_parallel"]
    while True:
        while len(active) < cap:
            with ENGINE:
                entry = pipeline.next_dispatch(rows, scope)
            if entry is None:
                break
            if entry["block"] not in blockmap:
                operator(f"pipeline entry {entry['id']} names block "
                         f"'{entry['block']}' but blocks/{entry['block']}.md "
                         "does not exist. 'abort' to quit.")
                halt("pipeline names a missing block")
            say("pipeline", f"dispatch: {entry['id']} ({entry['block']}), "
                f"deps done: {', '.join(entry['deps']) or 'none'}"
                + (f" [{len(active) + 1} in flight]" if active else ""))
            events.emit("dispatch", block=entry["block"],
                        deps=entry["deps"], in_flight=len(active) + 1)
            with MERGE:   # stamps move main — never inside someone's window
                with ENGINE:
                    if has_pipe:
                        rows = pipeline.stamp(path, rows, entry["id"], "doing")
                        trunk["sha"] = trunk_sha(path)
                    else:
                        entry["status"] = "doing"
            launch(entry)
        if not active:
            if all(r["status"] == "done" for r in rows if in_scope(r)):
                if not watch:
                    break
                # WAKE: the run does not end — the engine idles, wakes on
                # new register work, and shuts down on a STOP file
                say("wake", f"pipeline complete — watching (poll "
                    f"{WAKE_POLL_S}s; STOP file in the project to stop)")
                roster.block("(engine)", "watching — idle")
                stopped = False
                while True:
                    if (path / "STOP").exists():
                        (path / "STOP").unlink()
                        stopped = True
                        break
                    channels(path, architect)
                    time.sleep(WAKE_POLL_S)
                    if not has_pipe:
                        continue          # no register to grow — idle
                    with ENGINE:
                        fresh = pipeline.load(path)
                    if pipeline.next_dispatch(fresh, scope):
                        rows = fresh
                        context, blocks = load_project(path)
                        blockmap = dict(blocks)
                        say("wake", "new dispatchable work in the register "
                            "— waking")
                        roster.block("(engine)", "woken — dispatching")
                        break
                if stopped:
                    say("wake", "STOP — shutting down")
                    break
                continue
            operator("pipeline deadlock: blocks remain but nothing is "
                     "dispatchable. Fix pipeline.md; 'abort' to quit.")
            halt("pipeline deadlock")
        while True:   # wait for a landing; operator channels stay live
            try:
                entry, result = landed.get(timeout=WAKE_POLL_S)
                break
            except queue.Empty:
                channels(path, architect)
        del active[entry["id"]]
        if isinstance(result, BaseException):
            operator(f"block {entry['block']} crashed in-engine: {result!r}\n"
                     "'abort' to quit.")
            halt(f"block {entry['block']} crashed")
        # result = the branch, already landed inside its merge window
        with MERGE:
            with ENGINE:
                if has_pipe:
                    rows = pipeline.stamp(path, rows, entry["id"], "done",
                                          result)
                    trunk["sha"] = trunk_sha(path)
                else:
                    entry["status"], entry["branch"] = "done", result
                remove_arena(path, ARENAS / entry["block"])
                for j in ARENAS.glob(f"{entry['block']}-judge-*"):
                    remove_arena(path, j)   # judges retire with the block
        roster.block(entry["block"], f"done ({result})")
        say("pipeline", f"{entry['id']} stamped done ({result})")
        delivered.append(result)
        done = sum(r["status"] == "done" for r in rows)
        events.emit("block_done", block=entry["block"], done=done,
                    total=len(rows))
        milestone(f"[TRON] {entry['block']} landed. Trunk green. "
                  f"{done}/{len(rows)} in the register.")
    # the architect's seat closes with the run — its session log, recorded
    logp = f"logs/{stamp}-architect.md"
    body = architect.turn(prompt("seat_log", path=logp))
    with MERGE:
        with ENGINE:
            pipeline.record_doc(path, logp,
                                f"architect session log ({stamp})", body)
    say("log", f"architect session log recorded ({logp})")
    events.emit("run_done", delivered=len(delivered))
    print(f"\n[TRON -> OPERATOR] DONE — pipeline complete"
          + (f": {', '.join(delivered)} delivered this run."
             if delivered else " (nothing left to dispatch)."))
    milestone(f"[TRON] Run done: {len(delivered)} block(s) delivered, "
              "trunk green, register complete. End of line.")


# -------------------------------------------------------------- selftest
def selftest():
    def _refuses(fn):
        try:
            fn()
            return False
        except SystemExit:
            return True

    def _fixture():
        # a synthesized project — selftests never read live scratch
        # (demo/ is untracked; a fresh clone must selftest green)
        d = Path(__import__("tempfile").mkdtemp(prefix="tron-fixture-"))
        (d / "context.md").write_text("The architect owns the scope.\n")
        (d / "blocks").mkdir()
        for n in ("02", "03", "04"):
            (d / "blocks" / f"block-{n}.md").write_text(f"# block-{n}\n")
        (d / "pipeline.md").write_text(
            "| id | block | depends on | status | branch |\n"
            "|:--|:--|:--|:--|:--|\n"
            "| 01 | scoping | — | done | — |\n"
            "| 02 | block-02 | 01 | todo | — |\n"
            "| 03 | block-03 | 02 | todo | — |\n"
            "| 04 | block-04 | 03 | todo | — |\n")
        return d

    ok = [
        parse(">>DONE branch=feat/x summary=built it all", "worker")
        == ("DONE", {"branch": "feat/x", "summary": "built it all"}),
        parse("chatter\n>>WORKING", "worker") == ("WORKING", {}),
        parse(">>QUESTION text=which remainder policy for split()?", "worker")
        == ("QUESTION", {"text": "which remainder policy for split()?"}),
        parse(">>done branch=b summary=s", "worker") is not None,  # case-insensitive word
        parse(">>DONE branch=feat/x", "worker") is None,           # missing field
        parse(">>APPROVED summary=ok", "worker") is None,          # wrong role
        parse(">>APPROVED summary=ok", "reviewer") == ("APPROVED", {"summary": "ok"}),
        parse(">>REJECTED findings=1. no tests 2. no cli", "reviewer")
        == ("REJECTED", {"findings": "1. no tests 2. no cli"}),
        parse("no marks at all", "worker") is None,
        parse(">>WORKING\n>>DONE branch=b summary=s", "worker") is None,  # two lines
        parse(">>> tip(10, 20)\n>>WORKING", "worker") == ("WORKING", {}), # doctest noise
        parse(">>ESCALATE reason=needs a credential", "architect")
        == ("ESCALATE", {"reason": "needs a credential"}),
        parse(">>ANSWER text=first person absorbs the extra cent", "architect")
        == ("ANSWER", {"text": "first person absorbs the extra cent"}),
        parse(">>TRANSLATED DONE branch=b summary=s", "architect")
        == ("TRANSLATED", {"inner": "DONE branch=b summary=s"}),
        # ablation arms: closed vocabulary, unknown refuses, default empty
        ablation("") == frozenset(),
        ablation("truth_gate") == {"truth_gate"},
        ablation("judge_isolation, architect_first")
        == {"judge_isolation", "architect_first"},
        _refuses(lambda: ablation("trust_me")),
        # the vocabulary document is generated and must not be stale
        glossary.doc_in_sync(),
        # every prompt file renders (all placeholders satisfied)
        ">>" in prompt("worker_assign", role="worker", help="h",
                       block="b", branch="feat/x", base="main", name="x"),
        ">>" in prompt("review_assign", role="reviewer", help="h",
                       branch="feat/x", base="main", fork="abc123def456",
                       block="b", summary="s",
                       policy="none", rulings="- use Bob's Diner"),
        ">>" in prompt("arch_boot", role="architect", help="h", project="p"),
        ">>" in prompt("question_req", sender="worker", context="c", text="t"),
        ">>" in prompt("translate_req", sender="worker", context="c",
                       help="h", raw="r"),
        ">>" in prompt("player_boot", role="player", help="h", suspects="s",
                       rooms="r", objects="o", others="x", name="p", clues="c"),
        "'>>'" in prompt("continue"),
        "answer" in prompt("op_relay", answer="answer"),
        "answer" in prompt("arch_relay", answer="answer"),
        "f1" in prompt("fix", findings="f1", branch="feat/x"),
        "(empty)" in prompt("game_turn", inbox="(empty)"),
        "no commits" in prompt("gate_fail", reason="no commits",
                               branch="feat/x"),
        "the case" in prompt("wall_case", case="the case", block="b"),
        # the worker-owned merge window
        parse(">>MERGED branch=feat/x summary=trunk merged, 2 conflicts "
              "resolved, 20/20 green", "worker")
        == ("MERGED", {"branch": "feat/x", "summary": "trunk merged, 2 "
                       "conflicts resolved, 20/20 green"}),
        parse(">>MERGED branch=feat/x", "worker") is None,   # missing field
        parse(">>MERGED branch=b summary=s", "reviewer") is None,  # wrong role
        ">>MERGED" in prompt("merge_assign", branch="feat/x", base="main",
                             tests="python3 -m unittest"),
        ">>MERGED" in prompt("merge_fail", reason="not merged",
                             branch="feat/x"),
        "ruling" in prompt("arch_fyi", sender="worker", answer="ruling"),
        parse(">>CONFIRMED evidence=t1: ran CLI by hand; t2: 20/20 tests",
              "worker")
        == ("CONFIRMED", {"evidence": "t1: ran CLI by hand; t2: 20/20 tests"}),
        parse(">>CONFIRMED", "worker") is None,        # evidence required
        ">>CONFIRMED" in prompt("ac_challenge"),
        len(prompts.names()) == 32,
        # the AC challenge is a closed exchange: retry names the one legal
        # reply and forbids the DONE re-claim (the 260717 deadlock trap)
        ">>CONFIRMED" in prompt("ac_retry"),
        "evidence" in prompt("ac_retry"),
        ">>DONE" in prompt("ac_retry"),
        "RECORDED" in prompt("seat_log", path="logs/block-15-review.md"),
        ">>ANSWER" in prompt("parley_req", text="how many blocks are done?"),
        "RECORDED" in prompt("report_req", text="status report",
                             path="reports/x.md"),
        # ad-hoc report: engine moves the ask, the LLM writes, record lands
        (lambda d: (git(d, "init", "-qb", "main") or True)
         and ((d / "seed").write_text("s") or True)
         and (git(d, "add", "."), git(d, "commit", "-qm", "seed"), True)[-1]
         and ((d / "report-request.md").write_text("full status") or True)
         and (report_request(d, type("A", (), {"role": "architect", "turn":
              lambda self, m: "## State\n\nall 18 blocks done"})()) or True)
         and not (d / "report-request.md").exists()
         and "18 blocks done" in next(iter((d / "reports").glob("*.md"))
                                      ).read_text()
         and "log: reports/" in git(d, "log", "-1", "--format=%s").stdout)
        (Path(__import__("tempfile").mkdtemp(prefix="tron-report-"))),
        # parley: engine moves the message, the LLM answers, record lands
        (lambda d: (git(d, "init", "-qb", "main") or True)
         and ((d / "seed").write_text("s") or True)
         and (git(d, "add", "."), git(d, "commit", "-qm", "seed"), True)[-1]
         and ((d / "parley.md").write_text("how many blocks?") or True)
         and (parley(d, type("A", (), {"role": "architect", "turn":
              lambda self, m: ">>ANSWER text=17 blocks done"})()) or True)
         and not (d / "parley.md").exists()
         and "17 blocks done" in next(iter((d / "parley").glob("*.md"))
                                      ).read_text()
         and "log: parley/" in git(d, "log", "-1", "--format=%s").stdout)
        (Path(__import__("tempfile").mkdtemp(prefix="tron-parley-"))),
        # the post-merge wrap (operator ruling 260716: arenas retire only
        # after trunk validation + docs + session log + clean tree)
        parse(">>WRAPPED branch=feat/x summary=README + session log",
              "worker")
        == ("WRAPPED", {"branch": "feat/x",
                        "summary": "README + session log"}),
        parse(">>WRAPPED branch=feat/x", "worker") is None,
        "logs/block-14-session.md" in prompt("wrap_assign", name="block-14",
                                             branch="feat/x"),
        ">>WRAPPED" in prompt("wrap_fail", reason="tree dirty",
                              branch="feat/x"),
        # the flow: composed in workflow.toml, linted sound, docs in sync
        workflow.lint(workflow.parse_file()) == [],
        workflow.doc_in_sync(),
        workflow.limits(workflow.parse_file())["phase_turns"] >= 1,
        ">>MERGED" in prompt("phase_reminder", word="DONE",
                             expected=">>MERGED"),
        "AUDITOR" in prompts.raw("persona_auditor"),
        # personas compose into the boot/assign prompts, one per role
        "You are the WORKER" in prompt("worker_assign", role="worker",
                                       help="h", block="b", branch="feat/x",
                                       base="main", name="x"),
        "You are the REVIEWER" in prompt("review_assign", role="reviewer",
                                         help="h", branch="feat/x",
                                         base="main", fork="abc123def456",
                                         block="b", summary="s",
                                         policy="none", rulings="(none)"),
        # acceptance policy: operator default 'none'; per-project override
        load_policy(Path("/nonexistent")) == "none",
        (lambda d: ((d / "policy.md").write_text("# p\nfindings: minor-ok\n")
                    or load_policy(d) == "minor-ok")
         and load_policy(_fixture()) == "none")  # fixture has no policy.md
        (Path(__import__("tempfile").mkdtemp(prefix="tron-policy-"))),
        "You are the ARCHITECT" in prompt("arch_boot", role="architect",
                                          help="h", project="p"),
        "principles.md" in prompt("worker_assign", role="worker", help="h",
                                  block="b", branch="feat/x", base="main",
                                  name="x"),
        # untracked decisions.md joins the architect context; tracked = illegal
        (lambda d: (git(d, "init", "-qb", "main") or True)
         and ((d / "context.md").write_text("open info") or True)
         and ((d / "block.md").write_text("t") or True)
         and ((d / "decisions.md").write_text("PD-9: secret") or True)
         and "open info" in load_project(d)[0]
         and "PD-9: secret" in load_project(d)[0]
         and "Architect-exclusive" in load_project(d)[0])
        (Path(__import__("tempfile").mkdtemp(prefix="tron-selftest-"))),
        # a project loads: architect-only context + ordered blocks
        (lambda cb: "architect" in cb[0].lower()
         and [n for n, _ in cb[1]][:3] == ["block-02", "block-03", "block-04"])
        (load_project(_fixture())),
        # register structure: the permanent prefix holds and every dep
        # names a real row
        (lambda rows: [r["id"] for r in rows][:4] == ["01", "02", "03", "04"]
         and rows[0]["block"] == "scoping"
         and all(d in {x["id"] for x in rows}
                 for r in rows for d in r["deps"]))
        (pipeline.load(_fixture())),
    ]
    # total escalation: the architect judges every wall before the operator
    class _Arch:
        def __init__(self, reply): self.reply, self.role = reply, "architect"
        def turn(self, _): return self.reply
    ok += [
        wall_verdict(_Arch(">>ANSWER text=split the module"), "case", "b")
        == ("ruling", "split the module"),
        wall_verdict(_Arch(">>ESCALATE reason=spec defect"), "case", "b")
        == ("escalate", "spec defect"),
        # an unusable architect reply must still escalate, never dead-end
        wall_verdict(_Arch("prose with no word"), "case", "b")[0]
        == "escalate",
        wall_verdict(_Arch(">>TRANSLATED DONE branch=b summary=s"),
                     "case", "b")[0] == "escalate",
    ]
    # the engine's wall routing is now driven by workflow.escalation_route;
    # this pins the (occurrence, ablated) truth table the old hardcoded
    # if/elif/else encoded — architect-first is taken EXACTLY on the first
    # occurrence with the arm live, operator-direct otherwise (recurrence
    # or ablated). A drift here would silently change escalation behavior.
    def _first(occ, abl):     # does the engine route to the architect?
        return workflow.escalation_route(occ, abl)[0] == "architect"
    ok += [
        _first(1, False) is True,                 # architect-first
        _first(2, False) is False,                # recurrence -> operator
        _first(1, True) is False,                 # ablated -> operator
        _first(3, True) is False,
        workflow.escalation_route(1, False)[-1] == "operator",  # terminal
        workflow.ESC_SYNC == "architect",         # operator answer syncs
    ]
    # the AC challenge is a bounded exchange: the 260717 CONFIRMED-vs-DONE
    # deadlock is unrepresentable — a failed reply retries or withdraws,
    # it never reaches the phase loop
    class _Seat:
        def __init__(self, *replies): self.r = list(replies)
        def turn(self, _): return self.r.pop(0)
    ok += [
        ac_exchange(_Seat(">>CONFIRMED evidence=probed"), "worker", 3,
                    lambda n: None) == "probed",
        # a re-claimed DONE is retried, then the late confirmation lands
        ac_exchange(_Seat(">>DONE branch=b summary=s",
                          ">>CONFIRMED evidence=late"), "worker", 3,
                    lambda n: None) == "late",
        # a bare CONFIRMED (no evidence) is not a confirmation
        ac_exchange(_Seat(">>CONFIRMED", ">>CONFIRMED evidence=now"),
                    "worker", 3, lambda n: None) == "now",
        # exhaustion withdraws the claim instead of looping forever
        ac_exchange(_Seat(">>DONE branch=b summary=s", "prose",
                          ">>DONE branch=b summary=s"), "worker", 3,
                    lambda n: None) is None,
    ]
    # boot arena sweep: a dead engine's residue — even a foreign repo's
    # worktree — never survives to poison this run's dispatch (260717)
    global ARENAS
    _arenas = ARENAS
    ARENAS = Path(__import__("tempfile").mkdtemp(prefix="tron-sweep-"))
    (ARENAS / "block-09").mkdir()
    (ARENAS / "block-09" / ".git").write_text("gitdir: /nowhere")
    (ARENAS / "block-09" / "left.py").write_text("residue")
    ok += [sweep_arenas(_fixture()) == ["block-09"],
           not (ARENAS / "block-09").exists(),
           sweep_arenas(_fixture()) == []]        # empty stays empty
    ARENAS = ARENAS / "never-created"
    ok += [sweep_arenas(_fixture()) == []]        # missing dir: no-op
    ARENAS = _arenas
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    main()
