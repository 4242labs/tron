"""r3_lint — R3 honesty lint (ADR-0012 §2 R3 / block 01-40 T1).

The only legal ingress into the engine is the real reporting door:
`scripts/report.sh` writes a JSON line to `ctx.worker_inbox`, hardcoding
`sender.kind: "worker"` — the ONLY sender kind the real door can ever
produce. A harness that writes a report claiming any OTHER sender kind into
that file asserts an identity nothing real produced (R6), and a rig that
writes `ctx.operator_inbox` fabricates a channel wholesale — there is no
real operator transport yet (R8). A harness that mutates `manifest[...]`
directly, instead of letting the real drain (tick -> classify -> router)
apply the effect, skips the door entirely. Three violation classes:

  INBOX_FABRICATED_SENDER   a write to ctx.worker_inbox whose JSON payload
                             asserts sender.kind != "worker" (or is not a
                             statically-provable dict literal at all).
  OPERATOR_INBOX_WRITE      any write-capable touch of ctx.operator_inbox.
  MANIFEST_DIRECT_WRITE     any store/mutate of manifest-rooted state.

DESIGN — flow-insensitive TAINT UNION, monotone fixed point. Rebuilt a
FOURTH time: each of the first three rebuilds replaced one finite
enumeration (write mechanisms, then binding shapes) with a bigger finite
enumeration, and a hostile review kept finding the next shape outside it —
if/else and try/except branch shadowing beat "nearest binding wins";
os.path.* reconstruction beat a resolver that didn't propagate through
calls; IfExp/BoolOp beat an expression walk that didn't recurse into them;
AugAssign and lambda closures were missing binding forms entirely. A
resolver built from "the nearest/first proof wins" or "enumerate the shapes
I've seen" cannot structurally guarantee no false-GREEN — it only takes one
more shape. This rebuild replaces resolution with UNION: taint can only be
ADDED across every possible path, never picked between them, so a missed
case can only cause a false RED, never a false GREEN.

  1. SEEDS — a `ctx.worker_inbox`/`ctx.operator_inbox` Attribute, or any
     Name/Attribute whose bare name contains "manifest", taints its own
     occurrence with that marker's kind.
  2. UNION BINDING — a name is tainted with kind K if ANY statement,
     anywhere in the file, IN ITS OWN LEXICAL SCOPE, binds it to an
     expression tainted with K: Assign (any target shape), AugAssign,
     AnnAssign, NamedExpr, For/With targets, comprehension targets,
     function/lambda parameters (bound to the union of every same-file
     call site's actual argument, evaluated in the CALLER's scope, plus
     the parameter's own default). Never "the nearest one" — the union of
     ALL of them, via a monotone fixed point: relax every binding
     repeatedly until no key's taint set grows. Scoping is real Python
     lexical scoping (each `def`/`lambda` is its own scope; a name not
     locally bound falls back to module level) — NOT a whole-file flat
     namespace: two unrelated functions' same-named local (`path`, `f`,
     `root`, ...) are different variables and do not share provenance.
     `self.x`/`Cls.x`-style attribute storage is the one deliberate
     exception (kept bare/global — see limits below).
  3. CALL PROPAGATION — any call whose receiver or any argument is tainted
     has a tainted return, unconditionally — this is what makes `str(x)`,
     `os.path.join(...)`, and the next un-enumerated stdlib wrapper
     taint-transparent BY CONSTRUCTION instead of by enumeration. A
     same-file function or lambda additionally contributes the union of
     its own `return`/lambda-body taint to every call site.
  4. CONTAINERS — a Dict/List/Tuple/Set literal (or comprehension) is
     tainted if any element is; a Subscript or non-marker Attribute of a
     tainted expression is tainted.
  5. SINKS — a call is in scope only if it matches a recognized WRITE-
     OPERATION shape: `.write`/`.writelines`/`.write_text`/`.write_bytes`/
     `.append`/`.update`/`.extend`/`.insert` (target = the receiver),
     `print(file=...)` (target = the `file` kwarg), `json.dump`/
     `os.replace`/`os.rename`/`shutil.copy`/`copyfile`/`move` (target =
     the 2nd positional/`dst`-ish kwarg), or `open`/`io.open`/`.open()`
     opened in a write/unresolved mode (checked against
     `ctx.operator_inbox` unconditionally — illegal to write at all,
     regardless of payload; NEVER itself the WORKER/manifest sink, since
     it carries a mode not a payload — the real write is whatever
     downstream call taint propagation still reaches). A SMALL, STABLE
     enumeration of "what physically writes" — not of binding/aliasing
     shapes (what defeated the first three rebuilds; those are now
     resolved generically by rules 2-4). `ctx.worker_inbox` is illegal
     unless every candidate the sink's other slot can resolve to (via the
     same union substrate) is a dict literal with no `sender` key or
     `sender.kind == "worker"`. A manifest-rooted subscript store/
     augstore, or a write-sink call on manifest-rooted state, is always
     illegal.
  6. CONTAINER MUTATION (block 01-40 T1, second hostile review; extended
     TWICE since) — rule 2's binding forms only ever recorded taint for a
     name FRESHLY bound to a tainted value; a name whose already-bound
     container was MUTATED in place afterward read as permanently clean
     forever — `argv = []; argv.append(eng.ctx.worker_inbox);
     subprocess.run(argv)` was a GREEN miss (`argv` never "bound" to
     anything tainted; the taint arrived via mutation, invisible to rule
     2's binding walk). First closed for `.append`/`.extend`/`.insert`/
     `.add`/`.update` and a `Subscript` STORE `d[k] = v` via an enumerated
     method-name list; THIRD hostile review then found the enumeration
     itself was the SAME disease rule 2 was rebuilt four times to escape —
     `env.setdefault("P", eng.ctx.worker_inbox)` and `env.__setitem__("P",
     eng.ctx.worker_inbox)` were a live GREEN miss the enumeration simply
     didn't name. REPLACED (not extended again) with a STRUCTURAL rule: for
     ANY method call `recv.METHOD(...)`, if ANY positional/keyword argument
     carries taint, that taint is registered as an ADDITIONAL source for
     the RECEIVER's key — regardless of what `METHOD` is called. This
     covers `.setdefault`/`__setitem__`/`.update`/`.append`/`.extend`/
     `.insert`/`.add` and every future stdlib mutator BY CONSTRUCTION, the
     same move rule 3 (CALL PROPAGATION) already made for ordinary value
     flow. `.popitem()`-writeback needed NO new mechanism at all: once a
     container is genuinely tainted (via the mechanism above), a call
     whose RECEIVER is tainted already has a tainted RETURN by the
     pre-existing rule 3 — the popped-out value inherits it for free. All
     of this feeds the SAME SEPARATE substrate (`container_bindings`,
     folded into the same monotone fixed point) that contributes ONLY
     `{"worker", "operator"}` — deliberately NEVER `"manifest"` (see below).
     `d |= other` needed no separate handling at all: an `AugAssign` to a
     bare `Name` was already routed through rule 2's own generic `add()`
     call unconditionally, for every operator — verified empirically, not
     assumed (see `.github/scripts/r3_honesty_lint_check.py` fixture 44).
     TWO exclusions keep the generic "any method call" rule from
     over-firing on calls that structurally cannot be container mutations
     (both verified empirically against the real tree, and both
     FALSE-RED-reducing only for every case this tree currently exercises
     — see `_build_ctx`'s own inline comment for the full account,
     including the narrower-but-wrong variant tried and reverted along the
     way): a call whose bare method name matches a same-file function/
     method (`fname in funcs`) is excluded, since rule 3's own call-graph
     propagation already covers it correctly; a call whose receiver's
     attribute-chain root is a same-file `import`-bound name (`os.path.
     join(...)`) is excluded, since a module is never legitimately-mutable
     aliased state. Manifest's own sink checks (`_CONTAINER_MUTATE_ATTRS`
     in rule 5, and `_check_manifest_stores`) are about receiver ALIASING
     ("is this container itself manifest-rooted state" — rule 1's seed
     plus rule 4's subscript-READ aliasing, both of which stay real Python
     reference semantics), never about "did some element/value ever pass
     through it" — conflating the two (tried, then reverted, in an earlier
     round of this fix) false-REDs every ordinary `results.append(
     some_manifest_derived_summary)` reporting/iteration pattern across
     nearly every `core/*_rig.py`, none of which is a manifest write at
     all.

The fixture suite in `.github/scripts/r3_honesty_lint_check.py` — every
evasion four hostile reviews produced, plus the required-GREEN controls —
is this module's living spec; read it before touching this file.

REMAINING LIMITS (adversarial-only; over-approximation makes every one of
these a false-RED risk, never a false-GREEN one):
  - same-file only — a channel/manifest reference forwarded through
    another module is not traced.
  - attribute-storage keys (`self.x`, `Cls.x`) are matched BARE, across
    the whole file — two unrelated classes' same-named attribute share
    provenance. Ordinary local variables and parameters do NOT share this
    problem (they are properly scope-keyed).
  - a lambda/nested function closing over an ENCLOSING FUNCTION's local
    (not a module global, and not a marker Attribute) is not traced back
    through the closure — only module-level fallback is checked.
  - `exec`/`eval`, and `getattr(obj, computed_expr)` where the attribute
    name is not itself a statically-resolvable string, are not traced.
  - a `subprocess.{run,call,check_call,check_output,Popen,system,popen}`
    or `os.{system,popen,exec*,spawn*}` call is caught the moment ANY of
    its arguments carries WORKER/OPERATOR taint (an ingress FILE PATH,
    the shape a channel-fabrication evasion needs to hand a child) — the
    SAME union substrate as every other sink (rules 2-4), so a tainted
    path/payload inside an argv LIST, a concatenated string, or an
    f-string is caught identically, no shell redirect syntax required.
    (A PRIOR version of this check required a textual `>`/`>>` redirect
    and was WRONG — `subprocess.run([sys.executable, "-c", code,
    protected_path, payload])` contains no redirect character and
    slipped through clean; fixed block 01-40 T1, second pass,
    required-RED fixture 36.) MANIFEST taint is deliberately EXCLUDED
    from this particular sink — manifest taint marks any manifest-
    DERIVED value (rule 4: a subscript read off tainted state is itself
    tainted), which routinely flows into subprocess argv as ordinary
    data in this real tree (a case ID read off the manifest, passed to
    `land.sh`) with no receiver/target slot for a "direct write" to land
    on at all; scoping manifest in here would false-RED that legitimate
    pattern across most of `core/*_rig.py`, not catch a new evasion. The
    one TRUE residual, honest and adversarial-only: a child-process
    invocation built from NO tainted argument at all — every argument a
    bare literal, the protected path reconstructed or hardcoded
    independently rather than derived from a traced
    `ctx.worker_inbox`/`ctx.operator_inbox` marker. There is no taint to
    see in that shape, so no static prover — this one or any rebuild of
    it — can catch it; that gap belongs to a runtime mechanism
    (`core/r3_guard.py`), which itself documents the matching hole (its
    hook does not propagate through `exec`), never to this module.
  - a write OPERATION outside the enumerated list in rule 5 is not
    recognized as a STATIC sink — taint still flows through it (rule 3), so
    anything written FROM it further downstream is still caught; only that
    one call, standing alone, is not itself flagged. This enumeration is
    now DELIBERATELY non-exhaustive by design, not just by history: it is a
    fast, structural SMOKE layer (catches the common/obvious shapes at AST
    time, zero process spawned), never the thing actually responsible for
    "can a byte physically land on a protected path" — that job belongs to
    `core/r3_guard.py`'s runtime `sys.addaudithook` (block 01-40 T1, Opus-
    pivot item 1/2), which is mechanism-complete by construction (it sees
    every real OS-level write CPython can make, not an enumerated list of
    Python-level call shapes) for whatever paths it is told to protect.
    Extending this static enumeration further (csv/`os.write`/...) was
    considered and deliberately NOT done — it would duplicate, in a
    strictly weaker form, what the runtime guard already proves.
  - mutually-exclusive REBINDINGS of one bare name (if/else branches,
    try/except handlers, sequential unrelated `with open(...) as f:`
    blocks reusing `f`) UNION their taint under this module's flow-
    insensitive design — by construction (module docstring's rule 2: "the
    union of ALL of them", never flow/branch-aware). A name legitimately
    bound to something inert in one branch and something tainted in an
    UNRELATED branch is flagged as if EVERY use of that name were tainted,
    even a use that can only ever see the inert branch. This is accepted,
    not fixed: making it flow-sensitive is exactly the design this module
    was rebuilt FOUR times to get away from (each earlier attempt's
    flow/branch-awareness was also its false-GREEN hole — see the block
    01-40 T1 rebuild history above). The only sound, simple, PRACTICAL
    mitigation is what commit aeb6360 already applied in a handful of real
    call sites — rename the reused bare name (`f` -> `bf`) so the two
    bindings are no longer the same key at all. False-RED (an occasional
    forced rename) is the accepted cost; false-GREEN is not.
  - CONTAINER MUTATION (rule 6) — THIRD hostile review's fix — is now
    tracked for ANY method call `recv.METHOD(...)` whose receiver resolves
    to a container-like name, if ANY of the call's OWN arguments carries
    taint, REGARDLESS of `METHOD`'s name: a container is no longer silently
    clean forever after a tainted element/value passes through it via
    `.append`/`.extend`/`.insert`/`.add`/`.update`/`.setdefault`/
    `__setitem__`/`Subscript`-STORE/`AugAssign`, OR any future stdlib
    mutator this module has never seen, by construction rather than by
    enumeration — the SAME "structural, not enumerated" move rule 3 (CALL
    PROPAGATION) already made for ordinary value flow. `.popitem()`-
    writeback needs no dedicated handling: once a container is genuinely
    tainted, rule 3's PRE-EXISTING receiver-taint-propagates-to-return
    already carries that taint out through ANY call on it, popitem
    included. TWO exclusions bound the generic rule to calls that can
    structurally BE a container mutation (both verified empirically against
    the real tree — see `_build_ctx`'s own inline comment for the full
    account of what broke and why, including a narrower-but-wrong variant
    tried and reverted along the way): (a) a call whose bare method name
    matches a same-file function/method (`fname in funcs`) — rule 3's own
    call-graph propagation already covers such a call correctly, and
    treating it as a container mutation ANYWAY was the exact false-RED this
    round found TWICE, first for `self.method(...)` then for
    `plain_var.method(...)` on an instance held outside its own class; (b)
    a call whose receiver's attribute-chain root is a same-file
    `import`-bound name (`os.path.join(...)`) — a module is never
    legitimately-mutable aliased state. Two deliberate, honest scope limits
    remain: (1) a nested-subscript store (`x[a][b] = v`) taints only the
    ROOT container `x` as a whole, never a specific key path — the SAME
    flow-insensitive, whole-object granularity every other binding form in
    this module already accepts (see the mutually-exclusive-rebindings
    limit above), never a per-key/per-index precision this design was
    never meant to have; (2) exclusion (a) above is a bare/unscoped
    `funcs`-name collision risk of the SAME shape this module's `("attr",
    ...)` substrate already accepts elsewhere — a genuine
    `results.append(tainted)` would be false-GREENed if the SAME file
    happened to ALSO define any unrelated function/method literally named
    `append` (or whatever the real mutator's name is); verified EMPTY
    across every file `harness_files()` scans as of this fix, but not
    structurally impossible, since closing it fully needs real
    interprocedural type inference (is the receiver ACTUALLY a dict/list/
    set, not just "some object with a matching method name"), out of reach
    for an AST-only prover.

  TRUE RESIDUAL after this round (the two limits directly above aside):
  the ONLY way a WORKER/OPERATOR-tainted value can now reach a recognized
  sink without this module seeing it is a shape that never puts the tainted
  value INTO an ordinary Python-level argument/binding/mutation AT ALL —
  genuinely non-arg-carrying laundering (a channel reconstructed from
  scratch with no traceable link back to `ctx.worker_inbox`/
  `ctx.operator_inbox`, the SAME "no tainted argument at all" residual
  already documented for the subprocess sink above) or adversarial
  reflection (`exec`/`eval`, or `getattr` with a non-literal, dynamically
  computed attribute name — see the existing bullet above). Ordinary dict/
  list/set mutation, by ANY method name, is no longer part of that
  residual.
"""
import ast
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The explicit, visible known-red list (T1 spec: "an EXPLICIT, visible
# known-red manifest that lists each offender with its owning block"). This
# is never a silent whitelist — `run()` re-verifies every entry every call:
# a listed file that comes back CLEAN is a stale entry (FAIL, remove it or
# it regressed silently); a red file NOT listed here is an unlisted offender
# (FAIL, add it with its owning block or fix it).
KNOWN_RED = {
    "core/sim/operator_proxy.py": {
        "owning_block": "01-38",
        "reason": ('_inject_decision fabricates sender.kind="operator" and appends '
                   "it straight to eng.ctx.worker_inbox (the WORKER channel) — "
                   "report.sh, the one real door, can only ever emit "
                   'sender.kind="worker"; there is no real operator transport yet '
                   "(that is R8/R6, later blocks). ADR-0012 §2 R8 names this exact "
                   'harness: "the current harness injects into the worker channel '
                   'and lies exactly the way the old rigs lied." Rebuilt honestly '
                   "in 01-38 T4 once the real operator channel exists."),
    },
    "core/architect_rig.py": {
        "owning_block": "01-40",
        "reason": ("RIG2-C2 (run_seq_reconcile_rig) monkeypatches "
                   "real_eng2._next_mbox_seq and seeds real_eng2._manifest = {} on a "
                   "REAL core/engine.py Engine instance (CoreEngine — architect_rig.py's "
                   "own `from engine import Engine as CoreEngine`; its sys.path is "
                   "ordered core/ BEFORE engine/ — line 84's `sys.path.insert(0, HERE)` "
                   "runs AFTER line 83's engine/-dir insert, so it ends up first — so "
                   "the bare module name `engine` resolves to core/engine.py, R-A's "
                   "real implementation, NOT the engine/ package's engine/fsm.py), then "
                   "does `mbox[wid] = seq` off it — a manifest-rooted subscript store. "
                   "This block's own 3a fix (r3_lint's manifest fixture-local proof "
                   "now requires the receiver be provably bound to a LOCAL fixture "
                   "construction, never a real production class) correctly stops "
                   "exempting it: CoreEngine is real, imported production code, not a "
                   "same-file fake. CORRECTED (a prior version of this entry "
                   "investigated the WRONG FILE — engine/fsm.py's own unrelated Engine "
                   "class, which genuinely does compute "
                   "`seq = int(w.get('mbox_seq', 0)) + 1` inline off a worker dict and "
                   "never touches `_manifest`/`_next_mbox_seq` — and wrongly concluded "
                   "those attributes were dead on THIS class too): core/engine.py's "
                   "Engine._next_mbox_seq (lines 269-297) genuinely reads and writes "
                   "`self._manifest[\"mbox_seq\"][worker_id]` for real — "
                   "`mbox = self._manifest.setdefault(\"mbox_seq\", {})` then "
                   "`mbox[worker_id] = seq` — and Engine._to_worker (line 310) calls "
                   "`self._next_mbox_seq(worker_id)` at line 320 on every real dispatch; "
                   "Engine.start sets `self._manifest = snap.manifest` (line 654) as the "
                   "live handle for that pass. So the RED here is CORRECT under R3's "
                   "letter — this is in-process mutation of REAL engine state a real "
                   "code path genuinely reads, not a dead/vestigial attribute. The "
                   "rig's OWN intent is nonetheless legitimate mutation-testing "
                   "hygiene, not a lie: RIG2-C2 exists purely to prove RIG2-C1 (the "
                   "R-A engine-restart-wedge fix, asserted GREEN a few lines above) is "
                   "non-vacuous — it monkeypatches _next_mbox_seq to the pre-R-A, "
                   "persisted-counter-only reconciliation and asserts that the mutation "
                   "flips RIG2-C1's own assertion shape RED, i.e. that RIG2-C1 would "
                   "actually fail if the real fix regressed. That is the SAME AST shape "
                   "R3 targets (mutating real engine internals from a rig) but used "
                   "here for anti-vacuity, never to fake a drain outcome another module "
                   "then trusts. This lint intentionally cannot (and, by design, should "
                   "not try to) distinguish those two intents by AST shape alone, so "
                   "this stays KNOWN_RED rather than silently loosening the general "
                   "receiver-provenance rule for one caller, or touching RIG2-C1/"
                   "RIG2-C2's test semantics — a change outside 01-40 T1's "
                   "ruling-independent R3 scope. Follow-up decision, NOT resolved here, "
                   "for the ruling/01-40 completion: (a) rebuild RIG2-C1/RIG2-C2's "
                   "non-vacuity proof through a legitimate seam (e.g. a same-file "
                   "fixture Engine stand-in, or a public reset hook on CoreEngine) so "
                   "it no longer needs an in-process mutation of the real class at all, "
                   "or (b) formally, structurally reclassify 'real-class mutation for "
                   "anti-vacuity hygiene, never observed by other code as a fake drain "
                   "outcome' as an R3-exempt pattern — never a one-off carve-out for "
                   "this file alone."),
    },
}


class Violation:
    def __init__(self, path, lineno, rule, detail):
        self.path = path
        self.lineno = lineno
        self.rule = rule
        self.detail = detail

    def __str__(self):
        return f"{self.path}:{self.lineno}: [{self.rule}] {self.detail}"


def harness_files():
    """`core/*_rig.py` + every module under `core/sim/` (the whole proof-
    harness surface: the L1 mutation-proof rigs, plus the SIM apparatus they
    and the live runner share) — glob-discovered, never hand-maintained."""
    files = sorted(glob.glob(os.path.join(ROOT, "core", "*_rig.py")))
    files += sorted(
        p for p in glob.glob(os.path.join(ROOT, "core", "sim", "*.py"))
        if os.path.basename(p) != "__init__.py"
    )
    return files


# ═══════════════════════════ shared substrate ═══════════════════════════
#
# Every binding is stored as (target_key, value_expr, value_scope) — the
# VALUE's own free names resolve in `value_scope` (the scope the binding
# STATEMENT itself lives in — e.g. a call site's argument resolves in the
# CALLER's scope, even though it is bound into the CALLEE's parameter key).
# A key is either `("var", scope_id, name)` — `scope_id` is `id()` of the
# nearest enclosing `def`/`lambda`, or `None` at module level — or
# `("attr", attrname)` — deliberately UNSCOPED (see module docstring limit).

_MAX_DEPTH = 8
_INBOX_ATTRS = {"worker_inbox": "worker", "operator_inbox": "operator"}
_COPY_BOUNDARY_NAMES = {"list", "dict", "tuple", "set", "sorted", "frozenset"}
_COPY_BOUNDARY_METHODS = {"keys", "values", "items", "copy"}


def _is_manifest_name(name):
    return "manifest" in name.lower()


def _flatten_bind_targets(target):
    """Every bindable KEY a single assignment-target expression introduces
    — a bare `str` name, or `("attr", <attrname>)` for `self.x = ...`/
    `Cls.x = ...`. Recurses into `Tuple`/`List`/`Starred` so every name a
    compound target binds is captured. A `Subscript` target binds no NEW
    alias — handled separately by the manifest store-check."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Attribute):
        return [("attr", target.attr)]
    if isinstance(target, (ast.Tuple, ast.List)):
        out = []
        for elt in target.elts:
            out.extend(_flatten_bind_targets(elt))
        return out
    if isinstance(target, ast.Starred):
        return _flatten_bind_targets(target.value)
    return []


def _imported_module_names(tree):
    """Every bare name a same-file `import`/`from ... import ...` statement
    binds — `import os` -> `{"os"}`, `import os.path as osp` -> `{"osp"}`,
    `from ctx import Ctx` -> `{"Ctx"}`. Used ONLY to keep the THIRD hostile
    review's generic "any method call whose arg is tainted taints its
    receiver" rule (below) from mistaking a namespaced STDLIB FUNCTION CALL
    (`os.path.join(...)`, `json.dumps(...)`, `subprocess.run(...)`) for a
    container-mutation METHOD call on a stored object: structurally, both
    are `<Attribute-or-Name>.<name>(...)`, and Python's grammar alone cannot
    tell "an instance method mutating a stored container" apart from "a
    namespaced function reached through package dotting" — but a module
    import statement is itself the ONE unambiguous, structural signal that a
    name is a MODULE, never a container this rule should track aliasing for
    (a module is never reassigned/aliased as mutable state in legitimate
    code). Deliberately broad (covers `from X import Y` names too, even
    when `Y` is a class/function rather than a submodule) — a false
    exclusion here only means one more receiver isn't container-mutation-
    tracked, the SAME false-RED-only direction as every other choice in this
    module; it is never used to gate anything ELSE (rule 3's ordinary VALUE
    taint through `os.path.join(...)`'s arguments is untouched by this)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _attr_chain_root_name(expr):
    """Unwraps a (possibly multi-level) `Attribute` chain — `os.path.sep`,
    `a.b.c` — down to its leftmost `Name`, or `None` if the chain does not
    bottom out in a bare Name (e.g. it starts from a `Call`/`Subscript`).
    Used ONLY by the module-receiver exclusion above; `_container_receiver_
    key` itself deliberately does NOT do this unwrapping (it keeps `self.x`/
    `Cls.x` as its own distinct `("attr", "x")` key — see that function's
    own docstring)."""
    while isinstance(expr, ast.Attribute):
        expr = expr.value
    return expr.id if isinstance(expr, ast.Name) else None


def _container_receiver_key(expr):
    """The bindable KEY a container-MUTATION (never a fresh bind) should
    taint — block 01-40 T1, second hostile review's `argv.append(eng.ctx.
    worker_inbox)` / `env["P"] = tainted` miss, `.update()`/`|=`'s identical-
    shape miss, and THIRD hostile review's `env.setdefault("P", eng.ctx.
    worker_inbox)` / `env.__setitem__("P", eng.ctx.worker_inbox)` miss: rule
    2's binding forms only ever recorded taint for a name/attribute BOUND to
    a tainted value, never for a name whose already-bound container was
    MUTATED in place with tainted content afterward — `subprocess.
    run(argv)`/`subprocess.run(env=env)` then read `argv`/`env`
    itself, which the fixed point had never touched, straight through as
    clean. Unwraps nested `Subscript`s (`x[a][b] = v` / `x[a].append(v)`
    taints the ROOT `x`, consistent with this module's flow-insensitive
    UNION design — the exact same containing object, whichever key/index
    was touched) down to the nearest `Name`/`Attribute`, returning the SAME
    key shape `_flatten_bind_targets` already uses (`str` for a bare name,
    `("attr", name)` for `self.x`/`Cls.x`) so it feeds the identical
    `bindings`/union-taint substrate, or `None` if no such root exists
    (e.g. a mutation on a call result/literal — nothing to taint). THIRD
    hostile review's finding: this key is no longer gated on an enumerated
    METHOD NAME at all — see `_build_ctx`'s generic "any arg taints the
    receiver" call handling below, which is what actually decides WHEN to
    call this function now."""
    while isinstance(expr, ast.Subscript):
        expr = expr.value
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return ("attr", expr.attr)
    return None


def _destructured_bindings(target, iter_expr):
    """`[(flat_key, value_expr), ...]` for a `for <target> in <iter_expr>:`
    (or comprehension `for` clause). When `iter_expr` is a literal
    List/Tuple/Set of same-arity List/Tuple elements — the common `for a, b
    in ((x1, y1), (x2, y2)):` idiom — each loop variable is bound to the
    UNION of only its OWN positional column, not the whole iterable: this
    is a PRECISION improvement (deriving a tighter, still fully sound
    over-approximation from the same literal structure), not a weakening
    of union taint — it is what stops one tuple-unpack loop's `dep`/second
    column (legitimately manifest-derived) from bleeding into an unrelated
    `block`/first column reused by a LATER, different loop in the same
    function (flow-insensitivity's real cost, paid needlessly here since
    the destructuring is statically knowable). Any shape this cannot
    destructure falls back to binding every flattened target name to the
    WHOLE iterable — conservative, still sound, unchanged from before."""
    if isinstance(target, (ast.Tuple, ast.List)) and isinstance(iter_expr, (ast.Tuple, ast.List, ast.Set)):
        elts = iter_expr.elts
        n = len(target.elts)
        if elts and all(isinstance(e, (ast.Tuple, ast.List)) and len(e.elts) == n for e in elts):
            out = []
            for i, sub_target in enumerate(target.elts):
                for key in _flatten_bind_targets(sub_target):
                    for e in elts:
                        out.append((key, e.elts[i]))
            return out
    return [(key, iter_expr) for key in _flatten_bind_targets(target)]


def _direct_returns(fn):
    """Every `Return` node directly inside `fn`'s own body — never
    descending into a nested `def`/`lambda` (a different function's
    returns)."""
    out = []

    def walk(node, top):
        if node is not top and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(node, ast.Return):
            out.append(node)
            return
        for child in ast.iter_child_nodes(node):
            walk(child, top)

    walk(fn, fn)
    return out


def _direct_globals(fn):
    """Names declared `global`/`nonlocal` directly in `fn`'s own body (not
    descending into a nested `def`/`lambda`) — a binding to one of these
    inside `fn` is scoped to MODULE level, not to `fn`'s own local scope
    (`nonlocal` is conservatively also promoted to module level — an
    over-approximation, never a missed alias)."""
    names = set()

    def walk(node, top):
        if node is not top and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
            return
        for child in ast.iter_child_nodes(node):
            walk(child, top)

    walk(fn, fn)
    return names


def _build_parent_scope(tree):
    """AST node -> `id()` of its nearest enclosing `def`/`lambda`, or
    `None` at module level."""
    parent = {}

    def visit(node, cur):
        parent[node] = cur
        nxt = id(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) else cur
        for child in ast.iter_child_nodes(node):
            visit(child, nxt)

    visit(tree, None)
    return parent


def _call_target_name(call):
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


class _FuncInfo:
    __slots__ = ("params", "has_self", "scope_id")

    def __init__(self, params, has_self, scope_id):
        self.params = params
        self.has_self = has_self
        self.scope_id = scope_id


def _register_func(name, args_node, fn_scope, return_pairs, bindings, returns, funcs, default_scope):
    params = [a.arg for a in args_node.args]
    has_self = bool(params) and params[0] in ("self", "cls")
    funcs.setdefault(name, []).append(_FuncInfo(params, has_self, fn_scope))
    defaults = args_node.defaults
    if defaults:
        for pname, dflt in zip(params[len(params) - len(defaults):], defaults):
            bindings.setdefault(("var", fn_scope, pname), []).append((dflt, default_scope))
    if return_pairs:
        returns.setdefault(name, []).extend(return_pairs)


def _build_ctx(tree):
    """One whole-file walk collecting EVERY binding construct Python's own
    grammar uses to bind a name — never a gate on whether an occurrence is
    considered, only an input to the union (module docstring rule 2) —
    properly scoped (each `def`/`lambda` is its own scope), plus the
    same-file function/lambda registry needed for call-graph propagation
    (rule 3). A second pass then unions every real call site's actual
    argument, evaluated in the CALLER's scope, into its target's parameter
    binding."""
    parent_scope = _build_parent_scope(tree)
    global_names = {}   # scope_id -> {name, ...} declared global/nonlocal there
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            global_names[id(node)] = _direct_globals(node)

    bindings = {}   # key -> [(value_expr, value_scope), ...]
    returns = {}    # bare func/lambda name -> [(value_expr, value_scope), ...]
    funcs = {}      # bare func/lambda name -> [_FuncInfo, ...]

    def scope_of(node):
        return parent_scope.get(node)

    def var_key(name, scope_id):
        if scope_id is not None and name in global_names.get(scope_id, set()):
            return ("var", None, name)
        return ("var", scope_id, name)

    def target_key(flat_key, scope_id):
        return flat_key if isinstance(flat_key, tuple) else var_key(flat_key, scope_id)

    def add(key, value, value_scope):
        if value is not None:
            bindings.setdefault(key, []).append((value, value_scope))

    # CONTAINER-MUTATION taint (block 01-40 T1, second hostile review) —
    # a SEPARATE substrate from `bindings`, deliberately: `argv.append(eng.
    # ctx.worker_inbox)` / `.extend(...)`/`.insert(i, ...)`/`.add(...)`
    # (sets), and `d[k] = v` subscript-STORE, mutate an EXISTING receiver
    # in place — no assignment target exists for rule 2's aliasing walk to
    # ever see, so `argv`/`env` read as permanently clean once bound, even
    # after a tainted element/value is stored into them. Feeding this into
    # the SAME `bindings` dict as real aliasing binds (Assign `x = y`) was
    # tried and REJECTED (round-1 of this fix): it broke the real tree —
    # `_results.append(some_manifest_derived_summary)` made `_results`
    # itself carry the "manifest" MARKER, and every LATER, unrelated
    # `.append()`/subscript-store on `_results` anywhere in the file was
    # then flagged as a manifest-rooted mutation by the PRE-EXISTING
    # `_CONTAINER_MUTATE_ATTRS`/`_check_manifest_stores` receiver-taint
    # checks — a container that merely COLLECTS manifest-DERIVED VALUES
    # (ordinary, legitimate reporting/iteration code throughout `core/
    # *_rig.py`) is not thereby an ALIAS of the real manifest; MANIFEST's
    # sink checks are specifically about receiver ALIASING (rule 1 seed +
    # rule 4 subscript-read aliasing — a dict/list a real read returned IS
    # still the same mutable object), never about "was some element ever
    # a manifest-derived value". WORKER/OPERATOR taint has no such
    # aliasing meaning to violate — those markers exist to answer "does
    # this expression carry an ingress-channel PATH that could reach a
    # sink", pure content/value flow, which container mutation legitimately
    # is. So: `container_bindings` feeds ONLY {"worker", "operator"} into
    # the taint fixed point (`_compute_taint`), NEVER "manifest" — see its
    # own docstring.
    container_bindings = {}
    module_names = _imported_module_names(tree)

    def add_container(key, value, value_scope):
        if value is not None:
            container_bindings.setdefault(key, []).append((value, value_scope))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            scope_id = scope_of(node)
            for tgt in node.targets:
                for fk in _flatten_bind_targets(tgt):
                    add(target_key(fk, scope_id), node.value, scope_id)
                if isinstance(tgt, ast.Subscript):
                    # `d[k] = v` binds no NEW alias (per
                    # `_flatten_bind_targets`'s own contract, unchanged) —
                    # but the RECEIVER container `d` must union `v`'s
                    # worker/operator taint, or `env["P"] = tainted;
                    # f(env)` reads `env` as clean forever. See
                    # `_container_receiver_key` and `container_bindings`
                    # above for why this is NOT the same substrate as a
                    # real alias-bind.
                    rk = _container_receiver_key(tgt.value)
                    if rk is not None:
                        add_container(target_key(rk, scope_id), node.value, scope_id)
            if (isinstance(node.value, ast.Lambda) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)):
                lam = node.value
                _register_func(node.targets[0].id, lam.args, id(lam),
                                [(lam.body, id(lam))], bindings, returns, funcs, scope_id)
        elif isinstance(node, ast.AugAssign):
            scope_id = scope_of(node)
            for fk in _flatten_bind_targets(node.target):
                add(target_key(fk, scope_id), node.value, scope_id)
            if isinstance(node.target, ast.Subscript):
                rk = _container_receiver_key(node.target.value)
                if rk is not None:
                    add_container(target_key(rk, scope_id), node.value, scope_id)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            scope_id = scope_of(node)
            for fk in _flatten_bind_targets(node.target):
                add(target_key(fk, scope_id), node.value, scope_id)
        elif isinstance(node, ast.NamedExpr):
            scope_id = scope_of(node)
            for fk in _flatten_bind_targets(node.target):
                add(target_key(fk, scope_id), node.value, scope_id)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            scope_id = scope_of(node)
            for fk, val in _destructured_bindings(node.target, node.iter):
                add(target_key(fk, scope_id), val, scope_id)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            scope_id = scope_of(node)
            for item in node.items:
                if item.optional_vars is not None:
                    for fk in _flatten_bind_targets(item.optional_vars):
                        add(target_key(fk, scope_id), item.context_expr, scope_id)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            scope_id = scope_of(node)
            for gen in node.generators:
                for fk, val in _destructured_bindings(gen.target, gen.iter):
                    add(target_key(fk, scope_id), val, scope_id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rets = [(r.value, id(node)) for r in _direct_returns(node) if r.value is not None]
            _register_func(node.name, node.args, id(node), rets, bindings, returns, funcs, scope_of(node))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = _call_target_name(node)

        # ANY method call `recv.METHOD(...)` — THIRD hostile review's
        # finding: an enumerated method-NAME allow-list (`.append`/
        # `.extend`/`.insert`/`.add`/`.update`) is the SAME disease as the
        # binding-shape enumerations that defeated the first three rebuilds
        # of this module — it can only ever be as complete as the last
        # hostile review, and missed `env.setdefault("P", eng.ctx.
        # worker_inbox)`, `env.__setitem__("P", eng.ctx.worker_inbox)`,
        # `.popitem()`/`.pop(k, default)`-writeback, and any future method
        # by construction. Replaced with a STRUCTURAL rule instead of a
        # bigger enumeration: a mutation method's defining trait is that it
        # STORES one of its OWN ARGUMENTS into the receiver — a pure reader
        # like `.get(k)`/`.pop(k)` takes a KEY, never a VALUE it stores —
        # so union EVERY positional/keyword ARGUMENT's taint into the
        # receiver whenever ANY of them carries it, unconditionally,
        # regardless of what the method is named. This covers
        # `.setdefault`/`__setitem__`/`.update`/`.append`/`.extend`/
        # `.insert`/`.add` and every other stdlib mutator BY CONSTRUCTION
        # instead of by name — the same "structural, not enumerated" move
        # rule 3 (CALL PROPAGATION) already made for ordinary value flow
        # through calls. TWO exclusions keep this from over-firing on
        # calls that are not container mutations at all (both verified
        # empirically against the real tree, iteratively — see below):
        #   (a) `fname in funcs` — the call TARGETS a same-file function or
        #       method, REGARDLESS of what the receiver expression is.
        #       `self.react_architect_triage(manifest, inbox_path)` (a
        #       business-logic call from WITHIN the defining class) was the
        #       first false-RED found; narrowing this exclusion to fire only
        #       for a BARE `self`/`cls` receiver was tried next and ALSO
        #       false-REDded — `rs.react(i, manifest, inbox_path)` (the
        #       IDENTICAL same-file method, called on a plain instance
        #       variable from OUTSIDE the class, the ordinary way every
        #       driver in this tree invokes its own reaction object) proved
        #       "self/cls only" was still receiver-shaped, not structural:
        #       ANY object holding a same-file method can be called from ANY
        #       variable name holding it, so the receiver identity carries
        #       no signal at all here. `fname in funcs` alone is the correct
        #       structural boundary — a call whose bare method name matches
        #       a same-file `def` gets its OWN, ALREADY-CORRECT taint
        #       coverage from rule 3's call-graph propagation (this same
        #       loop, just below: the callee's parameters bind to the
        #       caller's actual arguments, and the callee's body/return
        #       taint flows back out) — nothing is lost by excluding such a
        #       call here, only a wrong receiver-MUTATION guess is avoided.
        #       RESIDUAL, honest and currently DORMANT (verified empty
        #       against every file `harness_files()` scans, at the time of
        #       this fix): a genuine container mutation whose method name
        #       COINCIDES with an unrelated same-file function/method of the
        #       identical bare name (`results.append(tainted)` would be
        #       missed if the SAME file also defined ANY function/method
        #       literally named `append`) would be false-GREENed by this
        #       exclusion — the SAME class of bare/unscoped-key collision
        #       this module's `("attr", ...)` substrate already accepts
        #       elsewhere (see module docstring), now extended to `funcs`.
        #       Closing this completely needs real interprocedural type
        #       inference (is the receiver ACTUALLY a dict/list/set, not
        #       just "some object with a matching method name") — out of
        #       reach for an AST-only prover, and not worth taking on given
        #       zero real occurrences today.
        #   (b) the receiver's attribute-chain ROOT resolves to a same-file
        #       `import`-bound name (`os.path.join(...)`, `json.dumps(...)`,
        #       `subprocess.run(...)`) — a module is never legitimately-
        #       mutable aliased state, and without this exclusion the bare/
        #       unscoped `("attr", name)` key space (already a documented
        #       limit — see module docstring) lets ANY tainted `os.path.
        #       dirname(eng.ctx.worker_inbox)`-shaped call ANYWHERE in the
        #       file permanently taint `("attr", "path")`, leaking into
        #       every UNRELATED `os.path.*` call's return by rule 3's own
        #       receiver-taint propagation.
        if isinstance(node.func, ast.Attribute) and fname not in funcs:
            root = _attr_chain_root_name(node.func.value)
            if root not in module_names:
                scope_id = scope_of(node)
                rk = _container_receiver_key(node.func.value)
                if rk is not None:
                    key = target_key(rk, scope_id)
                    for a in node.args:
                        add_container(key, a, scope_id)
                    for kw in node.keywords:
                        add_container(key, kw.value, scope_id)

        if fname is None or fname not in funcs:
            continue
        caller_scope = scope_of(node)
        is_attr_call = isinstance(node.func, ast.Attribute)
        for info in funcs[fname]:
            for idx, pname in enumerate(info.params):
                if is_attr_call and info.has_self and idx == 0:
                    continue   # `self`/`cls` is the receiver (`node.func.value`),
                                # implicit on a bound `instance.method(...)` call —
                                # never an element of `node.args`; binding it to
                                # the caller's first REAL argument would be wrong.
                eff_idx = idx - 1 if (is_attr_call and info.has_self and idx > 0) else idx
                arg = node.args[eff_idx] if 0 <= eff_idx < len(node.args) else None
                if arg is None:
                    arg = next((kw.value for kw in node.keywords if kw.arg == pname), None)
                add(("var", info.scope_id, pname), arg, caller_scope)

    return bindings, returns, container_bindings


def _lookup(bindings, scope, name):
    return bindings.get(("var", scope, name), []) + (
        bindings.get(("var", None, name), []) if scope is not None else [])


# ═══════════════════════════ taint (rules 1-4) ═══════════════════════════

_PASSTHROUGH_ATTR = {ast.UnaryOp: "operand", ast.NamedExpr: "value",
                      ast.Starred: "value", ast.FormattedValue: "value"}


def _union(exprs, nt, rt, bindings, scope):
    k = frozenset()
    for e in exprs:
        k |= _expr_taint(e, nt, rt, bindings, scope)
    return k


def _expr_taint(node, nt, rt, bindings, scope):
    """The set of marker kinds (`"worker"`/`"operator"`/`"manifest"`)
    reachable INTO `node`, evaluated in lexical `scope` — a pure function
    of the CURRENT `nt`/`rt` snapshot (never recurses into what a Name is
    bound to; that indirect link is the fixed point's job in
    `_compute_taint`). Recursion here is bounded by the node's own
    (finite, acyclic) expression tree."""
    if node is None:
        return frozenset()
    t = type(node)
    if t is ast.Attribute:
        own = _INBOX_ATTRS.get(node.attr)
        if own:
            return frozenset({own}) | _expr_taint(node.value, nt, rt, bindings, scope)
        if _is_manifest_name(node.attr):
            return frozenset({"manifest"}) | _expr_taint(node.value, nt, rt, bindings, scope)
        return nt.get(("attr", node.attr), frozenset()) | _expr_taint(node.value, nt, rt, bindings, scope)
    if t is ast.Name:
        base = frozenset({"manifest"}) if _is_manifest_name(node.id) else frozenset()
        k = base | nt.get(("var", scope, node.id), frozenset())
        if scope is not None:
            k |= nt.get(("var", None, node.id), frozenset())
        return k
    if t is ast.Call:
        k = frozenset()
        if isinstance(node.func, ast.Attribute):
            k |= _expr_taint(node.func.value, nt, rt, bindings, scope)
        k |= _union(node.args, nt, rt, bindings, scope) | _union(
            [kw.value for kw in node.keywords], nt, rt, bindings, scope)
        fname = _call_target_name(node)
        if fname is not None:
            k |= rt.get(fname, frozenset())
        # getattr(<obj>, "worker_inbox"/"operator_inbox"/<manifest-ish>) — the
        # LITERAL attr name (itself, or traced through a constant alias via
        # the same union substrate) is a SEED exactly like a real Attribute
        # node, whatever <obj> is.
        if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
            lit = _resolve_str_literal_union(node.args[1], bindings, scope)
            if lit in _INBOX_ATTRS:
                k |= frozenset({_INBOX_ATTRS[lit]})
            elif lit != "<unresolved>" and _is_manifest_name(lit):
                k |= frozenset({"manifest"})
        # A `list()`/`dict()`/`tuple()`/`set()`/`sorted()` constructor, or a
        # `.keys()`/`.values()`/`.items()`/`.copy()` view/copy method,
        # produces a NEW, INDEPENDENT object (Python's own semantics, not a
        # heuristic) — mutating a copy can never bypass the real drain,
        # however manifest-derived its contents are (VALUE propagation
        # stays intact — a fabricated payload built from copied data is
        # still caught; only the MUTATION-TARGET bit drops at this real
        # aliasing boundary). worker/operator never legitimately reach
        # here (the inbox is always a file path, never a dict/list).
        if fname in _COPY_BOUNDARY_NAMES or (
                isinstance(node.func, ast.Attribute) and node.func.attr in _COPY_BOUNDARY_METHODS):
            k = k - {"manifest"}
        return k
    if t is ast.IfExp:
        return _union((node.body, node.orelse, node.test), nt, rt, bindings, scope)
    if t is ast.BoolOp:
        return _union(node.values, nt, rt, bindings, scope)
    if t is ast.BinOp:
        return _union((node.left, node.right), nt, rt, bindings, scope)
    if t in _PASSTHROUGH_ATTR:
        return _expr_taint(getattr(node, _PASSTHROUGH_ATTR[t]), nt, rt, bindings, scope)
    if t is ast.Dict:
        return _union([k for k in node.keys if k is not None], nt, rt, bindings, scope) | \
            _union(node.values, nt, rt, bindings, scope)
    if t in (ast.List, ast.Tuple, ast.Set):
        return _union(node.elts, nt, rt, bindings, scope)
    if t is ast.Subscript:
        return _expr_taint(node.value, nt, rt, bindings, scope)   # rule 4: subscript of tainted => tainted
    if t is ast.JoinedStr:
        return _union(node.values, nt, rt, bindings, scope)
    if t in (ast.ListComp, ast.SetComp, ast.GeneratorExp):
        return _expr_taint(node.elt, nt, rt, bindings, scope) | \
            _union([g.iter for g in node.generators], nt, rt, bindings, scope)
    if t is ast.DictComp:
        return _union((node.key, node.value), nt, rt, bindings, scope) | \
            _union([g.iter for g in node.generators], nt, rt, bindings, scope)
    if t is ast.Lambda:
        return _expr_taint(node.body, nt, rt, bindings, id(node))
    if isinstance(node, ast.Constant):
        return frozenset()
    # conservative fallback: union of any direct expression children —
    # never fewer than a specialized rule would find, per the module's
    # over-approximation guarantee.
    return _union((c for c in ast.iter_child_nodes(node) if isinstance(c, ast.expr)), nt, rt, bindings, scope)


_CONTAINER_MUTATION_KINDS = frozenset({"worker", "operator"})


def _compute_taint(bindings, returns, container_bindings=None):
    """The monotone fixed point (rule 2/3): relax every binding's and every
    function's return taint against the CURRENT snapshot, repeatedly, until
    no key's kind-set grows. Taint only ever gets ADDED — guaranteed to
    terminate (finite keys x finite kinds) and guaranteed, by construction,
    to be an over-approximation of every real taint path in the file.
    `container_bindings` (block 01-40 T1, second hostile review) folds
    into the SAME fixed point, but each of its keys' contribution is
    INTERSECTED with `_CONTAINER_MUTATION_KINDS` ({"worker", "operator"})
    before unioning — never "manifest": a container-MUTATION (`.append`/
    `d[k]=v`/...) is a content-flow relationship ("this container now
    holds a value that carries an ingress-channel path"), not an ALIASING
    one ("this container IS manifest-rooted state") — see
    `_build_ctx`'s own `container_bindings` docstring for why conflating
    the two false-REDs the entire real tree."""
    nt, rt = {}, {}
    container_bindings = container_bindings or {}
    changed = True
    while changed:
        changed = False
        for key, values in bindings.items():
            new = nt.get(key, frozenset())
            for v, vscope in values:
                new = new | _expr_taint(v, nt, rt, bindings, vscope)
            if new != nt.get(key, frozenset()):
                nt[key] = new
                changed = True
        for key, values in container_bindings.items():
            new = nt.get(key, frozenset())
            for v, vscope in values:
                new = new | (_expr_taint(v, nt, rt, bindings, vscope) & _CONTAINER_MUTATION_KINDS)
            if new != nt.get(key, frozenset()):
                nt[key] = new
                changed = True
        for name, values in returns.items():
            new = rt.get(name, frozenset())
            for v, vscope in values:
                new = new | _expr_taint(v, nt, rt, bindings, vscope)
            if new != rt.get(name, frozenset()):
                rt[name] = new
                changed = True
    return nt, rt


# ═══════════════ manifest fixture-local proof (rule 5 refinement) ═══════════════
# A rig that builds its OWN throwaway manifest dict from scratch (`m = {}`)
# and mutates that isn't bypassing any real drain — there is no real drain
# to bypass, since nothing here came from a real engine/ctx (`eng.manifest`,
# `state.load(...)`). Formalizes the module's pre-existing, documented
# exemption ("seeding a scenario's initial `manifest = {...}` whole-dict
# fixture") as a PROOF, not a whitelist: deny by default unless every
# reachable candidate is provably a fresh Dict literal (or a re-binding /
# `.get()`/`.setdefault()`-passthrough of one) — a real attribute READ, a
# same-file helper's return, or anything else unresolvable fails the proof
# and is still denied exactly as before.
#
# RECEIVER-PROVENANCE FIX (block 01-40 T1, round-5 probe3): the Attribute
# branch below used to grant the exemption to ANY `<receiver>.manifest`
# access as long as SOME same-file `self.manifest = {...}`/`Cls.manifest =
# {...}` store existed ANYWHERE in the file — it never checked what
# `<receiver>` itself actually WAS. Since attribute-storage keys are
# deliberately BARE/unscoped (module docstring's documented limit), an
# unrelated class's own `self.manifest = {}` in `__init__` laundered a
# COMPLETELY different, unresolvable receiver's `.manifest` access (a real
# `real_eng` parameter, never locally constructed) into a false exemption —
# a genuine `real_eng.manifest["cases"][case_id]["decision"] = {...}`
# direct-write evaded detection entirely. The exemption now ALSO requires
# the receiver expression itself (`expr.value`) to independently prove
# fixture-local — a Name resolving (through the same union-bindings
# substrate) to a local dict-literal construction, or a call to a SAME-FILE
# class's constructor (`FakeEng()` — see the Call branch's `local_classes`
# check). A parameter with no same-file call-site binding, or one bound to
# anything unresolvable, denies by default exactly like every other
# unresolvable candidate in this proof.

def _is_manifest_fixture_local(expr, nt, rt, bindings, local_classes, scope, depth=0, seen=frozenset()):
    if expr is None or depth > _MAX_DEPTH:
        return False
    if isinstance(expr, ast.Constant):
        return True   # `None`/a literal can never alias a mutable manifest
    if isinstance(expr, ast.Dict):
        # Fixture-local unless it WRAPS a real manifest reference among its
        # values (the `bag = {"m": eng.manifest}` evasion) — any tainted
        # value must ALSO be independently fixture-local (rule 4).
        for v in expr.values:
            if "manifest" in _expr_taint(v, nt, rt, bindings, scope) and \
                    not _is_manifest_fixture_local(v, nt, rt, bindings, local_classes, scope, depth + 1, seen):
                return False
        return True
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        for e in expr.elts:
            if "manifest" in _expr_taint(e, nt, rt, bindings, scope) and \
                    not _is_manifest_fixture_local(e, nt, rt, bindings, local_classes, scope, depth + 1, seen):
                return False
        return True
    if isinstance(expr, ast.Subscript):
        return _is_manifest_fixture_local(expr.value, nt, rt, bindings, local_classes, scope, depth + 1, seen)
    if isinstance(expr, ast.Call):
        # `.get()`/`.setdefault()` on a manifest-rooted receiver is alias-
        # preserving (returns the SAME object, never a copy) — trace into
        # the receiver.
        if isinstance(expr.func, ast.Attribute) and expr.func.attr in ("get", "setdefault"):
            return _is_manifest_fixture_local(expr.func.value, nt, rt, bindings, local_classes, scope, depth + 1, seen)
        # A bare call to a SAME-FILE class's constructor (`FakeEng()`) is
        # itself a fresh, local fixture object — the receiver-provenance
        # fix above needs this to recognize `real_eng = FakeEng()` as a
        # legitimately fixture-local binding. A call to anything else
        # (an imported/real class, a same-file function, an unresolvable
        # callee) is NOT provably fixture-local.
        if isinstance(expr.func, ast.Name) and expr.func.id in local_classes:
            return True
        return False
    if isinstance(expr, ast.Attribute):
        if not _is_manifest_name(expr.attr):
            return False
        if not _is_manifest_fixture_local(expr.value, nt, rt, bindings, local_classes, scope, depth + 1, seen):
            return False
        key = ("attr", expr.attr)
        if key in seen:
            return False
        vals = bindings.get(key, [])
        if not vals:
            return False
        return all(_is_manifest_fixture_local(v, nt, rt, bindings, local_classes, vscope, depth + 1, seen | {key})
                   for v, vscope in vals)
    if isinstance(expr, ast.Name):
        local_key, global_key = ("var", scope, expr.id), ("var", None, expr.id)
        if local_key in seen and global_key in seen:
            return False
        vals = _lookup(bindings, scope, expr.id)
        if not vals:
            return False
        return all(_is_manifest_fixture_local(v, nt, rt, bindings, local_classes, vscope, depth + 1, seen | {local_key, global_key})
                   for v, vscope in vals)
    return False


# ═══════════════════ payload (sender-kind) resolution ═══════════════════
# A SEPARATE substrate from taint: taint answers "does this touch a marker
# at all"; this answers "what concrete dict literal(s) could this payload
# actually be" — expanding through the SAME scoped union bindings/returns
# graph, bounded + cycle-guarded, so a payload reached through indirection
# is judged by EVERY candidate it could be, not the nearest/first one.

def _expand_candidates(expr, bindings, returns, scope, depth=0, seen=frozenset()):
    """-> `[(dict_node_or_None, its_own_scope), ...]` — `its_own_scope` is
    the scope in which THAT candidate's own free names (e.g. a `sender`
    value nested inside it) should themselves be resolved."""
    if expr is None or depth > _MAX_DEPTH:
        return [(None, scope)]
    if isinstance(expr, ast.Dict):
        return [(expr, scope)]
    if isinstance(expr, ast.Name):
        local_key, global_key = ("var", scope, expr.id), ("var", None, expr.id)
        if local_key in seen and global_key in seen:
            return [(None, scope)]
        vals = _lookup(bindings, scope, expr.id)
        if not vals:
            return [(None, scope)]
        out = []
        for v, vscope in vals:
            out.extend(_expand_candidates(v, bindings, returns, vscope, depth + 1,
                                           seen | {local_key, global_key}))
        return out
    if isinstance(expr, ast.Call):
        fname = _call_target_name(expr)
        if fname is None or fname not in returns or fname in seen:
            return [(None, scope)]
        out = []
        for v, vscope in returns[fname]:
            out.extend(_expand_candidates(v, bindings, returns, vscope, depth + 1, seen | {fname}))
        return out if out else [(None, scope)]
    return [(None, scope)]


def _dict_literal_str_value(dict_node, key):
    if not isinstance(dict_node, ast.Dict):
        return None
    for k, v in zip(dict_node.keys, dict_node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                return v.value
            return "<non-literal>"
    return None


def _unwrap_json_dumps(arg):
    """`json.dumps(X) + "\\n"` or `json.dumps(X)` -> `X`; else `arg` as-is."""
    if arg is None:
        return None
    target = arg.left if isinstance(arg, ast.BinOp) else arg
    if (isinstance(target, ast.Call) and isinstance(target.func, ast.Attribute)
            and target.func.attr == "dumps" and target.args):
        return target.args[0]
    return target


def _payload_is_safe(payload_expr, payload_scope, bindings, returns):
    """SAFE iff every candidate the payload can statically resolve to (union
    over the whole file) is a dict literal with no `sender` key, or whose
    `sender` resolves (same expansion, recursively) to `kind == "worker"`
    at EVERY candidate. Any unresolvable/non-literal candidate anywhere in
    the union is UNSAFE — deny by default."""
    candidates = (_expand_candidates(payload_expr, bindings, returns, payload_scope)
                  if payload_expr is not None else [(None, payload_scope)])
    for dict_node, dscope in candidates:
        if not isinstance(dict_node, ast.Dict):
            return False
        sender = None
        for k, v in zip(dict_node.keys, dict_node.values):
            if isinstance(k, ast.Constant) and k.value == "sender":
                sender = v
                break
        if sender is None:
            continue
        sender_candidates = [(sender, dscope)] if isinstance(sender, ast.Dict) else \
            _expand_candidates(sender, bindings, returns, dscope)
        for sd, _ in sender_candidates:
            kind_val = _dict_literal_str_value(sd, "kind") if isinstance(sd, ast.Dict) else "<non-literal>"
            if kind_val != "worker":
                return False
    return True


# ════════════════════════ sink classification (rule 5) ════════════════════════
# A call is in scope ONLY if it matches a recognized WRITE-OPERATION shape —
# a small, stable enumeration of "what physically writes/mutates" (`.write`,
# `json.dump`, `print(file=)`, `os.replace`, ...; exactly rule 5's own list).
# This is NOT the enumeration that defeated the first three rebuilds — THOSE
# enumerated BINDING/ALIASING shapes (how a channel/payload is REACHED),
# which the union-taint substrate above now resolves generically. Write
# OPERATIONS are a different, small, stable axis (Python has a fixed set of
# ways to physically write bytes/mutate a container). Each shape's TARGET
# (never "any touch") is what taint is checked against — this is what keeps
# a shared helper (e.g. a rig's own `ok(name, cond, detail)` assertion
# helper, called throughout a file with unrelated manifest-derived
# diagnostic VALUES that are read, not written) from polluting an unrelated
# `.append()` elsewhere: reading tainted data into a payload is legal (R3
# never forbids reading); only the TARGET resolving to a marker is illegal.
# `ctx.worker_inbox`/`operator_inbox` are always FILE handles, never a
# dict/list a rig `.append()`s to; `manifest` is always an in-memory dict,
# never a file a rig `.write()`s to — each sink shape is checked ONLY
# against the kind(s) it could structurally BE, so a manifest-derived VALUE
# flowing into an unrelated file write never cross-contaminates.
_FILE_KINDS = frozenset({"worker", "operator"})
_MANIFEST_KINDS = frozenset({"manifest"})
_FILE_WRITE_ATTRS = {"write", "writelines", "write_text", "write_bytes"}
_CONTAINER_MUTATE_ATTRS = {"append", "update", "extend", "insert"}
_TARGET_ARG_SINKS = {
    "dump": ("fp",),                 # json.dump(obj, fp)
    "replace": ("dst",),             # os.replace(src, dst)
    "rename": ("dst",),              # os.rename(src, dst)
    "copy": ("dst",),                # shutil.copy(src, dst)
    "copyfile": ("dst",),            # shutil.copyfile(src, dst)
    "move": ("dst",),                # shutil.move(src, dst)
}


def _sink_target(call):
    """`(target_expr, relevant_kinds)` for a recognized sink shape, or
    `(None, frozenset())` if this call is not a write-sink shape at all.
    `name` is the bare call name regardless of whether it was reached as a
    bare `Name` (`dump(...)`) or module-qualified `Attribute`
    (`json.dump(...)`) — the same whole-file bare-name simplification used
    for function/lambda call-graph matching throughout this module."""
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)
    if name is None:
        return None, frozenset()
    if isinstance(func, ast.Attribute) and name in _FILE_WRITE_ATTRS:
        return func.value, _FILE_KINDS
    if isinstance(func, ast.Attribute) and name in _CONTAINER_MUTATE_ATTRS:
        return func.value, _MANIFEST_KINDS
    if name == "print":
        return next((kw.value for kw in call.keywords if kw.arg == "file"), None), _FILE_KINDS
    if name in _TARGET_ARG_SINKS:
        if len(call.args) >= 2:
            return call.args[1], _FILE_KINDS
        kw_names = _TARGET_ARG_SINKS[name]
        return next((kw.value for kw in call.keywords if kw.arg in kw_names), None), _FILE_KINDS
    return None, frozenset()


def _is_open_like(call):
    func = call.func
    return ((isinstance(func, ast.Name) and func.id == "open")
            or (isinstance(func, ast.Attribute) and func.attr == "open"))


def _open_path_arg(call):
    """The path-carrying slot: `path`/`file=` for the 2-arg `open()`/
    `io.open()` convention, or the RECEIVER for the 1-arg
    `<receiver>.open(mode)` convention (the receiver itself is the path)."""
    is_two_arg = ((isinstance(call.func, ast.Name) and call.func.id == "open")
                  or (isinstance(call.func, ast.Attribute) and call.func.attr == "open"
                      and isinstance(call.func.value, ast.Name) and call.func.value.id == "io"))
    if is_two_arg:
        if call.args:
            return call.args[0]
        return next((kw.value for kw in call.keywords if kw.arg == "file"), None)
    return call.func.value


def _resolve_str_literal_union(expr, bindings, scope, depth=0, seen=frozenset()):
    if expr is None or depth > _MAX_DEPTH:
        return "<unresolved>"
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, ast.Name):
        local_key, global_key = ("var", scope, expr.id), ("var", None, expr.id)
        if local_key in seen and global_key in seen:
            return "<unresolved>"
        vals = _lookup(bindings, scope, expr.id)
        if not vals:
            return "<unresolved>"
        lits = {_resolve_str_literal_union(v, bindings, vscope, depth + 1, seen | {local_key, global_key})
                for v, vscope in vals}
        return lits.pop() if len(lits) == 1 else "<unresolved>"
    return "<unresolved>"


def _open_mode(call, bindings, scope):
    """`open(path, mode)` / `io.open(path, mode)` (2-arg convention, path/
    mode via positional OR `file=`/`mode=` kwargs) vs `<receiver>.open(mode)`
    (1-arg convention, the receiver itself IS the path). Mode resolved
    through the same union-alias substrate as everything else — absent
    entirely, the real, provable `open()` default is `"r"`."""
    is_two_arg = ((isinstance(call.func, ast.Name) and call.func.id == "open")
                  or (isinstance(call.func, ast.Attribute) and call.func.attr == "open"
                      and isinstance(call.func.value, ast.Name) and call.func.value.id == "io"))
    if is_two_arg:
        mode_arg = call.args[1] if len(call.args) >= 2 else None
        for kw in call.keywords:
            if kw.arg == "mode" and mode_arg is None:
                mode_arg = kw.value
    else:
        mode_arg = call.args[0] if call.args else next(
            (kw.value for kw in call.keywords if kw.arg == "mode"), None)
    if mode_arg is None:
        return "r"
    return _resolve_str_literal_union(mode_arg, bindings, scope)


def _is_write_mode(mode):
    """DENY BY DEFAULT: unresolved is treated as a possible write."""
    return mode == "<unresolved>" or any(c in mode for c in "wax+")


def _call_touches(call):
    """Every position that could carry a marker: the receiver (a method
    call's target) plus every positional arg and keyword value."""
    touches = []
    if isinstance(call.func, ast.Attribute):
        touches.append(("receiver", call.func.value))
    for a in call.args:
        touches.append(("arg", a))
    for kw in call.keywords:
        touches.append((f"kw:{kw.arg}", kw.value))
    return touches


def _describe_call(call):
    try:
        return f"`{ast.unparse(call.func)}(...)`"
    except Exception:   # noqa: BLE001 — unparse is best-effort for the message only
        return "a call"


def _emit_violation(kind, payload_expr, payload_scope, path, lineno, violations, mechanism, bindings, returns):
    if kind == "operator":
        violations.append(Violation(
            path, lineno, "OPERATOR_INBOX_WRITE",
            f"writes to ctx.operator_inbox via {mechanism} — there is no real operator "
            "transport a rig or driver may use yet (ADR-0012 R8); illegal to write at all, "
            "regardless of payload"))
    elif kind == "manifest":
        violations.append(Violation(
            path, lineno, "MANIFEST_DIRECT_WRITE",
            f"touches manifest-rooted state via {mechanism} directly — bypasses the real "
            "drain (tick -> classify -> router)"))
    elif kind == "worker" and not _payload_is_safe(payload_expr, payload_scope, bindings, returns):
        violations.append(Violation(
            path, lineno, "INBOX_FABRICATED_SENDER",
            f"writes to ctx.worker_inbox via {mechanism} with a payload that cannot be proven "
            'safe — every statically-resolvable candidate must be a dict literal with no '
            '`sender` key, or `sender.kind == "worker"`; denied by default otherwise'))


def _check_calls(tree, nt, rt, bindings, returns, local_classes, parent_scope, path):
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        scope = parent_scope.get(node)
        if _is_open_like(node):
            path_arg = _open_path_arg(node)
            kinds = _expr_taint(path_arg, nt, rt, bindings, scope) if path_arg is not None else frozenset()
            if "operator" in kinds and _is_write_mode(_open_mode(node, bindings, scope)):
                _emit_violation("operator", None, scope, path, node.lineno, violations,
                                 _describe_call(node), bindings, returns)
            continue   # open()/io.open()/.open() never itself the WORKER/manifest sink
        target, relevant_kinds = _sink_target(node)
        if target is None:
            continue
        kinds = _expr_taint(target, nt, rt, bindings, scope) & relevant_kinds
        if "manifest" in kinds and _is_manifest_fixture_local(target, nt, rt, bindings, local_classes, scope):
            kinds = kinds - {"manifest"}
        if not kinds:
            continue
        payload_candidates = [e for role, e in _call_touches(node) if e is not target]
        payload_expr = _unwrap_json_dumps(payload_candidates[0]) if payload_candidates else None
        for kind in sorted(kinds):
            _emit_violation(kind, payload_expr, scope, path, node.lineno, violations,
                             _describe_call(node), bindings, returns)
    violations.extend(_check_subprocess_taint(tree, nt, rt, bindings, returns, parent_scope, path))
    return violations


# ───────────────────────── manifest direct-store ─────────────────────────

def _check_manifest_stores(tree, nt, rt, bindings, local_classes, parent_scope, path):
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        else:
            continue
        scope = parent_scope.get(node)
        for tgt in targets:
            if not (isinstance(tgt, ast.Subscript) and "manifest" in _expr_taint(tgt.value, nt, rt, bindings, scope)):
                continue
            if _is_manifest_fixture_local(tgt.value, nt, rt, bindings, local_classes, scope):
                continue
            try:
                shape = ast.unparse(tgt)
            except Exception:
                shape = "<subscript>"
            violations.append(Violation(
                path, node.lineno, "MANIFEST_DIRECT_WRITE",
                f"assigns into manifest-rooted `{shape}` directly — bypasses the real "
                "drain (tick -> classify -> router)"))
    return violations


# ───────────────────────── subprocess/exec/spawn child-ingress ─────────────────────────
# A child process is a NEW interpreter image — nothing in this file's own
# Python-level taint substrate can see what it does. But the substrate CAN
# see what it was HANDED: any subprocess/os.exec*/os.spawn* call carrying a
# WORKER/OPERATOR-tainted argument (an ingress channel path, or a fabricated
# payload alongside it) is a sink by construction, no shell-redirect syntax
# required — a redirect-gated version of this check missed
# `subprocess.run([sys.executable, "-c", code, protected_path, payload])`
# entirely (no `>`/`>>` in it at all). MANIFEST kind is deliberately excluded
# here (see module docstring's honest-limits section for why, and for the
# TRUE residual this leaves).

_SUBPROC_ATTRS = {"run", "call", "check_call", "check_output", "Popen", "system", "popen"}


def _is_subprocess_like_call(call):
    func = call.func
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            and func.value.id in ("subprocess", "os")):
        return False
    attr = func.attr
    return (attr in _SUBPROC_ATTRS
            or (func.value.id == "os" and (attr.startswith("exec") or attr.startswith("spawn"))))


def _find_dumps_payload(node):
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "dumps" and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "json" and sub.args):
            return sub.args[0]
    return None


# Scoped to worker/operator kinds ONLY, deliberately never manifest: worker/
# operator taint marks an INGRESS FILE PATH — handing that path (plus a
# fabricated payload) to a child is the ingress-escape shape this check
# exists to catch, "a tainted PATH handed to any child is ingress escape by
# construction". Manifest taint marks something structurally different — ANY
# manifest-DERIVED value (rule 4: a subscript READ off tainted state is
# itself tainted), which routinely flows into subprocess argv as ordinary,
# LEGITIMATE data (a case ID read off `gate["merge_case_id"]` passed to
# `land.sh case_id` is exactly this real tree's own pattern, dozens of call
# sites — see `core/casestate_rig.py::run_land` and its siblings across
# nearly every `core/*_rig.py`). Manifest's own DIRECT-WRITE semantics are
# about the TARGET/RECEIVER of a write-like operation being manifest-rooted
# (`_check_calls`'s `_sink_target`, `_check_manifest_stores`'s subscript
# target) — a subprocess call's argv/env has no such "receiver" slot at all,
# only DATA, so that semantic does not transfer here; scoping it in would
# false-RED nearly every real rig's legitimate "read manifest, act on a
# derived scalar" pattern, not catch a new evasion.
def _check_subprocess_taint(tree, nt, rt, bindings, returns, parent_scope, path):
    violations = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_subprocess_like_call(node)):
            continue
        scope = parent_scope.get(node)
        kinds = frozenset()
        for a in node.args:
            kinds |= _expr_taint(a, nt, rt, bindings, scope)
        for kw in node.keywords:
            kinds |= _expr_taint(kw.value, nt, rt, bindings, scope)
        kinds = kinds & {"worker", "operator"}
        if not kinds:
            continue
        payload = _find_dumps_payload(node)
        for kind in sorted(kinds):
            _emit_violation(kind, payload, scope, path, node.lineno, violations,
                             "a subprocess/os.exec/os.spawn call carrying a tainted argument",
                             bindings, returns)
    return violations


# ─────────────────────────────── driver ───────────────────────────────

def lint_file(path):
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    return lint_source(source, path=path)


def _local_class_names(tree):
    """Every same-file `class ...:` name — the receiver-provenance fix
    (manifest fixture-local proof, above) needs this to tell a call to a
    LOCAL test-double constructor (`FakeEng()`) apart from a call to
    anything else (an imported real class, a same-file function, an
    unresolvable callee)."""
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}


def lint_source(source, path="<fixture>"):
    tree = ast.parse(source, filename=path)
    bindings, returns, container_bindings = _build_ctx(tree)
    nt, rt = _compute_taint(bindings, returns, container_bindings)
    parent_scope = _build_parent_scope(tree)
    local_classes = _local_class_names(tree)
    return (_check_calls(tree, nt, rt, bindings, returns, local_classes, parent_scope, path)
            + _check_manifest_stores(tree, nt, rt, bindings, local_classes, parent_scope, path))


class LintResult:
    def __init__(self):
        self.violations_by_file = {}   # rel_path -> [Violation]
        self.stale_known_red = []      # KNOWN_RED entries that came back clean
        self.unlisted_offenders = []   # red rel_paths not in KNOWN_RED

    @property
    def ok(self):
        return not self.stale_known_red and not self.unlisted_offenders


def run(files=None):
    files = files if files is not None else harness_files()
    result = LintResult()
    for path in files:
        rel = os.path.relpath(path, ROOT)
        violations = lint_file(path)
        if violations:
            result.violations_by_file[rel] = violations
    for rel in KNOWN_RED:
        if rel not in result.violations_by_file:
            result.stale_known_red.append(rel)
    for rel in result.violations_by_file:
        if rel not in KNOWN_RED:
            result.unlisted_offenders.append(rel)
    return result


def main():
    result = run()
    for rel, entry in KNOWN_RED.items():
        red = rel in result.violations_by_file
        status = "RED (tracked)" if red else "STALE — now clean, remove from KNOWN_RED"
        print(f"[known-red] {rel}: {status} — owning block {entry['owning_block']}")
        for v in result.violations_by_file.get(rel, []):
            print(f"    {v}")
    for rel in result.unlisted_offenders:
        print(f"[UNLISTED OFFENDER] {rel}:")
        for v in result.violations_by_file[rel]:
            print(f"    {v}")
    ok = result.ok
    print(f"\nr3_lint: {'PASS' if ok else 'FAIL'} "
          f"({len(result.violations_by_file)} file(s) red, "
          f"{len(result.stale_known_red)} stale, {len(result.unlisted_offenders)} unlisted)")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
