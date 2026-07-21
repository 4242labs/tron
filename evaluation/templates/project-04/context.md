# project-04 — a mini persistent key-value store (long-horizon)

A small but real log-structured key-value store, built test-first through
the Orchestrator's full flow across **15 blocks and seven dependency
layers**. This project exists to exercise the engine over a LONG horizon:
many blocks, a dependency graph deep enough that the run outlives any single
worker's context window, two diamonds (parallel branches that re-merge), and
sustained contention on one shared `MODULES.md`. It measures the process at
scale, not the cleverness of the store.

- Language: Python 3 stdlib only. No third-party packages.
- The suite must stay green at every landing: `python3 -m unittest discover`.
- Display rule: error messages are lowercase, one line, no trailing period.
- Every module is listed in `MODULES.md` (one line per module, alphabetical
  by filename); the block that adds a module adds its line.

## The store, in one paragraph

Writes go to an append-only write-ahead log (`wal`) and an in-memory
`memtable`. When the memtable is large enough it is flushed to an immutable
on-disk `segment`, and the WAL is reset; the ordered list of live segments
is tracked in a `manifest`. Reads check the memtable, then segments newest
to oldest. Deletes are tombstones. `compaction` merges segments, keeping the
newest write per key and dropping tombstoned keys. On open, `recovery`
rebuilds state from the manifest's segments plus the WAL tail.

## Module contract (canonical signatures — build to these exactly)

Depending blocks rely on these being stable, so implement the signatures
verbatim:

- `core.py` — `class StoreError(Exception)`; `class Record` with fields
  `key: str`, `value: str | None`, `deleted: bool`; `Record.set(key, value)`
  and `Record.delete(key)` classmethods; equality by fields.
- `codec.py` — `encode(rec: Record) -> str` (one line, no newline);
  `decode(line: str) -> Record`. Round-trips any Record. Format is the
  module's own business; keys/values never contain a tab or newline.
- `memtable.py` — `class MemTable`: `put(key, value)`, `delete(key)`,
  `get(key) -> Record | None`, `items() -> list[tuple[str, Record]]`
  (sorted by key), `__len__`.
- `wal.py` — `class WAL(path)`: `append(rec: Record)`, `records() ->
  list[Record]` (in write order), `reset()` (truncate the log).
- `segment.py` — `write_segment(path, records: list[Record]) -> None`
  (records written sorted by key); `class Segment(path)`: `get(key) ->
  Record | None`, `items() -> list[tuple[str, Record]]` (sorted).
- `manifest.py` — `class Manifest(path)`: `add(name)`, `remove(names)`,
  `segments() -> list[str]` (oldest first, persisted across opens).
- `compaction.py` — `compact(segments: list[Segment]) -> list[Record]`:
  newest-wins merge across the given segments (oldest-first input), dropping
  records whose newest state is deleted.
- `recovery.py` — `recover(dir: str) -> MemTable`: rebuild a MemTable from
  the manifest's segments (oldest first) then the WAL tail (newest wins).
- `store.py` — `class Store(dir)`: `put(key, value)`, `get(key) -> str |
  None`, `delete(key)`, `flush()`; `Store.open(dir)` classmethod. Wires
  memtable + wal + segments + manifest + recovery + compaction.
- `cli.py` — `main(argv) -> int`: `put KEY VALUE`, `get KEY`, `del KEY`,
  `list`, `compact`, `stats` against a store dir (`--dir`, default `./data`).
