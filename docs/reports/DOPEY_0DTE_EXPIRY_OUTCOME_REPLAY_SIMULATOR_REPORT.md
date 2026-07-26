# DOPEY 0DTE Expiry Outcome Replay Simulator Report

## Objective

`DOPEY_0DTE_EXPIRY_OUTCOME_REPLAY_SIMULATOR_V1` adds a deterministic offline simulator for 0DTE long-premium equity option candidates. It replays approved, throttled, blocked, expiry-managed, and later-expiry alternative 0DTE paper candidates through fixture-only intraday and expiry paths.

This is paper-governance evidence only. It does not approve live trades, connect to brokers, request credentials, fetch market data, schedule jobs, or mutate live thresholds.

## Replay Input Model

Replay inputs are represented by `ZeroDTEReplayInput` in `dopey_options/zero_dte_outcome_models.py`. Each input is derived from a source 0DTE risk decision and carries candidate identity, option type, date, strike, open premium, risk caps, risk tier, proof score, liquidity, slippage, Greeks, IV, thesis, exit plan, fixture path, `paper_only=true`, and `live_blocked=true`.

## Intraday Fixture Paths

Fixture paths live at:

- `dopey_data/fixtures/active_trading_policy/zero_dte_outcome_replay_cases.json`
- `dopey_data/fixtures/active_trading_policy/zero_dte_intraday_paths.json`

The corpus contains 24 replay cases and 24 intraday paths. Paths cover trend wins, breakdown wins, spike/fade, theta bleed, chop decay, gamma reversal, IV crush, spread traps, liquidity decay, false breakouts, late rescue, expiry pin, OTM worthless expiry, ITM intrinsic expiry, later-expiry alternative confirmation, validated blocks, inconclusive blocked wins, throttle validation, event risk, and special-close guard behavior.

## Replay Engine

`dopey_options/zero_dte_replay_engine.py` evaluates each replay deterministically. It:

- loads source 0DTE risk decisions;
- pairs each decision with a fixture path;
- builds replay inputs, intraday states, decision points, outcomes, expiry-management records, feedback records, and proof records;
- computes premium outcome, max adverse excursion, max favorable excursion, theta decay, gamma opportunity, and slippage;
- classifies fixture outcomes without randomness or network access.

## Expiry Management Simulator

`dopey_options/zero_dte_expiry_management.py` models paper-only expiry states:

- `expires_worthless_simulated`
- `expires_itm_intrinsic_value_simulated`
- `pin_risk_simulated`
- `assignment_exercise_risk_flagged_simulated_only`
- `expiry_managed_hold_to_close`
- `expiry_managed_special_close`

It records intrinsic value estimates, paper premium outcome, risk flags, special-close risk reduction, and a `broker_instruction` value of `none_simulated_only`.

## Special-Close Replay Guard

Special-close replay is constrained by explicit reason, liquidity approval, risk-cap approval, and 0DTE lifecycle state. Missing reason, liquidity approval, or risk-cap approval creates blocked replay decision points instead of treating 0DTE same-day exits as normal day-trading churn.

## Threshold Feedback

`dopey_options/zero_dte_threshold_feedback.py` emits advisory-only threshold feedback:

- tighten spread, liquidity, gamma, theta, and IV limits where fixtures show pressure;
- prefer later expiry when 0DTE replay confirms the alternative;
- keep validated block reasons;
- mark inconclusive fixture coverage when a blocked setup works in replay.

Feedback records set `advisory_only=true` and `live_threshold_mutation_allowed=false`.

## Recursive Improvement Tags

Replay outcomes carry fixture-only recursive improvement tags such as outcome class, threshold feedback, and candidate-family stricter-filter signals. These tags are evidence labels, not autonomous live promotion.

## Integrations

Account ledger:

- stores advisory `zero_dte_replay_feedback` on position policy flags when provided;
- does not allow replay feedback to override 0DTE risk-model approval.

Rotation planner:

- can convert replay feedback that prefers later expiry into a paper rotation preference;
- does not convert replay feedback into live permission.

PaperBroker:

- records replay feedback in preview/proof records;
- remains `policy_executor_not_optimizer`.

Audit/report/export/review:

- audit inventory recognizes eight replay artifacts;
- active policy audit checks paper-only/live-blocked replay state, advisory-only feedback, and special-close reason integrity;
- reporting summary surfaces replay counts, outcome distribution, threshold feedback, special-close counts, expiry distribution, and later-expiry feedback;
- export/review selectors include replay artifacts and summary.

## Validation

Targeted validation completed:

- `tests/test_zero_dte_outcome_replay.py`: `76 passed`
- `tests/test_zero_dte_risk_model.py tests/test_zero_dte_account_lifecycle.py`: `64 passed`
- `tests/test_account_ledger_policy.py tests/test_rotation_planner.py tests/test_paperbroker_account_ledger.py`: `50 passed`
- `tests/test_active_policy_integration.py tests/test_active_trading_policy.py`: `32 passed`

Smoke validation completed:

- replay runner: `ok`
- risk model runner: `ok`
- account ledger planner: `ok`
- active policy integration: `ok`, enforcement points `19`
- offline evidence replay audit: `pass`, artifacts scanned `80`, records scanned `6397`, safety errors `0`
- reporting bundle: `ok`
- export verifier: `ok`, artifacts selected/exported `110`, credential findings `0`
- export review: `ok`, safety errors `0`
- validation stabilizer: `full_inconclusive_or_failed`, timeout recorded as pass `false`

Collection completed with `844` tests collected. Full `python -m pytest` timed out after about `307.6s` and also hit the known Windows pytest terminal flush `OSError: [Errno 22] Invalid argument`. This is recorded as `inconclusive_timeout`, not pass.

## Limitations

- Fixture-only replay is not empirical performance evidence.
- Outcomes do not imply live predictive power.
- Blocked candidates that work in fixture replay are not promoted; they require more fixture coverage.
- Threshold feedback is advisory and does not mutate live thresholds.
- Full pytest may still require longer orchestration if it times out.

## Safety State

- `mode=RESEARCH`
- `paper_only=true`
- `live_blocked=true`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- no real market data
- no broker connection
- no credentials
- no scheduler
- no live orders
- no git commit

## Threshold Optimizer Integration

`DOPEY_0DTE_THRESHOLD_FEEDBACK_OPTIMIZER_V1` now consumes replay outcomes, expiry-management records, and advisory threshold feedback from this simulator.

The optimizer aggregates replay feedback into deterministic candidate threshold profiles, runs fixture-only shadow replay against the 0DTE risk corpus, rejects unsafe new approvals, and writes promotion-gated paper-only artifacts under `artifacts/dopey/zero_dte_threshold_optimizer`.

Replay feedback remains advisory. Shadow replay validation cannot mutate live/default thresholds, cannot enable broker execution, and cannot convert a blocked-maybe-too-strict result into automatic approval.
## Adversarial Replay Corpus Support

The replay layer now has a companion adversarial corpus runner for baseline, adversarial, and combined summary modes. The default adversarial corpus run writes 99 fixture cases, 99 deterministic intraday paths, and a combined replay summary with 123 baseline plus adversarial cases.

This support remains offline, deterministic, fixture-only, advisory, paper-only, and live-blocked. It does not fetch market data, connect to brokers, place orders, create credentials, or create a scheduler.

## Cross-Underlying Replay Mode

The replay layer now has a cross-underlying v2 companion runner with `combined_v1_v2` as the default mode. It writes 192 synthetic cross-underlying replay cases, 192 intraday paths, and a combined v1/v2 replay summary with 315 total baseline, adversarial v1, and cross-underlying v2 cases.

The cross-underlying paths include underlying price, bid/mid/ask, spread, slippage, liquidity score, delta/gamma/theta/vega, IV, event/macro stress, close signal, special-close signal, expiry pressure, and pin-risk state. The runner remains deterministic, fixture-only, paper-only, and live-blocked.
