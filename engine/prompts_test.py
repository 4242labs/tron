"""prompts_test — AC test:pmt-registry (block 01-02).

Exercises the PMT layer against the real canon prompts/ folder:
  - the registry resolves each id to a self-contained file that exists;
  - every messages.yaml worker line references a known PMT id (closed + total);
  - load() resolves an id (never a path) and fills slots;
  - load() reads FRESH each call (imported at tick — an edit takes effect immediately);
  - load() fails loud on an unknown id and on a missing slot.

Run: python3 engine/prompts_test.py   (exit 0 = pass). No tokens, no network.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import util                         # noqa: E402
from prompts import Prompts, UnknownPrompt  # noqa: E402


class _Ctx:
    """Minimal ctx: just the paths the prompt layer reads."""
    def __init__(self, root):
        self.dir = root
        self.prompts_dir = os.path.join(root, "prompts")
        self.prompts_registry = os.path.join(root, "prompts", "registry.yaml")
        self.messages = os.path.join(root, "messages.yaml")


def main():
    root = os.path.dirname(HERE)              # the canon instance (repo root)
    ctx = _Ctx(root)
    p = Prompts(ctx)
    reg = (util.load_yaml(ctx.prompts_registry) or {}).get("prompts", {})
    assert reg, "registry has no prompts"

    # 1) every registry id resolves to a self-contained file that exists.
    for pid, spec in reg.items():
        f = os.path.join(ctx.prompts_dir, spec["file"])
        assert os.path.exists(f), f"{pid}: file missing {spec['file']}"

    # 2) every worker-channel message references a known PMT id (closed + total).
    msgs = (util.load_yaml(ctx.messages) or {}).get("templates", {})
    for mid, tpl in msgs.items():
        if (tpl or {}).get("channel") != "worker":
            continue
        pid = (tpl or {}).get("pmt")
        assert pid, f"worker message {mid} has no pmt ref"
        assert pid in reg, f"worker message {mid} -> unknown PMT {pid}"
        # the message's declared slots must match the registry's.
        assert set(tpl.get("slots", [])) == set(reg[pid].get("slots", [])), \
            f"{mid}: slot mismatch vs {pid}"

    # 3) load() resolves an id and fills slots.
    out = p.load("PMT-ENG-BRIEF", {"worker_id": "ENG-01-02", "block": "01-02", "branch": "feat/x"})
    assert "ENG-01-02" in out and "01-02" in out and "feat/x" in out, "slots not filled"

    # 4) fresh read: edit a temp PMT, load twice, second call sees the change.
    with tempfile.TemporaryDirectory() as td:
        pdir = os.path.join(td, "prompts")
        os.makedirs(pdir)
        util.atomic_write(os.path.join(pdir, "registry.yaml"),
                          "prompts:\n  PMT-TMP: { file: PMT-TMP.md, slots: [x] }\n")
        fp = os.path.join(pdir, "PMT-TMP.md")
        tctx = _Ctx(td)
        util.atomic_write(fp, "first {x}")
        assert p2_load(tctx, "PMT-TMP", {"x": "A"}) == "first A"
        util.atomic_write(fp, "second {x}")
        assert p2_load(tctx, "PMT-TMP", {"x": "A"}) == "second A", "stale: not read fresh"

    # 5) fail loud: unknown id, missing slot.
    try:
        p.load("PMT-NOPE", {})
        assert False, "unknown id did not raise"
    except UnknownPrompt:
        pass
    try:
        p.load("PMT-PING", {})                # PMT-PING needs worker_id
        assert False, "missing slot did not raise"
    except KeyError:
        pass

    print("prompts_test: PASS")
    return 0


def p2_load(ctx, pid, slots):
    return Prompts(ctx).load(pid, slots)


if __name__ == "__main__":
    sys.exit(main())
