"""tron — prompt loader.

Every boilerplate the engine ever says to an LLM lives under prompts/,
one file per prompt. `{gateway}` in a template composes the shared
preamble (prompts/gateway.md) — the single copy of the gateway rules —
and `{persona}` composes the sender's persona (prompts/persona_<role>.md,
picked by the template's `role` argument): minimal, one per role, never
duplicated into assignments.
"""

from pathlib import Path

DIR = Path(__file__).resolve().parent / "prompts"


def raw(name, /):
    return (DIR / f"{name}.md").read_text().rstrip("\n")


def prompt(name, /, **kw):
    text = raw(name)
    if "{persona}" in text:
        kw = {**kw, "persona": raw(f"persona_{kw['role']}")}
    if "{gateway}" in text:
        kw = {**kw, "gateway": raw("gateway").format(**kw)}
    return text.format(**kw)


def names():
    return sorted(p.stem for p in DIR.glob("*.md"))
