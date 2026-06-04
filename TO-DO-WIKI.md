# TO-DO: TRON Wiki

Status: not yet created. Repo at `42piratas/tron.wiki.git` returns 404. Landing page FAQ section depends on this — it redirects to `github.com/42piratas/tron/wiki`.

---

## Outline

### 1. Getting Started

- Quickstart (expanded from README)
- Prerequisites in depth
- First-seed walkthrough (annotated)
- Verifying your seed (`skill-validate` + `skill-doctor` explained)

### 2. Concepts

- Canon vs. instance (what the seeder does)
- The 23 design premises (currently only in private plan repo — surface here)
- Operator-in-the-loop architecture
- Workers-never-self-terminate (Premise 20 rationale)
- Peer-consult model (Premise 18)
- The autonomous loop (cron + Agent View + Telegram)
- Mode A vs Mode B edits (config vs runtime state)

### 3. How-To Guides

- Author a custom workflow rule
- Add a new worker role (beyond architect / engineer / reviewer)
- Define peer-consult pairs
- Add a custom situation to `scripts.md`
- Configure Telegram escalation (incl. chat-id discovery — undocumented per `FEEDBACK-seeder.md`)
- Set up multi-repo workspace (zovv-shape)
- Set up multi-reviewer (3 roles, split R5)
- Recover after a crash
- Update canon into your local instance

### 4. Reference

- All 9 skills, fully documented
- Schemas: `workflow.md`, `project.md`, `workflow-state.md`, `state.md`, `scripts.md`
- Handover templates (engineer / architect / reviewer)
- All 4 shell scripts (`cron-install.sh`, `sweep.sh`, `tg-poll.sh`, `tg-send.sh`)
- The 23 premises listed in one place

### 5. Operations & Troubleshooting

- Common operator situations (runbook)
- Stall sweep dynamics
- Debugging a stuck worker
- When TRON misbehaves
- Re-seeding safely

### 6. FAQ

- Can I use this commercially? (CC BY-NC nuance)
- How is this different from LangGraph / CrewAI / AutoGen?
- What stack does this require?
- Is there a SaaS / hosted version?
- Why markdown instead of YAML or code?
- What happens if TRON crashes mid-session?
- Can I extend it?
- How do I contribute?

### 7. Contributing

- Canon purity rules
- PR guidelines (no project-specific traces)
- Versioning convention
- Where feedback docs land

---

## Dependencies

- **Landing page FAQ** (`landing-page.md`) redirects to `/wiki` — wiki must exist before site goes live, OR FAQ section must be replaced with on-page Q&A.
- **23 design premises** — currently referenced in README L108 as living in "the related plan repo." For the wiki to be authoritative, those premises need to land here.
- **chat-id discovery walkthrough** — flagged in `FEEDBACK-seeder.md` Rec 8 as a missing piece.

## Notes

- Wiki repo is created automatically on first page-add via GitHub UI. No setup required.
- Keep wiki canon-shaped: no project-specific traces, no machine paths.
- Recommend home page (`Home.md`) to be a one-screen index pointing at the 7 sections above.
