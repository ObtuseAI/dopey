# DOPEY Greeks/IV Validation Report

## Status

Completed: deterministic paper-only Greeks, IV context, skew, term-structure, and attribution
validation are integrated into replay, tournament ranking, ProofLedger output, and the champion
registry.

This pass is still research-only fixture simulation. It does not fetch live option chains,
calibrate a market IV surface, connect to any broker, or create any live promotion path.

## Safety boundary

- `mode`: `RESEARCH`
- `live_trading_enabled`: `false`
- `funded_broker_connections_enabled`: `false`
- `allow_unofficial_robinhood_api`: `false`
- PaperBroker remains the only execution adapter used by replay/tournament.
- PaperBroker rejects `live_allowed=true`.
- Robinhood, Alpaca, and Tradier stubs still raise `LiveTradingDisabledError`.
- No broker credentials, network calls, live trades, commits, or autonomous schedules were used.

## Models added

- Greeks validation model: `dopey-greeks-validation-v1`
- IV fixture model: `dopey-iv-fixture-model-v1`

New deterministic dataclasses:

- `GreekVector`
- `GreekExposureSummary`
- `GreekRiskVerdict`
- `GreekAttributionResult`
- `StrategyGreekProfile`
- `IVContext`
- `IVSurfaceSummary`
- `SkewSummary`
- `TermStructureSummary`

## Integration points

- Ranked contract candidates now preserve `delta`, `gamma`, `theta`, `vega`, `rho`, and `iv`.
- Family-specific paper intents carry full fixture Greeks on each leg.
- Paper fill records include `greek_exposure_summary`.
- Execution-quality records pass through Greek exposure, IV context, risk verdict, and attribution
  fields when supplied.
- Replay results now record Greek fit, component fit scores, IV context score, skew score,
  term-structure score, risk flags, attribution quality, and raw deterministic summaries.
- Walk-forward scoring includes Greek fit, IV regime fit, and Greek attribution quality.
- Tournament scoring includes Greek fit, IV/skew/term score, attribution quality, liquidity,
  slippage, invalidation, holdout, overfit, and analysis fusion.
- ProofLedger and champion registry records include model versions, Greek/IV summaries,
  best/worst Greek regimes, strengths, weaknesses, attribution quality, and high-theta/high-vega
  survival.

## Tournament result

- Command: `python -m dopey_tournament.run_fixture_tournament`
- Tournament status: `ok`
- Champion: `genome-directional-convexity-spy-fixture-v1`
- Runner-up: `genome-short-duration-defined-risk-spy-fixture-v1`
- Windows replayed: 12
- Strategies evaluated: 4
- Reproducibility hash: `ddfabb0dc1931631683475c1268e1c2b4d1eb50190b9109afd1fb653ffec76eb`

## Greek/IV family summary

| Family | Rank | Avg Greek fit | Avg IV context | Avg skew | Avg term | Avg attribution | Best Greek regime | Worst Greek regime | Risk verdict |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| directional_convexity | 1 | 0.796540 | 0.619958 | 1.000000 | 0.986875 | 0.383419 | trend_vol_expansion | post_event_iv_crush | good_fit |
| short_duration_defined_risk | 2 | 0.881253 | 0.658458 | 1.000000 | 0.973750 | 0.371190 | liquidity_decay | low_liquidity_decay | good_fit |
| volatility_compression | 3 | 0.539739 | 0.550448 | 1.000000 | 0.927042 | 0.279498 | post_event_iv_crush | macro_shock_risk_off | fragile_fit |
| volatility_expansion | 4 | 0.684166 | 0.389750 | 0.000000 | 0.184062 | 0.444913 | macro_shock_risk_off | post_event_iv_crush | acceptable_fit |

## Champion Greek profile

- Average Greek fit: 0.796540
- Average IV context score: 0.619958
- Average Greek attribution quality: 0.383419
- Best Greek fit regime: `trend_vol_expansion`
- Worst Greek risk regime: `post_event_iv_crush`
- High-theta/high-vega risk survival: `true`
- Strengths: delta exposure fits family/regime; theta profile controlled; vega exposure fits IV
  context.
- Weakness: gamma profile remains fragile in the fixture corpus.

## Validation

Commands run:

```text
python -m pytest tests/test_greeks_iv_validation.py
python -m pytest
python -c "from dopey_options.greeks_validation import GreekVector, summarize_greek_exposure; from dopey_options.iv_surface_fixture import IV_FIXTURE_MODEL_VERSION; print('GREEKS_IV_IMPORT_OK', GreekVector(0.1,0.01,-0.02,0.03,0.0,0.2,'smoke','ok').to_dict()['delta'], IV_FIXTURE_MODEL_VERSION)"
python -m dopey_tournament.run_fixture_tournament
Blunder SHA256 manifest check via PowerShell
```

Results:

- `tests/test_greeks_iv_validation.py`: 21 passed
- Full suite: 110 passed
- Import smoke: `GREEKS_IV_IMPORT_OK 0.1 dopey-iv-fixture-model-v1`
- Tournament smoke: `tournament_status: ok`
- Blunder integrity: `BLUNDER_INTEGRITY_OK checked=78`

## Limitations

- Greeks and IV outputs are deterministic fixture math, not calibrated market-data models.
- Attribution quality is a deterministic decomposition, not empirical PnL explanation.
- The IV surface/skew/term summaries use fixture contracts only.
- No queue position, partial fill, routing, live quote, or broker execution behavior is modeled.
- Attribution quality is intentionally low for some families, and that remains visible as a
  failure mode rather than hidden.

## Next recommended build target

Improve deterministic option-structure construction so family legs express intended Greeks more
directly, especially compression negative vega/positive theta and directional positive gamma.

## IV Surface Skew Expansion Addendum

`DOPEY_IV_SURFACE_SKEW_EXPANSION_BUNDLE_V1` extends the original Greeks/IV fixture layer with
deterministic surface grids, skew profiles, term-structure states, and volatility-regime
transitions. The expanded model adds IV crush, IV expansion, premium overpayment, front-event
bump, backwardation, wing elevation, skew-trap, and surface-instability fields to replay results.

Tournament Greek/IV summaries now include average IV surface fit, family IV fit, skew/term score,
premium overpayment, IV crush, IV expansion, front-event bump, skew trap, wing elevation, surface
instability, term-structure risk, and IV mismatch. Latest champion Greek/IV surface metrics:

- Champion: `genome-directional-convexity-spy-fixture-v1`
- Average Greek fit: `0.79654`
- Average IV surface fit: `0.44432`
- Average family IV fit: `0.403497`
- Average skew/term score: `0.712775`
- Worst IV surface scenario: `premium_overpayment_trap`

Validation refresh:

- `python -m pytest` -> `227 passed`
- `python -m dopey_options.run_iv_surface_skew_bundle` -> `bundle_status: ok`
- Import smoke -> `IV_SURFACE_SKEW_IMPORT_OK scenarios=12 families=4`

Limitations remain unchanged: these are deterministic fixtures and paper-replay scores, not live
calibrated IV surfaces or performance evidence.
