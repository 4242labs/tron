The {sender}'s assignment (their block):
---
{context}
---
The {sender} sent the engine a message it cannot interpret.
The {sender}'s legal messages are:
{help}
Raw message:
---
{raw}
---
Reply with exactly one of:
>>TRANSLATED <WORD field=value ...>   (its intent clearly maps to one legal message)
>>ANSWER text=<your ruling>           (it is a question/decision you can settle
                                       yourself — a design or spec judgment; your
                                       ruling is relayed back to the {sender})
>>ESCALATE reason=<one line>          (only the human operator can decide this)
