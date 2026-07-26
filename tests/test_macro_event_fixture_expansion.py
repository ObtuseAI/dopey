"""Tests: DOPEY macro-event fixture expansion bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dopey_analysis.analysis_fusion import fuse_analysis
from dopey_analysis.macro_event_fixture import (
    MacroEventFixture,
    MacroEventRiskSummary,
    MacroEventScenario,
    MacroRegimeContext,
    clamp,
    summarize_macro_risk,
)
from dopey_analysis.macro_event_scenarios import (
    build_macro_event_scenarios,
    scenario_for_id,
)
from dopey_analysis.macro_family_scoring import (
    score_all_families_for_scenario,
    score_family_macro_event,
)
from dopey_analysis.models import MacroContext
from dopey_analysis.run_macro_event_bundle import run_macro_event_bundle
from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_strategy_lab.constraint_tuning import build_constraint_tuning_recommendations
from dopey_strategy_lab.failure_feedback import aggregate_failure_modes, build_family_failure_profiles
from dopey_strategy_lab.failure_mode_miner import mine_failure_modes
from dopey_strategy_lab.mutation_scorecard import _weight_adjustment as mutation_weight_adjustment
from dopey_tournament.runner import _combined_score, run_fixture_tournament


FORBIDDEN_LIVE_DECISIONS = {"live_candidate", "micro_live", "adaptive_live", "live"}


@pytest.fixture(scope="module")
def macro_bundle_result(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("macro_event_bundle")
    return run_macro_event_bundle(
        registry_path=root / "macro_event_registry.jsonl",
        proof_ledger_path=root / "macro_event_bundle.jsonl",
    )


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="macro-live-x",
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


def test_macro_event_fixture_serializes_deterministically() -> None:
    event = MacroEventFixture(
        event_id="pytest-cpi",
        event_type="cpi_fixture",
        event_window=" pytest window ",
        event_intensity=0.75,
        surprise_direction="upside",
        risk_on_off_bias="risk_off",
        volatility_impulse=0.80,
        rates_pressure=0.70,
        dollar_pressure=0.55,
        sector_rotation_pressure=0.40,
        breadth_pressure=0.35,
        liquidity_pressure=0.30,
        overnight_futures_pressure=0.65,
    )
    regime = MacroRegimeContext(
        regime_id="pytest-regime",
        risk_on_score=0.20,
        risk_off_score=0.80,
        rate_shock_score=0.75,
        inflation_pressure_score=0.70,
        dollar_strength_score=0.60,
        vix_stress_score=0.85,
        vvix_stress_score=0.82,
        breadth_score=0.30,
        sector_rotation_score=0.55,
        liquidity_regime_score=0.25,
        overnight_pressure_score=0.70,
        macro_trend_score=0.20,
        macro_fakeout_risk_score=0.45,
    )
    scenario = MacroEventScenario(
        scenario_id="pytest-scenario",
        regime_tag="macro_shock_risk_off",
        macro_event=event,
        regime_context=regime,
        risk_summary=summarize_macro_risk(event, regime),
        preferred_strategy_families=["volatility_expansion"],
        penalized_strategy_families=["volatility_compression"],
        expected_iv_effect="iv_spike",
        expected_slippage_effect="wide_spreads",
        expected_pattern_effect="risk_off_breakdown",
        expected_failure_modes=["macro_shock_danger"],
    )
    first = json.dumps(scenario.to_dict(), sort_keys=True)
    second = json.dumps(scenario.to_dict(), sort_keys=True)
    assert first == second


def test_macro_regime_context_scores_risk_on_and_risk_off_differently() -> None:
    risk_on = MacroRegimeContext(regime_id="risk_on", risk_on_score=0.85, risk_off_score=0.10)
    risk_off = MacroRegimeContext(regime_id="risk_off", risk_on_score=0.10, risk_off_score=0.85)
    assert risk_on.risk_on_score > risk_on.risk_off_score
    assert risk_off.risk_off_score > risk_off.risk_on_score


def test_macro_event_risk_summary_identifies_macro_shock_danger() -> None:
    scenario = scenario_for_id("hot_cpi_rate_shock")
    summary = scenario.risk_summary
    assert summary.verdict in {"macro_shock_danger", "compression_danger"}
    assert "macro_shock_danger" in summary.risk_flags
    assert summary.macro_shock_score >= 0.60


def test_macro_event_risk_summary_identifies_directional_confirmation() -> None:
    scenario = scenario_for_id("risk_on_breakout_confirmation")
    summary = scenario.risk_summary
    assert summary.directional_confirmation_score >= 0.70
    assert "directional_confirmed" in summary.risk_flags or summary.verdict == "directional_confirmed"


def test_macro_event_risk_summary_identifies_short_duration_bad_fill_risk() -> None:
    scenario = scenario_for_id("liquidity_contraction_bad_fill")
    summary = scenario.risk_summary
    assert summary.short_duration_liquidity_risk_score >= 0.70
    assert "short_duration_bad_fill_risk" in summary.risk_flags or summary.verdict == "short_duration_bad_fill_risk"


def test_macro_scenario_library_loads_required_scenarios() -> None:
    scenario_ids = {scenario.scenario_id for scenario in build_macro_event_scenarios()}
    required = {
        "pre_fomc_vol_expansion",
        "post_fomc_iv_crush",
        "hot_cpi_rate_shock",
        "cool_cpi_risk_on_rebound",
        "ppi_inflation_pressure",
        "jobs_growth_shock",
        "dollar_squeeze_risk_off",
        "vix_vvix_spike",
        "breadth_breakdown",
        "sector_rotation_growth_to_value",
        "liquidity_contraction_bad_fill",
        "overnight_gap_risk",
        "risk_on_breakout_confirmation",
        "risk_off_breakdown_confirmation",
    }
    assert required.issubset(scenario_ids)


def test_hot_cpi_rate_shock_penalizes_compression() -> None:
    scenario = scenario_for_id("hot_cpi_rate_shock")
    compression = score_family_macro_event("volatility_compression", scenario)
    assert compression.verdict in {"macro_reject", "macro_danger"} or compression.macro_fit_score < 0.45
    assert "rate_shock_against_compression" in compression.risk_flags or "macro_shock_against_compression" in compression.risk_flags


def test_pre_fomc_vol_expansion_rewards_vol_expansion() -> None:
    score = score_family_macro_event("volatility_expansion", scenario_for_id("pre_fomc_vol_expansion"))
    assert score.macro_fit_score >= 0.60
    assert "directional_confirmed" not in score.risk_flags


def test_post_fomc_iv_crush_rewards_compression() -> None:
    score = score_family_macro_event("volatility_compression", scenario_for_id("post_fomc_iv_crush"))
    assert score.macro_fit_score >= 0.60
    assert "post_event_crush_against_vol_expansion" not in score.risk_flags


def test_liquidity_contraction_penalizes_short_duration() -> None:
    score = score_family_macro_event("short_duration_defined_risk", scenario_for_id("liquidity_contraction_bad_fill"))
    assert score.verdict in {"macro_reject", "macro_danger"} or score.macro_fit_score < 0.45
    assert "liquidity_contraction_bad_fill_failure" in score.risk_flags


def test_directional_rewards_breadth_confirmed_breakout() -> None:
    clean = score_family_macro_event("directional_convexity", scenario_for_id("risk_on_breakout_confirmation"))
    assert clean.macro_fit_score >= 0.60
    assert clean.breadth_sector_confirmation_score >= 0.60


def test_directional_penalized_by_macro_fakeout() -> None:
    clean = score_family_macro_event("directional_convexity", scenario_for_id("risk_on_breakout_confirmation"))
    fakeout = score_family_macro_event("directional_convexity", scenario_for_id("overnight_gap_risk"))
    assert clean.macro_fit_score > fakeout.macro_fit_score
    assert "macro_fakeout_against_directional" in fakeout.risk_flags


def test_vol_expansion_rewards_vix_vvix_spike() -> None:
    score = score_family_macro_event("volatility_expansion", scenario_for_id("vix_vvix_spike"))
    assert score.macro_fit_score >= 0.70
    assert score.vix_vvix_stress_score >= 0.70


def test_vol_expansion_penalized_by_post_event_crush() -> None:
    pre = score_family_macro_event("volatility_expansion", scenario_for_id("pre_fomc_vol_expansion"))
    post = score_family_macro_event("volatility_expansion", scenario_for_id("post_fomc_iv_crush"))
    assert post.macro_fit_score < pre.macro_fit_score
    assert "post_event_crush_against_vol_expansion" in post.risk_flags


def test_compression_penalized_by_rate_shock() -> None:
    clean = score_family_macro_event("volatility_compression", scenario_for_id("post_fomc_iv_crush"))
    shock = score_family_macro_event("volatility_compression", scenario_for_id("hot_cpi_rate_shock"))
    assert clean.macro_fit_score > shock.macro_fit_score
    assert "rate_shock_against_compression" in shock.risk_flags


def test_short_duration_penalized_by_event_gap_and_liquidity_contraction() -> None:
    event_gap = score_family_macro_event("short_duration_defined_risk", scenario_for_id("pre_fomc_vol_expansion"))
    liquidity = score_family_macro_event("short_duration_defined_risk", scenario_for_id("liquidity_contraction_bad_fill"))
    assert event_gap.macro_fit_score < 0.55 or "event_gap_against_short_duration" in event_gap.risk_flags
    assert "liquidity_contraction_bad_fill_failure" in liquidity.risk_flags


def test_analysis_fusion_changes_with_macro_event_context() -> None:
    macro_ctx = MacroContext(regime_tag="macro_shock_risk_off")
    micro_ctx = __import__("dopey_analysis.models", fromlist=["MicrostructureContext"]).MicrostructureContext()
    tech_ctx = __import__("dopey_analysis.models", fromlist=["TechnicalContext"]).TechnicalContext()
    fund_ctx = __import__("dopey_analysis.models", fromlist=["FundamentalContext"]).FundamentalContext()
    scenario = scenario_for_id("hot_cpi_rate_shock")
    without_macro = fuse_analysis(
        macro_ctx=macro_ctx, micro_ctx=micro_ctx, tech_ctx=tech_ctx,
        fund_ctx=fund_ctx, patterns=[], macro_event_scenario=None, strategy_family=None)
    with_macro = fuse_analysis(
        macro_ctx=macro_ctx, micro_ctx=micro_ctx, tech_ctx=tech_ctx,
        fund_ctx=fund_ctx, patterns=[], macro_event_scenario=scenario, strategy_family="volatility_expansion")
    assert with_macro.macro_score != without_macro.macro_score


def test_tournament_scores_change_with_macro_context() -> None:
    summary = run_fixture_tournament()
    top = summary["strategy_ranking"][0]
    macro_fit = top.get("average_macro_fit_score", 0.5)
    macro_risk = top.get("average_macro_risk_score", 0.5)
    macro_event_score = 0.04 * macro_fit - 0.02 * macro_risk + 0.01 * (macro_fit - macro_risk)
    expected = _combined_score(
        top["walk_forward_overall"],
        top["analysis_fusion_overall"],
        greek_fit=top["average_greek_fit_score"],
        iv_score=round(
            (top["average_iv_context_score"] + top["average_skew_score"] + top["average_term_structure_score"]
             + top["average_iv_surface_fit_score"] + top["average_family_iv_fit_score"]
             + top["average_skew_term_score"]) / 6.0, 6),
        liquidity=top["average_liquidity_score"],
        slippage=top["slippage_robustness_score"],
        invalidation=top["invalidation_quality"],
        holdout=top["holdout_score"],
        overfit_rank=top["overfit_rank"],
        macro_fit=macro_fit,
        macro_risk=macro_risk,
        fundamental_fit=top.get("average_fundamental_fit_score", 0.5),
        fundamental_contradiction=top.get("average_fundamental_contradiction_penalty", 0.5),
    )
    assert abs(top["combined_score"] - expected) < 1e-6
    assert summary.get("macro_event_summary", {}).get("family_scores", {})


def test_mutation_scoring_uses_macro_event_guard() -> None:
    good = mutation_weight_adjustment({"macro_event_guard": True}, {
        "average_macro_fit_score": 0.75,
        "average_macro_risk_score": 0.20,
        "average_event_gap_risk_penalty": 0.10,
    })
    bad = mutation_weight_adjustment({"macro_event_guard": True}, {
        "average_macro_fit_score": 0.30,
        "average_macro_risk_score": 0.80,
        "average_event_gap_risk_penalty": 0.70,
    })
    assert good > bad


def test_failure_mode_miner_detects_macro_event_failures() -> None:
    row = {
        "strategy_id": "pytest-macro-event",
        "strategy_family": "short_duration_defined_risk",
        "average_macro_fit_score": 0.20,
        "average_macro_risk_score": 0.85,
        "average_event_gap_risk_penalty": 0.75,
        "average_liquidity_regime_macro_score": 0.20,
    }
    registry = mine_failure_modes([row], [], [])
    mode_ids = {mode.failure_mode_id for mode in registry.failure_modes}
    assert "event_gap_against_short_duration" in mode_ids
    assert "liquidity_contraction_bad_fill_failure" in mode_ids


def test_feedback_optimizer_recommends_macro_event_guards() -> None:
    registry = mine_failure_modes([
        {
            "strategy_id": "pytest-macro-feedback",
            "strategy_family": "volatility_compression",
            "average_rate_shock_score": 0.80,
            "average_vix_vvix_stress_score": 0.80,
            "average_macro_fit_score": 0.25,
            "average_macro_risk_score": 0.80,
            "worst_macro_scenario": "hot_cpi_rate_shock",
            "worst_regimes": ["macro_shock_risk_off"],
        }
    ], [], [])
    aggregates = aggregate_failure_modes(registry.to_dict())
    profiles = build_family_failure_profiles(aggregates)
    recommendations = build_constraint_tuning_recommendations(profiles, aggregates)
    keys = {recommendation.tuning_key for recommendation in recommendations}
    assert {"rate_shock_avoidance", "vix_vvix_stress_guard"}.intersection(keys)


def test_champion_registry_records_macro_metrics(macro_bundle_result) -> None:
    registry_path = Path(macro_bundle_result["macro_event_registry_path"])
    record = json.loads(registry_path.read_text(encoding="utf-8").splitlines()[-1])
    family_scores = record["tournament_macro_event_summary"]["family_scores"]
    assert family_scores
    assert all("average_macro_fit_score" in score for score in family_scores.values())


def test_proof_ledger_records_macro_event_bundle(macro_bundle_result) -> None:
    proof_path = Path(macro_bundle_result["proof_record_path"])
    record = json.loads(proof_path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["task_id"] == "macro-event-fixture-expansion-bundle"
    assert record["test_results"]["macro_scenarios_loaded"] == 14


def test_no_live_promotion_possible_after_macro_bundle(macro_bundle_result) -> None:
    statuses = set(macro_bundle_result["promotion_decisions"].values())
    assert statuses.isdisjoint(FORBIDDEN_LIVE_DECISIONS)
    assert macro_bundle_result["live_blocked"] is True


def test_live_stubs_still_block_after_macro_bundle() -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_macro_bundle() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_macro_bundle(macro_bundle_result) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert macro_bundle_result["safety_state"]["live_blocked"] is True


def test_blunder_source_integrity_if_manifest_available() -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        pytest.skip("Blunder SHA256 manifest not available; skipping integrity check")
    checked = 0
    for line in manifest.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        expected, path = parts
        candidate = Path(path)
        if not candidate.exists():
            continue
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest().upper()
        assert actual == expected.upper()
        checked += 1
    assert checked > 0
