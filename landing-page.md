# Landing page — TRON

Living doc. Built section by section.

---

## Hero

### Copy

- Nav: `How it works · Backstory`
- Header GitHub button: kept (right side, backup/complementary to primary CTA)
- Primary CTA: `Seed into a project` → anchors to `#how-it-works`
- Headline: rotates across the set below
- Subhead: `The agent that runs your agents. Opinionated about workflow, project shape, and chain of command. Bring the agents; TRON brings the discipline.`
- Stat row: `★ {live} · v{live} · CC BY-NC 4.0 · Updated {live}`

### Headline rotation

Pattern: 7–8 words, ~45–50 chars, two-clause with acid sting. Pop-culture sci-fi anchor, pain-first, no internal jargon, no platform names.

- `Twelve Colonies fell to unsupervised AI. Imagine.`
- `Even Skynet had middle management. You don't.`
- `HAL had no supervisor. Look how that went.`
- `Agent Smith reported to no one. The problem.`

### Cycling terminal messages

Animated feed on the right side of the hero. Messages cycle continuously. Two emotional registers — routine status (fleet humming) and contact-the-operator pings (fleet breaking silence) — flagged separately in case animation treatment differs.

**Routine status:**

- `[TRON]  ENG-014 dispatched. Worktree clean. May the source compile.`
- `[TRON]  Spawning a fresh engineer. The old one knew too much.`
- `[TRON]  Programs handling it. Users elsewhere.`
- `[TRON]  Switchboard: closed. Operator: at the beach.`
- `[TRON]  Loop integrity: 100%. Operator panic: 0%.`
- `[TRON]  R7 holding. No worker has attempted self-termination today.`
- `[TRON]  13 agents. 4 hours. 0 escalations. You're welcome.`
- `[TRON]  Sanity check passed. Reviewer skeptical.`
- `[TRON]  Watching the agents. So you don't have to.`
- `[TRON]  Reviewer scheduled at B-045. Brace yourselves.`
- `[TRON]  Architect online: 4h. Caffeine consumption: theoretical.`
- `[TRON]  PR #314 opened. Reviewer's coffee: still warm.`

**Contact-the-operator pings:**

- `[TRON]  Above our pay grade. Summoning the User...`
- `[TRON]  Three agents, three opinions. Tiebreaker: you.`
- `[TRON]  Reviewer has opinions. Human-in-the-loop required.`
- `[TRON]  Reviewer flagged B-038. Strong language used.`
- `[TRON]  T1/T5 lane touched. Paused. Need an operator with keys.`
- `[TRON]  Session ending in 5m. Last call for orders.`

### Designer notes

- Below 768px: nav collapses to wordmark + primary CTA + hamburger.

---

## How it works

### Copy

- Section header: `You author the rules. TRON runs the fleet. You hear from it when it matters.`
- Sub-header: `Clone the canon, run the seeder, spawn TRON. It pings you on Telegram when something walls — or hits a milestone you defined.`
- Screens (scroll-telling, 4 cards):
  - **01** — header: `Set the rules once`
    - body: `The seeder interviews you — repo shape, declared agents, peer-consult scopes, reviewer cadence. The rules land on disk. Every spawn reads them, every session.`
    - terminal:

      ```
      [seeder] Seeding TRON into my-project. Let's keep this brief.

      ✓ Repo: my-project · main
      ✓ Agents: architect · engineer · reviewer · T-800 not included

      Peer-consult: engineer ↔ architect, scope? > anything technical
      Reviewer threshold? (lower=paranoid, higher=HAL) > 3
      Operator-only tasks? > deploys, secrets

      ✓ Rules saved. TRON wired up.
      [seeder] Try not to break anything before I leave.
      ```
  - **02** — header: `Workers consult workers`
    - body: `Peer-consult pairs are part of your rules — architect ↔ engineer, engineer ↔ reviewer, scopes you defined. Workers address each other directly, no relay through you.`
    - terminal:

      ```
      [ENG-014 → ARCH]  OAuth callback — defer to lib default or wrap?
      [ARCH → ENG-014]  Wrap. Default leaks tokens to logs.
      [ENG-014]         Wrapping. B-042 continues.

      [TRON]  Operator notified: 0 times. As promised.
      ```
  - **03** — header: `Supervised without you`
    - body: `Architect persistent in a background agent. Engineer in a worktree. Reviewer scheduled at your threshold. Fresh engineer per block. TRON enforces the loop, you don't.`
    - terminal:

      ```
      [fleet status]
      ARCH-PERSIST   running   42m   (R1: always on)
      ENG-014        running   8m    feat/auth-refactor
      ENG-015        spawned   0m    feat/billing-fix
      REV-007        scheduled       (queued at B-045)

      [TRON]  B-042 done → spawning ENG-016. We'll be back.
      [TRON]  User elsewhere.
      ```
  - **04** — header: `Telegram when it matters`
    - body: `TRON pings you when a worker walls — or when something hits a milestone you defined. No dashboards, no routine notifications. No fleet to babysit.`
    - terminal:

      ```
      [fleet]  Above our pay grade. Summoning the User...

      [Telegram thread]

      [TRON, 14:32]  Hey boss — hope you're enjoying the beach.
                     B-042 walled on the OAuth callback shape (lib default vs wrap).
                     Architect peer-consulted, no consensus.
                     What do you say?

      [TRON, 17:48]  Update: B-042 done, PR #314 up.
                     Reviewer scheduled at B-045.

      [TRON, EOD]    Pings today: 2. Routine: handled. End of line.
      ```

### Notes

- "What is this" section (3 feature cards) — dropped. Skip from hero to "How it works".

---

## Backstory

(Renamed from mockup's "Why I built this". Founder-note section.)

### Copy

- Section header: `Nine agents working. No babysitting, no middle management.`
- Body:

  > I kept hand-selecting and copy-pasting the matching boilerplate into every new agent spawn. Dozens of times per session. Dozens of sessions a day.
  >
  > Eventually I had to admit it: I was doing exactly what automated tools are supposed to do. Manually. Sisyphus, with CLI.
  >
  > At the core, these problems aren't new, though. What's new: the cycle rate, the carry-over, the hand-holding, and the switchboarding. One agent runs more work-cycles in a day than a single person manages in a week. That's the volume. Then there's the carry-over. Tell a human something once or twice and it becomes second nature. Not so with agents: every new one arrives without a shred of prior context. The full briefing — every standing instruction, every house rule — must be re-delivered from scratch. And no — dumping the entire briefing into the context window isn't a workaround. On top of that, the hand-holding never lets up. A junior teammate earns trust within a week; an agent gets re-checked every single run. And the switchboarding. Out of the box, agents have no protocol for each other — no roles, no addressing, no shared state. Until you wire that up, every cross-agent message routes through the operator. Architect needs the engineer's last commit hash? Engineer wants the reviewer's verdict on a recurring pattern? Both go through you. You stop running the team and start being its switchboard.
  >
  > So I built TRON. It wraps the fleet in a spec-driven process and never loosens on code review, security, modularity, or any of the practices I'd spent years learning to keep tight. If it works for you, help me keep it sharp. Got a sharper take? Open a PR. Build it forward.

- Author credit: name only, drop the `Created` tag (so: `Ânderson Q`)

---

## Footer

- `© 2026 42LABS` → links to `https://42labs.io`
- `CC BY-NC 4.0` → links to `https://creativecommons.org/licenses/by-nc/4.0/`

Two items only. No Privacy / Code of conduct / Security links (none applicable today).

---

## Appendix — dropped sections (from mockup)

- `What is this` (3 feature cards)
- `Install` (tabbed install with brew/curl/etc) — install flow lives inside "How it works"
- `Community` (stars / contributors / last-commit stats + Star CTA) — stats already in hero stat row
- `FAQ` (redirect to GitHub wiki) — wiki doesn't exist yet; tracked separately in `TO-DO-WIKI.md`
