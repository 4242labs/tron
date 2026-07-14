#!/usr/bin/env python3
"""r3_honesty_lint_check.py — AC-2 (block 01-40 T1) CI proof.

`core/r3_lint.py` is the R3 honesty lint: a harness may not fabricate a
sender kind the real door (scripts/report.sh) could never produce, write
`ctx.operator_inbox` at all (no real operator transport exists yet), nor
mutate `manifest[...]` state directly. This is the FOURTH rebuild. Rounds
one through three each replaced one finite enumeration (write mechanisms,
then binding shapes) with a bigger finite enumeration, and each time a
hostile review found the next shape outside it — round three's own binding
walk still resolved a USE back to the NEAREST prior binding, which a FOURTH
review broke with if/else and try/except branch shadowing (the nearest
binding is not always the taint-carrying one), `os.path.*`/`str()`
reconstruction (taint didn't propagate through an arbitrary call), `IfExp`/
`BoolOp` (unhandled expression shapes fell through to unresolved-but-
skipped), `AugAssign` as a binding form, and lambda closures. This FOURTH
rebuild replaces resolution entirely with a flow-insensitive TAINT UNION
computed as a monotone fixed point (see `core/r3_lint.py`'s own docstring):
a name is tainted with a marker's kind if ANY binding anywhere in its own
lexical scope carries that kind — never "the nearest one" — so a missed
case can only cause a false RED, never a false GREEN. Proves, live:

  RED (x28)  every evasion the first three hostile reviews produced is
             still caught (10 write-mechanism evasions, 10 further
             write-mechanism evasions, 8 binding-shape evasions — see
             each fixture's own inline comment for what it demonstrates).
  RED (x6)   each of the 6 FOURTH-review evasions is caught: if/else and
             try/except branch shadowing (`dest = eng.ctx.worker_inbox`
             bound in one branch, an inert literal in the other — nearest-
             binding picked the wrong one depending on branch order),
             `AugAssign` as a binding form (`dest = ""; dest +=
             eng.ctx.worker_inbox`), a ternary (`IfExp`) and a `BoolOp`
             (`or`) channel-select, `os.path.dirname`/`basename`/`join`
             path RECONSTRUCTION (taint through a call, not a name alias),
             and a lambda closure (`getdest = lambda: eng.ctx.worker_inbox`).
  GREEN      two legal shapes stay clean: a door-only report (worker sender,
             or no sender key at all — report.sh's own shape) written
             straight, AND the identical "helper indirection" MECHANISM used
             legitimately (a thin same-file wrapper whose every real call
             site sends a safe payload) — proving the lint tells indirection
             APART from a violation, rather than reddening all indirection.
  RED (x1)   the ROUND-5 receiver-provenance evasion (block 01-40 T1, Opus-
             pivot item 3a): an unrelated same-file class's OWN
             `self.manifest = {}` used to launder ANY `<receiver>.manifest`
             access into a false exemption (attribute-storage keys are
             bare/unscoped); the manifest fixture-local proof now ALSO
             requires the receiver itself resolve to a locally-constructed
             fixture — a bare parameter denies by default.
  RED (x1)   the block 01-40 T1 SECOND-PASS hostile-review evasion
             (fixture 36): a plain `subprocess.run([sys.executable, "-c",
             code, protected_path, payload])` — the exact shape the
             runtime guard's own PoC (`core/r3_guard.py`'s "documented
             hole" proof) uses — contains NO `>`/`>>` shell-redirect text
             at all, so the PRIOR redirect-gated subprocess check let it
             through clean, and a PRIOR version of `core/r3_guard.py`'s
             module docstring falsely claimed this whole surface was
             OWNED by that check. Now caught by taint alone (any
             WORKER/OPERATOR-tainted argument to a subprocess/os.exec/
             os.spawn call is a sink, no redirect syntax required).
  PENDING(x2) two ROUND-5 payload-MUTATION PoCs (`payload["sender"] = ...`
             / `.update(...)` AFTER a safe dict literal is authored) are a
             REAL, currently KNOWN-GREEN gap — printed loudly as an
             explicit pending row, not fixed here: the fix is gated on an
             outstanding operator ruling (MODEL A deletes the payload
             prover entirely; MODEL B would extend it to trace mutations).
             (Do not confuse with fixtures 43/44 below — those are a
             CONTAINER-MUTATION taint gap, receiver identity, not payload
             SHAPE; unrelated axis, unrelated fix, already closed.)
  RED (x4)   the block 01-40 T1 SECOND hostile-review's CONTAINER-MUTATION
             evasions (fixtures 37-40): `.append`/`.insert`/`.extend`/a
             `Subscript`-STORE mutating an already-bound `argv`/`env`
             receiver in place, invisible to the taint UNION's binding
             walk until rule 6 (container_bindings) was added.
  RED (x2)   THIS round's finding (fixtures 43/44): `.update()` (dict
             merge) was NOT a container-mutation taint SOURCE at all —
             `env.update({"P": eng.ctx.worker_inbox})` was as ordinary a
             GREEN miss as `.append` for an argv list, same class as the
             four fixtures immediately above, just a different method
             name. `env |= {...}` (fixture 44) is a REGRESSION-confirming
             control, not a new fix — an `AugAssign` to a bare `Name` was
             already routed through the taint union unconditionally,
             before this round, for every operator including `|=`.
  GREEN      an ordinary `.update()`/`|=` whose value carries no
             WORKER/OPERATOR/MANIFEST taint at all stays clean — the fix
             is value-conditioned, never a blanket red on the method name.
  RED (x3)   THE THIRD hostile review's finding (fixtures 45-47): the
             SECOND review's own container-mutation fix (rule 6) was
             ITSELF still an enumerated method-NAME allow-list (`.append`/
             `.extend`/`.insert`/`.add`/`.update`) — `env.setdefault("P",
             eng.ctx.worker_inbox)` and `env.__setitem__("P", eng.ctx.
             worker_inbox)` were a live, two-layer GREEN miss (static AND
             the runtime guard both missed them, since the guard's own
             mechanism does not cross Python-level dict method calls
             either). Replaced the enumeration with a STRUCTURAL rule: ANY
             method call whose receiver resolves to a container-like name
             taints that receiver if ANY of the call's OWN arguments is
             tainted, regardless of method name — covers `.setdefault`/
             `__setitem__`/every other stdlib mutator by construction.
             Fixture 47 (`.popitem()`-writeback) needed NO new mechanism at
             all: once `env` is genuinely tainted (via the ordinary
             subscript-store already covered by rule 6), `env.popitem()`'s
             RETURN is tainted by the PRE-EXISTING rule 3 (a call whose
             RECEIVER is tainted has a tainted return, unconditionally) —
             proof that the fix composes with the rest of the design
             instead of needing its own bespoke case.
  GREEN      `.setdefault`/`.__setitem__`/`.get`/`.pop` whose value carries
             no taint stay clean (value-conditioned, not name-conditioned,
             same guarantee as `.update`/`|=` above) — AND a genuine
             evasion routed through a same-file method call (`self.emit(
             eng, {...})`) stays RED, proving the new rule's `funcs`-
             exclusion (added to stop it false-REDding ordinary business-
             logic method calls whose arguments happen to carry taint,
             e.g. `self.react_architect_triage(manifest, inbox_path)`) does
             not also hide a real evasion — rule 3's OWN call-graph
             propagation still catches it independently.
  GREEN/tree the real `core/` proof-harness tree is clean except the
             explicit, visible KNOWN_RED list (core/sim/operator_proxy.py
             + core/architect_rig.py, at minimum — see core/r3_lint.py's
             KNOWN_RED for the latter's block-01-40-introduced entry) —
             every KNOWN_RED entry is re-verified genuinely red on THIS
             run, never a silent whitelist.
  MECHANISM  the lint's own stale/unlisted detectors fire correctly — a
             known-red entry that has gone clean is caught, and a red file
             missing from KNOWN_RED is caught — proven with synthetic
             KNOWN_RED overrides, never by editing the real list.

The runtime write-guard (`core/r3_guard.py`, block 01-40 T1, Opus-pivot
item 1/2) is a SEPARATE CI proof — `.github/scripts/r3_guard_runtime_check.py`
— covering what this static lint structurally cannot (a genuine OS-level
write landing on a protected path, independent of AST shape/mechanism).

Exit 0 only if every one of the above holds.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "core"))

import r3_lint  # noqa: E402

# ─────────────────── the 10 evasions (each must stay RED) ───────────────────
# Every one of these is a DIRECT rewrite of the SAME violation the original
# lint caught (an operator-sender fabrication into worker_inbox, or a direct
# manifest mutation) — only the SYNTACTIC SHAPE changed. The old lint pattern-
# matched one shape per rule; these proved it caught none of the other nine.

EVASION_FIXTURES = {
    "1_renamed_inbox_path_variable": '''
import json

def bad(eng):
    p = eng.ctx.worker_inbox
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    with open(p, "a") as ib:
        ib.write(json.dumps(rep) + "\\n")
''',
    "2_path_as_file_kwarg": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    with open(file=eng.ctx.worker_inbox, mode="a") as ib:
        ib.write(json.dumps(rep) + "\\n")
''',
    "3_json_dump_to_inbox_handle": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    with open(eng.ctx.worker_inbox, "a") as ib:
        json.dump(rep, ib)
''',
    "4_bare_open_no_with": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    ib = open(eng.ctx.worker_inbox, "a")
    ib.write(json.dumps(rep) + "\\n")
    ib.close()
''',
    "5_helper_function_indirection": '''
import json

def _emit(eng, obj):
    with open(eng.ctx.worker_inbox, "a") as ib:
        ib.write(json.dumps(obj) + "\\n")

def bad(eng):
    _emit(eng, {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}})
''',
    "6_subprocess_shell_append": '''
import json
import subprocess

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    subprocess.run(["bash", "-c", f"echo '{json.dumps(rep)}' >> {eng.ctx.worker_inbox}"])
''',
    "7_manifest_alias": '''
def bad(manifest, case_id, verb):
    m = manifest
    m["cases"][case_id]["decision"] = {"verb": verb}
''',
    "8_depth1_wholesale_overwrite": '''
def bad(manifest, new_cases):
    manifest["cases"] = new_cases
''',
    "9_update_call": '''
def bad(manifest, case_id, decision):
    manifest["cases"][case_id].update({"decision": decision})
''',
    "10_sender_built_via_helper_call": '''
import json

def _build_sender():
    return {"kind": "operator", "id": "x"}

def bad(eng):
    rep = {"tag": "operator.decision", "sender": _build_sender()}
    with open(eng.ctx.worker_inbox, "a") as ib:
        ib.write(json.dumps(rep) + "\\n")
''',

    # ── SECOND-REVIEW evasions (block 01-40 T1, second rebuild) — each one
    #     defeated the FIRST rebuild's enumerated-mechanism design by using
    #     a write/target-resolution SHAPE outside its fixed shape list. ──

    "11_print_file_kwarg": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    with open(eng.ctx.worker_inbox, "a") as ib:
        print(json.dumps(rep), file=ib)
''',

    "12_pathlib_open_chain": '''
import json
import pathlib

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    pathlib.Path(eng.ctx.worker_inbox).open("a").write(json.dumps(rep) + "\\n")
''',

    "13_pathlib_write_text": '''
import json
import pathlib

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    p = pathlib.Path(eng.ctx.worker_inbox)
    existing = p.read_text() if p.exists() else ""
    p.write_text(existing + json.dumps(rep) + "\\n")
''',

    "14_target_path_helper_indirection": '''
import json

def _channel(eng):
    return eng.ctx.worker_inbox

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    dest = _channel(eng)
    with open(dest, "a") as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    "15_getattr_constant_indirection": '''
import json

_CHANNEL_ATTR = "worker_inbox"

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    with open(getattr(eng.ctx, _CHANNEL_ATTR), "a") as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    "16_manifest_wrapped_in_dict": '''
def bad(eng, case_id, verb):
    bag = {"m": eng.manifest}
    bag["m"]["cases"][case_id]["decision"] = {"verb": verb}
''',

    "17_manifest_wrapped_in_list": '''
def bad(eng, case_id, verb):
    refs = [eng.manifest]
    refs[0]["cases"][case_id]["decision"] = {"verb": verb}
''',

    "18_manifest_via_helper_call": '''
def _state(eng):
    return eng.manifest

def bad(eng, case_id, verb):
    _state(eng)["cases"][case_id]["decision"] = {"verb": verb}
''',

    "19_write_tmp_then_rename_onto_inbox": '''
import json
import os

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    tmp = eng.ctx.worker_inbox + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(json.dumps(rep) + "\\n")
    os.replace(tmp, eng.ctx.worker_inbox)
''',

    "20_io_open": '''
import io
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    with io.open(eng.ctx.worker_inbox, "a") as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    # ── THIRD-REVIEW evasions (block 01-40 T1, third rebuild) — each one
    #     defeated the SECOND rebuild's write-mechanism scan not by using an
    #     unrecognized WRITE mechanism, but by using a variable-BINDING
    #     SHAPE `_collect_all_bindings` never recorded at all (tuple/list
    #     unpacking, chained assigns, a for-loop target, walrus, an
    #     attribute target) — so the channel/manifest alias was invisible
    #     to the resolver from the start, never even reaching the
    #     (already-correct) deny-by-default payload/write check. ──

    "21_tuple_unpack_from_helper": '''
import json

def _channel_and_mode(eng):
    return eng.ctx.worker_inbox, "a"

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    path, mode = _channel_and_mode(eng)
    with open(path, mode) as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    "22_tuple_unpack_plain": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    path, mode = eng.ctx.worker_inbox, "a"
    with open(path, mode) as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    "23_manifest_tuple_unpack": '''
def bad(eng, case_id, verb):
    m, _extra = eng.manifest, None
    m["cases"][case_id]["decision"] = {"verb": verb}
''',

    "24_manifest_tuple_container": '''
def bad(eng, case_id, verb):
    refs = (eng.manifest,)
    refs[0]["cases"][case_id]["decision"] = {"verb": verb}
''',

    "25_chained_assignment": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    a = path = eng.ctx.worker_inbox
    with open(path, "a") as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    "26_self_attribute_storage": '''
import json

class Reporter:
    def __init__(self, eng):
        self.dest = eng.ctx.worker_inbox

    def bad(self):
        rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
        with open(self.dest, "a") as fh:
            fh.write(json.dumps(rep) + "\\n")
''',

    "27_for_loop_binding": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    for dest in (eng.ctx.worker_inbox,):
        with open(dest, "a") as fh:
            fh.write(json.dumps(rep) + "\\n")
''',

    "28_walrus_binding": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    if (p := eng.ctx.worker_inbox):
        with open(p, "a") as fh:
            fh.write(json.dumps(rep) + "\\n")
''',

    # ── FOURTH-REVIEW evasions (block 01-40 T1, fourth rebuild) — each one
    #     defeated the THIRD rebuild's generic-binding-walk-but-NEAREST-
    #     WINS resolution: `_nearest_assign_value` picked the textually
    #     nearest/last binding for a name, so an ORDINARY idiom that binds
    #     the SAME name to a tainted value in one place and an inert value
    #     in another (if/else, try/except, AugAssign, a ternary/BoolOp
    #     select, a call-based reconstruction, a lambda closure) could
    #     silently resolve to the wrong — or no — provenance depending on
    #     branch order or unhandled expression shape. ──

    "29_augassign_path_build": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    dest = ""
    dest += eng.ctx.worker_inbox
    with open(dest, "a") as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    "30_ifexp_channel_select": '''
import json

def bad(eng, use_alt=False):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    dest = eng.ctx.worker_inbox if not use_alt else eng.ctx.worker_inbox
    with open(dest, "a") as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    "31_boolor_channel_select": '''
import json

def bad(eng, override=None):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    dest = override or eng.ctx.worker_inbox
    with open(dest, "a") as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    "32_ospath_join_reconstruct": '''
import json, os

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    d = os.path.dirname(eng.ctx.worker_inbox)
    b = os.path.basename(eng.ctx.worker_inbox)
    dest = os.path.join(d, b)
    with open(dest, "a") as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    "33_lambda_closure": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    getdest = lambda: eng.ctx.worker_inbox
    with open(getdest(), "a") as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    "34_try_except_binding": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    try:
        dest = eng.ctx.worker_inbox
    except Exception as e:
        dest = None
    with open(dest, "a") as fh:
        fh.write(json.dumps(rep) + "\\n")
''',

    # ── ROUND-5 evasion (block 01-40 T1, Opus-pivot item 3a/4) — the
    #     manifest fixture-local proof's RECEIVER-PROVENANCE gap: an
    #     UNRELATED same-file class's own `self.manifest = {}` laundered
    #     ANY `<receiver>.manifest` access into a false exemption, because
    #     attribute-storage keys are bare/unscoped and the OLD proof never
    #     checked what the receiver itself resolved to. `real_eng` here is
    #     a plain PARAMETER — never locally constructed, no same-file call
    #     site to resolve it through — so it must DENY by default; only
    #     `FakeEng`'s OWN unrelated `self.manifest = {}` made this look
    #     fixture-local before the fix. ──
    "35_manifest_launder_via_unrelated_fakeeng": '''
class FakeEng:
    def __init__(self):
        self.manifest = {}

def bad(real_eng, case_id, verb):
    real_eng.manifest["cases"][case_id]["decision"] = {"verb": verb}
''',

    # ── block 01-40 T1 SECOND-PASS hostile-review evasion — the FALSE
    #     OWNERSHIP CLAIM PoC: no `>`/`>>` redirect text anywhere in this
    #     call at all (the OLD `_check_subprocess_redirect` gated on
    #     exactly that regex and let this straight through). This is the
    #     runtime guard's own "documented hole" PoC shape
    #     (`subprocess.run([sys.executable, "-c", code, protected_path,
    #     payload])`) — a tainted ingress path handed to a child, argv-only,
    #     zero shell syntax. ──
    "36_subprocess_no_redirect_argv_only": '''
import json
import subprocess
import sys

def bad(eng):
    rep = {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}}
    code = "import sys; open(sys.argv[1], 'a').write(sys.argv[2])"
    subprocess.run([sys.executable, "-c", code, eng.ctx.worker_inbox, json.dumps(rep)])
''',

    # ── block 01-40 T1, SECOND hostile-review evasions — the CONTAINER-
    #     MUTATION taint miss: rule 2's binding forms (Assign/AugAssign/
    #     AnnAssign/NamedExpr/For/With/comprehension/params) never treated
    #     list/dict/set MUTATION (`.append`/`.extend`/`.insert`/`.add`, or
    #     a `Subscript` STORE) as taint-propagating INTO the receiver
    #     container — only a fresh BINDING of the name itself. `argv = [];
    #     argv.append(eng.ctx.worker_inbox); subprocess.run(argv)` read
    #     `argv` as permanently clean, since nothing ever "bound" argv to a
    #     tainted value — the mutation happened to an object the fixed
    #     point had already stopped tracking. Fixed: `.append`/`.extend`/
    #     `.insert`/`.add` calls and `d[k] = v` subscript-stores now UNION
    #     their value's taint into the RECEIVER key, via the identical
    #     union-bindings substrate every other binding form already uses
    #     (see `core/r3_lint.py`'s `_container_receiver_key`). ──
    "37_container_mutation_append": '''
import subprocess

def bad(eng):
    argv = ["cat"]
    argv.append(eng.ctx.worker_inbox)
    subprocess.run(argv)
''',

    "38_container_mutation_insert": '''
import subprocess

def bad(eng):
    argv = ["cat", "-"]
    argv.insert(1, eng.ctx.worker_inbox)
    subprocess.run(argv)
''',

    "39_container_mutation_extend": '''
import subprocess

def bad(eng):
    argv = ["cat"]
    argv.extend([eng.ctx.worker_inbox])
    subprocess.run(argv)
''',

    "40_container_mutation_subscript_store": '''
import os
import subprocess

def bad(eng):
    env = dict(os.environ)
    env["P"] = eng.ctx.worker_inbox
    subprocess.run(["cat"], env=env)
''',

    # ── block 01-40 T1, THIS round's finding — `.update()` (dict merge) is
    #     the SAME container-mutation taint miss as fixtures 37-40 (a
    #     tainted VALUE mutated into an already-bound receiver, never a
    #     fresh binding of the receiver's own name), just via `.update`
    #     instead of `.append`/`.extend`/`.insert`/`.add`/subscript-store —
    #     `env={}; env.update({"P": eng.ctx.worker_inbox});
    #     subprocess.run(env=env)` was as ordinary a GREEN miss as
    #     `.append` for an argv list. ──
    "43_container_mutation_update_dict_literal": '''
import subprocess

def bad(eng):
    env = {}
    env.update({"P": eng.ctx.worker_inbox})
    subprocess.run(["cat"], env=env)
''',

    "44_container_mutation_bitor_augassign": '''
import subprocess

def bad(eng):
    env = {}
    env |= {"P": eng.ctx.worker_inbox}
    subprocess.run(["cat"], env=env)
''',

    # ── block 01-40 T1, THIRD hostile review's finding — the second
    #     hostile review's CONTAINER-MUTATION fix (rule 6) was itself STILL
    #     an enumerated method-NAME allow-list (`.append`/`.extend`/
    #     `.insert`/`.add`/`.update`) — the SAME disease as the binding-
    #     shape enumerations that defeated the first three rebuilds, just
    #     applied one level down. Ordinary dict idioms outside that list —
    #     `.setdefault(k, v)` (stores `v` when `k` is absent),
    #     `.__setitem__(k, v)` (the explicit spelling of `d[k] = v`) — were
    #     a live two-layer GREEN miss (static AND runtime both missed them).
    #     Fixed by replacing the enumeration with a STRUCTURAL rule: ANY
    #     method call whose receiver resolves to a container-like name is a
    #     mutation SOURCE if ANY of its own arguments carries taint,
    #     regardless of the method's name (see `core/r3_lint.py`'s
    #     `_build_ctx`, the "ANY method call" call-graph-loop branch). ──
    "45_container_mutation_setdefault": '''
import subprocess

def bad(eng):
    env = {}
    env.setdefault("P", eng.ctx.worker_inbox)
    subprocess.run(["cat"], env=env)
''',

    "46_container_mutation_dunder_setitem": '''
import subprocess

def bad(eng):
    env = {}
    env.__setitem__("P", eng.ctx.worker_inbox)
    subprocess.run(["cat"], env=env)
''',

    # `.popitem()`-WRITEBACK — not itself a mutation SOURCE (it takes no
    # arguments at all, so there is nothing for the arg-taints-receiver
    # rule to see); this fixture proves the container-mutation SOURCE fix
    # above (fixture 45's `env["P"] = eng.ctx.worker_inbox`, an ordinary
    # subscript-store already covered since rule 6) composes correctly with
    # the PRE-EXISTING rule 3 (CALL PROPAGATION): once `env` itself is
    # genuinely tainted, `env.popitem()` is a call whose RECEIVER is
    # tainted, so its RETURN is unconditionally tainted too — the
    # popped-out `(k, v)` pair, and the fresh `{k: v}` dict built from it,
    # carry the SAME taint straight through to the subprocess sink, with NO
    # additional container-mutation code needed for this direction at all.
    "47_container_mutation_popitem_writeback": '''
import subprocess

def bad(eng):
    env = {}
    env["X"] = "safe"
    env["P"] = eng.ctx.worker_inbox
    k, v = env.popitem()
    subprocess.run(["cat"], env={k: v})
''',
}

# ── ROUND-5 PoCs (Opus design review, pending the operator's MODEL A/B
#     ruling) — two of round-5's four PoCs are payload-MUTATION evasions:
#     the dict literal at the write-sink is safe (no `sender` key) AS
#     AUTHORED, but a fabricated sender is written into it via a POST-
#     CONSTRUCTION mutation (`payload["sender"] = ...` / `.update(...)`)
#     the payload-safety proof — a static proof over a dict literal's own
#     authored keys/values — has no mechanism to see. This is a REAL,
#     currently KNOWN-GREEN gap. It is NOT fixed here: MODEL A (route every
#     rig through scripts/report.sh, delete the payload prover) makes
#     payload SHAPE moot entirely; MODEL B would instead need the prover
#     taught to trace subscript-store/`.update()` mutations forward to
#     every sink that reads the same object. Asserted below as an
#     EXPLICIT, tagged-pending row — never a silent gap — so this suite
#     prints LOUDLY the moment either the ruling lands and ships a fix, or
#     a future rebuild accidentally closes (or widens) this unnoticed.
ROUND5_PENDING_RULING_FIXTURES = {
    "41_pending_payload_subscript_mutation": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision"}
    rep["sender"] = {"kind": "operator", "id": "x"}
    with open(eng.ctx.worker_inbox, "a") as ib:
        ib.write(json.dumps(rep) + "\\n")
''',

    "42_pending_payload_update_mutation": '''
import json

def bad(eng):
    rep = {"tag": "operator.decision"}
    rep.update({"sender": {"kind": "operator", "id": "x"}})
    with open(eng.ctx.worker_inbox, "a") as ib:
        ib.write(json.dumps(rep) + "\\n")
''',
}

# ─────────────────────── legal shapes (must stay GREEN) ───────────────────────

# No-false-RED control for fixture 43/44's fix: an ordinary `.update()`/`|=`
# whose VALUE never carries WORKER/OPERATOR/MANIFEST taint at all must stay
# clean — the fix taints the RECEIVER only when a real marker flows in, never
# unconditionally on sight of the method name.
CLEAN_CONTAINER_UPDATE_FIXTURE = '''
import subprocess

def fine(eng):
    env = {}
    env.update({"PATH": "/usr/bin"})
    env |= {"LANG": "C"}
    subprocess.run(["cat"], env=env)
'''

# No-false-RED control for fixtures 45/46's fix (the generic "any method
# call, any arg tainted" rule): `.setdefault`/`.__setitem__`/`.get`/`.pop`
# with NO worker/operator/manifest-tainted argument at all must stay clean —
# same value-conditioning guarantee as `.update`/`|=` above, now generalized
# to every method name instead of an enumerated few.
CLEAN_CONTAINER_SETDEFAULT_FIXTURE = '''
import subprocess

def fine(eng):
    env = {}
    env.setdefault("PATH", "/usr/bin")
    env.__setitem__("LANG", "C")
    env.get("PATH")
    env.pop("LANG", "C")
    subprocess.run(["cat"], env=env)
'''

# No-false-GREEN control for the `funcs`-exclusion added alongside fixtures
# 45/46 (a call whose bare method name matches a same-file function/method
# is NOT treated as a container mutation, to avoid false-REDding ordinary
# `self.helper(manifest_derived_arg)` business-logic calls — see
# `core/r3_lint.py`'s `_build_ctx` call-graph loop). Proves that exclusion
# does not ALSO hide a genuine evasion: a same-file method that itself
# stores its argument into `ctx.worker_inbox` and writes it must still be
# caught, via ordinary rule 3 CALL PROPAGATION (the excluded call's own
# RETURN/body taint), independent of the container-mutation mechanism
# entirely.
SAMEFILE_METHOD_CALL_STILL_CAUGHT_FIXTURE = '''
import json

class Reporter:
    def emit(self, eng, obj):
        with open(eng.ctx.worker_inbox, "a") as ib:
            ib.write(json.dumps(obj) + "\\n")

    def bad(self, eng):
        self.emit(eng, {"tag": "operator.decision", "sender": {"kind": "operator", "id": "x"}})
'''

# No-false-RED control for the `funcs`-exclusion's OWN iteration: the first
# attempt narrowed it to fire only for a bare `self`/`cls` receiver, which
# immediately false-REDded THIS shape — the identical same-file method
# called on a plain instance variable from OUTSIDE its class (the ordinary
# way a driver invokes its own reaction object; manifest/inbox_path are
# genuinely tainted, and were wrongly read as MUTATING `rs`). Proves the
# final, broader `fname in funcs` exclusion (receiver-agnostic) does not
# regress on this shape.
EXTERNAL_INSTANCE_METHOD_CALL_FIXTURE = '''
class Reactor:
    def react(self, manifest, inbox_path):
        pass

def fine(manifest, inbox_path):
    rs = Reactor()
    rs.react(manifest, inbox_path)
'''

DOOR_ONLY_FIXTURE = '''
from util import append_jsonl


def report_online(tron_ctx, agent_id, branch):
    append_jsonl(tron_ctx.worker_inbox,
                 {"tag": "worker.online", "agent_id": agent_id, "slots": {"branch": branch}})
'''

# The SAME mechanism as evasion #5 (a same-file helper wrapping the actual
# write) — but every real call site sends a safe payload (no `sender` key at
# all, matching core/casestate_rig.py's own real `inject()` helper). Proves
# the lint judges a wrapper by what its call sites ACTUALLY send, not by
# reddening all indirection on sight.
LEGAL_HELPER_INDIRECTION_FIXTURE = '''
from util import append_jsonl


def inject(tron_ctx, obj):
    append_jsonl(tron_ctx.worker_inbox, obj)


def use_it(tron_ctx):
    inject(tron_ctx, {"tag": "operator.decision", "slots": {"case_id": "c1", "verb": "resume"}})
    inject(tron_ctx, {"tag": "operator.decision", "slots": {"case_id": "c2", "verb": "abandon"}})
'''


def main():
    failed = False

    # ── RED x36: every evasion must still be caught ──
    for name, fixture in EVASION_FIXTURES.items():
        violations = r3_lint.lint_source(fixture, path=f"<evasion:{name}>")
        if violations:
            print(f"RED proof confirmed [{name}]: {[str(v) for v in violations]}")
        else:
            print(f"AC-2 REGRESSION: evasion fixture [{name}] was NOT caught "
                  "(expected RED, got GREEN — the lint is fingerprinting a shape again, "
                  "not the illegal class).", file=sys.stderr)
            failed = True

    # ── ROUND-5 pending-ruling PoCs: a VISIBLE open row, never a silent gap.
    #     Currently KNOWN-GREEN (documented, ruling-gated) — printed loudly
    #     either way so nobody has to go looking for this status. ──
    for name, fixture in ROUND5_PENDING_RULING_FIXTURES.items():
        violations = r3_lint.lint_source(fixture, path=f"<round5-pending:{name}>")
        if violations:
            print(f"ROUND-5 PENDING [{name}]: now RED ({[str(v) for v in violations]}) — "
                  "if the Model A/B payload-mutation fix has shipped, move this fixture "
                  "into EVASION_FIXTURES as a required-RED case; otherwise this is an "
                  "unexpected change, investigate.")
        else:
            print(f"ROUND-5 PENDING [{name}]: KNOWN-GREEN-PENDING-RULING confirmed — "
                  "a post-construction payload-mutation fabricated sender is NOT caught "
                  "(documented gap, ruling-gated fix — see core/r3_lint.py's 'payload "
                  "(sender-kind) resolution' docstring section).")

    # ── control: a door-only fixture (real report.sh shape) must be clean ──
    clean_violations = r3_lint.lint_source(DOOR_ONLY_FIXTURE, path="<door-only-fixture>")
    if clean_violations:
        print("AC-2 REGRESSION: a door-only fixture (worker sender, matches "
              f"report.sh's own real shape) was flagged: {[str(v) for v in clean_violations]}",
              file=sys.stderr)
        failed = True
    else:
        print("GREEN proof (fixture) confirmed: a door-only report is clean.")

    # ── control: legal helper indirection (same mechanism as evasion #5,
    #     safe payloads at every real call site) must ALSO be clean ──
    legal_indirection_violations = r3_lint.lint_source(
        LEGAL_HELPER_INDIRECTION_FIXTURE, path="<legal-helper-indirection-fixture>")
    if legal_indirection_violations:
        print("AC-2 REGRESSION: a legitimate same-file helper wrapper (every call site "
              f"sends a safe, sender-less payload) was flagged: "
              f"{[str(v) for v in legal_indirection_violations]}", file=sys.stderr)
        failed = True
    else:
        print("GREEN proof (fixture) confirmed: legal helper indirection (safe payload "
              "at every call site) is clean — the lint judges call sites, not the mere "
              "presence of indirection.")

    # ── control: `.update()`/`|=` with an UNTAINTED value must stay clean —
    #     fixture 43/44's fix taints the receiver only when a real marker
    #     flows in, never unconditionally on sight of the method/operator ──
    clean_update_violations = r3_lint.lint_source(
        CLEAN_CONTAINER_UPDATE_FIXTURE, path="<clean-container-update-fixture>")
    if clean_update_violations:
        print("AC-2 REGRESSION: an ordinary `.update()`/`|=` with no WORKER/OPERATOR/"
              f"MANIFEST-tainted value was flagged: "
              f"{[str(v) for v in clean_update_violations]}", file=sys.stderr)
        failed = True
    else:
        print("GREEN proof (fixture) confirmed: `.update()`/`|=` with an untainted "
              "value stays clean — container-mutation taint is value-conditioned, "
              "not name-conditioned.")

    # ── control: `.setdefault`/`.__setitem__`/`.get`/`.pop` with an
    #     UNTAINTED value must stay clean — fixtures 45/46's fix (the
    #     generic "any method call" rule) is value-conditioned, exactly
    #     like `.update`/`|=` above, now for EVERY method name instead of
    #     an enumerated few. ──
    clean_setdefault_violations = r3_lint.lint_source(
        CLEAN_CONTAINER_SETDEFAULT_FIXTURE, path="<clean-container-setdefault-fixture>")
    if clean_setdefault_violations:
        print("AC-2 REGRESSION: ordinary `.setdefault`/`.__setitem__`/`.get`/`.pop` calls "
              "with no WORKER/OPERATOR/MANIFEST-tainted value were flagged: "
              f"{[str(v) for v in clean_setdefault_violations]}", file=sys.stderr)
        failed = True
    else:
        print("GREEN proof (fixture) confirmed: `.setdefault`/`.__setitem__`/`.get`/`.pop` "
              "with an untainted value stay clean — the generic container-mutation rule "
              "is value-conditioned for ANY method name, not just the previously-"
              "enumerated `.append`/`.extend`/`.insert`/`.add`/`.update`.")

    # ── control: the `funcs`-exclusion added alongside fixtures 45/46 (a
    #     call whose bare method name matches a same-file function/method is
    #     NOT treated as a container mutation, to avoid false-REDding
    #     ordinary `self.helper(manifest_derived_arg)` business-logic calls)
    #     must NOT also hide a genuine evasion routed through such a call —
    #     rule 3's own call-graph propagation (unrelated to container-
    #     mutation taint) must still catch it. ──
    samefile_method_violations = r3_lint.lint_source(
        SAMEFILE_METHOD_CALL_STILL_CAUGHT_FIXTURE, path="<samefile-method-call-fixture>")
    if not samefile_method_violations:
        print("AC-2 REGRESSION: a fabricated-sender payload routed through a same-file "
              "method call (`self.emit(eng, {...})`) was NOT caught — the `funcs`-"
              "exclusion added to keep the container-mutation rule from false-RED-ing "
              "ordinary method calls also hid a real evasion.", file=sys.stderr)
        failed = True
    else:
        print("RED proof confirmed: a fabricated-sender payload routed through a "
              f"same-file method call is still caught: {[str(v) for v in samefile_method_violations]}")

    # ── control: a same-file method called on a PLAIN INSTANCE VARIABLE
    #     (not `self`/`cls`) from outside its own class, with genuinely
    #     tainted arguments, must NOT be misread as a mutation of the
    #     variable holding the instance — the exact shape that broke a
    #     narrower ("self"/"cls"-only) version of the `funcs`-exclusion
    #     during this fix's own development. ──
    external_instance_violations = r3_lint.lint_source(
        EXTERNAL_INSTANCE_METHOD_CALL_FIXTURE, path="<external-instance-method-call-fixture>")
    if external_instance_violations:
        print("AC-2 REGRESSION: a same-file method called on a plain instance variable "
              "(`rs.react(manifest, inbox_path)`) with genuinely tainted arguments was "
              f"misread as a container mutation of `rs`: "
              f"{[str(v) for v in external_instance_violations]}", file=sys.stderr)
        failed = True
    else:
        print("GREEN proof (fixture) confirmed: a same-file method called on a plain "
              "instance variable (not self/cls) with tainted arguments is not misread "
              "as a container mutation of the receiver.")

    # ── GREEN on tree, modulo the explicit KNOWN_RED list ──
    result = r3_lint.run()
    if result.stale_known_red:
        print(f"AC-2 FAILURE: KNOWN_RED entries came back CLEAN (stale — "
              f"remove them, or a real regression hid behind a silent "
              f"whitelist): {result.stale_known_red}", file=sys.stderr)
        failed = True
    if result.unlisted_offenders:
        print(f"AC-2 FAILURE: dishonest harness(es) NOT in the explicit "
              f"KNOWN_RED list: {result.unlisted_offenders}", file=sys.stderr)
        failed = True
    if not result.stale_known_red and not result.unlisted_offenders:
        print("GREEN proof (tree) confirmed: the proof-harness tree is clean "
              f"except the tracked KNOWN_RED set: {sorted(r3_lint.KNOWN_RED)}")

    # ── the named offender is, concretely, red ──
    op_proxy = "core/sim/operator_proxy.py"
    if op_proxy not in result.violations_by_file:
        print(f"AC-2 FAILURE: {op_proxy} (the ADR's named offender) is NOT "
              "flagged red.", file=sys.stderr)
        failed = True
    else:
        print(f"Previously-dishonest rig confirmed RED: {op_proxy} -> "
              f"{[str(v) for v in result.violations_by_file[op_proxy]]}")

    # ── mechanism self-test: stale-entry detection (synthetic KNOWN_RED,
    #     never touches the real list) ──
    orig_known_red = r3_lint.KNOWN_RED
    try:
        r3_lint.KNOWN_RED = dict(orig_known_red)
        r3_lint.KNOWN_RED["core/does_not_exist_rig.py"] = {
            "owning_block": "none", "reason": "synthetic stale-entry self-test"}
        stale_check = r3_lint.run()
        if "core/does_not_exist_rig.py" not in stale_check.stale_known_red:
            print("AC-2 REGRESSION: stale-known-red detection did not fire "
                  "for a synthetic clean-but-listed entry.", file=sys.stderr)
            failed = True
        else:
            print("Mechanism proof confirmed: a stale KNOWN_RED entry is caught.")
    finally:
        r3_lint.KNOWN_RED = orig_known_red

    # ── mechanism self-test: unlisted-offender detection (synthetic) ──
    try:
        r3_lint.KNOWN_RED = {}
        unlisted_check = r3_lint.run()
        if "core/sim/operator_proxy.py" not in unlisted_check.unlisted_offenders:
            print("AC-2 REGRESSION: unlisted-offender detection did not fire "
                  "when KNOWN_RED was emptied.", file=sys.stderr)
            failed = True
        else:
            print("Mechanism proof confirmed: an unlisted offender is caught.")
    finally:
        r3_lint.KNOWN_RED = orig_known_red

    print(f"\nAC-2: {'PASS' if not failed else 'FAIL'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
