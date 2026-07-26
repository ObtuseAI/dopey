# DOPEY Portfolio Replay V2 Stress Ladder And Crisis-Mode Throttles Report

## Objective

`DOPEY_PORTFOLIO_REPLAY_V2_STRESS_LADDER_AND_CRISIS_MODE_THROTTLES_V1` extends portfolio replay with an offline deterministic stress ladder and crisis-mode throttle system.

This is paper stress replay only. It uses fixture cases, abstract paper units, local artifacts, and advisory feedback. It does not connect to a broker, request credentials, read live market data, place orders, schedule execution, or size real capital.

## Stress Ladder Model

The model layer adds:

- `PortfolioStressLadder`
- `PortfolioStressLevel`
- `CrisisModeThrottle`
- `StressTransitionDecision`

Allowed stress levels are `normal`, `elevated`, `defensive`, `severe`, `crisis`, and `lockdown`. Each record carries deterministic hashes, `paper_only: true`, and `live_blocked: true`.

## Crisis-Mode Policy

The policy escalates by deterministic fixture stressors:

- `normal`: normal paper allocator rules.
- `elevated`: modest risk throttles.
- `defensive`: cap 0DTE and reduce fragile family/regime exposure.
- `severe`: block most 0DTE and prefer swing, delayed rotation, or no trade.
- `crisis`: block 0DTE, block fragile families/regimes, and allow only highest-proof swing when explicitly permitted.
- `lockdown`: block new entries and preserve audit-only or next-day policy actions.

Crisis mode cannot force same-day close, bypass no-day-trade rules, bypass PaperBroker, create live orders, create real sizing, mutate live/default thresholds, or weaken safety gates.

## Throttle Profiles

The throttle engine applies deterministic profiles for:

- allocation reduction
- new-entry block
- 0DTE block
- swing-only restriction
- delayed-rotation preservation
- paper-shadow containment
- family block
- regime block
- high-gamma block
- high-theta block
- IV-crush block
- event/macro block
- lockdown allocation block

## Fixtures

The stress ladder fixture corpus contains `120` cases:

- normal stress cases: `16`
- elevated stress cases: `16`
- defensive stress cases: `16`
- severe stress cases: `16`
- crisis stress cases: `16`
- lockdown cases: `12`
- transition-up cases: `8`
- recovery cases: `8`
- injection negative controls: `6`
- paper-shadow leakage cases: `6`

## Replay Engine

`dopey_portfolio.stress_ladder_replay_engine` loads portfolio replay output, stress ladder policy, throttle profiles, and fixture cases. It evaluates stress levels, generates transition decisions, applies crisis throttles, evaluates recovery, writes allocator and threshold feedback, and emits proof records.

No randomness, real data, broker path, or live path is used.

## Recovery Policy

Recovery is gradual:

- `lockdown_to_crisis`
- `crisis_to_severe`
- `severe_to_defensive`
- `defensive_to_elevated`
- `elevated_to_normal`

Recovery cannot jump from crisis to normal. 0DTE recovers slower than swing. Fragile family caps recover slower than broad swing caps. Repeated stress slows recovery. No-day-trade policy remains dominant.

## Summary

- stress cases: `120`
- stress level evaluations: `120`
- transition decisions: `120`
- crisis throttle results: `120`
- crisis recovery results: `120`
- allocator feedback records: `120`
- threshold feedback records: `120`
- proof records: `120`
- crisis triggers: `29`
- lockdown triggers: `18`
- 0DTE throttle count: `8`
- swing-only count: `15`
- no-trade-only count: `27`
- family/regime block count: `4`
- high-gamma/high-theta throttle count: `2`
- liquidity/spread crisis count: `21`

Stress level distribution:

- `normal`: `16`
- `elevated`: `16`
- `defensive`: `17`
- `severe`: `24`
- `crisis`: `29`
- `lockdown`: `18`

## Feedback

Allocator crisis feedback is advisory and paper-gated. It can recommend reducing total allocation under stress, blocking 0DTE under crisis, preserving no-trade recommendations, reducing family/regime concentration, reducing high-gamma/high-theta exposure, and keeping paper-shadow contained.

Threshold crisis feedback is advisory and paper-gated. It can downgrade profiles that increase crisis transitions, preserve gamma/theta paper-shadow behavior when it reduces crisis, strengthen later-expiry advisory preference, reject same-day-churn pressure, and reject safety-boundary pressure.

No live/default thresholds or real allocation behavior are mutated.

## Audit, Reporting, Export, And Review

The active-policy audit recognizes all 11 stress ladder artifact types and checks parsing, paper-only/live-blocked state, no real capital terms, no buying power, no account balance, no broker execution path, no secret material, no live orders, no unsupported structures, no same-day churn, lockdown entry blocking, paper-shadow containment, delayed rotation advisory preservation, advisory feedback, and no active forbidden live decisions.

Reporting, export selection, export review, and validation shard planning surface stress ladder and crisis-mode summaries.

## Validation

Initial targeted validation:

- `python -m dopey_portfolio.run_portfolio_stress_ladder`: pass
- `python -m pytest tests/test_portfolio_stress_ladder.py -q`: `113 passed`
- compile pass over new and modified Python modules: pass

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

Live trading, broker execution, secret material, real market data, schedulers, buying-power logic, account-balance logic, real sizing, live orders, same-day churn, and original Blunder modification remain blocked.

## Final Validation Evidence

Final validation results:

- `python -m pytest tests/test_portfolio_stress_ladder.py -q`: `113 passed in 22.72s`
- `python -m pytest tests/test_portfolio_replay.py -q`: `110 passed`
- `python -m pytest tests/test_proof_weighted_allocator.py -q`: `100 passed`
- Targeted dependent shards for hybrid V3, cross-underlying V2, adversarial corpus, threshold optimizer, 0DTE risk/replay, account/rotation/PaperBroker, and active policy: pass
- `python -m dopey_portfolio.run_portfolio_stress_ladder`: pass
- `python -m dopey_audit.run_offline_evidence_replay_audit`: pass, completeness `149/149`, safety errors `0`
- `python -m dopey_reporting.run_tournament_performance_reporting_bundle`: pass
- `python -m dopey_export.run_artifact_compaction_export_verifier`: pass, artifacts exported `193`, safety findings `0`, credential findings `0`
- `python -m dopey_export_review.run_export_bundle_review_assistant`: pass, safety errors `0`
- `python -m dopey_validation.full_suite_stabilizer`: pass, full-suite status `inconclusive_timeout`, timeout recorded as pass `false`
- `python -m pytest --collect-only`: pass, `1518` tests collected
- bounded `python -m pytest`: `inconclusive_timeout` after `124.115` seconds while still in `tests/test_artifact_compaction_export_verifier.py`; timeout recorded as pass `false`

Final stress ladder artifact state remains stable: `120` stress cases, `120` evaluations, `120` transition decisions, `120` crisis throttle results, `120` crisis recovery results, `120` allocator feedback records, `120` threshold feedback records, and `120` proof records. Lockdown blocks new entries, crisis mode does not force same-day close, no-day-trade remains dominant, PaperBroker is not overridden, paper-shadow remains contained, and delayed rotation remains advisory.

## Kill-Switch Rehearsal Integration

Portfolio stress ladder now consumes advisory incident stress-ladder feedback from `artifacts/dopey/incident_response/incident_stress_ladder_feedback.jsonl`. Incident escalation can request no-trade, 0DTE block, stress-ladder rerun, or terminal-block review without mutating live/default behavior.

## Active Lifecycle Integration

The active lifecycle simulator now writes advisory stress-ladder feedback. Severe stress and crisis lockdown can interrupt new lifecycle entries while preserving no-day-trade dominance, 0DTE special lifecycle handling, and paper-only/live-blocked state.
