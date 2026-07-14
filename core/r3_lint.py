"""r3_lint — R3 honesty lint (ADR-0012 §2 R3 / block 01-40 T1).

The only legal ingress into the engine, in tests too, is the real reporting
door: `scripts/report.sh` writes a JSON line to `ctx.worker_inbox`, hardcoding
`sender.kind: "worker"` — that is the ONLY sender kind the real door can ever
produce. A harness that writes a report claiming any OTHER sender kind into
that same file asserts an identity nothing real produced (R6: "identity is
ambient, not asserted") and proves a channel that does not exist (R8: "the
current harness injects into the worker channel and lies exactly the way the
old rigs lied") — exactly the failure ADR-0012 §1 names ("the proof surface
lied ... proved a channel the live engine never had"). Likewise, a harness
that mutates persisted engine state (`manifest[...]`) directly, instead of
letting the real drain (tick -> classify -> router) apply the effect, skips
the door entirely.

Two illegal-ingress shapes, checked statically (AST) over the proof-harness
surface (`core/*_rig.py`, every module under `core/sim/`):

  INBOX_FABRICATED_SENDER — a dict written to something that looks like the
    inbox file (`open(<path with "inbox">, "a")` + `.write(...)`, or a call
    to `append_jsonl`/`util.append_jsonl` whose first argument mentions
    "inbox") declares `sender.kind` as a string literal other than
    `"worker"`.

  MANIFEST_DIRECT_WRITE — an assignment into a `manifest[...][...]`-shaped
    subscript chain (2+ levels deep, root name containing "manifest"),
    instead of going through the real effect functions.

NOT flagged: calling an internal function directly with a constructed
argument (e.g. `classify.classify(eng, {...}, manifest)` to unit-test
`classify` itself, or seeding a scenario's initial `manifest = {...}` whole-
dict fixture). Those are ordinary whitebox unit tests / fixture setup — they
never claim to drive the real inbox -> drain path, so they cannot lie about
one. Only harnesses that construct what looks like a wire report AND hand it
to the real inbox-file surface are in scope.

Resolution of a write's payload, when it is a bare Name rather than an inline
dict literal, uses a flat, whole-file "last prior assignment of that name"
lookup — not real scope-aware data flow. That is a documented, deliberate
simplification: it is sufficient for every current harness (verified against
the whole `core/` proof surface when this lint was written) and for this
lint's own CI fixtures. A harness deliberately written to defeat it (e.g.
reusing a generic name across unrelated scopes) would need a follow-up rule;
this lint catches the direct, literal violations every current rig actually
writes, not obfuscated ones.
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


def _dict_literal_str_value(dict_node, key):
    """`{key: "literal"}` -> `"literal"`; `None` if absent or non-literal."""
    if not isinstance(dict_node, ast.Dict):
        return None
    for k, v in zip(dict_node.keys, dict_node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                return v.value
            return "<non-literal>"
    return None


def _collect_name_bindings(tree):
    """Flat, whole-file `(lineno, Name, Dict-literal-node)` list, sorted by
    line. See module docstring: a documented simplification, not real
    scope-aware data flow."""
    assigns = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    assigns.append((node.lineno, tgt.id, node.value))
    assigns.sort(key=lambda t: t[0])
    return assigns


def _nearest_binding(assigns, name, before_lineno):
    best = None
    for lineno, nm, dict_node in assigns:
        if nm == name and lineno <= before_lineno:
            best = dict_node
    return best


def _path_mentions_inbox(expr):
    try:
        text = ast.unparse(expr)
    except Exception:
        return False
    return "inbox" in text.lower()


def _open_append_mode(call):
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        return call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def _unwrap_json_dumps(arg):
    """`json.dumps(X) + "\\n"` or `json.dumps(X)` -> `X`; else `arg` as-is."""
    target = arg.left if isinstance(arg, ast.BinOp) else arg
    if (isinstance(target, ast.Call) and isinstance(target.func, ast.Attribute)
            and target.func.attr == "dumps" and target.args):
        return target.args[0]
    return target


def _sender_kind_violation(payload_expr, assigns, path, lineno, violations):
    dict_node = payload_expr
    if isinstance(dict_node, ast.Name):
        dict_node = _nearest_binding(assigns, dict_node.id, lineno)
    if not isinstance(dict_node, ast.Dict):
        return
    sender = None
    for k, v in zip(dict_node.keys, dict_node.values):
        if isinstance(k, ast.Constant) and k.value == "sender":
            sender = v
            break
    if sender is None:
        return  # no sender asserted at all — ambient/implicit, not flagged
    kind = _dict_literal_str_value(sender, "kind")
    if kind is None or kind == "worker":
        return
    violations.append(Violation(
        path, lineno, "INBOX_FABRICATED_SENDER",
        f'writes sender.kind={kind!r} into the inbox file — report.sh (the '
        f'one real door) can only ever emit sender.kind="worker"'))


def _check_inbox_fabricated_sender(tree, path):
    violations = []
    assigns = _collect_name_bindings(tree)

    for node in ast.walk(tree):
        # shape 1: `with open(<path>, "a") as ib: ib.write(<payload>)`
        if isinstance(node, ast.With):
            for item in node.items:
                ctx = item.context_expr
                if not (isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Name)
                        and ctx.func.id == "open"):
                    continue
                if _open_append_mode(ctx) not in ("a", "ab", "a+"):
                    continue
                if not ctx.args or not _path_mentions_inbox(ctx.args[0]):
                    continue
                var = item.optional_vars.id if isinstance(item.optional_vars, ast.Name) else None
                if not var:
                    continue
                for sub in ast.walk(node):
                    if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr == "write" and isinstance(sub.func.value, ast.Name)
                            and sub.func.value.id == var and sub.args):
                        continue
                    payload = _unwrap_json_dumps(sub.args[0])
                    _sender_kind_violation(payload, assigns, path, sub.lineno, violations)

        # shape 2: `append_jsonl(<path>, <payload>)` (util.append_jsonl or bare import)
        if (isinstance(node, ast.Call)
                and ((isinstance(node.func, ast.Name) and node.func.id == "append_jsonl")
                     or (isinstance(node.func, ast.Attribute) and node.func.attr == "append_jsonl"))
                and len(node.args) >= 2):
            if not _path_mentions_inbox(node.args[0]):
                continue
            _sender_kind_violation(node.args[1], assigns, path, node.lineno, violations)

    return violations


def _subscript_root_and_depth(node):
    depth = 0
    cur = node
    while isinstance(cur, ast.Subscript):
        depth += 1
        cur = cur.value
    root_name = None
    if isinstance(cur, ast.Name):
        root_name = cur.id
    elif isinstance(cur, ast.Attribute):
        root_name = cur.attr
    return root_name, depth


def _check_manifest_direct_write(tree, path):
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        else:
            continue
        for tgt in targets:
            if not isinstance(tgt, ast.Subscript):
                continue
            root_name, depth = _subscript_root_and_depth(tgt)
            if depth >= 2 and root_name and "manifest" in root_name.lower():
                violations.append(Violation(
                    path, node.lineno, "MANIFEST_DIRECT_WRITE",
                    f"assigns into {root_name}[...][...] directly (depth={depth}) "
                    f"— bypasses the real drain (tick -> classify -> router)"))
    return violations


def lint_file(path):
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    return lint_source(source, path=path)


def lint_source(source, path="<fixture>"):
    tree = ast.parse(source, filename=path)
    return _check_inbox_fabricated_sender(tree, path) + _check_manifest_direct_write(tree, path)


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
