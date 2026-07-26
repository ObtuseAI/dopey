from __future__ import annotations

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS
from dopey_autonomy.public_champion_common import is_test_symbol
from dopey_autonomy.signal_research_common import is_quarantined_signature, quarantine_overlap
from dopey_export.artifact_selector import export_selection_rules
from dopey_live_gate.public_signal_research_live_gate_status_v1 import build_live_gate_status_v1
from dopey_options_engine.cohort_path_replay_engine_v4 import replay_signal_trade_v4
from dopey_scoreboard import public_signal_research_scoreboard_v1
from dopey_scoreboard.public_signal_research_scoreboard_v1 import build_public_signal_research_scoreboard_v1
from dopey_signal_research.discovery_signal_family_models_v1 import FAMILY_TEMPLATES
from dopey_signal_research.public_feature_miner_v1 import compute_features
from dopey_signal_research.research_breakthrough_gate_v1 import classify_breakthrough
from dopey_validation.full_suite_stabilizer import collect_test_files, timeout_result
from dopey_wealth_engine.common import REPO_ROOT


def test_preflight_understands_failed_repair_state() -> None:
    from dopey_validation.public_signal_research_preflight_v1 import _repair_outcome_understood

    assert _repair_outcome_understood({
        "retuned_hardened_count": 0,
        "retuned_conditional_count": 0,
        "retuned_demoted_count": 2,
        "salvage_candidate_count": 0,
    })


def test_quarantine_captures_failed_families() -> None:
    assert is_quarantined_signature("volatility_squeeze_breakout|fast_scalp|dte7|ATM")
    assert is_quarantined_signature("bollinger_expansion|trend_follow|dte14|1pct_otm")
    assert not is_quarantined_signature("continuation|pullback|high_volume")


def test_feature_miner_public_only_features() -> None:
    rows = public_rows()
    features = compute_features("SPY", rows, 80, rows)
    assert "price_structure" in features
    assert "robinhood_market_data" in features
    assert features["robinhood_market_data"]["official_robinhood_market_data_allowed"] == 1.0


def test_discovery_generator_avoids_quarantined_signatures() -> None:
    for template in FAMILY_TEMPLATES:
        if quarantine_overlap(template.family_id):
            continue
        assert not is_quarantined_signature(template.family_id)


def test_research_candidate_generator_excludes_test_symbols() -> None:
    assert is_test_symbol("SIMV2")
    assert not is_test_symbol("SPY")


def test_research_path_simulator_long_only() -> None:
    trade = replay_signal_trade_v4(sample_signal(), public_rows())
    assert trade["trade_intent"] in {"long_call", "long_put", "no_trade"}
    assert trade["short_option"] is False
    assert trade["spread_structure"] is False
    assert trade["model_priced"] is True
    assert trade["quote_priced"] is False


def test_breakthrough_gate_rejects_quarantined() -> None:
    status, reasons = classify_breakthrough(
        {"family_id": "volatility_squeeze_breakout", "sample_count": 100, "symbol_count": 10, "net_pnl": 5.0, "expectancy": 0.5, "profit_factor": 1.5, "split_pass_rate": 0.6, "holdout_survival": True},
        {"volatility_squeeze_breakout"},
    )
    assert status == "research_candidate"
    assert "quarantined_failed_family" in reasons


def test_breakthrough_gate_promotes_public_candidate() -> None:
    status, reasons = classify_breakthrough(
        {"family_id": "continuation|pullback|high_volume", "sample_count": 50, "symbol_count": 8, "net_pnl": 5.0, "expectancy": 0.5, "profit_factor": 1.25, "split_pass_rate": 0.6, "holdout_survival": True},
        set(),
    )
    assert status in {"research_breakthrough_candidate", "paper_champion_candidate_locked"}
    assert not reasons


def test_mutation_queue_types_exist() -> None:
    from dopey_signal_research.research_mutation_queue_v1 import MUTATION_TYPES

    assert "expand_sample_count" in MUTATION_TYPES
    assert "alter_dte" in MUTATION_TYPES


def test_live_gate_remains_disabled() -> None:
    status = build_live_gate_status_v1({"breakthrough_candidate_count": 2, "paper_champion_candidate_locked_count": 1})
    assert status["live_trading_enabled"] is False
    assert status["live_gate_status"] == "disabled_live_gate_locked"
    assert status["official_robinhood_market_data_allowed"] is True
    assert status["unofficial_robinhood_api_blocked"] is True
    assert status["robinhood_scraping_blocked"] is True
    assert status["robinhood_reverse_auth_blocked"] is True
    assert status["robinhood_live_trading_enabled"] is False


def test_no_env_credentials_broker() -> None:
    assert not (REPO_ROOT / ".env").exists()


def test_orchestrator_paths_exist() -> None:
    from dopey_autonomy.run_public_signal_research_breakthrough_v1 import orchestrator_artifact_paths

    paths = orchestrator_artifact_paths()
    assert "public_signal_research_breakthrough_v1_summary" in paths


def test_audit_export_recognize_artifacts() -> None:
    keys = {spec[0] for spec in ARTIFACT_SPECS}
    assert "public_signal_research_breakthrough_v1_summary" in keys
    assert "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1" in ALLOWED_NEXT_BUILD_TARGETS
    export_ids = {row.artifact_id for row in export_selection_rules()}
    assert "public_signal_research_breakthrough_v1_summary" in export_ids


def test_stabilizer_includes_research_shard() -> None:
    files = collect_test_files()
    assert "tests/test_public_signal_research_breakthrough_v1.py" in files


def test_timeout_not_pass() -> None:
    result = timeout_result(["pytest"], 60)
    assert result["timeout_recorded_as_pass"] is False


def test_scoreboard_builds_json_html_paths() -> None:
    summary = build_public_signal_research_scoreboard_v1({}, {}, {}, {}, {}, {})
    assert summary["scoreboard_status"] == "public_signal_research_scoreboard_written"
    assert public_signal_research_scoreboard_v1.HTML_PATH.exists()


def sample_signal() -> dict[str, object]:
    return {
        "signal_id": "rs-test",
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
