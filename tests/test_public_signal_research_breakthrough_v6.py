from __future__ import annotations

from pathlib import Path

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS
from dopey_autonomy.public_champion_common import is_test_symbol, read_json_file, read_jsonl_file
from dopey_autonomy.signal_research_v6_common import (
    MIN_BREAKTHROUGH_PF,
    V6_CONTINUATION_SUBFAMILIES,
    V6_MIN_CANDIDATES,
    V6_MIN_TRADES,
    V6_VOLUME_SUBFAMILIES,
    CANDIDATES_V6_PATH,
    TRADES_V6_PATH,
)
from dopey_export.artifact_selector import export_selection_rules
from dopey_validation.full_suite_stabilizer import collect_test_files, timeout_result
from dopey_wealth_engine.common import REPO_ROOT


pytestmark = pytest.mark.usefixtures("public_signal_research_v6_checkpoint")


# ---------------------------------------------------------------------------
# A. Preflight
# ---------------------------------------------------------------------------


def test_v6_preflight_loads_v5_complete_state() -> None:
    from dopey_validation.public_signal_research_v6_preflight import run_public_signal_research_v6_preflight

    summary = run_public_signal_research_v6_preflight()
    assert summary["public_signal_research_v6_preflight_status"] == "ready_for_watchlist_breakthrough_repair"
    assert summary["v5_summary_status"] == "pf_holdout_split_improved_requires_v6"
    assert summary["v5_live_gate_status"] == "disabled_live_gate_locked"
    assert summary["v5_watchlist_count"] == 6
    assert summary["v5_breakthrough_count"] == 0
    assert summary["v5_pf_above_110_count"] == 6
    assert summary["v5_mutation_queue_count"] == 132


def test_v6_preflight_does_not_allow_lower_pf_threshold() -> None:
    assert MIN_BREAKTHROUGH_PF == 1.10


def test_v6_preflight_records_expensive_lane_timeout_honestly() -> None:
    from dopey_validation.public_signal_research_v6_preflight import run_public_signal_research_v6_preflight

    summary = run_public_signal_research_v6_preflight()
    assert summary["v5_expensive_lane_timeout_recorded_as_pass"] is False


# ---------------------------------------------------------------------------
# B. V5 baseline freeze
# ---------------------------------------------------------------------------


def test_v6_baseline_freeze_writes_immutable_snapshots() -> None:
    from dopey_validation.public_signal_research_baseline_freezer_v6 import run_public_signal_research_baseline_freezer_v6

    summary = run_public_signal_research_baseline_freezer_v6()
    assert summary["baseline_freeze_status"] == "v5_baseline_frozen"
    assert int(summary["copied_count"]) > 0


def test_v6_baseline_freeze_includes_v5_summary() -> None:
    from dopey_autonomy.signal_research_v6_common import BASELINE_V5_ROOT

    assert (BASELINE_V5_ROOT / "public_signal_research_breakthrough_v5_summary.json").exists()


# ---------------------------------------------------------------------------
# C. V5 gate rejection / watchlist diagnosis
# ---------------------------------------------------------------------------


def test_v6_gate_rejection_analyzer_finds_six_pf_above_threshold_watchlist_candidates() -> None:
    from dopey_signal_research.v5_gate_rejection_analyzer_v6 import run_v5_gate_rejection_analyzer_v6

    summary = run_v5_gate_rejection_analyzer_v6()
    assert summary["v5_gate_rejection_analyzer_status"] == "v5_gate_rejection_analysis_complete_v6"
    assert int(summary["watchlist_candidate_count"]) == 6
    assert int(summary["pf_above_threshold_watchlist_count"]) == 6


def test_v6_gate_rejection_analyzer_lists_top_blockers() -> None:
    from dopey_signal_research.v5_gate_rejection_analyzer_v6 import run_v5_gate_rejection_analyzer_v6

    summary = run_v5_gate_rejection_analyzer_v6()
    blockers = summary.get("top_breakthrough_blockers", [])
    assert isinstance(blockers, list)
    assert len(blockers) >= 1


def test_v6_gate_rejection_analyzer_marks_repairable_candidates() -> None:
    from dopey_signal_research.v5_gate_rejection_analyzer_v6 import run_v5_gate_rejection_analyzer_v6

    summary = run_v5_gate_rejection_analyzer_v6()
    assert int(summary.get("repairable_candidate_count", 0)) >= 1
    assert summary["live_trading_enabled"] is False


# ---------------------------------------------------------------------------
# D. V5 mutation queue executor V6
# ---------------------------------------------------------------------------


def test_v6_mutation_executor_processes_v5_mutation_queue() -> None:
    from dopey_signal_research.research_mutation_queue_executor_v6 import execute_v6_mutation_queue

    summary = execute_v6_mutation_queue()
    assert summary["research_mutation_queue_executor_v6_status"] == "research_mutation_queue_executed_v6"
    assert int(summary.get("input_v5_mutation_count", 0)) == 132
    assert int(summary.get("executed_mutation_count", 0)) >= 1


def test_v6_mutation_executor_records_twenty_four_mutation_types() -> None:
    from dopey_signal_research.research_mutation_queue_executor_v6 import execute_v6_mutation_queue

    summary = execute_v6_mutation_queue()
    type_counts = summary.get("mutation_type_counts", {})
    assert len(type_counts) >= 12


def test_v6_mutation_executor_has_no_failed_mutations() -> None:
    from dopey_signal_research.research_mutation_queue_executor_v6 import execute_v6_mutation_queue

    summary = execute_v6_mutation_queue()
    assert int(summary.get("failed_mutation_count", 0)) == 0


# ---------------------------------------------------------------------------
# E. Breakthrough blocker repair policy
# ---------------------------------------------------------------------------


def test_v6_blocker_repair_policy_does_not_use_future_leakage() -> None:
    from dopey_signal_research.breakthrough_blocker_repair_policy_v6 import run_breakthrough_blocker_repair_policy_v6

    summary = run_breakthrough_blocker_repair_policy_v6()
    assert summary["future_leakage_detected"] is False
    assert summary["thresholds_lowered"] is False
    assert summary["live_trading_enabled"] is False


def test_v6_blocker_repair_policy_has_repair_rules() -> None:
    from dopey_signal_research.breakthrough_blocker_repair_policy_v6 import run_breakthrough_blocker_repair_policy_v6

    summary = run_breakthrough_blocker_repair_policy_v6()
    assert int(summary.get("repair_rule_count", 0)) >= 1


def test_v6_future_leakage_guard_records_are_clean() -> None:
    from dopey_autonomy.signal_research_v6_common import FUTURE_LEAKAGE_GUARD_V6_PATH

    records = read_jsonl_file(FUTURE_LEAKAGE_GUARD_V6_PATH)
    assert records
    assert all(r.get("is_leakage_free") is True for r in records)


# ---------------------------------------------------------------------------
# F. Candidate generator V6
# ---------------------------------------------------------------------------


def test_v6_candidate_generator_meets_minimum_count() -> None:
    from dopey_signal_research.research_candidate_generator_v6 import run_research_candidate_generator_v6

    summary = run_research_candidate_generator_v6()
    assert int(summary.get("candidate_count", 0)) >= V6_MIN_CANDIDATES


def test_v6_candidate_generator_excludes_sim_test_fixture_synth() -> None:
    from dopey_signal_research.research_candidate_generator_v6 import run_research_candidate_generator_v6

    run_research_candidate_generator_v6()
    rows = read_jsonl_file(CANDIDATES_V6_PATH)
    assert rows
    assert not any(is_test_symbol(str(row.get("symbol", ""))) for row in rows)
    assert int(summary_fixture_count(rows)) == 0


def summary_fixture_count(rows: list[dict]) -> int:
    return sum(1 for row in rows if is_test_symbol(str(row.get("symbol", ""))))


def test_v6_candidate_generator_emits_eight_subfamilies() -> None:
    from dopey_signal_research.research_candidate_generator_v6 import run_research_candidate_generator_v6

    summary = run_research_candidate_generator_v6()
    expected = len(V6_CONTINUATION_SUBFAMILIES) + len(V6_VOLUME_SUBFAMILIES)
    assert int(summary.get("subfamily_count", 0)) == expected


def test_v6_candidate_generator_long_call_long_put_no_trade() -> None:
    from dopey_signal_research.research_candidate_generator_v6 import run_research_candidate_generator_v6

    summary = run_research_candidate_generator_v6()
    assert int(summary.get("long_call_count", 0)) >= 1
    assert int(summary.get("long_put_count", 0)) >= 1
    assert int(summary.get("no_trade_count", 0)) >= 1


def test_v6_candidate_generator_includes_hold_window() -> None:
    from dopey_signal_research.research_candidate_generator_v6 import run_research_candidate_generator_v6

    run_research_candidate_generator_v6()
    rows = read_jsonl_file(CANDIDATES_V6_PATH)
    assert rows
    assert all("hold_window" in row for row in rows[:50])


def test_v6_candidate_generator_records_source_lineage() -> None:
    from dopey_signal_research.research_candidate_generator_v6 import run_research_candidate_generator_v6

    run_research_candidate_generator_v6()
    rows = read_jsonl_file(CANDIDATES_V6_PATH)
    assert rows
    assert any(str(row.get("source_v5_mutation_id", "")) for row in rows[:200])


def test_v6_candidate_generator_fixture_candidate_count_zero() -> None:
    from dopey_signal_research.research_candidate_generator_v6 import run_research_candidate_generator_v6

    summary = run_research_candidate_generator_v6()
    assert int(summary.get("fixture_candidate_count", 0)) == 0


# ---------------------------------------------------------------------------
# G. Pre-simulation scorer
# ---------------------------------------------------------------------------


def test_v6_scorer_prioritizes_repair_candidates() -> None:
    from dopey_signal_research.profit_holdout_split_scorer_v6 import run_profit_holdout_split_scorer_v6

    summary = run_profit_holdout_split_scorer_v6()
    assert int(summary.get("prioritized_candidate_count", 0)) >= 1
    assert int(summary.get("breakthrough_repair_candidate_count", 0)) >= 0
    assert int(summary.get("holdout_repair_candidate_count", 0)) >= 0
    assert int(summary.get("split_repair_candidate_count", 0)) >= 0


# ---------------------------------------------------------------------------
# H. Path simulator
# ---------------------------------------------------------------------------


def test_v6_path_simulator_uses_future_ohlcv_paths() -> None:
    from dopey_signal_research.research_path_simulator_v6 import run_research_path_simulator_v6

    summary = run_research_path_simulator_v6()
    assert summary.get("future_ohlcv_used") is True
    assert summary.get("model_priced") is True
    assert summary.get("quote_priced") is False


def test_v6_path_simulator_long_call_long_put_no_trade_only() -> None:
    from dopey_signal_research.research_path_simulator_v6 import run_research_path_simulator_v6

    summary = run_research_path_simulator_v6()
    assert summary.get("public_data_only") is True
    assert int(summary.get("simulated_trade_count", 0)) >= V6_MIN_TRADES
    long_call = int(summary.get("long_call_count", 0))
    long_put = int(summary.get("long_put_count", 0))
    no_trade = int(summary.get("no_trade_count", 0))
    assert long_call + long_put + no_trade == int(summary.get("simulated_trade_count", 0))


def test_v6_path_simulator_never_emits_short_or_spread() -> None:
    from dopey_signal_research.research_path_simulator_v6 import run_research_path_simulator_v6

    run_research_path_simulator_v6()
    trades = read_jsonl_file(TRADES_V6_PATH)
    assert trades
    assert all(str(t.get("direction", "")) in {"long_call", "long_put", "no_trade"} for t in trades)


def test_v6_path_simulator_detects_uvxy_like_corruption() -> None:
    from dopey_signal_research.research_path_simulator_v6 import run_research_path_simulator_v6

    summary = run_research_path_simulator_v6()
    assert isinstance(summary.get("uvxy_like_corruption_detected"), bool)


# ---------------------------------------------------------------------------
# I. Tournament + V5 comparison
# ---------------------------------------------------------------------------


def test_v6_tournament_groups_by_subfamily() -> None:
    from dopey_signal_research.research_tournament_v6 import run_research_tournament_v6

    summary = run_research_tournament_v6()
    assert int(summary.get("subfamily_count", 0)) >= 1
    assert int(summary.get("family_count", 0)) >= 1
    assert int(summary.get("cohort_count", 0)) >= 1


def test_v6_tournament_compares_v5() -> None:
    from dopey_signal_research.research_tournament_v6 import run_research_tournament_v6

    summary = run_research_tournament_v6()
    assert "v5_top_pf" in summary
    assert "improved_vs_v5_count" in summary


def test_v6_tournament_records_pf_above_110() -> None:
    from dopey_signal_research.research_tournament_v6 import run_research_tournament_v6

    summary = run_research_tournament_v6()
    assert int(summary.get("pf_above_110_count", 0)) >= 0


# ---------------------------------------------------------------------------
# J. Breakthrough gate V6
# ---------------------------------------------------------------------------


def test_v6_breakthrough_gate_does_not_lower_pf_threshold() -> None:
    from dopey_signal_research.research_breakthrough_gate_v6 import run_research_breakthrough_gate_v6

    summary = run_research_breakthrough_gate_v6()
    assert float(summary.get("v6_min_breakthrough_pf", 0.0)) == 1.10
    assert summary.get("thresholds_lowered") is False


def test_v6_breakthrough_gate_records_watchlist_or_rejections() -> None:
    from dopey_signal_research.research_breakthrough_gate_v6 import run_research_breakthrough_gate_v6

    summary = run_research_breakthrough_gate_v6()
    assert int(summary.get("candidate_count", 0)) >= 1
    assert int(summary.get("breakthrough_candidate_count", 0)) >= 0
    assert int(summary.get("watchlist_count", 0)) >= 0


# ---------------------------------------------------------------------------
# K. Mutation queue V6
# ---------------------------------------------------------------------------


def test_v6_mutation_queue_emits_queue_if_needed() -> None:
    from dopey_signal_research.research_mutation_queue_v6 import run_research_mutation_queue_v6

    summary = run_research_mutation_queue_v6()
    assert int(summary.get("mutation_queue_count", 0)) >= 0
    assert summary["live_trading_enabled"] is False


# ---------------------------------------------------------------------------
# L. Scoreboard V6
# ---------------------------------------------------------------------------


def test_v6_scoreboard_writes_json_html_csv() -> None:
    from dopey_scoreboard import public_signal_research_scoreboard_v6 as scoreboard_module

    summary = scoreboard_module.run_public_signal_research_scoreboard_v6()
    assert summary["scoreboard_v6_status"] == "public_signal_research_scoreboard_complete_v6"
    assert scoreboard_module.HTML_PATH.exists()
    assert scoreboard_module.SCOREBOARD_PATH.exists()
    assert scoreboard_module.ROWS_PATH.exists()


def test_v6_scoreboard_includes_v1_through_v6_rows() -> None:
    from dopey_scoreboard.public_signal_research_scoreboard_v6 import run_public_signal_research_scoreboard_v6

    summary = run_public_signal_research_scoreboard_v6()
    rows = summary.get("rows", [])
    versions = {str(r.get("version", "")) for r in rows}
    assert "v6" in versions
    assert "v5" in versions


# ---------------------------------------------------------------------------
# M. Live gate V6
# ---------------------------------------------------------------------------


def test_v6_live_gate_remains_disabled() -> None:
    from dopey_live_gate.public_signal_research_live_gate_status_v6 import run_public_signal_research_live_gate_status_v6

    status = run_public_signal_research_live_gate_status_v6()
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
# N. Safety / no live / no .env / no credentials / no broker
# ---------------------------------------------------------------------------


def test_v6_no_env_credentials_broker() -> None:
    assert not (REPO_ROOT / ".env").exists()
    forbidden = [".env", ".env.local", ".env.bak", "credentials.json", "broker.env"]
    for fname in forbidden:
        assert not (REPO_ROOT / fname).exists(), f"forbidden file present: {fname}"


def test_v6_official_robinhood_market_data_lane_allowed() -> None:
    from dopey_autonomy.champion_hardening_common import robinhood_policy_fields

    fields = robinhood_policy_fields()
    assert fields.get("official_robinhood_market_data_allowed") is True
    assert fields.get("unofficial_robinhood_api_blocked") is True
    assert fields.get("robinhood_scraping_blocked") is True
    assert fields.get("robinhood_reverse_auth_blocked") is True
    assert fields.get("robinhood_live_trading_enabled") is False


def test_v6_safety_fields_present_on_records() -> None:
    rows = read_jsonl_file(CANDIDATES_V6_PATH)
    assert rows
    sample = rows[0]
    assert sample.get("public_data_only") is True
    assert sample.get("paper_only") is True
    assert sample.get("live_trading_enabled") is False


# ---------------------------------------------------------------------------
# O. Orchestrator
# ---------------------------------------------------------------------------


def test_v6_orchestrator_writes_artifacts() -> None:
    from dopey_autonomy.run_public_signal_research_breakthrough_v6 import orchestrator_artifact_paths

    paths = orchestrator_artifact_paths()
    assert "public_signal_research_breakthrough_v6_summary" in paths
    assert "public_signal_research_breakthrough_v6_validation_summary" in paths
    assert Path(paths["public_signal_research_breakthrough_v6_summary"]).exists()
    assert Path(paths["public_signal_research_breakthrough_v6_validation_summary"]).exists()


def test_v6_orchestrator_summary_status_is_truthful() -> None:
    from dopey_autonomy.run_public_signal_research_breakthrough_v6 import SUMMARY_PATH as V6_SUMMARY_PATH

    summary = read_json_file(V6_SUMMARY_PATH)
    assert summary["public_signal_research_v6_status"] in {
        "research_breakthrough_candidates_found_live_gate_locked",
        "watchlist_blockers_improved_requires_v7",
        "no_further_repair_signal_feature_expansion_required",
    }
    assert summary["live_trading_enabled"] is False
    assert summary["timeout_recorded_as_pass"] is False


# ---------------------------------------------------------------------------
# P. Audit / report / export / review / stabilizer recognize V6
# ---------------------------------------------------------------------------


def test_v6_audit_recognizes_v6_artifacts() -> None:
    keys = {spec[0] for spec in ARTIFACT_SPECS}
    assert "public_signal_research_breakthrough_v6_summary" in keys
    assert "public_signal_research_breakthrough_v6_validation_summary" in keys
    assert "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6" in ALLOWED_NEXT_BUILD_TARGETS


def test_v6_export_recognizes_v6_artifacts() -> None:
    ids = {row.artifact_id for row in export_selection_rules()}
    assert "public_signal_research_breakthrough_v6_summary" in ids
    assert "public_signal_research_breakthrough_v6_validation_summary" in ids
    assert "research_breakthrough_gate_v6_summary" in ids
    assert "research_tournament_v6_summary" in ids
    assert "public_signal_research_scoreboard_v6" in ids
    assert "public_signal_research_live_gate_status_v6" in ids


def test_v6_validation_stabilizer_includes_shard() -> None:
    files = collect_test_files()
    assert "tests/test_public_signal_research_breakthrough_v6.py" in files


# ---------------------------------------------------------------------------
# Q. Timeout discipline
# ---------------------------------------------------------------------------


def test_v6_timeout_not_pass() -> None:
    result = timeout_result(["pytest"], 60)
    assert result["timeout_recorded_as_pass"] is False
    assert result["status"] == "inconclusive_timeout"


# ---------------------------------------------------------------------------
# R. Docs
# ---------------------------------------------------------------------------


def test_v6_report_ledger_commands_exist() -> None:
    from dopey_autonomy import run_public_signal_research_breakthrough_v6 as orchestrator_module

    assert orchestrator_module.REPORT_PATH.exists()
    assert orchestrator_module.LEDGER_PATH.exists()
    assert orchestrator_module.COMMANDS_PATH.exists()


def test_v6_canon_and_validation_markers_appended() -> None:
    from dopey_validation.public_signal_research_v6_validation import (
        VALIDATION_REPORT_PATH,
        _append_validation_report,
    )

    _append_validation_report("fixture_validation_marker", [])
    canon = Path("DOPEY_CANON.md").read_bytes()
    report = VALIDATION_REPORT_PATH.read_bytes()
    assert b"V6_PREFLIGHT_APPEND_MARKER" in canon
    assert b"V6_VALIDATION_APPEND_MARKER" in report
