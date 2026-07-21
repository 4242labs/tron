# TRON — Operator's Guide

*Draft v0.1 — 2026-07-17. Operator-facing walkthrough: what TRON is, how
to point it at a project, the bootup journey it asks you, what it does
unattended, and how to read what it produces. This is a best-judgment
first draft; **the structure and depth the product should ship with are
the operator's call** — the spots marked `[OPERATOR]` need your ruling
before this is final. Written from the live engine, not from intent.*

---

## What TRON is (in one paragraph)

TRON runs a fleet of LLM agents that build software for you against a plan
you approve, and it supervises them with plain code — not with another
LLM. The agents build and review; TRON decides *nothing* by asking a
model. It reads the plan from git, hands each unit of work to a fresh
agent in its own isolated worktree, and refuses to mark anything "done"
until it has checked the repository itself: the branch exists, the tests
it runs *itself* pass, the worker has backed every acceptance criterion
with evidence, and the change re-validates on the trunk after landing.
The one line that captures it: **the model builds, but a deterministic
gate decides done.** You stay in contact through an advisor you can talk
to (AIDE), but the machine never needs you to keep moving — it contacts
you only at the touchpoints you chose, and escalates to you only when it
genuinely cannot proceed.

## What you need

- A **project** laid out the way TRON expects (below).
- Python 3, a git repo for the project, and the models you want seated
  (workers, reviewers, architect/AIDE).
- Optionally a `.env` with `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` so
  the operator line rides Telegram (milestone notes and pages that wait
  for your reply). Without it, everything degrades gracefully to the
  terminal. **Never commit `.env`** — it is gitignored by design.

## Starting a run

```
python3 tron.py            # asks for a project path (Enter = built-in demo)
python3 tron.py --watch    # long-running: idles and wakes on new register work
python3 tron.py --selftest # engine self-check — no agents, no tokens, no cost
```

The first thing TRON does is walk you through a short, **fixed** bootup
dialogue — the same questions every time, in the same order, so there is
no surprise in what you are agreeing to. (Pipe input in and it takes all
defaults and asks nothing — useful for scripted runs.)

## The bootup journey (what it asks you)

1. **Scope — how far do I run?**
   `[1] all · [2] a phase · [3] a range of blocks`
   Choose whether TRON takes the whole open plan, one named phase, or a
   block range. A scope that matches nothing on trunk is refused with a
   clear message, not guessed at.
2. **Worker count.** How many build+review workers to seat. (The
   persistent architect/spec-owner is separate and always present.)
3. **Inform you before each merge to trunk?** `[y/N]`
   Off (default) means TRON lands verified work autonomously up to trunk.
   On means every landing pauses for your go-ahead — useful when you want
   eyes on each merge, at the cost of throughput.
4. **Models per role.** AIDE (your advisor), the architect/spec-owner,
   and the engineers/reviewers — each defaulted, each overridable.

Every answer is written into the run's typed event log, so the exact
choices that governed a run are always recoverable. During scope-setting,
AIDE (a real LLM advisor) offers a recommendation; it is advisory only and
fails open — if it is unavailable the boot proceeds unaided.

> `[OPERATOR]` — the bootup questions, options, and AIDE's recommendation
> text are **frozen**; nothing here changes them. If the shipped product
> needs a different first-run experience, that is a separate decision.

## What a project looks like

TRON reads a project as data. The committed pieces:

| file | what it is |
|:--|:--|
| `context.md` | what the project is |
| `principles.md` | how agents should conduct themselves |
| `playbook.md` | shared infrastructure memory — agents *update* it as they learn |
| `policy.md` | the acceptance bar |
| `blocks/*.md` | one unit of work each; may declare a `test:` and a `trunk-test:` command |
| `pipeline.md` | the register — the ordered plan with per-block status; **written only by the engine** |
| `workflow.toml` | *(optional)* a project-owned process that overrides the engine default (same lint bar) |

You talk to a running fleet through two structural files: `parley.md`
(ask a question → the architect answers from the project's own
artifacts) and `report-request.md` (ask for a report → the architect
writes it, the engine records it under `reports/`).

> `[OPERATOR]` — a "quick start: stand up your first project" tutorial
> (a worked example project from empty dir to first clean landing) is the
> obvious next doc; holding it until you confirm the shape you want.

## What TRON does, unattended

- **Dispatch.** Every block whose dependencies are done is sent — in
  parallel up to your cap — to a fresh agent in its own git worktree
  (*arena*) on the block's own branch. Workers never share a working
  tree, so they cannot collide.
- **The gate.** A worker's `DONE` opens a candidate, nothing more. TRON
  checks the branch carries real work, runs the block's declared tests
  *itself* in the arena, and challenges the worker to confirm every
  acceptance criterion with evidence. Only then does landing begin.
- **Landing.** Inside a single engine-wide merge window, the worker owns
  the merge (it brings trunk in and resolves conflicts); TRON confirms
  the branch already contains trunk and performs the mechanical land,
  then re-validates on the trunk. A block is *done* only when it is
  landed, trunk-green, and wrapped (docs + session log + clean tree).
- **Judges read in isolation.** A reviewer sees the delivery in its own
  detached checkout pinned to the exact commit — the worker cannot move
  what the judge reads, and the judge cannot contaminate the work.
- **Escalation, architect-first.** When something does not fit — an
  unparseable reply, a gate a worker cannot pass, a stall — it routes to
  the in-fleet architect first, which rules on it, answers it, or
  escalates to you with content. You are the last resort, and your answer
  travels back to the exact worker that was stuck. You can answer from
  anywhere via Telegram.
- **Crash recovery.** If a run dies, the next boot kills stray processes,
  sweeps leftover arenas, preserves any unverified branch as `orphan/*`,
  and re-dispatches interrupted blocks fresh.

## Reading what a run produces

Everything for a run lands under `runs/<stamp>.*`:

| artifact | what it tells you |
|:--|:--|
| `…events.jsonl` | the typed event log — one line per engine decision (dispatch, gate, verdict, land, trunk-check). **This is the source of truth**; all stats derive from it, never from agent chatter. |
| `…report.md` | the deterministic, human-readable run report |
| `…manifest.md` | the session roster (who was seated, doing what) |
| `…log` | the verbatim transcript — for debugging, never for measurement |
| `…workflow.toml` | the exact process that drove this run |

Two reference docs stay in sync automatically and are worth knowing:
`GLOSSARY.md` (the closed vocabulary the agents speak) and `WORKFLOW.md`
(the process diagram) — both generated from their single sources, so they
can never drift from what actually ran.

## Stopping and resuming

- A run ends on its own when the scoped work is delivered.
- `--watch` keeps the engine idling; it wakes when new register work
  appears and stops when it finds a `STOP` file in the project.
- Killing the engine mid-run is safe: resume is a non-event (see crash
  recovery above). Nothing is lost, doubled, or double-dispatched.

## When to reach for the operator line

TRON pages you only when it genuinely cannot proceed on its own — a
recurring wall the architect already ruled on, a landing it cannot safely
perform, an impasse above the fleet. A page carries the context and waits
for your reply (on Telegram if configured). Everything short of that, it
handles and records.

> `[OPERATOR]` — remaining sections to add once you confirm scope:
> troubleshooting (common pages and what they mean), a glossary of the
> operator-visible verbs, and a "your first project" tutorial. Flagged,
> not written, pending your call on how much the product should ship.
