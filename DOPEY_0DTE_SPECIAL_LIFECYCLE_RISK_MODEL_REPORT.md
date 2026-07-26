# DOPEY 0DTE Special Lifecycle Risk Model Report

## Objective

`DOPEY_0DTE_SPECIAL_LIFECYCLE_RISK_MODEL_V1` adds a dedicated offline risk
gate for 0DTE long-premium equity option candidates. The model allows 0DTE
only when a paper candidate clears stricter liquidity, spread, slippage,
Greeks, IV, event, proof, lifecycle, and risk-cap controls.

## Model Inputs

The model evaluates deterministic fixture fields for candidate identity,
underlying, call/put type, expiry/trade date, strike, moneyness, quote,
spread, volume, open interest, implied volatility, IV rank, Greeks, liquidity,
slippage, event risk, regime alignment, trend/reversal evidence, macro risk,
proof score, signal confidence, expected hold minutes, explicit thesis, and
explicit exit or expiry plan.

## Thresholds

Thresholds are loaded from
`dopey_data/fixtures/active_trading_policy/zero_dte_risk_thresholds.json`.
Defaults are strict:

- spread cap: `0.04`
- minimum volume: `1000`
- minimum open interest: `2000`
- minimum liquidity score: `0.74`
- max slippage score: `0.30`
- max gamma instability score: `0.58`
- max theta decay pressure: `0.50`
- minimum proof score: `0.72`
- minimum signal confidence: `0.68`
- max paper premium at risk per trade: `500.0`
- max approved 0DTE candidates per day: `3`

## Decisions And Risk Tiers

Allowed decisions include `approved_for_paper_open`,
`approved_with_throttle`, `blocked_*`, `prefer_non_zero_dte_alternative`,
`expiry_managed_only`, and `rejected`. Risk tiers are
`low_fixture_risk`, `moderate_fixture_risk`, `high_fixture_risk`, and
`blocked_fixture_risk`.

## Blocked Reasons

Blocked candidates receive explicit reason codes for liquidity, spread,
slippage, IV/premium overpayment, theta decay, gamma instability, event or
macro risk, missing thesis, missing exit plan, missing proof, sell-to-open,
unsupported structures, undefined risk, paper/live safety violations, and
live-path attempts.

## Approved And Throttled Behavior

Approved candidates receive a deterministic decision hash, a threshold version,
paper-only/live-blocked state, an expiry handling plan, a max paper premium at
risk, and max paper contracts. Throttled candidates receive lower paper
premium and contract caps.

## Special Close And Expiry Management

0DTE special close remains separate from normal day trading. Same-day special
close requires an explicit reason, risk cap approval, liquidity approval,
0DTE lifecycle state, and audit proof. `expiry_managed_only` candidates are
recorded as restricted expiry-handling cases, not discretionary intraday churn.

## Integrations

- Account ledger rejects 0DTE opens without `approved_for_paper_open` or
  `approved_with_throttle`.
- Account ledger stores 0DTE risk decision, paper premium cap, contract cap,
  and expiry handling plan in position policy flags.
- Rotation planner blocks rejected 0DTE entries and can recommend a
  non-0DTE alternative.
- PaperBroker rejects 0DTE orders lacking risk model approval.
- Audit, reporting, export, and export review include the 0DTE risk artifacts.

## Validation

Targeted validation includes 57 new 0DTE risk model tests plus existing 0DTE
lifecycle, account ledger, rotation planner, PaperBroker, and active policy
regressions. Full-suite timeout status must remain `inconclusive_timeout`
unless a complete full pytest run actually finishes.

## Limitations

This is deterministic fixture math only. It is not live market data, broker
connectivity, legal advice, tax advice, regulatory advice, performance
evidence, or a profit claim.

## Safety State

- mode: `RESEARCH`
- fixture_only: `true`
- paper_only: `true`
- live_trading_enabled: `false`
- funded_broker_connections_enabled: `false`
- allow_unofficial_robinhood_api: `false`
- broker_connection: `none`
- credentials_used: `false`
- scheduler: `false`
- live_blocked: `true`

## Expiry Outcome Replay Integration

The 0DTE risk model now feeds `DOPEY_0DTE_EXPIRY_OUTCOME_REPLAY_SIMULATOR_V1`.
Replay consumes approved, throttled, blocked, expiry-managed-only, and
later-expiry-alternative source decisions without mutating the source risk
decisions.

Replay feedback is advisory only. It can mark a fixture block as validated,
flag a blocked candidate as maybe too strict, recommend stricter throttles,
or prefer later expiry more often. It cannot approve real trades, weaken the
risk model, alter live thresholds, or create same-day churn authority.

Special-close replay remains tied to explicit lifecycle reason codes,
liquidity approval, risk-cap approval, audit proof, paper-only state, and
live-blocked state.
## 0DTE Threshold Optimizer Integration

`DOPEY_0DTE_THRESHOLD_FEEDBACK_OPTIMIZER_V1` generates offline threshold candidate profiles from replay feedback and validates them through shadow replay.

The recommended profile remains paper-only and promotion-gated. It does not create live approval, does not mutate the default threshold fixture, and does not weaken special lifecycle, no-day-trade, thesis, exit-plan, liquidity, risk-cap, or broker boundaries.
## Adversarial Fixture Coverage Pressure

The 0DTE special lifecycle risk model is now covered by adversarial fixture pressure from the expanded corpus. The corpus includes 10 special-close stress cases, 8 expiry-management stress cases, and 6 policy-loophole adversarial cases. Same-day churn attempts, unsupported structure attempts, and live-path attempts remain blocked in the adversarial replay proof layer.

The added pressure is fixture-only and cannot create live confidence, broker execution, or same-day open/close permission.
