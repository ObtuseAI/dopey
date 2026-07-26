"""Tests: DOPEY failure-mode feedback optimizer bundle."""
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
from dopey_strategy_lab.constraint_tuning import build_constraint_tuning_recommendations
from dopey_strategy_lab.failure_feedback import (
    aggregate_failure_modes,
    build_family_failure_profiles,
    build_regime_failure_profiles,
)
from dopey_strategy_lab.failure_feedback_models import FailureFeedbackDecision
from dopey_strategy_lab.feedback_optimizer import (
    FeedbackCandidateScore,
    decide_feedback_candidate,
    run_failure_feedback_optimizer,
)
from dopey_strategy_lab.feedback_mutation_policy import build_feedback_mutation_batch
from dopey_tournament.genome_set import build_tournament_genomes


FORBIDDEN_LIVE_DECISIONS = {"live_candidate", "micro_live", "adaptive_live", "live"}


def _failure_mode(mode_id: str, family: str, regime: str, recurrence: int, severity: str) -> dict:
    return {
        "failure_mode_id": mode_id,
        "affected_strategy_ids": [f"genome-{family}-fixture"],
        "affected_family": family,
        "windows_or_regimes": [regime],
        "evidence_score": 0.82 if severity == "critical" else 0.70,
        "recurrence_count": recurrence,
        "severity": severity,
        "mitigation_hint": f"mitigate {mode_id}",
        "recommended_mutation_constraint_update": f"update {mode_id}",
        "evidence": [
            {
                "source": "pytest",
                "strategy_id": f"genome-{family}-fixture",
                "family": family,
                "window_or_regime": regime,
                "metric_name": mode_id,
                "metric_value": 0.70,
                "notes": "deterministic failure feedback fixture",
            }
        ],
    }


@pytest.fixture(scope="module")
def failure_record() -> dict:
    return {
        "registry_id": "pytest-failure-registry",
        "failure_modes": [
            _failure_mode("high_spread_bad_fill_failure", "directional_convexity", "high_spread_bad_fill", 4, "critical"),
            _failure_mode("fakeout_against_directional", "directional_convexity", "gap_reversal", 2, "high"),
            _failure_mode("low_liquidity_decay_failure", "short_duration_defined_risk", "low_liquidity_decay", 3, "high"),
            _failure_mode("theta_decay_against_short_duration", "short_duration_defined_risk", "low_liquidity_decay", 2, "high"),
            _failure_mode("IV_crush_against_vol_expansion", "volatility_expansion", "post_event_iv_crush", 5, "critical"),
            _failure_mode("overfit_train_only", "volatility_expansion", "train_validation_holdout", 3, "high"),
            _failure_mode("holdout_collapse", "volatility_expansion", "holdout", 2, "high"),
            _failure_mode("macro_shock_against_compression", "volatility_compression", "macro_shock_risk_off", 4, "critical"),
            _failure_mode("unsafe_structure_rejected", "volatility_compression", "family_limit_validator", 1, "critical"),
        ],
        "mitigation_hints": [],
        "constraint_updates": [],
        "version": "pytest",
    }


@pytest.fixture(scope="module")
def aggregates(failure_record) -> list:
    return aggregate_failure_modes(failure_record)


@pytest.fixture(scope="module")
def family_profiles(aggregates) -> list:
    return build_family_failure_profiles(aggregates)


@pytest.fixture(scope="module")
def recommendations(family_profiles, aggregates) -> list:
    return build_constraint_tuning_recommendations(family_profiles, aggregates)


@pytest.fixture(scope="module")
def optimizer_result(tmp_path_factory, failure_record) -> dict:
    root = tmp_path_factory.mktemp("failure_feedback_optimizer")
    failure_path = root / "failure_mode_registry.jsonl"
    failure_path.write_text(json.dumps(failure_record, ensure_ascii=False) + "\n", encoding="utf-8")
    return run_failure_feedback_optimizer(
        seed="pytest-feedback-v1",
        failure_mode_registry_path=failure_path,
        feedback_registry_path=root / "failure_feedback_registry.jsonl",
        proof_ledger_path=root / "feedback_optimizer.jsonl",
    )


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="feedback-live-x",
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


def _score(candidate_id: str, score_delta: float, overfit_delta: int, regression_delta: float, safety_ok: bool) -> FeedbackCandidateScore:
    return FeedbackCandidateScore(
        candidate_strategy_id=candidate_id,
        parent_strategy_id="parent",
        strategy_family="directional_convexity",
        raw_score=0.60,
        adjusted_score=0.60 + score_delta,
        score_delta_vs_previous=score_delta,
        score_delta_vs_base=score_delta + 0.01,
        overfit_level="low",
        overfit_delta=overfit_delta,
        failure_regression_delta=regression_delta,
        safety_ok=safety_ok,
        recommendation_ids=["rec"],
        targeted_failure_modes=["high_spread_bad_fill_failure"],
        row={},
    )


def test_failure_feedback_aggregates_by_family_and_regime(aggregates) -> None:
    families = {aggregate.strategy_family for aggregate in aggregates}
    regimes = {aggregate.regime_tag for aggregate in aggregates}
    assert "directional_convexity" in families
    assert "high_spread_bad_fill" in regimes


def test_failure_feedback_identifies_top_recurring_failures(family_profiles) -> None:
    vol_profile = next(profile for profile in family_profiles if profile.strategy_family == "volatility_expansion")
    assert vol_profile.top_failure_modes[0] == "IV_crush_against_vol_expansion"


def test_failure_feedback_classifies_liquidity_greek_overfit_and_structure_failures(aggregates) -> None:
    categories = {aggregate.failure_category for aggregate in aggregates}
    assert {"liquidity_slippage", "greek_iv", "overfit", "structure"}.issubset(categories)


def test_family_failure_profile_serializes_deterministically(family_profiles) -> None:
    first = [profile.to_dict() for profile in family_profiles]
    second = [profile.to_dict() for profile in family_profiles]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_high_spread_failure_recommends_tighter_spread_and_liquidity(recommendations) -> None:
    recs = [rec for rec in recommendations if rec.failure_mode_id == "high_spread_bad_fill_failure"]
    keys = {rec.tuning_key for rec in recs}
    assert {"max_spread_threshold", "liquidity_minimum"}.issubset(keys)


def test_iv_crush_failure_recommends_vol_expansion_guard(recommendations) -> None:
    recs = [rec for rec in recommendations if rec.failure_mode_id == "IV_crush_against_vol_expansion"]
    assert any(rec.tuning_key == "iv_expansion_threshold" for rec in recs)


def test_macro_shock_failure_recommends_compression_guard(recommendations) -> None:
    recs = [rec for rec in recommendations if rec.failure_mode_id == "macro_shock_against_compression"]
    assert any(rec.tuning_key == "macro_shock_avoidance" for rec in recs)


def test_fakeout_failure_recommends_directional_confirmation_guard(recommendations) -> None:
    recs = [rec for rec in recommendations if rec.failure_mode_id == "fakeout_against_directional"]
    assert any(rec.tuning_key == "pattern_confirmation" for rec in recs)


def test_holdout_collapse_recommends_overfit_penalty(recommendations) -> None:
    recs = [rec for rec in recommendations if rec.failure_mode_id == "holdout_collapse"]
    assert any(rec.tuning_key == "overfit_penalty" for rec in recs)


def test_unsafe_structure_failure_recommends_ban_pattern(recommendations) -> None:
    recs = [rec for rec in recommendations if rec.failure_mode_id == "unsafe_structure_rejected"]
    assert any(rec.tuning_key == "mutation_ban_pattern" for rec in recs)


def test_feedback_optimizer_generates_replay_only_recommendations(optimizer_result) -> None:
    assert optimizer_result["optimizer_status"] == "ok"
    assert all(recommendation["replay_only"] for recommendation in optimizer_result["recommendations"])


def test_feedback_optimizer_generates_at_least_16_mutations(optimizer_result) -> None:
    assert optimizer_result["feedback_mutations_generated"] >= 16


def test_feedback_mutations_preserve_live_allowed_false(optimizer_result) -> None:
    assert all(result["row"]["live_allowed"] is False for result in optimizer_result["scoring_results"])


def test_feedback_mutations_preserve_defined_risk(optimizer_result) -> None:
    assert all(result["row"]["defined_risk_only"] is True for result in optimizer_result["scoring_results"])
    assert all(result["row"]["structure_risk"] == "defined" for result in optimizer_result["scoring_results"])


def test_feedback_optimizer_rejects_overfit_worse_candidate() -> None:
    decision = decide_feedback_candidate(_score("candidate-overfit", 0.02, 1, -0.01, True), "candidate-overfit")
    assert decision.status == "rejected_overfit_worse"


def test_feedback_optimizer_rejects_failure_regression_candidate() -> None:
    decision = decide_feedback_candidate(_score("candidate-regression", 0.02, 0, 0.01, True), "candidate-regression")
    assert decision.status == "rejected_failure_regression"


def test_feedback_optimizer_can_accept_replay_only_improvement() -> None:
    decision = decide_feedback_candidate(_score("candidate-best", 0.02, 0, -0.01, True), "candidate-best")
    assert decision.status == "accepted_replay_only"


def test_feedback_optimizer_compares_base_previous_and_feedback_candidate(optimizer_result) -> None:
    comparison = optimizer_result["comparison"]
    assert comparison["base_champion_strategy_id"]
    assert "previous_mutation_strategy_id" in comparison
    assert comparison["best_feedback_strategy_id"] == optimizer_result["best_feedback_mutation"]


def test_feedback_registry_written(optimizer_result) -> None:
    assert Path(optimizer_result["feedback_registry_path"]).exists()


def test_feedback_optimizer_proof_ledger_record_written(optimizer_result) -> None:
    assert Path(optimizer_result["proof_record_path"]).exists()


def test_feedback_record_contains_recommendations_and_decisions(optimizer_result) -> None:
    record = json.loads(Path(optimizer_result["feedback_registry_path"]).read_text(encoding="utf-8").splitlines()[-1])
    assert record["constraint_recommendations"]
    assert record["decisions"]


def test_feedback_reproducibility_hash_is_deterministic(optimizer_result) -> None:
    first = optimizer_result["reproducibility_hash"]
    second = optimizer_result["reproducibility_hash"]
    assert first == second
    assert len(first) == 64
    int(first, 16)


def test_no_live_promotion_possible_after_feedback_optimizer(optimizer_result) -> None:
    statuses = {decision["status"] for decision in optimizer_result["decisions"]}
    assert statuses.isdisjoint(FORBIDDEN_LIVE_DECISIONS)


def test_live_stubs_still_block_after_feedback_optimizer() -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_feedback_optimizer() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_feedback_optimizer(optimizer_result) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert optimizer_result["live_blocked"] is True


def test_feedback_optimizer_does_not_modify_live_settings(optimizer_result) -> None:
    safety = optimizer_result["safety_state"]
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


def test_feedback_mutation_batch_has_all_valid_replay_candidates(family_profiles, recommendations) -> None:
    batch = build_feedback_mutation_batch(build_tournament_genomes(), family_profiles, recommendations, "pytest")
    assert len(batch.candidates) >= 16
    assert len(batch.valid_candidates()) == len(batch.candidates)


def test_regime_failure_profiles_rank_recurring_regimes(aggregates) -> None:
    profiles = build_regime_failure_profiles(aggregates)
    assert profiles[0].recurrence_count >= profiles[-1].recurrence_count


def test_failure_feedback_decision_serializes_recommendations_sorted() -> None:
    decision = FailureFeedbackDecision("d", "f", ["b", "a"], "c", "advisory_only", 0.0, 0, 0.0, ["z", "a"])
    assert decision.to_dict()["recommendation_ids"] == ["a", "b"]
