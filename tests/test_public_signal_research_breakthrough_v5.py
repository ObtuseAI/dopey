from __future__ import annotations

from pathlib import Path

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS
from dopey_autonomy.public_champion_common import is_test_symbol, read_json_file, read_jsonl_file
from dopey_autonomy.signal_research_v5_common import (
    MIN_BREAKTHROUGH_PF,
    V5_CONTINUATION_SUBFAMILIES,
    V5_MIN_CANDIDATES,
    V5_MIN_TRADES,
    V5_VOLUME_SUBFAMILIES,
    CANDIDATES_V5_PATH,
    TRADES_V5_PATH,
)
from dopey_export.artifact_selector import export_selection_rules
from dopey_validation.full_suite_stabilizer import collect_test_files
from dopey_wealth_engine.common import REPO_ROOT


pytestmark = pytest.mark.usefixtures("public_signal_research_v5_checkpoint")


# ---------------------------------------------------------------------------
# A. Preflight
# ---------------------------------------------------------------------------


def test_v5_preflight_loads_v4_complete_state() -> None:
    from dopey_validation.public_signal_research_v5_preflight import run_public_signal_research_v5_preflight

    summary = run_public_signal_research_v5_preflight()
    assert summary["public_signal_research_v5_preflight_status"] == "ready_for_breakthrough_finishing_loop"
    assert summary["v4_summary_status"] == "pf_holdout_split_improved_requires_v5"
    assert summary["v4_live_gate_status"] == "disabled_live_gate_locked"


def test_v5_preflight_does_not_allow_lower_pf_threshold() -> None:
    assert MIN_BREAKTHROUGH_PF == 1.10


# ---------------------------------------------------------------------------
# B. V4 baseline freeze
# ---------------------------------------------------------------------------


def test_v5_baseline_freeze_writes_immutable_snapshots() -> None:
    from dopey_validation.public_signal_research_baseline_freezer_v5 import run_public_signal_research_baseline_freezer_v5

    summary = run_public_signal_research_baseline_freezer_v5()
    assert summary["baseline_freeze_status"] == "v4_baseline_frozen"
    assert int(summary["copied_count"]) > 0


# ---------------------------------------------------------------------------
# C. Safe append
# ---------------------------------------------------------------------------


def test_v5_safe_append_does_not_corrupt_long_docs() -> None:
    from dopey_validation.safe_append_canon_validation_docs_v5 import run_safe_append_canon_validation_docs_v5

    summary = run_safe_append_canon_validation_docs_v5()
    assert summary["safe_append_docs_status"] in {"safe_append_completed", "safe_append_already_present"}
    assert summary["invalid_utf8_detected"] is False


# ---------------------------------------------------------------------------
# D. Optional expensive lane runner
# ---------------------------------------------------------------------------


def test_v5_expensive_lane_records_timeouts_honestly() -> None:
    from dopey_validation.public_signal_research_expensive_lane_runner_v5 import run_public_signal_research_expensive_lane_runner_v5

    summary = run_public_signal_research_expensive_lane_runner_v5()
    assert summary["timeout_recorded_as_pass"] is False
    assert summary["optional_timeout_does_not_block_v5"] is True


# ---------------------------------------------------------------------------
# E. V4 result analyzer
# ---------------------------------------------------------------------------


def test_v5_v4_result_analyzer_extracts_repair_targets() -> None:
    from dopey_signal_research.run_v4_result_analyzer_v5 import main as v4_analyzer_main

    # Running the CLI module populates the analyzer artifacts.
    v4_analyzer_main()
    from dopey_autonomy.signal_research_v5_common import V4_ANALYZER_V5_SUMMARY_PATH

    summary = read_json_file(V4_ANALYZER_V5_SUMMARY_PATH)
    assert summary["v4_result_analyzer_status"] == "v4_result_analyzer_complete_v5"
    assert int(summary["v4_repair_target_count"]) >= 1


# ---------------------------------------------------------------------------
# F. Mutation executor
# ---------------------------------------------------------------------------


def test_v5_mutation_executor_executes_or_records_v4_queue() -> None:
    from dopey_signal_research.research_mutation_queue_executor_v5 import execute_v5_mutation_queue

    summary = execute_v5_mutation_queue()
    assert summary["research_mutation_queue_executor_v5_status"] == "research_mutation_queue_executed_v5"
    assert int(summary.get("executed_mutation_count", 0)) >= 1


# ---------------------------------------------------------------------------
# G. No-trade filter optimizer
# ---------------------------------------------------------------------------


def test_v5_no_trade_optimizer_blocks_future_leakage() -> None:
    from dopey_signal_research.no_trade_filter_optimizer_v5 import run_no_trade_filter_optimizer_v5

    summary = run_no_trade_filter_optimizer_v5()
    assert int(summary.get("filter_rule_count", 0)) >= 1
    assert summary.get("future_leakage_detected") is False


# ---------------------------------------------------------------------------
# H. Candidate generator
# ---------------------------------------------------------------------------


def test_v5_candidate_generator_meets_minimum_count() -> None:
    from dopey_signal_research.research_candidate_generator_v5 import run_research_candidate_generator_v5

    summary = run_research_candidate_generator_v5()
    assert int(summary.get("candidate_count", 0)) >= V5_MIN_CANDIDATES


def test_v5_candidate_generator_excludes_sim_test_fixture_synth() -> None:
    assert is_test_symbol("SIMV5")
    assert is_test_symbol("TESTX")
    assert is_test_symbol("FIXTURE_001")
    assert is_test_symbol("SYNTH_X")
    assert not is_test_symbol("SPY")

    rows = read_jsonl_file(CANDIDATES_V5_PATH)
    assert rows
    assert not any(is_test_symbol(str(row.get("symbol", ""))) for row in rows)
    assert int(summary_fixture_count(rows)) == 0


def summary_fixture_count(rows: list[dict]) -> int:
    # The generator summary tracks fixture_candidate_count; raw rows use forbidden-symbol logic.
    return sum(1 for row in rows if is_test_symbol(str(row.get("symbol", ""))))


def test_v5_candidate_generator_emits_eight_subfamilies() -> None:
    from dopey_signal_research.research_candidate_generator_v5 import run_research_candidate_generator_v5

    summary = run_research_candidate_generator_v5()
    assert int(summary.get("subfamily_count", 0)) == len(V5_CONTINUATION_SUBFAMILIES) + len(V5_VOLUME_SUBFAMILIES)


def test_v5_candidate_generator_long_call_long_put_no_trade() -> None:
    from dopey_signal_research.research_candidate_generator_v5 import run_research_candidate_generator_v5

    summary = run_research_candidate_generator_v5()
    assert int(summary.get("long_call_count", 0)) >= 1
    assert int(summary.get("long_put_count", 0)) >= 1
    assert int(summary.get("no_trade_count", 0)) >= 1


def test_v5_candidate_generator_includes_hold_window() -> None:
    rows = read_jsonl_file(CANDIDATES_V5_PATH)
    assert rows
    assert all("hold_window" in row for row in rows[:50])


def test_v5_candidate_generator_records_source_mutation_id() -> None:
    rows = read_jsonl_file(CANDIDATES_V5_PATH)
    assert rows
    assert any(str(row.get("source_v5_mutation_id", "")) for row in rows[:200])


# ---------------------------------------------------------------------------
# I. PF / holdout / split scorer
# ---------------------------------------------------------------------------


def test_v5_profit_holdout_split_scorer_prioritizes_repair_candidates() -> None:
    from dopey_signal_research.profit_holdout_split_scorer_v5 import run_profit_holdout_split_scorer_v5

    summary = run_profit_holdout_split_scorer_v5()
    assert int(summary.get("prioritized_candidate_count", 0)) >= 1


# ---------------------------------------------------------------------------
# J. Path simulator
# ---------------------------------------------------------------------------


def test_v5_path_simulator_uses_future_ohlcv_paths() -> None:
    from dopey_signal_research.research_path_simulator_v5 import run_research_path_simulator_v5

    summary = run_research_path_simulator_v5()
    assert summary.get("future_ohlcv_used") is True
    assert summary.get("model_priced") is True
    assert summary.get("quote_priced") is False


def test_v5_path_simulator_long_call_long_put_no_trade_only() -> None:
    from dopey_signal_research.research_path_simulator_v5 import run_research_path_simulator_v5

    summary = run_research_path_simulator_v5()
    assert summary.get("short_call_count", 0) == 0
    assert summary.get("short_put_count", 0) == 0
    assert summary.get("spread_count", 0) == 0
    assert summary.get("public_data_only") is True
    assert int(summary.get("simulated_trade_count", 0)) >= V5_MIN_TRADES
    long_call = int(summary.get("long_call_count", 0))
    long_put = int(summary.get("long_put_count", 0))
    no_trade = int(summary.get("no_trade_count", 0))
    assert long_call + long_put + no_trade == int(summary.get("simulated_trade_count", 0))


def test_v5_path_simulator_never_emits_short_or_spread() -> None:
    trades = read_jsonl_file(TRADES_V5_PATH)
    assert trades
    assert all(str(t.get("direction", "")) in {"long_call", "long_put", "no_trade"} for t in trades)


# ---------------------------------------------------------------------------
# K. Tournament + V4 comparison
# ---------------------------------------------------------------------------


def test_v5_tournament_groups_by_subfamily() -> None:
    from dopey_signal_research.research_tournament_v5 import run_research_tournament_v5

    summary = run_research_tournament_v5()
    assert int(summary.get("subfamily_count", 0)) >= 1
    assert int(summary.get("family_count", 0)) >= 1
    assert int(summary.get("cohort_count", 0)) >= 1


def test_v5_tournament_compares_v4() -> None:
    from dopey_signal_research.research_tournament_v5 import run_research_tournament_v5

    summary = run_research_tournament_v5()
    assert "v4_top_pf" in summary
    assert "improved_vs_v4_count" in summary


# ---------------------------------------------------------------------------
# L. Breakthrough gate
# ---------------------------------------------------------------------------


def test_v5_breakthrough_gate_does_not_lower_pf_threshold() -> None:
    from dopey_signal_research.research_breakthrough_gate_v5 import run_research_breakthrough_gate_v5

    summary = run_research_breakthrough_gate_v5()
    assert float(summary.get("v5_min_breakthrough_pf", 0.0)) == 1.10
    assert summary.get("thresholds_lowered") is False


# ---------------------------------------------------------------------------
# M. Mutation queue V5
# ---------------------------------------------------------------------------


def test_v5_mutation_queue_nonempty_when_watchlist_exists() -> None:
    from dopey_signal_research.research_mutation_queue_v5 import run_research_mutation_queue_v5

    summary = run_research_mutation_queue_v5()
    assert int(summary.get("mutation_queue_count", 0)) >= 1


# ---------------------------------------------------------------------------
# N. Scoreboard V5
# ---------------------------------------------------------------------------


def test_v5_scoreboard_writes_json_html() -> None:
    from dopey_scoreboard import public_signal_research_scoreboard_v5 as scoreboard_module

    summary = scoreboard_module.run_public_signal_research_scoreboard_v5()
    assert summary["scoreboard_v5_status"] == "public_signal_research_scoreboard_complete_v5"
    assert scoreboard_module.HTML_PATH.exists()
    assert scoreboard_module.SCOREBOARD_PATH.exists()


# ---------------------------------------------------------------------------
# O. Live gate V5
# ---------------------------------------------------------------------------


def test_v5_live_gate_remains_disabled() -> None:
    from dopey_live_gate.public_signal_research_live_gate_status_v5 import run_public_signal_research_live_gate_status_v5

    status = run_public_signal_research_live_gate_status_v5()
    assert status["live_gate_status"] == "disabled_live_gate_locked"
    assert status["live_trading_enabled"] is False
    assert status["broker_connection_enabled"] is False
    assert status["real_order_enabled"] is False
    assert status["credentials_present"] is False
    assert status["env_present"] is False
    assert status["official_robinhood_market_data_allowed"] is True
    assert status["unofficial_robinhood_api_blocked"] is True
    assert status["robinhood_live_trading_enabled"] is False
    assert status["robinhood_scraping_blocked"] is True
    assert status["robinhood_reverse_auth_blocked"] is True


# ---------------------------------------------------------------------------
# P. Safety / no live / no .env / no credentials / no broker
# ---------------------------------------------------------------------------


def test_v5_no_env_credentials_broker() -> None:
    assert not (REPO_ROOT / ".env").exists()
    forbidden = [".env", ".env.local", ".env.bak", "credentials.json", "broker.env"]
    for fname in forbidden:
        assert not (REPO_ROOT / fname).exists(), f"forbidden file present: {fname}"


def test_v5_official_robinhood_market_data_lane_allowed() -> None:
    from dopey_autonomy.champion_hardening_common import robinhood_policy_fields

    fields = robinhood_policy_fields()
    assert fields.get("official_robinhood_market_data_allowed") is True
    assert fields.get("unofficial_robinhood_api_blocked") is True
    assert fields.get("robinhood_scraping_blocked") is True
    assert fields.get("robinhood_reverse_auth_blocked") is True
    assert fields.get("robinhood_live_trading_enabled") is False


# ---------------------------------------------------------------------------
# Q. Orchestrator
# ---------------------------------------------------------------------------


def test_v5_orchestrator_writes_artifacts() -> None:
    from dopey_autonomy.run_public_signal_research_breakthrough_v5 import orchestrator_artifact_paths

    paths = orchestrator_artifact_paths()
    assert "public_signal_research_breakthrough_v5_summary" in paths
    assert "public_signal_research_breakthrough_v5_validation_summary" in paths
    assert Path(paths["public_signal_research_breakthrough_v5_summary"]).exists()
    assert Path(paths["public_signal_research_breakthrough_v5_validation_summary"]).exists()


# ---------------------------------------------------------------------------
# R. Audit / report / export / review recognize V5
# ---------------------------------------------------------------------------


def test_v5_audit_recognize_v5_artifacts() -> None:
    keys = {spec[0] for spec in ARTIFACT_SPECS}
    assert "public_signal_research_breakthrough_v5_summary" in keys
    assert "public_signal_research_breakthrough_v5_validation_summary" in keys
    assert "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5" in ALLOWED_NEXT_BUILD_TARGETS


def test_v5_export_recognize_v5_artifacts() -> None:
    ids = {row.artifact_id for row in export_selection_rules()}
    assert "public_signal_research_breakthrough_v5_summary" in ids
    assert "public_signal_research_breakthrough_v5_validation_summary" in ids
    assert "research_breakthrough_gate_v5_summary" in ids
    assert "research_tournament_v5_summary" in ids
    assert "public_signal_research_scoreboard_v5" in ids
    assert "public_signal_research_live_gate_status_v5" in ids


def test_v5_validation_stabilizer_includes_shard() -> None:
    files = collect_test_files()
    assert "tests/test_public_signal_research_breakthrough_v5.py" in files


# ---------------------------------------------------------------------------
# S. Timeout discipline
# ---------------------------------------------------------------------------


def test_v5_timeout_not_pass() -> None:
    from dopey_validation.full_suite_stabilizer import timeout_result

    assert timeout_result(["pytest"], 60)["timeout_recorded_as_pass"] is False
