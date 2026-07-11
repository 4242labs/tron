"""core — the TRON engine rewrite's new-stack package (ADR-0004).

First brick: `core.landing` — the ONE landing primitive, re-implemented with
CONTENT-BOUND case-id identity (the confirmed root of the paperwork-landing
silent-loss bug on `engine/land.py`, forensically nailed down by
`engine/land_paperwork_rig.py`). Nothing in this package modifies the old
engine or its respected contracts (`land.sh`, `grants.py`, `trunk.py`,
`land.py`, `fsm.py`) — it imports `grants`/`trunk` and adds new files only.
"""
