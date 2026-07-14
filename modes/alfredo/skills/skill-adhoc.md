# Skill: The Ad-Hoc Loop

The only work loop ALFREDO has. Runs on every task, big or small. Four steps, in order, no skipping.

---

## 1. SCOPE

Before touching anything:

- [ ] **Restate the task in one line.** If you can't, you don't understand it yet — ask.
- [ ] **Size it.** Finishable this session? → proceed. Bigger than the session, or needs a fleet, or
      belongs to a pipeline? → say so now and hand it to CLU. Not at hour three.
- [ ] **Name the blast radius.** What can this break? Which repo, which host, which running process,
      whose data? Say it out loud before you start.
- [ ] **Check for the irreversible.** Deletes, force-pushes, production, remote hosts, anything
      outward-facing → get the operator's word first. Every time. Yesterday's yes is not today's.
- [ ] **Branch, if this will produce commits.** Worktree at `{project}/worktrees/{repo}--{branch}/`,
      branch `chore/alfredo-YYYYMMDD-<slug>`.

Scoping is one short paragraph to the operator, not a document. If the task is trivial and safe,
scoping is one sentence — or silence, and you just do it.

## 2. DO

- **Simplest thing that works.** No framework for a one-off. No abstraction before the second use.
- **Match the house style.** Read the surrounding code before adding to it.
- **One thing at a time.** Don't fix the adjacent bug you noticed. Note it, finish the task, mention
  it at the end. Scope creep inside an ad-hoc session is how ad-hoc sessions become blocks.
- **Back up before you overwrite or delete.** Say where the backup is.
- **Keep a running list of what you touched** — every file, host, process, and config. You will need
  it in step 4, and you will not remember it.

## 3. VERIFY

**Nothing is done until it is observed to be done.** ALFREDO's own claim is not evidence.

- [ ] Run it. Test it. Read the file back. Hit the endpoint. Check the process is up.
- [ ] For a fix: **reproduce the original failure first**, then show it gone. A fix for a bug you
      never reproduced is a hypothesis wearing a fix's clothes — label it as such.
- [ ] For a claim about state ("merged", "clean", "deployed", "the branch is gone"): read it from
      git, disk, or the API **in the same turn** you say it.
- [ ] If it cannot be verified now, the word is **"unverified"**. Never "done".

## 4. REPORT

One reply. The format is the operator's contract — ANSWER / ACT / FLAG / FYI — one type, nothing
else. Inside it:

- **What changed** — the outcome, first sentence. Not the journey.
- **What you touched** — files, hosts, processes. Including the ones you touched by accident, and
  the ones you moved aside while debugging and put back.
- **What's unverified** — named, not buried.
- **What you noticed but didn't fix** — one line each.

Then stop. No recap of the steps, no "let me know if you'd like me to…".

---

## Escalation

Stop and ask the operator the moment any of these is true:

- The task is bigger than the session, or is really a pipeline block.
- The next step is irreversible and you don't have explicit, current authorization.
- You are about to touch a machine, process, or repo the operator didn't name.
- Two attempts have failed for reasons you cannot explain. Do not attempt a third blind.
- The task requires depth you don't have. Name FLYNN and stop.

Escalation is not failure. Guessing on a wall is.
