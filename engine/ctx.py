"""ctx — the runtime context: where every file the engine touches lives.

A TRON instance dir holds the canon (routing/messages/tron.md), the per-project
composition + config (workflow.yaml/project.yaml), live state, inboxes and logs.
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

    # ── per-project (seeder-authored) ──
    @property
    def workflow(self):
        return self.p("workflow.yaml")

    @property
    def project(self):
        return self.p("project.yaml")

    # ── live state (runtime, gitignored) ──
    @property
    def state(self):
        return self.p("workflow-state.yaml")

    @property
    def current_id(self):
        return self.p("current-id")

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

    @property
    def logs_dir(self):
        return self.p("logs")

    @property
    def scripts_dir(self):
        return self.p("scripts")

    # ── loaders (read fresh each session start / tick) ──
    def load_routing(self):
        return util.load_yaml(self.routing)

    def load_workflow(self):
        return util.load_yaml(self.workflow)

    def load_project(self):
        return util.load_yaml(self.project) if os.path.exists(self.project) else {}

    def heartbeat_effective(self):
        """Is the autonomous heartbeat (cron) effective? telegram==on OR cron==on;
        cron==auto follows telegram; cron==off wins. Single source for every start path."""
        notif = (self.load_project().get("notifications") or {})
        tg = str(notif.get("telegram", "off")).lower() == "on"
        cron = str(notif.get("cron", "auto")).lower()
        if cron == "off":
            return False
        if cron == "on":
            return True
        return tg

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
            "pipeline": under("pipeline_path", "meta/pipeline.md"),
            "blocks": under("blocks_dir", "meta/blocks/"),
            "archive": under("archive_dir", "meta/blocks/archive/"),
        }
