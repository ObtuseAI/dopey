# DOPEY Failure Mode Miner Report

## Scope

The failure-mode miner converts deterministic tournament and mutation outcomes into recurring
failure categories, mitigation hints, and mutation-constraint updates. It is a fixture-only
diagnostic layer and does not perform live execution.

## Implemented modules

- `dopey_strategy_lab/failure_mode_miner.py`
- `dopey_strategy_lab/failure_mode_registry.py`
- `dopey_strategy_lab/mutation_constraints.py`
- `dopey_strategy_lab/mutation_scorecard.py`
- `dopey_strategy_lab/run_mutation_population_bundle.py`
- `dopey_tournament/runner.py`
- `dopey_tournament/models.py`
- `dopey_tournament/ledger_tournament.py`

## Model versions

- Failure-mode miner version: `dopey-failure-mode-miner-v1`
- Failure-mode registry version: `dopey-failure-mode-registry-v1`
- Mutation constraint version: `dopey-mutation-constraints-v1`

## Failure modes detected

The latest bundle detects `28` family-specific failure-mode records across all four families.
Detected classes include:

- `high_spread_bad_fill_failure`
- `low_liquidity_decay_failure`
- `IV_crush_against_vol_expansion`
- `macro_shock_against_compression`
- `fakeout_against_directional`
- `theta_decay_against_short_duration`
- `wrong_delta_direction`
- `overfit_train_only`
- `holdout_collapse`
- `poor_greek_fit`
- `pattern_contradiction`
- `slippage_over_sensitivity`
- `regime_mismatch`
- `mutation_drift`
- `unsafe_structure_rejected`

## Top latest failures

- `unsafe_structure_rejected`: all four unsafe family probes rejected before scoring.
- `overfit_train_only`: volatility expansion still carries high train/holdout fragility.
- `IV_crush_against_vol_expansion`: long-vol expansion remains vulnerable to post-event IV crush.
- `high_spread_bad_fill_failure`: compression and short-duration families remain sensitive to
  high-spread fixture fills.
- `low_liquidity_decay_failure`: liquidity-decay regimes still pressure all families.

## Mitigation hints

- Reject undefined-risk structures before scoring.
- Raise validation and holdout consistency before promotion.
- Raise IV-crush avoidance for long-vol expansion.
- Increase bad-fill avoidance weighting.
- Tighten liquidity thresholds.
- Increase fakeout penalty for directional entries.
- Raise macro-shock avoidance for compression.
- Reject family-envelope drift.

## Integration

Failure-mode summaries are written to `artifacts/dopey/failure_modes/failure_mode_registry.jsonl`
and carried into the tournament ProofLedger and champion registry. The mutation scorecard consumes
constraint updates as small deterministic penalties; it does not overwrite the tournament score or
emit live decisions.

## Safety state

The miner is diagnostic only. It makes no network calls, broker calls, live trades, scheduled
runs, or live promotion decisions.

## Failure-Mode Feedback Optimizer Feed

The latest mined failure registry now feeds `dopey-failure-feedback-optimizer-v1`.
The optimizer consumes the top recurring failures, mitigation hints, recurrence counts, regimes,
family labels, and mutation-constraint updates from
`artifacts/dopey/failure_modes/failure_mode_registry.jsonl`.

Current feedback run `failure-feedback-dopey-feedback-v1` converted the latest mined evidence
into `31` aggregate failure slices, `65` bounded constraint recommendations, and `16` valid
feedback-guided replay mutations. The most influential failure classes were
`high_spread_bad_fill_failure`, `low_liquidity_decay_failure`,
`IV_crush_against_vol_expansion`, `overfit_train_only`, `unsafe_structure_rejected`,
`macro_shock_against_compression`, `fakeout_against_directional`, and
`theta_decay_against_short_duration`.

Mitigation hints are consumed as replay-only guidance. They do not overwrite safety settings,
connect to brokers, fetch market data, or promote live trading.
