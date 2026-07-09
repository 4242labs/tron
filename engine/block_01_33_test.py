r"""block_01_33_test — Fleet as config: roles.yaml bound to capability classes
(ADR-0002 Decision 4). Standalone runner convention (exit 0 = pass, no tokens, no
network, no real `claude` — every case below stays TRON_DRY).

Covers the block's own acceptance criteria (01-33-fleet-as-config.md):
  AC-1 test:<fleet_from_config> + cmd:<grep engine for role literals = 0>
       The trivial scaffold's fleet (engineer/reviewer-code/architect) runs
       unchanged from roles.yaml alone; RENAMING every role in a custom roles.yaml
       (with no engine edit) still dispatches/pools/closes/paperworks correctly —
       proof nothing in fsm.py/roles.py keys off the literal strings "engineer",
       "reviewer", or "architect" for FLEET DISPATCH. The `cmd:` half is a real
       grep over the engine's dispatch-facing modules — post review-round-1 (F2)
       this now includes lint.py and roles.py too — with a closed, individually
       justified allowlist (visible below, ALLOWED_HITS, one reason string per
       entry) for what legitimately still spells those words: (a) fsm.py's
       `_worker_id` cosmetic ID-prefix table (a display nicety with a graceful
       `role.upper()` fallback for anything not listed — it never gates
       BUILD/REVIEW/TRIAGE/CLOSE dispatch, pool membership, or paperwork); (b) the
       `_open_case`/log "architect" CASE-KIND tag (an internal escalation taxonomy
       value — "this case concerns the persistent TRIAGE/spec_owner worker's own
       job queue" — never compared against `w.get("role")` or any roles.yaml
       value); and (c) lint.py's L13, a DIFFERENT pre-existing config surface
       (project.yaml's optional `agents:` roster) that mirrors the retired naming
       convention for its own backward compat only. roles.py itself now
       contributes ZERO hits — F1 removed the shadowing "reviewer" literal from
       `select_review_role` entirely rather than allowlisting it. Comments/
       docstrings are excluded per the block's own scoping note.
  AC-2 test:<injected_role_builds> — an injected 4th role (designer,
       selector: {block_tag: design}, binds BUILD) builds a design-tagged block
       with ZERO engine edits (this test only adds config + a fixture block file).
  AC-3 test:<boot_fail_closed_matrix> — every named boot-fatal arm, individually.
  AC-4 test:<close_affinity> — CLOSE resolves to the building role when it binds
       CLOSE; else deterministically to the CLOSE fallback (the sole CLOSE-binding
       role when there's only one — the ADR's own worked example, undecorated, no
       flag — else the unique close_fallback:true-flagged role when several bind
       CLOSE — B1, review round 1).
  AC-5 test:<paperwork_config_parity> — per-role roles.yaml `paperwork:` produces
       the same allow/deny/line_scoped verdict shape as the retired hardcoded
       engineer/architect special-cases (and the plain default for any other role).

AC-6 (P2/P5/P8 premise regression) is `manual_by:engineer` — covered in the PR
body's checklist, not here.

Review-fixes-round-1 notes (see the PR body's own "## Review fixes (round 1)"
section for the full per-finding writeup):
B1: close_role_for/close_fallback now treat a SOLE CLOSE-binding role as the
    implicit fallback (flag irrelevant, per the ADR's own worked example);
    several-roles-bind-CLOSE still requires the boot-enforced unique flag. Boot
    validation additionally rejects any BUILD-bound role with no resolvable CLOSE
    path at all — total by construction.
B2: fsm._worker_id's eager `role.upper()` default-arg bug fixed (lazy now); every
    selector-resolution call site (`_build_role_for`, `_close_role`, REVIEW/BUILD
    dispatch, gate-giveup/tick, fleet-refusal canary) raises a named, loud
    roles.RolesError via a shared `_require_role` guard if it ever receives None —
    defense in depth even though B1/B3 make it unreachable through real dispatch.
B3: roles.select_review_role is total by construction — boot validation (given
    the project's real cadence types, passed by Engine) requires either a
    selector-less default REVIEW role or explicit reviewer-<type>/
    selector.reviewer_class coverage of every declared type; at runtime an
    unmatched type resolves deterministically to the default when one exists.
F1: select_review_role's selector TABLE now runs before any name-based fallback;
    the hardcoded `binds("reviewer", "REVIEW") -> "reviewer"` literal is REMOVED
    entirely (it was pure redundancy with the plain-default arm whenever it wasn't
    the shadowing bug).
F2: ENGINE_FILES now includes lint.py + roles.py; ALLOWED_HITS is a closed list of
    (pattern, reason) pairs, one reason string per entry, asserted non-empty.
F3: `_close_affinity_doc` now exercises the UNDECORATED ADR-example shape (single
    CLOSE role, no flag) through the real B1 fix; a several-CLOSE-roles +
    explicit-flag variant is kept alongside it (`_multi_close_roles_doc`).

Run: python3 engine/block_01_33_test.py   (exit 0 = pass).
"""
import os
import sys
import copy
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["TRON_DRY"] = "1"

import util             # noqa: E402
import roles as roles_mod  # noqa: E402
from fsm import Engine  # noqa: E402
from sentry_test import build, started, seed_trivial_roles, TRIVIAL_ROLES  # noqa: E402

_results = []


def ok(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def _block_md_tagged(bid, role_hdr=None, tags=None, status="\U0001F4CB", deps="none"):
    lines = [f"# Block {bid}: test {bid}", "**Phase:** Phase 1: Test", f"**Status:** {status}",
              f"**Depends on:** {deps}", "**Reviewer class:** code", "**Merge approval:** auto",
              "**Deploy:** none"]
    if role_hdr:
        lines.append(f"**Role:** {role_hdr}")
    if tags:
        lines.append(f"**Tags:** {', '.join(tags)}")
    lines += ["", "---", "", "## Body", ""]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# AC-1: the trivial fleet runs from config alone — and a FULLY RENAMED fleet
# (same shape, different role names, zero engine edits) proves nothing in the
# engine keys off the literal strings "engineer"/"reviewer"/"architect".
# ══════════════════════════════════════════════════════════════════════════

def t1_trivial_fleet_dispatches_engineer_reviewer_architect_from_config_alone():
    ctx, repo = build(blocks=[("A-01", "\U0001F4CB", "none")])
    eng = Engine(ctx); started(eng)
    row = eng.st.row("A-01")
    ok("AC-1 the default BUILD role (no Role:/Tags: header) resolves to 'engineer' "
       "purely via roles.yaml's binds — no header, no selector match",
       eng._build_role_for(row) == "engineer")
    eng._dispatch_engineer("A-01")
    w = next(x for x in eng.st.workers if x.get("block") == "A-01")
    ok("AC-1 the dispatched worker's role + persona resolve straight from roles.yaml",
       w["role"] == "engineer" and eng._agent_file("engineer").endswith("meta/agents/engineer.md"))
    eng._dispatch_reviewer("code")
    rev = next(x for x in eng.st.workers if x.get("rtype") == "code")
    ok("AC-1 the reviewer role for cadence type 'code' resolves to 'reviewer-code'",
       rev["role"] == "reviewer-code")
    eng._spawn_architect()
    arch = eng._architect()
    ok("AC-1 the persistent TRIAGE/spec_owner worker resolves to 'architect'",
       arch is not None and arch["role"] == "architect")


def _renamed_roles_doc():
    """Same SHAPE as the trivial scaffold (BUILD+CLOSE / REVIEW / TRIAGE+spec_owner+
    persistent), every role NAME changed, the reviewer deliberately NOT following the
    `reviewer-<lens>` naming convention (selector.reviewer_class forces the table-lookup
    arm, not the naming shortcut) — the strongest available proof against hidden
    literal-name dependence."""
    return {
        "roles": {
            "crafter": {
                "persona": "meta/agents/crafter.md", "model": "test-model",
                "binds": ["BUILD", "CLOSE"],
                "paperwork": {"allow": ["{block_doc}", "{archive}"],
                              "deny": ["{pipeline}", "{blocks_dir}"],
                              "line_scoped": {"{pipeline}": "{block_id}"}},
            },
            "code-checker": {
                "persona": "meta/agents/code-checker.md", "model": "test-model",
                "binds": ["REVIEW"], "selector": {"reviewer_class": "code"},
            },
            "overseer": {
                "persona": "meta/agents/overseer.md", "model": "test-model",
                "binds": ["TRIAGE"], "persistent": True, "spec_owner": True,
                "paperwork": {"allow": ["{pipeline}", "{blocks_dir}"]},
            },
        }
    }


def t1_fully_renamed_fleet_dispatches_identically_with_zero_engine_edits():
    ctx, repo = build(blocks=[("A-01", "\U0001F4CB", "none")])
    seed_trivial_roles(repo, _renamed_roles_doc())     # overwrite: same shape, new names
    eng = Engine(ctx); started(eng)

    eng._dispatch_engineer("A-01")
    w = next(x for x in eng.st.workers if x.get("block") == "A-01")
    ok("AC-1 a renamed BUILD+CLOSE role dispatches under its OWN name (no 'engineer' "
       "fallback anywhere)", w["role"] == "crafter", f"role={w['role']!r}")

    eng._dispatch_reviewer("code")
    rev = next(x for x in eng.st.workers if x.get("rtype") == "code")
    ok("AC-1 the REVIEW role resolves via selector.reviewer_class (the naming-shortcut "
       "deliberately doesn't apply here) -> 'code-checker', never a 'reviewer' literal",
       rev["role"] == "code-checker", f"role={rev['role']!r}")

    eng._spawn_architect()
    arch = eng._architect()
    ok("AC-1 the renamed persistent spec_owner role is found via roles.spec_owner, "
       "never a hardcoded 'architect' comparison", arch is not None and arch["role"] == "overseer")
    ok("AC-1 _spec_owner_persistent reads the renamed role's OWN persistent: flag",
       eng._spec_owner_persistent() is True)

    eng.st.block_roles["A-01"] = "crafter"
    ok("AC-1 CLOSE affinity resolves off the renamed role's OWN binds (crafter binds "
       "CLOSE) — no hardcoded 'engineer' anywhere in the close path",
       eng._close_role("A-01") == "crafter")

    allow, deny, scoped = eng._paperwork_rules("crafter", "A-01")
    ok("AC-1 paperwork rules resolve off the renamed role's OWN roles.yaml config",
       any(p.endswith("A-01.md") for p in allow) and scoped == {
           eng.paths["pipeline_rel"]: "A-01"})


ENGINE_FILES = ["fsm.py", "console.py", "engine.py", "jobs.py", "ctx.py", "state.py",
                "reader.py", "render.py", "trunk.py", "grants.py", "judge.py",
                "eventlog.py", "util.py", "wake.py",
                # F2 (review round 1): the grep gate previously excluded these two —
                # lint.py carried an unaudited hit (L13, below), and roles.py is where
                # F1's fix actually removed the shadowing "reviewer" literal from
                # `select_review_role`. Both now in scope; roles.py contributes zero
                # hits post-fix (nothing to allowlist there any more).
                "lint.py", "roles.py"]

# Every remaining hit of a bare fleet-role literal in the files above, individually
# justified with a visible reason (F2) — (pattern, reason). Anything NOT matching one
# of these substrings is a genuine regression — a NEW hardcoded role slot the grep
# must catch.
ALLOWED_HITS = [
    ('case.get("kind") == "architect"',
     "an internal escalation CASE-KIND tag (fsm.py) — 'this case concerns the "
     "persistent TRIAGE/spec_owner worker's own job queue', never compared against "
     "w.get('role') or any roles.yaml value"),
    ('self.log("architect", f"dispatch {job}")',
     "a log channel name (fsm.py), not a role comparison — cosmetic"),
    ('_open_case(job.get("block"), "architect", arch.get("id")',
     "same CASE-KIND tag as above, at the open-case call site (fsm.py)"),
    ('{"engineer": "ENG", "architect": "ARCH", "reviewer": "REV"}',
     "fsm.py _worker_id's cosmetic ID-prefix table — a display nicety with a "
     "graceful role.upper() fallback (lazy, post-B2) for anything not listed; never "
     "gates BUILD/REVIEW/TRIAGE/CLOSE dispatch, pool membership, or paperwork"),
    ('D4 dissolves the old "engineer"/"reviewer" literal here too.',
     "docstring prose (fsm.py), not code — describes this very block's own history"),
    ('"reviewer" not in roles)',
     "lint.py L13: a DIFFERENT, pre-existing config surface (project.yaml's optional "
     "`agents:` roster, not roles.yaml) — skipped entirely whenever `agents:` is "
     "absent (every current scaffold/project has no such key); mirrors the OLD "
     "reviewer/reviewer-<lens> naming convention for THAT surface's own backward "
     "compat only, and is never consulted by fleet dispatch (roles.select_review_role, "
     "post-F1, has no such literal at all)"),
    # ADR-0003 D-D (block 01-35): the restored bootup model question's RECOMMENDATION
    # tier vocabulary — "architect" (the persistent spec-owner tier) vs. "other"
    # (everyone else) label a built-in FALLBACK SUGGESTION only, shown when roles.yaml
    # itself declares no model for a role. Never a fleet-dispatch lookup: the tier for
    # an arbitrary role name is derived from that role's OWN spec_owner/persistent
    # flags (console._role_label/_recommended_model), never from its literal name —
    # unlike the pre-01-33 hardcoded {architect, other} split this label vocabulary
    # echoes, no role is ever matched or selected by comparing against these strings.
    ('ROLE_MODEL_RECOMMENDED = {"architect": "claude-opus-4-8", "other": "claude-sonnet-4-5"}',
     "console.py: the bootup model recommendation's fallback-tier CONSTANT — a "
     "display suggestion only, never a role-identity comparison (see note above)"),
    ('ROLE_MODEL_LABEL = {"architect": "the persistent architect/spec-owner", "other": "engineers/reviewers"}',
     "console.py: the matching fallback-tier LABEL constant — same reasoning"),
    ('tier = "architect" if (cfg.get("spec_owner") or cfg.get("persistent")) else "other"',
     "console.py (_role_label/_recommended_model): derives the tier from the role's "
     "OWN spec_owner/persistent flags, not its name — appears twice (both helpers), "
     "same reasoning as the constants above"),
]


def cmd_ac1_grep_engine_for_role_literals():
    """AC-1's `cmd:` half, run for real: grep the engine's dispatch-facing modules for
    the fleet role-name literals; every hit must match the closed, justified allowlist
    above (comments/docstrings excluded — a `#`-led line, or this file's own docstring
    text, never counts)."""
    ok("AC-1/F2 the allowlist itself is closed and every entry carries a non-empty "
       "reason string (visible, in-test — F2)",
       all(isinstance(pat, str) and isinstance(reason, str) and reason.strip()
           for pat, reason in ALLOWED_HITS))
    patterns = [pat for pat, _reason in ALLOWED_HITS]
    pattern = r'"engineer"\|"reviewer"\|"architect"'
    hits = []
    for fname in ENGINE_FILES:
        path = os.path.join(HERE, fname)
        if not os.path.exists(path):
            continue
        out = subprocess.run(["grep", "-n", pattern, path], capture_output=True, text=True)
        for line in out.stdout.splitlines():
            lineno, _, content = line.partition(":")   # grep -n <single file>: "lineno:content"
            stripped = content.strip()
            if stripped.startswith("#"):
                continue                       # a plain comment never counts (block scope note)
            hits.append((fname, lineno, content))
    unjustified = [(f, n, c) for f, n, c in hits
                   if not any(pat in c for pat in patterns)]
    ok("AC-1 cmd: grep engine for role literals = 0 (beyond the closed, justified "
       "allowlist — comments excluded; F2: lint.py + roles.py now in scope)",
       not unjustified, f"unjustified={unjustified}")


# ══════════════════════════════════════════════════════════════════════════
# AC-2: an injected 4th role builds a tagged block — zero engine edits (this
# test itself only adds config + a fixture block file, never touches fsm.py/roles.py).
# ══════════════════════════════════════════════════════════════════════════

def t2_injected_designer_role_builds_a_design_tagged_block():
    ctx, repo = build(blocks=[("A-01", "\U0001F4CB", "none")])
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["designer"] = {
        "persona": "meta/agents/designer.md", "model": "test-model",
        "binds": ["BUILD"], "selector": {"block_tag": "design"},
    }
    seed_trivial_roles(repo, doc)
    # Tag A-01 as a design block (the ONLY change to the fixture's own data — no engine edit).
    util.atomic_write(os.path.join(repo, "meta", "blocks", "A-01.md"),
                      _block_md_tagged("A-01", tags=["design"]))
    eng = Engine(ctx); started(eng)
    row = eng.st.row("A-01")
    ok("AC-2 the Tags: header round-trips through reader.parse_block",
       "design" in (row.get("tags") or []), f"row={row}")
    ok("AC-2 the selector resolves the tagged block to the injected role, no engine edit",
       eng._build_role_for(row) == "designer")
    eng._dispatch_engineer("A-01")
    w = next(x for x in eng.st.workers if x.get("block") == "A-01")
    ok("AC-2 the injected role actually dispatches (persona/model/spawn all config-only)",
       w["role"] == "designer" and eng._agent_file("designer").endswith("meta/agents/designer.md")
       and eng._model_for_role("designer") == "test-model")


def t2_untagged_block_still_falls_through_to_the_project_default_builder():
    """The Tags: header is OPTIONAL (nearly every block omits it) — an injected role must
    never steal the default BUILD slot from blocks that don't ask for it."""
    ctx, repo = build(blocks=[("A-02", "\U0001F4CB", "none")])
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["designer"] = {
        "persona": "meta/agents/designer.md", "model": "test-model",
        "binds": ["BUILD"], "selector": {"block_tag": "design"},
    }
    seed_trivial_roles(repo, doc)
    eng = Engine(ctx); started(eng)
    row = eng.st.row("A-02")
    ok("AC-2 an untagged block still resolves to the project's DEFAULT BUILD role "
       "(the one with no selector) -- injection never steals the default slot",
       eng._build_role_for(row) == "engineer")


def t2_explicit_role_header_wins_over_tag_selector():
    ctx, repo = build(blocks=[("A-03", "\U0001F4CB", "none")])
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["designer"] = {
        "persona": "meta/agents/designer.md", "model": "test-model",
        "binds": ["BUILD"], "selector": {"block_tag": "design"},
    }
    seed_trivial_roles(repo, doc)
    # An explicit Role: header, no Tags: at all -> the header wins outright.
    util.atomic_write(os.path.join(repo, "meta", "blocks", "A-03.md"),
                      _block_md_tagged("A-03", role_hdr="designer"))
    eng = Engine(ctx); started(eng)
    row = eng.st.row("A-03")
    ok("AC-2 an explicit Role: header resolves the block to that role directly",
       eng._build_role_for(row) == "designer", f"row={row}")


# ══════════════════════════════════════════════════════════════════════════
# AC-3: fail-closed boot validation — every named arm, individually.
# ══════════════════════════════════════════════════════════════════════════

def _fixture_root():
    ctx, repo = build(blocks=[])
    return repo


def _personas(repo, roles_doc):
    """Materialize every persona file a roles_doc references so ONLY the specific
    violation under test trips validation (never a spurious missing-persona failure)."""
    for name, r in roles_doc.get("roles", {}).items():
        p = r.get("persona")
        if not p:
            continue
        full = os.path.join(repo, p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if not os.path.isfile(full):
            util.atomic_write(full, f"# {name} stub\n")


def _raises(roles_doc, repo):
    try:
        roles_mod.RolesConfig(roles_doc.get("roles", {}), repo)
        return None
    except roles_mod.RolesError as e:
        return str(e)


def t3_unbound_reachable_class_is_boot_fatal():
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    del doc["roles"]["architect"]          # TRIAGE now has zero bound roles
    _personas(repo, doc)
    err = _raises(doc, repo)
    ok("AC-3 a reachable class with zero bound roles is boot-fatal, named",
       err is not None and "TRIAGE" in err, f"err={err}")


def t3_zero_spec_owners_is_boot_fatal():
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["architect"]["spec_owner"] = False
    _personas(repo, doc)
    err = _raises(doc, repo)
    ok("AC-3 zero spec_owner roles is boot-fatal, named",
       err is not None and "spec_owner" in err and "found 0" in err, f"err={err}")


def t3_two_spec_owners_is_boot_fatal():
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["reviewer-code"]["spec_owner"] = True   # now two: architect + reviewer-code
    _personas(repo, doc)
    err = _raises(doc, repo)
    ok("AC-3 two spec_owner roles is boot-fatal, named",
       err is not None and "spec_owner" in err and "found 2" in err, f"err={err}")


def t3_ambiguous_close_fallback_is_boot_fatal():
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    # a second CLOSE-binding role, neither marked close_fallback -> ambiguous.
    doc["roles"]["reviewer-code"]["binds"] = ["REVIEW", "CLOSE"]
    _personas(repo, doc)
    err = _raises(doc, repo)
    ok("AC-3 >1 role binds CLOSE with no unique close_fallback is boot-fatal, named",
       err is not None and "close_fallback" in err, f"err={err}")

    # The positive path: mark exactly one -> boots clean.
    doc2 = copy.deepcopy(doc)
    doc2["roles"]["engineer"]["close_fallback"] = True
    _personas(repo, doc2)
    ok("AC-3 ...but resolves clean once exactly one CLOSE-binding role is marked "
       "close_fallback", _raises(doc2, repo) is None)


def t3_sole_close_role_needs_no_flag_the_flag_is_optional_not_ambiguous():
    """B1 (review round 1): the ADR-0002 D4 worked example itself — engineer binds
    [BUILD, CLOSE], designer binds [BUILD] only, NO close_fallback flag anywhere. A
    single CLOSE-binding role is never ambiguous; the flag is documented irrelevant in
    that case, not required. This boots clean with zero errors (the bug this
    regresses: the OLD close_fallback property required an explicit flag even when
    there was only one candidate, so this exact undecorated shape used to silently
    fail at CLOSE time — see t4_adr_worked_example_closes_end_to_end below)."""
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["designer"] = {
        "persona": "meta/agents/designer.md", "model": "test-model", "binds": ["BUILD"],
        "selector": {"block_tag": "design"},
    }
    _personas(repo, doc)
    err = _raises(doc, repo)
    ok("B1 the undecorated ADR-example shape (sole CLOSE role, no flag) boots with "
       "zero errors", err is None, f"err={err}")
    rc = roles_mod.RolesConfig(doc["roles"], repo)
    ok("B1 ...and close_fallback resolves to the sole CLOSE role directly, flag or no "
       "flag", rc.close_fallback == "engineer")


def t3_build_role_lacking_close_path_and_no_fallback_is_boot_fatal():
    """B1 (review round 1): the close path is total BY CONSTRUCTION — a BUILD-bound
    role with no resolvable CLOSE path (doesn't bind CLOSE itself, and no fallback is
    resolvable) is boot-fatal, named. Constructed here alongside the pre-existing
    ambiguous-multi-CLOSE-role shape (the only way to make `close_fallback` resolve to
    None while CLOSE still has bound roles at all) so the NEW check's own wording is
    directly exercised, not just implied by the ambiguity error."""
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["designer"] = {          # binds BUILD only -- no path of its own to CLOSE
        "persona": "meta/agents/designer.md", "model": "test-model", "binds": ["BUILD"],
        "selector": {"block_tag": "design"},
    }
    doc["roles"]["reviewer-code"]["binds"] = ["REVIEW", "CLOSE"]   # now 2 roles bind CLOSE, neither flagged
    _personas(repo, doc)
    err = _raises(doc, repo)
    ok("AC-3/B1 designer (binds BUILD only) has no resolvable CLOSE path while CLOSE "
       "is ambiguous — boot-fatal, named, with the NEW total-by-construction wording",
       err is not None and "designer" in err and "no resolvable CLOSE path" in err,
       f"err={err}")


# ══════════════════════════════════════════════════════════════════════════
# B3 (review round 1): REVIEW total by construction — boot requires either a
# selector-less default role or explicit per-declared-type coverage; at runtime an
# unmatched type resolves deterministically (never None).
# ══════════════════════════════════════════════════════════════════════════

def t3_review_missing_default_and_incomplete_selector_coverage_is_boot_fatal():
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["reviewer-code"]["selector"] = {"reviewer_class": "code"}  # no longer a default
    _personas(repo, doc)
    err = None
    try:
        roles_mod.RolesConfig(doc["roles"], repo, cadence_types=["code", "docs"])
    except roles_mod.RolesError as e:
        err = str(e)
    ok("AC-3/B3 an uncovered declared cadence type ('docs') with no default REVIEW "
       "role is boot-fatal, named", err is not None and "docs" in err, f"err={err}")
    # The same roles doc boots clean once the project only declares the covered type.
    ok("AC-3/B3 ...but boots clean when cadence_types only contains what's covered",
       _boots_clean(doc, repo, cadence_types=["code"]))
    # And boots clean regardless of coverage when cadence_types isn't passed at all
    # (opt-out — every bespoke RolesConfig(...) construction elsewhere in this suite).
    ok("AC-3/B3 ...and boots clean with no cadence_types argument at all (opt-out)",
       _boots_clean(doc, repo))


def _boots_clean(doc, repo, cadence_types=None):
    try:
        roles_mod.RolesConfig(doc["roles"], repo, cadence_types=cadence_types)
        return True
    except roles_mod.RolesError:
        return False


def t3_review_explicit_selector_coverage_of_every_declared_type_boots_clean():
    """The 'or explicit coverage' branch: NO selector-less default REVIEW role, but
    every declared cadence type has its own selector.reviewer_class — boots clean."""
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["reviewer-code"]["selector"] = {"reviewer_class": "code"}
    doc["roles"]["reviewer-docs"] = {
        "persona": "meta/agents/reviewer-docs.md", "model": "test-model",
        "binds": ["REVIEW"], "selector": {"reviewer_class": "docs"},
    }
    _personas(repo, doc)
    ok("AC-3/B3 explicit selector coverage of every declared cadence type boots clean "
       "with no default REVIEW role required",
       _boots_clean(doc, repo, cadence_types=["code", "docs"]))


def t3_review_unmatched_type_resolves_deterministically_via_default_never_none():
    """B3 runtime half: WITH a selector-less default REVIEW role in play (the trivial
    fixture — reviewer-code has no selector at all), an unmatched/unknown cadence type
    still resolves deterministically to that default — never None."""
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    _personas(repo, doc)
    rc = roles_mod.RolesConfig(doc["roles"], repo)
    ok("AC-3/B3 an unmatched cadence type resolves to the selector-less default "
       "role, never None",
       rc.select_review_role("some-unlisted-type") == "reviewer-code")


# ══════════════════════════════════════════════════════════════════════════
# F1 (review round 1): the selector table beats the bare "reviewer" name shortcut —
# regression for the precedence bug (the shortcut used to run FIRST).
# ══════════════════════════════════════════════════════════════════════════

def t3_selector_table_beats_the_bare_reviewer_name_shortcut():
    repo = _fixture_root()
    doc = {"roles": {
        "reviewer": {"persona": "meta/agents/reviewer.md", "model": "test-model",
                     "binds": ["REVIEW"]},                       # bare name, NO selector
        "specialist": {"persona": "meta/agents/specialist.md", "model": "test-model",
                       "binds": ["REVIEW"], "selector": {"reviewer_class": "design"}},
        "builder": {"persona": "meta/agents/builder.md", "model": "test-model",
                    "binds": ["BUILD", "CLOSE"]},
        "owner": {"persona": "meta/agents/owner.md", "model": "test-model",
                  "binds": ["TRIAGE"], "spec_owner": True},
    }}
    _personas(repo, doc)
    rc = roles_mod.RolesConfig(doc["roles"], repo)
    ok("F1 typ='design' resolves via the SELECTOR TABLE to 'specialist', NOT the "
       "bare 'reviewer' name (the precedence/shadowing bug this regresses)",
       rc.select_review_role("design") == "specialist",
       f"got={rc.select_review_role('design')!r}")
    ok("F1 an unmatched type still falls through to 'reviewer' via the plain-default "
       "arm (no selector at all on it) — the naming SHORTCUT is gone, the ordinary "
       "default rule still covers a bare-named role that happens to qualify for it",
       rc.select_review_role("something-else") == "reviewer")


def t3_missing_persona_file_is_boot_fatal():
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    _personas(repo, doc)
    os.remove(os.path.join(repo, doc["roles"]["engineer"]["persona"]))
    err = _raises(doc, repo)
    ok("AC-3 a persona path that doesn't resolve to a file on disk is boot-fatal, named",
       err is not None and "persona" in err and "engineer" in err, f"err={err}")


def t3_missing_and_unknown_model_are_boot_fatal():
    """ADR-0003 D-D (block 01-35) moved this ONE check out of plain construction
    (`RolesConfig(...)`/`_raises`) into an explicit `validate_models()` call — session
    overrides (a TRON-owned bootup answer, unknown to RolesConfig at construction) can
    now rescue an absent roles.yaml model, so construction alone can no longer be the
    enforcement point (see roles.py's `_validate`/`validate_models` docstrings). Called
    with NO session override (as here), the CONTRACT is unchanged byte-for-byte:
    roles.yaml alone must still supply every role's model, boot-fatal otherwise."""
    repo = _fixture_root()
    for bad_model in (None, "", "   "):
        doc = copy.deepcopy(TRIVIAL_ROLES)
        doc["roles"]["engineer"]["model"] = bad_model
        _personas(repo, doc)
        rc = roles_mod.RolesConfig(doc["roles"], repo)
        err = None
        try:
            rc.validate_models()
        except roles_mod.RolesError as e:
            err = str(e)
        ok(f"AC-3 model={bad_model!r} is boot-fatal, named, no default",
           err is not None and "model" in err and "engineer" in err, f"err={err}")
    # absent entirely (key not even present) is the same failure.
    doc = copy.deepcopy(TRIVIAL_ROLES)
    del doc["roles"]["engineer"]["model"]
    _personas(repo, doc)
    rc = roles_mod.RolesConfig(doc["roles"], repo)
    err = None
    try:
        rc.validate_models()
    except roles_mod.RolesError as e:
        err = str(e)
    ok("AC-3 an entirely absent model key is boot-fatal too (never a KeyError, never "
       "a crash — a named RolesError)", err is not None and "model" in err, f"err={err}")
    # ADR-0003 D-D (01-35): a session override for the SAME role rescues it — the
    # only case where construction alone would have raised, but the layered check
    # (roles.yaml OR session) no longer does.
    doc2 = copy.deepcopy(TRIVIAL_ROLES)
    doc2["roles"]["engineer"]["model"] = ""
    _personas(repo, doc2)
    rc2 = roles_mod.RolesConfig(doc2["roles"], repo)
    rescued = True
    try:
        rc2.validate_models({"engineer": "session-supplied-model"})
    except roles_mod.RolesError:
        rescued = False
    ok("AC-3/D-D a session override for the SAME role rescues an otherwise-boot-fatal "
       "missing roles.yaml model", rescued)


def t3_the_trivial_fixture_itself_boots_clean():
    repo = _fixture_root()
    doc = copy.deepcopy(TRIVIAL_ROLES)
    _personas(repo, doc)
    ok("AC-3 sanity: the unmodified trivial fixture boots with no error at all",
       _raises(doc, repo) is None)


def t3_missing_roles_yaml_file_is_boot_fatal():
    ctx, repo = build(blocks=[])
    os.remove(os.path.join(repo, "meta", "tron", "roles.yaml"))
    raised = False
    try:
        Engine(ctx)
    except roles_mod.RolesError as e:
        raised = "roles.yaml" in str(e)
    ok("AC-3 a missing roles.yaml file entirely refuses Engine construction, named",
       raised)


# ══════════════════════════════════════════════════════════════════════════
# AC-4: CLOSE affinity — building role/worker continues into CLOSE when it binds
# CLOSE; else deterministic fallthrough to the unique close_fallback.
# ══════════════════════════════════════════════════════════════════════════

def _close_affinity_doc():
    """F3 (review round 1): the UNDECORATED ADR-0002 D4 worked example shape — a
    SINGLE role binds CLOSE (engineer, via TRIVIAL_ROLES' own [BUILD, CLOSE]), no
    close_fallback flag anywhere at all. This must pass through the REAL B1 fix (the
    sole CLOSE-binding role is the implicit fallback) instead of the test hand-
    patching the flag onto the fixture to dodge the bug it's meant to catch."""
    doc = copy.deepcopy(TRIVIAL_ROLES)
    # "designer" binds BUILD only (no CLOSE) -> must fall through at close time.
    doc["roles"]["designer"] = {
        "persona": "meta/agents/designer.md", "model": "test-model", "binds": ["BUILD"],
        "selector": {"block_tag": "design"},
    }
    return doc


def _multi_close_roles_doc():
    """F3's companion variant: SEVERAL roles bind CLOSE (not the ADR's single-role
    worked example) — here close_fallback genuinely matters and stays boot-enforced
    unique. Kept alongside the undecorated single-CLOSE-role case above so both shapes
    stay covered after F3's fix."""
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["designer"] = {
        "persona": "meta/agents/designer.md", "model": "test-model", "binds": ["BUILD"],
        "selector": {"block_tag": "design"},
    }
    doc["roles"]["reviewer-code"]["binds"] = ["REVIEW", "CLOSE"]   # now 2 roles bind CLOSE
    doc["roles"]["engineer"]["close_fallback"] = True              # explicit, required now
    return doc


def t4_build_role_that_binds_close_continues_unchanged():
    ctx, repo = build(blocks=[("A-01", "\U0001F4CB", "none")])
    seed_trivial_roles(repo, _close_affinity_doc())
    eng = Engine(ctx); started(eng)
    eng.st.block_roles["A-01"] = "engineer"
    ok("AC-4 a role that binds CLOSE continues into CLOSE unchanged (no fallthrough)",
       eng._close_role("A-01") == "engineer")


def t4_build_role_lacking_close_falls_through_to_the_designated_fallback():
    ctx, repo = build(blocks=[("A-02", "\U0001F4CB", "none")])
    seed_trivial_roles(repo, _close_affinity_doc())
    eng = Engine(ctx); started(eng)
    eng.st.block_roles["A-02"] = "designer"    # designer binds BUILD only
    ok("AC-4 a BUILD role that does NOT bind CLOSE falls through to the unique "
       "close_fallback role, deterministically", eng._close_role("A-02") == "engineer")


def t4_affinity_survives_the_building_worker_dying():
    """block_roles is durable (recorded at dispatch) — CLOSE affinity resolves
    identically whether or not the worker that built it is still alive."""
    ctx, repo = build(blocks=[("A-03", "\U0001F4CB", "none")])
    seed_trivial_roles(repo, _close_affinity_doc())
    eng = Engine(ctx); started(eng)
    eng._dispatch_engineer("A-03")
    ok("setup: engineer dispatched and recorded", eng.st.block_roles.get("A-03") == "engineer")
    eng.st.workers[:] = [w for w in eng.st.workers if w.get("block") != "A-03"]  # worker died
    ok("AC-4 CLOSE affinity resolves off the DURABLE record even with no live worker left",
       eng._close_role("A-03") == "engineer")


def t4_roles_config_close_role_for_is_deterministic_and_total():
    repo = _fixture_root()
    doc = _close_affinity_doc()
    _personas(repo, doc)
    rc = roles_mod.RolesConfig(doc["roles"], repo)
    ok("AC-4 close_role_for(<role that binds CLOSE>) returns that role directly",
       rc.close_role_for("engineer") == "engineer")
    ok("AC-4 close_role_for(<role that doesn't bind CLOSE>) returns the unique fallback",
       rc.close_role_for("designer") == "engineer")
    ok("AC-4 close_role_for(None) (no recorded builder, e.g. a workerless gate) still "
       "resolves totally to the fallback whenever CLOSE has any bound role at all",
       rc.close_role_for(None) == "engineer")


def t4_several_close_roles_resolve_via_the_explicit_flag():
    """F3's companion variant: with SEVERAL CLOSE-binding roles in play, resolution
    still goes through the explicit close_fallback flag (not the single-role-implicit
    rule, which only applies when there's exactly one)."""
    repo = _fixture_root()
    doc = _multi_close_roles_doc()
    _personas(repo, doc)
    rc = roles_mod.RolesConfig(doc["roles"], repo)
    ok("AC-4/F3 several CLOSE-binding roles resolve the fallback via the explicit "
       "close_fallback: true flag", rc.close_role_for("designer") == "engineer")
    ok("AC-4/F3 a role that itself binds CLOSE (reviewer-code here) still continues "
       "unchanged, even with several CLOSE roles in play",
       rc.close_role_for("reviewer-code") == "reviewer-code")


def t4_adr_worked_example_closes_end_to_end_for_the_designer_built_block():
    """B1 (review round 1), end to end: the ADR-0002 D4 worked example, driven through
    REAL dispatch + CLOSE-affinity resolution + worker-id assignment (not just a bare
    close_role_for() call) for a block actually BUILT by the non-CLOSE-binding role
    (designer). This is the exact scenario B1 was filed against: the OLD
    close_fallback property returned None here (a single CLOSE role, no flag —
    treated as "ambiguous" instead of "obviously that one"), which would have crashed
    _worker_id downstream (B2) the moment CLOSE was reached."""
    ctx, repo = build(blocks=[("A-01", "\U0001F4CB", "none")])
    seed_trivial_roles(repo, _close_affinity_doc())
    util.atomic_write(os.path.join(repo, "meta", "blocks", "A-01.md"),
                      _block_md_tagged("A-01", tags=["design"]))
    eng = Engine(ctx); started(eng)
    row = eng.st.row("A-01")
    ok("B1 the design-tagged block resolves BUILD to designer (binds BUILD only, no "
       "CLOSE)", eng._build_role_for(row) == "designer")
    eng._dispatch_engineer("A-01")     # dispatch is role-agnostic; resolves via _build_role_for
    w = next(x for x in eng.st.workers if x.get("block") == "A-01")
    ok("B1 designer actually dispatched to build it, durably recorded",
       w["role"] == "designer" and eng.st.block_roles.get("A-01") == "designer")
    ok("B1 CLOSE affinity for the designer-built block resolves to engineer — the "
       "SOLE CLOSE-binding role, with NO close_fallback flag set anywhere in this "
       "undecorated ADR-example roles.yaml", eng._close_role("A-01") == "engineer")
    wid = eng._worker_id(eng._close_role("A-01"), "A-01")
    ok("B1 CLOSE's worker id resolves cleanly through the real fix end to end — no "
       "AttributeError, no None ever reaching worker-id assignment",
       wid == "ENG-A-01", f"wid={wid!r}")


# ══════════════════════════════════════════════════════════════════════════
# B2 (review round 1): defense in depth — a None role must never reach _worker_id
# (or the fsm.py wrapper methods around the selector-resolution functions) without a
# named, loud RolesError; never a bare AttributeError.
# ══════════════════════════════════════════════════════════════════════════

def t2_worker_id_raises_named_rolerror_on_none_role_never_attributeerror():
    """The original bug: `{...}.get(role, role.upper())` evaluates `role.upper()`
    EAGERLY as dict.get's default argument, unconditionally — so role=None crashed
    with a bare AttributeError mid-CLOSE. Fixed AND defended: _worker_id now raises a
    named RolesError immediately if ever handed None (unreachable via real dispatch
    post B1/B3, but must fail loud, not weird, if that invariant is ever violated)."""
    ctx, repo = build(blocks=[("A-01", "\U0001F4CB", "none")])
    eng = Engine(ctx); started(eng)
    try:
        eng._worker_id(None, "A-01")
        ok("B2 _worker_id(None, ...) raises", False, "did not raise at all")
    except AttributeError as e:
        ok("B2 _worker_id(None, ...) raises RolesError, never AttributeError",
           False, f"AttributeError leaked: {e}")
    except roles_mod.RolesError as e:
        ok("B2 _worker_id(None, ...) raises a named, loud RolesError",
           "role" in str(e).lower(), f"err={e}")


def t2_close_role_and_build_role_for_call_sites_never_hand_none_downstream():
    """B2 defense in depth: even if roles.RolesConfig.close_role_for/select_build_role
    somehow returned None (contrived here directly, bypassing boot validation — proof
    the fsm.py WRAPPER is the guard, not just a luckily-valid config), the call sites
    (_close_role/_build_role_for) raise a named RolesError rather than propagating
    None to a caller that would otherwise crash bare."""
    ctx, repo = build(blocks=[("A-01", "\U0001F4CB", "none")])
    eng = Engine(ctx); started(eng)
    eng.st.block_roles["A-01"] = "engineer"
    orig_close = eng.roles.close_role_for
    eng.roles.close_role_for = lambda build_role: None
    try:
        eng._close_role("A-01")
        ok("B2 _close_role raises when close_role_for returns None", False, "did not raise")
    except roles_mod.RolesError as e:
        ok("B2 _close_role raises a named RolesError when close_role_for returns None",
           True, f"err={e}")
    finally:
        eng.roles.close_role_for = orig_close

    orig_build = eng.roles.select_build_role
    eng.roles.select_build_role = lambda *a, **k: None
    try:
        eng._build_role_for(eng.st.row("A-01"))
        ok("B2 _build_role_for raises when select_build_role returns None", False, "did not raise")
    except roles_mod.RolesError as e:
        ok("B2 _build_role_for raises a named RolesError when select_build_role "
           "returns None", True, f"err={e}")
    finally:
        eng.roles.select_build_role = orig_build


# ══════════════════════════════════════════════════════════════════════════
# AC-5: per-role paperwork: config feeds verify_docs with verdict parity against
# the retired hardcoded engineer/architect special-cases.
# ══════════════════════════════════════════════════════════════════════════

def _old_hardcoded_paperwork_rules(eng, role, block=None):
    """The EXACT pre-01-33 formula (fsm.py, before ADR-0002 D4), reproduced here as the
    parity oracle — never re-imported from anywhere, so a future edit to the new path
    can't accidentally make both sides drift together."""
    base = list(eng.paths.get("paperwork") or [])
    pipe = eng.paths.get("pipeline_rel") or "meta/pipeline.md"
    blocks = eng.paths.get("blocks_rel") or "meta/blocks/"
    if role == "architect":
        return base + [blocks, pipe], None, None
    deny = [blocks, pipe]
    if role == "engineer" and block:
        rel = eng._block_relpath(block)
        archive_rel = os.path.relpath(
            os.path.join(eng.paths["archive"], os.path.basename(rel)), eng.paths["root"])
        return base + [rel, archive_rel], deny, {pipe: str(block)}
    return base, deny, None


def t5_engineer_paperwork_matches_the_retired_hardcoded_rule():
    ctx, repo = build(blocks=[("A-01", "\U0001F4CB", "none")])
    eng = Engine(ctx); started(eng)
    new_allow, new_deny, new_scoped = eng._paperwork_rules("engineer", "A-01")
    old_allow, old_deny, old_scoped = _old_hardcoded_paperwork_rules(eng, "engineer", "A-01")
    ok("AC-5 engineer ALLOW set matches the retired hardcoded rule (order-independent)",
       set(new_allow) == set(old_allow), f"new={new_allow} old={old_allow}")
    ok("AC-5 engineer DENY set matches the retired hardcoded rule",
       set(new_deny or []) == set(old_deny or []), f"new={new_deny} old={old_deny}")
    ok("AC-5 engineer LINE-SCOPED map matches the retired hardcoded rule exactly",
       new_scoped == old_scoped, f"new={new_scoped} old={old_scoped}")


def t5_architect_paperwork_matches_the_retired_hardcoded_rule():
    ctx, repo = build(blocks=[("A-01", "\U0001F4CB", "none")])
    eng = Engine(ctx); started(eng)
    new_allow, new_deny, new_scoped = eng._paperwork_rules("architect")
    old_allow, old_deny, old_scoped = _old_hardcoded_paperwork_rules(eng, "architect")
    ok("AC-5 architect ALLOW set matches the retired hardcoded rule (the explicit "
       "union — pipeline + blocks_dir + the paperwork base)",
       set(new_allow) == set(old_allow), f"new={new_allow} old={old_allow}")
    ok("AC-5 architect has NO deny/line_scoped, matching the retired hardcoded rule",
       new_deny == old_deny and new_scoped == old_scoped,
       f"new deny={new_deny} scoped={new_scoped}")


def t5_a_role_with_no_paperwork_config_gets_the_plain_default():
    """Matches the retired rule's fall-through arm (any role that was neither engineer
    nor architect got `base, deny, None`)."""
    ctx, repo = build(blocks=[("A-01", "\U0001F4CB", "none")])
    doc = copy.deepcopy(TRIVIAL_ROLES)
    doc["roles"]["plain-builder"] = {
        "persona": "meta/agents/plain-builder.md", "model": "test-model", "binds": ["BUILD"],
    }
    seed_trivial_roles(repo, doc)
    eng = Engine(ctx); started(eng)
    allow, deny, scoped = eng._paperwork_rules("plain-builder", "A-01")
    old_allow, old_deny, old_scoped = _old_hardcoded_paperwork_rules(eng, "plain-builder", "A-01")
    ok("AC-5 a role with no paperwork: config gets the plain default, matching the "
       "retired rule's fall-through arm exactly",
       set(allow) == set(old_allow) and set(deny or []) == set(old_deny or [])
       and scoped == old_scoped, f"allow={allow} deny={deny} scoped={scoped}")


def t5_paperwork_placeholders_drop_block_scoped_entries_with_no_block_in_play():
    ctx, repo = build(blocks=[])
    eng = Engine(ctx); started(eng)
    allow, deny, scoped = eng._paperwork_rules("engineer", block=None)
    ok("AC-5 a block-scoped paperwork entry ({block_doc}/{archive}) with NO block in "
       "play is DROPPED, never emitted as a bogus/unresolved literal path",
       not any("{" in p for p in allow), f"allow={allow}")
    ok("AC-5 ...and the line_scoped map is empty/None too (never a half-substituted key)",
       not scoped, f"scoped={scoped}")


def main():
    fns = sorted(k for k in globals() if k.startswith(("t1_", "t2_", "t3_", "t4_", "t5_", "cmd_")))
    for fn in fns:
        globals()[fn]()
    bad = [(n, d) for n, c, d in _results if not c]
    for n, c, d in _results:
        print(("PASS" if c else "FAIL"), n, (f" [{d}]" if d and not c else ""))
    print(f"{len(_results) - len(bad)}/{len(_results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
