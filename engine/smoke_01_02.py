"""smoke_01_02 — the 01-02 surface smoke (config rename + WAKE knobs + PMT layer).

Honest, self-contained, no tokens / no network. Asserts what this block delivered against
the real canon instance (the repo root):

  1. knobs.yaml parses, and the WAKE bounds load as positive ints with cooldown <= ceiling.
  2. the PMT registry resolves EVERY id to an existing self-contained file.
  3. prompts.load() resolves a PMT by id and fills its slots.
  4. every worker-channel messages.yaml line carries a `pmt:` the registry knows (no inline copy).

Run: python3 engine/smoke_01_02.py   (exit 0 = pass). Pairs with `./lint.sh` for AC-6.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import util                  # noqa: E402
from ctx import Ctx          # noqa: E402
from prompts import Prompts  # noqa: E402

ROOT = os.path.dirname(HERE)            # the canon instance (repo root)
ctx = Ctx(ROOT)
fails = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


print("smoke_01_02 — config rename + WAKE knobs + PMT layer:")

# 1) knobs.yaml + WAKE bounds
knobs = (ctx.load_knobs() or {}).get("knobs", {})
cd, ce = knobs.get("wake_cooldown_sec"), knobs.get("wake_ceiling_sec")
check("1 knobs.yaml parses + worker_count present", "worker_count" in knobs)
check("1 WAKE bounds positive ints", isinstance(cd, int) and cd > 0 and isinstance(ce, int) and ce > 0,
      f"cooldown={cd!r} ceiling={ce!r}")
check("1 WAKE cooldown <= ceiling", isinstance(cd, int) and isinstance(ce, int) and cd <= ce,
      f"{cd} > {ce}")

# 2) PMT registry resolves every id to a file
reg = (util.load_yaml(ctx.prompts_registry) or {}).get("prompts", {})
check("2 PMT registry non-empty", bool(reg))
unresolved = [pid for pid, spec in reg.items()
              if not os.path.exists(os.path.join(ctx.prompts_dir, (spec or {}).get("file", "")))]
check("2 every registry id resolves to a file", not unresolved, f"unresolved: {unresolved}")

# 3) prompts.load() resolves by id + fills slots
try:
    body = Prompts(ctx).load("PMT-ASSIGN",
                             {"worker_id": "ENG-01-02", "assignment": "build block 01-02",
                              "merge_path": "open a PR", "report": "/x/report.sh"})
    filled = all(s in body for s in ("ENG-01-02", "block 01-02"))
except Exception as e:           # noqa: BLE001
    filled = False
    body = f"<raised {e}>"
check("3 prompts.load() resolves id + fills slots", filled, repr(body)[:80])

# 4) every worker message references a known PMT, none inlined
msgs = (util.load_yaml(ctx.messages) or {}).get("templates", {})
worker = {k: v for k, v in msgs.items() if (v or {}).get("channel") == "worker"}
bad = [k for k, v in worker.items() if not v.get("pmt") or v.get("pmt") not in reg or "text" in v]
check("4 worker lines reference a known PMT, none inlined", not bad and bool(worker), f"bad: {bad}")

print("smoke_01_02:", "PASS" if not fails else f"FAIL ({len(fails)})")
sys.exit(0 if not fails else 1)
