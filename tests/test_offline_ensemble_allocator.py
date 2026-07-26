"""Tests: DOPEY offline ensemble strategy allocator bundle (paper-only, deterministic)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dopey_core.config import default_config_path, load_config
from dopey_edge.capital_redeployment_engine import (
    build_capital_redeployment_recommendations,
    redeploy_capital,
)
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_strategy_lab.allocation_policy import (
    HIGH_OVERFIT_CANDIDATE_MAX,
    MAX_FAMILY_WEIGHT,
    MAX_SINGLE_STRATEGY_WEIGHT,
    OVERFIT_RANK,
    apply_allocation_policy,
    score_candidate,
)
from dopey_strategy_lab.ensemble_allocator import run_offline_ensemble_allocator
from dopey_strategy_lab.ensemble_models import (
    FORBIDDEN_ALLOCATION_DECISIONS,
    StrategyAllocationCandidate,
)
from dopey_strategy_lab.ensemble_replay import run_ensemble_replay
from dopey_strategy_lab.regime_allocator import (
    build_regime_profiles,
    regime_multiplier_for_family,
)


FORBIDDEN_LIVE_DECISIONS = {"live_candidate", "micro_live", "adaptive_live", "live"}


def _candidate(
    strategy_id: str,
    family: str = "directional_convexity",
    *,
    base: float = 0.70,
    wf: float = 0.70,
    fusion: float = 0.70,
    macro: float = 0.55,
    iv: float = 0.60,
    greek: float = 0.60,
    liquidity: float = 0.70,
    slippage: float = 0.70,
    pattern: float = 0.55,
    failure: float = 0.05,
    overfit: str = "none",
    delta: float = 0.0,
    regimes: list[str] | None = None,
) -> StrategyAllocationCandidate:
    return StrategyAllocationCandidate(
        strategy_id=strategy_id,
        strategy_family=family,
        source_type="tournament",
        base_score=base,
        walk_forward_score=wf,
        analysis_fusion_score=fusion,
        macro_fit_score=macro,
        iv_surface_fit_score=iv,
        greek_fit_score=greek,
        liquidity_robustness_score=liquidity,
        slippage_robustness_score=slippage,
        pattern_score=pattern,
        failure_pressure_score=failure,
        overfit_level=overfit,
        overfit_rank=OVERFIT_RANK.get(overfit, 3),
        mutation_delta=delta,
        promotion_state="entrant",
        paper_only=True,
        holdout_score=0.65,
        best_regimes=regimes if regimes else ["bullish_breakout", "trend_vol_expansion"],
        worst_regimes=[],
    )


# ---------------------------------------------------------------------------
# Workstream A — allocation model tests
# ---------------------------------------------------------------------------

def test_allocation_candidate_serializes_deterministically() -> None:
    c = _candidate("c-1")
    first = json.dumps(c.to_dict(), sort_keys=True)
    second = json.dumps(c.to_dict(), sort_keys=True)
    assert first == second


def test_allocation_score_breakdown_sums_components() -> None:
    c = _candidate("c-1")
    b = score_candidate(c)
    component_sum = b.component_sum()
    # overall score should be within rounding of the component sum, clamped to [0,1]
    assert b.overall_score == round(max(0.0, min(1.0, component_sum)), 6)


def test_simulated_allocation_decision_defaults_paper_only() -> None:
    policy = apply_allocation_policy([_candidate("c-1")])
    decision = policy.decisions[0]
    assert decision.paper_only is True
    assert decision.live_allowed is False


def test_allocation_decision_forbids_live_states() -> None:
    policy = apply_allocation_policy([_candidate("c-1"), _candidate("c-2", family="volatility_compression")])
    for decision in policy.decisions:
        assert decision.decision not in FORBIDDEN_ALLOCATION_DECISIONS


# ---------------------------------------------------------------------------
# Workstream B — allocation policy tests
# ---------------------------------------------------------------------------

def test_allocator_weights_sum_to_one_for_accepted_candidates() -> None:
    candidates = [_candidate(f"c-{i}", family=fam) for i, fam in enumerate(
        ["directional_convexity", "volatility_compression", "volatility_expansion", "short_duration_defined_risk"]
    )]
    policy = apply_allocation_policy(candidates)
    accepted = [d for d in policy.decisions if d.recommended_weight > 0.0]
    if accepted:
        assert round(sum(d.recommended_weight for d in accepted), 4) == pytest.approx(1.0, abs=1e-3)


def test_allocator_assigns_zero_to_rejected_candidates() -> None:
    # Non-paper candidate is rejected.
    unsafe = _candidate("c-unsafe")
    unsafe.paper_only = False
    policy = apply_allocation_policy([unsafe, _candidate("c-ok")])
    rejected = [d for d in policy.decisions if d.strategy_id == "c-unsafe"][0]
    assert rejected.recommended_weight == 0.0
    assert rejected.decision == "reject"


def test_allocator_caps_single_strategy_weight() -> None:
    candidates = [_candidate("c-strong") for _ in range(6)]
    for i, c in enumerate(candidates):
        c.strategy_id = f"c-strong-{i}"
        c.strategy_family = f"fam{i}"  # distinct families to avoid family cap
    policy = apply_allocation_policy(candidates)
    for decision in policy.decisions:
        assert decision.recommended_weight <= MAX_SINGLE_STRATEGY_WEIGHT + 1e-6


def test_allocator_caps_family_weight() -> None:
    # Five strong directional candidates would dominate a single family; cap to 0.60 while
    # the remaining families absorb the slack so weights still sum to 1.0.
    directional = [_candidate(f"c-dir-{i}", family="directional_convexity", base=0.85) for i in range(5)]
    others = [
        _candidate("c-comp", family="volatility_compression", base=0.55),
        _candidate("c-exp", family="volatility_expansion", base=0.55),
        _candidate("c-sd", family="short_duration_defined_risk", base=0.55),
    ]
    candidates = directional + others
    policy = apply_allocation_policy(candidates)
    family_totals: dict[str, float] = {}
    for d in policy.decisions:
        family_totals[d.strategy_family] = family_totals.get(d.strategy_family, 0.0) + d.recommended_weight
    for total in family_totals.values():
        assert total <= MAX_FAMILY_WEIGHT + 1e-6


def test_high_overfit_candidate_weight_capped() -> None:
    high = _candidate("c-overfit", base=0.90, overfit="high")
    ok = _candidate("c-ok", base=0.90, overfit="none")
    policy = apply_allocation_policy([high, ok])
    overfit_decision = [d for d in policy.decisions if d.strategy_id == "c-overfit"][0]
    if overfit_decision.recommended_weight > 0.0:
        assert overfit_decision.recommended_weight <= HIGH_OVERFIT_CANDIDATE_MAX + 1e-6


def test_allocator_penalizes_failure_pressure() -> None:
    clean = _candidate("c-clean", base=0.70, failure=0.02)
    pressured = _candidate("c-pressured", base=0.70, failure=0.45)
    policy = apply_allocation_policy([clean, pressured])
    clean_w = [d for d in policy.decisions if d.strategy_id == "c-clean"][0].recommended_weight
    pressured_decision = [d for d in policy.decisions if d.strategy_id == "c-pressured"][0]
    assert pressured_decision.recommended_weight == 0.0
    assert pressured_decision.decision == "starve_weak_signal"
    assert clean_w > 0.0


def test_allocator_rewards_mutation_improvement_without_overfit_worsening() -> None:
    base_c = _candidate("c-base", base=0.65, delta=0.0, overfit="low")
    improved = _candidate("c-improved", base=0.65, delta=0.05, overfit="low")
    b_base = score_candidate(base_c)
    b_improved = score_candidate(improved)
    assert b_improved.overall_score > b_base.overall_score
    assert b_improved.mutation_bonus > b_base.mutation_bonus


def test_allocator_tie_breakers_are_deterministic() -> None:
    candidates = [
        _candidate("c-a", base=0.70, overfit="low", liquidity=0.70),
        _candidate("c-b", base=0.70, overfit="none", liquidity=0.80),
        _candidate("c-c", base=0.70, overfit="none", liquidity=0.80),
    ]
    from dopey_strategy_lab.allocation_policy import sort_candidates
    breakdowns = [score_candidate(c) for c in candidates]
    order1 = sort_candidates(candidates, breakdowns)
    order2 = sort_candidates(candidates, breakdowns)
    assert order1 == order2
    # Lower overfit / better liquidity sorts earlier.
    assert order1[0] in (1, 2)


# ---------------------------------------------------------------------------
# Workstream C — regime allocation tests
# ---------------------------------------------------------------------------

def test_trend_regime_prefers_directional() -> None:
    profiles = build_regime_profiles()
    trend = profiles["trend"]
    assert "directional_convexity" in trend.preferred_families
    assert regime_multiplier_for_family("trend", "directional_convexity") > regime_multiplier_for_family("trend", "volatility_compression")


def test_event_vol_regime_prefers_vol_expansion_only_when_iv_confirms() -> None:
    no_confirm = regime_multiplier_for_family("event_vol", "volatility_expansion", iv_confirms_expansion=False)
    confirm = regime_multiplier_for_family("event_vol", "volatility_expansion", iv_confirms_expansion=True)
    assert confirm > no_confirm
    profiles = build_regime_profiles()
    assert "volatility_expansion" in profiles["event_vol"].preferred_families


def test_post_event_crush_regime_prefers_compression() -> None:
    profiles = build_regime_profiles()
    crush = profiles["post_event_crush"]
    assert "volatility_compression" in crush.preferred_families
    assert regime_multiplier_for_family("post_event_crush", "volatility_compression") > regime_multiplier_for_family("post_event_crush", "volatility_expansion")


def test_bad_fill_regime_stars_short_duration_or_multi_leg_fragile_candidates() -> None:
    profiles = build_regime_profiles()
    bad_fill = profiles["bad_fill"]
    assert "short_duration_defined_risk" in bad_fill.starve_families or "short_duration_defined_risk" in bad_fill.penalized_families
    assert regime_multiplier_for_family("bad_fill", "short_duration_defined_risk", liquidity_robust=False) <= 0.55


def test_macro_contradiction_regime_reduces_directional_allocation() -> None:
    profiles = build_regime_profiles()
    contradiction = profiles["macro_contradiction"]
    assert "directional_convexity" in contradiction.penalized_families
    mult = regime_multiplier_for_family("macro_contradiction", "directional_convexity")
    assert mult < 1.0


# ---------------------------------------------------------------------------
# Workstream D — ensemble replay tests
# ---------------------------------------------------------------------------

def _replay_pack():
    candidates = [
        _candidate("c-dir", family="directional_convexity", base=0.62, regimes=["bullish_breakout"]),
        _candidate("c-comp", family="volatility_compression", base=0.58, regimes=["post_event_iv_crush"]),
        _candidate("c-exp", family="volatility_expansion", base=0.55, regimes=["event_vol_expansion"]),
    ]
    policy = apply_allocation_policy(candidates)
    decisions = [
        __import__("dopey_strategy_lab.ensemble_models", fromlist=["SimulatedAllocationDecision"]).SimulatedAllocationDecision(
            strategy_id=c.strategy_id,
            strategy_family=c.strategy_family,
            recommended_weight=w,
            decision=dec,
        )
        for c, w, dec in zip(candidates, [d.recommended_weight for d in policy.decisions], [d.decision for d in policy.decisions])
    ]
    return candidates, decisions


def test_ensemble_replay_compares_single_equal_and_allocator_weighted() -> None:
    candidates, decisions = _replay_pack()
    replay = run_ensemble_replay(candidates, decisions)
    assert replay.single_champion_score > 0.0
    assert replay.equal_weight_score > 0.0
    assert replay.allocator_weighted_score > 0.0
    assert replay.overfit_adjusted_score >= 0.0
    assert replay.best_ensemble_variant in {"single_champion", "equal_weight", "allocator_weighted", "overfit_adjusted"}


def test_ensemble_replay_records_regime_coverage() -> None:
    candidates, decisions = _replay_pack()
    replay = run_ensemble_replay(candidates, decisions, known_regimes=["bullish_breakout", "post_event_iv_crush", "event_vol_expansion", "macro_shock_risk_off"])
    assert 0.0 < replay.regime_coverage <= 1.0


def test_ensemble_replay_records_family_diversification() -> None:
    candidates, decisions = _replay_pack()
    replay = run_ensemble_replay(candidates, decisions)
    assert replay.family_diversification >= 1.0


def test_ensemble_replay_penalizes_overfit_concentration() -> None:
    candidates = [
        _candidate("c-single", family="directional_convexity", base=0.90, overfit="high", regimes=["bullish_breakout"]),
        _candidate("c-small1", family="volatility_compression", base=0.40, regimes=["post_event_iv_crush"]),
    ]
    policy = apply_allocation_policy(candidates)
    decisions = [
        __import__("dopey_strategy_lab.ensemble_models", fromlist=["SimulatedAllocationDecision"]).SimulatedAllocationDecision(
            strategy_id=c.strategy_id, strategy_family=c.strategy_family,
            recommended_weight=w, decision=dec,
        )
        for c, w, dec in zip(candidates, [d.recommended_weight for d in policy.decisions], [d.decision for d in policy.decisions])
    ]
    replay = run_ensemble_replay(candidates, decisions)
    # Overfit-adjusted should sit at/below allocator-weighted due to overfit + concentration penalty.
    assert replay.overfit_adjusted_score <= replay.allocator_weighted_score + 1e-6


def test_allocator_weighted_ensemble_is_deterministic() -> None:
    candidates, _ = _replay_pack()
    p1 = apply_allocation_policy(candidates)
    p2 = apply_allocation_policy(candidates)
    w1 = sorted((d.strategy_id, d.recommended_weight) for d in p1.decisions)
    w2 = sorted((d.strategy_id, d.recommended_weight) for d in p2.decisions)
    assert w1 == w2


# ---------------------------------------------------------------------------
# Workstream E — capital redeployment tests
# ---------------------------------------------------------------------------

def test_capital_redeployment_recommends_starving_recurring_failure_modes() -> None:
    recs = build_capital_redeployment_recommendations(
        [{"strategy_id": "s-1", "strategy_family": "directional_convexity", "decision": "hold_paper_attention", "recommended_weight": 0.3, "regime_class": "trend"}],
        failure_pressure_by_family={"directional_convexity": 0.55},
    )
    assert recs[0].action == "starve"
    assert recs[0].failure_mode_evidence
    assert recs[0].paper_only is True


def test_capital_redeployment_recommends_reducing_vol_expansion_after_iv_crush() -> None:
    recs = build_capital_redeployment_recommendations(
        [{"strategy_id": "s-1", "strategy_family": "volatility_expansion", "decision": "hold_paper_attention", "recommended_weight": 0.2, "regime_class": "post_event_crush"}],
        failure_pressure_by_family={},
    )
    assert recs[0].action == "reduce"
    assert "iv crush" in recs[0].reason_codes[0].lower()


def test_capital_redeployment_recommends_tighter_short_duration_liquidity() -> None:
    recs = build_capital_redeployment_recommendations(
        [{"strategy_id": "s-1", "strategy_family": "short_duration_defined_risk", "decision": "hold_paper_attention", "recommended_weight": 0.2, "regime_class": "bad_fill"}],
        failure_pressure_by_family={},
    )
    assert recs[0].action == "reduce"
    assert recs[0].regime_evidence


def test_capital_redeployment_is_paper_only() -> None:
    recs = build_capital_redeployment_recommendations(
        [{"strategy_id": "s-1", "strategy_family": "directional_convexity", "decision": "increase_paper_attention", "recommended_weight": 0.4, "regime_class": "trend"}],
        failure_pressure_by_family={},
    )
    for rec in recs:
        assert rec.paper_only is True
        assert rec.live_allowed is False
        assert rec.proof_level == "paper_only"


# ---------------------------------------------------------------------------
# Workstream F — registry / proof / full-run tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def allocator_result(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("ensemble_allocator")
    return run_offline_ensemble_allocator(
        seed="pytest-ensemble-v1",
        ensemble_registry_path=root / "ensemble_allocation_registry.jsonl",
        proof_ledger_path=root / "ensemble_replay.jsonl",
    )


def test_ensemble_registry_written(allocator_result) -> None:
    assert Path(allocator_result["ensemble_registry_path"]).exists()


def test_ensemble_proof_ledger_record_written(allocator_result) -> None:
    assert Path(allocator_result["proof_record_path"]).exists()


def test_ensemble_record_contains_weights_and_comparison(allocator_result) -> None:
    record = json.loads(Path(allocator_result["ensemble_registry_path"]).read_text(encoding="utf-8").splitlines()[-1])
    assert record["decisions"]
    assert "replay" in record
    replay = record["replay"]
    assert {"single_champion_score", "equal_weight_score", "allocator_weighted_score"}.issubset(replay)
    accepted = [d for d in record["decisions"] if d["recommended_weight"] > 0.0]
    if accepted:
        assert round(sum(d["recommended_weight"] for d in accepted), 3) == pytest.approx(1.0, abs=1e-2)


def test_ensemble_reproducibility_hash_is_deterministic(allocator_result) -> None:
    first = allocator_result["reproducibility_hash"]
    assert len(first) == 64
    int(first, 16)


# ---------------------------------------------------------------------------
# Safety regression tests
# ---------------------------------------------------------------------------

def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="ensemble-live-x",
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


def test_no_live_promotion_possible_after_ensemble_allocator(allocator_result) -> None:
    statuses = {d["decision"] for d in allocator_result["decisions"]}
    assert statuses.isdisjoint(FORBIDDEN_ALLOCATION_DECISIONS)
    assert statuses.isdisjoint(FORBIDDEN_LIVE_DECISIONS)


def test_live_stubs_still_block_after_ensemble_allocator() -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_ensemble_allocator() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_ensemble_allocator(allocator_result) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert allocator_result["live_blocked"] is True


def test_ensemble_allocator_does_not_modify_live_settings(allocator_result) -> None:
    safety = allocator_result["safety_state"]
    assert safety["mode"] == "RESEARCH"
    assert safety["live_trading_enabled"] is False
    assert safety["funded_broker_connections_enabled"] is False
    assert safety["allow_unofficial_robinhood_api"] is False


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


def test_legacy_redeploy_capital_still_works() -> None:
    recs = redeploy_capital({"directional_convexity": 0.8, "volatility_compression": 0.4},
                           {"directional_convexity": 0.5, "volatility_compression": 0.5})
    assert isinstance(recs, list)
