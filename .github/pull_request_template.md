<!-- Keep it to what changed and why. Delete any section that doesn't apply. -->

## What & why


## Source of truth touched?
<!-- If you edited a generator input, tick what you regenerated AND committed —
     the selftests fail when a generated doc/diagram is stale. -->
- [ ] `engine/workflow.toml` → `python3 engine/workflow.py --write` (docs/WORKFLOW.md) + `python3 engine/bpmn.py --write` (workflow/)
- [ ] `engine/glossary.py` → `--write` (docs/GLOSSARY.md)
- [ ] `engine/events.py` → `--write` (docs/EVENTS.md)
- [ ] N/A — no generated artifact affected

## Checklist
- [ ] Full selftest suite passes locally (`engine/*.py`, `evaluation/harness.py --selftest`)
- [ ] Least-necessary change; matches the surrounding code
- [ ] Docs/comments updated where behaviour changed
