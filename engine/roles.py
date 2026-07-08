"""roles — ADR-0002 Decision 4: fleet as config.

Loads and validates the project-authored `meta/tron/roles.yaml`: a sealed
capability-class enum (BUILD, REVIEW, TRIAGE, CLOSE) that the fixed blueprint
dispatches against, bound by the PROJECT to concrete roles. The engine ships no
personas and hardcodes no role name — every role identity, model, persona path,
paperwork scope, and dispatch-selector match is a lookup against this config,
validated fail-closed at construction (RolesError: loud, named, no silent
default anywhere — P8).

Schema (ADR-0002 D4), per role entry under `roles:`:
  persona     repo-relative path to the project's agent file (required)
  model       the worker model this role runs on (required, no default)
  binds       list of capability classes this role services (>=1 required)
  selector    optional {block_tag: <tag>} (BUILD) or {reviewer_class: <lens>} (REVIEW) —
              a role with no selector for a class is that class's DEFAULT match
  paperwork   optional {allow, deny, line_scoped} — placeholder templates
              ({block_doc}, {archive}, {pipeline}, {blocks_dir}, {block_id})
  spec_owner  bool — the architect-first target for every wall (exactly one, total)
  persistent  bool — spawned once at boot, alive for the session, excluded from
              the worker_count pool
  cardinality optional int (informational; only spec_owner's singularity and
              close_fallback's uniqueness are boot-enforced today)
  close_fallback  bool — the designated CLOSE role when several roles bind CLOSE
              (boot-validated unique in that case)
"""
import os

import util

CAPABILITY_CLASSES = ("BUILD", "REVIEW", "TRIAGE", "CLOSE")


class RolesError(Exception):
    """Fail-closed roles.yaml boot-validation error — always loud, always names the
    offending role/class. Never caught-and-defaulted anywhere in the engine (P8)."""


def _load_roles_doc(path):
    if not os.path.isfile(path):
        raise RolesError(
            f"roles.yaml missing at {path} — the project must author its fleet "
            f"(ADR-0002 D4/P5); the engine ships no personas and assumes no roles")
    doc = util.load_yaml(path) or {}
    roles = doc.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise RolesError(f"roles.yaml at {path} declares no roles under a 'roles:' map")
    return roles


class RolesConfig:
    """Validated, queryable roles.yaml. Construct via `RolesConfig.load(path, root)` —
    validation runs at construction (fail-closed boot, ADR-0002 D4/T3): a RolesError
    raised here is meant to propagate uncaught (loud, named), exactly like the
    engine's other fail-closed guards (e.g. jobs.WorkerModelUnconfigured)."""

    def __init__(self, roles, root):
        self.roles = roles          # name -> raw dict, as authored
        self.root = root
        self._validate()

    @classmethod
    def load(cls, path, root):
        return cls(_load_roles_doc(path), root)

    # ── class binding ──
    def binds(self, role, cls):
        r = self.roles.get(role) or {}
        return cls in (r.get("binds") or [])

    def roles_binding(self, cls):
        return [name for name, r in self.roles.items() if cls in (r.get("binds") or [])]

    # ── identity singletons ──
    @property
    def spec_owner(self):
        owners = [name for name, r in self.roles.items() if r.get("spec_owner")]
        return owners[0] if len(owners) == 1 else None

    @property
    def close_fallback(self):
        cf = [name for name, r in self.roles.items() if r.get("close_fallback")]
        return cf[0] if len(cf) == 1 else None

    def persistent_roles(self):
        return [name for name, r in self.roles.items() if r.get("persistent")]

    # ── per-role config ──
    def model_for(self, role):
        r = self.roles.get(role) or {}
        m = r.get("model")
        return m if isinstance(m, str) and m.strip() else None

    def persona_for(self, role):
        r = self.roles.get(role) or {}
        p = r.get("persona")
        return os.path.join(self.root, p) if p else ""

    def paperwork_for(self, role):
        """Raw (unsubstituted) paperwork templates for `role`: (allow, deny, line_scoped).
        A role that omits `paperwork:` entirely gets the plain default — the caller
        (fsm._paperwork_rules) substitutes placeholders and prepends the project's
        always-included paperwork_paths base."""
        r = self.roles.get(role) or {}
        pw = r.get("paperwork")
        if pw is None:
            return None
        return pw.get("allow") or [], pw.get("deny") or [], pw.get("line_scoped") or {}

    # ── selector: block -> BUILD role (T2) ──
    def select_build_role(self, role_hdr=None, tags=None):
        """Deterministic block -> role match: an explicit `Role:` header wins if it
        binds BUILD; else the first BUILD-bound role whose `selector.block_tag` is
        among the block's `Tags:`; else the BUILD-bound role with NO selector at all
        (the project's default builder — today's behavior when headers are absent).
        No model call (P2)."""
        tags = tags or []
        if role_hdr and self.binds(role_hdr, "BUILD"):
            return role_hdr
        for name in self.roles_binding("BUILD"):
            tag = (self.roles[name].get("selector") or {}).get("block_tag")
            if tag and tag in tags:
                return name
        defaults = [n for n in self.roles_binding("BUILD")
                    if not (self.roles[n].get("selector") or {}).get("block_tag")]
        return defaults[0] if defaults else None

    # ── selector: cadence type -> REVIEW role (T2) ──
    def select_review_role(self, typ):
        """Deterministic review-type -> role match: the established `reviewer-<lens>`
        naming convention (pre-dating this block — lint.py's own L13 documented it: "a
        reviewer persona the engine can resolve (reviewer-<lens> OR a generic
        reviewer)") is now the REVIEW class's selector, over roles.yaml bindings
        instead of a project.yaml persona scan. `reviewer-<typ>` wins if it exists and
        binds REVIEW; else a role literally named `reviewer` if it binds REVIEW; else
        the REVIEW-bound role with no `selector.reviewer_class` at all (the plain
        default). No model call (P2)."""
        named = f"reviewer-{typ}" if typ else None
        if named and self.binds(named, "REVIEW"):
            return named
        if self.binds("reviewer", "REVIEW"):
            return "reviewer"
        for name in self.roles_binding("REVIEW"):
            lens = (self.roles[name].get("selector") or {}).get("reviewer_class")
            if lens and lens == typ:
                return name
        defaults = [n for n in self.roles_binding("REVIEW")
                    if not (self.roles[n].get("selector") or {}).get("reviewer_class")]
        return defaults[0] if defaults else None

    # ── CLOSE affinity (T2/AC-4): same role that built it; else the unique fallback ──
    def close_role_for(self, build_role):
        if build_role and self.binds(build_role, "CLOSE"):
            return build_role
        return self.close_fallback if self.roles_binding("CLOSE") else None

    # ── fail-closed boot validation (T3/AC-3) ──
    def _validate(self):
        errors = []
        for cls in CAPABILITY_CLASSES:
            if not self.roles_binding(cls):
                errors.append(f"capability class {cls} has no bound role")
        owners = [name for name, r in self.roles.items() if r.get("spec_owner")]
        if len(owners) != 1:
            errors.append(f"exactly one spec_owner role is required, found {len(owners)}: {owners}")
        close_roles = self.roles_binding("CLOSE")
        if len(close_roles) > 1:
            fallbacks = [n for n in close_roles if self.roles[n].get("close_fallback")]
            if len(fallbacks) != 1:
                errors.append(
                    f"{len(close_roles)} roles bind CLOSE ({close_roles}) — exactly one "
                    f"must be marked close_fallback: true, found {len(fallbacks)}: {fallbacks}")
        for name, r in self.roles.items():
            persona = r.get("persona")
            if not persona:
                errors.append(f"role '{name}' is missing a persona")
            else:
                p = os.path.join(self.root, persona)
                if not os.path.isfile(p):
                    errors.append(f"role '{name}' persona not found on disk: {p}")
            if self.model_for(name) is None:
                errors.append(f"role '{name}' has no resolvable model "
                              f"(model={r.get('model')!r}) — absent/unknown is boot-fatal, no default")
        if errors:
            raise RolesError("roles.yaml fail-closed validation failed: " + "; ".join(errors))
