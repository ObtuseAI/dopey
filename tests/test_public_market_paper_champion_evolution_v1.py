from __future__ import annotations

from dopey_autonomy.run_public_market_paper_champion_evolution import artifact_paths as orchestrator_artifact_paths
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS
from dopey_champion.public_champion_models import champion_threshold_profile_v1
from dopey_champion.public_paper_champion_gate import champion_decision
from dopey_evolution.public_champion_mutation_queue import build_public_champion_mutation_queue
from dopey_evolution.public_loser_kill_queue import build_public_loser_kill_queue
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import FINDING_CATEGORIES
from dopey_live_gate.public_champion_live_gate_status import build_public_champion_live_gate_status
from dopey_market_intake.public_lake_freeze_guard import freeze_guard_status_for_records
from dopey_market_intake.public_universe_expansion_v2 import (
    STARTING_WATCH_UNIVERSE_SIZE,
    TARGET_CANDIDATE_UNIVERSE_SIZE,
    candidate_symbol_universe_v2,
    expansion_status,
)
from dopey_options_engine.realized_path_trade_replayer import replay_signal_trade_v3
from dopey_risk_engine.public_champion_risk_engine_v3 import evaluate_public_champion_risk_v3
from dopey_scoreboard.public_champion_scoreboard_v3 import build_public_champion_scoreboard_v3
from dopey_signal_engine.public_signal_family_registry_v3 import public_signal_family_registry_v3
from dopey_signal_engine.public_signal_mutation_factory_v3 import build_parameter_grid_v3, build_signal_candidate
from dopey_tournament.public_holdout_tournament_v3 import build_public_holdout_scores_v3
from dopey_tournament.public_regime_tournament_v3 import build_public_regime_scores_v3
from dopey_tournament.public_walk_forward_tournament_v3 import build_walk_forward_scores
from dopey_validation.full_suite_stabilizer import collect_test_files, timeout_result
from dopey_wealth_engine.common import REPO_ROOT


def test_public_lake_freeze_guard_detects_fixture_contamination() -> None:
    status = freeze_guard_status_for_records([
        {"symbol": "SIMV2", "market_data_source_type": "fixture_fallback"},
    ])
    assert status == "public_lake_broken_contamination_detected"


def test_public_lake_freeze_guard_detects_clean_public_lake() -> None:
    status = freeze_guard_status_for_records([
        {"symbol": "SPY", "market_data_source_type": "public_live_fetch"},
    ])
    assert status == "public_lake_clean"


def test_public_universe_expansion_does_not_add_fixture_symbols() -> None:
    symbols = candidate_symbol_universe_v2()
    assert len(symbols) >= TARGET_CANDIDATE_UNIVERSE_SIZE
    assert len(symbols) == len(set(symbols))
    assert (
        expansion_status(len(symbols), STARTING_WATCH_UNIVERSE_SIZE, 0)
        == "public_universe_expanded_target_met"
    )


def test_model_priced_path_simulator_uses_future_ohlcv_path() -> None:
    trade, exits, _, _ = replay_signal_trade_v3(long_call_signal(), public_rows())
    assert trade["entry_date"] == "2024-01-03"
    assert trade["exit_date"] != trade["entry_date"]
    assert trade["exit_reason"] in {"target_hit", "option_target_hit", "max_hold_days", "time_stop", "drawdown_stop", "theta_bleed_stop", "invalidation_hit"}
    assert exits


def test_model_priced_path_simulator_produces_long_calls_long_puts_and_no_trade_only() -> None:
    call_trade, _, _, _ = replay_signal_trade_v3(long_call_signal(), public_rows())
    put_signal = {**long_call_signal(), "trade_intent": "long_put", "direction": "bearish", "invalidation_level": 106.0, "target_price": 96.0}
    put_trade, _, _, _ = replay_signal_trade_v3(put_signal, public_rows())
    no_trade_signal = {**long_call_signal(), "trade_intent": "no_trade", "option_side": "none"}
    no_trade, _, _, _ = replay_signal_trade_v3(no_trade_signal, public_rows())
    assert {call_trade["trade_intent"], put_trade["trade_intent"], no_trade["trade_intent"]} == {"long_call", "long_put", "no_trade"}


def test_model_priced_path_simulator_records_exit_reasons_and_never_shorts() -> None:
    trade, exits, _, _ = replay_signal_trade_v3(long_call_signal(), public_rows())
    assert trade["exit_reason"]
    assert exits[0]["exit_reason"] == trade["exit_reason"]
    assert trade["option_position"] == "long"
    assert trade["unsupported_structure"] is False


def test_signal_mutation_factory_generates_multiple_families_and_source_type() -> None:
    registry = public_signal_family_registry_v3()
    grid = build_parameter_grid_v3()
    signal = build_signal_candidate("SPY", {"date": "2024-01-03"}, feature_snapshot(), grid[0], "public_live_fetch", 1)
    assert len({record["setup_family"] for record in registry}) >= 20
    assert len(grid) > len(registry)
    assert signal["market_data_source_type"] == "public_live_fetch"


def test_walk_forward_holdout_and_regime_tournaments_produce_scores() -> None:
    trades = sample_trade_records()
    assert build_walk_forward_scores(trades)
    holdout_scores, symbol_scores = build_public_holdout_scores_v3(trades)
    assert holdout_scores
    assert symbol_scores
    assert build_public_regime_scores_v3(trades)


def test_champion_gate_rejects_fixture_derived_candidates() -> None:
    row = champion_row()
    decision = champion_decision({**row, "public_data_only": False, "fixture_trade_count": 2}, champion_threshold_profile_v1())
    assert decision["public_data_paper_champion"] is False
    assert "fixture_trades_present" in decision["rejection_reasons"]


def test_champion_gate_promotes_public_candidate_only_if_threshold_passes() -> None:
    decision = champion_decision(champion_row(), champion_threshold_profile_v1())
    assert decision["public_data_paper_champion"] is True
    assert decision["live_gate_candidate_locked"] is True


def test_champion_gate_does_not_lower_thresholds_silently() -> None:
    thresholds = champion_threshold_profile_v1()
    assert thresholds["minimum_trades"] == 30
    assert thresholds["minimum_profit_factor"] == 1.15
    assert thresholds["minimum_splits_passed_rate"] == 0.60


def test_scoreboard_separates_public_from_fixture() -> None:
    scoreboard = build_public_champion_scoreboard_v3(sample_trade_records(), [champion_row()], [{**champion_row(), "promotion_level": "public_paper_champion", "public_data_paper_champion": True}])
    assert scoreboard["public_data_only"] is True
    assert scoreboard["fixture_trade_count"] == 0


def test_risk_engine_creates_throttles_and_kill_records() -> None:
    summary = evaluate_public_champion_risk_v3([champion_row(), weak_row()], sample_trade_records())
    assert summary["risk_throttle_count"] >= summary["strategy_count"]
    assert summary["kill_switch_record_count"] >= 1


def test_evolution_loop_mutates_winners_and_kills_losers() -> None:
    mutations = build_public_champion_mutation_queue([champion_row(), weak_row()], [{"strategy_id": champion_row()["strategy_id"], "promotion_level": "public_watchlist"}], 1)
    kills = build_public_loser_kill_queue([champion_row(), weak_row()], 1)
    assert mutations
    assert kills


def test_live_gate_remains_disabled_even_if_champions_exist() -> None:
    status = build_public_champion_live_gate_status({"public_paper_champion_count": 2, "live_gate_candidate_locked_count": 2})
    assert status["live_trading_enabled"] is False
    assert status["broker_connection_enabled"] is False
    assert status["real_order_enabled"] is False


def test_no_env_credentials_broker_orders_or_live_trading() -> None:
    status = build_public_champion_live_gate_status({"public_paper_champion_count": 0, "live_gate_candidate_locked_count": 0})
    assert not (REPO_ROOT / ".env").exists()
    assert status["credentials_present"] is False
    assert status["broker_connection_enabled"] is False
    assert status["real_order_enabled"] is False
    assert status["live_trading_enabled"] is False


def test_full_orchestrator_declares_artifacts() -> None:
    paths = orchestrator_artifact_paths()
    assert "public_market_paper_champion_evolution_summary" in paths
    assert "public_market_paper_champion_validation_summary" in paths


def test_audit_report_export_review_recognize_artifacts() -> None:
    spec_names = {spec[0] for spec in ARTIFACT_SPECS}
    rule_names = {rule.artifact_id for rule in export_selection_rules()}
    assert "public_market_paper_champion_evolution_summary" in spec_names
    assert "public_market_paper_champion_evolution_summary" in rule_names
    assert "public_champion_evolution" in FINDING_CATEGORIES
    assert "DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1" in ALLOWED_NEXT_BUILD_TARGETS


def test_validation_stabilizer_includes_public_champion_shard() -> None:
    files = collect_test_files(REPO_ROOT)
    assert "tests/test_public_market_paper_champion_evolution_v1.py" in files


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


def long_call_signal() -> dict[str, object]:
    return {
        "signal_id": "unit-signal-1",
        "strategy_id": "volatility_squeeze_breakout|trend_follow|dte14|ATM",
        "setup_family": "volatility_squeeze_breakout",
        "symbol": "SPY",
        "sector": "broad_etf",
        "timestamp": "2024-01-03",
        "trade_intent": "long_call",
        "direction": "bullish",
        "entry_price": 102.0,
        "invalidation_level": 98.0,
        "target_price": 108.0,
        "hold_window": 5,
        "dte_bucket": 14,
        "moneyness_bucket": "ATM",
        "exit_policy": "trend_follow",
        "iv_proxy_regime": "realized_vol",
        "slippage_stress": "normal",
        "market_data_source_type": "public_live_fetch",
        "data_source_label": "public_live_fetch",
        "volatility_regime": "low_volatility",
        "trend_regime": "uptrend",
    }


def feature_snapshot() -> dict[str, object]:
    return {
        "close": 100.0,
        "realized_vol_20": 0.22,
        "spy_relative_strength": 0.03,
        "trend_regime": "uptrend",
        "volatility_regime": "low_volatility",
        "sector": "broad_etf",
    }


def sample_trade_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    symbols = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMD"]
    for index in range(36):
        records.append({
            "strategy_id": champion_row()["strategy_id"],
            "setup_family": "volatility_squeeze_breakout",
            "symbol": symbols[index % len(symbols)],
            "sector": "technology",
            "entry_date": f"202{index % 6}-03-15",
            "trade_intent": "long_call" if index % 2 == 0 else "long_put",
            "paper_pnl": 45.0 if index % 3 else -18.0,
            "market_data_source_type": "public_live_fetch",
            "regime": "high_volatility" if index % 4 == 0 else "low_volatility",
            "trend_regime": "uptrend" if index % 3 else "downtrend",
            "slippage_stress": "high" if index % 4 == 0 else "normal",
            "iv_proxy_regime": "realized_vol_minus_10pct" if index % 5 == 0 else "realized_vol",
            "dte_bucket": 14,
        })
    return records


def champion_row() -> dict[str, object]:
    return {
        "strategy_id": "volatility_squeeze_breakout|trend_follow|dte14|ATM",
        "setup_family": "volatility_squeeze_breakout",
        "net_pnl": 1200.0,
        "expectancy": 25.0,
        "profit_factor": 1.62,
        "max_drawdown": -420.0,
        "sample_count": 48,
        "symbol_count": 8,
        "split_pass_rate": 0.72,
        "top_symbol_trade_share": 0.22,
        "top_regime_trade_share": 0.55,
        "worst_trade": -120.0,
        "high_slippage_net_pnl": 300.0,
        "theta_stress_net_pnl": 100.0,
        "iv_shock_negative_net_pnl": 80.0,
        "market_data_source_type": "public_live_fetch",
        "public_data_only": True,
        "fixture_trade_count": 0,
    }


def weak_row() -> dict[str, object]:
    return {**champion_row(), "strategy_id": "weak_strategy", "net_pnl": -50.0, "profit_factor": 0.8, "split_pass_rate": 0.1}
