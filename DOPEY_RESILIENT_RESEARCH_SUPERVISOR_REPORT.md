# DOPEY Resilient Research Supervisor Report

## Policy
Every stage runs; failures are absorbed into incident + repair artifacts and true
dependents are skipped with reasons. A failure is never recorded as a pass, and the
supervisor can never promote a strategy.

- supervisor_status: `degraded_with_incidents`
- stages: `29`/`31` completed (`21` green, `8` degraded/blocked-input), `2` failed (absorbed), `0` skipped on dependencies
- regressions vs previous run: `['action_readiness_gate', 'baseline_arbitration', 'chart_vision', 'distributional_stress', 'indicator_foundry', 'market_structure', 'model_iv_calibration', 'real_backtest', 'real_signals']` | recoveries: `['statistical_truth', 'truth_gated_fitness']`
- incidents: `2` | repair queue: `2`

## Stage Results
- `data_freshness_sentinel`: `completed` (data_freshness_green)
- `envelope_integrity_sentinel`: `completed` (envelope_intact)
- `macro_context_gate`: `completed` (macro_context_computed)
- `history_validation`: `completed` (invalid_real_dataset)
- `governed_import_stack`: `completed` (local_ohlcv_validation_fail)
- `real_signals`: `completed_degraded` (blocked_missing_valid_real_history)
- `market_structure`: `completed_degraded` (blocked_missing_valid_real_history)
- `model_iv_calibration`: `completed_degraded` (blocked_missing_valid_real_history)
- `real_backtest`: `completed_degraded` (blocked_missing_valid_real_history)
- `baseline_arbitration`: `failed_absorbed` (ValueError)
- `era_walk_forward`: `completed` (era_walk_forward_complete)
- `statistical_truth`: `completed` (fixture_model_statistics_only)
- `truth_gated_fitness`: `completed` (fixture_model_statistics_only)
- `chain_analytics_gate`: `completed` (real_chain_analytics_computed)
- `vol_surface_metrics`: `completed` (vol_surface_metrics_computed)
- `market_context_fusion`: `completed` (market_context_fusion_computed)
- `forward_paper_walk`: `completed` (forward_walk_marked)
- `forward_book_risk`: `completed` (forward_book_risk_complete)
- `adversarial_stress`: `completed` (no_open_positions_book_trivially_survives)
- `distributional_stress`: `completed_degraded` (blocked_missing_valid_real_history)
- `exit_playbook`: `completed` (no_open_positions_playbook_trivial)
- `signal_calibration`: `completed` (phantom_settlements_graded)
- `adversarial_signal_panel`: `completed` (no_new_entries_panel_idle)
- `trade_loss_coach`: `completed` (trade_loss_coach_complete)
- `target_screener`: `completed` (targets_ranked)
- `universe_governor`: `completed` (universe_governed)
- `exit_policy_search`: `completed` (exit_policy_search_complete)
- `chart_vision`: `completed_degraded` (blocked_missing_valid_real_history)
- `indicator_foundry`: `completed_degraded` (blocked_missing_valid_real_history)
- `agentic_account_reconciliation`: `completed_degraded` (blocked_missing_account_snapshot)
- `action_readiness_gate`: `failed_absorbed` (FileNotFoundError)

## Safety
- paper_only: `true`; live_blocked: `true`; strategy_promotion_allowed: `false`.
