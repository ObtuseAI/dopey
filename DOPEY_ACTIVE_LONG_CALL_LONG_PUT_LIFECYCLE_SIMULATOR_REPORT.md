# DOPEY Active Long Call / Long Put Lifecycle Simulator Report

## Objective

`DOPEY_ACTIVE_LONG_CALL_LONG_PUT_LIFECYCLE_SIMULATOR_V1` adds an offline, deterministic, fixture-only simulator for complete active long-premium option lifecycles. It models signal, candidate build, active policy validation, risk validation, paper allocation, portfolio/stress/incident gates, PaperBroker paper open, account ledger recording, hold/manage, delayed rotation, next-day close, 0DTE special close or simulated expiry, proof output, audit, reporting, export, and review.

## Scope

This bundle is paper-only and fixture-only. It does not enable live trading, broker execution, Robinhood, credentials, real market data, account connection, scheduling, buying power, account balance, real sizing, or deployment.

## Lifecycle Model

The new `dopey_lifecycle` package defines deterministic records for `ActiveOptionLifecycle`, `LifecycleState`, `LifecycleTransition`, and `LifecycleProofRecord`. Allowed option types are `call` and `put`. Allowed strategy types are `zero_dte_long_call`, `zero_dte_long_put`, `swing_long_call`, `swing_long_put`, `delayed_rotation_long_call`, and `delayed_rotation_long_put`.

## Transition Policy

The lifecycle policy blocks sell-to-open, naked sale, unsupported spread, undefined-risk structure, live path injection, broker path injection, credential reference, scheduler emergence, real sizing reference, PaperBroker override, terminal-block auto-recovery, and full-suite-timeout-as-pass. It preserves normal same-day close rejection, 0DTE special lifecycle proof, and next-day-or-later swing exits.

## Simulator Engine

The simulator writes 136 deterministic lifecycle cases:

- 16 swing long-call cases
- 16 swing long-put cases
- 16 0DTE long-call expiry-managed cases
- 16 0DTE long-put special-close cases
- 12 delayed rotation cases
- 12 no-day-trade blocked close cases
- 8 incident-interrupted cases
- 8 stress-interrupted cases
- 8 PaperBroker rejection cases
- 24 negative-control and boundary cases

## PaperBroker Adapter

`PaperBrokerLifecycleAdapter` translates lifecycle open and close requests into existing `ExecutionIntent` objects and delegates to the existing `PaperBroker`. It rejects live paths, sell-to-open, close-without-open, same-day normal close, and PaperBroker override attempts without bypassing broker authority.

## Account Ledger Adapter

`AccountLedgerLifecycleAdapter` delegates open and close decisions to the existing account ledger and day-trade policy. It records close eligibility, delayed rotation, 0DTE state, and same-day close rejection. Ledger mismatch and missing audit proof are routed to audit-only/manual-review style lifecycle states.

## Lifecycle Summary

- lifecycle_case_count: 136
- state_count: 1686
- transition_count: 1550
- proof_record_count: 1686
- paper_open_count: 92
- paper_close_count: 60
- blocked_transition_count: 60
- no_day_trade_block_count: 169
- delayed_rotation_count: 12
- zero_dte_special_lifecycle_count: 33
- zero_dte_expiry_managed_count: 16
- swing_next_day_close_count: 32
- paperbroker_rejection_count: 21
- account_ledger_mismatch_count: 2
- incident_interruption_count: 8
- stress_interruption_count: 8
- terminal_block_count: 16

## Feedback Integration

Lifecycle feedback is written for allocator, portfolio replay, stress ladder, and incident response. Feedback is advisory only and cannot mutate live defaults, allocation defaults, portfolio state, stress ladder defaults, or incident response policy.

## Audit / Reporting / Export

Offline evidence replay audit recognizes all 12 lifecycle artifacts. Reporting includes `active_lifecycle_summary`. Export selection and export review include lifecycle summary, states, transitions, proof, PaperBroker results, account ledger results, and feedback artifacts.

## Validation

Targeted lifecycle tests pass: `python -m pytest tests/test_active_option_lifecycle_simulator.py -q` -> 132 passed.

Dependent requested shards passed sequentially. Smokes passed through audit, reporting, export, export review, and validation stabilizer. `python -m pytest --collect-only -q` collected 1835 tests. Bounded full `python -m pytest` timed out after 125.03 seconds and is recorded as `inconclusive_timeout`, not pass.

## Limitations

Evidence is deterministic fixture evidence only. It is not live-readiness, profitability, predictive power, market accuracy, broker capability, or empirical trading proof. Full pytest remains inconclusive under the bounded timeout.

## Safety State

Live trading remains disabled. Broker connection remains absent. Credentials remain absent. Scheduler remains absent. Real market data remains absent. Real sizing and buying-power logic remain absent. Original Blunder was not modified. No git commit was created.

## Broker-Readiness Consumption

- broker_readiness_preflight_consumes_lifecycle_proof: `true`
- lifecycle_remains_paper_only: `true`
- lifecycle_remains_broker_disconnected: `true`
- broker_readiness_does_not_enable_live_trading: `true`
