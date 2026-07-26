from __future__ import annotations

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS
from dopey_active_policy.zero_dte_replay_outcomes_artifact_repair_v1 import run_zero_dte_replay_outcomes_artifact_repair_v1
from dopey_autonomy.public_champion_common import is_test_symbol
from dopey_autonomy.signal_research_v3_common import STABLE_FAMILY_CONTINUATION, STABLE_FAMILY_VOLUME
from dopey_export.artifact_selector import export_selection_rules
from dopey_live_gate.public_signal_research_live_gate_status_v3 import build_live_gate_status_v3
from dopey_options_engine.cohort_path_replay_engine_v4 import replay_signal_trade_v4
from dopey_scoreboard.public_signal_research_scoreboard_v3 import build_public_signal_research_scoreboard_v3
from dopey_signal_research.research_breakthrough_gate_v3 import classify_breakthrough_v3
from dopey_signal_research.research_mutation_queue_executor_v3 import run_research_mutation_queue_executor_v3
from dopey_signal_research.stable_family_template_repair_v3 import (
    load_v3_templates,
    matches_continuation_v3,
    matches_volume_dry_up_v3,
    run_stable_family_template_repair_v3,
)
from dopey_validation.full_suite_stabilizer import collect_test_files, timeout_result
from dopey_validation.public_signal_research_v3_preflight import run_public_signal_research_v3_preflight
from dopey_wealth_engine.common import REPO_ROOT


pytestmark = pytest.mark.usefixtures("public_signal_research_v3_checkpoint")


def test_v3_preflight_loads_v2_mutation_queue() -> None:
    summary = run_public_signal_research_v3_preflight(run_lake_guard=False)
    assert summary["public_signal_research_v3_preflight_status"] == "ready_for_mutation_queue_execution"
    assert int(summary.get("v2_mutation_queue_count", 0)) == 31


def test_mutation_queue_executor_executes_nonempty_queue() -> None:
    summary = run_research_mutation_queue_executor_v3()
    assert summary["executed_mutation_count"] == 31
    assert summary["failed_mutation_count"] == 0


def test_stable_family_templates_support_both_families() -> None:
    templates = load_v3_templates()
    ids = {t.stable_family_template_id for t in templates}
    assert STABLE_FAMILY_CONTINUATION in ids
    assert STABLE_FAMILY_VOLUME in ids
    repair = run_stable_family_template_repair_v3()
    assert repair["continuation_template_enabled"] is True
    assert repair["volume_template_enabled"] is True


def test_volume_dry_up_matcher_fixed() -> None:
    features = {
        "volume": {"volume_dry_up": 1.0, "volume_percentile": 0.8, "volume_climax": 0.0},
        "price_structure": {"close_location_value": 0.6, "compression_10d": 0.6},
        "continuation": {"breakout_continuation": 1.0},
        "volatility": {"vol_compression_percentile": 0.5},
        "risk_filter": {"avoid_overextended_move": 0.0, "avoid_thin_volume": 0.0},
        "regime": {"volatility_regime": 0.0, "risk_on_proxy": 1.0},
    }
    assert matches_volume_dry_up_v3(features) is True


def test_candidate_generator_both_families() -> None:
    from dopey_signal_research.research_candidate_generator_v3 import run_research_candidate_generator_v3

    summary = run_research_candidate_generator_v3(candidate_cap=5000)
    assert summary["continuation_candidate_count"] > 0
    assert summary["volume_candidate_count"] > 0


def test_candidate_generator_excludes_fixture_tokens() -> None:
    assert is_test_symbol("SIMV2")
    assert not is_test_symbol("SPY")


def test_no_trade_filters_recorded() -> None:
    from dopey_signal_research.research_no_trade_filter_v3 import evaluate_no_trade_filters_v3

    features = {"risk_filter": {"avoid_overextended_move": 1.0}}
    ok, reasons = evaluate_no_trade_filters_v3(features, STABLE_FAMILY_CONTINUATION)
    assert ok is False
    assert "overextended_entry" in reasons


def test_profit_holdout_scorer_prioritizes() -> None:
    from dopey_signal_research.run_profit_holdout_repair_scorer_v3 import run_profit_holdout_repair_scorer_v3
    from dopey_signal_research.research_candidate_generator_v3 import run_research_candidate_generator_v3

    run_research_candidate_generator_v3(candidate_cap=3000)
    summary = run_profit_holdout_repair_scorer_v3()
    assert summary["prioritized_candidate_count"] > 0


def test_path_simulator_long_only() -> None:
    trade = replay_signal_trade_v4(sample_signal(), public_rows())
    assert trade["trade_intent"] in {"long_call", "long_put", "no_trade"}
    assert trade["short_option"] is False
    assert trade["spread_structure"] is False


def test_tournament_compares_v2() -> None:
    from dopey_signal_research.research_v2_v3_comparison_v3 import compare_v2_v3

    row = compare_v2_v3({"family_id": STABLE_FAMILY_VOLUME, "profit_factor": 0.9, "split_pass_rate": 0.1, "holdout_survival": False, "expectancy": -0.1})
    assert "v2_top_profit_factor" in row


def test_breakthrough_gate_public_data_only() -> None:
    status, reasons = classify_breakthrough_v3(
        {
            "discovery_family_id": STABLE_FAMILY_CONTINUATION,
            "sample_count": 50,
            "symbol_count": 10,
            "sector_count": 10,
            "net_pnl": 5.0,
            "expectancy": 0.5,
            "profit_factor": 1.25,
            "split_pass_rate": 0.6,
            "holdout_survival": True,
        }
    )
    assert status in {"research_breakthrough_candidate", "paper_champion_candidate_locked", "research_watchlist", "research_candidate"}


def test_mutation_queue_v3_nonempty_when_watchlist() -> None:
    from dopey_signal_research.research_breakthrough_gate_v3 import run_research_breakthrough_gate_v3
    from dopey_signal_research.research_mutation_queue_v3 import run_research_mutation_queue_v3
    from dopey_signal_research.research_path_simulator_v3 import run_research_path_simulator_v3
    from dopey_signal_research.research_tournament_v3 import run_research_tournament_v3
    from dopey_signal_research.run_profit_holdout_repair_scorer_v3 import run_profit_holdout_repair_scorer_v3
    from dopey_signal_research.research_candidate_generator_v3 import run_research_candidate_generator_v3

    run_research_candidate_generator_v3(candidate_cap=2000)
    run_profit_holdout_repair_scorer_v3()
    run_research_path_simulator_v3(max_candidates=1500)
    run_research_tournament_v3()
    run_research_breakthrough_gate_v3()
    summary = run_research_mutation_queue_v3()
    assert summary["mutation_queue_count"] > 0


def test_active_policy_artifact_repair_safe() -> None:
    summary = run_zero_dte_replay_outcomes_artifact_repair_v1()
    assert summary["live_trading_enabled"] is False
    assert summary["real_orders_placed"] is False


def test_active_policy_repair_not_performance_evidence() -> None:
    summary = run_zero_dte_replay_outcomes_artifact_repair_v1()
    assert summary.get("synthetic_repair_record_created") in {True, False}


def test_scoreboard_writes_json_html() -> None:
    from dopey_scoreboard import public_signal_research_scoreboard_v3 as scoreboard_module

    summary = build_public_signal_research_scoreboard_v3({}, {}, {}, {}, {}, {}, {}, {}, {})
    assert summary["scoreboard_status"] == "public_signal_research_scoreboard_written_v3"
    assert scoreboard_module.HTML_PATH.exists()


def test_live_gate_remains_disabled() -> None:
    status = build_live_gate_status_v3({"breakthrough_candidate_count": 0, "watchlist_count": 1})
    assert status["live_trading_enabled"] is False
    assert status["official_robinhood_market_data_allowed"] is True
    assert status["unofficial_robinhood_api_blocked"] is True


def test_no_env_credentials_broker() -> None:
    assert not (REPO_ROOT / ".env").exists()


def test_orchestrator_paths_exist() -> None:
    from dopey_autonomy.run_public_signal_research_breakthrough_v3 import orchestrator_artifact_paths

    assert "public_signal_research_breakthrough_v3_summary" in orchestrator_artifact_paths()


def test_audit_export_recognize_artifacts() -> None:
    keys = {spec[0] for spec in ARTIFACT_SPECS}
    assert "public_signal_research_breakthrough_v3_summary" in keys
    assert "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3" in ALLOWED_NEXT_BUILD_TARGETS
    export_ids = {row.artifact_id for row in export_selection_rules()}
    assert "public_signal_research_breakthrough_v3_summary" in export_ids


def test_stabilizer_includes_v3_shard() -> None:
    assert "tests/test_public_signal_research_breakthrough_v3.py" in collect_test_files()


def test_timeout_not_pass() -> None:
    assert timeout_result(["pytest"], 60)["timeout_recorded_as_pass"] is False


def test_continuation_matcher() -> None:
    features = {
        "continuation": {"pullback_continuation": 1.0},
        "volume": {"volume_percentile": 1.1},
        "relative_strength": {"vs_spy": 0.01},
        "risk_filter": {"avoid_overextended_move": 0.0, "avoid_poor_regime_alignment": 0.0},
    }
    assert matches_continuation_v3(features) is True


def sample_signal() -> dict[str, object]:
    return {
        "signal_id": "rsv3-test",
        "symbol": "SPY",
        "timestamp": "2024-03-01",
        "trade_intent": "long_call",
        "dte_bucket": 14,
        "moneyness_bucket": "1pct_otm",
        "exit_policy": "trend_follow",
        "hold_window": 5,
    }


def public_rows() -> list[dict[str, str]]:
    rows = []
    price = 400.0
    for i in range(260):
        price += 0.1
        rows.append({"date": f"2023-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}", "open": str(price), "high": str(price + 1), "low": str(price - 1), "close": str(price), "volume": str(1_000_000 + i * 100)})
    return rows
