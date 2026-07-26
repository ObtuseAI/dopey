"""Tests: DOPEY deterministic Greeks/IV validation upgrade.

All tests are offline, fixture-only, paper-only, and live-blocked.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from dopey_core.config import default_config_path, load_config
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_options.greeks_validation import (
    GreekVector,
    attribute_greek_outcome,
    evaluate_greek_risk,
    iv_surface_family_score,
    summarize_greek_exposure,
)
from dopey_options.iv_surface_fixture import (
    IVContext,
    IVSurfaceSummary,
    SkewSummary,
    TermStructureSummary,
    build_iv_context,
)
from dopey_tournament.aggression_tournament import ALLOWED_TARGETS, FORBIDDEN_LIVE_TARGETS
from dopey_tournament.runner import run_fixture_tournament
from dopey_walk_forward.window_model import WALK_FORWARD_DIR, load_walk_forward_windows


def _tmp_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "tournament_ledger.jsonl", tmp_path / "champion_registry.jsonl"


def _leg(
    side: str,
    delta: float,
    gamma: float,
    theta: float,
    vega: float,
    option_type: str,
    ratio: float,
) -> dict[str, Any]:
    return {
        "side": side,
        "symbol": f"T-{side}-{option_type}-{delta}-{gamma}-{theta}-{vega}",
        "strike": 100.0,
        "expiry": "2024-01-19",
        "option_type": option_type,
        "ratio": ratio,
        "delta": delta,
        "gamma": gamma,
        "theta": theta,
        "vega": vega,
        "rho": 0.01,
        "iv": 0.24,
    }


def _iv_context(crush: float, expansion: float, regime: str) -> IVContext:
    return IVContext(
        iv_rank=0.60,
        iv_percentile=0.62,
        realized_volatility=0.20,
        implied_vs_realized_gap=0.08,
        iv_regime=regime,
        iv_event_risk=0.60,
        iv_crush_risk=crush,
        iv_expansion_potential=expansion,
    )


def _surface(stability: float, opportunity: float) -> IVSurfaceSummary:
    return IVSurfaceSummary(
        surface_shape="flat",
        atm_iv=0.24,
        otm_call_iv=0.25,
        otm_put_iv=0.25,
        wings_elevated=False,
        surface_stability_score=stability,
        surface_opportunity_score=opportunity,
    )


def _skew(risk: float, opportunity: float) -> SkewSummary:
    return SkewSummary(
        put_skew_score=0.50,
        call_skew_score=0.50,
        skew_steepness=risk / 10.0,
        skew_direction="balanced",
        skew_opportunity_score=opportunity,
        skew_risk_score=risk,
    )


def _term(event_bump: float, risk: float, state: str) -> TermStructureSummary:
    return TermStructureSummary(
        front_iv=0.26,
        back_iv=0.24,
        term_slope=-0.02 if state == "backwardation" else 0.0,
        contango_backwardation_state=state,
        event_bump_score=event_bump,
        term_opportunity_score=event_bump,
        term_risk_score=risk,
    )


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="greeks-live-x",
        symbol="SPY_FIXTURE",
        structure="vertical",
        legs=[
            {"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19",
             "option_type": "call", "mid": 1.0},
            {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19",
             "option_type": "call", "mid": 0.5},
        ],
        quantity=1,
        defined_risk=True,
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=5.0,
        target_profit=5.0,
    )


def test_greek_vector_serializes_deterministically() -> None:
    vector = GreekVector(0.42, 0.03, -0.08, 0.21, 0.01, 0.24, "fixture", "unit")
    first = json.dumps(vector.to_dict(), sort_keys=True)
    second = json.dumps(GreekVector.from_dict(vector.to_dict()).to_dict(), sort_keys=True)
    assert first == second
    assert vector.to_dict()["delta"] == 0.42


def test_greek_exposure_summary_netting() -> None:
    legs = [
        _leg("buy", 0.60, 0.020, -0.10, 0.30, "call", 1.0),
        _leg("sell", 0.25, 0.010, -0.05, 0.10, "call", 1.0),
    ]
    summary = summarize_greek_exposure(legs)
    assert summary.net_delta == 0.35
    assert summary.net_gamma == 0.01
    assert summary.net_theta == -0.05
    assert summary.net_vega == 0.20


def test_directional_profile_rewards_correct_delta_positive_gamma() -> None:
    exposure = summarize_greek_exposure([
        _leg("buy", 0.55, 0.030, -0.08, 0.20, "call", 1.0),
    ])
    verdict = evaluate_greek_risk(
        "s1", "directional_convexity", exposure,
        _iv_context(0.20, 0.70, "event_expansion"), _surface(0.90, 0.40),
        _skew(0.10, 0.20), _term(0.50, 0.10, "backwardation"),
        "bullish_breakout", 0.90,
    )
    assert verdict.greek_fit_score > 0.70
    assert "wrong_sign_delta" not in verdict.risk_flags


def test_directional_profile_penalizes_wrong_sign_delta() -> None:
    exposure = summarize_greek_exposure([
        _leg("buy", -0.55, 0.030, -0.08, 0.20, "put", 1.0),
    ])
    verdict = evaluate_greek_risk(
        "s1", "directional_convexity", exposure,
        _iv_context(0.20, 0.70, "event_expansion"), _surface(0.90, 0.40),
        _skew(0.10, 0.20), _term(0.50, 0.10, "backwardation"),
        "bullish_breakout", 0.90,
    )
    assert verdict.greek_fit_score < 0.55
    assert "wrong_sign_delta" in verdict.risk_flags
    assert verdict.verdict in {"poor_fit", "reject"}


def test_volatility_expansion_profile_rewards_positive_vega_gamma_in_expansion_regime() -> None:
    exposure = summarize_greek_exposure([
        _leg("buy", 0.20, 0.035, -0.09, 0.35, "call", 1.0),
        _leg("buy", -0.18, 0.035, -0.09, 0.35, "put", 1.0),
    ])
    verdict = evaluate_greek_risk(
        "s2", "volatility_expansion", exposure,
        _iv_context(0.15, 0.90, "event_expansion"), _surface(0.70, 0.80),
        _skew(0.20, 0.60), _term(0.85, 0.20, "backwardation"),
        "event_vol_expansion", 0.85,
    )
    assert verdict.greek_fit_score > 0.75
    assert verdict.vega_fit_score > 0.70


def test_volatility_expansion_penalized_by_iv_crush_risk() -> None:
    exposure = summarize_greek_exposure([
        _leg("buy", 0.10, 0.030, -0.10, 0.60, "call", 1.0),
        _leg("buy", -0.10, 0.030, -0.10, 0.60, "put", 1.0),
    ])
    expansion = evaluate_greek_risk(
        "s2", "volatility_expansion", exposure,
        _iv_context(0.10, 0.90, "event_expansion"), _surface(0.70, 0.80),
        _skew(0.20, 0.60), _term(0.85, 0.20, "backwardation"),
        "event_vol_expansion", 0.85,
    )
    crush = evaluate_greek_risk(
        "s2", "volatility_expansion", exposure,
        _iv_context(0.90, 0.10, "post_event_crush"), _surface(0.70, 0.20),
        _skew(0.20, 0.20), _term(0.10, 0.20, "flat"),
        "post_event_iv_crush", 0.85,
    )
    assert crush.greek_fit_score < expansion.greek_fit_score
    assert "iv_crush_risk_against_long_vega" in crush.risk_flags


def test_volatility_compression_rewards_iv_crush_range_context() -> None:
    exposure = summarize_greek_exposure([
        _leg("sell", 0.30, 0.015, -0.08, 0.25, "call", 1.0),
        _leg("sell", -0.30, 0.015, -0.08, 0.25, "put", 1.0),
    ])
    verdict = evaluate_greek_risk(
        "s3", "volatility_compression", exposure,
        _iv_context(0.90, 0.10, "post_event_crush"), _surface(0.95, 0.10),
        _skew(0.05, 0.10), _term(0.00, 0.05, "flat"),
        "post_event_iv_crush", 0.90,
    )
    assert verdict.greek_fit_score > 0.70
    assert verdict.vega_fit_score > 0.70


def test_volatility_compression_penalized_by_macro_shock_expansion_context() -> None:
    exposure = summarize_greek_exposure([
        _leg("sell", 0.30, 0.015, -0.08, 0.25, "call", 1.0),
        _leg("sell", -0.30, 0.015, -0.08, 0.25, "put", 1.0),
    ])
    crush = evaluate_greek_risk(
        "s3", "volatility_compression", exposure,
        _iv_context(0.90, 0.10, "post_event_crush"), _surface(0.95, 0.10),
        _skew(0.05, 0.10), _term(0.00, 0.05, "flat"),
        "post_event_iv_crush", 0.90,
    )
    shock = evaluate_greek_risk(
        "s3", "volatility_compression", exposure,
        _iv_context(0.15, 0.90, "macro_shock"), _surface(0.70, 0.70),
        _skew(0.35, 0.50), _term(0.80, 0.40, "backwardation"),
        "macro_shock_risk_off", 0.90,
    )
    assert shock.greek_fit_score < crush.greek_fit_score
    assert "compression_exposed_to_expansion" in shock.risk_flags


def test_short_duration_penalized_by_theta_gamma_liquidity_combo() -> None:
    exposure = summarize_greek_exposure([
        _leg("buy", 0.40, 0.070, -0.32, 0.20, "call", 1.0),
    ])
    verdict = evaluate_greek_risk(
        "s4", "short_duration_defined_risk", exposure,
        _iv_context(0.20, 0.30, "normal"), _surface(0.80, 0.20),
        _skew(0.40, 0.20), _term(0.10, 0.50, "flat"),
        "high_spread_bad_fill", 0.10,
    )
    assert verdict.theta_fit_score < 0.45
    assert "theta_gamma_liquidity_combo" in verdict.risk_flags


def test_iv_context_scores_event_expansion_and_iv_crush_differently() -> None:
    window = load_walk_forward_windows()[0]
    event = build_iv_context(
        window.option_chain, "event_vol_expansion", window.underlying_snapshot,
        {"iv_effect": 0.50},
    )
    crush = build_iv_context(
        window.option_chain, "post_event_iv_crush", window.underlying_snapshot,
        {"iv_effect": -0.50},
    )
    assert event.iv_expansion_potential > event.iv_crush_risk
    assert crush.iv_crush_risk > crush.iv_expansion_potential
    assert event.iv_regime != crush.iv_regime


def test_skew_summary_affects_family_score_deterministically() -> None:
    base = iv_surface_family_score(
        "volatility_compression", _iv_context(0.80, 0.10, "post_event_crush"),
        _surface(0.90, 0.10), _skew(0.05, 0.10), _term(0.00, 0.05, "flat"),
        "post_event_iv_crush",
    )
    steep = iv_surface_family_score(
        "volatility_compression", _iv_context(0.80, 0.10, "post_event_crush"),
        _surface(0.90, 0.10), _skew(0.70, 0.80), _term(0.00, 0.05, "flat"),
        "post_event_iv_crush",
    )
    assert base["skew_score"] > steep["skew_score"]
    assert base == iv_surface_family_score(
        "volatility_compression", _iv_context(0.80, 0.10, "post_event_crush"),
        _surface(0.90, 0.10), _skew(0.05, 0.10), _term(0.00, 0.05, "flat"),
        "post_event_iv_crush",
    )


def test_term_structure_summary_affects_family_score_deterministically() -> None:
    flat = iv_surface_family_score(
        "volatility_expansion", _iv_context(0.10, 0.90, "event_expansion"),
        _surface(0.70, 0.80), _skew(0.20, 0.50), _term(0.05, 0.05, "flat"),
        "event_vol_expansion",
    )
    event = iv_surface_family_score(
        "volatility_expansion", _iv_context(0.10, 0.90, "event_expansion"),
        _surface(0.70, 0.80), _skew(0.20, 0.50), _term(0.90, 0.20, "backwardation"),
        "event_vol_expansion",
    )
    assert event["term_structure_score"] > flat["term_structure_score"]


def test_greek_attribution_result_records_delta_gamma_theta_vega_components() -> None:
    exposure = summarize_greek_exposure([
        _leg("buy", 0.50, 0.020, -0.05, 0.30, "call", 1.0),
    ])
    result = attribute_greek_outcome(
        "s1", "w1", "directional_convexity", exposure,
        2.0, 100.0, 104.0, 0.20, 0.24, 3,
    )
    data = result.to_dict()
    assert data["delta_contribution"] != 0.0
    assert data["gamma_contribution"] != 0.0
    assert data["theta_contribution"] != 0.0
    assert data["vega_contribution"] != 0.0
    assert 0.0 <= data["attribution_quality_score"] <= 1.0


def test_tournament_scores_change_when_greek_context_changes(tmp_path: Path) -> None:
    alt = tmp_path / "alt_corpus"
    alt.mkdir()
    for fixture in WALK_FORWARD_DIR.iterdir():
        if fixture.name.endswith(".json"):
            shutil.copy(fixture, alt / fixture.name)
    target = alt / "window_001_train.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    for contract in data["option_chain"]["contracts"]:
        contract["gamma"] = 0.0
        contract["theta"] = -0.65
        contract["vega"] = 1.15
    target.write_text(json.dumps(data), encoding="utf-8")

    l1, r1 = _tmp_paths(tmp_path / "run1")
    l2, r2 = _tmp_paths(tmp_path / "run2")
    base = run_fixture_tournament(proof_ledger_path=l1, champion_registry_path=r1)
    changed = run_fixture_tournament(proof_ledger_path=l2, champion_registry_path=r2, windows_dir=alt)
    base_scores = {r["strategy_id"]: r["combined_score"] for r in base["strategy_ranking"]}
    changed_scores = {r["strategy_id"]: r["combined_score"] for r in changed["strategy_ranking"]}
    assert base["greek_iv_summary"] != changed["greek_iv_summary"]
    assert base_scores != changed_scores


def test_champion_registry_records_greek_metrics(tmp_path: Path) -> None:
    ledger, registry = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=registry)
    entry = json.loads(registry.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert entry["champion_strategy_id"] == summary["champion_strategy_id"]
    assert entry["greeks_validation_model_version"] == "dopey-greeks-validation-v1"
    assert entry["iv_fixture_model_version"] == "dopey-iv-fixture-model-v1"
    assert entry["average_greek_fit_score"] > 0.0
    assert entry["average_iv_context_score"] > 0.0
    assert entry["best_greek_fit_regime"]
    assert entry["worst_greek_risk_regime"]
    assert entry["greek_strengths"]
    assert entry["greek_weaknesses"]
    assert "greek_iv_summary" in entry
    assert "survived_high_theta_high_vega_risk" in entry


def test_proof_ledger_records_greeks_validation_fields(tmp_path: Path) -> None:
    ledger, registry = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=registry)
    record = json.loads(ledger.read_text(encoding="utf-8").strip().splitlines()[-1])
    execution = record["execution_result"]
    tests = record["test_results"]
    assert execution["greeks_validation_model_version"] == summary["greeks_validation_model_version"]
    assert execution["iv_fixture_model_version"] == summary["iv_fixture_model_version"]
    assert execution["greek_iv_summary"] == summary["greek_iv_summary"]
    assert execution["worst_greek_risk_regimes"] == summary["worst_greek_risk_regimes"]
    assert execution["best_greek_fit_regimes"] == summary["best_greek_fit_regimes"]
    assert tests["greeks_validation_model_version"] == "dopey-greeks-validation-v1"


def test_no_live_promotion_possible_after_greeks_upgrade(tmp_path: Path) -> None:
    ledger, registry = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=registry)
    for decision in summary["promotion_decisions"].values():
        assert decision in ALLOWED_TARGETS
        assert decision not in FORBIDDEN_LIVE_TARGETS
        assert "live" not in decision
    assert summary["live_blocked"] is True


def test_live_stubs_still_block_after_greeks_upgrade() -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_greeks_upgrade() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_greeks_upgrade(tmp_path: Path) -> None:
    ledger, registry = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=registry)
    cfg = load_config(default_config_path())
    assert summary["mode"] == "RESEARCH"
    assert summary["live_trading_enabled"] is False
    assert summary["live_blocked"] is True
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert cfg["funded_broker_connections_enabled"] is False


def test_blunder_source_integrity_if_manifest_available() -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        pytest.skip("Blunder SHA256 manifest not available; skipping integrity check")
    bad = 0
    checked = 0
    for line in manifest.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            continue
        expected, path = parts
        candidate = Path(path)
        if not candidate.exists():
            continue
        checked += 1
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest().upper()
        if actual != expected.strip().upper():
            bad += 1
    assert checked > 0, "no Blunder files were checked (manifest paths unresolved)"
    assert bad == 0, f"{bad} Blunder source file(s) changed since baseline (checked {checked})"
