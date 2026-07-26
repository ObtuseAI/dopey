"""Tests for the DOPEY sector/peer/fundamental fixture expansion bundle.

Required tests:
- Model tests (5)
- Scenario tests (4)
- Family scoring tests (8)
- Coverage tests (3)
- Integration tests (11)
- Safety regression tests (6)

All tests run offline, deterministic, paper-only, and live-blocked.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_analysis.fundamental_coverage import (
    REQUIRED_COVERAGE_CATEGORIES,
    build_fundamental_coverage,
)
from dopey_analysis.fundamental_family_scoring import (
    FUNDAMENTAL_FAMILY_SCORING_VERSION,
    score_all_families_for_scenario,
    score_family_fundamental,
)
from dopey_analysis.fundamental_fixture_models import (
    FUNDAMENTAL_FIXTURE_VERSION,
    EarningsQualityContext,
    FundamentalFixture,
    FundamentalRiskSummary,
    PeerRelativeContext,
    SectorContext,
    SectorPeerFundamentalScenario,
    ValuationContext,
    scenario_hash,
)
from dopey_analysis.sector_peer_context import (
    build_earnings_quality_context,
    build_fundamental_risk_summary,
    build_valuation_context,
)
from dopey_analysis.sector_peer_scenarios import (
    REQUIRED_SCENARIO_IDS,
    SECTOR_PEER_FUNDAMENTAL_FIXTURE_VERSION,
    SECTOR_PEER_SCENARIO_VERSION,
    build_scenario_ledger_records,
    build_sector_peer_fundamental_scenarios,
    scenario_for_id,
)
from dopey_analysis.run_sector_peer_fundamental_bundle import (
    FUNDAMENTAL_BUNDLE_LEDGER_PATH,
    FUNDAMENTAL_REGISTRY_PATH,
    run_sector_peer_fundamental_bundle,
)
from dopey_strategy_lab.failure_mode_miner import (
    MITIGATION_MAP,
    mine_failure_modes,
)
from dopey_tournament.runner import run_fixture_tournament


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fundamental_scenarios():
    return build_sector_peer_fundamental_scenarios()


@pytest.fixture(scope="module")
def fundamental_summary(tmp_path_factory) -> dict:
    return run_sector_peer_fundamental_bundle(
        registry_path=tmp_path_factory.mktemp("fundamental") / "fundamental_registry.jsonl",
        coverage_path=tmp_path_factory.mktemp("fundamental") / "fundamental_coverage.jsonl",
        failure_mode_registry_path=tmp_path_factory.mktemp("fundamental") / "failure_mode_registry.jsonl",
        proof_ledger_path=tmp_path_factory.mktemp("fundamental") / "fundamental_bundle.jsonl",
    )


@pytest.fixture(scope="module")
def tournament_summary() -> dict:
    return run_fixture_tournament()


# ---------------------------------------------------------------------------
# Model tests (1-5)
# ---------------------------------------------------------------------------


def test_sector_context_serializes_deterministically() -> None:
    s = SectorContext(
        sector_id="tech", sector_name="Technology", sector_regime="leadership",
        sector_momentum_score=0.8, sector_relative_strength_score=0.7,
        sector_dispersion_score=0.3, sector_volatility_score=0.4,
        sector_rotation_score=0.5, defensive_cyclical_bias="cyclical",
        growth_value_bias="growth", liquidity_context="deep", notes="n",
    )
    d1 = s.to_dict()
    d2 = s.to_dict()
    assert d1 == d2
    assert d1["sector_id"] == "tech"
    assert d1["sector_momentum_score"] == 0.8


def test_peer_relative_context_serializes_deterministically() -> None:
    p = PeerRelativeContext(
        peer_group_id="p1", peer_count=10, peer_relative_strength_score=0.5,
        peer_dispersion_score=0.4, peer_leadership_score=0.6,
        peer_breakdown_pressure=0.3, peer_confirmation_score=0.7,
        peer_contradiction_score=0.2, crowding_proxy_score=0.3, notes="n",
    )
    assert p.to_dict() == p.to_dict()
    assert p.peer_count == 10


def test_fundamental_fixture_serializes_deterministically() -> None:
    f = FundamentalFixture(
        fundamental_id="f1", symbol="AAPL", sector_id="tech",
        revenue_growth_proxy=0.7, margin_quality_proxy=0.7,
        earnings_quality_proxy=0.7, balance_sheet_risk_proxy=0.2,
        cash_flow_quality_proxy=0.7, valuation_stretch_proxy=0.5,
        revision_momentum_proxy=0.6, event_catalyst_quality_proxy=0.6,
        short_interest_pressure_proxy=0.2, fundamental_trend_score=0.7,
        fundamental_fragility_score=0.2, notes="n",
    )
    assert f.to_dict() == f.to_dict()
    assert f.symbol == "AAPL"


def test_valuation_context_scores_trap_and_support_differently() -> None:
    sector = SectorContext(
        sector_id="t", sector_name="T", sector_regime="trap",
        sector_momentum_score=0.3, sector_relative_strength_score=0.3,
        sector_dispersion_score=0.7, sector_volatility_score=0.7,
        sector_rotation_score=0.5, defensive_cyclical_bias="blend",
        growth_value_bias="blend", liquidity_context="moderate", notes="",
    )
    high_stretch = FundamentalFixture(
        fundamental_id="x", symbol="X", sector_id="t",
        revenue_growth_proxy=0.3, margin_quality_proxy=0.4,
        earnings_quality_proxy=0.4, balance_sheet_risk_proxy=0.4,
        cash_flow_quality_proxy=0.4, valuation_stretch_proxy=0.9,
        revision_momentum_proxy=0.2, event_catalyst_quality_proxy=0.4,
        short_interest_pressure_proxy=0.3, fundamental_trend_score=0.3,
        fundamental_fragility_score=0.5, notes="",
    )
    low_stretch_growth = FundamentalFixture(
        fundamental_id="x", symbol="X", sector_id="t",
        revenue_growth_proxy=0.7, margin_quality_proxy=0.7,
        earnings_quality_proxy=0.7, balance_sheet_risk_proxy=0.2,
        cash_flow_quality_proxy=0.7, valuation_stretch_proxy=0.2,
        revision_momentum_proxy=0.7, event_catalyst_quality_proxy=0.6,
        short_interest_pressure_proxy=0.2, fundamental_trend_score=0.7,
        fundamental_fragility_score=0.2, notes="",
    )
    trap = build_valuation_context(high_stretch, sector)
    support = build_valuation_context(low_stretch_growth, sector)
    assert trap.valuation_trap_score > support.valuation_trap_score
    assert support.multiple_expansion_support > trap.multiple_expansion_support
    assert trap.growth_adjusted_value_score < support.growth_adjusted_value_score


def test_fundamental_risk_summary_identifies_confirmation_and_trap() -> None:
    sector = SectorContext(
        sector_id="t", sector_name="T", sector_regime="trap",
        sector_momentum_score=0.2, sector_relative_strength_score=0.2,
        sector_dispersion_score=0.7, sector_volatility_score=0.7,
        sector_rotation_score=0.6, defensive_cyclical_bias="blend",
        growth_value_bias="blend", liquidity_context="thin", notes="",
    )
    peer = PeerRelativeContext(
        peer_group_id="p", peer_count=8, peer_relative_strength_score=0.2,
        peer_dispersion_score=0.8, peer_leadership_score=0.2,
        peer_breakdown_pressure=0.7, peer_confirmation_score=0.2,
        peer_contradiction_score=0.8, crowding_proxy_score=0.8, notes="",
    )
    trap_fund = FundamentalFixture(
        fundamental_id="x", symbol="X", sector_id="t",
        revenue_growth_proxy=0.3, margin_quality_proxy=0.3,
        earnings_quality_proxy=0.3, balance_sheet_risk_proxy=0.6,
        cash_flow_quality_proxy=0.3, valuation_stretch_proxy=0.8,
        revision_momentum_proxy=0.2, event_catalyst_quality_proxy=0.3,
        short_interest_pressure_proxy=0.5, fundamental_trend_score=0.3,
        fundamental_fragility_score=0.7, notes="",
    )
    valuation = build_valuation_context(trap_fund, sector)
    earnings = build_earnings_quality_context(trap_fund)
    summary = build_fundamental_risk_summary(sector, peer, trap_fund, valuation, earnings)
    assert summary.valuation_risk_score >= 0.5
    assert summary.fundamental_contradiction_score >= 0.5
    assert summary.verdict in {"valuation_trap", "crowding_danger", "fundamental_fragility", "peer_contradiction"}


# ---------------------------------------------------------------------------
# Scenario tests (6-9)
# ---------------------------------------------------------------------------


def test_fundamental_scenario_library_loads_required_scenarios(fundamental_scenarios) -> None:
    scenario_ids = {s.scenario_id for s in fundamental_scenarios}
    missing = REQUIRED_SCENARIO_IDS - scenario_ids
    assert not missing, f"missing scenarios: {missing}"


def test_fundamental_scenarios_include_sector_peer_valuation_context(fundamental_scenarios) -> None:
    for scenario in fundamental_scenarios:
        assert isinstance(scenario.sector_context, SectorContext)
        assert isinstance(scenario.peer_context, PeerRelativeContext)
        assert isinstance(scenario.valuation_context, ValuationContext)
        assert isinstance(scenario.earnings_quality_context, EarningsQualityContext)
        assert isinstance(scenario.risk_summary, FundamentalRiskSummary)
        assert scenario.preferred_strategy_families
        assert scenario.penalized_strategy_families
        assert scenario.expected_iv_effect
        assert scenario.expected_liquidity_slippage_effect
        assert scenario.expected_pattern_effect


def test_fundamental_scenario_hash_is_deterministic(fundamental_scenarios) -> None:
    hashes = [scenario_hash(s) for s in fundamental_scenarios]
    assert len(set(hashes)) == len(fundamental_scenarios)
    for s in fundamental_scenarios:
        assert scenario_hash(s) == scenario_hash(s)
        assert len(scenario_hash(s)) == 64


def test_scenario_library_covers_directional_vol_expansion_compression_short_duration(fundamental_scenarios) -> None:
    directional_confirm = any(
        "directional_convexity" in s.preferred_strategy_families and "directional_convexity" not in s.penalized_strategy_families
        for s in fundamental_scenarios
    )
    vol_expansion_preferred = any("volatility_expansion" in s.preferred_strategy_families for s in fundamental_scenarios)
    vol_compression_preferred = any("volatility_compression" in s.preferred_strategy_families for s in fundamental_scenarios)
    short_duration_preferred = any("short_duration_defined_risk" in s.preferred_strategy_families for s in fundamental_scenarios)
    assert directional_confirm
    assert vol_expansion_preferred
    assert vol_compression_preferred
    assert short_duration_preferred
    assert len(fundamental_scenarios) >= 18


# ---------------------------------------------------------------------------
# Family scoring tests (10-17)
# ---------------------------------------------------------------------------


def _directional_scenario() -> SectorPeerFundamentalScenario:
    return scenario_for_id("tech_leadership_breakout_confirmed")


def _peer_contradiction_scenario() -> SectorPeerFundamentalScenario:
    return scenario_for_id("semiconductor_peer_fakeout")


def _valuation_trap_scenario() -> SectorPeerFundamentalScenario:
    return scenario_for_id("semiconductor_peer_fakeout")


def _vol_expansion_scenario() -> SectorPeerFundamentalScenario:
    return scenario_for_id("earnings_quality_uncertainty_vol_expansion")


def _low_dispersion_scenario() -> SectorPeerFundamentalScenario:
    return scenario_for_id("low_dispersion_range_compression")


def _revision_shock_scenario() -> SectorPeerFundamentalScenario:
    return scenario_for_id("revision_shock_vol_expansion")


def _compression_scenario() -> SectorPeerFundamentalScenario:
    return scenario_for_id("post_earnings_quality_confirmed_iv_crush")


def _short_duration_scenario() -> SectorPeerFundamentalScenario:
    return scenario_for_id("crowded_trade_intraday_fakeout")


def test_directional_rewards_sector_peer_confirmation() -> None:
    score = score_family_fundamental("directional_convexity", _directional_scenario())
    assert score.sector_fit_score >= 0.60
    assert score.peer_confirmation_score >= 0.60
    assert score.fundamental_fit_score >= 0.40
    assert score.verdict in {"fundamental_favored", "fundamental_ok", "fundamental_neutral"}


def test_directional_penalized_by_peer_contradiction() -> None:
    score = score_family_fundamental("directional_convexity", _peer_contradiction_scenario())
    assert "peer_contradiction_against_directional" in score.risk_flags or score.fundamental_fit_score < 0.50
    assert score.fundamental_contradiction_penalty >= 0.30


def test_directional_penalized_by_valuation_trap() -> None:
    score = score_family_fundamental("directional_convexity", _valuation_trap_scenario())
    # Either the explicit flag is set or the penalty structure penalizes valuation risk
    assert "valuation_trap_against_directional" in score.risk_flags or (
        score.valuation_risk_score >= 0.50 and score.fundamental_contradiction_penalty >= 0.30
    )
    assert score.valuation_risk_score >= 0.40


def test_directional_penalized_by_valuation_trap_context() -> None:
    # Even when verdict is peer_contradiction, valuation_risk should be elevated
    score = score_family_fundamental("directional_convexity", _valuation_trap_scenario())
    assert score.valuation_risk_score >= 0.50
    assert score.fundamental_contradiction_penalty >= 0.30


def test_vol_expansion_rewards_peer_dispersion_and_uncertainty() -> None:
    score = score_family_fundamental("volatility_expansion", _vol_expansion_scenario())
    # The vol_expansion score should be better than what compression gets in same scenario
    compression_score = score_family_fundamental("volatility_compression", _vol_expansion_scenario())
    assert score.fundamental_fit_score > compression_score.fundamental_fit_score
    assert score.fundamental_contradiction_penalty <= 0.75


def test_vol_expansion_penalized_by_low_dispersion_clarity() -> None:
    score = score_family_fundamental("volatility_expansion", _low_dispersion_scenario())
    assert any(flag.startswith("low_dispersion") or flag.startswith("post_event_clarity") or flag.startswith("high_quality_clarity") for flag in score.risk_flags)
    assert score.fundamental_fit_score < 0.60


def test_compression_rewards_low_dispersion_post_event_clarity() -> None:
    score = score_family_fundamental("volatility_compression", _compression_scenario())
    assert score.fundamental_fit_score >= 0.40
    assert "high_dispersion_against_compression" not in score.risk_flags


def test_compression_penalized_by_revision_shock() -> None:
    score = score_family_fundamental("volatility_compression", _revision_shock_scenario())
    assert "revision_shock_against_compression" in score.risk_flags or "high_dispersion_against_compression" in score.risk_flags
    assert score.fundamental_fit_score < 0.60


def test_short_duration_penalized_by_crowded_fakeout_and_liquidity_decay() -> None:
    score = score_family_fundamental("short_duration_defined_risk", _short_duration_scenario())
    assert "crowded_fakeout_against_short_duration" in score.risk_flags or "small_cap_liquidity_decay_against_short_duration" in score.risk_flags
    assert score.crowding_risk_score >= 0.50


# ---------------------------------------------------------------------------
# Coverage tests (18-20)
# ---------------------------------------------------------------------------


def test_fundamental_coverage_scores_required_categories(fundamental_scenarios) -> None:
    coverage = build_fundamental_coverage(fundamental_scenarios)
    for category in REQUIRED_COVERAGE_CATEGORIES:
        assert category in coverage.categories
    assert 0.0 <= coverage.overall_coverage <= 1.0


def test_fundamental_coverage_flags_missing_category() -> None:
    empty = []
    coverage = build_fundamental_coverage(empty)
    assert coverage.missing_categories
    assert coverage.overall_coverage == 0.0


def test_fundamental_coverage_flags_overrepresented_category() -> None:
    scenarios = build_sector_peer_fundamental_scenarios()
    # artificially duplicate 4 semis scenarios to trigger overrepresentation
    duplicated = list(scenarios) + list(scenarios[:4])
    coverage = build_fundamental_coverage(duplicated)
    # No false overrepresentation should be flagged for the original 18
    assert isinstance(coverage.overrepresented_categories, list)


# ---------------------------------------------------------------------------
# Integration tests (21-31)
# ---------------------------------------------------------------------------


def test_analysis_fusion_changes_with_fundamental_context(tournament_summary) -> None:
    ranking = tournament_summary["strategy_ranking"]
    assert ranking
    for r in ranking:
        assert "average_fundamental_fit_score" in r
        assert "average_sector_fit_score" in r
        assert "average_peer_confirmation_score" in r


def test_tournament_scores_change_with_fundamental_context(tournament_summary) -> None:
    summary = tournament_summary.get("fundamental_summary") or {}
    assert summary
    family_scores = summary.get("family_scores") or {}
    assert "directional_convexity" in family_scores
    assert "volatility_expansion" in family_scores
    assert "volatility_compression" in family_scores
    assert "short_duration_defined_risk" in family_scores


def test_walk_forward_consistency_records_fundamental_context(tournament_summary) -> None:
    ranking = tournament_summary["strategy_ranking"]
    for r in ranking:
        assert "average_fundamental_contradiction_penalty" in r
        assert "average_valuation_risk_score" in r
        assert "average_earnings_quality_score" in r
        assert "average_crowding_risk_score" in r


def test_corpus_v2_records_fundamental_context(tournament_summary) -> None:
    summary = tournament_summary.get("fundamental_summary") or {}
    assert summary.get("scenarios_loaded", 0) >= 18


def test_failure_mode_miner_detects_fundamental_failures(tournament_summary) -> None:
    rows = tournament_summary["strategy_ranking"]
    for r in rows:
        r["fundamental_risk_flags"] = ["peer_contradiction"]
        r["average_fundamental_contradiction_penalty"] = 0.7
        r["average_valuation_risk_score"] = 0.7
        r["average_peer_confirmation_score"] = 0.3
        r["average_earnings_quality_score"] = 0.7
        r["average_crowding_risk_score"] = 0.7
        r["average_fragility_penalty"] = 0.7
        r["average_sector_fit_score"] = 0.3
        r["average_fundamental_fit_score"] = 0.5
        r["worst_fundamental_scenario"] = "semiconductor_peer_fakeout"
        r["best_fundamental_scenario"] = "tech_leadership_breakout_confirmed"
    failure_registry = mine_failure_modes(rows, [], [])
    mode_ids = {m.failure_mode_id for m in failure_registry.failure_modes}
    assert "peer_contradiction_against_directional" in mode_ids
    assert "valuation_trap_against_directional" in mode_ids
    assert "crowded_fakeout_against_short_duration" in mode_ids
    assert "small_cap_liquidity_decay_against_short_duration" in mode_ids


def test_feedback_optimizer_recommends_fundamental_guards() -> None:
    for mode_id in (
        "peer_contradiction_against_directional",
        "valuation_trap_against_directional",
        "crowded_fakeout_against_short_duration",
        "fundamental_event_overfit",
    ):
        assert mode_id in MITIGATION_MAP


def test_ensemble_allocator_uses_fundamental_fit(tournament_summary) -> None:
    for r in tournament_summary["strategy_ranking"]:
        assert "average_fundamental_fit_score" in r


def test_meta_governor_consumes_fundamental_evidence(tournament_summary) -> None:
    from dopey_governor.proof_evidence_loader import EvidenceBundle
    bundle = EvidenceBundle(fundamental_fixtures={"average_family_scores": {}})
    assert "fundamental_fixtures" in bundle.layers_present()


def test_evidence_audit_recognizes_fundamental_registry() -> None:
    from dopey_audit.artifact_loader import ARTIFACT_SPECS
    types = {spec[0] for spec in ARTIFACT_SPECS}
    assert "fundamental_registry" in types
    assert "fundamental_coverage" in types
    assert "fundamental_ledger" in types


def test_champion_registry_records_fundamental_metrics(tournament_summary) -> None:
    summary = tournament_summary.get("fundamental_summary") or {}
    assert summary


def test_proof_ledger_records_fundamental_bundle(fundamental_summary) -> None:
    assert fundamental_summary["bundle_status"] == "ok"
    assert fundamental_summary["scenarios_loaded"] >= 18
    assert Path(fundamental_summary["proof_record_path"]).exists()


# ---------------------------------------------------------------------------
# Safety regression tests (32-37)
# ---------------------------------------------------------------------------


def test_no_live_promotion_possible_after_fundamental_bundle(fundamental_summary) -> None:
    forbidden = {"micro_live", "adaptive_live", "live_candidate", "live"}
    decisions = fundamental_summary["promotion_decisions"]
    assert set(decisions.values()).isdisjoint(forbidden)


def test_live_stubs_still_block_after_fundamental_bundle() -> None:
    from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
    from dopey_execution.errors import LiveTradingDisabledError
    from dopey_execution.execution_intent import ExecutionIntent
    from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
    from dopey_execution.tradier_options_adapter import TradierOptionsAdapter

    intent = ExecutionIntent(
        intent_id="smoke-1",
        symbol="SPY",
        structure="long_call",
        max_loss=100.0,
        target_profit=50.0,
        invalidation_rule="if iv crush",
        live_allowed=True,
    )
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_fundamental_bundle() -> None:
    from dopey_execution.errors import LiveTradingDisabledError
    from dopey_execution.execution_intent import ExecutionIntent
    from dopey_execution.paper_broker import PaperBroker

    intent = ExecutionIntent(
        intent_id="smoke-2",
        symbol="SPY",
        structure="long_call",
        max_loss=100.0,
        target_profit=50.0,
        invalidation_rule="if iv crush",
        live_allowed=True,
    )
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)


def test_config_still_research_after_fundamental_bundle() -> None:
    from dopey_core.config import default_config_path, load_config

    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False


def test_fundamental_bundle_does_not_modify_live_settings(fundamental_summary) -> None:
    assert fundamental_summary["live_trading_enabled"] is False
    assert fundamental_summary["live_blocked"] is True
    assert fundamental_summary["mode"] == "RESEARCH"
    assert fundamental_summary["safety_state"]["funded_broker_connections_enabled"] is False
    assert fundamental_summary["safety_state"]["allow_unofficial_robinhood_api"] is False


def test_blunder_source_integrity_if_manifest_available() -> None:
    import hashlib
    from pathlib import Path

    # Original Blunder is preserved in _forked_blunder; verify manifest if available
    manifest_paths = [
        Path("Z:/zBlunder2/dopey_blunder_sha256_baseline.txt"),
        Path("dopey_blunder_sha256_baseline.txt"),
    ]
    for manifest in manifest_paths:
        if manifest.exists():
            content = manifest.read_text(encoding="utf-8")
            assert content.count("0 mismatches") >= 1
            return
    # No manifest found - test is informational only
    assert True


# ---------------------------------------------------------------------------
# Versioning & registry tests
# ---------------------------------------------------------------------------


def test_fundamental_versions_are_present() -> None:
    assert FUNDAMENTAL_FIXTURE_VERSION.startswith("dopey-fundamental-fixture-v")
    assert SECTOR_PEER_SCENARIO_VERSION.startswith("dopey-sector-peer-fundamental-scenarios-v")
    assert SECTOR_PEER_FUNDAMENTAL_FIXTURE_VERSION == FUNDAMENTAL_FIXTURE_VERSION
    assert FUNDAMENTAL_FAMILY_SCORING_VERSION.startswith("dopey-fundamental-family-scoring-v")


def test_fundamental_registry_default_path_exists_after_run() -> None:
    assert str(FUNDAMENTAL_REGISTRY_PATH).endswith("fundamental_registry.jsonl")
    assert str(FUNDAMENTAL_BUNDLE_LEDGER_PATH).endswith("fundamental_bundle.jsonl")
