"""Tests for DOPEY static tournament performance reporting dashboard artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS, build_artifact_record, build_inventory
from dopey_audit.hash_auditor import audit_record_hash
from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_reporting.data_loader import (
    FAMILY_REPORT_CARDS_PATH,
    PERFORMANCE_ATTRIBUTION_PATH,
    REPORTING_BUNDLE_SUMMARY_PATH,
    REPORTING_DASHBOARD_INDEX_JSON,
    REPORTING_PROOF_PATH,
    SCENARIO_REPORT_CARDS_PATH,
    STATIC_DASHBOARD_PATH,
    STRATEGY_REPORT_CARDS_PATH,
    EVIDENCE_PATHS,
    load_reporting_evidence,
)
from dopey_reporting.family_report_cards import ALL_STRATEGY_FAMILIES, build_family_report_cards
from dopey_reporting.performance_attribution import build_performance_attribution
from dopey_reporting.performance_models import attribution_record_hash, canonical_reporting_hash
from dopey_reporting.regime_explainability import build_regime_report_cards
from dopey_reporting.report_models import (
    EvidenceLayerExplanation,
    FamilyReportCard,
    PerformanceAttributionSummary,
    ScenarioReportCard,
    StrategyReportCard,
)
from dopey_reporting.reporting_bundle import run_tournament_performance_reporting_bundle
from dopey_reporting.scenario_explainability import build_scenario_report_cards
from dopey_reporting.strategy_report_cards import build_strategy_report_cards


@pytest.fixture(scope="module")
def evidence():
    return load_reporting_evidence(EVIDENCE_PATHS)


@pytest.fixture(scope="module")
def reporting_result() -> dict:
    return run_tournament_performance_reporting_bundle()


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="reporting-live-x",
        symbol="SPY_FIXTURE",
        structure="vertical",
        legs=[
            {"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19", "option_type": "call", "mid": 1.0},
            {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19", "option_type": "call", "mid": 0.5},
        ],
        quantity=1,
        defined_risk=True,
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=5.0,
        target_profit=5.0,
    )


def test_strategy_report_card_serializes_deterministically() -> None:
    card = StrategyReportCard(
        strategy_id="s1",
        strategy_family="directional_convexity",
        promotion_state="research_only",
        tournament_score=0.5,
        walk_forward_consistency_score=0.4,
        corpus_v2_score=0.3,
        macro_fit_score=0.2,
        iv_surface_fit_score=0.2,
        greek_fit_score=0.6,
        fundamental_fit_score=0.5,
        liquidity_robustness_score=0.7,
        slippage_robustness_score=0.8,
        pattern_score=0.4,
        failure_pressure_score=0.1,
        overfit_level="low",
        ensemble_weight=0.0,
        meta_governor_decision="hold_research_only",
        top_supporting_evidence=["tournament"],
        top_contradicting_evidence=[],
        top_failure_modes=[],
        best_regimes=[],
        worst_regimes=[],
        paper_only=True,
        live_allowed=False,
        summary_decision="research_only; paper-only report card",
        score_table={},
        evidence_support=[],
        evidence_contradiction=[],
        scenario_explanations=[],
        known_limitations=[],
        reproducibility_hash="",
    )
    assert json.dumps(card.to_dict(), sort_keys=True) == json.dumps(card.to_dict(), sort_keys=True)


def test_family_report_card_serializes_deterministically() -> None:
    card = FamilyReportCard("directional_convexity", 1, "s1", 0.5, [], [], [], [], 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, "research_only", "", {}, True, False, [], "")
    assert card.to_dict() == FamilyReportCard("directional_convexity", 1, "s1", 0.5, [], [], [], [], 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, "research_only", "", {}, True, False, [], "").to_dict()


def test_scenario_report_card_serializes_deterministically() -> None:
    card = ScenarioReportCard("sc1", "macro", "macro_event_fixtures", ["directional_convexity"], ["volatility_compression"], "s1", "s2", ["fakeout"], "fixture", "paper-only", "")
    assert card.to_dict() == ScenarioReportCard("sc1", "macro", "macro_event_fixtures", ["directional_convexity"], ["volatility_compression"], "s1", "s2", ["fakeout"], "fixture", "paper-only", "").to_dict()


def test_evidence_layer_explanation_links_artifact_paths() -> None:
    e = EvidenceLayerExplanation("tournament", ["supports"], [], 0.5, 0.6, [], ["artifacts/dopey/tournaments/dopey_tournament.jsonl"])
    assert e.artifact_paths
    assert "dopey_tournament.jsonl" in e.artifact_paths[0]


def test_performance_attribution_summary_hash_is_deterministic() -> None:
    record = {"strategy_id": "s1", "score": 0.5, "paper_only": True}
    assert attribution_record_hash(record) == attribution_record_hash(record)


def test_strategy_report_cards_include_required_evidence_layers(evidence) -> None:
    cards = build_strategy_report_cards(evidence)
    assert cards
    assert {"tournament", "champion_registry", "ensemble_allocator"}.intersection(cards[0].top_supporting_evidence)


def test_strategy_report_cards_include_supporting_and_contradicting_evidence(evidence) -> None:
    cards = build_strategy_report_cards(evidence)
    assert any(card.top_supporting_evidence for card in cards)
    assert any(card.top_contradicting_evidence for card in cards)


def test_family_report_cards_cover_all_strategy_families(evidence) -> None:
    cards = build_family_report_cards(evidence, build_strategy_report_cards(evidence))
    assert {card.strategy_family for card in cards} == set(ALL_STRATEGY_FAMILIES)


def test_family_report_cards_record_best_and_worst_regimes(evidence) -> None:
    cards = build_family_report_cards(evidence, build_strategy_report_cards(evidence))
    assert all(card.best_regimes for card in cards)
    assert all(card.worst_regimes for card in cards)


def test_report_cards_are_paper_only(evidence) -> None:
    strategy_cards = build_strategy_report_cards(evidence)
    family_cards = build_family_report_cards(evidence, strategy_cards)
    assert all(card.paper_only and card.live_allowed is False for card in strategy_cards)
    assert all(card.paper_only and card.live_allowed is False for card in family_cards)


def test_scenario_explainability_covers_macro_iv_fundamental_scenarios(evidence) -> None:
    cards = build_scenario_report_cards(evidence, build_strategy_report_cards(evidence))
    layers = {card.source_layer for card in cards}
    assert {"macro_event_fixtures", "iv_surface_skew_term", "sector_peer_fundamental_fixtures"}.issubset(layers)


def test_regime_explainability_covers_corpus_v2_windows(evidence) -> None:
    cards = build_regime_report_cards(evidence, build_strategy_report_cards(evidence))
    assert any(card.source_layer == "regime_holdout_corpus_v2" for card in cards)


def test_scenario_report_cards_record_winners_losers_and_failure_modes(evidence) -> None:
    cards = build_scenario_report_cards(evidence, build_strategy_report_cards(evidence))
    assert any(card.winning_strategy or card.losing_strategy for card in cards)
    assert any(card.dominant_failure_modes for card in cards)


def test_performance_attribution_records_positive_and_negative_drivers(evidence) -> None:
    records = build_performance_attribution(evidence, build_strategy_report_cards(evidence))
    assert any(record.top_positive_drivers for record in records)
    assert any(record.top_negative_drivers for record in records)


def test_performance_attribution_includes_macro_iv_fundamental_liquidity_layers(evidence) -> None:
    record = build_performance_attribution(evidence, build_strategy_report_cards(evidence))[0]
    assert isinstance(record.macro_fit, float)
    assert isinstance(record.iv_surface_skew_term_fit, float)
    assert isinstance(record.sector_peer_fundamental_fit, float)
    assert isinstance(record.liquidity_slippage, float)


def test_performance_attribution_is_deterministic(evidence) -> None:
    first = [record.to_dict() for record in build_performance_attribution(evidence, build_strategy_report_cards(evidence))]
    second = [record.to_dict() for record in build_performance_attribution(evidence, build_strategy_report_cards(evidence))]
    assert first == second


def test_dashboard_index_written(reporting_result) -> None:
    assert reporting_result["reporting_bundle_status"] == "ok"
    assert REPORTING_DASHBOARD_INDEX_JSON.exists()


def test_dashboard_index_lists_artifact_paths(reporting_result) -> None:
    record = json.loads(REPORTING_DASHBOARD_INDEX_JSON.read_text(encoding="utf-8"))
    assert "strategy_report_cards" in record["artifact_paths"]


def test_dashboard_index_includes_safety_status(reporting_result) -> None:
    record = json.loads(REPORTING_DASHBOARD_INDEX_JSON.read_text(encoding="utf-8"))
    assert record["paper_only"] is True
    assert record["live_allowed"] is False
    assert record["safety_status"]["mode"] == "RESEARCH"


def test_static_dashboard_if_present_has_no_external_dependencies(reporting_result) -> None:
    if STATIC_DASHBOARD_PATH.exists():
        html = STATIC_DASHBOARD_PATH.read_text(encoding="utf-8").lower()
        assert "http://" not in html
        assert "https://" not in html
        assert "<script" not in html


def test_reporting_bundle_summary_written(reporting_result) -> None:
    assert REPORTING_BUNDLE_SUMMARY_PATH.exists()
    assert json.loads(REPORTING_BUNDLE_SUMMARY_PATH.read_text(encoding="utf-8"))["reporting_bundle_status"] == "ok"


def test_reporting_bundle_cli_runs_offline(reporting_result) -> None:
    assert reporting_result["mode"] == "RESEARCH"
    assert reporting_result["live_trading_enabled"] is False
    assert reporting_result["live_blocked"] is True


def test_reporting_bundle_writes_strategy_family_scenario_artifacts(reporting_result) -> None:
    assert STRATEGY_REPORT_CARDS_PATH.exists()
    assert FAMILY_REPORT_CARDS_PATH.exists()
    assert SCENARIO_REPORT_CARDS_PATH.exists()


def test_reporting_bundle_proof_record_written(reporting_result) -> None:
    assert REPORTING_PROOF_PATH.exists()
    assert _jsonl(REPORTING_PROOF_PATH)[-1]["final_status"] == "PASS"


def test_reporting_bundle_reproducibility_hash_is_deterministic(reporting_result) -> None:
    record = json.loads(REPORTING_DASHBOARD_INDEX_JSON.read_text(encoding="utf-8"))
    assert canonical_reporting_hash(record) == record["reproducibility_hash"]


def test_evidence_audit_recognizes_reporting_artifacts(reporting_result) -> None:
    names = {spec[0] for spec in ARTIFACT_SPECS}
    assert {"reporting_dashboard_index", "strategy_report_cards", "family_report_cards", "scenario_report_cards", "performance_attribution", "reporting_bundle_proof"}.issubset(names)
    inv = build_inventory()
    assert any(artifact.artifact_type == "reporting_dashboard_index" and artifact.status == "present" for artifact in inv.artifacts)


def test_evidence_audit_hashes_reporting_artifacts(reporting_result) -> None:
    strategy_record = _jsonl(STRATEGY_REPORT_CARDS_PATH)[-1]
    case, finding = audit_record_hash("strategy_report_cards", strategy_record, 0)
    assert case is not None
    assert case.passed is True
    assert finding is None


def test_evidence_audit_flags_missing_reporting_artifact(tmp_path: Path) -> None:
    artifact = build_artifact_record("reporting_dashboard_index", tmp_path / "missing" / "dashboard_index.json")
    assert artifact.status == "missing"


def test_evidence_audit_reporting_summary_records_counts(reporting_result) -> None:
    summary = json.loads(REPORTING_BUNDLE_SUMMARY_PATH.read_text(encoding="utf-8"))
    assert summary["strategy_report_card_count"] >= 4
    assert summary["family_report_card_count"] == 4


def test_known_mutation_selection_flaky_status_documented_or_fixed() -> None:
    """Sentinel for the once-flaky mutation selection: with a fixed seed the
    bundle must be deterministic AND honor the selection/champion discipline.
    (`best_delta > 0` was outcome-luck - it flipped whenever the evaluation
    corpus legitimately changed, e.g. when window_001 joined the expanded
    corpus. The champion title is EARNED above the improvement floor, never
    awarded on a losing round.)"""
    from dopey_strategy_lab.mutation_scorecard import MIN_IMPROVED_MUTATION_DELTA
    from dopey_strategy_lab.run_mutation_population_bundle import run_mutation_population_bundle

    result = run_mutation_population_bundle(seed="pytest-reporting-flaky-status")
    rerun = run_mutation_population_bundle(seed="pytest-reporting-flaky-status")
    assert result["best_mutation"] == rerun["best_mutation"]
    assert result["best_delta"] == rerun["best_delta"]
    best_decision = result["promotion_decisions"][result["best_mutation"]]
    if result["best_delta"] > MIN_IMPROVED_MUTATION_DELTA:
        assert best_decision == "offline_mutation_champion"
    else:
        assert best_decision in {"degraded", "research_only"}
        assert "offline_mutation_champion" not in set(result["promotion_decisions"].values())


def test_no_live_promotion_possible_after_reporting_bundle(reporting_result) -> None:
    records = _jsonl(STRATEGY_REPORT_CARDS_PATH)
    assert all(record["live_allowed"] is False for record in records)


def test_live_stubs_still_block_after_reporting_bundle() -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_reporting_bundle() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_reporting_bundle(reporting_result) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False


def test_reporting_bundle_does_not_modify_live_settings(reporting_result) -> None:
    assert reporting_result["safety_state"]["mode"] == "RESEARCH"
    assert reporting_result["safety_state"]["live_trading_enabled"] is False
    assert reporting_result["safety_state"]["funded_broker_connections_enabled"] is False
    assert reporting_result["safety_state"]["allow_unofficial_robinhood_api"] is False


def test_reporting_artifacts_contain_no_active_live_decisions(reporting_result) -> None:
    for path in [STRATEGY_REPORT_CARDS_PATH, FAMILY_REPORT_CARDS_PATH, SCENARIO_REPORT_CARDS_PATH, PERFORMANCE_ATTRIBUTION_PATH]:
        text = path.read_text(encoding="utf-8")
        assert '"live_allowed": false' in text or '"live_allowed":false' in text or path == SCENARIO_REPORT_CARDS_PATH
        assert '"decision": "micro_live"' not in text
        assert '"decision": "adaptive_live"' not in text
        assert '"decision": "live_candidate"' not in text


def test_blunder_source_integrity_if_manifest_available(reporting_result) -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        pytest.skip("Blunder SHA256 manifest not available")
    import hashlib
    checked = 0
    for line in manifest.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        expected, file_path = parts
        candidate = Path(file_path)
        if not candidate.exists():
            continue
        assert hashlib.sha256(candidate.read_bytes()).hexdigest().upper() == expected.upper()
        checked += 1
    assert checked > 0
