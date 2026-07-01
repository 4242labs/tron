"""ctx — the runtime context: where every file the engine touches lives.

A TRON instance dir holds the canon (routing/messages/tron.md/prompts), the
per-project knobs (knobs.yaml/project.yaml), live state, inboxes and logs.
The seeder lays this out; the engine reads it. One object, resolved once.
"""
import os

import util


class Ctx:
    def __init__(self, tron_dir):
        self.dir = os.path.abspath(tron_dir)

    def p(self, *parts):
        return os.path.join(self.dir, *parts)

    # ── canon (copied verbatim at seed) ──
    @property
    def routing(self):
        return self.p("routing.yaml")

    @property
    def messages(self):
        return self.p("messages.yaml")

    @property
    def tron_md(self):
        return self.p("tron.md")

    # ── prompt layer (canon, copied verbatim at seed; PMT-* resolved by id) ──
    @property
    def prompts_dir(self):
        return self.p("prompts")

    @property
    def prompts_registry(self):
        return self.p("prompts", "registry.yaml")

    # ── per-project (seeder-authored) ──
    @property
    def knobs_file(self):
        return self.p("knobs.yaml")

    @property
    def project(self):
        return self.p("project.yaml")

    # ── live state (runtime, gitignored) — the MANIFEST: durable run-memory ──
    @property
    def state(self):
        return self.p("manifest.yaml")

    @property
    def current_id(self):
        return self.p("current-id")

    # ── WAKE daemon (01-04): the single tick-source while a session is live ──
    @property
    def wake_pid(self):
        return self.p(".wake.pid")

    @property
    def tick_lock(self):
        # Single-flight: every tick — daemon-fired or the console's manual `tick` —
        # takes this flock so two ticks never overlap (a tick is not re-entrant).
        return self.p(".tick.lock")

    @property
    def dispatched_log(self):
        return self.p("dispatched.log")

    # ── inboxes (drained each tick) ──
    @property
    def worker_inbox(self):
        return self.p("worker-inbox.jsonl")

    @property
    def operator_inbox(self):
        return self.p("operator-inbox.jsonl")

    @property
    def tg_inbox(self):
        return self.p("tg-inbox.jsonl")

    # ── home event log (B7 console replays this on reconnect) ──
    @property
    def home_log(self):
        return self.p("home-events.jsonl")

    # ── structured forensic event + failure log (01-06): records, not prose ──
    @property
    def event_log(self):
        return self.p("events.jsonl")

    @property
    def logs_dir(self):
        return self.p("logs")

    # ── worker store (01-10): TRON-owned, keyed by STABLE worker id (never session id). Each
    # worker's mailbox (engine->worker), runner state, and turn timeline live here. Replaces the
    # host job store: workers are runner-wrapped processes TRON owns, not free-running bg agents. ──
    @property
    def workers_dir(self):
        return self.p("workers")

    def worker_dir(self, worker_id):
        return self.p("workers", worker_id)

    @property
    def scripts_dir(self):
        return self.p("scripts")

    # ── loaders (read fresh each session start / tick) ──
    def load_routing(self):
        return util.load_yaml(self.routing)

    def load_knobs(self):
        return util.load_yaml(self.knobs_file)

    def load_project(self):
        return util.load_yaml(self.project) if os.path.exists(self.project) else {}

    # ── canon paths in the target repo (TRON reads these; never writes them) ──
    def repo_paths(self, project):
        """Resolve the trunk checkout + canon file paths from project.yaml.

        repo.root is the trunk checkout; pipeline/blocks/archive are relative to it.
        Returns {root, pipeline, blocks, archive, main_branch, staging}."""
        repo = (project or {}).get("repo") or {}
        root = os.path.expanduser(repo.get("root") or self.dir)

        def under(rel, default):
            return os.path.join(root, (project or {}).get(rel) or default)

        return {
            "root": root,
            "main_branch": repo.get("main_branch", "main"),
            "staging": repo.get("staging", "none"),
            "remote": repo.get("remote"),   # None/"none" -> local trunk mode (read HEAD in place, no fetch)
            "pipeline": under("pipeline_path", "meta/pipeline.md"),
            "blocks": under("blocks_dir", "meta/blocks/"),
            "archive": under("archive_dir", "meta/blocks/archive/"),
        }
