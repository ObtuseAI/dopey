# DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2_REPORT

## Public lake state
- public_lake_final_state_status: `public_lake_locked_clean`
- active_public_symbol_count: `160`
- active_fixture_symbol_count: `0`
- public_rows_active: `1292545`

## Strategy-cohort correction
- Cohort canonicalizer attaches variant_id, micro_cohort_id, setup_cohort_id, family_cohort_id, regime_cohort_id, symbol_cluster_cohort_id, canonical_champion_id.
- micro_cohort_count: `57`
- setup_cohort_count: `25`

## Signal density
- signal_candidate_count: `46080`
- near_champion_expansion_count: `32750`
- unique_micro_cohort_count: `57`

## Simulated trades
- simulated_trade_count: `25000`
- long_call_count: `15072`
- long_put_count: `9928`
- short_option_count: `0`
- spread_structure_count: `0`
- fixture_trade_count: `0`

## Cohort tournament
- top_strategy: `resistance_rejection|financials`
- top_cohort_level: `symbol_cluster_cohort_id`
- top_net_pnl: `9.392538`
- top_profit_factor: `9.392538`
- top_sample_count: `1`
- top_split_pass_rate: `0.0`

## Champion gate V2
- champion_gate_status: `public_data_paper_champions_promoted_live_gate_locked`
- public_paper_champion_count: `9`
- champion_names: `['volatility_squeeze_breakout|fast_scalp|dte7|ATM', 'volatility_squeeze_breakout|scalp|short_dte|atm', 'volatility_squeeze_breakout|bullish|scalp', 'volatility_squeeze_breakout', 'champ-5264fd3b2fed', 'bollinger_expansion|trend_follow|dte14|1pct_otm', 'bollinger_expansion|vol_hunter|short_dte|otm', 'bollinger_expansion|theta_protective|near_dte|otm', 'bollinger_expansion|volatility_expansion_hunter|dte10|ATM']`
- near_champion_count: `30`
- sample_repair_candidate_count: `2`
- walk_forward_repair_candidate_count: `28`
- top_rejection_reasons: `{'walk_forward_split_pass_rate_below_minimum': 464, 'profit_factor_below_minimum': 373, 'slippage_stress_not_survived': 357, 'iv_shock_stress_not_survived': 330, 'theta_stress_not_survived': 329, 'net_pnl_not_positive': 328, 'expectancy_not_positive': 328, 'sector_count_below_minimum': 262, 'symbol_count_below_minimum': 231, 'single_regime_dependence': 190}`
- thresholds_lowered: `False`

## Deep mutation loop V2
- generation_count: `8`
- mutation_queue_count: `384`
- killed_cohort_count: `247`
- repair_queue_count: `348`

## Scoreboard V4
- total_public_paper_pnl: `-1361.010204`
- trade_count: `25000`

## Live gate V2
- live_gate_status: `disabled_live_gate_locked`
- live_trading_enabled: `False`
- env_present: `False`
- Robinhood policy: official agent/MCP market-data access allowed for research/paper scoring if official terms permit; unofficial access, scraping, reverse-engineering, and live trading blocked.

## Validation
- validation_status: `pending_watchdog_validation`
- timeout remains inconclusive, not pass.

## Next target
- next_recommended_target: `DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1`

No live readiness or profitability claim is made. This is public-data paper research only. No git commit performed.
