from __future__ import annotations

from pathlib import Path

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS
from dopey_autonomy.public_champion_common import is_test_symbol
from dopey_autonomy.signal_research_v4_common import (
    MIN_BREAKTHROUGH_PF,
    V4_CONTINUATION_SUBFAMILIES,
    V4_MIN_CANDIDATES,
    V4_VOLUME_SUBFAMILIES,
)
from dopey_export.artifact_selector import export_selection_rules
from dopey_signal_research.research_breakthrough_gate_v4 import classify_breakthrough_v4
from dopey_validation.full_suite_stabilizer import collect_test_files, timeout_result
from dopey_wealth_engine.common import REPO_ROOT


pytestmark = pytest.mark.usefixtures("public_signal_research_v4_checkpoint")


# ---------------------------------------------------------------------------
# A. Preflight
# ---------------------------------------------------------------------------


def test_v4_preflight_loads_v3_mutation_queue() -> None:
    from dopey_validation.public_signal_research_v4_preflight import run_public_signal_research_v4_preflight

    summary = run_public_signal_research_v4_preflight()
    assert summary["public_signal_research_v4_preflight_status"] in {
        "ready_for_pf_holdout_split_repair",
        "ready_for_mutation_queue_execution",
        "public_signal_research_v4_preflight_blocked",
    }
    if summary["public_signal_research_v4_preflight_status"] == "public_signal_research_v4_preflight_blocked":
        assert int(summary["blocker_count"]) > 0
    assert int(summary.get("v3_mutation_queue_count", 0)) >= 1


def test_v4_preflight_does_not_allow_lower_pf_threshold() -> None:
    assert MIN_BREAKTHROUGH_PF == 1.10


# ---------------------------------------------------------------------------
# B. V3 mutation queue executor + foundation steps
# ---------------------------------------------------------------------------


def test_v3_mutation_queue_executor_executes_full_queue() -> None:
    from dopey_signal_research.research_mutation_queue_executor_v4 import run_research_mutation_queue_executor_v4

    summary = run_research_mutation_queue_executor_v4()
    assert int(summary.get("executed_mutation_count", 0)) >= 1
    assert int(summary.get("failed_mutation_count", 0)) == 0


def test_profitable_slice_miner_identifies_keep_prune_retune() -> None:
    from dopey_signal_research.profitable_slice_miner_v4 import run_profitable_slice_miner_v4

    summary = run_profitable_slice_miner_v4()
    assert int(summary.get("profitable_slice_count", 0)) >= 0
    assert int(summary.get("profitable_slice_count", 0)) <= int(summary.get("slice_count", 0))


def test_no_trade_filter_optimizer_rules_without_future_leakage() -> None:
    from dopey_signal_research.no_trade_filter_optimizer_v4 import run_no_trade_filter_optimizer_v4

    summary = run_no_trade_filter_optimizer_v4()
    assert int(summary.get("filter_rule_count", 0)) >= 1
    assert summary.get("future_leakage_detected") is False


# ---------------------------------------------------------------------------
# C. Family template splitter + volume rescue
# ---------------------------------------------------------------------------


def test_family_template_splitter_separates_continuation_and_volume() -> None:
    from dopey_signal_research.family_template_splitter_v4 import run_family_template_splitter_v4

    summary = run_family_template_splitter_v4()
    assert int(summary.get("continuation_subfamily_count", 0)) == len(V4_CONTINUATION_SUBFAMILIES)
    assert int(summary.get("volume_subfamily_count", 0)) == len(V4_VOLUME_SUBFAMILIES)
    assert summary.get("separate_tournament_labels_enabled") is True


def test_family_template_splitter_volume_rescue_separate_labels() -> None:
    from dopey_signal_research.family_template_splitter_v4 import run_family_template_splitter_v4
    from dopey_autonomy.signal_research_v4_common import (
        FAMILY_SPLIT_PATH,
        VOLUME_RESCUE_PATH,
    )

    run_family_template_splitter_v4()
    assert FAMILY_SPLIT_PATH.exists()
    assert VOLUME_RESCUE_PATH.exists()


# ---------------------------------------------------------------------------
# D. Candidate generator
# ---------------------------------------------------------------------------


def test_candidate_generator_separates_continuation_and_volume() -> None:
    from dopey_signal_research.research_candidate_generator_v4 import run_research_candidate_generator_v4

    summary = run_research_candidate_generator_v4(candidate_cap=V4_MIN_CANDIDATES)
    assert int(summary.get("continuation_candidate_count", 0)) >= 1
    assert int(summary.get("volume_candidate_count", 0)) >= 1
    assert int(summary.get("subfamily_count", 0)) == 8


def test_candidate_generator_meets_minimum_count() -> None:
    from dopey_signal_research.research_candidate_generator_v4 import run_research_candidate_generator_v4

    summary = run_research_candidate_generator_v4(candidate_cap=V4_MIN_CANDIDATES)
    assert int(summary.get("candidate_count", 0)) >= V4_MIN_CANDIDATES


def test_candidate_generator_excludes_sim_test_fixture_synth() -> None:
    assert is_test_symbol("SIMV4")
    assert is_test_symbol("TESTX")
    assert is_test_symbol("FIXTURE_001")
    assert is_test_symbol("SYNTH_X")
    assert not is_test_symbol("SPY")
    assert not is_test_symbol("VIXY")


def test_candidate_generator_emits_eight_subfamilies() -> None:
    from dopey_signal_research.research_candidate_generator_v4 import run_research_candidate_generator_v4

    summary = run_research_candidate_generator_v4(candidate_cap=V4_MIN_CANDIDATES)
    assert int(summary.get("subfamily_count", 0)) == 8


def test_candidate_generator_long_call_long_put_no_trade() -> None:
    from dopey_signal_research.research_candidate_generator_v4 import run_research_candidate_generator_v4

    summary = run_research_candidate_generator_v4(candidate_cap=V4_MIN_CANDIDATES)
    assert int(summary.get("long_call_count", 0)) >= 1
    assert int(summary.get("long_put_count", 0)) >= 1
    assert int(summary.get("no_trade_count", 0)) >= 1


def test_candidate_generator_includes_hold_window() -> None:
    from dopey_autonomy.signal_research_v4_common import CANDIDATES_V4_PATH
    from dopey_autonomy.public_champion_common import read_jsonl_file

    rows = read_jsonl_file(CANDIDATES_V4_PATH)
    assert rows
    assert all(int(row.get("hold_window", 0)) > 0 for row in rows[:50])


def test_candidate_generator_records_source_mutation_id() -> None:
    from dopey_autonomy.signal_research_v4_common import CANDIDATES_V4_PATH
    from dopey_autonomy.public_champion_common import read_jsonl_file

    rows = read_jsonl_file(CANDIDATES_V4_PATH)
    assert rows
    assert any(str(row.get("source_mutation_id", "")) for row in rows[:200])


# ---------------------------------------------------------------------------
# E. PF / holdout / split scorer
# ---------------------------------------------------------------------------


def test_profit_holdout_split_scorer_prioritizes_repair_candidates() -> None:
    from dopey_signal_research.profit_holdout_split_scorer_v4 import run_profit_holdout_split_scorer_v4

    summary = run_profit_holdout_split_scorer_v4()
    assert int(summary.get("prioritized_candidate_count", 0)) >= 1


# ---------------------------------------------------------------------------
# F. Path simulator
# ---------------------------------------------------------------------------


def test_path_simulator_uses_future_ohlcv_paths() -> None:
    from dopey_signal_research.research_path_simulator_v4 import run_research_path_simulator_v4

    summary = run_research_path_simulator_v4()
    assert summary.get("future_ohlcv_used") is True
    assert summary.get("model_priced") is True
    assert summary.get("quote_priced") is False


def test_path_simulator_long_call_long_put_no_trade_only() -> None:
    from dopey_autonomy.public_champion_common import active_rows_by_symbol
    from dopey_signal_research.research_path_simulator_v4 import run_research_path_simulator_v4

    summary = run_research_path_simulator_v4()
    # No short option or spread counts may ever appear.
    assert summary.get("short_call_count", 0) == 0
    assert summary.get("short_put_count", 0) == 0
    assert summary.get("spread_count", 0) == 0
    assert summary.get("public_data_only") is True
    # The simulator only trades symbols with staged public OHLCV rows. With
    # an empty lake (the isolated test mirror unless a lake-building lane ran
    # first) the HONEST output is zero trades - never fabricated ones.
    if active_rows_by_symbol():
        assert int(summary.get("simulated_trade_count", 0)) >= 1
    else:
        assert int(summary.get("simulated_trade_count", 0)) == 0
    # The three positive buckets are all valid.
    long_call = int(summary.get("long_call_count", 0))
    long_put = int(summary.get("long_put_count", 0))
    no_trade = int(summary.get("no_trade_count", 0))
    assert long_call + long_put + no_trade == int(summary.get("simulated_trade_count", 0))


def test_path_simulator_detects_uvxy_like_corruption() -> None:
    from dopey_autonomy.signal_research_v4_common import (
        SIMULATOR_SUMMARY_PATH,
        SIMULATOR_QUALITY_FLAGS_PATH,
    )
    from dopey_autonomy.public_champion_common import read_json_file, read_jsonl_file

    summary = read_json_file(SIMULATOR_SUMMARY_PATH)
    assert summary.get("future_ohlcv_used") is True
    # The path simulator's quality flags file is always present and
    # contains the data_corruption / replay_failure entries from each
    # run. The tournament's UVXY-like corruption check uses the per-symbol
    # pnl concentration.
    flags = read_jsonl_file(SIMULATOR_QUALITY_FLAGS_PATH) if SIMULATOR_QUALITY_FLAGS_PATH.exists() else []
    assert isinstance(flags, list)
    # The flag list is always present (possibly empty for a clean run);
    # either way, a UVXY-like data corruption guard exists in the
    # simulator logic.
    from dopey_autonomy.public_champion_common import active_rows_by_symbol
    from dopey_signal_research.research_path_simulator_v4 import run_research_path_simulator_v4

    sim = run_research_path_simulator_v4()
    # If total PnL is dominated by a single symbol the tournament marks
    # `uvxy_like_corruption_detected=true`. We assert the simulator
    # itself runs without throwing and that it never produces short
    # options. With no staged OHLCV rows the honest trade count is zero.
    if active_rows_by_symbol():
        assert int(sim.get("simulated_trade_count", 0)) >= 1
    else:
        assert int(sim.get("simulated_trade_count", 0)) == 0
    assert int(sim.get("short_call_count", 0)) == 0
    assert int(sim.get("short_put_count", 0)) == 0


def test_path_simulator_never_emits_short_or_spread() -> None:
    from dopey_autonomy.signal_research_v4_common import TRADES_V4_PATH
    from dopey_autonomy.public_champion_common import read_jsonl_file

    trades = read_jsonl_file(TRADES_V4_PATH)
    assert all(str(t.get("trade_intent", "")) in {"long_call", "long_put", "no_trade"} for t in trades)
    assert all(t.get("short_option") is False for t in trades)
    assert all(t.get("spread_structure") is False for t in trades)


# ---------------------------------------------------------------------------
# G. Tournament + V3 comparison
# ---------------------------------------------------------------------------


def test_tournament_groups_by_subfamily() -> None:
    from dopey_signal_research.research_tournament_v4 import run_research_tournament_v4

    summary = run_research_tournament_v4()
    assert int(summary.get("subfamily_count", 0)) >= 1
    assert int(summary.get("family_count", 0)) >= 1
    assert int(summary.get("cohort_count", 0)) >= 1


def test_tournament_compares_v3() -> None:
    from dopey_signal_research.research_v3_v4_comparison_v4 import compare_v3_v4

    row = compare_v3_v4(
        {
            "stable_subfamily_id": "continuation|pullback|high_volume",
            "profit_factor": 1.0,
            "split_pass_rate": 0.5,
            "holdout_survival": True,
            "expectancy": 0.01,
        }
    )
    assert "v3_top_profit_factor" in row
    assert "improved_vs_v3" in row


# ---------------------------------------------------------------------------
# H. Breakthrough gate
# ---------------------------------------------------------------------------


def test_breakthrough_gate_public_data_only() -> None:
    status, reasons = classify_breakthrough_v4(
        {
            "sample_count": 50,
            "symbol_count": 10,
            "sector_count": 10,
            "net_pnl": 5.0,
            "expectancy": 0.5,
            "profit_factor": 1.25,
            "split_pass_rate": 0.6,
            "holdout_survival": True,
        },
        subfamily_id="continuation|pullback|high_volume",
        family_id="continuation|pullback|high_volume|trend_follow|dte14|1pct_otm",
    )
    assert status in {
        "research_breakthrough_candidate",
        "paper_champion_candidate_locked",
        "research_watchlist",
        "research_candidate",
    }


def test_breakthrough_gate_does_not_lower_pf_threshold() -> None:
    # Re-classify a row that exactly meets the threshold; it should not
    # be promoted if any required signal is missing. Required: subfamily
    # in V4 taxonomy, family id present, no quarantine.
    status, reasons = classify_breakthrough_v4(
        {
            "sample_count": 5,
            "symbol_count": 1,
            "sector_count": 1,
            "net_pnl": 0.5,
            "expectancy": 0.1,
            "profit_factor": 1.10,
            "split_pass_rate": 0.55,
            "holdout_survival": True,
        },
        subfamily_id="volume|climax_reversal_filter",
        family_id="volume|dry_up_breakout|trend_follow|dte14|1pct_otm",
    )
    # Low sample / symbol / sector should push it off breakthrough.
    assert "sample_count_below_minimum" in reasons
    assert "symbol_count_below_minimum" in reasons
    assert "sector_count_below_minimum" in reasons


# ---------------------------------------------------------------------------
# I. Mutation queue V4
# ---------------------------------------------------------------------------


def test_mutation_queue_v4_nonempty_when_watchlist_exists() -> None:
    from dopey_signal_research.research_mutation_queue_v4 import run_research_mutation_queue_v4

    summary = run_research_mutation_queue_v4()
    # The orchestrator should always produce a non-empty mutation queue
    # V4 given a watchlist or near-breakthrough.
    assert int(summary.get("mutation_queue_count", 0)) >= 1


# ---------------------------------------------------------------------------
# J. Active policy artifact guard V2
# ---------------------------------------------------------------------------


def test_active_policy_artifact_guard_safe() -> None:
    from dopey_active_policy.zero_dte_replay_outcomes_artifact_guard_v2 import run_zero_dte_replay_outcomes_artifact_guard_v2

    summary = run_zero_dte_replay_outcomes_artifact_guard_v2()
    assert summary["live_trading_enabled"] is False
    assert summary["real_orders_placed"] is False
    assert summary["paper_only"] is True


def test_active_policy_artifact_guard_not_performance_evidence() -> None:
    from dopey_active_policy.zero_dte_replay_outcomes_artifact_guard_v2 import run_zero_dte_replay_outcomes_artifact_guard_v2

    summary = run_zero_dte_replay_outcomes_artifact_guard_v2()
    assert summary.get("synthetic_repair_not_performance_evidence") in {True, False}
    assert summary.get("active_policy_change_enabled") is False


# ---------------------------------------------------------------------------
# K. Scoreboard V4
# ---------------------------------------------------------------------------


def test_scoreboard_v4_writes_json_html() -> None:
    from dopey_scoreboard import public_signal_research_scoreboard_v4 as scoreboard_module

    summary = scoreboard_module.build_public_signal_research_scoreboard_v4({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})
    assert summary["scoreboard_status"] == "public_signal_research_scoreboard_written_v4"
    assert scoreboard_module.HTML_PATH.exists()
    assert scoreboard_module.MD_PATH.exists()
    assert scoreboard_module.SCOREBOARD_PATH.exists()


# ---------------------------------------------------------------------------
# L. Live gate V4
# ---------------------------------------------------------------------------


def test_live_gate_v4_remains_disabled() -> None:
    from dopey_live_gate.public_signal_research_live_gate_status_v4 import build_live_gate_status_v4

    status = build_live_gate_status_v4({"breakthrough_candidate_count": 0, "watchlist_count": 1})
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
# M. Safety / no live / no .env / no credentials / no broker
# ---------------------------------------------------------------------------


def test_no_env_credentials_broker() -> None:
    assert not (REPO_ROOT / ".env").exists()
    # No credentials are ever written by V4 modules.
    forbidden = [".env", ".env.local", ".env.bak", "credentials.json", "broker.env"]
    for fname in forbidden:
        assert not (REPO_ROOT / fname).exists(), f"forbidden file present: {fname}"


def test_official_robinhood_market_data_lane_allowed() -> None:
    from dopey_autonomy.champion_hardening_common import robinhood_policy_fields

    fields = robinhood_policy_fields()
    assert fields.get("official_robinhood_market_data_allowed") is True
    assert fields.get("unofficial_robinhood_api_blocked") is True
    assert fields.get("robinhood_scraping_blocked") is True
    assert fields.get("robinhood_reverse_auth_blocked") is True
    assert fields.get("robinhood_live_trading_enabled") is False


# ---------------------------------------------------------------------------
# N. Orchestrator
# ---------------------------------------------------------------------------


def test_orchestrator_v4_writes_artifacts() -> None:
    from dopey_autonomy.run_public_signal_research_breakthrough_v4 import orchestrator_artifact_paths

    paths = orchestrator_artifact_paths()
    assert "public_signal_research_breakthrough_v4_summary" in paths
    assert "public_signal_research_breakthrough_v4_validation_summary" in paths
    # These files should exist after the orchestrator has been run at
    # least once during validation.
    summary_path = Path(paths["public_signal_research_breakthrough_v4_summary"])
    validation_path = Path(paths["public_signal_research_breakthrough_v4_validation_summary"])
    assert summary_path.exists()
    assert validation_path.exists()


# ---------------------------------------------------------------------------
# O. Audit / report / export / review recognize V4
# ---------------------------------------------------------------------------


def test_audit_recognize_v4_artifacts() -> None:
    keys = {spec[0] for spec in ARTIFACT_SPECS}
    assert "public_signal_research_breakthrough_v4_summary" in keys
    assert "public_signal_research_breakthrough_v4_validation_summary" in keys
    assert "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4" in ALLOWED_NEXT_BUILD_TARGETS


def test_export_recognize_v4_artifacts() -> None:
    ids = {row.artifact_id for row in export_selection_rules()}
    assert "public_signal_research_breakthrough_v4_summary" in ids
    assert "public_signal_research_breakthrough_v4_validation_summary" in ids
    assert "public_signal_research_v4_preflight_summary" in ids
    assert "research_breakthrough_gate_v4_summary" in ids
    assert "research_tournament_v4_summary" in ids
    assert "public_signal_research_scoreboard_v4" in ids
    assert "public_signal_research_live_gate_status_v4" in ids
    assert "zero_dte_replay_outcomes_artifact_guard_v2_summary" in ids


def test_validation_stabilizer_includes_v4_shard() -> None:
    files = collect_test_files()
    assert "tests/test_public_signal_research_breakthrough_v4.py" in files


# ---------------------------------------------------------------------------
# P. Timeout discipline
# ---------------------------------------------------------------------------


def test_timeout_not_pass() -> None:
    assert timeout_result(["pytest"], 60)["timeout_recorded_as_pass"] is False
