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

    @property
    def version_file(self):
        return self.p("VERSION")

    @property
    def worker_contract(self):
        # The worker/TRON interface doc (canon, copied at seed) — PMT-SPAWN points every
        # worker at it before the persona; the project's docs own the METHOD, this owns
        # the handshake.
        return self.p("worker-contract.md")

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

    # ── pinned trunk snapshot (W9): the canon files as of the tick's pinned sha ──
    @property
    def trunk_snapshot_dir(self):
        return self.p(".trunk-snapshot")

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

    # ── durable inbound-message archive (T8, 01-18 addendum 2) ──
    @property
    def message_log(self):
        """Beside `event_log`, not inside it: `events.jsonl` records what TRON DECIDED;
        this preserves what was actually SAID. Engine->worker is fully durable (mailbox +
        home log) but worker/operator/tg->engine raw text used to live only in the inbox
        sidecar — claimed each tick and DELETED after a clean save, leaving only derived
        events and truncated snippets. E2 adjudication and any post-hoc dispute needs
        exactly what the agent said, so `_claim_inboxes` archives every claimed line here
        verbatim, parsed or not, before/regardless of processing."""
        return self.p("messages.jsonl")

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

    # ── scratch (01-32 T2, ADR-0002 D1): TRON-owned spawn cwd + validation-checkout root.
    # Squarely inside TRON's own folder-absolute writable surface — every worker spawns
    # here and carves its OWN worktree+branch as its first ritual act (never a pre-carve
    # write landing in the shared project checkout); the declared-command trunk verdict's
    # validation checkouts (trunk._run_declared_command) live here too (the "scratch
    # worktree admin" exception Decision 1 names). Swept by TRON, never project content —
    # the scaffold's `.gitignore` covers it. ──
    @property
    def scratch_dir(self):
        return self.p("scratch")

    def worker_scratch_dir(self, worker_id):
        return self.p("scratch", worker_id)

    # ── grants (T3, 01-32 T3, ADR-0002 D2): patch-id-bound merge/close authorizations,
    # minted here on gate approval and consumed by `land.sh` (or administratively, by
    # the engine itself, in the post-advance crash window) — squarely inside TRON's own
    # folder-absolute writable surface, never a project write. ──
    @property
    def grants_dir(self):
        return self.p("grants")

    @property
    def landlock_path(self):
        return self.p("grants", ".landlock")

    # ── loaders (read fresh each session start / tick) ──
    def load_routing(self):
        return util.load_yaml(self.routing)

    def load_knobs(self):
        return util.load_yaml(self.knobs_file)

    def load_project(self):
        return util.load_yaml(self.project) if os.path.exists(self.project) else {}

    def load_version(self):
        """The instance's own copied canon VERSION — its byte-identical stamp at last
        seed. None if absent (pre-M-06 instance)."""
        if not os.path.exists(self.version_file):
            return None
        with open(self.version_file) as f:
            return f.read().strip()

    # ── canon paths in the target repo (TRON reads these; never writes them) ──
    def repo_paths(self, project):
        """Resolve the trunk checkout + canon file paths from project.yaml.

        repo.root is the trunk checkout; pipeline/blocks/archive are relative to it.
        Returns {root, pipeline, pipeline_rel, blocks, blocks_rel, archive, paperwork,
        main_branch, staging, remote}."""
        repo = (project or {}).get("repo") or {}
        root = os.path.expanduser(repo.get("root") or self.dir)

        def under(rel, default):
            return os.path.join(root, (project or {}).get(rel) or default)

        pipeline_rel = (project or {}).get("pipeline_path") or "meta/pipeline.md"
        # tron-13 D1: what counts as PAPERWORK is the project's to declare
        # (`paperwork_paths`, seeder-authored; repo-relative, dirs end with /).
        # Default: the meta dir holding the pipeline.
        paperwork = (project or {}).get("paperwork_paths") or [
            (os.path.dirname(pipeline_rel) or "meta") + "/"]
        # Block 01-28 (T2/T4): the declared trunk-validation command/env, and the optional
        # CI check-run name the DONE-TRUNK gate may trust instead of re-running. Both live
        # under project.yaml top-level keys (`test:`, `ci:`) — contracts/schema/project.schema.yaml
        # is the source of truth; absent either -> None/{} (never a guessed default).
        test_cfg = (project or {}).get("test") or {}
        ci_cfg = (project or {}).get("ci") or {}
        return {
            "root": root,
            "main_branch": repo.get("main_branch", "main"),
            "staging": repo.get("staging", "none"),
            "remote": repo.get("remote"),   # None/"none" -> local trunk mode (read HEAD in place, no fetch)
            "pipeline": under("pipeline_path", "meta/pipeline.md"),
            "pipeline_rel": pipeline_rel,
            "blocks": under("blocks_dir", "meta/blocks/"),
            "blocks_rel": ((project or {}).get("blocks_dir") or "meta/blocks/").rstrip("/") + "/",
            "archive": under("archive_dir", "meta/blocks/archive/"),
            "paperwork": [str(p) for p in paperwork],
            "test_command": test_cfg.get("command"),
            "test_env": test_cfg.get("env") or {},
            "ci_check_name": ci_cfg.get("check_name"),
        }
