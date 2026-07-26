# DOPEY SLIPPAGE LIQUIDITY REPORT

## Purpose

This pass replaces the old fixed 0.2% paper slippage heuristic with deterministic,
fixture-only fill-quality scoring. Replay and tournament scoring now price the same strategy
families against spread width, depth proxies, quote stability, fillability, regime pressure,
structure leg count, and family-specific bad-fill sensitivity.

This remains offline, paper-only, deterministic simulation. It is not real execution quality,
market impact, queue-position modeling, or a profit claim.

## Model versions

- Liquidity model: `dopey-liquidity-model-v1`
- Slippage model: `dopey-slippage-model-v1`
- Legacy reference retained only for audit fields: `0.002`

## Liquidity model

Module: `dopey_execution/liquidity_model.py`

Inputs used:

- bid, ask, mid, spread width, spread percentage
- volume, open interest
- regime tag and microstructure context
- quote stability score and contract fillability score
- liquidity decay score
- strategy family, structure type, DTE bucket, leg count

Outputs recorded:

- `liquidity_score`
- `spread_quality_score`
- `depth_proxy_score`
- `quote_stability_score`
- `fillability_score`
- `liquidity_penalty`
- `liquidity_verdict`

Verdicts are deterministic: `excellent`, `good`, `acceptable`, `fragile`, `poor`, `reject`.
Paper research intents downgrade poor/reject-level liquidity into research labels unless strict
liquidity rejection is requested or the intent is non-paper.

## Slippage model

Module: `dopey_execution/slippage_model.py`

Inputs used:

- spread percentage and liquidity score
- regime tag, strategy family, structure type, leg count
- volatility regime score, quote stability, slippage sensitivity
- volume/open-interest anomaly score
- high-spread, low-liquidity, event-vol, macro-shock, and short-duration flags

Outputs recorded:

- `expected_slippage_pct`
- `expected_slippage_amount`
- `worst_case_fixture_slippage_pct`
- `fill_price_adjustment`
- `fill_quality_score`
- `slippage_verdict`

Slippage increases deterministically in `high_spread_bad_fill`, `low_liquidity_decay`,
`macro_shock_risk_off`, and `event_vol_expansion`; multi-leg structures pay higher modeled
friction than single-leg fills; short-duration, directional, compression, and volatility
expansion families carry family-specific bad-regime penalties.

## Integration

- `rank_pipeline_candidates()` now ranks contracts with the liquidity model and carries model
  fields into paper intent legs.
- `simulate_paper_fill()` now uses the liquidity and slippage models for every leg and records
  bid/ask/mid, verdicts, model versions, expected slippage, fill price adjustment, paper-only,
  and `live=false`.
- `ReplayEngine` passes window regime context into the fill model, subtracts deterministic
  expected slippage cost from paper PnL, and records fill quality/liquidity fields per window.
- `score_walk_forward()` blends expected slippage and fill quality into slippage tolerance.
- `run_fixture_tournament()` records per-family liquidity/slippage summaries, worst slippage
  regimes, best fill-quality regimes, and champion registry liquidity fields.
- Tournament ProofLedger records include both model versions and slippage/liquidity summaries.

## Current tournament result

- Command: `python -m dopey_tournament.run_fixture_tournament`
- Status: `ok`
- Champion: `genome-directional-convexity-spy-fixture-v1`
- Runner-up: `genome-short-duration-defined-risk-spy-fixture-v1`
- Worst slippage regime: `high_spread_bad_fill`
- Best fill-quality regimes: `trend_vol_expansion`, `bullish_breakout`
- Reproducibility hash: `31a7a877778beabe8d0fcd9eacc76fb919a11c36ef28b32ccdeb55f8a411ce3a`

## Family fill summary

| Family | Rank | Avg liquidity | Avg fill quality | Avg slippage pct | Worst slippage regime | Best liquidity regime | Slippage robustness |
|---|---:|---:|---:|---:|---|---|---:|
| directional_convexity | 1 | 0.554364 | 0.551823 | 0.042358 | high_spread_bad_fill | bullish_breakout | 0.661136 |
| short_duration_defined_risk | 2 | 0.516918 | 0.467892 | 0.055853 | high_spread_bad_fill | bullish_breakout | 0.553176 |
| volatility_expansion | 3 | 0.532663 | 0.528211 | 0.045774 | high_spread_bad_fill | bullish_breakout | 0.633808 |
| volatility_compression | 4 | 0.473306 | 0.435184 | 0.055847 | high_spread_bad_fill | trend_vol_expansion | 0.553224 |

## Proof paths

- Tournament ProofLedger: `artifacts/dopey/tournaments/dopey_tournament.jsonl`
- Champion registry: `artifacts/dopey/champion_registry/champion_registry.jsonl`

## Validation

Commands run:

```text
python -m pytest
python -c "import dopey_execution.liquidity_model, dopey_execution.slippage_model, dopey_execution.paper_broker, dopey_research_pipeline.fill_simulator, dopey_walk_forward.replay_engine, dopey_tournament.runner; print('SLIPPAGE_LIQUIDITY_IMPORT_OK')"
python -m dopey_tournament.run_fixture_tournament
python -m pytest tests/test_slippage_liquidity_upgrade.py::test_blunder_source_integrity_if_manifest_available tests/test_expanded_regime_tournament.py::test_16_blunder_source_integrity_if_manifest_available tests/test_tournament.py::test_15_blunder_source_integrity_if_manifest_available tests/test_walk_forward.py::test_12_blunder_source_integrity_if_manifest_available -q
```

Results:

- `python -m pytest` -> 89 passed
- Import smoke -> `SLIPPAGE_LIQUIDITY_IMPORT_OK`
- Tournament smoke -> `tournament_status: ok`
- Blunder integrity tests -> 4 passed, 78/78 source baseline unchanged where manifest paths resolved

## Safety state

- mode: `RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker is the only execution adapter used for replay/tournament
- PaperBroker rejects `live_allowed=true`
- Robinhood/Alpaca/Tradier stubs raise `LiveTradingDisabledError`
- No broker connection, no credentials, no network, no autonomous scheduled runs
- Original Blunder source remains unchanged by this pass

## Limitations

- The model is deterministic fixture simulation, not calibrated market impact.
- It uses synthetic fixture bid/ask, volume, OI, and context fields, not live market data.
- It does not model Greeks, IV surface/skew dynamics, queue position, partial fills, or routing.
- It improves paper tournament realism only inside the offline fixture corpus.

## Follow-up completion note

Richer deterministic options math/Greeks validation was completed in the follow-up
`dopey-greeks-validation-v1` / `dopey-iv-fixture-model-v1` pass. Fill quality itself remains
deterministic fixture simulation and is still not calibrated live market impact.
