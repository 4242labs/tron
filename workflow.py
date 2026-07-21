#!/usr/bin/env python3
"""tron-reborn — the dev process as data.

workflow.toml COMPOSES the process (phases, actors, personas, closing
words, gates, transitions, limits); the engine EXECUTES it — tron.py is
a generic driver walking the parsed table. Every name the file cites
must already exist in code or prompts/: lint() refuses unknown verbs,
unsound wiring, and any flow that drops an invariant — a truth gate
(verify_done + AC challenge) and a recorded review verdict on the pass
spine BEFORE the single landing window. The process is re-modelable by
editing TOML; never past the invariants.

The diagram WORKFLOW.md is GENERATED from the same parsed table
(`python3 workflow.py --write`); selftests fail when it is stale.
"""

import sys
import tomllib
from pathlib import Path

import glossary
import prompts

ROOT = Path(__file__).resolve().parent
FILE = ROOT / "workflow.toml"
DOC = ROOT / "WORKFLOW.md"
END = "landed"                              # the terminal pseudo-phase
ACTORS = ("worker", "reviewer")             # vocabulary roles a phase may seat
GATES = ("verify_done", "verify_merged",    # engine verbs a work phase may cite
         "verify_wrapped")
LIMITS = {"phase_turns": 40, "review_cycles": 2, "gate_fails": 2,
          "turn_seconds": 900, "max_parallel": 2}
REQUIRED = {
    "work":    ("actor", "assign", "word", "gate", "bounce", "next"),
    "verdict": ("actor", "assign", "pass_word", "reject_word", "fix",
                "on_reject", "next"),
}

# ---------------------------------------------------- escalation routing
# workflow.toml above composes the PASS spine — how a block advances when
# all goes well. This table composes the EXCEPTION spine — where a stuck
# seat's signal goes. The engine (tron.py) ROUTES from it and the diagram
# (bpmn.py) DRAWS it, so the escalation the engine runs and the escalation
# the picture shows read one source and cannot drift.
#
# Above the workflow actors sit two seats: the ARCHITECT (an LLM, judges
# every stuck signal FIRST — "architect-first") and the OPERATOR (the
# terminal, the last resort). A signal climbs the tiers in order; a ruling
# returns it to the stuck seat; an escalation — or a recurrence of an
# already-ruled wall, or the architect_first arm ablated — reaches the
# operator, whose answer syncs back down through the architect.
ESC_TIERS = ("architect", "operator")   # above the actors; architect-first
ESC_SYNC = "architect"                  # the operator's answer syncs here

# what puts a seat on the exception spine, and how each is judged
ESC_TRIGGERS = (
    {"id": "question", "origin": "seat",
     "judge": "architect reads the block, rules or escalates"},
    {"id": "unparsable", "origin": "seat",
     "judge": "architect translates, rules, or escalates"},
    {"id": "wall", "origin": "engine",
     "judge": "architect rules first; a recurrence goes straight up"},
    {"id": "parley", "origin": "operator",
     "judge": "architect answers from the artifacts, or escalates"},
)

# the exception edges, source lane -> target lane; "seat" is whichever
# workflow actor is stuck. bpmn.py draws exactly these as the overlay.
ESC_EDGES = (
    {"frm": "seat", "to": "architect",
     "name": "stuck: QUESTION / wall / unparsable"},
    {"frm": "architect", "to": "seat", "name": "ruling — back to the seat"},
    {"frm": "architect", "to": "operator", "name": "ESCALATE / recurrence"},
    {"frm": "operator", "to": "architect", "name": "answer — syncs back"},
)


def escalation_route(occurrence=1, ablated=False):
    """The tiers a stuck signal climbs, in order. Architect-first — unless
    the architect tier is skipped, which happens on a recurrence of an
    already-ruled wall (occurrence > 1) or when the architect_first arm is
    ablated; then the signal goes straight to the operator. The operator's
    answer always syncs back through ESC_SYNC. Returns the ordered tier ids
    the engine visits — the single source of the architect-first decision."""
    skip_architect = ablated or occurrence > 1
    return [t for t in ESC_TIERS
            if not (t == "architect" and skip_architect)]


def parse_file(path=FILE):
    return tomllib.loads(Path(path).read_text())


def file_for(project):
    """The flow that governs a project: its own committed workflow.toml
    when it carries one (the project owns its process), else the engine
    default. Both pass the same lint — invariants hold either way."""
    p = Path(project) / "workflow.toml"
    return p if p.exists() else FILE


def limits(flow):
    return {**LIMITS, **flow.get("limits", {})}


def persona_of(ph):
    return ph.get("persona", ph["actor"])


def lint(flow):
    """Every problem in the flow; empty = sound. The engine refuses to
    boot on a non-empty list — an unsound process must never run."""
    p = []
    if flow.get("version") != 1:
        p.append("version must be 1")
    if not str(flow.get("name", "")).strip():
        p.append("name is required")
    for k, v in flow.get("limits", {}).items():
        if k not in LIMITS:
            p.append(f"limits.{k} is not a limit")
        elif not (isinstance(v, int) and v >= 1):
            p.append(f"limits.{k} must be an integer >= 1")
    phases = flow.get("phase") or []
    if not phases:
        return p + ["at least one [[phase]] is required"]
    ids = [ph.get("id") for ph in phases]
    if None in ids or len(set(ids)) != len(ids):
        return p + ["every phase needs a unique id"]
    for ph in phases:
        pid, kind = ph["id"], ph.get("kind")
        if kind not in REQUIRED:
            p.append(f"{pid}: kind must be work|verdict")
            continue
        missing = [f for f in REQUIRED[kind] if not ph.get(f)]
        if missing:
            p.append(f"{pid}: missing {', '.join(missing)}")
            continue
        actor = ph["actor"]
        if actor not in ACTORS:
            p.append(f"{pid}: actor must be one of {'|'.join(ACTORS)}")
            continue
        if not (prompts.DIR / f"persona_{persona_of(ph)}.md").exists():
            p.append(f"{pid}: persona '{persona_of(ph)}' has no "
                     f"prompts/persona_{persona_of(ph)}.md")
        for key in ("assign", "bounce", "fix"):
            if ph.get(key) and not (prompts.DIR / f"{ph[key]}.md").exists():
                p.append(f"{pid}: {key} prompt '{ph[key]}' does not exist")
        words = glossary.words_for(actor)
        for key in ("word", "pass_word", "reject_word"):
            if ph.get(key) and ph[key] not in words:
                p.append(f"{pid}: {key} '{ph[key]}' is not a {actor} word")
        if kind == "work" and ph["gate"] not in GATES:
            p.append(f"{pid}: gate must be one of {'|'.join(GATES)}")
        if kind == "verdict" and any(ph.get(k) for k in
                                     ("land", "window", "challenge", "gate")):
            p.append(f"{pid}: land/window/challenge/gate belong to work phases")
        for key in ("next", "on_reject"):
            tgt = ph.get(key)
            if tgt and tgt != END and tgt not in ids:
                p.append(f"{pid}: {key} '{tgt}' is not a phase")
        if ph.get("on_reject") == END:
            p.append(f"{pid}: on_reject may never reach {END}")
    if p:
        return p     # field problems first; wiring checks need clean fields
    byid = {ph["id"]: ph for ph in phases}
    # the pass spine: follow `next` from the entry; it must reach `landed`
    spine, seen, cur = [], set(), phases[0]["id"]
    while cur != END:
        if cur in seen:
            return [f"pass spine loops at '{cur}' — it must reach {END}"]
        seen.add(cur)
        spine.append(byid[cur])
        cur = byid[cur]["next"]
    # the window span: opened at the first window=true spine phase, held
    # to the very end — main only moves inside it, so every land is safe
    win = [i for i, ph in enumerate(spine) if ph.get("window")]
    if not win:
        p.append("no window on the spine: landing needs a merge window")
    else:
        first = win[0]
        if win != list(range(first, len(spine))):
            p.append("the window must be one unbroken span ending the spine "
                     "— a non-window phase after it would land outside it")
        if not spine[first].get("gate") == "verify_merged":
            p.append(f"{spine[first]['id']}: the window opens on the merge — "
                     "its first phase must gate on verify_merged")
        if not (spine[-1].get("land") and spine[-1]["next"] == END):
            p.append(f"{spine[-1]['id']}: the spine must end with a landing "
                     f"phase (land=true, next={END})")
        pre = spine[:first]
        if not any(ph["kind"] == "work" and ph.get("gate") == "verify_done"
                   and ph.get("challenge") for ph in pre):
            p.append("no truth gate on the spine: a work phase with "
                     "gate=verify_done and challenge=true must precede the "
                     "window")
        if not any(ph["kind"] == "verdict" for ph in pre):
            p.append("no review on the spine: a verdict phase must precede "
                     "the window")
    for ph in phases:
        if ph.get("land") and not ph.get("window"):
            p.append(f"{ph['id']}: every landing phase must be in the window")
        if ph.get("window") and ph not in spine:
            p.append(f"{ph['id']}: a window phase must sit on the pass spine")
        if ph["next"] == END and not ph.get("land"):
            p.append(f"{ph['id']}: only a landing phase may reach {END}")
        if ph.get("window") and ph.get("on_reject"):
            p.append(f"{ph['id']}: no reject route out of the window")
    # reachability: every phase, from the entry, via next + on_reject
    reach, todo = set(), [phases[0]["id"]]
    while todo:
        cur = todo.pop()
        if cur in reach or cur == END:
            continue
        reach.add(cur)
        todo += [t for t in (byid[cur]["next"], byid[cur].get("on_reject"))
                 if t]
    p += [f"{ph['id']}: unreachable from the entry phase"
          for ph in phases if ph["id"] not in reach]
    return p


# --------------------------------------------------------- WORKFLOW.md
def seat_of(ph):
    return ph["actor"] + (f" as {persona_of(ph)}"
                          if persona_of(ph) != ph["actor"] else "")


def mermaid(flow):
    lim = limits(flow)
    L = ["flowchart TD",
         '  DISPATCH(["engine: dispatch — fresh arena, '
         'branch feat/&lt;block&gt; off main"])']
    for ph in flow["phase"]:
        if ph["kind"] == "work":
            gate = ph["gate"] + (" + AC challenge" if ph.get("challenge")
                                 else "")
            win = "<br>window: one at a time" if ph.get("window") else ""
            L.append(f'  {ph["id"]}["{ph["id"].upper()} — {seat_of(ph)}'
                     f'<br>closes >>{ph["word"]} ⊢ {gate}{win}"]')
        else:
            L.append(f'  {ph["id"]}{{"{ph["id"].upper()} — {seat_of(ph)}'
                     f'<br>>>{ph["pass_word"]} / >>{ph["reject_word"]} '
                     f'(recorded)"}}')
    L += ['  LAND["engine: mechanical land + suite re-run ON the trunk"]',
          '  REGISTER(["engine: register stamped done"])',
          f'  DISPATCH --> {flow["phase"][0]["id"]}']
    for ph in flow["phase"]:
        if ph["kind"] == "work":
            tgt = "LAND" if ph.get("land") else ph["next"]
            L.append(f'  {ph["id"]} -->|">>{ph["word"]} ✓ {ph["gate"]}"| {tgt}')
            L.append(f'  {ph["id"]} -.->|"bounce ≤{lim["gate_fails"]}, '
                     f'then operator"| {ph["id"]}')
        else:
            L.append(f'  {ph["id"]} -->|">>{ph["pass_word"]}"| {ph["next"]}')
            L.append(f'  {ph["id"]} -.->|">>{ph["reject_word"]} '
                     f'≤{lim["review_cycles"]} → {ph["fix"]}"| '
                     f'{ph["on_reject"]}')
    L.append("  LAND --> REGISTER")
    return "\n".join(L)


def render(flow=None):
    flow = flow or parse_file()
    lim = limits(flow)
    lines = [
        "# tron-reborn — the workflow",
        "",
        "> GENERATED from `workflow.toml` (the single source of the process).",
        "> Edit there, then run `python3 workflow.py --write`. Selftests fail",
        "> when this file is stale; the engine lints the same table at boot",
        "> and refuses to run an unsound flow.",
        "",
        f"Process: **{flow['name']}** (version {flow['version']}) — limits: "
        f"{lim['phase_turns']} turns/phase, {lim['review_cycles']} review "
        f"cycles, {lim['gate_fails']} gate bounces (each cap ends at the "
        f"operator), {lim['max_parallel']} blocks in flight.",
        "",
        "```mermaid",
        mermaid(flow),
        "```",
        "",
        "## Phases",
        "",
        "| Phase | Kind | Seat | Opens with | Closes on | Verified by "
        "| Pass → | Reject/bounce |",
        "|:--|:--|:--|:--|:--|:--|:--|:--|",
    ]
    for ph in flow["phase"]:
        if ph["kind"] == "work":
            ver = ph["gate"] + (" + AC challenge" if ph.get("challenge")
                                else "")
            nxt = ph["next"] + (" (engine lands + re-validates the trunk)"
                                if ph.get("land") else "")
            lines.append(
                f"| {ph['id']} | work{' · window' if ph.get('window') else ''}"
                f" | {seat_of(ph)} | `{ph['assign']}` | `>>{ph['word']}` "
                f"| {ver} | {nxt} | bounce `{ph['bounce']}` |")
        else:
            lines.append(
                f"| {ph['id']} | verdict | {seat_of(ph)} | `{ph['assign']}` "
                f"| `>>{ph['pass_word']}` / `>>{ph['reject_word']}` "
                f"| recorded in reviews.md | {ph['next']} "
                f"| {ph['on_reject']} via `{ph['fix']}` |")
    lines += [
        "",
        "## Escalation — the exception spine",
        "",
        "> The same table the engine routes from (`workflow.ESCALATION`) and",
        "> the BPMN diagram (`workflow/`) draws from — the picture cannot",
        "> drift from what the engine runs.",
        "",
        f"Above the actors sit two seats — **{'** then **'.join(ESC_TIERS)}** "
        f"— climbed in that order (architect-first). A ruling returns to the "
        f"stuck seat; an escalation, a recurrence of an already-ruled wall, or "
        f"the `architect_first` arm ablated reaches the operator, whose answer "
        f"syncs back through the **{ESC_SYNC}**.",
        "",
        "| Trigger | Raised by | How it is judged |",
        "|:--|:--|:--|",
    ]
    lines += [f"| {t['id']} | {t['origin']} | {t['judge']} |"
              for t in ESC_TRIGGERS]
    lines += [
        "",
        "## Invariants the lint enforces (cannot be edited away)",
        "",
        "- a truth gate (`verify_done` + AC challenge) and a recorded review",
        "  verdict sit on the pass spine BEFORE landing",
        "- exactly one landing phase; it is the only window and the only exit",
        "- every verdict is recorded durably — recording is not optional",
        "- every word/gate/prompt/persona named here exists in code or",
        "  prompts/; transitions resolve; every phase is reachable",
        "",
    ]
    return "\n".join(lines)


def doc_in_sync():
    return DOC.exists() and DOC.read_text() == render()


# -------------------------------------------------------------- selftest
def selftest():
    import copy
    base = parse_file()

    def broke(mut):
        f = copy.deepcopy(base)
        mut(f)
        return bool(lint(f))

    # a LEGAL re-model: a second verdict seat under a different persona,
    # inserted by data alone — the double-review variant the SIM runs
    variant = copy.deepcopy(base)
    variant["phase"].insert(2, {
        "id": "audit", "kind": "verdict", "actor": "reviewer",
        "persona": "auditor", "assign": "review_assign",
        "pass_word": "APPROVED", "reject_word": "REJECTED",
        "fix": "fix", "on_reject": "build", "next": "merge"})
    variant["phase"][1]["next"] = "audit"

    ok = [
        lint(base) == [],
        doc_in_sync(),
        limits(base)["phase_turns"] >= 1,
        limits({}) == LIMITS,
        limits({"limits": {"max_parallel": 4}})["max_parallel"] == 4,
        # the lint refuses every class of unsound edit
        broke(lambda f: f.pop("version")),
        broke(lambda f: f.update(name=" ")),
        broke(lambda f: f["phase"][0].update(gate="trust_me")),
        broke(lambda f: f["phase"][0].update(word="APPROVED")),  # not a worker word
        broke(lambda f: f["phase"][0].update(actor="ghost")),
        broke(lambda f: f["phase"][0].update(persona="ghost")),
        broke(lambda f: f["phase"][0].update(assign="no_such_prompt")),
        broke(lambda f: f["phase"][0].update(next="nowhere")),
        broke(lambda f: f["phase"][0].update(challenge=False)),  # truth gate gone
        broke(lambda f: f["phase"][0].update(next="merge")),     # review skipped
        broke(lambda f: f["phase"][1].update(on_reject="landed")),
        broke(lambda f: f["phase"][1].update(land=True)),        # land on a verdict
        broke(lambda f: f["phase"][3].update(land=False)),       # spine end not landing
        broke(lambda f: f["phase"][2].update(window=False)),     # land outside window
        broke(lambda f: f["phase"][2].update(gate="verify_done")),  # window w/o merge gate
        broke(lambda f: f["phase"][0].update(land=True, window=True)),  # broken window span
        broke(lambda f: (f["phase"][3].pop("window"),
                         f["phase"][3].pop("land"))),            # wrap outside window
        broke(lambda f: f["phase"][1].update(next="review")),    # spine loops
        broke(lambda f: f["phase"][1].update(id="build")),       # duplicate id
        broke(lambda f: f.update(limits={"gate_fails": 0})),
        broke(lambda f: f.update(limits={"budget": 9})),
        broke(lambda f: f.update(phase=[])),
        lint(variant) == [],
        # per-project override: a project carrying workflow.toml owns its
        # process; one without falls back to the engine default
        file_for(ROOT / "nonexistent-project") == FILE,
        (lambda d: ((d / "workflow.toml").write_text("version = 1") or True)
         and file_for(d) == d / "workflow.toml")
        (Path(__import__("tempfile").mkdtemp(prefix="wf-proj-"))),
        "audit" in mermaid(variant),
        "auditor" in render(variant),
        ">>DONE" in mermaid(base),
        "verify_merged" in render(),
        # escalation table: architect-first, operator terminal, sync home
        ESC_TIERS[0] == "architect" and ESC_TIERS[-1] == "operator",
        ESC_SYNC in ESC_TIERS,
        # the route the engine executes — architect-first exactly when the
        # architect tier is NOT skipped (first occurrence, arm not ablated)
        escalation_route(1, False) == ["architect", "operator"],
        escalation_route(2, False) == ["operator"],     # recurrence skips up
        escalation_route(1, True) == ["operator"],       # ablated skips up
        escalation_route(9, True) == ["operator"],
        # the overlay edges the diagram draws reference only known lanes
        all(e["frm"] in ("seat",) + ESC_TIERS
            and e["to"] in ("seat",) + ESC_TIERS for e in ESC_EDGES),
        # the exception spine appears in the generated doc
        "Escalation — the exception spine" in render(),
        "architect-first" in render(),
    ]
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--write" in sys.argv:
        DOC.write_text(render())
        print(f"wrote {DOC}")
    else:
        problems = lint(parse_file())
        print("sound" if not problems else "UNSOUND:\n  - "
              + "\n  - ".join(problems))
        print("doc in sync" if doc_in_sync()
              else "DOC STALE — run: python3 workflow.py --write")
        sys.exit(0 if not problems and doc_in_sync() else 1)
