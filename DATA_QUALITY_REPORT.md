# Data Quality Report

Environment: `dopey-options-paper-v1`  
Source cutoff: 2026-07-16  
Status: `development_mechanics_only_frozen_snapshot`

This report describes the immutable 2026-07-17 evaluation snapshot. It is not a
claim about the current operational option-chain lake; drift from the live
manifest is expected and must be surfaced separately.

The frozen protected source manifest identifies 420 option-chain CSVs, 85,608
rows, 199 unique symbols, and six snapshot sessions from 2026-07-09 through
2026-07-16. The source files are Yahoo Finance chain snapshots with date-level
identity.

The corpus does not contain observation or receipt timestamps, quote sizes, venue
identity, firm-quote conditions, NBBO proof, complete-chain proof, adjusted-contract
identity, or later quote witnesses. It therefore supports parsing, schema checks,
surface-mechanics tests, and negative cases only. It is blocked from claims about
execution quality, chronological strategy performance, calibration, sealed
evaluation, forward shadow evidence, capacity, or profitability.

The 199-symbol latest snapshot nearly covers the 200-symbol operating universe,
but file count is not point-in-time universe membership proof. Missing membership,
survivorship, or source-version evidence remains a hard abstention condition.

## Full-manifest quality scan

All 85,608 rows in the 420 files were scanned on 2026-07-17.

| Check | Count | Rate |
| --- | ---: | ---: |
| Crossed markets | 0 | 0.00% |
| Zero bids | 9,078 | 10.60% |
| Bid below USD 0.05 | 12,543 | 14.65% |
| Relative spread above 10% | 49,592 | 57.93% |
| Volume below 5 | 39,711 | 46.39% |
| Open interest below 25 | 29,659 | 34.65% |
| Invalid or nonpositive implied volatility | 0 | 0.00% |
| Negative bid, volume, or open interest | 0 | 0.00% |
| Nonpositive ask | 0 | 0.00% |
| Midpoint mismatch above USD 0.01 | 0 | 0.00% |
| Expiry before snapshot or calendar-DTE mismatch | 0 | 0.00% |
| Missing required CSV values | 0 | 0.00% |
| Duplicate date/symbol/expiry/type/strike keys | 0 | 0.00% |

The high wide-spread and low-participation rates reinforce the fail-closed liquidity
gate. These measurements describe the stored snapshots; they do not establish quote
firmness, NBBO status, availability at a decision time, or executability.
