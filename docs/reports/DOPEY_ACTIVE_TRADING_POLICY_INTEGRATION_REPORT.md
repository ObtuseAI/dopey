# DOPEY Active Trading Policy Integration Report

Session date: 2026-07-03

## Objective

`DOPEY_ACTIVE_TRADING_POLICY_INTEGRATION_AND_FULL_VALIDATION_STABILIZER_V1`
integrates the active long-premium options policy beyond the standalone
governor kernel. The bundle remains offline, fixture-only, paper-only, and
live-blocked.

## Enforcement Points

The deterministic integration map is written to:

- `artifacts/dopey/governor/active_policy_integration_map.json`
- `ACTIVE_POLICY_INTEGRATION_MAP.md`

It records 14 enforcement points:

- strategy genome generation
- strategy mutation
- structure builder
- tournament candidate validation
- order intent creation
- order intent validator
- PaperBroker
- simulated position ledger
- simulated close/exit evaluator
- 0DTE lifecycle handler
- meta-governor
- ProofLedger
- evidence audit
- reporting/export review

## Allowed Actions

Active-policy order lifecycle allows:

- buy-to-open long call
- buy-to-open long put
- sell-to-close existing long call on the next trading day or later
- sell-to-close existing long put on the next trading day or later
- explicitly approved 0DTE special lifecycle handling

## Rejected Actions

Active-policy validation and PaperBroker enforcement reject:

- sell-to-open call
- sell-to-open put
- naked option sale
- uncovered writing
- undefined-risk structure
- unsupported multi-leg spread
- close without matching open position
- close before open
- normal same-day open/close round trip
- live order flag

The deterministic rejection codes include:

- `unsupported_short_option_leg`
- `naked_option_sale_rejected`
- `undefined_risk_structure_rejected`
- `same_day_round_trip_rejected`
- `close_without_open_position_rejected`
- `unsupported_multileg_structure_rejected`
- `live_order_rejected`
- `zero_dte_requires_special_lifecycle`
- `zero_dte_policy_violation`

## 0DTE Lifecycle Handling

0DTE is modeled as a special lifecycle path, not a normal day-trading loophole.
The 0DTE evaluator requires explicit lifecycle state, liquidity approval, risk
cap approval, and reason code for same-day special handling.

Proof path:

- `artifacts/dopey/governor/zero_dte_lifecycle_proof.jsonl`

## No-Day-Trade Guard

The no-day-trade guard rejects normal same-day round trips and allows normal
sell-to-close only on the next trading day or later. 0DTE expiry handling is
separate and must pass the 0DTE lifecycle rules.

Proof path:

- `artifacts/dopey/governor/no_day_trade_guard_proof.jsonl`

## PaperBroker Enforcement

PaperBroker now independently enforces active-policy intents. Even if upstream
validation is skipped, PaperBroker rejects active-policy sell-to-open, same-day
normal close, unsupported active spreads, and live flags.

Proof path:

- `artifacts/dopey/governor/active_policy_paperbroker_proof.jsonl`

## Order-Intent Enforcement

`dopey_execution.order_intent_validator.validate_intent()` now returns
`active_policy_errors` for active-policy intents and keeps existing validation
errors intact.

Proof path:

- `artifacts/dopey/governor/active_policy_order_validation_proof.jsonl`

## Strategy, Mutation, and Structure Constraints

`dopey_governor.active_policy_compliance` defines active generation templates
for long calls, long puts, swing calls/puts, rotation calls/puts, and guarded
0DTE calls/puts. It rejects short option mutation, same-day churn mutation,
unsupported spread complexity, and live execution mutation.

`dopey_options.structure_builder` now labels legacy multi-leg structures as
`research_legacy_unsupported` / `not_active_trading_policy_compliant` without
deleting historical fixture behavior.

## Audit Integration

`dopey_audit.active_policy_audit` writes and checks:

- active policy kernel
- fixture cases
- integration map
- no-day-trade guard
- 0DTE lifecycle rules
- order-validation proof
- position-lifecycle proof
- PaperBroker proof
- no forbidden live decisions

Audit smoke result:

- `python -m dopey_audit.run_offline_evidence_replay_audit`
- verdict: `pass`
- safety_errors: `0`
- forbidden_live_decisions_active: `0`

## Reporting and Export Integration

Reporting dashboard evidence now includes active policy audit state, allowed
strategy universe, rejected structure summary, no-day-trade guard summary, 0DTE
lifecycle summary, PaperBroker proof, and live-blocked state.

Export selection now includes active policy reports and proof artifacts. Export
review safety and executive summaries surface active policy state.

## Tests

Targeted tests passed:

- `python -m pytest tests/test_active_trading_policy.py -q`
- `python -m pytest tests/test_pipeline.py tests/test_active_trading_policy.py -q`
- `python -m pytest tests/test_active_policy_integration.py -q`
- `python -m pytest tests/test_position_lifecycle_policy.py -q`
- `python -m pytest tests/test_paperbroker_active_policy.py -q`
- `python -m pytest tests/test_full_validation_stabilizer.py -q`
- `python -m pytest tests/test_text_encoding_guard.py -q`

Slow group probe:

- `python -m pytest tests/test_artifact_compaction_export_verifier.py -q`
- result: `42 passed in 112.55s`

Full suite status remains inconclusive, not passed. The stabilizer collected
654 tests, timed out the full suite probe after 30 seconds, and recorded
`timeout_recorded_as_pass=false`.

## Known Gaps

- Legacy vertical/spread fixtures remain present for historical research tests
  and are marked noncompliant for active trading rather than deleted.
- Full pytest is too slow for a single unbounded pass in this environment; the
  export verifier file alone takes about 112 seconds.
- Active policy is still paper/offline governance. It is not a broker
  connection, live trading system, or performance claim.

## Account Ledger And Rotation Planner Integration

`DOPEY_NO_DAY_TRADE_ACCOUNT_LEDGER_AND_PDT_SAFE_ROTATION_PLANNER_V1`
adds account-level lifecycle tracking before exits are approved. DOPEY may
rotate and swing trade aggressively by opening new compliant long-call or
long-put positions, but normal same-day close of the same position is blocked
and converted into a delayed-exit or delayed-rotation plan.

New enforcement layers:

- `dopey_execution.account_ledger`
- `dopey_execution.day_trade_policy`
- `dopey_execution.pdt_safe_policy`
- `dopey_execution.rotation_planner`
- `dopey_execution.run_account_ledger_rotation_planner`

The configurable policy layer models conservative offline PDT-safe planning
without making legal claims. 0DTE remains special lifecycle handling, not a
normal day-trading loophole. PaperBroker now consults and updates the paper
account ledger for active-policy orders.

## Dedicated 0DTE Risk Model Integration

The active policy map now includes `0dte_special_lifecycle_risk_model` in
`dopey_options.zero_dte_decision_engine`. This gate applies stricter 0DTE
controls before account-ledger entry:

- strict liquidity, spread, and slippage controls
- gamma instability and theta decay controls
- IV shock and premium-overpayment controls
- event, macro, and regime-alignment controls
- proof score and signal confidence controls
- explicit thesis and exit or expiry plan requirements
- max paper premium and contract caps
- paper-only/live-blocked enforcement

Reason-code taxonomy includes blocked liquidity, spread, slippage, IV shock,
theta decay, gamma instability, event risk, weak thesis, missing exit plan,
missing proof, policy violation, live path, non-0DTE alternative preference,
and expiry-managed-only classification.

## 0DTE Replay Advisory Integration

The active policy map now includes `0dte_expiry_outcome_replay_simulator` in
`dopey_options.zero_dte_replay_engine`. This layer replays 0DTE paper outcomes
through deterministic fixture paths and publishes advisory feedback only.

Replay outputs do not weaken the no-day-trade policy. Special-close outcomes
remain controlled by explicit 0DTE lifecycle rules, reason codes, liquidity
approval, risk-cap approval, paper-only state, and live-blocked state.

Replay feedback can inform future paper simulations and later-expiry
preference, but cannot approve live trading, broker execution, real market
data use, or automatic promotion of blocked candidates.
## 0DTE Threshold Feedback Optimizer

The active policy integration map now includes `0dte_threshold_feedback_optimizer` as an enforcement point. The optimizer is advisory and fixture-only: it can produce paper-shadow or research-default candidate artifacts, but it cannot enable live trading, broker routing, same-day churn, unsupported structures, or live threshold mutation.
