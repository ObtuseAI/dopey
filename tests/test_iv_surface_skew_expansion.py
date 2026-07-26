"""Tests: DOPEY IV surface/skew/term expansion bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_options.iv_family_scoring import score_family_iv_surface
from dopey_options.iv_surface_expansion import IVSurfacePoint, build_surface_grid, summarize_iv_surface_risk
from dopey_options.iv_surface_scenarios import build_iv_surface_scenarios, scenario_for_id
from dopey_options.run_iv_surface_skew_bundle import run_iv_surface_skew_bundle
from dopey_options.skew_term_structure import (
    build_skew_profile,
    build_term_structure_profile,
    score_skew_term_for_family,
)
from dopey_strategy_lab.constraint_tuning import build_constraint_tuning_recommendations
from dopey_strategy_lab.failure_feedback import aggregate_failure_modes, build_family_failure_profiles
from dopey_strategy_lab.failure_mode_miner import mine_failure_modes
from dopey_strategy_lab.mutation_scorecard import _weight_adjustment
from dopey_tournament.runner import _combined_score, run_fixture_tournament


FORBIDDEN_LIVE_DECISIONS = {"live_candidate", "micro_live", "adaptive_live", "live"}


@pytest.fixture(scope="module")
def iv_bundle_result(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("iv_surface_bundle")
    return run_iv_surface_skew_bundle(
        registry_path=root / "iv_surface_registry.jsonl",
        proof_ledger_path=root / "iv_surface_skew_bundle.jsonl",
    )


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="iv-surface-live-x",
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


def test_iv_surface_point_serializes_deterministically() -> None:
    point = IVSurfacePoint("front", "atm", "call", 0.25, 0.0, 0.50, "pytest point")
    first = json.dumps(point.to_dict(), sort_keys=True)
    second = json.dumps(point.to_dict(), sort_keys=True)
    assert first == second


def test_iv_surface_grid_loads_required_scenarios() -> None:
    scenario_ids = {scenario.scenario_id for scenario in build_iv_surface_scenarios()}
    assert {
        "pre_event_vol_expansion",
        "post_event_iv_crush",
        "macro_shock_backwardation",
        "range_bound_compression",
        "bullish_call_skew_breakout",
        "bearish_put_skew_breakdown",
        "premium_overpayment_trap",
        "stable_low_iv_breakout",
        "unstable_surface_fakeout",
        "low_liquidity_wide_skew",
        "front_expiry_event_bump",
        "normal_contango_chop",
    }.issubset(scenario_ids)


def test_iv_surface_risk_summary_identifies_iv_crush_danger() -> None:
    scenario = scenario_for_id("post_event_iv_crush")
    risk = summarize_iv_surface_risk(scenario, build_surface_grid(scenario, "SPY_FIXTURE"))
    assert risk.verdict == "iv_crush_danger"
    assert "iv_crush_danger" in risk.risk_flags


def test_iv_surface_risk_summary_identifies_expansion_setup() -> None:
    scenario = scenario_for_id("pre_event_vol_expansion")
    risk = summarize_iv_surface_risk(scenario, build_surface_grid(scenario, "SPY_FIXTURE"))
    assert risk.verdict in {"excellent_expansion_setup", "good_expansion_setup"}
    assert "iv_expansion_opportunity" in risk.risk_flags


def test_iv_surface_risk_summary_identifies_premium_overpayment_trap() -> None:
    scenario = scenario_for_id("premium_overpayment_trap")
    risk = summarize_iv_surface_risk(scenario, build_surface_grid(scenario, "SPY_FIXTURE"))
    assert risk.verdict == "premium_overpayment_trap"
    assert risk.premium_overpayment_score >= 0.78


def test_skew_profile_scores_put_and_call_skew_differently() -> None:
    call_skew = build_skew_profile(scenario_for_id("bullish_call_skew_breakout"))
    put_skew = build_skew_profile(scenario_for_id("bearish_put_skew_breakdown"))
    assert call_skew.skew_direction == "call_skew"
    assert put_skew.skew_direction == "put_skew"
    assert call_skew.call_skew_score > call_skew.put_skew_score
    assert put_skew.put_skew_score > put_skew.call_skew_score


def test_term_structure_profile_identifies_front_event_bump() -> None:
    term = build_term_structure_profile(scenario_for_id("front_expiry_event_bump"))
    assert term.term_state == "front_event_bump"
    assert term.event_bump_score >= 0.90


def test_term_structure_profile_identifies_backwardation() -> None:
    term = build_term_structure_profile(scenario_for_id("macro_shock_backwardation"))
    assert term.term_state == "backwardation"
    assert term.backwardation_pressure == 1.0


def test_skew_term_score_affects_family_fit() -> None:
    scenario = scenario_for_id("front_expiry_event_bump")
    skew = build_skew_profile(scenario)
    term = build_term_structure_profile(scenario)
    expansion = score_skew_term_for_family("volatility_expansion", scenario, skew, term)
    compression = score_skew_term_for_family("volatility_compression", scenario, skew, term)
    assert expansion.combined_score > compression.combined_score


def test_directional_penalized_by_premium_overpayment_trap() -> None:
    clean = score_family_iv_surface("directional_convexity", scenario_for_id("stable_low_iv_breakout"))
    trap = score_family_iv_surface("directional_convexity", scenario_for_id("premium_overpayment_trap"))
    assert clean.family_iv_fit_score > trap.family_iv_fit_score
    assert trap.verdict == "premium_overpayment_trap"


def test_vol_expansion_rewards_pre_event_expansion() -> None:
    score = score_family_iv_surface("volatility_expansion", scenario_for_id("pre_event_vol_expansion"))
    assert score.family_iv_fit_score >= 0.70
    assert score.verdict in {"good_iv_fit", "excellent_iv_fit"}


def test_vol_expansion_penalized_by_post_event_iv_crush() -> None:
    pre_event = score_family_iv_surface("volatility_expansion", scenario_for_id("pre_event_vol_expansion"))
    post_event = score_family_iv_surface("volatility_expansion", scenario_for_id("post_event_iv_crush"))
    assert post_event.family_iv_fit_score < pre_event.family_iv_fit_score
    assert "iv_crush_after_vol_expansion_risk" in post_event.risk_flags


def test_compression_rewards_post_event_iv_crush() -> None:
    score = score_family_iv_surface("volatility_compression", scenario_for_id("post_event_iv_crush"))
    assert score.family_iv_fit_score >= 0.80
    assert score.verdict == "excellent_iv_fit"


def test_compression_penalized_by_macro_backwardation() -> None:
    clean = score_family_iv_surface("volatility_compression", scenario_for_id("range_bound_compression"))
    shock = score_family_iv_surface("volatility_compression", scenario_for_id("macro_shock_backwardation"))
    assert clean.family_iv_fit_score > shock.family_iv_fit_score
    assert "backwardation_against_compression" in shock.risk_flags


def test_short_duration_penalized_by_front_iv_instability() -> None:
    clean = score_family_iv_surface("short_duration_defined_risk", scenario_for_id("normal_contango_chop"))
    event = score_family_iv_surface("short_duration_defined_risk", scenario_for_id("front_expiry_event_bump"))
    assert clean.family_iv_fit_score > event.family_iv_fit_score
    assert "short_duration_front_iv_instability" in event.risk_flags


def test_tournament_scores_change_with_iv_surface_context() -> None:
    summary = run_fixture_tournament()
    top = summary["strategy_ranking"][0]
    old_iv_score = round((
        top["average_iv_context_score"]
        + top["average_skew_score"]
        + top["average_term_structure_score"]
    ) / 3.0, 6)
    new_iv_score = round((
        top["average_iv_context_score"]
        + top["average_skew_score"]
        + top["average_term_structure_score"]
        + top["average_iv_surface_fit_score"]
        + top["average_family_iv_fit_score"]
        + top["average_skew_term_score"]
    ) / 6.0, 6)
    assert new_iv_score != old_iv_score
    expected = _combined_score(
        top["walk_forward_overall"],
        top["analysis_fusion_overall"],
        greek_fit=top["average_greek_fit_score"],
        iv_score=new_iv_score,
        liquidity=top["average_liquidity_score"],
        slippage=top["slippage_robustness_score"],
        invalidation=top["invalidation_quality"],
        holdout=top["holdout_score"],
        overfit_rank=top["overfit_rank"],
        macro_fit=top.get("average_macro_fit_score", 0.5),
        macro_risk=top.get("average_macro_risk_score", 0.5),
        fundamental_fit=top.get("average_fundamental_fit_score", 0.5),
        fundamental_contradiction=top.get("average_fundamental_contradiction_penalty", 0.5),
    )
    assert abs(top["combined_score"] - expected) < 1e-6


def test_mutation_scoring_uses_iv_surface_guard() -> None:
    params = {"iv_regime_preference": "event_vol_expansion"}
    good = _weight_adjustment(params, {
        "average_family_iv_fit_score": 0.70,
        "average_premium_overpayment_score": 0.20,
        "average_iv_crush_score": 0.20,
    })
    bad = _weight_adjustment(params, {
        "average_family_iv_fit_score": 0.30,
        "average_premium_overpayment_score": 0.80,
        "average_iv_crush_score": 0.80,
    })
    assert good > bad


def test_failure_mode_miner_detects_premium_overpayment_trap() -> None:
    row = {
        "strategy_id": "pytest-premium-trap",
        "strategy_family": "directional_convexity",
        "average_premium_overpayment_score": 0.80,
    }
    registry = mine_failure_modes([row], [], [])
    mode_ids = {mode.failure_mode_id for mode in registry.failure_modes}
    assert "premium_overpayment_trap_failure" in mode_ids


def test_feedback_optimizer_recommends_iv_surface_guards() -> None:
    registry = mine_failure_modes([
        {
            "strategy_id": "pytest-premium-trap",
            "strategy_family": "directional_convexity",
            "average_premium_overpayment_score": 0.80,
        }
    ], [], [])
    aggregates = aggregate_failure_modes(registry.to_dict())
    profiles = build_family_failure_profiles(aggregates)
    recommendations = build_constraint_tuning_recommendations(profiles, aggregates)
    keys = {recommendation.tuning_key for recommendation in recommendations}
    assert {"premium_overpayment_penalty", "iv_entry_value_guard"}.issubset(keys)


def test_champion_registry_records_iv_surface_metrics(iv_bundle_result) -> None:
    registry_path = Path(iv_bundle_result["iv_surface_registry_path"])
    record = json.loads(registry_path.read_text(encoding="utf-8").splitlines()[-1])
    family_scores = record["tournament_iv_surface_expansion_summary"]["family_scores"]
    assert family_scores
    assert all("average_family_iv_fit_score" in score for score in family_scores.values())


def test_proof_ledger_records_iv_surface_bundle(iv_bundle_result) -> None:
    proof_path = Path(iv_bundle_result["proof_record_path"])
    record = json.loads(proof_path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["task_id"] == "iv-surface-skew-expansion-bundle"
    assert record["test_results"]["surface_scenarios_loaded"] == 12


def test_no_live_promotion_possible_after_iv_surface_bundle(iv_bundle_result) -> None:
    statuses = set(iv_bundle_result["promotion_decisions"].values())
    assert statuses.isdisjoint(FORBIDDEN_LIVE_DECISIONS)
    assert iv_bundle_result["live_blocked"] is True


def test_live_stubs_still_block_after_iv_surface_bundle() -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_iv_surface_bundle() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_iv_surface_bundle(iv_bundle_result) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert iv_bundle_result["safety_state"]["live_blocked"] is True


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
