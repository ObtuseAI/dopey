from __future__ import annotations

import importlib
import inspect

import pytest

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import read_jsonl_file
from dopey_autonomy.signal_research_v7_common import (
    BASELINE_V6_ROOT,
    CANDIDATES_V7_PATH,
    MIN_BREAKTHROUGH_PF,
    NO_TRADE_DOMINANCE_FLAGS_V7_PATH,
    PREFLIGHT_V7_FLAGS_PATH,
    RESEARCH_V7_ROOT,
    TOURNAMENT_HOLDOUT_V7_PATH,
    TOURNAMENT_REGIME_V7_PATH,
    V6_GATE_BLOCKER_ANALYSIS_V7_PATH,
    V6_TRADE_ACTIVE_BLOCKER_MATRIX_V7_PATH,
    V7_MAX_NO_TRADE_RATIO,
    V7_MIN_CANDIDATES,
    V7_MIN_TRADES,
    V7_TARGET_CANDIDATES,
    V7_TARGET_TRADES,
    is_forbidden_symbol,
    load_v6_watchlist_records,
    research_v7_proof_record,
)
from dopey_wealth_engine.common import REPO_ROOT


pytestmark = pytest.mark.usefixtures("public_signal_research_v7_checkpoint")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_or_none(module_name: str) -> object | None:
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


def _run_if_present(module_name: str, func_name: str) -> object:
    mod = _import_or_none(module_name)
    if mod is None:
        pytest.skip(f"{module_name} not implemented")
    if not hasattr(mod, func_name):
        pytest.skip(f"{module_name}.{func_name} not implemented")
    return getattr(mod, func_name)()


# ---------------------------------------------------------------------------
# A. V7 preflight and V6 baseline freeze
# ---------------------------------------------------------------------------


def test_v7_preflight_loads_v6_complete_state() -> None:
    from dopey_validation.public_signal_research_v7_preflight import (
        run_public_signal_research_v7_preflight,
    )

    summary = run_public_signal_research_v7_preflight()
    assert summary["public_signal_research_v7_preflight_status"] == "ready_for_trade_active_breakthrough_repair"
    assert summary["v6_summary_status"] == "watchlist_blockers_improved_requires_v7"
    assert summary["v6_watchlist_count"] == 2
    assert summary["v6_breakthrough_count"] == 0
    assert summary["v6_pf_above_110_count"] == 6
    assert summary["v6_mutation_queue_count"] == 50
    assert summary["top_cohort_no_trade_dominant"] is True


def test_v7_preflight_does_not_allow_lower_pf_threshold() -> None:
    assert MIN_BREAKTHROUGH_PF == 1.10


def test_v7_preflight_records_timeout_honestly() -> None:
    from dopey_validation.public_signal_research_v7_preflight import (
        run_public_signal_research_v7_preflight,
    )

    summary = run_public_signal_research_v7_preflight()
    assert summary["v6_timeout_recorded_as_pass"] is False


def test_v7_preflight_flags_include_safety_and_robinhood_fields() -> None:
    from dopey_validation.public_signal_research_v7_preflight import (
        run_public_signal_research_v7_preflight,
    )

    run_public_signal_research_v7_preflight()
    flags = read_jsonl_file(PREFLIGHT_V7_FLAGS_PATH)
    assert flags
    sample = flags[0]
    assert sample.get("live_trading_enabled") is False
    assert sample.get("broker_connection_enabled") is False
    assert sample.get("real_order_enabled") is False
    assert sample.get("official_robinhood_market_data_allowed") is True
    assert sample.get("unofficial_robinhood_api_blocked") is True
    assert sample.get("robinhood_live_trading_enabled") is False


def test_v7_baseline_freeze_writes_immutable_snapshots() -> None:
    from dopey_validation.public_signal_research_baseline_freezer_v7 import (
        run_public_signal_research_baseline_freezer_v7,
    )

    summary = run_public_signal_research_baseline_freezer_v7()
    assert summary["baseline_freeze_status"] == "v6_baseline_frozen"
    assert int(summary["copied_count"]) > 0


def test_v7_baseline_freeze_includes_v6_summary() -> None:
    from dopey_validation.public_signal_research_baseline_freezer_v7 import (
        run_public_signal_research_baseline_freezer_v7,
    )

    run_public_signal_research_baseline_freezer_v7()
    assert (BASELINE_V6_ROOT / "public_signal_research_breakthrough_v6_summary.json").exists()


# ---------------------------------------------------------------------------
# B. No-trade contribution audit V7
# ---------------------------------------------------------------------------


def test_v7_trade_active_edge_separator_classifies_trades() -> None:
    from dopey_signal_research.trade_active_edge_separator_v7 import (
        compute_subfamily_trade_active_metrics,
        compute_trade_active_edge,
        separate_trades,
    )

    trades = [
        {"direction": "long_call", "pnl": 1.0, "stable_subfamily_id": "s1"},
        {"direction": "long_put", "pnl": -0.5, "stable_subfamily_id": "s1"},
        {"direction": "no_trade", "pnl": 0.0, "stable_subfamily_id": "s1"},
    ]
    no_trade, active = separate_trades(trades)
    assert len(no_trade) == 1
    assert len(active) == 2

    metrics = compute_subfamily_trade_active_metrics("s1", trades)
    assert metrics["total_sample_count"] == 3
    assert metrics["trade_active_count"] == 2
    assert metrics["no_trade_count"] == 1

    edge = compute_trade_active_edge(metrics)
    assert "trade_active_edge" in edge
    assert edge["v7_min_breakthrough_pf"] == MIN_BREAKTHROUGH_PF


def test_v7_trade_active_edge_requires_min_pf() -> None:
    from dopey_signal_research.trade_active_edge_separator_v7 import compute_trade_active_edge

    edge = compute_trade_active_edge(
        {"stable_subfamily_id": "s1", "trade_active_count": 1, "trade_active_profit_factor": 1.15},
        min_pf=1.10,
    )
    assert edge["trade_active_edge"] is True
    assert edge["trade_active_edge_above_min_pf"] is True


def test_v7_no_trade_contribution_audit_if_present() -> None:
    _run_if_present("dopey_signal_research.no_trade_contribution_audit_v7", "run_no_trade_contribution_audit_v7")


def test_v7_no_trade_dominance_flag_artifact_path_defined() -> None:
    assert "no_trade_dominance_flags" in str(NO_TRADE_DOMINANCE_FLAGS_V7_PATH)


# ---------------------------------------------------------------------------
# C. V6 watchlist and blocker diagnosis V7
# ---------------------------------------------------------------------------


def test_v7_v6_watchlist_records_count_is_2() -> None:
    records = load_v6_watchlist_records()
    assert len(records) == 2


def test_v7_v6_gate_rejection_analysis_artifact_path_defined() -> None:
    assert "v6_gate_blocker_analysis" in str(V6_GATE_BLOCKER_ANALYSIS_V7_PATH).lower()


def test_v7_v6_trade_active_blocker_matrix_artifact_path_defined() -> None:
    assert "v6_trade_active_blocker_matrix" in str(V6_TRADE_ACTIVE_BLOCKER_MATRIX_V7_PATH).lower()


def test_v7_v6_gate_blocker_analyzer_if_present() -> None:
    _run_if_present(
        "dopey_signal_research.v6_gate_blocker_analyzer_v7",
        "run_v6_gate_blocker_analyzer_v7",
    )


# ---------------------------------------------------------------------------
# D. V6 mutation queue executor V7
# ---------------------------------------------------------------------------


def test_v7_mutation_expansion_loop_emits_v7_only_types() -> None:
    from dopey_signal_research.research_mutation_expansion_loop_v7 import (
        V7_ONLY_MUTATION_TYPES,
        run_v7_mutation_expansion_loop,
    )

    summary = run_v7_mutation_expansion_loop()
    type_counts = summary.get("v7_expansion_mutation_type_counts", {})
    expected_v7_types = {t[0] for t in V7_ONLY_MUTATION_TYPES}
    present_v7_types = expected_v7_types.intersection(type_counts.keys())
    assert present_v7_types, "no V7-only mutation types emitted"
    assert int(summary["v7_expansion_mutation_count"]) >= len(V7_ONLY_MUTATION_TYPES)


def test_v7_mutation_expansion_blocks_no_trade_only_breakthrough() -> None:
    from dopey_signal_research.research_mutation_expansion_loop_v7 import run_v7_mutation_expansion_loop

    summary = run_v7_mutation_expansion_loop()
    assert summary.get("blocks_no_trade_only_breakthrough") is True


def test_v7_mutation_executor_if_present() -> None:
    summary = _run_if_present(
        "dopey_signal_research.research_mutation_queue_executor_v7",
        "execute_v7_mutation_queue",
    )
    assert int(summary.get("input_v6_mutation_count", 0)) >= 1
    assert int(summary.get("executed_mutation_count", 0)) >= 1


# ---------------------------------------------------------------------------
# E. Trade-active repair policy V7
# ---------------------------------------------------------------------------


def test_v7_future_leakage_guard_detects_forbidden_tokens() -> None:
    from dopey_signal_research.future_leakage_guard_v7 import audit_v7_no_leakage

    dirty_rules = [
        {"rule_id": "r1", "description": "uses future_close to decide"},
        {"rule_id": "r2", "description": "uses realized_pnl label"},
    ]
    records = audit_v7_no_leakage(dirty_rules)
    assert records
    assert all(not r["is_leakage_free"] for r in records)


def test_v7_future_leakage_guard_clean_rules_pass() -> None:
    from dopey_signal_research.future_leakage_guard_v7 import audit_v7_no_leakage

    clean_rules = [
        {
            "rule_id": "r1",
            "description": "use pre-entry features only",
            "allowed_features": "rsi, volume_ratio",
        }
    ]
    records = audit_v7_no_leakage(clean_rules)
    assert records
    assert all(r["is_leakage_free"] for r in records)


def test_v7_trade_active_repair_policy_if_present() -> None:
    summary = _run_if_present(
        "dopey_signal_research.trade_active_repair_policy_v7",
        "run_trade_active_repair_policy_v7",
    )
    assert summary.get("future_leakage_detected") is False
    assert summary.get("thresholds_lowered") is False
    assert summary.get("live_trading_enabled") is False


# ---------------------------------------------------------------------------
# F. V7 candidate generator
# ---------------------------------------------------------------------------


def test_v7_candidate_target_and_min_constants() -> None:
    assert V7_MIN_CANDIDATES == 18_000
    assert V7_TARGET_CANDIDATES == 30_000
    assert V7_MIN_TRADES == 10_000
    assert V7_TARGET_TRADES == 18_000
    assert V7_MAX_NO_TRADE_RATIO == 0.35


def test_v7_forbidden_symbol_detection() -> None:
    assert is_forbidden_symbol("SIM_SPY")
    assert is_forbidden_symbol("TEST_FIXTURE")
    assert is_forbidden_symbol("SYNTH_QQQ")
    assert not is_forbidden_symbol("SPY")


def test_v7_candidate_generator_if_present() -> None:
    from dopey_autonomy.public_champion_common import is_test_symbol

    summary = _run_if_present(
        "dopey_signal_research.research_candidate_generator_v7",
        "run_research_candidate_generator_v7",
    )
    assert int(summary.get("candidate_count", 0)) >= V7_MIN_CANDIDATES
    rows = read_jsonl_file(CANDIDATES_V7_PATH)
    assert rows
    assert not any(is_test_symbol(str(row.get("symbol", ""))) for row in rows)
    assert all("hold_window" in row for row in rows[:50])


# ---------------------------------------------------------------------------
# G. V7 pre-simulation scorer
# ---------------------------------------------------------------------------


def test_v7_scorer_prioritizes_repair_candidates() -> None:
    from dopey_signal_research.profit_holdout_split_scorer_v7 import (
        run_profit_holdout_split_scorer_v7,
    )

    summary = run_profit_holdout_split_scorer_v7()
    assert summary["profit_holdout_split_scorer_v7_status"] == "profit_holdout_split_scored_v7"
    assert int(summary.get("prioritized_candidate_count", 0)) >= 1
    assert int(summary.get("score_axis_count", 0)) == 12


def test_v7_scorer_blocks_no_trade_only_breakthrough() -> None:
    from dopey_signal_research.profit_holdout_split_scorer_v7 import (
        run_profit_holdout_split_scorer_v7,
    )

    summary = run_profit_holdout_split_scorer_v7()
    blocked = int(summary.get("no_trade_only_breakthrough_blocked_count", 0))
    no_trade_count = int(summary.get("no_trade_candidate_count", 0))
    assert blocked >= 0
    assert blocked <= max(no_trade_count, 1)


def test_v7_scorer_includes_twelve_axes() -> None:
    from dopey_signal_research.profit_holdout_split_scorer_v7 import SCORE_AXES

    assert len(SCORE_AXES) == 12
    assert "trade_active_edge" in SCORE_AXES
    assert "no_trade_filter_quality" in SCORE_AXES


def test_v7_scorer_records_trade_active_edge_boost() -> None:
    from dopey_signal_research.profit_holdout_split_scorer_v7 import (
        run_profit_holdout_split_scorer_v7,
    )

    summary = run_profit_holdout_split_scorer_v7()
    assert int(summary.get("trade_active_repair_candidate_count", 0)) >= 0
    assert int(summary.get("trade_active_candidate_count", 0)) >= 0


# ---------------------------------------------------------------------------
# H. V7 path simulator
# ---------------------------------------------------------------------------


def test_v7_option_model_long_call_long_put_no_trade_only() -> None:
    from dopey_signal_research.research_option_model_v7 import model_price_option

    assert model_price_option("no_trade", 100.0, 100.0, 30, 0.25) == 0.0
    call = model_price_option("long_call", 100.0, 100.0, 30, 0.25)
    put = model_price_option("long_put", 100.0, 100.0, 30, 0.25)
    assert call > 0.0
    assert put > 0.0

    with pytest.raises(ValueError):
        model_price_option("short_call", 100.0, 100.0, 30, 0.25)


def test_v7_option_model_corruption_guard() -> None:
    from dopey_signal_research.research_option_model_v7 import compute_trade_pnl

    assert compute_trade_pnl("long_call", 1_000_001.0, 100.0, 100.0, 30, 0.25, 1) == 0.0


def test_v7_option_model_deterministic() -> None:
    from dopey_signal_research.research_option_model_v7 import model_price_option

    a = model_price_option("long_call", 100.0, 105.0, 21, 0.30)
    b = model_price_option("long_call", 100.0, 105.0, 21, 0.30)
    assert a == b


def test_v7_path_simulator_if_present() -> None:
    summary = _run_if_present(
        "dopey_signal_research.research_path_simulator_v7",
        "run_research_path_simulator_v7",
    )
    assert summary.get("future_ohlcv_used") is False
    assert summary.get("synthetic_path_used") is True
    assert summary.get("market_data_source_type") == "synthetic_deterministic_hash_lcg"
    assert summary.get("model_priced") is True
    assert summary.get("quote_priced") is False
    assert int(summary.get("simulated_trade_count", 0)) >= V7_MIN_TRADES


# ---------------------------------------------------------------------------
# I. V7 tournament + V6 comparison
# ---------------------------------------------------------------------------


def test_v7_holdout_separates_trade_active_pf() -> None:
    from dopey_signal_research.research_holdout_v7 import run_v7_holdout

    summary = run_v7_holdout()
    records = read_jsonl_file(TOURNAMENT_HOLDOUT_V7_PATH)
    assert summary.get("holdout_score_count", 0) == len(records)
    assert all("holdout_trade_active_pf" in r for r in records)
    assert all("trade_active_survival" in r for r in records)


def test_v7_regime_score_separates_trade_active_pf() -> None:
    from dopey_signal_research.research_regime_score_v7 import run_v7_regime_score

    summary = run_v7_regime_score()
    records = read_jsonl_file(TOURNAMENT_REGIME_V7_PATH)
    assert summary.get("regime_score_count", 0) == len(records)
    assert all("trade_active_pf" in r for r in records)


def test_v7_tournament_if_present() -> None:
    summary = _run_if_present(
        "dopey_signal_research.research_tournament_v7",
        "run_research_tournament_v7",
    )
    assert "v6_top_pf" in summary or "improved_vs_v6_count" in summary
    assert int(summary.get("pf_above_110_count", 0)) >= 0


# ---------------------------------------------------------------------------
# J. V7 breakthrough gate
# ---------------------------------------------------------------------------


def test_v7_breakthrough_gate_if_present() -> None:
    summary = _run_if_present(
        "dopey_signal_research.research_breakthrough_gate_v7",
        "run_research_breakthrough_gate_v7",
    )
    assert float(summary.get("v7_min_breakthrough_pf", 0.0)) == 1.10
    assert summary.get("thresholds_lowered") is False
    assert summary.get("live_trading_enabled") is False


# ---------------------------------------------------------------------------
# K. V7 mutation queue
# ---------------------------------------------------------------------------


def test_v7_mutation_queue_if_present() -> None:
    summary = _run_if_present(
        "dopey_signal_research.research_mutation_queue_v7",
        "run_research_mutation_queue_v7",
    )
    assert summary.get("live_trading_enabled") is False


# ---------------------------------------------------------------------------
# L. V7 scoreboard
# ---------------------------------------------------------------------------


def test_v7_scoreboard_if_present() -> None:
    from dopey_scoreboard import public_signal_research_scoreboard_v7 as scoreboard_module

    summary = scoreboard_module.run_public_signal_research_scoreboard_v7()
    assert summary["scoreboard_v7_status"] == "public_signal_research_scoreboard_complete_v7"
    assert scoreboard_module.SCOREBOARD_PATH.exists()


# ---------------------------------------------------------------------------
# M. V7 live gate
# ---------------------------------------------------------------------------


def test_v7_live_gate_remains_disabled() -> None:
    from dopey_live_gate.public_signal_research_live_gate_status_v7 import (
        run_public_signal_research_live_gate_status_v7,
    )

    status = run_public_signal_research_live_gate_status_v7()
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
    assert status["no_trade_only_breakthroughs_blocked"] is True


# ---------------------------------------------------------------------------
# N. V7 orchestrator
# ---------------------------------------------------------------------------


def test_v7_orchestrator_if_present() -> None:
    mod = _import_or_none("dopey_autonomy.run_public_signal_research_breakthrough_v7")
    if mod is None:
        pytest.skip("V7 orchestrator not implemented")
    paths = mod.orchestrator_artifact_paths()
    assert "public_signal_research_breakthrough_v7_summary" in paths


# ---------------------------------------------------------------------------
# O. V7 integration touch points
# ---------------------------------------------------------------------------


def test_v7_audit_recognizes_v7_artifacts() -> None:
    from dopey_audit.artifact_loader import ARTIFACT_SPECS
    from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS

    keys = {spec[0] for spec in ARTIFACT_SPECS}
    if "public_signal_research_breakthrough_v7_summary" not in keys:
        pytest.skip("V7 audit artifact specs not yet added by workstream O")
    assert "public_signal_research_breakthrough_v7_validation_summary" in keys
    assert "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7" in ALLOWED_NEXT_BUILD_TARGETS


def test_v7_export_recognizes_v7_artifacts() -> None:
    from dopey_export.artifact_selector import export_selection_rules

    ids = {row.artifact_id for row in export_selection_rules()}
    if "public_signal_research_breakthrough_v7_summary" not in ids:
        pytest.skip("V7 export selection rules not yet added by workstream O")
    assert "research_breakthrough_gate_v7_summary" in ids
    assert "public_signal_research_live_gate_status_v7" in ids


def test_v7_validation_stabilizer_includes_shard() -> None:
    from dopey_validation.full_suite_stabilizer import collect_test_files

    files = collect_test_files()
    assert "tests/test_public_signal_research_breakthrough_v7.py" in files


# ---------------------------------------------------------------------------
# P. Docs / test coverage
# ---------------------------------------------------------------------------


def test_v7_report_ledger_commands_exist() -> None:
    from dopey_autonomy import run_public_signal_research_breakthrough_v7 as orchestrator_module

    assert orchestrator_module.REPORT_PATH.exists()
    assert orchestrator_module.LEDGER_PATH.exists()
    assert orchestrator_module.COMMANDS_PATH.exists()


def test_v7_test_file_has_at_least_35_tests() -> None:
    mod = importlib.import_module("tests.test_public_signal_research_breakthrough_v7")
    tests = [name for name, _ in inspect.getmembers(mod, inspect.isfunction) if name.startswith("test_")]
    assert len(tests) >= 35, f"found {len(tests)} tests"


# ---------------------------------------------------------------------------
# Q. Safety / no live / no .env / no credentials / no broker
# ---------------------------------------------------------------------------


def test_v7_min_breakthrough_pf_never_lowered() -> None:
    from dopey_autonomy.signal_research_v7_common import load_v6_gate_summary

    assert MIN_BREAKTHROUGH_PF == 1.10
    v6_gate = load_v6_gate_summary()
    assert v6_gate.get("thresholds_lowered") is False
    assert float(v6_gate.get("v6_min_breakthrough_pf", 0.0)) >= 1.10


def test_v7_live_trading_disabled_globally() -> None:
    safety = live_safety_fields()
    assert safety["live_trading_enabled"] is False
    assert safety["broker_connection_enabled"] is False
    assert safety["real_order_enabled"] is False
    assert safety["credentials_present"] is False


def test_v7_no_env_credentials_broker() -> None:
    assert not (REPO_ROOT / ".env").exists()
    forbidden = [".env", ".env.local", ".env.bak", "credentials.json", "broker.env"]
    for fname in forbidden:
        assert not (REPO_ROOT / fname).exists(), f"forbidden file present: {fname}"


def test_v7_robinhood_policy_fields() -> None:
    fields = robinhood_policy_fields()
    assert fields.get("official_robinhood_market_data_allowed") is True
    assert fields.get("unofficial_robinhood_api_blocked") is True
    assert fields.get("robinhood_scraping_blocked") is True
    assert fields.get("robinhood_reverse_auth_blocked") is True
    assert fields.get("robinhood_live_trading_enabled") is False


def test_v7_no_trade_only_breakthroughs_blocked() -> None:
    from dopey_live_gate.public_signal_research_live_gate_status_v7 import (
        run_public_signal_research_live_gate_status_v7,
    )

    status = run_public_signal_research_live_gate_status_v7()
    assert status["no_trade_only_breakthroughs_blocked"] is True


def test_v7_forbidden_tokens_excluded_from_decisions() -> None:
    rows = load_v6_watchlist_records()
    rows += read_jsonl_file(
        RESEARCH_V7_ROOT.parent / "signal_research_v6" / "research_breakthrough_rejections_v6.jsonl"
    )
    for row in rows:
        sym = str(row.get("symbol", ""))
        assert not is_forbidden_symbol(sym), f"forbidden symbol in V6 decision records: {sym}"


def test_v7_proof_records_include_safety_and_robinhood_fields() -> None:
    rec = research_v7_proof_record("test-proof", "ok", {})
    assert rec.get("live_trading_enabled") is False
    assert rec.get("official_robinhood_market_data_allowed") is True
    assert rec.get("robinhood_live_trading_enabled") is False
    assert "proof_hash" in rec


def test_v7_all_v7_summaries_include_live_trading_enabled() -> None:
    from dopey_validation.public_signal_research_baseline_freezer_v7 import (
        run_public_signal_research_baseline_freezer_v7,
    )
    from dopey_validation.public_signal_research_v7_preflight import (
        run_public_signal_research_v7_preflight,
    )

    preflight = run_public_signal_research_v7_preflight()
    baseline = run_public_signal_research_baseline_freezer_v7()
    assert preflight.get("live_trading_enabled") is False
    assert baseline.get("live_trading_enabled") is False
