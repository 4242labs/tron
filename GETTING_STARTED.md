# Getting started

How to install, seed, and run TRON. For what it is and how it works, see [`README.md`](README.md).

## Requirements

- `python3` and `git`.
- `jq` — the shell connectors parse JSON.
- A background-capable agent runtime on `PATH` — it runs the worker agents TRON dispatches. TRON drives
  it; you never address it directly.

## Commands

Two commands. Everything else is internal — the heartbeat, recovery, and validation run themselves.

| Command | What it does |
|:--|:--|
| `tron seeder` | Seed TRON into a target project — an interview that detects your repo, settles the knobs, and writes the instance. Touches only TRON's own folder. Run from the project root. |
| `tron start`  | Wake TRON — a short bootup (where to start, how many workers) then the live console: watch the fleet, talk to TRON, `stop` when done. |

```bash
# 1. From a canon clone, seed TRON into your project:
cd ~/code/my-project
~/code/tron/tron seeder

# 2. Wake it (from the seeded instance):
<agents>/tron/tron start
```

Inside `tron start`: type to talk to TRON; `status` / `pipeline` to look; `stop` to end.

## File layout — canon (this repo)

```
tron/
├── tron                    # the operator entrypoint (seeder · start)
├── README.md · LICENSE
├── tron.md                 # the judgment context (the one judgment LLM call runs under this)
├── tron-seed.md            # the seeding protocol
├── routing.yaml            # the trigger grammar + inbound-message map (canon, never per-project)
├── knobs.yaml              # the default knobs (worker/architect counts, cadence, WAKE timing, git)
├── messages.yaml           # every line TRON says, by template (worker lines point at a PMT)
├── prompts/                # the PMT-* worker prompts + registry (referenced by id, imported at tick)
├── engine/                 # the deterministic engine (dispatch loop, selector, trunk reader, judgment, lint)
├── protocols/              # lifecycle: bootup · run-teardown
├── scripts/                # thin shell connectors (heartbeat, worker→engine report, notifications)
├── templates/              # runtime-state seeds
├── contracts/              # design contracts + schemas
├── project.example.yaml    # the project-profile shape the seeder fills
└── knobs.example.md        # the knobs, explained
```

TRON ships no agents and no pipeline of its own: it reads the project's `agents/*.md` and its git-tracked
canon pipeline (`pipeline.md` + `blocks/`), which the `new-project-template` defines.

## File layout — your project (after `tron seeder`)

```
<agents>/tron.md            # the judgment context (copied)
<agents>/tron/
├── tron · engine/          # the entrypoint + the deterministic engine (canon, copied)
├── project.yaml            # this project's pointers, agents, repo facts
├── knobs.yaml              # this project's knobs
├── routing.yaml · messages.yaml · prompts/ · protocols/ · scripts/   # canon, copied verbatim
└── …runtime state…         # manifest.yaml (the MANIFEST), logs, inboxes (gitignored, edited in place)
```

To remove TRON entirely: delete `<agents>/tron.md` and `<agents>/tron/`. No other traces.
