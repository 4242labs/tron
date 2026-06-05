"""util — shared helpers for the TRON engine (B3).

Atomic writes, YAML/JSON load, ISO timestamps, append-only logs. No flow logic
lives here; this is the plumbing every other module leans on.
"""
import os
import json
import tempfile
from datetime import datetime, timezone

import yaml


def now_iso():
    """UTC ISO-8601, second resolution. The one clock the engine reads."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_yaml(path):
    with open(path, "r") as fh:
        return yaml.safe_load(fh) or {}


def dump_yaml(data):
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)


def atomic_write(path, text):
    """Write tmp then rename over the live file (contracts §5).

    Rename is atomic on a single filesystem, so the live file is never left
    half-written and a crashed tick leaves the prior state intact.
    """
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_yaml(path, data):
    atomic_write(path, dump_yaml(data))


def append_jsonl(path, obj):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(obj) + "\n")


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def log_line(logs_dir, name, text):
    """Append a dated line to logs/<name>-<date>.log."""
    os.makedirs(logs_dir, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    with open(os.path.join(logs_dir, f"{name}-{date}.log"), "a") as fh:
        fh.write(f"{now_iso()} {text}\n")
