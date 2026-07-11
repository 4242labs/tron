"""core.sim.seed_canon — install the TRON instance CANON into a live instance
dir, exactly as the real seeder does.

`core.engine.Engine` (via `core.emit`/`engine.render.Renderer`) and a real
`claude` worker both need the canon a real `tron seeder` run leaves at
`<project>/meta/agents/tron/`: `messages.yaml` + `prompts/` (the PMT registry
and bodies) so the engine can RENDER a worker order carrying its reply
channel; `routing.yaml` + `tron.md` so real `classify` can resolve a free-text
report; `worker-contract.md` so the agent can learn the report verbs; and
`scripts/report.sh` — the worker→engine channel itself, which the reply line
names (`{report}` = `ctx.p("scripts","report.sh")`).

report.sh SELF-LOCATES the engine inbox as `<its dir>/../worker-inbox.jsonl`,
so it MUST land at `<instance>/scripts/report.sh` for that `..` to resolve to
`<instance>/worker-inbox.jsonl` (== `ctx.worker_inbox`, what the tick drains).

The canonical source is the TRON app root itself (`messages.yaml`, `routing.
yaml`, `tron.md`, `worker-contract.md`, `prompts/`, `scripts/report.sh` — the
reference instance canon a seeder copies from). The boot rig's
`seed_live_instance` seeds only `project.yaml`+`knobs.yaml`; THIS installs the
rest, so a live L3 run has the full canon a real seeded project would.
"""
import os
import shutil
import stat

_HERE = os.path.dirname(os.path.abspath(__file__))            # core/sim
_CORE_DIR = os.path.dirname(_HERE)                              # core
_APP_ROOT = os.path.dirname(_CORE_DIR)                            # tron-app root == canonical canon source

CANON_FILES = ("messages.yaml", "routing.yaml", "tron.md", "worker-contract.md")
CANON_DIRS = ("prompts",)


class CanonError(RuntimeError):
    """A required canon source is missing at the app root — fail loud, never
    seed a half-canon a real worker would silently wall on."""


def _mkexec(path):
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_canon(inst_dir, app_root=_APP_ROOT):
    """Copy the instance canon from `app_root` into `inst_dir` (the live TRON
    instance = `<project>/meta/agents/tron/`). Overwrites any stale copy.
    Returns the list of installed relative paths. Fail-loud on a missing
    source (never a silent partial canon)."""
    installed = []

    for name in CANON_FILES:
        src = os.path.join(app_root, name)
        if not os.path.isfile(src):
            raise CanonError(f"seed_canon: canon source missing: {src}")
        shutil.copy2(src, os.path.join(inst_dir, name))
        installed.append(name)

    for d in CANON_DIRS:
        src = os.path.join(app_root, d)
        if not os.path.isdir(src):
            raise CanonError(f"seed_canon: canon dir missing: {src}")
        dst = os.path.join(inst_dir, d)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        installed.append(d + "/")

    # scripts/report.sh — the worker->engine channel. Lands at <instance>/
    # scripts/report.sh so its own `../worker-inbox.jsonl` == ctx.worker_inbox.
    src_report = os.path.join(app_root, "scripts", "report.sh")
    if not os.path.isfile(src_report):
        raise CanonError(f"seed_canon: report.sh missing: {src_report}")
    inst_scripts = os.path.join(inst_dir, "scripts")
    os.makedirs(inst_scripts, exist_ok=True)
    dst_report = os.path.join(inst_scripts, "report.sh")
    shutil.copy2(src_report, dst_report)
    _mkexec(dst_report)
    installed.append("scripts/report.sh")

    return installed
