from __future__ import annotations

from pathlib import Path

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_autonomy.run_wealth_engine_full_completion import run_wealth_engine_full_completion
from dopey_chart_vision.indicator_engine import build_indicator_rows
from dopey_chart_vision.run_chart_vision_engine import run_chart_vision_engine
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import FINDING_CATEGORIES
from dopey_live_gate.run_live_gate_status import run_live_gate_status
from dopey_market_intake.market_data_lake_builder import run_market_data_lake_builder
from dopey_options_engine.run_model_priced_trade_constructor import run_model_priced_trade_constructor
from dopey_risk_engine.run_risk_throttle_engine import run_risk_throttle_engine
from dopey_runtime_bootstrap.local_dependency_bootstrap import run_local_dependency_bootstrap
from dopey_scoreboard.run_performance_cockpit import run_performance_cockpit
from dopey_signal_engine.run_aggressive_signal_engine import run_aggressive_signal_engine
from dopey_tournament.run_paper_money_tournament_engine import run_paper_money_tournament_engine
from dopey_validation.full_suite_stabilizer import timeout_result
from dopey_wealth_engine.common import DATA_ROOT, REPO_ROOT, read_csv, read_jsonl
from dopey_wealth_engine.fixtures import ensure_wealth_engine_fixtures


def test_wealth_engine_market_vision_paper_tournament_completion() -> None:
    bootstrap = run_local_dependency_bootstrap(0)
    assert bootstrap["bootstrap_status"] in {"completed_with_installs", "completed_with_fallbacks"}
    assert bootstrap["credentials_created"] is False
    assert bootstrap["env_created"] is False
    assert bootstrap["broker_connection_used"] is False

    fixture_summary = ensure_wealth_engine_fixtures(DATA_ROOT / "fixtures" / "wealth_engine", 720)
    fixture_cases = read_jsonl(DATA_ROOT / "fixtures" / "wealth_engine" / "wealth_engine_cases.jsonl")
    assert fixture_summary["case_count"] >= 700
    assert len(fixture_cases) >= 700

    no_data = run_market_data_lake_builder(False, False)
    assert no_data["market_data_status"] == "blocked_no_market_data"

    market = run_market_data_lake_builder(False, True)
    assert market["market_data_status"] in {"loaded", "internal_fixture_fallback_loaded_blocked_no_public_market_data"}
    assert market["daily_ohlcv_rows"] > 0
    assert market["paper_trading_file_count"] + market["research_sandbox_file_count"] > 0
    assert market["credentials_created"] is False
    assert market["env_created"] is False
    assert market["broker_connection_used"] is False

    rows = read_csv(DATA_ROOT / "market_lake" / "normalized" / "daily_ohlcv" / "SPY.csv")
    indicators = build_indicator_rows("SPY", rows)
    latest = indicators[-1]
    assert latest["sma_8"] > 0
    assert latest["sma_21"] > 0
    assert latest["sma_50"] > 0
    assert latest["sma_200"] > 0
    assert latest["realized_vol_21"] >= 0
    assert 0 <= latest["rsi_14"] <= 100
    assert "macd" in latest

    chart = run_chart_vision_engine()
    assert chart["chart_vision_status"] == "charts_generated"
    assert chart["chart_count"] > 0
    assert Path(chart["artifact_paths"]["chart_html_root"]).exists()

    signals = run_aggressive_signal_engine()
    assert signals["signal_generation_status"] == "candidates_generated"
    assert signals["long_call_candidate_count"] > 0
    assert signals["long_put_candidate_count"] > 0
    assert signals["no_trade_count"] > 0

    options = run_model_priced_trade_constructor()
    assert options["model_priced_options_status"] == "candidates_generated"
    assert options["unsupported_structure_count"] == 0
    option_records = read_jsonl(Path(options["artifact_paths"]["model_priced_trade_candidates"]))
    assert option_records
    assert {record["trade_intent"] for record in option_records} <= {"long_call", "long_put", "no_trade"}
    assert {record["option_side"] for record in option_records} <= {"call", "put", "none"}
    assert all(record["paper_only"] is True and record["live_blocked"] is True for record in option_records)

    tournament = run_paper_money_tournament_engine()
    assert tournament["paper_tournament_status"] == "complete"
    assert tournament["paper_tournament_trade_count"] > 0
    assert tournament["winner_promotion_count"] >= 0
    assert tournament["loser_elimination_count"] >= 0

    scoreboard = run_performance_cockpit()
    assert scoreboard["pnl_scoreboard_status"] == "complete"
    assert Path(scoreboard["artifact_paths"]["performance_cockpit_html"]).exists()

    risk = run_risk_throttle_engine()
    assert risk["risk_throttle_status"] == "complete"
    assert risk["risk_throttle_count"] >= 0

    orchestrator = run_wealth_engine_full_completion(0, False, False)
    assert orchestrator["wealth_engine_status"] in {"market_vision_paper_tournament_complete", "complete_with_internal_fallback_blocked_no_market_data"}
    assert orchestrator["live_trading_enabled"] is False
    assert orchestrator["credentials_created"] is False
    assert orchestrator["env_created"] is False
    assert orchestrator["broker_connection_used"] is False

    live_gate = run_live_gate_status()
    assert live_gate["live_trading_enabled"] is False
    assert live_gate["broker_connection_enabled"] is False
    assert live_gate["real_order_enabled"] is False
    assert live_gate["credentials_present"] is False

    artifact_types = {spec[0] for spec in ARTIFACT_SPECS}
    assert "wealth_engine_full_completion_summary" in artifact_types
    assert "market_data_lake_summary" in artifact_types
    export_ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "wealth_engine_full_completion_summary" in export_ids
    assert "wealth_engine" in FINDING_CATEGORIES

    stabilizer_source = (REPO_ROOT / "dopey_validation" / "full_suite_stabilizer.py").read_text(encoding="utf-8")
    assert "tests/test_wealth_engine_market_vision_paper_tournament_completion.py" in stabilizer_source
    timeout = timeout_result(["python", "-m", "pytest"], 1)
    assert timeout["status"] == "inconclusive_timeout"
    assert timeout["timeout_recorded_as_pass"] is False

    assert not (REPO_ROOT / ".env").exists()
