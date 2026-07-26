"""Tests: DOPEY mutation population and structure-builder bundle."""
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
from dopey_options.structure_builder import StructureBuildRequest, build_option_structure
from dopey_strategy_lab.failure_mode_miner import mine_failure_modes
from dopey_strategy_lab.family_mutation_limits import FamilyMutationLimitValidator
from dopey_strategy_lab.mutation_constraints import constraint_updates_from_failure_modes
from dopey_strategy_lab.mutation_population import POPULATION_MUTATION_TYPES, build_mutation_population
from dopey_strategy_lab.run_mutation_population_bundle import run_mutation_population_bundle
from dopey_strategy_lab.strategy_genome import StrategyGenome
from dopey_tournament.genome_set import build_tournament_genomes
from dopey_walk_forward.window_model import load_walk_forward_windows


FORBIDDEN_LIVE_DECISIONS = {"live_candidate", "micro_live", "adaptive_live", "live"}


@pytest.fixture(scope="module")
def candidates() -> list[dict]:
    window = load_walk_forward_windows()[0]
    rows: list[dict] = []
    for contract in window.option_chain.contracts:
        row = contract.to_dict()
        row["mid"] = contract.mid()
        row["spread_pct"] = contract.spread_pct()
        row["liquidity"] = 0.72
        row["liquidity_score"] = 0.72
        row["quote_stability_score"] = 0.80
        row["fillability_score"] = 0.78
        row["depth_proxy_score"] = 0.70
        row["expected_slippage_pct"] = 0.012
        rows.append(row)
    return rows


@pytest.fixture(scope="module")
def population_batch():
    return build_mutation_population(build_tournament_genomes(), "pytest-population-v1")


@pytest.fixture(scope="module")
def bundle_result() -> dict:
    return run_mutation_population_bundle(seed="pytest-population-v1")


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="population-live-x",
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


def _mode_ids(registry) -> set[str]:
    return {mode.failure_mode_id for mode in registry.failure_modes}


def _row(strategy_id: str, family: str) -> dict:
    return {
        "strategy_id": strategy_id,
        "strategy_family": family,
        "worst_regimes": ["gap_reversal", "low_liquidity_decay", "macro_shock_risk_off"],
        "worst_slippage_regime": "high_spread_bad_fill",
        "average_expected_slippage_pct": 0.061,
        "average_liquidity_score": 0.44,
        "average_iv_score": 0.30,
        "average_iv_context_score": 0.30,
        "worst_greek_risk_regime": "post_event_iv_crush",
        "average_theta_fit_score": 0.40,
        "average_delta_fit_score": 0.30,
        "average_greek_fit_score": 0.40,
        "average_pattern_fixture_score": 0.40,
        "slippage_robustness_score": 0.40,
        "family_regime_survival": 0.20,
        "holdout_score": -6.0,
        "overfit_level": "high",
        "mutation_adjustment": -0.03,
        "penalizing_pattern_ids": ["pattern-failed-breakout-reversal"],
    }


def test_mutation_population_generates_at_least_24(population_batch) -> None:
    assert len(population_batch.records) >= 24
    assert len(population_batch.valid_records()) >= 24
    assert len(POPULATION_MUTATION_TYPES) == 16


def test_mutation_population_is_deterministic_by_seed() -> None:
    first = build_mutation_population(build_tournament_genomes(), "same-seed").to_dict()
    second = build_mutation_population(build_tournament_genomes(), "same-seed").to_dict()
    assert first == second


def test_mutation_population_covers_all_strategy_families(population_batch) -> None:
    families = {record.genome.family for record in population_batch.valid_records()}
    assert families == {
        "directional_convexity",
        "volatility_expansion",
        "volatility_compression",
        "short_duration_defined_risk",
    }


def test_mutation_population_preserves_live_allowed_false(population_batch) -> None:
    assert all(record.genome.live_allowed is False for record in population_batch.valid_records())


def test_mutation_population_preserves_defined_risk(population_batch) -> None:
    assert all(record.genome.defined_risk_only is True for record in population_batch.valid_records())
    assert all(record.genome.parameters.get("structure_risk") == "defined" for record in population_batch.valid_records())


def test_directional_mutation_limits_reject_non_directional_drift() -> None:
    genome = StrategyGenome("g", "directional_convexity", parameters={
        "mutation_type": "adjust_spread_structure_proxy",
        "structure_risk": "defined",
        "thesis_mutation": "volatility_compression_only",
        "directional_exposure": "none",
    })
    result = FamilyMutationLimitValidator().validate(genome)
    assert result.allowed is False


def test_vol_expansion_limits_reject_short_vol_drift() -> None:
    genome = StrategyGenome("g", "volatility_expansion", parameters={
        "mutation_type": "adjust_iv_regime_preference",
        "structure_risk": "defined",
        "iv_regime_preference": "iv_crush_only",
        "volatility_bias": "short",
        "positive_vega_thesis": False,
    })
    assert FamilyMutationLimitValidator().validate(genome).allowed is False


def test_compression_limits_reject_unlimited_risk() -> None:
    genome = StrategyGenome("g", "volatility_compression", parameters={
        "mutation_type": "adjust_spread_structure_proxy",
        "structure_risk": "undefined",
        "unlimited_risk_short_vol": True,
    })
    assert FamilyMutationLimitValidator().validate(genome).decision == "unsafe_rejected"


def test_short_duration_limits_reject_low_liquidity_drift() -> None:
    genome = StrategyGenome("g", "short_duration_defined_risk", parameters={
        "mutation_type": "adjust_liquidity_threshold",
        "structure_risk": "defined",
        "liquidity_threshold": 0.10,
        "spread_width_threshold": 20.0,
    })
    assert FamilyMutationLimitValidator().validate(genome).allowed is False


def test_family_mutation_limit_validator_allows_valid_family_mutations(population_batch) -> None:
    assert all(record.validation.allowed for record in population_batch.valid_records())


def test_structure_builder_builds_long_call_vertical(candidates) -> None:
    result = build_option_structure(StructureBuildRequest("long_call_vertical", "directional_convexity", "SPY_FIXTURE", "bullish_breakout", candidates))
    assert result.ok is True
    assert result.structure is not None
    assert result.risk_summary.leg_count == 2


def test_structure_builder_builds_long_put_vertical(candidates) -> None:
    result = build_option_structure(StructureBuildRequest("long_put_vertical", "directional_convexity", "SPY_FIXTURE", "bearish_breakdown", candidates))
    assert result.ok is True
    assert result.risk_summary.directional_bias == "bearish"


def test_structure_builder_builds_vol_expansion_proxy(candidates) -> None:
    result = build_option_structure(StructureBuildRequest("long_strangle_proxy", "volatility_expansion", "SPY_FIXTURE", "event_vol_expansion", candidates))
    assert result.ok is True
    assert result.risk_summary.volatility_bias == "positive_vega"


def test_structure_builder_builds_compression_proxy_defined_risk(candidates) -> None:
    result = build_option_structure(StructureBuildRequest("iron_condor_proxy", "volatility_compression", "SPY_FIXTURE", "range_bound_pin", candidates))
    assert result.ok is True
    assert result.risk_summary.structure_safety_verdict == "defined_risk"
    assert result.risk_summary.net_credit >= 0.0


def test_structure_builder_builds_short_duration_proxy(candidates) -> None:
    result = build_option_structure(StructureBuildRequest("short_dte_debit_spread_proxy", "short_duration_defined_risk", "SPY_FIXTURE", "bullish_breakout", candidates))
    assert result.ok is True
    assert result.risk_summary.execution_structure == "vertical"


def test_structure_builder_rejects_naked_undefined_risk(candidates) -> None:
    result = build_option_structure(StructureBuildRequest("naked_short_call", "volatility_compression", "SPY_FIXTURE", "range_bound_pin", candidates))
    assert result.ok is False
    assert result.risk_summary.structure_safety_verdict == "unsafe_rejected"


def test_structure_risk_summary_records_max_loss_and_leg_count(candidates) -> None:
    result = build_option_structure(StructureBuildRequest("butterfly_proxy", "short_duration_defined_risk", "SPY_FIXTURE", "range_bound_pin", candidates))
    assert result.risk_summary.max_loss > 0
    assert result.risk_summary.leg_count == 3


def test_structure_builder_integrates_liquidity_slippage_and_greeks(candidates) -> None:
    result = build_option_structure(StructureBuildRequest("long_straddle_proxy", "volatility_expansion", "SPY_FIXTURE", "event_vol_expansion", candidates))
    assert result.risk_summary.liquidity_aggregate > 0
    assert result.risk_summary.slippage_aggregate > 0
    assert "net_delta" in result.risk_summary.greek_exposure_summary


def test_failure_mode_miner_detects_high_spread_bad_fill() -> None:
    registry = mine_failure_modes([_row("g", "directional_convexity")], [], [])
    assert "high_spread_bad_fill_failure" in _mode_ids(registry)


def test_failure_mode_miner_detects_iv_crush_against_vol_expansion() -> None:
    registry = mine_failure_modes([_row("g", "volatility_expansion")], [], [])
    assert "IV_crush_against_vol_expansion" in _mode_ids(registry)


def test_failure_mode_miner_detects_macro_shock_against_compression() -> None:
    row = _row("g", "volatility_compression")
    row["worst_greek_risk_regime"] = "macro_shock_risk_off"
    registry = mine_failure_modes([row], [], [])
    assert "macro_shock_against_compression" in _mode_ids(registry)


def test_failure_mode_miner_detects_fakeout_against_directional() -> None:
    registry = mine_failure_modes([_row("g", "directional_convexity")], [], [])
    assert "fakeout_against_directional" in _mode_ids(registry)


def test_failure_mode_miner_detects_holdout_collapse() -> None:
    registry = mine_failure_modes([_row("g", "volatility_expansion")], [], [])
    assert "holdout_collapse" in _mode_ids(registry)


def test_failure_mode_registry_records_recurrence_and_mitigation() -> None:
    registry = mine_failure_modes([_row("g1", "directional_convexity"), _row("g2", "directional_convexity")], [], [])
    mode = next(mode for mode in registry.failure_modes if mode.failure_mode_id == "high_spread_bad_fill_failure")
    assert mode.recurrence_count == 2
    assert mode.mitigation_hint


def test_mutation_population_bundle_runs_offline(bundle_result) -> None:
    assert bundle_result["bundle_status"] == "ok"
    assert bundle_result["mode"] == "RESEARCH"
    assert bundle_result["live_blocked"] is True


def test_mutation_population_bundle_writes_mutation_registry(bundle_result) -> None:
    assert Path(bundle_result["mutation_registry_path"]).exists()


def test_mutation_population_bundle_writes_failure_mode_registry(bundle_result) -> None:
    assert Path(bundle_result["failure_mode_registry_path"]).exists()


def test_mutation_population_bundle_writes_proof_ledger(bundle_result) -> None:
    assert Path(bundle_result["proof_record_path"]).exists()


def test_best_mutation_selection_uses_score_and_overfit(bundle_result) -> None:
    """Selection correctness, not outcome luck: the reported best must be the
    adjusted-score argmax, high-overfit candidates must never be promoted, and
    the champion title must be EARNED (delta beats the improvement floor) -
    never awarded on a round where the population failed to beat its parents.
    (The old `best_delta > 0` assertion pinned an empirical accident of the
    fixture population.)"""
    from dopey_strategy_lab.mutation_scorecard import MIN_IMPROVED_MUTATION_DELTA

    registry_lines = Path(bundle_result["mutation_registry_path"]).read_text(encoding="utf-8").splitlines()
    registry = json.loads(registry_lines[-1])
    ranking = registry["ranking"]
    assert ranking
    # Selection property: reported best == adjusted-score argmax.
    assert bundle_result["best_mutation"] == ranking[0]["strategy_id"]
    assert bundle_result["best_delta"] == ranking[0]["population_score_delta"]
    # Overfit discipline: no high-overfit candidate is ever promoted.
    for row in ranking:
        if row.get("overfit_level") == "high":
            assert bundle_result["promotion_decisions"][row["strategy_id"]] == "rejected"
    # Champion discipline: title earned only by beating the parent.
    best_decision = bundle_result["promotion_decisions"][bundle_result["best_mutation"]]
    if bundle_result["best_delta"] > MIN_IMPROVED_MUTATION_DELTA:
        assert best_decision == "offline_mutation_champion"
    else:
        assert best_decision in {"degraded", "research_only"}
        assert "offline_mutation_champion" not in set(bundle_result["promotion_decisions"].values())


def test_failure_modes_feed_back_into_mutation_constraints(bundle_result) -> None:
    updates = bundle_result["failure_mode_summary"]["constraint_updates"]
    assert updates
    assert constraint_updates_from_failure_modes([{"failure_mode_id": "holdout_collapse", "affected_family": "directional_convexity", "severity": "high"}])


def test_no_live_promotion_possible_after_population_bundle(bundle_result) -> None:
    decisions = set(bundle_result["promotion_decisions"].values())
    assert decisions.isdisjoint(FORBIDDEN_LIVE_DECISIONS)


def test_live_stubs_still_block_after_population_bundle() -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_population_bundle() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_population_bundle(bundle_result) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert bundle_result["safety_state"]["live_blocked"] is True


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
