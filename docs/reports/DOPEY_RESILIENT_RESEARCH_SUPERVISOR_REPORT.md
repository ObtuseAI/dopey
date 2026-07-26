# DOPEY Resilient Research Supervisor Report

## Policy
Every stage runs; failures are absorbed into incident + repair artifacts and true
dependents are skipped with reasons. A failure is never recorded as a pass, and the
supervisor can never promote a strategy.

- supervisor_status: `completed_with_degraded_statuses`
- stages: `32`/`32` completed (`29` green, `3` degraded/blocked-input), `0` failed (absorbed), `0` skipped on dependencies
- regressions vs previous run: `[]` | recoveries: `['adversarial_signal_panel', 'adversarial_stress', 'chart_vision', 'distributional_stress', 'exit_playbook', 'forward_book_quality', 'forward_book_risk', 'forward_paper_walk', 'indicator_foundry', 'market_context_fusion', 'market_structure', 'target_screener', 'trade_loss_coach', 'universe_governor']`
- incidents: `0` | repair queue: `0`

## Stage Results
- `data_freshness_sentinel`: `completed` (data_freshness_green)
- `envelope_integrity_sentinel`: `completed` (envelope_intact)
- `macro_context_gate`: `completed` (macro_context_computed)
- `history_validation`: `completed` (valid_real_dataset)
- `real_signals`: `completed` (current_history_signals_reused)
- `market_structure`: `completed` (market_structure_computed_real_history)
- `model_iv_calibration`: `completed` (model_iv_calibration_complete)
- `real_backtest`: `completed` (valid_real_history_model_priced_backtest_complete)
- `baseline_arbitration`: `completed` (baseline_arbitration_complete)
- `era_walk_forward`: `completed` (era_walk_forward_complete)
- `statistical_truth`: `completed_degraded` (insufficient_real_sample)
- `truth_gated_fitness`: `completed_degraded` (insufficient_real_sample)
- `chain_analytics_gate`: `completed` (real_chain_analytics_computed)
- `vol_surface_metrics`: `completed` (vol_surface_metrics_computed)
- `market_context_fusion`: `completed` (market_context_fusion_computed)
- `forward_paper_walk`: `completed` (forward_walk_marked)
- `forward_book_quality`: `completed` (completed_no_status_field)
- `forward_book_risk`: `completed` (forward_book_risk_complete)
- `adversarial_stress`: `completed` (book_vulnerable_repair_required)
- `distributional_stress`: `completed` (distributional_stress_complete)
- `exit_playbook`: `completed` (exit_playbook_complete)
- `signal_calibration`: `completed` (phantom_settlements_graded)
- `playbook_research`: `completed` (completed_no_status_field)
- `adversarial_signal_panel`: `completed` (no_new_entries_panel_idle)
- `trade_loss_coach`: `completed` (trade_loss_coach_complete)
- `target_screener`: `completed` (targets_ranked)
- `universe_governor`: `completed` (universe_governed)
- `exit_policy_search`: `completed` (exit_policy_search_complete)
- `chart_vision`: `completed` (real_structure_charts_rendered)
- `indicator_foundry`: `completed` (indicator_foundry_complete)
- `agentic_account_reconciliation`: `completed_degraded` (blocked_missing_account_snapshot)
- `action_readiness_gate`: `completed` (not_action_ready)

## Safety
- paper_only: `true`; live_blocked: `true`; strategy_promotion_allowed: `false`.
