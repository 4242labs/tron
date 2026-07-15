"""core.bootup — the operator's interactive bootup front to `core.engine.
Engine` (block 01-38 T23, consolidates 01-30 + 01-35 + 01-33's regression;
ADR-0003 D-D).

The new `core/*` engine had NO bootup/console surface at all before this
task — the operator journey lived only in the retiring `engine/console.py`
(read in full for T23's own frozen shape; see that module's docstring +
ADR-0003 D-D for the corrective history). This module restores it against
`core.engine.Engine` instead of the legacy `fsm.Engine`.

THE FROZEN SEQUENCE (byte-for-byte — no question/option/recommendation may
change without explicit operator sign-off, [[journey-frozen]]; this module
RESTORES the journey, it does not redesign it):

  1. scope            [1] all / [2] a phase / [3] a range of blocks
  2. worker_count      "worker_count (build + review workers; the
                        persistent spec-owner role is extra)? "
  3. ask-before-merging "Inform you before each merge to trunk? [y/N] "
  4. model, PER ROLE    "Model for {role label} [{recommended default}]? "
                        — recommends the role's OWN declared roles.yaml
                        model when present, else a per-tier default
                        (architect/spec-owner = a strong tier, every other
                        role = a fast tier) — 01-30 parity, restored per
                        ADR-0003 D-D after 01-33 stripped it.

Every prompt string below is copied verbatim from `engine/console.py`
(`_ask_scope`, the `worker_count` loop, the ask-before-merging line,
`_ask_role_models`/`_recommended_model`/`_role_label`) — this is the check
against which `test:<bootup_journey_sequence_frozen>` holds the sequence.

Block 01-38 T24 (ADR-0003 D-J) layers the AIDE advisory lane onto this SAME
sequence, ahead of the two questions it advises — `_ask_aide_model` (a new
session knob, fail-open) -> `_aide_advise_scope` (ND-01-08) -> the scope
question -> `_aide_advise_counts` (ND-01-09) -> the worker_count question.
AIDE is advisory ONLY (never decides scope/worker_count itself) and is a
REAL LLM call every time (`engine/judge.py::call_aide`, never a heuristic/
deterministic stand-in — the binding AIDE-must-be-LLM mandate) that
degrades to "proceeding unaided" on any failure (fail-open, never blocks
boot). `judge.call_aide`'s own chokepoint already writes the
`aide_invocation` forensic event on every real call (T7's registry entry,
`core/emit.py`) — this module does not duplicate that emission.

NOT in this module (deliberately, by task split):
  - The REPL / fleet-view / attach / run-control commands — not named by
    any T23-25 acceptance criterion; only the BOOTUP JOURNEY is in scope
    here. Restoring the full interactive shell is not requested by this
    block and would be scope creep past what T23-25's ACs test.
  - Persisting the ask-before-merging / worker-model answers into the
    session-store manifest so a LATER tick (a fresh `Engine(ctx)`
    instance) still sees them — block 01-38 T25's own job
    (`test:<journey_persist_session_store_only>`). This module stashes
    both on itself (`self.ask_before_merging`, `self.worker_models`) so
    T25 has something to persist without re-deriving the answers; the
    worker-model answers ARE already effective for THIS boot's own spawns
    (the persistent architect + the first dispatch pass), since they are
    threaded straight into the SAME `Engine.start(models=...)` in-memory
    override `core/engine.py` already implements — only a SECOND, later
    `Engine` instance (e.g. a fresh wake-tick process) needs T25's durable
    layer.

FAIL-CLOSED MODEL RESOLUTION (AC-19): enforced at the root, inside
`core.engine.Engine.start()` itself (see that module's own T23 comment) —
not re-implemented here — so BOTH this interactive journey and a headless
caller that bypasses this module entirely (`eng.start(...)` directly, the
harness's own documented shape) get the identical fail-closed guarantee. A
`roles.RolesError` raised there propagates straight up through `bootup()`
uncaught, exactly like `engine.BootupError` already does. (AIDE's OWN model
is the opposite — explicitly FAIL-OPEN, D-J reconciliation (a); see
`_ask_aide_model` below.)

ND-01-14 RESOLVE / ND-09 PARLEY `ask` (disclosed T24 scope note): D-J maps
FIVE AIDE nodes total. The two bootup nodes (scope/counts, above) and the
runtime escalation case-brief (`core/casestate.py::architect_resolve`,
wired by this same task) all have REAL, live triggers in `core/*` and are
wired for real. `ask` (an operator posing a fresh free-text question
mid-run) has NO live trigger anywhere in `core/*` today — grepped, no
"operator asks a new question" concept exists (only the OPPOSITE: an
operator ANSWERING an already-open case, `core/casestate.py::settle`, a
different thing). The REFERENCE implementation has the SAME disclosed gap
for its own ND-01-14 node (`engine/console.py::_aide_resolve`'s own
docstring: "this block's frozen journey does not itself wire a live
resume-conflict TRIGGER... this is the advisory half ready for it to
call"). `_aide_answer_ask` below mirrors that shape exactly: a real,
directly-callable, real-LLM primitive (tested directly), not wired to any
live in-tick trigger, since none exists to wire it to — inventing a new
"operator asks mid-run" subsystem is not named by any T23-25 AC.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import emit               # noqa: E402 — core/emit.py, the one emit API (the scope-fallback event)
import pipeline            # noqa: E402 — core/pipeline.py, the trunk-pinned view (scope resolution)
from engine import Engine, BootupError   # noqa: E402 — core/engine.py, the module this fronts
import judge                              # noqa: E402 — engine/judge.py, the ONE real-LLM AIDE lane

DIM, RST, BOLD = "\033[2m", "\033[0m", "\033[1m"

# ADR-0003 D-D — the bootup model question's RECOMMENDED fallback tier when
# a role's own roles.yaml declares no model: a strong tier for the
# persistent spec-owner role, a fast tier for everyone else. Shown as a
# confirm/override suggestion ONLY (never itself a silent resolution path —
# `core.engine.Engine.start`'s fail-closed `validate_models` call owns
# that). Byte-for-byte copy of `engine/console.py`'s own
# `ROLE_MODEL_RECOMMENDED`/`ROLE_MODEL_LABEL` — the frozen recommendation.
ROLE_MODEL_RECOMMENDED = {"architect": "claude-opus-4-8", "other": "claude-sonnet-4-5"}
ROLE_MODEL_LABEL = {"architect": "the persistent architect/spec-owner", "other": "engineers/reviewers"}


class Bootup:
    """The frozen operator bootup journey, ported into `core/*` against
    `core.engine.Engine`. Construct with a live `ctx` (`engine/ctx.py::Ctx`,
    the same runtime-context resolver `core.engine.Engine` itself takes),
    call `.bootup(staged_model=...)` once."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.ask_before_merging = None   # set by bootup() — T25 persists this
        self.worker_models = None        # set by bootup() — T25 persists this
        self.engine = None                # the booted Engine instance, post-bootup

    # ── AIDE (block 01-38 T24, ADR-0003 D-J): a real judge.call("aide") LLM
    #     lane, NEVER a heuristic/deterministic stand-in — advisory only.
    #     `judge.call_aide`'s own chokepoint writes the `aide_invocation`
    #     forensic event on every real call (T7's registry, core/emit.py);
    #     not duplicated here. ──
    def _ask_aide_model(self, eng, staged=None):
        """AIDE's own model (D-J reconciliation (a)): a session knob,
        FAIL-OPEN to judge's built-in default — resolved BEFORE any AIDE
        call below so the very first advisory already rides the
        operator's choice. Never boot-fatal (unlike the per-role model
        question): a headless/staged caller with no "aide" answer
        silently keeps the built-in default. Byte-for-byte copy of
        `engine/console.py::_ask_aide_model`."""
        default = judge.TIER.get("aide", judge.AIDE_DEFAULT_MODEL)
        if staged is not None:
            v = (staged.get("aide") or "").strip()
        else:
            v = input(f"Model for AIDE (the operator's LLM advisor) [{default}]? ").strip()
        eng.set_aide_model(v or default)

    def _aide_advise_scope(self, eng):
        """ND-01-08 SET SCOPE: AIDE — a REAL LLM (`judge.call_aide`, never
        a heuristic) — advises on scope, including which block to pick,
        over the dispatch-eligible candidates on the current trunk-pinned
        view. Advisory only — never sets scope itself; the operator's own
        answer right after this always wins. Fail-safe: AIDE unavailable
        -> proceeds unaided, never a deterministic substitute. Byte-for-
        byte copy of `engine/console.py::_aide_advise_scope`, retargeted
        at `core.pipeline` (this stack's dispatch-eligible read) instead
        of the legacy `reader.dispatchable(row, idx)` loop."""
        view, _sha = pipeline.read_view(eng)
        candidates = pipeline.dispatchable(eng, {}, view=view)[:5]
        block_files = [c["block_file"] for c in candidates if c.get("block_file")]
        ok, out, _ = judge.call_aide(
            eng.ctx, eng.paths, "scope",
            extra={"candidate_blocks": [c["id"] for c in candidates]},
            block_files=block_files, model=eng.aide_model(), elog=eng.events)
        if ok and out and out.get("advice"):
            print(f"{DIM}  AIDE: {out['advice']}{RST}")
            if out.get("recommended_block"):
                print(f"{DIM}  AIDE recommends: block {out['recommended_block']}{RST}")
        else:
            print(f"{DIM}  AIDE: unavailable — proceeding unaided; your scope choice "
                  f"below decides.{RST}")

    def _aide_advise_counts(self, eng, scope):
        """ND-01-09 SET COUNTS: AIDE advises on `worker_count` only
        (`#architects` is fixed at 1 this version — no count to advise,
        ADR-0003 D-D/D-J BLOCKER-2) via a real `judge.call_aide`, given
        the JUST-ANSWERED scope. Fail-safe: unavailable -> proceeds
        unaided. Byte-for-byte copy of `engine/console.py::
        _aide_advise_counts` (passed `scope` directly — this module has
        no `eng.st.scope` to read back)."""
        ok, out, _ = judge.call_aide(
            eng.ctx, eng.paths, "counts", extra={"scope": scope},
            model=eng.aide_model(), elog=eng.events)
        if ok and out and out.get("advice"):
            print(f"{DIM}  AIDE: {out['advice']}{RST}")
        else:
            print(f"{DIM}  AIDE: unavailable — proceeding unaided.{RST}")

    def _aide_answer_ask(self, eng, question):
        """ND-09 PARLEY open `ask` (ADR-0003 D-J): a real `judge.call_aide`
        'ask'-mode call attempting to answer `question` strictly from the
        Project Docs. A directly-callable, testable, REAL-LLM primitive —
        see this module's own docstring for why no live in-tick trigger
        exists in `core/*` to wire it to yet (no "operator poses a fresh
        question mid-run" concept exists anywhere in `core/*` today;
        mirrors the reference `engine/console.py::_aide_resolve`'s own
        disclosed same-shape gap for ND-01-14). Returns `(answered,
        advice)`: `answered` is True ONLY when AIDE both responded AND
        explicitly signaled it could answer from the docs (`out.get
        ("answered")` — the ask-mode-only field `engine/judge.py::_v_aide`
        validates); `(False, None)` on any failure or an explicit "can't
        answer from the docs" — never a heuristic guess either way."""
        ok, out, _ = judge.call_aide(
            eng.ctx, eng.paths, "ask", extra={"question": question},
            model=eng.aide_model(), elog=eng.events)
        if ok and out and out.get("advice"):
            return bool(out.get("answered")), out["advice"]
        return False, None

    # ── 1. scope: [1] all / [2] a phase / [3] a range of blocks ──
    def _ask_scope(self, eng):
        """Byte-for-byte copy of `engine/console.py::_ask_scope`'s own
        prompt wording/options — the operator NEVER sees a different
        question here than the legacy engine asked. Returns the value
        `core.engine.Engine.start(scope=...)` expects: `"all"` or an
        explicit list of trunk block ids.

        Judgment call (disclosed, T23 WORK LOG): `core.engine.Engine.
        start()` resolves scope ONCE at boot as an explicit id list (see
        that module's own docstring: "never a re-derivation of a question
        this brick doesn't own") — unlike the legacy engine, which stores
        `{mode, value}` and re-filters every tick. The QUESTION and its
        THREE OPTIONS are unchanged (frozen); only the mechanical
        translation into core's boot-time id-list shape is new, and it
        reuses the legacy engine's OWN phase/range matching semantics
        (`engine/fsm.py::_in_scope_rows`, read for shape only) so the
        operator-visible RESULT of picking a phase/range is identical."""
        choice = input("  [1] all  ·  [2] a phase  ·  [3] a range of blocks  → ").strip()
        if choice == "2":
            phase = input("  Which phase (name or number, e.g. 'Phase 2' or '2')? ").strip()
            return self._resolve_phase_scope(eng, phase)
        if choice == "3":
            lo = input("  First block ID? ").strip()
            hi = input("  Last block ID? ").strip()
            return self._resolve_range_scope(eng, lo, hi)
        return "all"

    def _resolve_phase_scope(self, eng, phase):
        """`engine/fsm.py::_in_scope_rows`'s `mode == "phase"` arm,
        re-expressed against a fresh trunk-pinned read (`core.pipeline.
        read_view`) instead of a re-filter of `self.st.pipeline` every
        tick: substring, case-insensitive, over each row's own `phase`
        field. An empty phase answer (or one matching nothing on the
        trunk) is legitimate and unrestricted — never a typo/error at this
        step (the legacy engine's own `_bootup_gateway` only flags a
        NON-EMPTY unmatched phase as `scope-typo`, and even then merely
        holds the bootup gateway rather than raising; core's `Engine.
        start` already fails loud on an explicitly-named unknown block id,
        so an unmatched non-empty phase answer here safely degrades to
        "all" rather than duplicating that gateway)."""
        view, _sha = pipeline.read_view(eng)
        want = str(phase or "").strip().lower()
        if not want:
            return "all"
        ids = [row["id"] for row in view if want in str(row.get("phase") or "").lower()]
        if not ids:
            self._fallback_to_all(eng, "phase", phase,
                                  f"no trunk block's phase field matches {phase!r}")
            return "all"
        return ids

    def _resolve_range_scope(self, eng, lo, hi):
        """`engine/fsm.py::_in_scope_rows`'s `mode == "range"` arm: the
        inclusive slice of the trunk-pinned pipeline's own id ORDER
        between the two named endpoints (order swapped if given
        backwards). An unresolvable endpoint falls back to "all" — the
        exact legacy fallback (`except (ValueError, IndexError, TypeError):
        return rows`, i.e. every row, unrestricted)."""
        view, _sha = pipeline.read_view(eng)
        ids = [row["id"] for row in view]
        try:
            i, j = ids.index(lo), ids.index(hi)
        except ValueError:
            self._fallback_to_all(eng, "range", [lo, hi],
                                  f"endpoint {lo!r} or {hi!r} not found on the trunk-pinned "
                                  f"pipeline view")
            return "all"
        i, j = min(i, j), max(i, j)
        return ids[i:j + 1]

    def _fallback_to_all(self, eng, mode, value, reason):
        """A phase/range scope answer that resolves to NO trunk block ids
        (or an unresolvable endpoint) silently-widening to "all" is a known
        TRON silent-defaults killer — made observable two ways, never a
        quiet swallow: (1) a forensic `bootup_scope_fallback` event on
        `eng.events` (readable from `events.jsonl`, ground truth, even
        though no manifest exists yet at this pre-`Engine.start` point —
        see `core/emit.py`'s own registration comment); (2) a loud
        (non-DIM) operator-visible print, distinct from every other DIM
        informational line in this journey, so an interactive operator
        cannot miss that their answer was WIDENED rather than honored."""
        print(f"{BOLD}  ! scope {mode}={value!r} matched nothing on trunk ({reason}) — "
              f"widening to 'all'.{RST}")
        emit.record(eng, "bootup_scope_fallback", requested_mode=mode,
                   requested_value=value, reason=reason, resolved="all")

    # ── 2. worker_count ──
    def _ask_worker_count(self):
        """Byte-for-byte copy of `engine/console.py`'s own worker_count
        loop — identical prompt text, identical validation (a positive
        integer, re-asked until satisfied)."""
        worker_count = None
        while worker_count is None:
            v = input("worker_count (build + review workers; the persistent spec-owner "
                      "role is extra)? ").strip()
            if v.isdigit() and int(v) > 0:
                worker_count = int(v)
            else:
                print(f"{DIM}  (a positive integer){RST}")
        return worker_count

    # ── 3. ask-before-merging ──
    def _ask_before_merging_q(self):
        """Byte-for-byte copy of `engine/console.py`'s own ask-before-
        merging prompt. NOT wired into any downstream gating behavior by
        this task (no `core/*.py` module reads an `ask_before_merging`
        knob today) — restoring the ANSWER + its later session-store
        persistence is T23/T25's job; wiring the answer into the landing
        path is out of scope for this task (not named by any T23-25 AC)."""
        ans = input("Inform you before each merge to trunk? [y/N] ").strip().lower()
        return ans in ("y", "yes")

    # ── 4. model, per role ──
    def _role_label(self, role, cfg):
        tier = "architect" if (cfg.get("spec_owner") or cfg.get("persistent")) else "other"
        return f"{role} ({ROLE_MODEL_LABEL[tier]})"

    def _recommended_model(self, eng, role):
        """The default OFFERED at the bootup model prompt for `role` —
        never itself the resolution path (`core.engine.Engine.start`'s
        `validate_models` call owns that). Prefers the role's OWN declared
        roles.yaml `model:` field; falls back to the per-tier suggestion
        only when roles.yaml itself declares none for this role. Byte-for-
        byte copy of `engine/console.py::_recommended_model`."""
        rc = eng._roles_config()
        cfg = rc.roles.get(role) or {}
        declared = rc.model_for(role)
        if declared:
            return declared
        tier = "architect" if (cfg.get("spec_owner") or cfg.get("persistent")) else "other"
        return ROLE_MODEL_RECOMMENDED[tier]

    def _ask_role_models(self, eng, staged=None):
        """Ask the worker model PER ROLE — every role roles.yaml declares
        gets its own question, each showing a recommended default the
        operator confirms (Enter) or overrides. `staged` (01-30 T3
        parity) supplies the answers programmatically with NO prompt at
        all — a non-interactive call must never block on `input()`. A
        staged role with no answer (missing/blank) is left UNRESOLVED
        here (never silently given the recommended default) —
        `core.engine.Engine.start`'s `validate_models` call is the
        fail-closed guard for that; this method's own job is only to
        report whatever was actually decided, never to paper over an
        absent one. Byte-for-byte copy of `engine/console.py::
        _ask_role_models`'s own logic (retargeted at `core.engine.Engine`
        via `eng._roles_config()` instead of `eng.roles`)."""
        rc = eng._roles_config()
        answers = {}
        for role in sorted(rc.roles.keys()):
            if staged is not None:
                answers[role] = (staged.get(role) or "").strip() or None
                continue
            cfg = rc.roles.get(role) or {}
            default = self._recommended_model(eng, role)
            label = self._role_label(role, cfg)
            v = input(f"Model for {label} [{default}]? ").strip() or default
            answers[role] = v or None
        return answers

    # ── the whole journey ──
    def bootup(self, staged_model=None):
        """Run the frozen sequence, then boot the real engine.

        `staged_model` (01-30 T3 parity): an optional {role: model} dict
        supplied programmatically so the MODEL question never calls
        `input()` — a non-interactive bootup must never hang on a prompt.
        Interactive callers pass nothing and get asked, per role, exactly
        as the legacy console behaved. Scope/worker_count/ask-before-
        merging still prompt regardless (unchanged from the legacy
        engine's own `staged_model` scope, `engine/console.py:119-123`) —
        a caller that wants those non-interactive too seeds `input` itself
        (the same convention `tron-meta/sims/autopilot/bootstrap.py`'s
        live-boot launcher already uses against the legacy console).

        Returns `(engine, spawned)` — the booted `core.engine.Engine`
        instance and the list of freshly spawned agent-ids `Engine.start`
        itself returns."""
        print(f"{BOLD}== TRON bootup =={RST}")
        eng = Engine(self.ctx)

        # ADR-0003 D-J: AIDE's own model, resolved BEFORE any AIDE call
        # (fail-open — never boot-fatal, unlike the per-role model question
        # below). Then ND-01-08 SET SCOPE (advisory only — never sets scope
        # itself) ahead of the real scope question, then ND-01-09 SET COUNTS
        # ahead of the worker_count question, given the just-answered scope.
        self._ask_aide_model(eng, staged=staged_model)
        self._aide_advise_scope(eng)
        scope = self._ask_scope(eng)
        self._aide_advise_counts(eng, scope)
        worker_count = self._ask_worker_count()
        self.ask_before_merging = self._ask_before_merging_q()
        self.worker_models = self._ask_role_models(eng, staged=staged_model)

        spawned = eng.start(scope=scope, worker_count=worker_count, models=self.worker_models)
        self.engine = eng
        print()
        print(f"{DIM}  TRON is live. (session-store persistence of ask-before-merging / "
              f"per-role model answers past this boot is block 01-38 T25.){RST}\n")
        return eng, spawned
