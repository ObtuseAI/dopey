# DOPEY 0DTE Empirical Fixture Expansion And Adversarial Replay Corpus Report

## Objective

DOPEY_0DTE_EMPIRICAL_FIXTURE_EXPANSION_AND_ADVERSARIAL_REPLAY_CORPUS_V1 expands the 0DTE proof environment with a harder deterministic replay corpus before threshold candidates can move beyond paper-shadow status.

The word empirical here means fixture-empirical inside DOPEY's deterministic offline corpus. It does not mean real-market empirical proof, live profitability proof, predictive confidence, broker execution evidence, or live readiness.

## Corpus Expansion Summary

- Baseline replay cases: 24
- New adversarial cases: 99
- Combined corpus cases: 123
- Adversarial intraday paths: 99
- Replay expectation match: true
- Feedback expectation match: true
- Optimizer effect expectation match: true
- Paper-only: true
- Live-blocked: true
- Real market data: none
- Broker path: none

## Case-Family Distribution

- approved_candidate_stress: 16
- blocked_candidate_validation: 16
- blocked_maybe_overstrict: 12
- throttled_candidate_stress: 10
- later_expiry_alternative: 10
- special_close_stress: 10
- expiry_management_stress: 8
- gamma_theta_adversarial: 8
- policy_loophole_adversarial: 6
- liquidity_spread_adversarial: 1
- iv_event_adversarial: 1
- regime_reversal_adversarial: 1

## Risk-Vector Distribution

- liquidity_decay: 9
- spread_explosion: 6
- slippage_spike: 5
- gamma_reversal: 4
- theta_bleed: 5
- iv_crush: 2
- iv_overpayment: 3
- event_shock: 2
- macro_reversal: 7
- false_breakout: 2
- false_breakdown: 1
- pin_risk: 7
- late_day_liquidity_collapse: 5
- missing_thesis: 8
- missing_exit_plan: 10
- same_day_churn_attempt: 8
- unsupported_structure_attempt: 7
- live_path_attempt: 8

## Adversarial Path Builder

The path builder generates deterministic intraday records from fixture cases. Each path includes underlying movement, option bid/mid/ask movement, spread and slippage shocks, liquidity decay, delta/gamma/theta/vega paths, IV movement, event shock timing, macro reversal timing, close and special-close timing, expiry pressure, and pin-risk state.

No randomness, external calls, market data, broker connection, credential use, or scheduler is used.

## Combined Replay Results

- Baseline fixture count: 24
- Adversarial fixture count: 99
- Combined fixture count: 123
- Policy loophole block rate: 1.0
- Special-close stress count: 10
- Expiry-management stress count: 8
- Overfit-pressure score: 1.0

## Optimizer Impact

The threshold optimizer now writes adversarial corpus context into the optimizer summary. The stricter_gamma_theta_profile remains the selected offline paper-shadow threshold candidate, but the post-adversarial recommendation is paper_shadow_only_no_research_default_promotion.

Research-default promotion remains blocked because adversarial pressure is high and the corpus is fixture-only evidence.

## Coverage Scoring

- Coverage completeness score: 1.0
- Case-family coverage score: 1.0
- Risk-vector coverage score: 1.0
- Policy-loophole coverage score: 1.0
- Overfit-pressure score: 1.0
- Missing coverage areas: none in v1 scoring
- Recommended next fixture additions: cross-underlying regime families, paired call/put macro shocks, and more overstrict blocked replay variants

## Audit, Reporting, Export, And Review Integration

The active policy audit recognizes adversarial fixture cases, paths, replay outcomes, threshold feedback, optimizer effects, coverage summary, combined replay summary, and proof records.

Reporting and export review surfaces adversarial corpus size, distributions, policy loophole block rate, overfit pressure, threshold candidate survival status, and paper-only/live-blocked state. Export selection includes the adversarial artifacts and this report.

## Validation

Targeted adversarial tests passed: 86 passed.

Sequential targeted regression shards passed:

- zero_dte_threshold_optimizer: 67 passed
- zero_dte_outcome_replay plus zero_dte_risk_model: 133 passed
- zero_dte_account_lifecycle plus account ledger, rotation planner, and paperbroker ledger: 57 passed
- active_policy_integration plus active_trading_policy: 32 passed

Parallel execution of artifact-writing shards can race on shared JSONL outputs. Sequential targeted shards are the reliable validation mode for these artifact writers.

Full pytest remains not claimed as pass unless it completes. A timeout must remain inconclusive_timeout.

## Limitations

- Fixture-empirical evidence only.
- No live profitability proof.
- No predictive confidence claim.
- No real market data.
- No broker execution.
- No live/default threshold mutation.
- No same-day churn loophole.
- No research-default promotion from this corpus alone.

## Safety State

- Live trading disabled.
- Broker execution absent.
- Robinhood, Alpaca, and Tradier live stubs still block live order attempts.
- Credentials not created.
- Scheduler not created.
- Original Blunder untouched by this bundle.

## Cross-Underlying V2 Support

`DOPEY_0DTE_ADVERSARIAL_CORPUS_V2_CROSS_UNDERLYING_REGIME_FAMILIES_V1` extends this corpus with 192 deterministic synthetic cross-underlying 0DTE cases. The combined baseline plus adversarial v1 plus cross-underlying v2 corpus now has 315 cases.

The v2 runner supports `baseline`, `adversarial_v1`, `cross_underlying_v2`, and `combined_v1_v2` modes. The default mode writes the v2 replay outcomes, threshold feedback, optimizer effects, coverage summary, combined v1/v2 summary, threshold survival report, and proof ledger under `artifacts/dopey/zero_dte_cross_underlying_v2`.

Cross-underlying v2 records `stricter_gamma_theta_profile` as paper-shadow only, downgrades non-gamma/theta paper-shadow candidates to advisory-only under cross-underlying pressure, preserves negative-control rejection, and keeps research-default promotion blocked.
