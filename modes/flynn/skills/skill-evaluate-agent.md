# Skill: Evaluate Agent

Audits an existing agent spec against agentic best practices. User specifies which agent to evaluate.

---

## Steps

1. **Read the agent doc** and all its referenced skills.

2. **Check against criteria:**

   | # | Check | What to look for |
   |:--|:------|:-----------------|
   | 1 | Role clarity | Is the role one sentence? Can you tell what this agent does in 5 seconds? |
   | 2 | Negative scope | Does it explicitly list what it must NOT do? Is this section present and specific? |
   | 3 | Scope overlap | Does it overlap with any other agent in the project? Check for shared owned artifacts. |
   | 4 | Permissions & boundaries | Are the agent's allowed actions clearly bounded? Are dangerous/irreversible actions gated? |
   | 5 | Owned artifacts | Are output files clearly listed? Is there exactly one writer per artifact? |
   | 6 | Evaluation criteria | Can you objectively verify the agent did its job? Are criteria checkable, not vague? |
   | 7 | Escalation triggers | Does the agent know when to stop and ask for help? |
   | 8 | Skill quality | Are skills step-by-step procedures with clear inputs, outputs, and exit criteria? |
   | 9 | Context management | Does the agent read only what it needs? Does it reference `principles.md` and `context.md`? |
   | 10 | Guardrails | Are hard constraints explicit? Is there a session-end skill? |

3. **Output findings:**

   ```
   | # | Check | Status | Finding |
   |:--|:------|:-------|:--------|
   ```

   Status: `PASS` / `WARN` / `FAIL`

4. **Provide recommendations** — specific, actionable fixes for any WARN or FAIL items.

5. **Overall assessment** — one sentence: is this agent well-defined enough to operate reliably?
