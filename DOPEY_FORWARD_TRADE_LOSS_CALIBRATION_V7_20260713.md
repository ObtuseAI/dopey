# DOPEY forward-trade loss calibration V7

Date: 2026-07-13
Scope: quote-priced paper forward walk only
Live trading: blocked

## Finding

The four closed paper losses do not support a profitability or strategy-edge conclusion. They do expose two concrete implementation failures:

1. The forward walk selected the nearest ATM / approximately 30-DTE contract without minimum volume, minimum open interest, or maximum relative-spread requirements.
2. The forward walk did not consume news and cross-asset context, so an energy-sector long put could pass solely on gamma and relative-strength inputs.

Three of the four recorded stops were dominated by severe option-quote dislocations. One was a genuine adverse directional move.

| Symbol | Side | Entry volume | Entry OI | Entry spread | Exit spread | Underlying move aligned to trade | Diagnosis | New entry policy |
|---|---:|---:|---:|---:|---:|---:|---|---|
| XLE | long put | 7 | 15 | 7.51% | 198.77% | -0.30% | liquidity-hole stop | reject: OI below 25 |
| XLV | long call | 21 | 103 | 16.64% | 138.46% | -0.43% | liquidity-hole stop | reject: spread above 10% |
| XLI | long call | 1 | 4 | 13.84% | 94.74% | +0.21% | liquidity-hole stop despite favorable underlying move | reject: spread, volume, and OI |
| META | long put | 5 | 25 | 3.57% | 6.04% | -8.59% | genuine adverse directional stop | passes liquidity policy |

The retrospective entry-policy replay rejects three of four historical entries. This is a contract-quality counterfactual only; it is not a claim that avoiding those entries would have produced profit.

## Energy-short correction

The XLE August 7 55 put was opened on 2026-07-09 and stopped on the next marking session. Its contract was already too thin at entry (open interest 15), and its next-session quote was non-executable for a trustworthy stop mark (bid 0.01, ask 3.25).

Current local context evidence records 22 seven-day geopolitical-conflict events, five energy-supply events, and a positive energy cross-asset context score of 0.035792. The current news manifest is partial and the context is not aligned to the 2026-07-10 option-chain snapshot, so those current counts are not treated as retroactive proof about the 2026-07-09 decision.

The forward policy now behaves defensively:

- An energy-sector long put is rejected when external context is missing, incomplete, or not aligned to the option-chain snapshot.
- With complete aligned context, it is rejected when geopolitical-conflict count is at least 3 or energy-supply count is at least 2 and the energy cross-asset score is non-negative.
- The veto applies to XLE and constituents mapped to the XLE sector. It does not manufacture a bullish energy signal or force a long position.

The rebuilt XLE context is currently `unfavorable` with veto reason `energy_short_external_context_unavailable`, which is the honest fail-closed state while the chain and external context are not aligned.

## Implemented hardening

- Added forward-entry contract gates: bid at least 0.05, positive ask, relative spread at most 10%, volume at least 5, and open interest at least 25.
- Changed contract selection to choose only from candidates that pass every liquidity gate, then rank tenor, moneyness, spread, open interest, and volume deterministically.
- Required same-snapshot context before any new forward entry; missing or stale context now rejects the signal.
- Added energy-short external-context vetoes and explicit rejection reason codes.
- Frozen signal, context, volume, open interest, spread, and entry-policy provenance onto every future paper position.
- Added exit bid/ask, relative spread, volume, open interest, spot, and quote-quality attribution to future closes.
- Repaired the loss coach to read the ledger's actual `exit_reason` and `holding_sessions` fields.
- Added quote reconstruction for historical closed trades and a `liquidity_hole_stop` loss mode.
- Added a versioned retrospective entry-policy replay to the loss-coach artifact.

## Validation

- Focused regression: 38 passed.
- Broader scoped regression excluding the real staged-news test: 58 passed, 1 deselected.
- The excluded integration test remains honestly blocked because `news_context_manifest.json` reports `partial_explicit_source_failures`; the full invocation produced 58 passes and that one expected failure.
- Python compilation: passed for all changed Python modules and tests.
- Git diff whitespace validation: passed.
- Protected public-lake final-state lock: `public_lake_locked_clean`, 160 active public symbols, 1,292,545 active rows, zero fixture symbols.
- The forward-walk runner was not executed, so this calibration did not open, close, mark, or rewrite any paper position.

## Current readiness

The local DOPEY control-plane snapshot remains `not_action_ready`, `paper_only=true`, and `live_blocked=true`. Only four real forward closes exist versus the unchanged minimum sample of 100, the geometric mean is negative, and compounding remains blocked. No profitability, edge, or live-readiness claim is supported.

## Primary evidence

- `artifacts/dopey/forward_walk/trade_loss_hypotheses.json`
- `artifacts/dopey/forward_walk/forward_walk_ledger.json`
- `artifacts/dopey/market_context/entry_context_fusion.jsonl`
- `artifacts/dopey/market_context/market_context_fusion_summary.json`
- `artifacts/dopey/equity_swing/news_intelligence.json`
- `artifacts/dopey/equity_swing/cross_asset_regime.json`
- `artifacts/dopey/public_signal_deepening/public_lake_final_state_lock_v2_summary.json`
