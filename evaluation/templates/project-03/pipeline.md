# Pipeline — permanent block register

Engine-owned: statuses are stamped by the engine's own verdict.

| id | block | depends on | status | branch |
|:--|:--|:--|:--|:--|
| 01 | block-01 | — | todo | — |
| 02 | block-02 | 01 | todo | — |
| 03 | block-03 | 01 | todo | — |
| 04 | block-04 | 01 | todo | — |
| 05 | block-05 | 03, 04 | todo | — |
| 06 | block-06 | 02 | todo | — |
| 07 | block-07 | 02, 05, 06 | todo | — |
| 08 | block-08 | 07 | todo | — |
