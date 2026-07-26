# DOPEY Portfolio-Level Rotation And Exposure Replay Report

## Objective

`DOPEY_PORTFOLIO_LEVEL_ROTATION_AND_EXPOSURE_REPLAY_V1` adds an offline deterministic portfolio replay layer for long-premium equity options. It converts proof-weighted paper allocation decisions into portfolio states, positions, rotation decisions, exposure snapshots, stress results, and advisory feedback.

This is paper portfolio replay only. It uses abstract paper units, fixture evidence, and static artifacts. It does not use live market data, broker execution, credentials, account balances, buying power, real dollars, schedulers, or deployment.

## Portfolio State Model

`PaperPortfolioState` records the simulated day, open positions, pending entries and exits, delayed rotations, paper-shadow positions, watchlist items, rejected items, exposure snapshot, constraint snapshot, paper-only state, live-blocked state, and a deterministic hash.

## Position Model

`PaperPortfolioPosition` records source allocation, opportunity, synthetic underlying, regime, option type, strategy type, lifecycle, open and close eligibility days, abstract paper attention, abstract paper premium risk units, capped paper contract units, same-day close blocking, 0DTE special lifecycle state, delayed-rotation state, paper-shadow state, and safety flags.

Allowed strategies are long calls and long puts only:

- `zero_dte_long_call`
- `zero_dte_long_put`
- `swing_long_call`
- `swing_long_put`
- `delayed_rotation_long_call`
- `delayed_rotation_long_put`

Unsupported structures, sell-to-open, naked sales, uncovered writing, undefined-risk structures, live paths, credentials, and real sizing are rejected by model validation.

## Exposure Snapshot Model

`PortfolioExposureSnapshot` records total paper exposure, 0DTE units, swing units, paper-shadow units, delayed-rotation reserved units, call/put units, high-gamma units, high-theta units, IV-crush exposure, event/macro exposure, underlying-family exposure, regime-family exposure, strategy exposure, constraint status, and deterministic hash.

## Rotation Decision Model

`PortfolioRotationDecision` records open, hold, close, delayed close, allowed rotation, delayed rotation, paper-shadow, watchlist, policy rejection, exposure rejection, and live-path rejection decisions. Same-day normal churn remains blocked.

## Portfolio Exposure Policy

The policy is aggressive but capped:

- max total paper premium risk units
- max 0DTE share
- max swing share
- max paper-shadow share
- max delayed-rotation reserve share
- max underlying-family exposure
- max regime-family exposure
- max synthetic-underlying exposure
- max high-gamma exposure
- max high-theta exposure
- max IV-crush exposure
- max event/macro exposure
- max call/put imbalance
- max open positions and daily entries

0DTE is not banned. It is capped at portfolio level and kept tighter than swing exposure.

## Timeline Fixtures

The bundle writes 96 deterministic replay cases:

- clean swing allocations: `12`
- clean 0DTE capped allocations: `12`
- delayed rotation cases: `10`
- same-day close blocked cases: `10`
- paper-shadow containment cases: `8`
- watchlist-only cases: `8`
- no-trade/rejection cases: `8`
- underlying-family concentration cases: `8`
- regime-family concentration cases: `8`
- high-gamma/high-theta throttle cases: `6`
- IV/event/macro throttle cases: `6`

## Replay Engine

`dopey_portfolio.portfolio_replay_engine` consumes the proof-weighted paper allocation plan and allocation decisions, applies the portfolio policy, writes rotation decisions and exposure snapshots, and creates advisory feedback for the allocator and threshold optimizer.

## Exposure Stress Replay

`dopey_portfolio.exposure_stress_replay` writes 60 stress records covering:

- 0DTE concentration
- same-underlying-family concentration
- same-regime concentration
- call-heavy and put-heavy exposure
- high-gamma and high-theta exposure
- IV-crush and event/macro exposure
- delayed-rotation backlog
- paper-shadow leakage
- no-day-trade close blocking
- live-path, broker-boundary, and real-sizing negative controls

## Feedback

Allocator feedback is advisory and paper-gated. It can recommend reducing 0DTE exposure, high-gamma exposure, high-theta exposure, family concentration, regime concentration, reserving delayed-rotation capacity, preferring swing, preferring no-trade, keeping allocation unchanged, increasing fixture coverage, or rejecting unsafe allocation profiles.

Threshold optimizer feedback is advisory and paper-gated. It can preserve strict 0DTE profiles, keep pressure-sensitive profiles paper-shadow only, recommend later-expiry advisory strengthening, or reject profiles that increase same-day churn or safety-boundary pressure. It cannot mutate live/default thresholds.

## Summary

- replay cases: `96`
- stress records: `60`
- portfolio states: `96`
- positions: `52`
- rotation decisions: `96`
- exposure snapshots: `96`
- allocator feedback records: `96`
- threshold feedback records: `96`
- proof records: `96`
- blocked actions: `63`
- same-day close blocked count: `11`
- paper-shadow containment count: `8`
- delayed rotation decision count: `10`
- max 0DTE exposure share: `0.35`
- 0DTE exposure status: `within_cap`

## Audit, Reporting, Export, And Review Integration

The active-policy audit recognizes all 11 portfolio replay artifact types and checks paper-only/live-blocked state, parsing, no real capital sizing terms, no buying power, no account balance, no broker execution path, no credentials, no live orders, no unsupported structures, no same-day churn, capped 0DTE exposure, contained paper-shadow states, delayed rotations that do not force same-day close, advisory-only allocator feedback, advisory-only threshold feedback, and no active forbidden live decisions.

Reporting, export selection, export review, and the test shard stabilizer now surface portfolio replay summary fields and select portfolio replay artifacts.

## Validation

Initial targeted validation:

- `python -m dopey_portfolio.run_portfolio_replay`: pass
- `python -m pytest tests/test_portfolio_replay.py -q`: `110 passed`
- direct portfolio audit checker: pass, `21` checks

Full-suite timeout remains `inconclusive_timeout` if it times out. Timeout is never pass.

## Limitations

- Fixture-only deterministic evidence.
- Abstract paper units only.
- No live profitability claim.
- No predictive-power claim.
- No market-accuracy claim.
- No broker capability claim.
- No real account allocation or sizing claim.

## Safety State

Live trading, broker execution, credentials, real market data, schedulers, real buying-power logic, real account sizing, real-dollar portfolio allocation, live orders, and original Blunder modification remain blocked.


## Final Validation Evidence

Final validation results:

- `python -m pytest tests/test_portfolio_replay.py -q`: `110 passed`
- `python -m pytest tests/test_proof_weighted_allocator.py -q`: `100 passed`
- Targeted dependent shards for hybrid V3, cross-underlying V2, adversarial corpus, threshold optimizer, 0DTE risk/replay, account/rotation/PaperBroker, and active policy: pass
- `python -m dopey_portfolio.run_portfolio_replay`: pass
- `python -m dopey_audit.run_offline_evidence_replay_audit`: pass, exit code `0`, completeness `138/138`, safety errors `0`
- `python -m dopey_reporting.run_tournament_performance_reporting_bundle`: pass
- `python -m dopey_export.run_artifact_compaction_export_verifier`: pass, artifacts exported `180`, safety findings `0`, credential findings `0`
- `python -m dopey_export_review.run_export_bundle_review_assistant`: pass, safety errors `0`
- `python -m dopey_validation.full_suite_stabilizer`: pass, full-suite status `inconclusive_timeout`, timeout recorded as pass `false`
- `python -m pytest --collect-only`: pass, `1405` tests collected
- bounded `python -m pytest`: `inconclusive_timeout` after `124.027` seconds while still in `tests/test_artifact_compaction_export_verifier.py`; timeout recorded as pass `false`

Final portfolio replay artifact state remains stable: `96` replay cases, `60` stress result records, `96` states, `52` positions, `96` rotation decisions, `96` exposure snapshots, `96` allocator feedback records, `96` threshold feedback records, `96` proof records, and max 0DTE exposure share `0.35` with status `within_cap`.
## Stress Ladder V2 Integration

`DOPEY_PORTFOLIO_REPLAY_V2_STRESS_LADDER_AND_CRISIS_MODE_THROTTLES_V1` now consumes portfolio replay output and escalates fixture stress through normal, elevated, defensive, severe, crisis, and lockdown states. Crisis-mode throttles block or reduce fragile paper exposure, block 0DTE under severe/crisis/lockdown pressure, preserve same-day close blocking, keep paper-shadow contained, and keep delayed rotations advisory. Recovery is gradual and cannot jump directly from crisis to normal.

## Incident Handling For Portfolio Replay Failures

Portfolio replay failures now feed into the offline incident response rehearsal through portfolio exposure violation cases. Family concentration, regime concentration, call/put imbalance, high-gamma, high-theta, IV/event/macro, paper-shadow leakage, and delayed rotation backlog cases can throttle or lock down paper governance without creating broker execution or real sizing.

## Active Lifecycle Feedback

Portfolio replay now reads advisory lifecycle feedback from `artifacts/dopey/lifecycle/lifecycle_feedback_portfolio.jsonl`. This summarizes lifecycle open/close success, same-day-close blocks, delayed rotation, PaperBroker rejections, stress interruptions, and incident interruptions without mutating live/default portfolio state.
