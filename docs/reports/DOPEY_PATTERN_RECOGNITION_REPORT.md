# DOPEY Pattern Recognition Report

## Purpose

The pattern fixture layer expands DOPEY's deterministic analysis context with 16 offline pattern
fixtures. These are not trained signals, not predictive market signals, and not real-data
features. They are fixture-only scoring hints for analysis fusion, tournament interpretation,
and mutation scoring.

## Model versions

- Pattern fixture corpus: `dopey-pattern-fixture-corpus-v1`
- Pattern scorecard: `dopey-pattern-scorecard-v1`

## Pattern types

- `bullish_breakout_continuation`
- `bearish_breakdown_continuation`
- `failed_breakout_reversal`
- `failed_breakdown_reversal`
- `range_pin`
- `volatility_expansion_setup`
- `post_event_iv_crush_setup`
- `liquidity_trap`
- `high_spread_false_signal`
- `gamma_squeeze_proxy`
- `theta_decay_window`
- `macro_shock_reversal`
- `chop_fakeout`
- `trend_vol_continuation`
- `low_liquidity_decay_pattern`
- `skew_warning_pattern`

## Integration

- `analysis_fusion.fuse_analysis()` now accepts `pattern_fixture_score`, neutral by default.
- Tournament fusion computes fixture pattern scorecards per family/regime window.
- Tournament summaries record average pattern fixture score and supporting/penalizing pattern IDs.
- Champion registry and ProofLedger records include the pattern recognition summary.
- Mutation scoring uses average pattern fixture score as one deterministic paper-only input.

## Current pattern impact

Current tournament average pattern fixture scores:

- directional_convexity: 0.666563
- volatility_expansion: 0.638542
- volatility_compression: 0.626563
- short_duration_defined_risk: 0.509687

Pattern context changes analysis fusion deterministically; tests verify high versus low pattern
fixture scores change fused output.

## Limitations

- No ML model is trained.
- No real data is used.
- Pattern fixtures are static deterministic engineering inputs.
- They should be treated as analysis context, not prediction.
