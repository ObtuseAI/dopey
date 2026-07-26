# DOPEY Hybrid Swing 0DTE V3 Artifact Ledger

All artifacts are local, deterministic, fixture-only, paper-only, and live-blocked.

## Fixture Files

- `dopey_data/fixtures/active_trading_policy/hybrid_underlying_families_v3.json`
- `dopey_data/fixtures/active_trading_policy/hybrid_swing_candidates_v3.json`
- `dopey_data/fixtures/active_trading_policy/hybrid_opportunity_pairs_v3.json`
- `dopey_data/fixtures/active_trading_policy/hybrid_multi_day_paths_v3.json`
- `dopey_data/fixtures/active_trading_policy/hybrid_expected_outcomes_v3.json`
- `dopey_data/fixtures/active_trading_policy/hybrid_expected_allocator_tags_v3.json`

## Replay Artifacts

- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_underlying_families.json`
- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_swing_candidates.json`
- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_opportunity_pairs.json`
- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_multi_day_paths.json`
- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_replay_outcomes.jsonl`
- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_preference_scores.jsonl`
- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_allocator_tags.jsonl`
- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_coverage_summary.json`
- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_threshold_survival.json`
- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_replay_summary.json`
- `artifacts/dopey/hybrid_swing_0dte_v3/hybrid_corpus_proof.jsonl`

## Code Surfaces

- `dopey_options/swing_option_models.py`
- `dopey_options/hybrid_replay_models.py`
- `dopey_options/multi_day_option_path_models.py`
- `dopey_options/hybrid_swing_0dte_fixture_builder.py`
- `dopey_options/multi_day_swing_path_builder.py`
- `dopey_options/swing_lifecycle_policy.py`
- `dopey_options/hybrid_preference_scoring.py`
- `dopey_options/hybrid_swing_zero_dte_replay_engine.py`
- `dopey_options/hybrid_swing_0dte_coverage.py`
- `dopey_options/run_hybrid_swing_0dte_v3.py`
- `tests/test_hybrid_swing_0dte_v3.py`

## Integration Surfaces

- `dopey_options/zero_dte_threshold_optimizer.py`
- `dopey_audit/active_policy_audit.py`
- `dopey_audit/artifact_loader.py`
- `dopey_reporting/data_loader.py`
- `dopey_reporting/reporting_bundle.py`
- `dopey_export/artifact_selector.py`
- `dopey_export_review/review_packet.py`
- `dopey_validation/full_suite_stabilizer.py`

## Safety State

- `paper_only`: `true`
- `live_blocked`: `true`
- `no_real_market_data`: `true`
- `no_broker`: `true`
- `real_sizing_allowed`: `false`
