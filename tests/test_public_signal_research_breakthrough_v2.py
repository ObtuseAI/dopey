from __future__ import annotations

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS
from dopey_autonomy.public_champion_common import is_test_symbol
from dopey_autonomy.signal_research_v2_common import is_generic_label
from dopey_export.artifact_selector import export_selection_rules
from dopey_live_gate.public_signal_research_live_gate_status_v2 import build_live_gate_status_v2
from dopey_options_engine.cohort_path_replay_engine_v4 import replay_signal_trade_v4
from dopey_scoreboard.public_signal_research_scoreboard_v2 import build_public_signal_research_scoreboard_v2
from dopey_signal_research.research_breakthrough_gate_v2 import classify_breakthrough_v2
from dopey_signal_research.research_coverage_penalty_v2 import coverage_penalty
from dopey_signal_research.research_universe_coverage_v2 import build_universe
from dopey_signal_research.stable_discovery_family_id_v2 import assign_stable_ids
from dopey_signal_research.watchlist_mutation_planner_v2 import plan_mutations
from dopey_validation.full_suite_stabilizer import collect_test_files, timeout_result
from dopey_wealth_engine.common import REPO_ROOT


pytestmark = pytest.mark.usefixtures("public_signal_research_v2_checkpoint")


def test_v2_preflight_reads_v1_watchlist_state() -> None:
    from dopey_autonomy.signal_research_v2_common import load_v1_gate_summary

    gate = load_v1_gate_summary()
    assert int(gate.get("watchlist_count", 0)) == 2
    assert int(gate.get("breakthrough_candidate_count", 0)) == 0


def test_watchlist_extractor_finds_two_candidates() -> None:
    from dopey_signal_research.watchlist_candidate_extractor_v2 import run_watchlist_candidate_extractor_v2

    summary = run_watchlist_candidate_extractor_v2()
    assert summary["watchlist_candidate_count"] == 2


def test_generic_label_repair_assigns_stable_ids() -> None:
    ids = assign_stable_ids("continuation")
    assert ids["generic_label_repaired"] is True
    assert "|" in ids["discovery_family_id"]
    assert not is_generic_label(ids["discovery_family_id"])


def test_symbol_sector_scheduler_broadens_universe() -> None:
    universe = build_universe(target_symbols=100)
    assert universe["symbol_count"] >= 60
    assert universe["sector_count"] >= 8


def test_mutation_planner_non_empty_from_watchlist() -> None:
    mutations = plan_mutations(["symbol_count_below_minimum", "profit_factor_below_threshold"])
    assert "symbol_expansion" in mutations
    assert len(mutations) >= 5


def test_candidate_generator_excludes_test_symbols() -> None:
    assert is_test_symbol("SIMV2")
    assert not is_test_symbol("SPY")


def test_path_simulator_long_only() -> None:
    trade = replay_signal_trade_v4(sample_signal(), public_rows())
    assert trade["trade_intent"] in {"long_call", "long_put", "no_trade"}
    assert trade["short_option"] is False
    assert trade["spread_structure"] is False


def test_tournament_coverage_penalty() -> None:
    score, penalties = coverage_penalty({"symbol_count": 2, "sector_count": 2, "family_id": "continuation|pullback|high_volume"})
    assert score < 1.0
    assert "symbol_count_below_minimum" in penalties


def test_breakthrough_gate_v2_rejects_quarantined() -> None:
    status, reasons = classify_breakthrough_v2({
        "discovery_family_id": "volatility_squeeze_breakout",
        "sample_count": 100, "symbol_count": 10, "sector_count": 10,
        "net_pnl": 5.0, "expectancy": 0.5, "profit_factor": 1.5,
        "split_pass_rate": 0.6, "holdout_survival": True,
    })
    assert status == "research_candidate"
    assert "quarantined_failed_family" in reasons


def test_breakthrough_gate_v2_promotes_public_candidate() -> None:
    status, reasons = classify_breakthrough_v2({
        "discovery_family_id": "continuation|pullback|high_volume|trend_follow|dte14|1pct_otm",
        "sample_count": 50, "symbol_count": 10, "sector_count": 10,
        "net_pnl": 5.0, "expectancy": 0.5, "profit_factor": 1.25,
        "split_pass_rate": 0.6, "holdout_survival": True,
    })
    assert status in {"research_breakthrough_candidate", "paper_champion_candidate_locked"}
    assert not reasons


def test_mutation_queue_nonempty_when_watchlist() -> None:
    from dopey_signal_research.research_mutation_queue_v2 import run_research_mutation_queue_v2
    from dopey_signal_research.watchlist_mutation_planner_v2 import run_watchlist_mutation_planner_v2

    run_watchlist_mutation_planner_v2()
    summary = run_research_mutation_queue_v2()
    assert summary["mutation_queue_count"] > 0


def test_live_gate_remains_disabled() -> None:
    status = build_live_gate_status_v2({"breakthrough_candidate_count": 0, "watchlist_count": 2})
    assert status["live_trading_enabled"] is False
    assert status["official_robinhood_market_data_allowed"] is True
    assert status["unofficial_robinhood_api_blocked"] is True


def test_no_env_credentials_broker() -> None:
    assert not (REPO_ROOT / ".env").exists()


def test_orchestrator_paths_exist() -> None:
    from dopey_autonomy.run_public_signal_research_breakthrough_v2 import orchestrator_artifact_paths

    assert "public_signal_research_breakthrough_v2_summary" in orchestrator_artifact_paths()


def test_audit_export_recognize_artifacts() -> None:
    keys = {spec[0] for spec in ARTIFACT_SPECS}
    assert "public_signal_research_breakthrough_v2_summary" in keys
    assert "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V2" in ALLOWED_NEXT_BUILD_TARGETS
    export_ids = {row.artifact_id for row in export_selection_rules()}
    assert "public_signal_research_breakthrough_v2_summary" in export_ids


def test_stabilizer_includes_v2_shard() -> None:
    assert "tests/test_public_signal_research_breakthrough_v2.py" in collect_test_files()


def test_timeout_not_pass() -> None:
    assert timeout_result(["pytest"], 60)["timeout_recorded_as_pass"] is False


def test_scoreboard_writes_json_html() -> None:
    from dopey_scoreboard import public_signal_research_scoreboard_v2 as scoreboard_module

    summary = build_public_signal_research_scoreboard_v2({}, {}, {}, {}, {}, {}, {})
    assert summary["scoreboard_status"] == "public_signal_research_scoreboard_written_v2"
    assert scoreboard_module.HTML_PATH.exists()


def sample_signal() -> dict[str, object]:
    return {
        "signal_id": "rsv2-test",
        "symbol": "SPY",
        "timestamp": "2024-03-01",
        "trade_intent": "long_call",
        "dte_bucket": 14,
        "moneyness_bucket": "ATM",
        "exit_policy": "trend_follow",
        "hold_window": 5,
        "invalidation_level": 0.0,
        "target_price": 0.0,
        "market_data_source_type": "public_live_fetch",
    }


def public_rows() -> list[dict[str, str]]:
    rows = []
    price = 100.0
    for day in range(120):
        price *= 1.001
        rows.append({
            "date": f"2024-{(day // 28) + 1:02d}-{(day % 28) + 1:02d}",
            "open": f"{price:.4f}",
            "high": f"{price * 1.01:.4f}",
            "low": f"{price * 0.99:.4f}",
            "close": f"{price:.4f}",
            "volume": "1000000",
        })
    return rows
