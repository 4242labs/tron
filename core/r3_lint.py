"""r3_lint — R3 honesty lint (ADR-0012 §2 R3 / block 01-40 T1).

The only legal ingress into the engine, in tests too, is the real reporting
door: `scripts/report.sh` writes a JSON line to `ctx.worker_inbox`, hardcoding
`sender.kind: "worker"` — that is the ONLY sender kind the real door can ever
produce. A harness that writes a report claiming any OTHER sender kind into
that same file asserts an identity nothing real produced (R6: "identity is
ambient, not asserted") and proves a channel that does not exist (R8: "the
current harness injects into the worker channel and lies exactly the way the
old rigs lied"). There is also no real OPERATOR transport yet at all (R8) — a
rig that writes `ctx.operator_inbox` fabricates a channel wholesale. Likewise,
a harness that mutates persisted engine state (`manifest[...]`) directly,
instead of letting the real drain (tick -> classify -> router) apply the
effect, skips the door entirely.

DESIGN (rebuilt, block 01-40 T1 REQUIRED CHANGE 2): the first version of this
lint pattern-matched a small, ENUMERATED set of illegal-write SHAPES (a
specific `open(<path with "inbox">, "a")` + `.write(...)` idiom, a specific
`append_jsonl(...)` call idiom). A hostile review proved 10/10 plain
(non-adversarial) rewrites of the exact same violation defeat shape-matching:
renaming the path variable, passing the path as a `file=` kwarg, writing via
`json.dump` instead of `.write`, opening without `with`, hiding the write
inside a same-file helper function, shelling out with `>>` instead of calling
Python's `open`, aliasing `manifest` to a short name before subscripting it,
overwriting `manifest["cases"]` wholesale at depth 1 instead of depth >= 2,
calling `.update()` instead of assigning a subscript, and building the
`sender` dict via a helper call instead of an inline literal.

The rebuild inverts the default: DENY BY DEFAULT, allow a small, explicit,
statically-provable legal surface — never enumerate illegal shapes and chase
the next rewrite. Concretely:

  1. Any file-write-capable operation (`open(...)` in a write/append mode —
     whether opened with `with` or bound to a bare name, whether the path is
     positional or a `file=` kwarg —, `.write`/`.writelines` on the resulting
     handle, `json.dump` to it, or an equivalent `subprocess`/`os.system`
     shell command containing a `>`/`>>` redirect) whose TARGET resolves,
     via a whole-file "nearest prior assignment" alias trace (see below), to
     `ctx.worker_inbox` or `ctx.operator_inbox` — OR the recognized
     `append_jsonl(path, obj)` primitive called with such a target — is
     IN SCOPE, regardless of which function in the file it lives inside
     (this is exactly what closes the "helper-function indirection" evasion:
     detection is whole-file and mechanism-based, never tied to a specific
     call site or enclosing function name).

  2. Within scope, `ctx.operator_inbox` is ALWAYS illegal
     (`OPERATOR_INBOX_WRITE`) — there is no real operator transport a rig or
     driver may legitimately use yet (R8), so no payload shape makes this
     legal.

  3. Within scope, `ctx.worker_inbox` is legal ONLY if the write's JSON
     payload is a statically-resolvable dict literal that either carries NO
     `sender` key at all (ambient — the shape `scripts/report.sh`'s own
     free-text/structured lines and `core.sim.live`'s courier fallback both
     use) or carries `sender.kind` as the string literal `"worker"`. ANY
     other outcome — a literal non-"worker" kind, OR a `sender`/payload that
     cannot be resolved to a literal at all (a helper-call result, an
     unresolved name, a dict built through indirection) — is DENIED
     (`INBOX_FABRICATED_SENDER`). Denying the unresolvable case (rather than
     only the provably-bad case) is the deliberate inversion: it closes
     "sender built via helper call" without needing to understand what the
     helper does.

  4. `manifest[...]` direct-write is unchanged in kind but alias-aware: any
     assignment (or `AugAssign`, or `.update()` call) into a subscript chain
     — of ANY depth (>= 1, not >= 2) — whose ROOT resolves, via the SAME
     whole-file alias trace, to a name literally containing "manifest" (a
     bare `manifest` reference, an attribute ending in `.manifest`, or an
     alias of either assigned earlier in the file: `m = eng.manifest`) is
     `MANIFEST_DIRECT_WRITE`.

Two illegal-ingress classes remain the visible violation vocabulary
(`INBOX_FABRICATED_SENDER` + `OPERATOR_INBOX_WRITE` for the reporting door;
`MANIFEST_DIRECT_WRITE` for direct state mutation), matching R3's own
framing — only the DETECTION underneath them was rebuilt.

NOT flagged: calling an internal function directly with a constructed
argument (e.g. `classify.classify(eng, {...}, manifest)` to unit-test
`classify` itself, or seeding a scenario's initial `manifest = {...}`
whole-dict fixture, or reading `manifest[...]`/`ctx.worker_inbox` anywhere).
Only a WRITE-capable operation whose target resolves to ingress state is in
scope — ordinary whitebox unit tests and fixture setup never claim to drive
the real inbox -> drain path, so they cannot lie about one.

REAL, HONESTLY-DISCLOSED REMAINING LIMITS (not closed by this rebuild):

  - Alias/name resolution is a flat, whole-file "nearest prior assignment
    before this line" walk — NOT real scope-aware/interprocedural data flow.
    A function PARAMETER named `manifest` is treated as tainted by its
    literal name (not by call-graph analysis of what's passed in); a
    parameter with some OTHER name that receives `ctx.worker_inbox` from a
    caller is invisible to this lint (no cross-function taint). This is
    sufficient for every current harness (re-verified against the whole
    `core/` proof surface + the 10 adversarial fixtures below when this
    rebuild landed) but is not a general dataflow prover.
  - The recognized ingress-state markers are exactly `worker_inbox`,
    `operator_inbox`, and `manifest` — the concrete real doors/state this
    ADR names. Other `ctx` fields the engine also owns and appends to
    (`event_log`, `home_log`, `message_log`, ...) are NOT covered; a rig
    writing directly to one of those would not be caught by this lint.
  - The subprocess/shell-redirect check is a textual/AST pattern match for a
    `>`/`>>` operator plus an ingress-marker reference inside a
    `subprocess.*`/`os.system`/`os.popen` call — it is not a shell parser
    (e.g. redirects hidden behind further indirection, like a `.sh` script
    file the rig writes and then executes, are out of scope).
  - This is a static AST lint, not a dynamic/runtime enforcement layer — a
    sufficiently obfuscated adversarial rewrite (e.g. `getattr`/`exec`-based
    indirection) can still defeat static analysis in principle. The design
    goal is to catch the ILLEGAL CLASS as it is actually written by a
    developer trying to pass CI, not to be a covert-channel-proof sandbox.
"""
import ast
import glob
import os
import re

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


# ─────────────────────────── shared alias tracing ───────────────────────────
# Every trace below is the SAME documented simplification: a flat,
# whole-file, line-ordered "nearest prior binding" walk — not real
# scope-aware data flow (see module docstring).

def _dict_literal_str_value(dict_node, key):
    """`{key: "literal"}` -> `"literal"`; `None` if absent, `"<non-literal>"`
    if present but not a string constant."""
    if not isinstance(dict_node, ast.Dict):
        return None
    for k, v in zip(dict_node.keys, dict_node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                return v.value
            return "<non-literal>"
    return None


def _collect_dict_bindings(tree):
    """Flat, whole-file `(lineno, Name, Dict-literal-node)` list, sorted by
    line — resolves a bare Name payload/sender back to its dict literal."""
    assigns = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    assigns.append((node.lineno, tgt.id, node.value))
    assigns.sort(key=lambda t: t[0])
    return assigns


def _nearest_binding(bindings, name, before_lineno):
    best = None
    for lineno, nm, node in bindings:
        if nm == name and lineno <= before_lineno:
            best = node
    return best


def _build_parent_function_map(tree):
    """AST node -> its nearest enclosing `ast.FunctionDef` (or `None` at
    module level). Powers the bounded, same-file call-site trace below —
    NOT a general interprocedural analysis (see module docstring)."""
    parent_func = {}

    def visit(node, current_func):
        parent_func[node] = current_func
        nxt = node if isinstance(node, ast.FunctionDef) else current_func
        for child in ast.iter_child_nodes(node):
            visit(child, nxt)

    visit(tree, None)
    return parent_func


_MAX_INDIRECTION_DEPTH = 3


def _param_index(funcdef, name):
    for i, a in enumerate(funcdef.args.args):
        if a.arg == name:
            return i
    return None


def _call_arg_for_param(call, idx, name):
    if idx < len(call.args):
        return call.args[idx]
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _resolve_payload_dicts(expr, dict_bindings, lineno, parent_func, tree, depth=0):
    """Resolve a payload expression to `[(dict_node_or_None, effective_lineno), ...]`
    — normally one candidate. Closes the "helper-function indirection"
    evasion for the specific shape it actually takes in this codebase: a
    same-file helper whose payload argument is a bare pass-through
    parameter (`def inject(obj): append_jsonl(path, obj)`), never itself
    locally bound to a dict literal. Rather than declaring every such
    parameter unresolvable (which would falsely redden every legitimate
    thin wrapper), this walks every call site of the enclosing function
    (exact name match, same file) and resolves what was ACTUALLY passed
    there, recursively (bounded depth) — so a wrapper is judged by what
    every one of its call sites really sends, not by its own signature."""
    if isinstance(expr, ast.Dict):
        return [(expr, lineno)]
    if isinstance(expr, ast.Name):
        direct = _nearest_binding(dict_bindings, expr.id, lineno)
        if direct is not None:
            return [(direct, lineno)]
        if depth < _MAX_INDIRECTION_DEPTH:
            enclosing = parent_func.get(expr)
            if enclosing is not None:
                idx = _param_index(enclosing, expr.id)
                if idx is not None:
                    sites = [n for n in ast.walk(tree)
                             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == enclosing.name]
                    if sites:
                        out = []
                        for call in sites:
                            arg = _call_arg_for_param(call, idx, expr.id)
                            if arg is None:
                                out.append((None, call.lineno))
                            else:
                                out.extend(_resolve_payload_dicts(
                                    arg, dict_bindings, call.lineno, parent_func, tree, depth + 1))
                        return out
        return [(None, lineno)]
    return [(None, lineno)]


def _unwrap_json_dumps(arg):
    """`json.dumps(X) + "\\n"` or `json.dumps(X)` -> `X`; else `arg` as-is."""
    if arg is None:
        return None
    target = arg.left if isinstance(arg, ast.BinOp) else arg
    if (isinstance(target, ast.Call) and isinstance(target.func, ast.Attribute)
            and target.func.attr == "dumps" and target.args):
        return target.args[0]
    return target


def _classify_path_expr(expr, path_bindings, before_lineno):
    """Does `expr` resolve to `ctx.worker_inbox` / `ctx.operator_inbox`
    (directly, or via a traced alias)? Returns "worker" / "operator" / None.
    Falls back to a textual match ONLY as a last resort (documented in the
    module docstring) — the primary mechanism is the alias trace, which is
    what actually defeats a renamed variable."""
    if expr is None:
        return None
    if isinstance(expr, ast.Attribute):
        if expr.attr == "worker_inbox":
            return "worker"
        if expr.attr == "operator_inbox":
            return "operator"
    if isinstance(expr, ast.Name):
        best = None
        for lineno, nm, kind in path_bindings:
            if nm == expr.id and lineno <= before_lineno:
                best = kind
        if best:
            return best
        return None
    try:
        text = ast.unparse(expr).lower()
    except Exception:
        return None
    if "worker_inbox" in text or "worker-inbox" in text:
        return "worker"
    if "operator_inbox" in text or "operator-inbox" in text:
        return "operator"
    if "inbox" in text:
        return "worker"
    return None


def _collect_path_bindings(tree):
    """`(lineno, Name, "worker"|"operator")` list: names assigned (anywhere
    in the file, single-hop-per-pass but processed in line order, so chains
    like `p = ctx.worker_inbox; q = p` resolve in one forward sweep) from an
    inbox-path-shaped expression."""
    bindings = []
    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)]
    assigns.sort(key=lambda n: n.lineno)
    for node in assigns:
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        kind = _classify_path_expr(node.value, bindings, node.lineno)
        if kind:
            bindings.append((node.lineno, node.targets[0].id, kind))
    return bindings


def _open_call_path_mode(call):
    """`open(<path>, <mode>)` — path/mode resolved from EITHER positional
    args OR `file=`/`mode=` kwargs (closes the kwarg-only evasion)."""
    path_arg = call.args[0] if len(call.args) >= 1 else None
    mode_arg = call.args[1] if len(call.args) >= 2 else None
    for kw in call.keywords:
        if kw.arg == "file" and path_arg is None:
            path_arg = kw.value
        if kw.arg == "mode" and mode_arg is None:
            mode_arg = kw.value
    if mode_arg is None:
        mode = "r"          # open()'s own default
    elif isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
        mode = mode_arg.value
    else:
        mode = "<non-literal>"
    return path_arg, mode


def _is_write_mode(mode):
    return isinstance(mode, str) and any(c in mode for c in "wax+")


def _is_open_call(node):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"


def _collect_handle_bindings(tree, path_bindings):
    """`(lineno, Name, "worker"|"operator")` for a file HANDLE bound to a
    write-capable `open(<inbox path>, ...)` — via `with ... as X:` OR a bare
    `X = open(...)` (closes the "no `with`" evasion; both shapes covered by
    a single scan)."""
    events = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            if not _is_open_call(node.value):
                continue
            path_arg, mode = _open_call_path_mode(node.value)
            if not _is_write_mode(mode):
                continue
            kind = _classify_path_expr(path_arg, path_bindings, node.lineno)
            if kind:
                events.append((node.lineno, node.targets[0].id, kind))
        elif isinstance(node, ast.With):
            for item in node.items:
                if not _is_open_call(item.context_expr):
                    continue
                if not isinstance(item.optional_vars, ast.Name):
                    continue
                path_arg, mode = _open_call_path_mode(item.context_expr)
                if not _is_write_mode(mode):
                    continue
                kind = _classify_path_expr(path_arg, path_bindings, node.lineno)
                if kind:
                    events.append((node.lineno, item.optional_vars.id, kind))
    events.sort(key=lambda t: t[0])
    return events


def _resolve_handle_kind(expr, handle_bindings, path_bindings, before_lineno):
    """The object a `.write`/`.writelines`/`json.dump` call targets: a
    traced handle Name, OR an inline `open(<inbox path>, <write mode>)`
    (the chained-call shape, no intermediate variable at all)."""
    if isinstance(expr, ast.Name):
        best = None
        for lineno, nm, kind in handle_bindings:
            if nm == expr.id and lineno <= before_lineno:
                best = kind
        return best
    if _is_open_call(expr):
        path_arg, mode = _open_call_path_mode(expr)
        if _is_write_mode(mode):
            return _classify_path_expr(path_arg, path_bindings, before_lineno)
    return None


_SUBPROC_ATTRS = {"run", "call", "check_call", "check_output", "Popen", "system", "popen"}


def _is_subprocess_like_call(call):
    func = call.func
    return (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            and func.value.id in ("subprocess", "os") and func.attr in _SUBPROC_ATTRS)


_REDIRECT_RE = re.compile(r">>|(?<!-)>(?!=)")


def _find_dumps_payload(node):
    """The first `json.dumps(X)` call anywhere inside `node`'s subtree ->
    `X`; used to recover a payload embedded in a shelled-out command
    string."""
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "dumps" and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "json" and sub.args):
            return sub.args[0]
    return None


def _emit_channel_violation(kind, payload_expr, dict_bindings, path, lineno, violations, mechanism,
                             parent_func, tree):
    if kind == "operator":
        violations.append(Violation(
            path, lineno, "OPERATOR_INBOX_WRITE",
            f"writes to ctx.operator_inbox via {mechanism} — there is no real operator "
            "transport a rig or driver may use yet (ADR-0012 R8); this channel is illegal "
            "to write at all, regardless of payload"))
        return
    # kind == "worker"
    candidates = (_resolve_payload_dicts(payload_expr, dict_bindings, lineno, parent_func, tree)
                  if payload_expr is not None else [(None, lineno)])
    for dict_node, at_lineno in candidates:
        if not isinstance(dict_node, ast.Dict):
            violations.append(Violation(
                path, at_lineno, "INBOX_FABRICATED_SENDER",
                f"writes to ctx.worker_inbox via {mechanism} with a payload that is not a "
                "statically-resolvable dict literal — cannot verify sender.kind, denied by "
                "default (see module docstring: this is the deliberate deny-unless-provable "
                "inversion, not a false positive on an unrelated write)"))
            continue
        sender = None
        for k, v in zip(dict_node.keys, dict_node.values):
            if isinstance(k, ast.Constant) and k.value == "sender":
                sender = v
                break
        if sender is None:
            continue  # no sender asserted — ambient/implicit, matches report.sh's own shape
        sender_dict = sender
        if isinstance(sender_dict, ast.Name):
            sender_dict = _nearest_binding(dict_bindings, sender_dict.id, at_lineno)
        kind_val = (_dict_literal_str_value(sender_dict, "kind")
                    if isinstance(sender_dict, ast.Dict) else "<non-literal>")
        if kind_val == "worker":
            continue
        violations.append(Violation(
            path, at_lineno, "INBOX_FABRICATED_SENDER",
            f'writes to ctx.worker_inbox via {mechanism} asserting sender.kind={kind_val!r} — '
            f'report.sh (the one real door) can only ever emit sender.kind="worker"'))


def _check_inbox_writes(tree, dict_bindings, path_bindings, handle_bindings, path, parent_func):
    violations = []
    for node in ast.walk(tree):
        # shape A: `<handle>.write(...)` / `.writelines(...)` — traced
        # handle OR an inline `open(<path>, <mode>).write(...)` chain.
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("write", "writelines")):
            kind = _resolve_handle_kind(node.func.value, handle_bindings, path_bindings, node.lineno)
            if kind:
                payload = _unwrap_json_dumps(node.args[0]) if node.args else None
                _emit_channel_violation(kind, payload, dict_bindings, path, node.lineno,
                                         violations, "a raw open()/.write()", parent_func, tree)

        # shape B: `json.dump(<obj>, <handle>)`.
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "dump" and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "json"):
            obj_arg = node.args[0] if len(node.args) >= 1 else next(
                (kw.value for kw in node.keywords if kw.arg == "obj"), None)
            fp_arg = node.args[1] if len(node.args) >= 2 else next(
                (kw.value for kw in node.keywords if kw.arg == "fp"), None)
            kind = _resolve_handle_kind(fp_arg, handle_bindings, path_bindings, node.lineno) if fp_arg else None
            if kind:
                _emit_channel_violation(kind, obj_arg, dict_bindings, path, node.lineno,
                                         violations, "json.dump()", parent_func, tree)

        # shape C: `append_jsonl(<path>, <obj>)` — the recognized real
        # primitive; still checked, since the DOOR itself can be called
        # with an illegal target/payload.
        if (isinstance(node, ast.Call)
                and ((isinstance(node.func, ast.Name) and node.func.id == "append_jsonl")
                     or (isinstance(node.func, ast.Attribute) and node.func.attr == "append_jsonl"))):
            path_arg = node.args[0] if len(node.args) >= 1 else next(
                (kw.value for kw in node.keywords if kw.arg == "path"), None)
            payload_arg = node.args[1] if len(node.args) >= 2 else next(
                (kw.value for kw in node.keywords if kw.arg == "obj"), None)
            kind = _classify_path_expr(path_arg, path_bindings, node.lineno) if path_arg is not None else None
            if kind:
                _emit_channel_violation(kind, payload_arg, dict_bindings, path, node.lineno,
                                         violations, "append_jsonl()", parent_func, tree)

        # shape D: a shelled-out `subprocess`/`os.system` command containing
        # a `>`/`>>` redirect into an inbox-shaped target — never a real
        # production shape (report.sh is always invoked via argv, never
        # shell-redirected into).
        if isinstance(node, ast.Call) and _is_subprocess_like_call(node):
            try:
                text = ast.unparse(node)
            except Exception:
                continue
            if not _REDIRECT_RE.search(text):
                continue
            low = text.lower()
            if "operator_inbox" in low or "operator-inbox" in low:
                kind = "operator"
            elif "worker_inbox" in low or "worker-inbox" in low or "inbox" in low:
                kind = "worker"
            else:
                kind = None
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name):
                        for lineno, nm, k in path_bindings:
                            if nm == sub.id and lineno <= node.lineno:
                                kind = k
                if kind is None:
                    continue
            payload = _find_dumps_payload(node)
            _emit_channel_violation(kind, payload, dict_bindings, path, node.lineno,
                                     violations, "a shelled-out subprocess redirect (>>/>)",
                                     parent_func, tree)
    return violations


# ─────────────────────────── manifest direct-write ───────────────────────────

def _is_direct_manifest_ref(node):
    if isinstance(node, ast.Name):
        return "manifest" in node.id.lower()
    if isinstance(node, ast.Attribute):
        return "manifest" in node.attr.lower()
    return False


def _manifest_rooted(expr, manifest_bindings, before_lineno):
    """Is `expr` (an assignment target, or the object of a `.update()`
    call) rooted at a manifest reference — literal `manifest`, `<x>.
    manifest`, or a traced alias of either (`m = eng.manifest`, `cases =
    manifest["cases"]`, `q = m`)? Subscripts are unwound to find the root;
    any depth >= 1 counts (closes the "depth-1 wholesale overwrite"
    evasion — the OLD lint required depth >= 2)."""
    cur = expr
    while isinstance(cur, ast.Subscript):
        cur = cur.value
    if _is_direct_manifest_ref(cur):
        return True
    if isinstance(cur, ast.Name):
        for lineno, nm in manifest_bindings:
            if nm == cur.id and lineno <= before_lineno:
                return True
    return False


def _collect_manifest_bindings(tree):
    bindings = []
    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)]
    assigns.sort(key=lambda n: n.lineno)
    for node in assigns:
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if _manifest_rooted(node.value, bindings, node.lineno):
            bindings.append((node.lineno, node.targets[0].id))
    return bindings


def _check_manifest_direct_write(tree, manifest_bindings, path):
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        else:
            targets = None
        if targets:
            for tgt in targets:
                if isinstance(tgt, ast.Subscript) and _manifest_rooted(tgt, manifest_bindings, node.lineno):
                    try:
                        shape = ast.unparse(tgt)
                    except Exception:
                        shape = "<subscript>"
                    violations.append(Violation(
                        path, node.lineno, "MANIFEST_DIRECT_WRITE",
                        f"assigns into manifest-rooted `{shape}` directly — bypasses the "
                        "real drain (tick -> classify -> router)"))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "update" and _manifest_rooted(node.func.value, manifest_bindings, node.lineno)):
            try:
                shape = ast.unparse(node.func.value)
            except Exception:
                shape = "<expr>"
            violations.append(Violation(
                path, node.lineno, "MANIFEST_DIRECT_WRITE",
                f"calls `.update()` on manifest-rooted `{shape}` directly — bypasses the "
                "real drain (tick -> classify -> router)"))
    return violations


# ─────────────────────────────── driver ───────────────────────────────

def lint_file(path):
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    return lint_source(source, path=path)


def lint_source(source, path="<fixture>"):
    tree = ast.parse(source, filename=path)
    dict_bindings = _collect_dict_bindings(tree)
    path_bindings = _collect_path_bindings(tree)
    handle_bindings = _collect_handle_bindings(tree, path_bindings)
    manifest_bindings = _collect_manifest_bindings(tree)
    parent_func = _build_parent_function_map(tree)
    return (_check_inbox_writes(tree, dict_bindings, path_bindings, handle_bindings, path, parent_func)
            + _check_manifest_direct_write(tree, manifest_bindings, path))


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
