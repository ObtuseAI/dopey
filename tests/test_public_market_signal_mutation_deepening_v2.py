from __future__ import annotations

from pathlib import Path

from dopey_autonomy.run_public_market_signal_mutation_deepening_v2 import artifact_paths as orchestrator_artifact_paths
from dopey_autonomy.signal_deepening_common import NEAR_CHAMPION_SEEDS
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS
from dopey_champion.champion_threshold_profiles_v2 import champion_threshold_profile_v2, minimum_trades_for_level
from dopey_champion.public_paper_champion_gate_v2 import (
    champion_decision_v2,
    evaluate_public_paper_champions_v2,
)
from dopey_evolution.cohort_loser_elimination_v2 import build_cohort_loser_elimination_v2
from dopey_evolution.near_champion_repair_loop_v2 import build_near_champion_repair_queue_v2
from dopey_evolution.public_signal_deepening_loop_v2 import _generation_mutations
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import FINDING_CATEGORIES
from dopey_live_gate.public_signal_deepening_live_gate_status_v2 import build_live_gate_status_v2
from dopey_market_intake.public_lake_final_state_lock_v2 import final_state_status_for_records
from dopey_options_engine.cohort_path_replay_engine_v4 import replay_signal_trade_v4
from dopey_scoreboard.public_signal_deepening_scoreboard_v4 import build_public_signal_deepening_scoreboard_v4
from dopey_signal_engine.near_champion_signal_expander_v4 import near_champion_expansion_plan_v4
from dopey_signal_engine.public_signal_mutation_factory_v4 import (
    build_parameter_grid_v4,
    build_signal_candidate_v4,
)
from dopey_strategy_cohorts.strategy_cohort_models import COHORT_LEVELS
from dopey_strategy_cohorts.strategy_id_canonicalizer import assign_cohort_ids, attach_cohort_ids
from dopey_tournament.public_cohort_walk_forward_tournament_v4 import score_public_cohort_walk_forward_tournament_v4
from dopey_validation.full_suite_stabilizer import collect_test_files, timeout_result
from dopey_wealth_engine.common import REPO_ROOT


def test_public_lake_final_state_lock_blocks_fixture_residue() -> None:
    status = final_state_status_for_records([
        {"symbol": "SIMV2", "market_data_source_type": "fixture_fallback"},
        {"symbol": "SPY", "market_data_source_type": "public_live_fetch"},
    ])
    assert status == "public_lake_broken_contamination_detected"


def test_public_lake_final_state_lock_blocks_test_symbol_residue() -> None:
    status = final_state_status_for_records([
        {"symbol": "TESTALPHA", "market_data_source_type": "public_live_fetch"},
    ])
    assert status == "public_lake_broken_contamination_detected"


def test_public_lake_final_state_lock_accepts_clean_public_records() -> None:
    status = final_state_status_for_records([
        {"symbol": "SPY", "market_data_source_type": "public_live_fetch"},
        {"symbol": "QQQ", "market_data_source_type": "public_cache_fetch"},
    ])
    assert status == "public_lake_locked_clean"


def test_strategy_cohort_canonicalizer_groups_variants_into_cohort_ids() -> None:
    record = attach_cohort_ids({
        "signal_id": "unit-signal-1",
        "strategy_id": "bollinger_expansion|fast_scalp|dte7|ATM",
        "setup_family": "bollinger_expansion",
        "exit_policy": "fast_scalp",
        "dte_bucket": 7,
        "moneyness_bucket": "ATM",
        "symbol": "SPY",
        "sector": "broad_etf",
        "regime": "low_volatility",
    })
    for level in COHORT_LEVELS:
        assert record[level]
    assert record["micro_cohort_id"] == "bollinger_expansion|scalp|short_dte|atm"
    assert record["setup_cohort_id"] == "bollinger_expansion|bullish|scalp"
    assert record["family_cohort_id"] == "bollinger_expansion"
    assert record["regime_cohort_id"] == "bollinger_expansion|low_volatility"
    assert record["symbol_cluster_cohort_id"] == "bollinger_expansion|broad_etf"
    assert record["canonical_champion_id"].startswith("champ-")


def test_all_cohort_ids_exist_on_sample_signal_trade_and_score_records() -> None:
    base = {
        "setup_family": "atr_compression_breakout",
        "exit_policy": "trend_follow",
        "dte_bucket": 14,
        "moneyness_bucket": "1pct_otm",
        "symbol": "AAPL",
        "sector": "technology",
        "regime": "high_volatility",
        "direction": "bullish",
        "strategy_id": "atr_compression_breakout|trend_follow|dte14|1pct_otm",
    }
    for seed in ("signal_id", "trade_id", "strategy_id"):
        record = attach_cohort_ids({**base, seed: "unit-source-1"})
        ids = assign_cohort_ids(record)
        assert set(ids.keys()) == set(COHORT_LEVELS)
        for level in COHORT_LEVELS:
            assert ids[level]


def test_dense_mutation_factory_produces_repeated_samples_per_cohort() -> None:
    grid = build_parameter_grid_v4()
    assert len(grid) >= 5000
    features = feature_snapshot_v4()
    candidate_a = build_signal_candidate_v4("SPY", {"date": "2024-01-03"}, features, grid[0], "public_live_fetch", 1)
    candidate_b = build_signal_candidate_v4("SPY", {"date": "2024-01-03"}, features, grid[0], "public_live_fetch", 2)
    assert candidate_a["micro_cohort_id"] == candidate_b["micro_cohort_id"]
    assert candidate_a["market_data_source_type"] == "public_live_fetch"
    assert candidate_a["public_data_only"] is True
    assert candidate_a["live_blocked"] is True
    for level in COHORT_LEVELS:
        assert candidate_a[level]


def test_near_champion_expander_targets_prior_near_champions() -> None:
    plans = near_champion_expansion_plan_v4()
    seed_ids = {plan["seed_id"] for plan in plans}
    for seed in NEAR_CHAMPION_SEEDS:
        assert seed in seed_ids
    assert "bollinger_expansion|fast_scalp|dte7|ATM" in seed_ids
    assert "atr_compression_breakout|fast_scalp|dte7|ATM" in seed_ids
    assert "sector_relative_strength|invalidation_strict|dte14|1pct_otm" in seed_ids
    assert all(plan["fixture_allowed"] is False for plan in plans)
    assert all(plan["live_trading_enabled"] is False for plan in plans)


def test_model_priced_path_simulator_v4_uses_future_ohlcv_path() -> None:
    trade = replay_signal_trade_v4(long_call_signal_v4(), public_rows())
    assert trade["entry_date"] == "2024-01-03"
    assert trade["exit_date"] != trade["entry_date"]
    assert trade["exit_reason"] in {
        "target_hit", "option_target_hit", "max_hold_days", "time_stop",
        "drawdown_stop", "theta_bleed_stop", "invalidation_hit",
    }
    assert trade["model_priced"] is True
    assert trade["quote_priced"] is False


def test_model_priced_path_simulator_v4_produces_long_calls_long_puts_and_no_trade_only() -> None:
    call_trade = replay_signal_trade_v4(long_call_signal_v4(), public_rows())
    put_signal = {
        **long_call_signal_v4(),
        "trade_intent": "long_put",
        "direction": "bearish",
        "invalidation_level": 106.0,
        "target_price": 96.0,
    }
    put_trade = replay_signal_trade_v4(put_signal, public_rows())
    no_trade_signal = {**long_call_signal_v4(), "trade_intent": "no_trade", "option_side": "none"}
    no_trade = replay_signal_trade_v4(no_trade_signal, public_rows())
    assert {call_trade["trade_intent"], put_trade["trade_intent"], no_trade["trade_intent"]} == {"long_call", "long_put", "no_trade"}


def test_model_priced_path_simulator_v4_never_shorts_or_spreads() -> None:
    trade = replay_signal_trade_v4(long_call_signal_v4(), public_rows())
    assert trade["option_position"] == "long"
    assert trade["short_option"] is False
    assert trade["spread_structure"] is False
    assert trade["unsupported_structure"] is False
    assert trade["fixture_trade"] is False
    assert trade["public_data_only"] is True
    assert trade["live_trading_enabled"] is False


def test_cohort_tournament_scores_variants_and_cohorts_separately() -> None:
    trades = sample_v4_trades()
    summary = score_public_cohort_walk_forward_tournament_v4(trades)
    assert summary["trade_count"] > 0
    assert summary["leaderboard_count"] > 0
    cohort_counts = summary["cohort_counts"]
    for level in COHORT_LEVELS:
        assert cohort_counts.get(level, 0) >= 1
    assert summary["public_data_only"] is True
    assert summary["fixture_trade_count"] == 0
    assert summary["live_trading_enabled"] is False


def test_cohort_tournament_creates_sample_counts_above_tiny_sample_cases() -> None:
    trades = sample_v4_trades()
    summary = score_public_cohort_walk_forward_tournament_v4(trades)
    assert int(summary["top_sample_count"]) >= 20
    assert int(summary["split_count"]) > 0


def test_champion_gate_v2_rejects_tiny_sample_winners() -> None:
    thresholds = champion_threshold_profile_v2()
    tiny_row = {**champion_leaderboard_row(), "sample_count": 5}
    decision = champion_decision_v2(tiny_row, thresholds)
    assert decision["public_data_paper_champion"] is False
    assert "sample_count_below_minimum" in decision["rejection_reasons"]
    assert decision["live_trading_enabled"] is False


def test_champion_gate_v2_promotes_only_public_candidates_meeting_thresholds() -> None:
    thresholds = champion_threshold_profile_v2()
    decision = champion_decision_v2(champion_leaderboard_row(), thresholds)
    assert decision["public_data_paper_champion"] is True
    assert decision["live_gate_candidate_locked"] is True
    assert decision["no_live_promotion"] is True


def test_champion_gate_v2_rejects_fixture_or_non_public_candidates() -> None:
    thresholds = champion_threshold_profile_v2()
    fixture_row = {**champion_leaderboard_row(), "public_data_only": False, "fixture_trade_count": 2}
    decision = champion_decision_v2(fixture_row, thresholds)
    assert decision["public_data_paper_champion"] is False
    assert "fixture_trades_present" in decision["rejection_reasons"]
    assert "not_public_data_only" in decision["rejection_reasons"]


def test_champion_gate_v2_does_not_lower_thresholds_silently() -> None:
    thresholds = champion_threshold_profile_v2()
    assert thresholds["profile_id"] == "public-paper-champion-thresholds-v2-explicit"
    assert thresholds["variant_minimum_trades"] == 30
    assert thresholds["setup_cohort_minimum_trades"] == 60
    assert thresholds["family_cohort_minimum_trades"] == 100
    assert thresholds["minimum_splits_passed_rate"] == 0.60
    assert thresholds["minimum_profit_factor"] == 1.15
    assert minimum_trades_for_level("family_cohort_id", thresholds) == 100


def test_champion_gate_v2_emits_sample_repair_plans() -> None:
    thresholds = champion_threshold_profile_v2()
    near_row = near_champion_sample_row()
    summary = evaluate_public_paper_champions_v2([near_row], thresholds, artifact_mode="test", persist=True)
    assert summary["near_champion_count"] >= 1
    assert summary["sample_repair_candidate_count"] >= 1
    assert summary["thresholds_lowered"] is False
    assert summary["live_trading_enabled"] is False


def test_signal_deepening_loop_generates_mutations() -> None:
    gate_results = [{**champion_leaderboard_row(), "public_data_paper_champion": True, "cohort_id": "bollinger_expansion|fast_scalp|dte7|ATM"}]
    leaderboard = [champion_leaderboard_row()]
    mutations = _generation_mutations(gate_results, [], leaderboard, 1)
    assert mutations
    assert all(m["live_trading_enabled"] is False for m in mutations)
    assert all(m["fixture_allowed"] is False for m in mutations)


def test_loser_elimination_kills_fragile_cohorts() -> None:
    gate_results = [
        {**weak_leaderboard_row(), "rejection_reasons": ["net_pnl_not_positive", "expectancy_not_positive", "profit_factor_below_minimum"]},
    ]
    leaderboard = [weak_leaderboard_row()]
    kills = build_cohort_loser_elimination_v2(gate_results, leaderboard)
    assert kills
    assert all(k["exclude_from_future_mutation_seeding"] is True for k in kills)
    assert all(k["live_trading_enabled"] is False for k in kills)


def test_near_champion_repair_queue_generates_focuses() -> None:
    thresholds = champion_threshold_profile_v2()
    near_summary = evaluate_public_paper_champions_v2([near_champion_sample_row()], thresholds, artifact_mode="test", persist=True)
    # Repair plans are written into the sample_repair path; rebuild queue from the gate repair plans.
    repair_plans = [{
        "near_champion_label": "sample_count_insufficient_near_champion",
        "cohort_level": "variant_id",
        "cohort_id": "bollinger_expansion|fast_scalp|dte7|ATM",
        "target_sample_count": 30,
        "current_sample_count": 12,
        "estimated_new_candidates_needed": 60,
    }]
    queue = build_near_champion_repair_queue_v2(repair_plans)
    assert queue
    assert all(q["fixture_allowed"] is False for q in queue)
    assert all(q["live_trading_enabled"] is False for q in queue)
    assert near_summary["sample_repair_candidate_count"] >= 1


def test_scoreboard_separates_public_from_fixture() -> None:
    trades = sample_v4_trades()
    leaderboard = [champion_leaderboard_row(), weak_leaderboard_row()]
    gate_results = [{**champion_leaderboard_row(), "public_data_paper_champion": True}]
    scoreboard = build_public_signal_deepening_scoreboard_v4(trades, leaderboard, gate_results)
    assert scoreboard["public_data_only"] is True
    assert scoreboard["fixture_trade_count"] == 0
    assert scoreboard["live_trading_enabled"] is False


def test_official_robinhood_market_data_lane_allowed_and_unofficial_blocked() -> None:
    status = build_live_gate_status_v2({"public_paper_champion_count": 3})
    policy = status["robinhood_policy"]
    assert policy["official_robinhood_agent_mcp_market_data_allowed"] is True
    assert policy["official_robinhood_permitted_market_data_research_allowed"] is True
    assert policy["unofficial_robinhood_api_blocked"] is True
    assert policy["robinhood_scraping_blocked"] is True
    assert policy["robinhood_reverse_engineered_auth_blocked"] is True
    assert policy["robinhood_hidden_credentials_blocked"] is True
    assert policy["robinhood_live_trading_blocked"] is True
    assert policy["robinhood_real_orders_blocked"] is True


def test_live_gate_remains_disabled_even_if_champions_exist() -> None:
    status = build_live_gate_status_v2({"public_paper_champion_count": 5})
    assert status["live_gate_status"] == "disabled_live_gate_locked"
    assert status["live_trading_enabled"] is False
    assert status["broker_connection_enabled"] is False
    assert status["real_order_enabled"] is False
    assert status["human_live_approval_required"] is True
    assert status["paper_champion_hardening_required"] is True
    assert status["separate_future_bundle_required"] is True


def test_no_env_credentials_broker_orders_or_live_trading() -> None:
    status = build_live_gate_status_v2({"public_paper_champion_count": 0})
    assert not (REPO_ROOT / ".env").exists()
    assert status["credentials_present"] is False
    assert status["env_created"] is False
    assert status["broker_connection_used"] is False
    assert status["real_orders_placed"] is False
    assert status["live_trading_enabled"] is False


def test_full_orchestrator_declares_artifact_paths() -> None:
    paths = orchestrator_artifact_paths()
    assert "public_market_signal_mutation_deepening_v2_summary" in paths
    assert "public_market_signal_mutation_deepening_v2_validation_summary" in paths
    assert "public_market_signal_mutation_deepening_v2_timeout_records" in paths


def test_audit_report_export_review_recognize_v2_artifacts() -> None:
    spec_names = {spec[0] for spec in ARTIFACT_SPECS}
    rule_names = {rule.artifact_id for rule in export_selection_rules()}
    v2_artifacts = [
        "public_lake_final_state_lock_v2_summary",
        "strategy_cohort_summary",
        "public_signal_mutation_factory_v4_summary",
        "model_priced_path_simulator_v4_summary",
        "public_cohort_walk_forward_tournament_v4_summary",
        "public_paper_champion_gate_v2_summary",
        "public_signal_deepening_loop_v2_summary",
        "public_signal_deepening_scoreboard_v4",
        "public_signal_deepening_live_gate_status_v2",
        "public_market_signal_mutation_deepening_v2_summary",
        "public_market_signal_mutation_deepening_v2_validation_summary",
    ]
    for artifact_id in v2_artifacts:
        assert artifact_id in spec_names
        assert artifact_id in rule_names
    assert "public_champion_evolution" in FINDING_CATEGORIES
    assert "DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2" in ALLOWED_NEXT_BUILD_TARGETS


def test_validation_stabilizer_includes_deepening_v2_shard() -> None:
    files = collect_test_files(REPO_ROOT)
    assert "tests/test_public_market_signal_mutation_deepening_v2.py" in files


def test_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def public_rows() -> list[dict[str, str]]:
    prices = [100.0, 101.0, 102.0, 104.0, 106.0, 107.0, 109.0, 108.0, 110.0, 111.0, 112.0, 113.0]
    rows: list[dict[str, str]] = []
    for index, close in enumerate(prices):
        rows.append({
            "date": f"2024-01-{index + 1:02d}",
            "open": str(close - 0.5),
            "high": str(close + 1.0),
            "low": str(close - 1.0),
            "close": str(close),
            "volume": "1000000",
            "provider": "unit_public",
            "market_data_source_type": "public_live_fetch",
        })
    return rows


def long_call_signal_v4() -> dict[str, object]:
    return {
        "signal_id": "unit-signal-v4-1",
        "strategy_id": "bollinger_expansion|fast_scalp|dte7|ATM",
        "setup_family": "bollinger_expansion",
        "symbol": "SPY",
        "sector": "broad_etf",
        "timestamp": "2024-01-03",
        "date": "2024-01-03",
        "trade_intent": "long_call",
        "direction": "bullish",
        "entry_price": 102.0,
        "invalidation_level": 98.0,
        "target_price": 108.0,
        "hold_window": 5,
        "dte_bucket": 7,
        "moneyness_bucket": "ATM",
        "exit_policy": "fast_scalp",
        "iv_proxy_regime": "realized_vol",
        "slippage_stress": "normal",
        "theta_stress": "normal",
        "iv_shock_stress": "normal",
        "market_data_source_type": "public_live_fetch",
        "data_source_label": "public_live_fetch",
        "volatility_regime": "low_volatility",
        "trend_regime": "uptrend",
        "regime": "low_volatility",
    }


def feature_snapshot_v4() -> dict[str, object]:
    return {
        "symbol": "SPY",
        "date": "2024-01-03",
        "close": 100.0,
        "open": 99.5,
        "high": 101.0,
        "low": 99.0,
        "ma_10": 99.8,
        "ma_20": 99.5,
        "ma_50": 99.0,
        "ma_100": 98.5,
        "recent_high": 101.0,
        "recent_low": 99.0,
        "returns_20": 0.02,
        "spy_relative_strength": 0.01,
        "realized_vol_20": 0.22,
        "realized_vol_60": 0.20,
        "volume_ratio": 1.10,
        "rsi_proxy": 54.0,
        "gap": 0.005,
        "trend_regime": "uptrend",
        "volatility_regime": "low_volatility",
        "sector": "broad_etf",
    }


def sample_v4_trades() -> list[dict[str, object]]:
    symbols = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMD"]
    sectors = ["broad_etf", "broad_etf", "technology", "technology", "technology", "technology"]
    regimes = ["low_volatility", "high_volatility", "normal_volatility", "low_volatility", "high_volatility", "normal_volatility"]
    records: list[dict[str, object]] = []
    for index in range(90):
        symbol = symbols[index % len(symbols)]
        sector = sectors[index % len(sectors)]
        regime = regimes[index % len(regimes)]
        base = attach_cohort_ids({
            "trade_id": f"unit-trade-v4-{index}",
            "signal_id": f"unit-trade-v4-{index}",
            "strategy_id": "bollinger_expansion|fast_scalp|dte7|ATM",
            "variant_id": "bollinger_expansion|fast_scalp|dte7|ATM",
            "setup_family": "bollinger_expansion",
            "exit_policy": "fast_scalp",
            "dte_bucket": 7,
            "moneyness_bucket": "ATM",
            "symbol": symbol,
            "sector": sector,
            "regime": regime,
            "volatility_regime": regime,
            "direction": "bullish",
            "entry_date": f"2023-{(index % 9) + 1:02d}-15",
            "trade_intent": "long_call" if index % 2 == 0 else "long_put",
            "paper_pnl": 55.0 if index % 3 else -15.0,
            "market_data_source_type": "public_live_fetch",
            "data_source_label": "public_live_fetch",
            "slippage_stress": "high" if index % 4 == 0 else "normal",
            "iv_proxy_regime": "realized_vol_minus_10pct" if index % 5 == 0 else "realized_vol",
        })
        records.append(base)
    return records


def champion_leaderboard_row() -> dict[str, object]:
    return {
        "cohort_level": "variant_id",
        "cohort_id": "bollinger_expansion|fast_scalp|dte7|ATM",
        "net_pnl": 1400.0,
        "expectancy": 28.0,
        "profit_factor": 1.65,
        "max_drawdown": -380.0,
        "sample_count": 48,
        "symbol_count": 6,
        "sector_count": 2,
        "split_pass_rate": 0.74,
        "top_symbol_trade_share": 0.22,
        "top_regime_trade_share": 0.50,
        "worst_trade": -120.0,
        "high_slippage_net_pnl": 350.0,
        "theta_stress_net_pnl": 120.0,
        "iv_shock_negative_net_pnl": 90.0,
        "market_data_source_type": "public_live_fetch",
        "public_data_only": True,
        "fixture_trade_count": 0,
        "unsupported_structure": False,
    }


def weak_leaderboard_row() -> dict[str, object]:
    return {
        **champion_leaderboard_row(),
        "cohort_id": "weak_fragile_cohort",
        "net_pnl": -240.0,
        "expectancy": -5.0,
        "profit_factor": 0.82,
        "split_pass_rate": 0.12,
        "sample_count": 36,
    }


def near_champion_sample_row() -> dict[str, object]:
    return {
        **champion_leaderboard_row(),
        "cohort_level": "variant_id",
        "cohort_id": "atr_compression_breakout|trend_follow|dte14|1pct_otm",
        "sample_count": 12,
        "split_pass_rate": 0.82,
        "net_pnl": 420.0,
        "expectancy": 18.0,
        "profit_factor": 1.45,
        "symbol_count": 6,
        "sector_count": 2,
        "high_slippage_net_pnl": 120.0,
        "theta_stress_net_pnl": 60.0,
        "iv_shock_negative_net_pnl": 40.0,
    }
