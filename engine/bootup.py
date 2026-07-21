#!/usr/bin/env python3
"""tron — the operator bootup journey (FROZEN).

Every question, option, and AIDE line below is the frozen operator
journey, VERBATIM (operator law: none of them changes without an
explicit operator OK). AIDE is a REAL LLM seat — advisory only, never a
heuristic or deterministic stand-in; unavailable means the boot proceeds
unaided. The operator's own answers always win.

Non-interactive boots (piped stdin: the SIM harness, staged callers)
get NO questions and all defaults — a staged boot must never block on
input(). Every answered step is typed into the event log.
"""

import sys
import tempfile

import agents
import events
from glossary import glossary_help, parse
from prompts import prompt

# ---------------------------------------------------- the frozen texts
SCOPE_TEXT = (
    "[TRON]  Online. Before I take the fleet — how far do I run? "
    "Should I proceed with:\n"
    "  1) All open phases and blocks\n"
    "  2) A specific phase\n"
    "  3) A range of blocks\n"
    "Your call. End of line.")
SCOPE_ASK = "  [1] all  ·  [2] a phase  ·  [3] a range of blocks  → "
PHASE_ASK = "  Which phase (name or number, e.g. 'Phase 2' or '2')? "
RANGE_LO_ASK = "  First block ID? "
RANGE_HI_ASK = "  Last block ID? "
SCOPE_UNKNOWN = ("[TRON]  That scope ({detail}) matches nothing on trunk. "
                 "Typo, or a plan that doesn't exist yet. Fix it and try "
                 "again. End of line.")
COUNT_ASK = ("worker_count (build + review workers; the persistent "
             "spec-owner role is extra)? ")
COUNT_NAG = "  (a positive integer)"
MERGE_ASK = "Inform you before each merge to trunk? [y/N] "
AIDE_MODEL_ASK = "Model for AIDE (the operator's LLM advisor) [{default}]? "
MODEL_ASK = "Model for {label} [{default}]? "
ROLE_LABEL = {"architect": "the persistent architect/spec-owner",
              "other": "engineers/reviewers"}
AIDE_LINE = "  AIDE: {advice}"
AIDE_BLOCK_LINE = "  AIDE recommends: block {block}"
AIDE_DOWN_SCOPE = ("  AIDE: unavailable — proceeding unaided; your scope "
                   "choice below decides.")
AIDE_DOWN = "  AIDE: unavailable — proceeding unaided."

DEFAULTS = {"scope": None, "max_parallel": None, "ask_before_merging": False}


# ------------------------------------------------------------ AIDE seat
def _docs(path, rows):
    """The Project Docs an AIDE call carries: context.md + pipeline.md +
    the top dispatchable block doc(s). Missing files degrade silently to
    absence — never fabricated content."""
    done = {r["id"] for r in rows if r["status"] == "done"}
    cands = [r for r in rows if r["status"] == "todo"
             and all(d in done for d in r["deps"])][:5]
    sections = []
    for name in ("context.md", "pipeline.md"):
        f = path / name
        if f.exists():
            sections.append(f"=== {name} ===\n{f.read_text()}")
    for r in cands:
        f = path / "blocks" / f"{r['block']}.md"
        if f.exists():
            sections.append(f"=== block {r['block']} ===\n{f.read_text()}")
    return "\n\n".join(sections), [r["id"] for r in cands]


def _aide(path, seat_of):
    """The AIDE seat, seated in an EMPTY scratch home: it advises from the
    documents the engine hands it — it holds no working copy to mutate."""
    home = tempfile.mkdtemp(prefix="aide-boot-")
    return seat_of("aide", home)


def _advice(aide, name, **kw):
    """(advice, block|None) from a real AIDE turn, or None if the LLM lane
    is unavailable/unparsable — the caller proceeds unaided, NEVER with a
    heuristic substitute."""
    try:
        reply = aide.turn(prompt(name, role="aide",
                                 help=glossary_help("aide"), **kw))
        m = parse(reply, "aide")
        if m and m[0] == "ADVICE":
            block = m[1]["block"].strip()
            return m[1]["text"], (None if block.lower() in ("none", "")
                                  else block)
    except Exception:
        pass
    return None


# ---------------------------------------------------------- the journey
def journey(path, rows, ask=input, echo=print, seat_of=agents.Agent,
            interactive=None):
    """The frozen bootup journey. Returns {scope, max_parallel,
    ask_before_merging}: scope = a set of in-scope block ids or None
    (all); max_parallel = the operator's worker_count or None (the flow's
    own limit); model answers are written into agents.MODELS directly."""
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        return dict(DEFAULTS)

    # 0. AIDE's own model — fail-open: blank keeps the default, never blocks
    default = agents.MODELS["aide"]
    v = ask(AIDE_MODEL_ASK.format(default=default)).strip()
    agents.MODELS["aide"] = v or default
    events.emit("bootup", step="aide_model", value=agents.MODELS["aide"])

    context, candidates = _docs(path, rows)
    aide = None
    try:
        aide = _aide(path, seat_of)
    except Exception:
        pass

    # AIDE advises on scope — advisory only; the operator's answer wins
    out = _advice(aide, "aide_scope", context=context,
                  candidates=", ".join(candidates) or "(none)") if aide \
        else None
    if out:
        echo(AIDE_LINE.format(advice=out[0]))
        if out[1]:
            echo(AIDE_BLOCK_LINE.format(block=out[1]))
    else:
        echo(AIDE_DOWN_SCOPE)

    # 1. run scoping — the three-way prompt; TRON never edits status
    echo(SCOPE_TEXT)
    ids = [r["id"] for r in rows]
    scope = None
    while True:
        choice = ask(SCOPE_ASK).strip()
        if choice == "2":
            phase = ask(PHASE_ASK).strip()
            # this register declares no phases — nothing can match
            echo(SCOPE_UNKNOWN.format(detail=phase))
            continue
        if choice == "3":
            lo, hi = ask(RANGE_LO_ASK).strip(), ask(RANGE_HI_ASK).strip()
            if lo not in ids or hi not in ids or ids.index(lo) > ids.index(hi):
                echo(SCOPE_UNKNOWN.format(detail=f"{lo}..{hi}"))
                continue
            scope = set(ids[ids.index(lo):ids.index(hi) + 1])
        break
    events.emit("bootup", step="scope",
                value="all" if scope is None else ",".join(sorted(scope)))

    # AIDE advises on worker_count only — advisory, same fail-safe
    out = _advice(aide, "aide_counts", context=context,
                  scope="all" if scope is None
                  else ", ".join(sorted(scope))) if aide else None
    echo(AIDE_LINE.format(advice=out[0]) if out else AIDE_DOWN)

    # 2. worker_count
    worker_count = None
    while worker_count is None:
        v = ask(COUNT_ASK).strip()
        if v.isdigit() and int(v) > 0:
            worker_count = int(v)
        else:
            echo(COUNT_NAG)
    events.emit("bootup", step="worker_count", value=worker_count)

    # 3. ask-before-merging — ON pauses each landing for your go-ahead
    ans = ask(MERGE_ASK).strip().lower()
    before = ans in ("y", "yes")
    events.emit("bootup", step="ask_before_merging", value=before)

    # 4. worker model, PER ROLE — a recommended default, confirm or override
    for role in ("architect", "reviewer", "worker"):
        tier = "architect" if role == "architect" else "other"
        label = f"{role} ({ROLE_LABEL[tier]})"
        default = agents.MODELS[role]
        v = ask(MODEL_ASK.format(label=label, default=default)).strip()
        agents.MODELS[role] = v or default
        events.emit("bootup", step=f"model:{role}",
                    value=agents.MODELS[role])

    return {"scope": scope, "max_parallel": worker_count,
            "ask_before_merging": before}


# -------------------------------------------------------------- selftest
def selftest():
    saved = dict(agents.MODELS)

    class FakeSeat:
        def __init__(self, role, cwd, reply=">>ADVICE text=start at the "
                     "core block=01"):
            self.reply = reply

        def turn(self, _):
            return self.reply

    rows = [{"id": "01", "block": "block-01", "deps": [], "status": "todo"},
            {"id": "02", "block": "block-02", "deps": ["01"],
             "status": "todo"},
            {"id": "03", "block": "block-03", "deps": ["01"],
             "status": "todo"}]

    def run(answers, seat_of=FakeSeat):
        script, said = list(answers), []
        out = journey(Path("."), [dict(r) for r in rows],
                      ask=lambda q: (said.append(q), script.pop(0))[1],
                      echo=said.append, seat_of=seat_of, interactive=True)
        return out, said

    from pathlib import Path
    # non-interactive: all defaults, not one question asked
    quiet = journey(Path("."), rows, ask=None, echo=None,
                    seat_of=None, interactive=False)
    # the full interactive pass: range scope, count, merging, models
    out, said = run(["", "3", "01", "02", "4", "y", "", "opus-x", ""])
    # a phase choice can match nothing here and re-asks; bad count nags
    out2, said2 = run(["", "2", "Phase 2", "1", "zero", "3", "n",
                       "", "", ""])
    # AIDE down: seat raises -> the unaided lines, journey completes
    def down(role, cwd):
        raise RuntimeError("no lane")
    out3, said3 = run(["", "1", "2", "", "", "", ""], seat_of=down)
    ok = [
        quiet == DEFAULTS,
        out["scope"] == {"01", "02"},
        out["max_parallel"] == 4,
        out["ask_before_merging"] is True,
        agents.MODELS["reviewer"] == "opus-x",   # override written
        agents.MODELS["worker"] == saved["worker"],   # Enter = default
        AIDE_LINE.format(advice="start at the core") in said,
        AIDE_BLOCK_LINE.format(block="01") in said,
        SCOPE_TEXT in said,
        out2["scope"] is None and out2["max_parallel"] == 3,
        SCOPE_UNKNOWN.format(detail="Phase 2") in said2,
        COUNT_NAG in said2,
        out2["ask_before_merging"] is False,
        out3["scope"] is None and out3["max_parallel"] == 2,
        AIDE_DOWN_SCOPE in said3 and AIDE_DOWN in said3,
    ]
    agents.MODELS.clear()
    agents.MODELS.update(saved)
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    selftest()
