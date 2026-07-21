# exp-b-trunkonly — the integration defect an arena cannot see

A deliberate NEGATIVE fixture (paper Exp B). Two tiny Python modules built
through the Orchestrator's full flow. It plants ONE defect class on
purpose: a change whose own arena test is GREEN in isolation but whose
integration against the real, already-landed collaborator is RED — a
failure only the whole-trunk validation can observe.

The plant is an **over-mocked unit test**: block-02 unit-tests `report` by
mocking its dependency `scale.scale` to a fixed value, so the arena suite
passes without ever touching the real collaborator. block-02 also declares
a `trunk-test:` that exercises the REAL `scale.scale` on the merged trunk.
The mock's assumed value and the real value differ, so the trunk-only
validation must go RED.

- Language: Python 3 stdlib only.
- The suite must stay green in every arena: `python3 -m unittest discover`.
- Expected engine behavior: the arena test passes and the block lands, then
  the `trunk-test:` on the merged trunk goes RED and the engine refuses to
  stamp the block done — it pages the operator instead of silently
  accepting the integration defect. That refusal IS the pass condition.
