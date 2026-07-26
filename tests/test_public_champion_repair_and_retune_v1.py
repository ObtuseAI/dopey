from __future__ import annotations

from pathlib import Path

from dopey_autonomy.run_public_champion_repair_and_retune_v1 import orchestrator_artifact_paths
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS
from dopey_champion.conditional_champion_retune_hardening_gate_v1 import classify_retune
from dopey_champion.conditional_champion_repair_planner_v1 import derive_repair_actions
from dopey_champion.demoted_champion_salvage_analyzer_v1 import classify_demoted
from dopey_champion.public_paper_champion_gate_v2 import evaluate_public_paper_champions_v2
from dopey_export.artifact_selector import export_selection_rules
from dopey_live_gate.public_champion_repair_live_gate_status_v1 import build_live_gate_status_v1
from dopey_options_engine.cohort_path_replay_engine_v4 import replay_signal_trade_v4
from dopey_scoreboard.public_champion_repair_scoreboard_v1 import build_public_champion_repair_scoreboard_v1
from dopey_signal_engine.conditional_champion_signal_retune_v1 import build_retune_candidate, feature_snapshot
from dopey_tournament.conditional_champion_before_after_comparison_v1 import build_before_after_rows
from dopey_validation.full_suite_stabilizer import collect_test_files, timeout_result
from dopey_validation.public_champion_artifact_guard_v1 import artifact_shrunk, CANONICAL_ARTIFACTS
from dopey_wealth_engine.common import REPO_ROOT


def test_artifact_guard_prevents_test_evaluator_canonical_overwrite() -> None:
    from dopey_champion.champion_threshold_profiles_v2 import champion_threshold_profile_v2

    before_rows = Path("artifacts/dopey/champions/public_paper_champion_gate_v2_results.jsonl").stat().st_size if Path("artifacts/dopey/champions/public_paper_champion_gate_v2_results.jsonl").exists() else 0
    evaluate_public_paper_champions_v2([{"cohort_id": "test-only", "cohort_level": "variant_id", "public_data_only": True, "sample_count": 1}], champion_threshold_profile_v2(), artifact_mode="test", persist=True)
    after_rows = Path("artifacts/dopey/champions/public_paper_champion_gate_v2_results.jsonl").stat().st_size if Path("artifacts/dopey/champions/public_paper_champion_gate_v2_results.jsonl").exists() else 0
    assert before_rows == after_rows


def test_preflight_expects_two_conditional_champions() -> None:
    from dopey_autonomy.champion_repair_common import conditional_champion_names

    names = conditional_champion_names()
    assert len(names) == 2


def test_repair_planner_emits_plans_for_both_conditional_champions() -> None:
    actions = derive_repair_actions(["core_deep_stress_failure"], [("sample_count_inadequate", 1)], {"sample_count": 20})
    assert "sample_expansion" in actions
    assert "slippage_hardening" in actions


def test_retune_generator_excludes_test_symbols() -> None:
    from dopey_autonomy.public_champion_common import is_test_symbol

    assert is_test_symbol("SIMV2")
    assert is_test_symbol("TESTX")
    assert not is_test_symbol("SPY")


def test_retune_path_simulator_long_only_structures() -> None:
    trade = replay_signal_trade_v4(sample_signal(), public_rows())
    assert trade["trade_intent"] in {"long_call", "long_put", "no_trade"}
    assert trade["short_option"] is False
    assert trade["spread_structure"] is False
    assert trade["model_priced"] is True
    assert trade["quote_priced"] is False


def test_retune_hardening_gate_does_not_lower_thresholds() -> None:
    status, reasons = classify_retune("parent", 0.9, {"sample_count": 40, "profit_factor": 1.2, "expectancy": 0.5}, {"expectancy": 0.2}, True)
    assert status == "retuned_hardened_public_paper_champion"
    assert "threshold" not in " ".join(reasons)


def test_demoted_salvage_classifies_all_seven() -> None:
    demoted = [
        "volatility_squeeze_breakout|fast_scalp|dte7|ATM",
        "volatility_squeeze_breakout|scalp|short_dte|atm",
        "volatility_squeeze_breakout|bullish|scalp",
        "volatility_squeeze_breakout",
        "champ-5264fd3b2fed",
        "bollinger_expansion|vol_hunter|short_dte|otm",
        "bollinger_expansion|volatility_expansion_hunter|dte10|ATM",
    ]
    statuses = {classify_demoted(name, {"sample_count": 40, "profit_factor": 1.0, "net_pnl": 1.0}, "volatility_squeeze" in name) for name in demoted}
    assert len(statuses) >= 2


def test_live_gate_remains_disabled() -> None:
    status = build_live_gate_status_v1({"retuned_hardened_count": 2, "retuned_conditional_count": 0, "retuned_demoted_count": 0})
    assert status["live_trading_enabled"] is False
    assert status["official_robinhood_market_data_allowed"] is True
    assert status["unofficial_robinhood_api_blocked"] is True


def test_no_env_credentials_broker_orders() -> None:
    assert not (REPO_ROOT / ".env").exists()
    status = build_live_gate_status_v1({"retuned_hardened_count": 0, "retuned_conditional_count": 0, "retuned_demoted_count": 0})
    assert status["credentials_present"] is False
    assert status["broker_connection_enabled"] is False
    assert status["real_order_enabled"] is False


def test_full_orchestrator_declares_artifact_paths() -> None:
    paths = orchestrator_artifact_paths()
    assert "public_champion_repair_and_retune_v1_summary" in paths


def test_audit_export_recognize_repair_artifacts() -> None:
    spec_names = {spec[0] for spec in ARTIFACT_SPECS}
    rule_names = {rule.artifact_id for rule in export_selection_rules()}
    for artifact_id in [
        "public_champion_repair_preflight_v1_summary",
        "public_champion_artifact_guard_v1_summary",
        "conditional_champion_retune_hardening_gate_v1_summary",
        "public_champion_repair_and_retune_v1_summary",
    ]:
        assert artifact_id in spec_names
        assert artifact_id in rule_names
    assert "DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1" in ALLOWED_NEXT_BUILD_TARGETS


def test_validation_stabilizer_includes_repair_shard() -> None:
    files = collect_test_files(REPO_ROOT)
    assert "tests/test_public_champion_repair_and_retune_v1.py" in files


def test_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_before_after_comparison_builds_rows() -> None:
    rows = build_before_after_rows([], [])
    assert isinstance(rows, list)


def test_scoreboard_writes_structure() -> None:
    board = build_public_champion_repair_scoreboard_v1(
        {"input_public_champion_count": 9, "conditional_champion_names": ["a", "b"], "demoted_champion_names": []},
        {"retuned_hardened_names": [], "retuned_conditional_names": ["a"], "retuned_demoted_names": ["b"]},
        {"salvage_candidate_count": 0, "kill_confirmed_count": 5},
        [],
    )
    assert board["scoreboard_status"] == "public_champion_repair_scoreboard_written"


def sample_signal() -> dict[str, object]:
    return {
        "signal_id": "unit-retune-1",
        "symbol": "SPY",
        "timestamp": "2024-01-03",
        "date": "2024-01-03",
        "trade_intent": "long_call",
        "direction": "bullish",
        "entry_price": 100.0,
        "invalidation_level": 98.0,
        "target_price": 104.0,
        "hold_window": 5,
        "dte_bucket": 14,
        "moneyness_bucket": "ATM",
        "exit_policy": "trend_follow",
        "market_data_source_type": "public_live_fetch",
    }


def public_rows() -> list[dict[str, str]]:
    rows = []
    for index in range(12):
        close = 100.0 + index
        rows.append({"date": f"2024-01-{index + 1:02d}", "open": str(close - 0.5), "high": str(close + 1), "low": str(close - 1), "close": str(close), "volume": "1000000", "market_data_source_type": "public_live_fetch"})
    return rows
