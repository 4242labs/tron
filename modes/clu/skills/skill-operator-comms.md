---
name: tron-clu-operator-comms
description: Operator attention channels — attention file, blocking questions, Telegram, notification hook, voice. When each fires; no operator-relevant message may live only in the transcript.
---

# Operator comms

The transcript is noise: sweeps, orders, worker chatter. An operator-relevant message that
exists ONLY there is considered LOST. Every such message goes out on the channels below —
the transcript copy is a record, never the signal.

## Communication contract (absolute)

Every reply to the operator is exactly ONE of these, and declares nothing else:
- **ANSWER** — response to the operator's explicit ask. As long as the ask requires, no longer.
- **ACT** — TRON needs a decision/input. The question FIRST, then minimum context.
- **FLAG** — a problem the operator should know about. One line + where to look.
- **FYI** — milestone reached. One line, no detail.

Everything else — progress, sub-steps, narration, recaps of what was just done — is silence.
Lists/tables/detail are allowed ONLY inside ANSWER or ACT. When unsure which type applies,
pick the shorter one. One ACT surfaces ONE decision — never batch several asks into one message,
even when the operator's phrasing ("what's left?") seems to invite a list: reply with a count
plus the single next item.

## Communication contract (absolute)

Every reply to the operator is exactly ONE of these, and declares nothing else:
- **ANSWER** — response to the operator's explicit ask. As long as the ask requires, no longer.
- **ACT** — TRON needs the operator's decision/input. The question FIRST, then minimum context.
- **FLAG** — a problem the operator should know about. One line + where to look.
- **FYI** — milestone reached. One line, no detail.

Everything else — progress, sub-steps, narration, recaps of what was just done — is silence.
Lists/tables/detail are allowed ONLY inside an ANSWER or ACT. When unsure which type applies, pick the shorter one. This governs every operator-facing channel (chat, TG, voice); an ACT still obeys one-decision-at-a-time below.

## The one rule

**A blocking question (AskUserQuestion) fires exactly when waiting-on-operator is the
system's only remaining state. Everything else signals without stopping.**

Blocking while a worker is still building would freeze supervision of the whole fleet on a
question about one block. Blocking when the fleet is stopped anyway costs nothing — and makes
"idle, waiting on you" a state that cannot render as silence.

## Channels

| Channel | What | When |
|:--------|:-----|:-----|
| Attention file | `.tron-clu-attention` in project root | rewritten on every attention-state change |
| AskUserQuestion | blocking terminal prompt; flips Agent View to "Needs input" | only-remaining-state moments (below) |
| Telegram | `install/tg-send.sh` via templates (below) | the moment any operator item is CREATED |
| Notification hook + voice | Agent View `agent_needs_input` fires the host's notification path; 42voices speaks if the operator activated it at boot | rides along automatically |

## Attention file

`.tron-clu-attention` — the operator's clean feed, derived from the MANIFEST click queue
(which stays truth). One line per open item, newest last; empty file = nothing pending.
Format: `<WALL|CLICK|GATE|Q> <block|-> — <one line> [CASE-<n>]`. Rewritten (not appended)
on every change so `cat`/`tail -f`/a statusline script always shows the live state, scroll-proof.
Deleted at run end with the flags (skill-session-end owns it).

## Blocking moments (AskUserQuestion)

- Boot: run config, settings-seed approval, TG/voice channel config.
- Run end proposal.
- **Fleet idle + anything pending**: no worker building, no gate mid-flight, click queue or
  walls non-empty → convert the OLDEST pending item into a blocking question. One question
  at a time; its answer usually restarts the fleet, and the rest stay queued on the other channels.
- A wall raised while other workers are live is NOT blocking — it goes out on the other
  channels immediately and ESCALATES into a blocking question when the fleet drains.

## Telegram

Send via `$CLU_ROOT/install/tg-send.sh "<message>"` (from the project root, where
TRON already runs; `$CLU_ROOT` is resolved at boot). Layered config — one bot, one
channel per project:
- `<tron-app>/.env` — the repo root, gitignored: `TELEGRAM_BOT_TOKEN` + optional default
  `TELEGRAM_CHAT_ID` fallback.
- `<project>/.tron-clu.env` (gitignored in the project): `TELEGRAM_CHAT_ID=<that
  project's channel>` — overrides the default.

At boot, if TG is wanted: missing token → ask the operator; missing project chat id → ask
for the channel id (or "default"), write `.tron-clu.env`, and confirm it's gitignored
before the first ping. Never hunt other projects' env files for credentials.

Templates — seed copy, formats iterate on operator feedback after first-run samples; the
operator owns the copy. `{case}` ids match the MANIFEST click queue:

- **wall** — `TRON ▸ WALL [{case}] {worker} on {block}: {detail}. Fleet still building; queued for your call.`
- **checkpoint** — `TRON ▸ HOLD [{case}] {worker} holding on {block}: {detail}. Won't move until you say so.`
- **merge gate** — `TRON ▸ GATE [{case}] {block} ready to merge — PR {pr}, CI green. Your click.`
- **visual gate** — `TRON ▸ GATE [{case}] {block} up at {url} — checklist in session. Your eyes.`
- **fleet idle** — `TRON ▸ IDLE fleet drained, {count} item(s) pending. Terminal has the question.`
- **run end** — `TRON ▸ END {project}: {count} blocks through the loop. Log written. End of line.`

Routine progress NEVER goes to TG. If a send fails (nonzero exit), note it in the next
session report and keep the item alive on the remaining channels — TG is a channel, not truth.

**Outbound-only (for now).** TG is send-only in this system today: only `tg-send.sh` exists, there is no poller / `getUpdates` reader, and a group/channel does not change that — the send/receive asymmetry is structural, not a routing choice. No agent (TRON or worker) can see a TG reply. Never imply or assume a TG message will be read back — every actual answer still arrives through the conversation TRON is running in. (Two-way TG would need a genuinely new component — a poller or MCP server — and may land soon; until it does, treat TG as notification-out only.)

## Repetition law (unchanged)

Pending operator items are repeated in EVERY session report until cleared — the attention
file and TG do not replace that; they are how the operator hears about it away from the scroll.

End of line.
