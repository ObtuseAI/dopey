# DOPEY Proof-Weighted Capital Allocator For Long-Premium Options

## Objective

This bundle implements DOPEY's first deterministic proof-weighted paper allocator for long-premium equity options. It translates offline fixture proof into abstract paper attention, paper premium-at-risk units, and paper contract-unit caps for compliant long-call and long-put opportunities.

This is not real capital allocation. It does not use real balances, buying power, broker balances, market data, or live orders.

## Paper-Only Scope

- mode: `offline_fixture_only`
- paper_only: `true`
- live_blocked: `true`
- broker_execution: `none`
- credentials: `none`
- real_market_data: `none`
- real_sizing: `false`
- scheduler: `none`

## Proof Evidence Inputs

- active trading policy and no-day-trade controls
- paper account ledger and PDT-safe rotation planner
- 0DTE special lifecycle risk model
- 0DTE expiry replay outcomes and threshold feedback
- adversarial v1 corpus
- cross-underlying v2 corpus
- hybrid v3 swing/0DTE replay corpus
- threshold optimizer survival and downgrade signals
- audit/report/export safety summaries

## Allocation Model

The model layer adds:

- `ProofWeightedOpportunity`
- `PaperAllocationDecision`
- `PaperAllocationPlan`
- `PaperRiskBudget`

All sizing values are abstract paper units:

- `paper_attention_weight`
- `paper_premium_risk_units`
- `max_paper_contract_units`

Forbidden real-capital concepts such as dollars, buying power, account balances, credentials, live orders, and broker execution references remain rejected.

## Allocation Policy

The policy rejects live paths, sell-to-open paths, unsupported structures, missing thesis or exit plans, normal same-day churn, poor liquidity, wide spreads, no-trade preferences, and high contradiction cases.

Compliant opportunities can receive:

- `standard_paper` for strong swing candidates
- `aggressive_paper_capped` for high-proof 0DTE candidates
- `small_paper` for moderated or throttled candidates
- `paper_shadow` for insufficient coverage
- `watchlist` or delayed reserve for non-entry advisory states

## Paper Risk Budget

The default budget is aggressive but capped:

- max paper attention per opportunity: `1.0`
- max paper premium risk units per opportunity: `3.0`
- max 0DTE paper exposure share: `0.35`
- max same-regime concentration: `0.28`
- max delayed-rotation reserve: `4.0`
- max paper-shadow exposure: `5.0`

## Exposure Controls

Generated allocation exposure:

- total paper premium risk units: `52.3`
- 0DTE paper premium risk units: `17.9`
- swing paper premium risk units: `32.4`
- 0DTE exposure share: `0.342256`
- 0DTE share status: `within_cap`
- delayed rotation risk units: `2.0`

Swing receives more paper allocation than 0DTE because hybrid v3 evidence favors swing in more cases and 0DTE remains lifecycle-capped.

## Allocation Engine

The engine writes deterministic fixtures and artifacts under:

- `dopey_data/fixtures/allocation`
- `artifacts/dopey/allocation`

It generates:

- 83 proof-weighted opportunities
- 83 allocation decisions
- 30 rejection records
- 22 watchlist records
- 83 allocation proof records

## Allocation Decision Distribution

- `allocate_paper`: `23`
- `allocate_paper_throttled`: `8`
- `allocate_paper_shadow_only`: `8`
- `reserve_for_delayed_rotation`: `8`
- `needs_more_fixture_coverage`: `6`
- `reject_liquidity`: `8`
- `reject_live_path`: `1`
- `reject_no_day_trade_constraint`: `6`
- `reject_no_trade`: `8`
- `reject_policy_violation`: `7`

## Allocation By Strategy Type

- `swing_long_call`: `18.55`
- `swing_long_put`: `13.85`
- `zero_dte_long_call`: `10.65`
- `zero_dte_long_put`: `7.25`
- `delayed_rotation_long_call`: `0.75`
- `delayed_rotation_long_put`: `1.25`
- `no_trade`: `0.0`

## 0DTE Handling

0DTE allocation is allowed only through strict special-lifecycle caps. High-proof 0DTE candidates can become `aggressive_paper_capped`, but they are capped at one abstract paper contract unit and remain below the 0DTE exposure-share cap.

## Swing Handling

Strong swing candidates can receive `standard_paper` when hybrid evidence, proof score, coverage, and next-day close eligibility are complete. Swing allocation can exceed 0DTE allocation when hybrid evidence supports it.

## Delayed Rotation Handling

Delayed rotations reserve paper attention only. They do not force same-day close, do not override the no-day-trade guard, and do not create broker instructions.

## Account Ledger And Rotation Planner Integration

The account ledger runner now records an `allocation_context` when the paper allocation plan exists. The context is advisory only:

- allocator role: `advisory_paper_attention_only`
- paper attention priority available: `true`
- delayed rotation reserves advisory only: `true`
- allocator can force same-day close: `false`
- PaperBroker override allowed: `false`

## Threshold Optimizer Integration

The 0DTE threshold optimizer consumes allocation feedback from the paper allocation plan and exposure summary. It records that 0DTE caps remain strict and that live threshold mutation from allocation feedback is not allowed.

## Audit, Reporting, Export, And Review Integration

The offline active-policy audit now recognizes all 10 allocation artifact types and checks:

- paper-only state
- live-blocked state
- no real dollars, buying power, or account balance
- no broker path
- no credentials
- no live orders
- no sell-to-open, naked, unsupported, or undefined-risk allocation
- no same-day churn allocation
- no real sizing
- capped 0DTE allocation
- delayed rotations advisory only

Reporting, export selection, export review, and the test shard stabilizer now surface allocation summaries and include allocation artifacts.

## Validation

Initial allocator smoke passed:

- `python -m dopey_allocation.run_proof_weighted_allocator`
- `python -m dopey_execution.run_account_ledger_rotation_planner`
- `python -m dopey_options.run_zero_dte_threshold_optimizer`
- `python -m dopey_audit.run_offline_evidence_replay_audit`

The full suite remains subject to the known bounded-timeout behavior and must be reported as `inconclusive_timeout` if it times out.

Final validation evidence from this session:

- `python -m pytest tests/test_proof_weighted_allocator.py -q`: `100 passed`
- Targeted dependent 0DTE/account/audit shards: pass
- `python -m dopey_allocation.run_proof_weighted_allocator`: pass
- `python -m dopey_audit.run_offline_evidence_replay_audit`: pass, verdict `pass`, safety errors `0`
- `python -m pytest --collect-only`: pass, `1295` tests collected
- `python -m dopey_validation.full_suite_stabilizer`: pass as a diagnostic command, with full-suite status `inconclusive_timeout`
- bounded `python -m pytest`: `inconclusive_timeout` after `124.036` seconds while in `tests/test_artifact_compaction_export_verifier.py`; timeout was not recorded as pass

## Limitations

- Fixture evidence only.
- No live profitability claim.
- No predictive-power claim.
- No market-accuracy claim.
- No broker capability claim.
- No real capital or portfolio allocation.

## Safety State

Live trading, broker execution, credentials, real market data, schedulers, real buying-power logic, real account sizing, and original Blunder modification remain blocked.

## Portfolio Replay Consumption

`DOPEY_PORTFOLIO_LEVEL_ROTATION_AND_EXPOSURE_REPLAY_V1` now consumes proof-weighted allocation decisions as paper-only portfolio replay inputs. The portfolio layer records how allocated, throttled, delayed-rotation, paper-shadow, watchlist, no-trade, rejected, and live-path negative-control decisions interact over simulated portfolio days.

Portfolio feedback is read by the allocator as advisory paper context only:

- feedback records loaded: `96`
- feedback state: `advisory_only`
- live allocation mutation allowed: `false`
- real sizing allowed: `false`

This portfolio context can recommend reduced 0DTE exposure, reduced gamma/theta pressure, reduced concentration, delayed-rotation capacity reserve, swing preference, no-trade preference, fixture-coverage expansion, or keeping allocation unchanged. It cannot override active policy, no-day-trade controls, PaperBroker boundaries, broker safety, credentials, live paths, or real capital sizing.

## Stress Ladder Crisis Feedback

The proof-weighted paper allocator now reads advisory crisis feedback from `artifacts/dopey/portfolio_stress_ladder/crisis_allocator_feedback.jsonl`. The feedback can recommend reducing total paper allocation under stress, blocking 0DTE under crisis, preserving no-trade recommendations, reducing family/regime concentration, reducing high-gamma/high-theta exposure, and keeping paper-shadow contained. It does not mutate live/default behavior and does not create real allocation.

## Allocator Incident Feedback Handling

The proof-weighted allocator now reads advisory incident feedback from `artifacts/dopey/incident_response/incident_allocator_feedback.jsonl`. Feedback can recommend paper allocation throttle, no-trade, or terminal-block awareness. It cannot mutate live/default allocation behavior, create real capital sizing, use buying power, or override PaperBroker.

## Active Lifecycle Feedback

The proof-weighted allocator now reads advisory lifecycle feedback from `artifacts/dopey/lifecycle/lifecycle_feedback_allocator.jsonl`. Feedback remains offline and cannot mutate live allocation defaults, real capital sizing, or buying-power logic.
