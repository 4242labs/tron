# pipeline — Example + contract

The pipeline is the single **status + sequence record** for the project: which blocks exist, in what order, who owns them, and where each one stands. It joins to specs by ID.

**Where it lives:**
- If the project **already keeps a pipeline doc**, TRON validates it has the required fields and **uses it directly** as the live pipeline.
- If the project **has none**, TRON interviews the operator about the blocks and their statuses, then **creates the pipeline inside its own folder** (`<agents>/tron/pipeline.md`, from `templates/pipeline.md`).

During a session, **TRON's pipeline is authoritative**. Specs are pure declarations; the pipeline is the running record.

---

## Required fields

Each row/entry must carry:

| Field | Meaning |
|:--|:--|
| **ID** | The spec ID this block builds. Joins pipeline ↔ spec. |
| **Order** | Intended sequence (the operator's plan). A preference, not a hard gate — spec **dependencies** are the hard gates. |
| **Owner** | Worker role that builds it (default from the spec). |
| **Status** | One of: `todo`, `in-progress`, `blocked`, `review`, `done`. |
| **Notes** | Optional — free text (why blocked, links, decisions). |

When validating a host's existing pipeline doc, TRON checks these fields are present (by name or obvious equivalent) and asks the operator to fill any gap. It does not force the operator to reformat.

---

## Example

```
| Order | ID       | Owner     | Status      | Notes                     |
|:------|:---------|:----------|:------------|:--------------------------|
| 1     | AUTH-01  | engineer  | done        |                           |
| 2     | AUTH-02  | engineer  | in-progress |                           |
| 3     | AUTH-03  | engineer  | blocked     | waits on AUTH-02          |
| 4     | UI-01    | engineer  | todo        | operator-only DNS step    |
```

---

## Notes

- The pipeline reflects reality at seed time too: for a **mid-project** repo, TRON populates initial statuses from the host pipeline doc (if any) or by interviewing the operator — so injecting TRON into work already underway doesn't lose track of what's done.
- TRON updates statuses as blocks progress. If the live pipeline is a host-tracked file, those updates change a host file each turn — acceptable per the operator's choice to use their own doc.
