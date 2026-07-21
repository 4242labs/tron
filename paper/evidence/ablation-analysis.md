# Ablation event-mining analysis (campaign deliverable)

All 30 ablated SIMs and all baselines completed CLEAN, so pass/fail does not
discriminate the arms. This analysis mines the typed `events.jsonl` (sole
ground truth) for event-level differences. Sample: 10 SIMs per arm (PROJ-02,
6 blocks each = 60 blocks/arm), non-ablated reference = the arms themselves
cross-compared plus the 4 pinned PROJ-02 pilot runs (@2 and @4).

| group | runs | avg dur | gates | gate FAILs | verdicts | REJECTED | re-review cycles |
|:--|--:|--:|--:|--:|--:|--:|--:|
| ablate truth_gate | 10 | 594 s | 180 | **0 (0.0%)** | 60 | 0 | 0 |
| ablate judge_isolation | 10 | 681 s | 192 | 10 (5.2%) | 62 | 2 | 2 (max cycle 3) |
| ablate architect_first | 10 | 700 s | 196 | 14 (7.1%) | 62 | 2 | 2 (max cycle 2) |
| pilot baseline @2 | 2 | 738 s | 38 | 2 (5.3%) | 12 | 0 | 0 |
| pilot baseline @4 | 2 | 742 s | 38 | 2 (5.3%) | 12 | 0 | 0 |

## Arm 1 — truth_gate (accept claims unverified)

**The only arm with a clear behavioral delta.** Every gate event in the arm
carries the marker `ABLATED: claim accepted unverified` — **180/180 worker
claims accepted with zero verification** (that is the unverified-claim
surface: every gate check of every block). Against the 5.2–7.1% real catch
rate every non-ablated group shows (all catches at the wrap phase — dirty
tree / missing session log), ~9–13 genuine catches were statistically
suppressed across the arm. Consequences visible in events: zero gate retries,
zero re-review cycles, and the arm runs **~15% faster** (594 s vs 681–742 s)
— the verification work is real work. At n=10 the removal was not
product-fatal (all 10 products probed green): the review-verdict seat and
worker discipline covered the gap at this scale. Paper phrasing: the gate's
enforcement load is measurable and its removal bounds — not zeroes — product
risk at this sample size.

## Arm 2 — judge_isolation (judges read the worker's own arena)

**No contamination signal at this scale.** Rejection rate (2/62 = 3.2%),
wrap-gate catch rate (5.2%), and re-review cycling match the non-ablated
profile; all products probed green. Instrument gap logged: verdict events do
not record *which tree* the judge read, so read-surface overlap cannot be
mined post-hoc — if this arm is ever re-run, the verdict event should carry
the read-source field.

## Arm 3 — architect_first (walls page the operator directly)

**Not exercised — no discrimination data.** Zero walls occurred in the arm's
10 runs (as in the whole campaign's valid runs), so the ablated escalation
path never fired. The arm's event profile matches baseline, as expected for
an untriggered code path. Any claim about architect-first routing must rest
on the separately-validated wall/page runs (e.g. the batch-04 SIM-04 real
529 escalation and the batch-06 gate-deadlock incident, where the
architect-then-page chain demonstrably executed), not on this arm.

## Conclusion

Event-level discrimination confirms `truth_gate` carries the engine's real
enforcement load (only arm with behavioral delta: 180 unverified accepts,
~9–13 suppressed catches, 15% speedup from skipped verification);
`judge_isolation` shows no measurable effect at n=10; `architect_first` was
never triggered and is inconclusive by design of a zero-wall sample. For the
paper: report invariant-removal effects as *bounded, not zero*, and scope the
architect-first claim to the incident evidence.
