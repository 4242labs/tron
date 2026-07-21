# Pipeline — permanent block register

Engine-owned: statuses are stamped by the engine's own verdict.

| id | block | depends on | status | branch |
|:--|:--|:--|:--|:--|
| 01 | block-01 | — | todo | — |
| 02 | block-02 | 01 | todo | — |
| 03 | block-03 | 01 | todo | — |
| 04 | block-04 | 02 | todo | — |
| 05 | block-05 | 02 | todo | — |
| 06 | block-06 | 01 | todo | — |
| 07 | block-07 | 05, 06 | todo | — |
| 08 | block-08 | 04, 05, 06 | todo | — |
| 09 | block-09 | 03, 04, 05 | todo | — |
| 10 | block-10 | 09, 06 | todo | — |
| 11 | block-11 | 07, 10 | todo | — |
| 12 | block-12 | 08, 09 | todo | — |
| 13 | block-13 | 09, 12 | todo | — |
| 14 | block-14 | 11, 13 | todo | — |
| 15 | block-15 | 12, 13, 14 | todo | — |
