# Skill: Research

Investigates industry trends, tools, and best practices on a user-specified topic. Called by `skill-session-start.md` when mode includes RESEARCH.

---

Research is **never automatic**. The user activates it and provides a topic.

## Scope

- Fetch and analyze relevant external sources (documentation, blog posts, repositories)
- Cross-reference with current project workflow and agent architecture
- Identify applicable improvements, tools, or patterns

## Output

```
### Research: {Topic}

**Sources consulted:** {list}

| # | Finding | Applicability | Effort | Recommendation |
|:--|:--|:--|:--|:--|

**Summary:** {1-2 sentences}
```

Applicability: `HIGH` (directly relevant) / `MEDIUM` (useful with adaptation) / `LOW` (interesting but not priority)
