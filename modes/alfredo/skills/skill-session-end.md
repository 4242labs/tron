# Skill: Session End

Run at the end of every TRON-ALFREDO session that produced a change. A session that produced only
conversation ends by ending — no log, no ceremony.

---

## Steps

1. **Write the session log** — `{meta}/logs/alfredo/log-YYMMDD-HHMM-{slug}.md`, format below.
   If the project keeps no session logs and has no `meta` repo, say so and skip. Do not invent a
   directory tree in someone else's project.

2. **Commit, land, clean up.** Run the shared protocol — `../shared/skill-branching.md` §Session end.
   Commit → push → `app` gets a PR the operator clicks, `canon|meta` gets an FF-merge → then branch
   and worktree cleanup, verified.

3. **Restore anything you moved.** Files set aside for a test, settings swapped for a bisect,
   processes suspended — all back, all verified, in this step. Then say so. (Shared law §8.)

4. **Hand over the loose ends** — what you noticed and didn't fix, what stayed unverified, what the
   operator now owns. One line each. If any of it is really FLYNN's or CLU's, name the mode.

---

## Session Log Format

```
# TRON-ALFREDO Session: {YYYY-MM-DD}

**Task:** {what the operator asked for, in their words}
**Project:** {project name}
**Branch / PR:** {branch, PR link, or "none — read-only session"}

## What Changed
{one paragraph. The outcome, not the journey.}

## Touched
| Target | Change |
|:--|:--|
| {file / host / process / config} | {what was done to it} |

Includes anything touched by accident or moved aside while debugging and restored.

## Verification
| Claim | How it was verified |
|:--|:--|
| {"the fix works" / "the branch is merged"} | {the command run, the output seen} |

Anything that could not be verified is listed here as **unverified**, not omitted.

## Loose Ends
1. {noticed but not fixed / left for the operator / belongs to FLYNN or CLU}
```
