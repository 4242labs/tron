# Block 02 — the codec

test: python3 -m unittest discover

## Tasks

1. Create `codec.py` importing `core.Record`:
   - `encode(rec) -> str`: a single line, NO trailing newline, that
     captures key, value, and the deleted flag. Keys and values never
     contain a tab or newline (state that assumption).
   - `decode(line) -> Record`: the exact inverse; `decode(encode(r)) == r`
     for both set and delete records.
2. Tests in `test_codec.py`: at least 6 cases — round-trip a set record, a
   delete record, an empty-string value, a value with spaces; and assert a
   malformed line raises `core.StoreError`.
3. Add the `codec.py` line to `MODULES.md`, alphabetical.
4. The whole repository suite stays green.

_Depends on: 01 — those modules are already landed on the trunk you branch from; import them._
