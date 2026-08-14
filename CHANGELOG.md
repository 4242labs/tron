# Changelog

## [0.4.4](https://github.com/4242labs/tron/compare/v0.4.3...v0.4.4) (2026-08-14)


### Bug Fixes

* **ci:** open a PR for the contributors refresh instead of pushing to main ([#194](https://github.com/4242labs/tron/issues/194)) ([de0f84d](https://github.com/4242labs/tron/commit/de0f84d807d2e8ab02a95d722cbc9fc298a5d292))
* **install:** require python3 3.11+ in preflight ([#181](https://github.com/4242labs/tron/issues/181)) ([ff27d50](https://github.com/4242labs/tron/commit/ff27d504d083a2ff7409227d1ff3a287a8a6570f))
* refuse a project with no block specs by name, not by traceback ([#180](https://github.com/4242labs/tron/issues/180)) ([dc1f8a2](https://github.com/4242labs/tron/commit/dc1f8a2bcf1e54ffe7059cd12890fce0194c65dd))

## [0.4.3](https://github.com/4242labs/TRON/compare/v0.4.2...v0.4.3) (2026-07-24)


### Bug Fixes

* perfection-review findings (42L-1129) ([#176](https://github.com/4242labs/TRON/issues/176)) ([81581ee](https://github.com/4242labs/TRON/commit/81581ee9d19aabdccd531af0f1a4b073126902b5))

## [0.4.2](https://github.com/4242labs/TRON/compare/v0.4.1...v0.4.2) (2026-07-24)

First public release of the deterministic engine. The engine takes the model off
the control path: the process is data (`workflow.toml` + escalation table), a lint
validates it before it runs, and the model is called only to build and to make a
few narrow, bounded judgments — never to choose a step.

### Engine

* **Truth gate & the DONE ladder** — "reports done" is only a trigger. The gate
  decides *done* on the evidence: commits + untouched trunk + engine-run tests +
  an acceptance challenge. The worker merges inside a single engine-wide window;
  the engine lands, re-validates **on trunk**, then the worker wraps.
* **Per-block `test-timeout:` directive** — the gate judges a slow-but-legitimate
  test suite by its result, not a fixed clock; the per-turn wall-clock budget was
  raised so a worker self-running a long suite in-turn isn't flagged as stuck.
* **Architect-first escalation** — every wall routes to the architect first; the
  operator is the last resort, reachable from anywhere via Telegram.
* **Crash-safe recovery** — crashed runs recover at boot: stray agents killed,
  unverified branches preserved as `orphan/*`, blocks re-dispatched. Every engine
  decision is one typed JSON line in `events.jsonl` — the single measurement source.
* **Liveness** — a silence-sweep → ping → stalled → recover pacing ladder; no
  silent gate hangs.
* **Deterministic worker↔engine messaging** with an online handshake.
* **Runtime write-guard** — deny-by-default protection keeping worker writes inside
  their arena.

### Modes

* **One-command install** (`curl … | sh`) wiring the slash commands and terminal
  shortcuts on a fresh machine.
* New modes: **SCAFFOLD** (`/tron-scaffold` stands up a new project), **KONDO**
  (tidy an existing project up to canon), **ALFREDO** (the generalist), plus the
  FLYNN and CLU personas.

### Docs & research

* Published the **paper bundle** under [`paper/`](paper/) — the preprint plus the
  evidence: typed event logs, ablations, and two third-party-oracle probes
  (MIT 6.5840 MapReduce + Raft).
* The **wiki** is the single docs home; the generated GLOSSARY / EVENTS / WORKFLOW
  reference is kept in sync by a lint.

### Interactive diagram

* Vendored bpmn-js with a Content-Security-Policy; version-stamp and watermark
  fixes.

---

*This release consolidates the full engine rebuild; the complete per-commit
history is available in the [git log](https://github.com/4242labs/TRON/commits/v0.4.2).*
