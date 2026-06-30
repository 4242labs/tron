"""prompts — the PMT layer: resolve a PMT id to its filled prompt body (M-04, R-PMT).

Every LLM-facing worker prompt lives as a self-contained `PMT-*` file in `prompts/`,
indexed by `prompts/registry.yaml`. Callers pass an id (`PMT-ASSIGN`), never a path —
the registry owns the id->file map. The body is read FRESH on every call (imported at
tick, never cached) so an edited prompt takes effect on the next use, and slots are filled
with str.format. The prompt copy itself is the operator's to author (R-PMT seam 2); this
module is only the mechanism: resolve, read, fill, fail loud.
"""
import os

import util


class UnknownPrompt(KeyError):
    pass


class Prompts:
    def __init__(self, ctx):
        self.ctx = ctx

    def _registry(self):
        # Read fresh: the registry travels with the canon and may be edited between ticks.
        return (util.load_yaml(self.ctx.prompts_registry) or {}).get("prompts", {})

    def ids(self):
        return set(self._registry().keys())

    def slots(self, pmt_id):
        spec = self._registry().get(pmt_id)
        if spec is None:
            raise UnknownPrompt(f"prompts: no PMT '{pmt_id}' in registry")
        return list(spec.get("slots", []) or [])

    def load(self, pmt_id, slots=None):
        """Resolve id -> file via the registry, read it fresh, fill slots. Raises
        UnknownPrompt (bad id / missing file) or KeyError (missing slot)."""
        slots = slots or {}
        spec = self._registry().get(pmt_id)
        if spec is None:
            raise UnknownPrompt(f"prompts: no PMT '{pmt_id}' in registry")
        path = os.path.join(self.ctx.prompts_dir, spec["file"])
        if not os.path.exists(path):
            raise UnknownPrompt(f"prompts: PMT '{pmt_id}' file missing: {spec['file']}")
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        try:
            return body.format(**slots)
        except KeyError as e:
            raise KeyError(f"prompts: PMT '{pmt_id}' missing slot {e}")
