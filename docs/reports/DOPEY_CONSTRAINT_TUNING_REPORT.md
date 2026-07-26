# DOPEY Constraint Tuning Report

## Scope

The constraint-tuning layer maps mined failure classes into bounded replay-only recommendations.
It sharpens future fixture mutation and scoring decisions without altering live settings,
broker adapters, or safety gates.

## Failure-Class Mapping

| Failure class | Replay-only tuning recommendations |
|---|---|
| `high_spread_bad_fill_failure` | tighten max spread threshold, increase slippage penalty, increase liquidity minimum, reduce short-duration aggressiveness in bad-fill windows |
| `low_liquidity_decay_failure` | increase minimum fillability score, penalize low OI/volume more strongly, require stronger liquidity robustness |
| `IV_crush_against_vol_expansion` | raise IV expansion threshold, penalize IV-crush risk, increase theta/premium overpayment penalty, require stronger event-vol confirmation |
| `macro_shock_against_compression` | strengthen macro-shock avoidance, penalize compression in risk-off windows, increase breakout/macro contradiction penalty |
| `fakeout_against_directional` | increase fakeout penalty, require stronger pattern confirmation, tighten invalidation sensitivity |
| `theta_decay_against_short_duration` | reduce theta tolerance in chop/liquidity-decay windows, require cleaner breakout confirmation, strengthen time-decay invalidation |
| `overfit_train_only` / `holdout_collapse` | increase holdout weighting, increase overfit penalty, reduce train-only promotion score, require multi-regime consistency |
| `unsafe_structure_rejected` | add mutation ban pattern, strengthen family envelope validation, record blocked mutation type |

## Family-Specific Guard Changes

- `directional_convexity`: added replay-only fakeout pattern preference, tighter invalidation,
  liquidity tightening, and holdout weighting candidates.
- `volatility_expansion`: added IV confirmation, theta/premium guard, bad-fill avoidance, and
  holdout weighting candidates.
- `volatility_compression`: added macro-shock regime guard, credit-spread slippage guard,
  bad-fill avoidance, and overfit penalty candidates.
- `short_duration_defined_risk`: added stricter liquidity, stricter slippage, lower theta
  tolerance, and tighter invalidation candidates.

## Advisory vs Accepted

- Recommendations generated: `65`
- Candidate decisions accepted: `3`
- Candidate decisions rejected: `13`
- Advisory-only recommendations: `41`
- Best accepted replay-only candidate:
  `genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern`

Advisory recommendations are stored for future replay batches. Accepted recommendations only
affect deterministic offline candidate selection and ProofLedger evidence.

## Safety Rules

Every recommendation carries these rules:

- replay-only
- paper-only
- live trading disabled
- defined risk required
- no naked undefined-risk selling
- no broker connection

The layer does not change `mode`, `live_trading_enabled`,
`funded_broker_connections_enabled`, `allow_unofficial_robinhood_api`, `LiveOrderGate`,
PaperBroker, or live broker stubs.
