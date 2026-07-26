# DOPEY Elite Action Hardening V9

Date: 2026-07-13

## Outcome

DOPEY is materially safer and more selective for its next paper-research cycle. This pass closes the two largest execution-quality defects found in the existing forward book, replaces a confounded cohort baseline method, and makes stale evidence policies explicit readiness blockers.

This is not a profitability or live-readiness claim. The current machine verdict remains `not_action_ready`, paper-only, and live-blocked.

## Forward option execution hardening

- Added exit policy `dopey-forward-exit-quality-v3`.
- A quote with relative spread above 25% is an observation, not an executable exit.
- Dislocated quotes cannot trigger premium stops or targets and cannot replace the last executable quote.
- Time-stop and expiry-proximity exits defer until the next executable quote; the pending reason remains in the ledger.
- Missing contracts force-close only after three misses and use the last executable bid with explicit stale-quote attribution.
- Every new position freezes its last executable bid, ask, date, quote-quality state, and unreliable-quote count.
- `_close_with_quote` now raises if any caller attempts to close on a non-executable quote.

The loss coach now replays both entry and exit policies without revising historical outcomes:

- closed sample: 4
- losses classified as liquidity-hole stops: 3
- genuine adverse-move stop: 1
- trades the V2 entry policy would have rejected: 3 of 4
- exits the V3 executable-quote policy would have rejected/deferred: 3 of 4

The historical ledger is preserved unchanged. These replay results explain the sample; they do not erase or restate it.

## Portfolio construction hardening

New forward entries now enforce:

- maximum 12 open positions
- maximum 8 new positions per run
- maximum 3 positions per sector
- maximum 8 positions per direction
- one open position per symbol, regardless of call/put direction

The current 17-position legacy book was not force-closed or rewritten. Its audit now reports:

- 17 positions across 16 unique symbols
- one duplicate-symbol exposure
- technology exposure of 4, above the cap of 3
- bullish exposure of 9, above the cap of 8
- total open positions above the cap of 12
- 4 positions nonconforming with the current entry-liquidity policy

The action-readiness gate now includes `open_book_concentration_green`; the current legacy book correctly fails it. New entries remain blocked while the total cap is exceeded and cannot add same-symbol, sector, or directional concentration afterward.

## Cohort and statistical calibration

The previous baseline code claimed cohort-specific symbol/month matching but pooled controls across the entire call or put strategy. That could confuse signal quality with a cohort's symbol and era composition.

Baseline policy `dopey-cohort-matched-baseline-v2` now:

- constructs exactly one control for each real modeled trade
- matches the same cohort, symbol, and calendar month
- uses the same pricing, exit, and cost engine
- preserves the real trade ID for auditable pairing
- raises on missing or incomplete matches
- bootstraps paired differences by month cluster to retain within-month dependence
- applies Bonferroni familywise control across evaluated cohorts

Era policy `dopey-era-robustness-v2` now emits per-cohort failure reasons, passing-era counts, worst-era average P&L, and a separate `near_robust_two_of_three_eras` status. The all-era robustness threshold is unchanged.

Readiness and paper-aggression gates now require current baseline and era policy versions. Old artifacts cannot earn readiness or increased paper sizing. The V2 baseline and era engines were deliberately not executed in this session because the governed research-cycle confirmation phrase was not supplied; current V1 evidence therefore remains stale and fail-closed.

## Current governed inputs

- News manifest: `complete`
- Required official source coverage: 7 of 7 staged
- Current news events: 202
- Cross-asset and news staged-input integration: passed
- Context decisions: 2 recorded, 0 resolved, 2 pending
- Required resolved context decisions: 200

## Current readiness blockers

The regenerated action gate reports 10 unmet conditions:

1. `cohort_baseline_policy_current`
2. `any_cohort_beats_matched_baseline_familywise`
3. `cohort_era_policy_current`
4. `any_cohort_regime_robust`
5. `forward_track_sample_sufficient`
6. `forward_track_net_positive`
7. `no_active_discipline_halt`
8. `open_book_entry_quality_green`
9. `open_book_concentration_green`
10. `statistical_truth_promotion_allowed`

The forward track remains at 4 closed trades against the unchanged requirement of 100. No gate or evidence threshold was reduced.

## Validation

- Expanded chain, context, forward-walk, readiness, real-history, statistical-truth, sharpness, and adaptable-build regression: 115 passed.
- Real staged cross-asset and news integration: passed using manifest-derived decision timestamps and event counts.
- Python compilation of every changed module: passed.
- Scoped Git whitespace validation: passed.
- Protected public lake read-only audit: `public_lake_locked_clean`.
- Public lake: 160 public symbols, 1,292,545 rows, 0 fixture symbols, 0 test-symbol residue, 0 error flags.
- No forward mark, baseline/era production rerun, paper-research cycle, broker connection, credential operation, or order operation was performed.
- Publication state: see `DOPEY_GITHUB_PUBLICATION_V10_20260713.md`.

## Next governed action

The highest-value next mutation is one allowlisted paper-research cycle that regenerates baseline V2, era V2, forward/context diagnostics, and the readiness gate against the fresh complete context manifests. Explicit operator invocation authorizes this governed paper-research lane; no elapsed-context gate applies under the creator policy.
