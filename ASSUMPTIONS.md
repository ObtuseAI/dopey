# DOPEY Ascendancy Assumptions

Environment: `dopey-options-paper-v1`  
Status: conservative defaults awaiting evidence  
Every item below is an assumption, not an observed fact.

| Area | V1 assumption | Consequence |
|---|---|---|
| Authority | Paper research only; no funded-account access | L5 is the maximum autonomous level |
| Universe | 200 liquid US-listed equities and ETFs from an operator-approved manifest | A symbol absent from the manifest is rejected |
| Sessions | Regular US equity session only | Extended-hours options decisions are rejected |
| Chain data | Timestamped, sized, firm NBBO snapshots with immutable source hashes are required | Current date-only Yahoo snapshots cannot support promotion |
| Quote age | At most 15 seconds for a paper entry decision | Older quotes force abstention |
| Spread | Relative spread at most 10% | Wider markets force abstention |
| Liquidity | Volume at least 5 and open interest at least 25 | Lower-liquidity contracts are rejected |
| Structures | Defined-risk structures only | Naked or uncapped loss is prohibited |
| Costs | USD 0.65 per contract plus declared fees and adverse-side slippage | Missing fees or midpoint-only economics force abstention |
| Paper bankroll | USD 100,000 notional research bankroll | This is not real capital or proof of capacity |
| Position risk | Maximum loss at most 1% of paper bankroll | Larger candidates are rejected |
| Portfolio risk | Daily loss 2%, drawdown 10%, expected shortfall 3% | Any breach activates abstention and review |
| Ruin | Estimated probability of ruin at most 0.1% | Higher estimates are rejected |
| 0DTE | Prohibited in v1 except dedicated intraday capability tests | Daily data cannot qualify 0DTE |
| Holdout | One aggregate-only submission per frozen candidate | Feedback cannot be used for tuning |
| Forward evidence | At least 100 resolved decisions across at least 20 sessions | Unsettled decisions do not qualify for L5 |
| Profitability | No edge is currently demonstrated | Current outputs must not imply profitability |

The available development corpus contains 420 chain files, 85,608 rows, 199
symbols, and six date-only sessions through 2026-07-16. Those are observed
inventory counts, not evidence that quotes were executable or historically complete.

Missing fields are not silently imputed. A new environment version is required to
change an assumption, and prior evidence remains tied to its original version.
