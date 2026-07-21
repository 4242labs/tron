#!/usr/bin/env python3
"""tron — the vocabulary. THE single source of truth.

Every word the engine understands is defined here and nowhere else. The
human-readable document GLOSSARY.md is GENERATED from this module
(`python3 glossary.py --write`); selftests fail when it is stale.
"""

import re
import sys
from collections import namedtuple
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "docs" / "GLOSSARY.md"

Word = namedtuple("Word", "sender fields domain meaning")

GLOSSARY = {
    "WORKING":    Word("worker", [], "build",
                       "mid-work heartbeat; never carries a question"),
    "QUESTION":   Word("worker", ["text"], "build",
                       "a decision the worker needs; routed to the architect, "
                       "ruling relayed back"),
    "DONE":       Word("worker", ["branch", "summary"], "build",
                       "all tasks built, tests green, committed on the branch"),
    "CONFIRMED":  Word("worker", ["evidence"], "build",
                       "reply to the engine's DONE challenge: every acceptance "
                       "criterion validated by the worker, with evidence — "
                       "only this makes a DONE valid"),
    "MERGED":     Word("worker", ["branch", "summary"], "build",
                       "merge-window reply: the trunk is merged into the "
                       "branch, conflicts resolved by the worker, full suite "
                       "green on the merged state"),
    "WRAPPED":    Word("worker", ["branch", "summary"], "build",
                       "post-merge wrap: project docs updated where the "
                       "block requires, session log written and committed, "
                       "working tree clean — the arena may retire"),
    "APPROVED":   Word("reviewer", ["summary"], "build",
                       "every task fulfilled and the tests pass"),
    "REJECTED":   Word("reviewer", ["findings"], "build",
                       "numbered, actionable findings; relayed to the worker"),
    "TRANSLATED": Word("architect", [], "build",
                       "an uninterpretable message mapped to its legal form "
                       "(payload = the sender's glossary line)"),
    "ANSWER":     Word("architect", ["text"], "build",
                       "the architect's own ruling; relayed back to the sender"),
    "ESCALATE":   Word("architect", ["reason"], "build",
                       "only the human operator can decide; surfaces in the "
                       "terminal"),
    "ADVICE":     Word("aide", ["text", "block"], "build",
                       "AIDE's bootup advisory to the operator — counsel "
                       "only, never a decision; block names a recommended "
                       "next block or 'none'"),
    "SEND":       Word("player", ["to", "text"], "game",
                       "store-and-forward message; engine stamps identity + "
                       "action ID, delivers on the recipient's next turn"),
    "SOLVE":      Word("player", ["answer"], "game",
                       "one-shot solution who / where / what (pipe-separated); "
                       "judged by the engine "
                       "against the truth it dealt"),
    "PASS":       Word("player", [], "game", "do nothing this turn"),
}


def words_for(role):
    return [w for w, spec in GLOSSARY.items() if spec.sender == role]


def glossary_help(role):
    out = []
    for w in words_for(role):
        payload = " ".join(f"{f}=<{f}>" for f in GLOSSARY[w].fields)
        out.append(f"  >>{w} {payload}".rstrip())
    return "\n".join(out)


def parse(reply, role):
    """(WORD, {field: value}) for a well-formed glossary message, else None."""
    marks = [l.strip() for l in (reply or "").splitlines()
             if l.strip().startswith(">>") and not l.strip().startswith(">>>")]
    if len(marks) != 1:
        return None
    body = marks[0][2:].strip()
    if not body:
        return None
    word = body.split(None, 1)[0].upper()
    if word not in GLOSSARY or GLOSSARY[word].sender != role:
        return None
    rest = body[len(word):].strip()
    if word == "TRANSLATED":
        return (word, {"inner": rest})
    fields = GLOSSARY[word].fields
    keys = "|".join(fields)
    out = {}
    for f in fields:
        m = re.search(rf"{f}=(.*?)(?=\s+(?:{keys})=|$)", rest, re.S)
        if not m or not m.group(1).strip():
            return None
        out[f] = m.group(1).strip()
    return (word, out)


# ---------------------------------------------------------- GLOSSARY.md
def render():
    lines = [
        "# tron — the vocabulary",
        "",
        "> GENERATED from `glossary.py` (the single source of truth).",
        "> Edit there, then run `python3 glossary.py --write`.",
        "> Selftests fail when this file is stale.",
        "",
        "## Gateway rules",
        "",
        "- The engine reads exactly ONE line starting `>>` per reply; zero or"
        " several such lines make the reply uninterpretable. Lines starting"
        " `>>>` are ignored (doctest noise).",
        "- The word must be legal for the sender's role (case-insensitive);"
        " every required field must appear as `field=value`, non-empty.",
        "- All other text is void to the engine. An uninterpretable reply"
        " routes sender → architect (translate | answer | escalate) →"
        " operator.",
        "- `TRANSLATED` is the exception: its payload is the sender's whole"
        " glossary line, not named fields.",
        "",
    ]
    for domain in ("build", "game"):
        lines += [f"## {domain.capitalize()} words", "",
                  "| Word | Sender | Required fields | Meaning |",
                  "|:--|:--|:--|:--|"]
        for w, spec in GLOSSARY.items():
            if spec.domain == domain:
                fields = " ".join(f"`{f}=`" for f in spec.fields) or "—"
                lines.append(f"| `>>{w}` | {spec.sender} | {fields} "
                             f"| {spec.meaning} |")
        lines.append("")
    return "\n".join(lines)


def doc_in_sync():
    return DOC.exists() and DOC.read_text() == render()


if __name__ == "__main__":
    if "--write" in sys.argv:
        DOC.write_text(render())
        print(f"wrote {DOC}")
    else:
        print("in sync" if doc_in_sync() else "STALE — run: python3 glossary.py --write")
        sys.exit(0 if doc_in_sync() else 1)
