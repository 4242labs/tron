# Skill: Create Agent

Designs and bootstraps a new agent from scratch. User provides the agent's purpose; TRON-FLYNN handles the spec.

---

## Steps

1. **Understand the need.** Ask the user:
   - What does this agent do? (one sentence)
   - Which project(s) will it serve? (42hq-only, a specific project, or cross-project template?)
   - What tools/access does it need?
   - What must it never do?
   - Authority model — full autonomy, triage-first, or something in between?

2. **Research gate (MANDATORY for net-new agents).** Before drafting any spec, consult authoritative, battle-tested sources covering the agent's domain.
   - **Acceptable sources:** O'Reilly / Manning / Addison-Wesley books from recognized authors; official framework docs (NIST, ITIL, DORA, FinOps Foundation, AWS Well-Architected, Google Cloud Architecture Framework); engineering blogs from top-tier orgs (Stripe, Shopify, GitHub, Cloudflare, Netflix, Airbnb, Datadog, Honeycomb, PagerDuty, Atlassian); standards bodies (Linux Foundation, IAPP, OWASP, W3C); academic/industrial research from DeepMind, Anthropic, OpenAI, MIT CSAIL, Stanford; Anthropic's own agent documentation.
   - **Reject:** GitHub repos <5k stars unless from a top-tier engineering org; hobby blogs; Medium posts without institutional backing; AI-agent frameworks <6 months old not shipped in production at a known company.
   - Record the source list in the session log; the agent spec should cite the principles that shaped it.
   - **Enhancements** to existing agents may skip this gate unless the enhancement introduces a new operating domain.

3. **Choose shape.** Two canonical shapes for the agent home:
   - **Direct 42Agents agent** — `42hq/{agent}/` with skills in `skills/`. Use when the agent's procedures are uniform across projects.
   - **Base template + instantiation guide** — `42hq/{agent}/{agent}.template.md` + `templates/` + `instantiation-guide.md`. Use when the agent must be tailored per project (tool wiring, authority grants, project-specific inventory). See `42hq/coo/` as the canonical example.
   - If a shared knowledge base is configured → also read applicable design theory in `{shared_knowledge_path}/reference/`.

4. **Draft the agent spec** using this structure:

   ```markdown
   # Agent: {Name}

   {One-line description.}

   ---

   ## Prerequisites
   {Context files to read before any work.}

   ## Role
   {What the agent does — bullet list.}

   **{Name} does NOT:**
   {Negative scope — what it must never do. This section is mandatory and more important than the role section.}

   ## Owned Artifacts
   {Files this agent is the sole writer of. Exactly one writer per artifact — no overlap with other agents.}

   ## Skills
   {List of skill files, one per workflow.}

   ## Session End
   {Reference to session-end skill. Every agent must have one.}

   ## Evaluation Criteria
   {Checkable assertions — not "do a good job" but specific, verifiable outcomes.}

   ## Escalation Triggers
   {Conditions under which the agent must stop and hand off to user or another agent.}
   ```

5. **Verify the draft against design principles:**
   - [ ] Negative scope is present and specific
   - [ ] No owned-artifact overlap with existing agents in the same project
   - [ ] No naming conflict with existing agents
   - [ ] Evaluation criteria are objectively checkable
   - [ ] Escalation triggers are defined
   - [ ] Session-end skill is referenced
   - [ ] Prerequisites include project's `principles.md` and `context.md` (if applicable)
   - [ ] Research sources are cited where they shaped the design (principles, authority model, state machine, etc.)

6. **Create the first skill.** Write the agent's most common workflow as a step-by-step skill file with clear inputs, outputs, and exit criteria.

7. **Review with user.** Present the draft spec and first skill. Iterate until approved.

8. **Write the files in 42Agents ONLY.** Cross-project agents always land in `42hq/{agent}/` first. Project-specific agents still land in their owning project as directed.
   - **Do NOT wire the agent into any target project as part of this step.** No project-local context files, no CLAUDE.md row edits, no agent registry entries — even if the user mentioned a "first project" during step 1.
   - The agent is built in 42Agents so it can be reviewed in isolation.

9. **Propose project installations. Wait for explicit user direction.** After the agent is reviewed:
   - Present the list of projects where this agent could reasonably install (based on step 1 + project context)
   - For each, describe what the install would touch: `{meta}/agents/{agent}-local.md`, CLAUDE.md rows, registry entries, local-context bootstrap
   - **Do not install.** Only after the user explicitly directs "install on project X" does installation proceed — and then on its own branch + PR per project Git rules.

10. **On user approval, wire into the target project.** On a dedicated branch in the target project's meta repo:
    - Author the project-local context from the agent's template (if using the base-template shape) or from the agent spec's instructions (if direct)
    - Add the agent to the project's CLAUDE.md agent table and any other registries
    - For base-template agents, follow the agent's `instantiation-guide.md`
    - Commit with a lowercase subject; open a PR; wait for user validation before merge

11. **Recommend a test run.** Suggest a real task to validate the agent before finalizing.

---

## Constraints

- **Never install an agent into a project without explicit user direction.** Building the agent in 42Agents and wiring it into a project are two separate steps, each with its own user approval.
- **Never skip the research gate for a net-new agent.** A draft without authoritative grounding gets walked back.
- **Never edit base templates in place for a specific project.** Instantiation always produces a copy; the base stays canonical.
- **Never bypass project Git rules** (branch + PR) even for session-log or registry edits in the target project.
