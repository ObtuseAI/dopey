# DOPEY Active Trading Canon Policy Report

Session date: 2026-07-03

## Scope

Converted the attached research report into enforceable DOPEY doctrine for
active long-premium equity and ETF options. The implementation is deterministic,
offline, fixture-backed, paper-only, and does not enable live trading.

## Research Sources Used

- User-provided report:
  `C:\Users\CH\.codex\attachments\22557764-db5d-4d2f-9a07-c34bf81d122d\pasted-text.txt`
- Robinhood Agentic Trading overview:
  `https://robinhood.com/us/en/support/articles/agentic-trading-overview/`
- Robinhood expiration, exercise, and assignment:
  `https://robinhood.com/us/en/support/articles/expiration-exercise-and-assignment/`
- Robinhood option order pages:
  `https://robinhood.com/us/en/support/articles/limit-order-options/`
  `https://robinhood.com/us/en/support/articles/market-order-options/`
  `https://robinhood.com/us/en/support/articles/stop-market-order-options/`
  `https://robinhood.com/us/en/support/articles/options-chain-metrics/`
- Robinhood basic and advanced options strategy pages:
  `https://robinhood.com/us/en/support/articles/basic-options-strategies/`
  `https://robinhood.com/us/en/support/articles/advanced-options-strategies/`
- FINRA 0DTE investor guidance:
  `https://www.finra.org/investors/insights/zeroing-in-options-trading-strategy`
- FINRA frequent intraday trading guidance:
  `https://www.finra.org/investors/insights/frequent-intraday-trading`
- SEC options market structure roundtable supporting data:
  `https://www.sec.gov/files/roundtable-options-market-structure.pdf`

## Implemented Artifacts

- `dopey_governor/active_trading_policy.py`
  - Adds `ACTIVE_TRADING_POLICY_VERSION =
    dopey-active-long-premium-options-policy-v1`.
  - Adds pure dataclass models for candidates, thresholds, decisions, and
    recursive improvement proposals.
  - Adds strategy-universe checks for equity/ETF underliers, long-premium or
    net-debit structures, defined risk, no uncovered short options, liquidity,
    spread, open-interest, volume, forecast-move score, convexity-value score,
    surface quality, and multi-signal confirmation.
  - Adds lifecycle rules for swing-first behavior, 0DTE exception states,
    long-put exercise fragility, forced-broker-liquidation tolerance, and
    same-day round-trip rejection.
  - Adds execution rules that require limit pricing for openings and permit
    market-style exits only as explicit emergency sell-to-close fail-safes.
  - Adds recursive improvement gates that allow alpha-layer changes only after
    offline evidence checks and reject any safety-layer weakening or live
    enablement.
- `dopey_governor/__init__.py`
  - Exports the active trading policy kernel.
- `dopey_data/fixtures/active_trading_policy/long_premium_policy_cases.json`
  - Adds offline policy fixtures covering approved swing premium, approved
    event 0DTE, rejected 0DTE put exercise, rejected same-day churn, rejected
    market opening order, rejected undefined short-vol, rejected illiquid chain,
    rejected premium overpayment, approved alpha-layer recursive improvement,
    rejected safety-layer mutation, and rejected overfit mutation.
- `tests/test_active_trading_policy.py`
  - Adds deterministic coverage for canon records, fixture verdicts, 0DTE
    budget/lifecycle constraints, recursive improvement safety, and stable
    serialization.
- `DOPEY_CANON.md`
  - Appends the active long-premium policy canon section.

## Policy Kernel

The kernel enforces these hard safety rules:

- Paper-only until explicit future live enablement.
- No uncovered or undefined-risk options.
- Long-premium or net-debit structures only.
- Limit orders for opening trades.
- No default same-day round-trip churn.
- 0DTE requires a declared lifecycle state.
- Recursive improvement cannot weaken the safety layer.

Allowed adaptive layers are limited to:

- signal ranking;
- regime weighting;
- execution thresholds;
- ensemble allocation;
- surface model calibration.

The hard safety layer is not adaptive.

## Strategy-Universe Constraints

The active universe is constrained to liquid equity and ETF options. A candidate
must pass all of these gates before it can become a paper policy candidate:

- approved strategy sleeve:
  `directional_continuation_rotation`,
  `volatility_surface_relative_value`,
  `event_convexity`, or `flow_fundamental_asymmetry`;
- approved long-premium or net-debit structure;
- no forbidden structure type such as naked calls, naked puts, short straddles,
  short strangles, credit spreads, short iron condors, or undefined short vol;
- defined risk;
- no uncovered short option marker;
- liquidity score, spread, open interest, and volume above policy thresholds;
- favorable forecast-move score;
- favorable convexity-value score;
- acceptable surface-quality score;
- at least three independent confirmations across catalyst, flow,
  fundamental, and technical context.

## Lifecycle Rules

Swing-first positions use `swing_hold`, `planned_exit`, or `planned_roll`.

0DTE is not the default personality. It is allowed only through one of these
declared exception states:

- `hold_to_expiration_worthless_tolerant`;
- `exercise_capable`;
- `forced_broker_liquidation_tolerant`.

The 0DTE path carries tighter spread and size caps. The forced-broker-liquidation
state is capped separately and must be explicitly tolerated. A 0DTE long put
using `exercise_capable` is rejected unless short-stock capacity is explicitly
available, because exercising a long put can create short stock exposure.

## Recursive Improvement Rules

The policy allows recursive improvement only in model beliefs and offline paper
allocation behavior. A proposal must pass out-of-sample, CPCV-style, deflated
Sharpe, and multiple-testing penalty checks. Any proposal that touches hard
safety rules, weakens the safety layer, requests live enablement, or leaves
paper-only mode is rejected regardless of apparent score.

## Validation

Passed:

```text
python -m pytest tests/test_active_trading_policy.py
5 passed in 0.18s
```

Passed:

```text
python -m pytest tests/test_pipeline.py tests/test_active_trading_policy.py
15 passed in 0.30s
```

Import check passed:

```text
python -c "import dopey_governor; from dopey_governor.active_trading_policy import active_trading_canon_record; print(active_trading_canon_record()['policy_version'])"
dopey-active-long-premium-options-policy-v1
```

Full-suite validation was attempted twice but remains inconclusive:

- `python -m pytest` timed out after 120 seconds.
- `python -m pytest -q` timed out after 302.9 seconds and pytest hit
  `OSError: [Errno 22] Invalid argument` while flushing terminal output during
  shutdown.

No full-suite failure was observed before timeout, but the run did not produce a
complete pass/fail signal.

## Safety State

The change does not connect a broker, request credentials, fetch live market
data, schedule automation, modify original Blunder sources, enable funded
broker connections, enable live trading, or relax `LiveOrderGate`.

`live_allowed=true` remains rejected by existing execution and pipeline tests.

## Practical Meaning

Dopey is now stricter and more explicit about what "active" means:

- active does not mean maximum trade count;
- aggressive does not mean max size through bad regimes;
- adaptive does not mean safety-rule drift;
- 0DTE does not mean default churn;
- long premium does not mean buying overpriced convexity.

The policy now encodes the research report as a reviewable, testable offline
kernel that future ranking, tournament, walk-forward, and execution-intent layers
can call before any paper candidate is promoted.

## Integration Update: Active Policy System Layer

Session date: 2026-07-03

The active trading policy is now integrated beyond the standalone governor kernel.

Added system enforcement:

- active policy integration map and CLI
- order-intent active-policy validation reason codes
- no-day-trade guard
- 0DTE special lifecycle evaluator
- offline position lifecycle ledger
- PaperBroker independent active-policy enforcement
- strategy/mutation/structure compliance helpers
- active policy audit artifacts and proof records
- reporting/export/export-review active policy summaries
- full validation stabilizer
- non-mutating text encoding guard

Key proof paths:

- `artifacts/dopey/governor/active_policy_integration_map.json`
- `artifacts/dopey/governor/active_policy_order_validation_proof.jsonl`
- `artifacts/dopey/governor/active_policy_position_lifecycle_proof.jsonl`
- `artifacts/dopey/governor/active_policy_paperbroker_proof.jsonl`
- `artifacts/dopey/governor/zero_dte_lifecycle_proof.jsonl`
- `artifacts/dopey/governor/no_day_trade_guard_proof.jsonl`
- `artifacts/dopey/audit/active_policy_audit.jsonl`

Safety state remains research-only, paper-only, fixture-only, and live-blocked.
