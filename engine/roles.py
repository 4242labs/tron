"""roles — ADR-0002 Decision 4: fleet as config.

Loads and validates the project-authored `meta/tron/roles.yaml`: a sealed
capability-class enum (BUILD, REVIEW, TRIAGE, CLOSE) that the fixed blueprint
dispatches against, bound by the PROJECT to concrete roles. The engine ships no
personas and hardcodes no role name — every role identity, model, persona path,
paperwork scope, and dispatch-selector match is a lookup against this config,
validated fail-closed at construction (RolesError: loud, named, no silent
default anywhere — P8).

Schema (ADR-0002 D4, amended by ADR-0003 D-D), per role entry under `roles:`:
  persona     repo-relative path to the project's agent file (required)
  model       the worker model this role runs on. No baked default — but ADR-0003 D-D
              restores a bootup model question (console._ask_role_models) whose SESSION
              answer (never written here — a TRON-owned MANIFEST knob under
              meta/agents/tron/) is layered on top by fsm._model_for_role: session
              answer wins for the session; else this field; boot-fatal (validate_models,
              called once the session answer is known) only if NEITHER resolves.
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
  close_fallback  bool — the designated CLOSE role when SEVERAL roles bind CLOSE
              (boot-validated unique in that case). Irrelevant/optional when only ONE
              role binds CLOSE at all — that sole role IS the implicit fallback, flag
              or no flag (the ADR's own worked example: engineer binds [BUILD, CLOSE],
              designer binds [BUILD] only, no close_fallback flag anywhere — a
              design-tagged block's CLOSE still resolves to engineer). Boot validation
              additionally rejects any roles.yaml where a BUILD-bound role has no
              resolvable CLOSE path at all (doesn't bind CLOSE itself and no fallback
              is resolvable) — the close path is total by construction, never a None
              reaching dispatch.
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

    def __init__(self, roles, root, cadence_types=None):
        self.roles = roles          # name -> raw dict, as authored
        self.root = root
        # B3 (review round 1): the closed set of cadence lenses the PROJECT actually
        # declares (project.yaml's `cadence:` map, passed in by the caller — RolesConfig
        # itself owns no cadence config). Used only to make REVIEW's selector total by
        # construction at boot when there's no selector-less default role; None/omitted
        # (every direct RolesConfig(...) test construction) skips that extra coverage
        # check, matching prior behavior.
        self.cadence_types = list(cadence_types) if cadence_types else []
        self._validate()

    @classmethod
    def load(cls, path, root, cadence_types=None):
        return cls(_load_roles_doc(path), root, cadence_types=cadence_types)

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
        """The role CLOSE falls through to when the builder doesn't bind CLOSE itself
        (B1, review round 1). When exactly ONE role binds CLOSE, that role IS the
        implicit fallback — the `close_fallback` flag is documented irrelevant/optional
        in that case (the ADR's own worked example never sets it). Only when SEVERAL
        roles bind CLOSE does the flag matter: exactly one of them must be marked
        `close_fallback: true` (boot-enforced — `_validate`), and that one is returned.
        None if CLOSE has no bound role, or several bind it with no unique flag."""
        close_roles = self.roles_binding("CLOSE")
        if len(close_roles) == 1:
            return close_roles[0]
        flagged = [name for name in close_roles if self.roles[name].get("close_fallback")]
        return flagged[0] if len(flagged) == 1 else None

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
        NAMING CONVENTION (pre-dating this block — lint.py's own L13 documented it: "a
        reviewer persona the engine can resolve (reviewer-<lens> OR a generic
        reviewer)") is now the REVIEW class's selector, over roles.yaml bindings
        instead of a project.yaml persona scan. `reviewer-<typ>` wins if it exists and
        binds REVIEW; ELSE the selector table (`selector.reviewer_class == typ`) over
        every REVIEW-bound role; else the REVIEW-bound role with no
        `selector.reviewer_class` at all (the plain default). No model call (P2).

        F1 (review round 1): the selector TABLE runs before any name-based fallback —
        a bare role literally named `reviewer` must never shadow a selector match for a
        DIFFERENT type just because it happens to exist. There is in fact no hardcoded
        bare-name-literal branch left here at all: a role named `reviewer` with no
        `selector.reviewer_class` already resolves via the plain-default arm below like
        any other selector-less REVIEW role — the naming SHORTCUT was pure redundancy
        with that arm (and, when it wasn't redundant, was exactly the shadowing bug)."""
        named = f"reviewer-{typ}" if typ else None
        if named and self.binds(named, "REVIEW"):
            return named
        for name in self.roles_binding("REVIEW"):
            lens = (self.roles[name].get("selector") or {}).get("reviewer_class")
            if lens and lens == typ:
                return name
        defaults = [n for n in self.roles_binding("REVIEW")
                    if not (self.roles[n].get("selector") or {}).get("reviewer_class")]
        return defaults[0] if defaults else None

    # ── CLOSE affinity (T2/AC-4): same role that built it; else the fallback ──
    def close_role_for(self, build_role):
        """B1 (review round 1): total by construction whenever CLOSE has any bound role
        at all — a single CLOSE-binding role is always resolvable (the implicit
        fallback), several require the boot-enforced unique flag. Boot validation
        additionally requires every BUILD-bound role to have a resolvable path here
        (`_validate`), so a live roles.yaml never hands this method a `build_role`
        for which it returns None."""
        if build_role and self.binds(build_role, "CLOSE"):
            return build_role
        return self.close_fallback

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
        # B1 (review round 1): the close path must be TOTAL by construction — every
        # BUILD-bound role must resolve somewhere at CLOSE time, either because it binds
        # CLOSE itself or because a fallback is resolvable. `self.close_fallback` folds
        # in the single-role-implicit / several-roles-explicit-flag rule validated above.
        fallback = self.close_fallback
        for name in self.roles_binding("BUILD"):
            if not self.binds(name, "CLOSE") and fallback is None:
                errors.append(
                    f"role '{name}' binds BUILD but has no resolvable CLOSE path — it "
                    f"doesn't bind CLOSE itself and no close_fallback role is resolvable "
                    f"(bind CLOSE on '{name}', or mark exactly one CLOSE-binding role "
                    f"close_fallback: true)")
        # B3 (review round 1): REVIEW must be total by construction too — either a
        # selector-less default REVIEW role exists (catches any type the naming
        # convention/selector table misses), or every cadence type this project actually
        # declares (cadence_types, supplied by the caller — Engine passes its real
        # cadence map) has EXPLICIT coverage via `reviewer-<type>` naming or
        # `selector.reviewer_class`. Skipped when cadence_types is empty (opt-out for
        # direct RolesConfig(...) construction that doesn't pass it, matching prior
        # behavior for this suite's many bespoke-fixture tests).
        review_roles = self.roles_binding("REVIEW")
        review_defaults = [n for n in review_roles
                            if not (self.roles[n].get("selector") or {}).get("reviewer_class")]
        if review_roles and not review_defaults and self.cadence_types:
            covered = {(self.roles[n].get("selector") or {}).get("reviewer_class")
                       for n in review_roles}
            covered |= {n[len("reviewer-"):] for n in review_roles if n.startswith("reviewer-")}
            missing = sorted(t for t in self.cadence_types if t not in covered)
            if missing:
                errors.append(
                    f"REVIEW has no selector-less default role and cadence type(s) "
                    f"{missing} have no reviewer-<type> naming or selector.reviewer_class "
                    f"coverage — would resolve to None at review-dispatch time")
        for name, r in self.roles.items():
            persona = r.get("persona")
            if not persona:
                errors.append(f"role '{name}' is missing a persona")
            else:
                p = os.path.join(self.root, persona)
                if not os.path.isfile(p):
                    errors.append(f"role '{name}' persona not found on disk: {p}")
        # ADR-0003 D-D (T2/BL-1): the "every role has a resolvable model" check used to
        # live HERE, at plain construction — but construction happens before the
        # restored bootup model question is ever asked (Console.bootup constructs
        # Engine/RolesConfig FIRST, asks the question SECOND), so enforcing it
        # unconditionally at this point would refuse to boot before the operator ever
        # got a chance to supply the missing value via a session answer. That check now
        # lives in `validate_models()` below, called explicitly once the TRON-owned
        # session override (if any) is known (fsm.Engine.start) — never here.
        if errors:
            raise RolesError("roles.yaml fail-closed validation failed: " + "; ".join(errors))

    def validate_models(self, session_models=None):
        """ADR-0003 D-D (amends ADR-0002 D4; T2/BL-1): the model-resolvable fail-closed
        check, run EXPLICITLY once the TRON-owned session override (if any) is known —
        never at plain construction (see `_validate`'s note). `session_models` is the
        bootup model answer ({role: model}, from the session's own MANIFEST live_config
        under meta/agents/tron/ — never roles.yaml) layered by fsm._model_for_role: a
        role resolves here if EITHER the session supplies one OR roles.yaml's own
        `model:` does; boot-fatal (RolesError, loud, named) only if NEITHER does, for
        ANY declared role (D4's fail-closed preserved, never a silent default). Called
        with session_models=None/omitted, this matches the pre-D-D behavior exactly:
        roles.yaml alone must supply every role's model."""
        session_models = session_models or {}
        errors = []
        for name, r in self.roles.items():
            sess = session_models.get(name)
            sess = sess.strip() if isinstance(sess, str) else None
            if sess or self.model_for(name):
                continue
            errors.append(f"role '{name}' has no resolvable model "
                          f"(model={r.get('model')!r}, no session override either) — "
                          f"absent/unknown is boot-fatal, no default")
        if errors:
            raise RolesError("roles.yaml fail-closed validation failed: " + "; ".join(errors))
