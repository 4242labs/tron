[TRON]  Architect — a {type} review just completed; its findings log is in.

Validate each finding against the code first — drop only the ones you can prove false, with a reason. Everything that survives becomes adhoc blocks queued ahead — as FEW blocks as possible (≤7 tasks each): group every related finding into one; one block per finding is never acceptable. Cover every survivor — defer nothing, wave off nothing. Then reconcile any upcoming block built on the same flaw. Forward only — don't reopen the reviewed blocks.

Author it all on a branch and report the branch name (`--tag branch --branch <name>`); I land it on trunk myself. Report the adhoc blocks you authored and any you adjusted, or "no valid findings."
