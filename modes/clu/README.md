# CLU — supervisor mode

> ⚠️ **Experimental** — under active development; structure and interfaces may change without notice.

LLM-run TRON: a supervisor agent that runs a fleet of worker agents against a project's pipeline.
Persona in `clu.md`, procedures in `skills/`, setup in `install/README.md` (slash command
`/tron-clu`, PULSE-guard hook, run flags).

CLU is a **mode of TRON**, shipped in `tron-app/modes/`. It is persona-layer content and never
touches `engine/`, `core/`, or `contracts/` — the deterministic runtime.
