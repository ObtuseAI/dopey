"""Integration proofs for downgrade-only epistemic supervision."""

from __future__ import annotations

from dataclasses import replace

import pytest

from dopey_autonomy.run_resilient_research_supervisor import STAGES, _is_degraded
from dopey_validation.epistemic_adversary import (
    CandidateClaim,
    EvidencePoint,
    RegimeEffect,
    StageContract,
    audit_supervisor_topology,
    default_epistemic_policy,
    evaluate_epistemic_claim,
)

CLAIM_AT = "2026-07-26T15:00:00+00:00"
OBSERVED_AT = "2026-07-26T13:00:00+00:00"
AVAILABLE_AT = "2026-07-26T14:00:00+00:00"


def _clean_claim() -> CandidateClaim:
    return CandidateClaim(
        claim_id="claim:targeting:AAA:20260726",
        symbol="AAA",
        lane="targeting",
        upstream_status="targeting_shadow_eligible_for_forward_validation",
        as_of_utc=CLAIM_AT,
        direction="bullish",
        score=0.65,
        aggregate_effect=0.03,
        issuer_sector="technology",
        valuation_peer_sector="technology",
        days_since_ipo=None,
        catalyst_ids=("earnings-revision:AAA:2026Q2",),
        promotion_requested=False,
        fitness_delta=0.02,
        training_evidence_ids=("train:1", "train:2"),
        evaluation_evidence_ids=("evaluation:1", "evaluation:2"),
        hidden_holdout_passed=True,
        external_holdout_passed=True,
        prior_artifact_hash="a" * 64,
        order_capability_present=False,
    )


def _clean_evidence() -> tuple[EvidencePoint, ...]:
    return (
        EvidencePoint(
            evidence_id="evaluation:1",
            source_id="official-filing",
            source_hash="1" * 64,
            observed_at_utc=OBSERVED_AT,
            available_at_utc=AVAILABLE_AT,
            feature_name="revenue_revision",
            feature_family="fundamental",
            value=0.50,
            direction="supports",
            denominator=100,
            requires_denominator=True,
            weight=0.25,
            regime="risk_on",
            cohort="technology",
            catalyst_id="earnings-revision:AAA:2026Q2",
            point_in_time=True,
            origin_layer="research",
        ),
        EvidencePoint(
            evidence_id="evaluation:2",
            source_id="exchange-options",
            source_hash="2" * 64,
            observed_at_utc=OBSERVED_AT,
            available_at_utc=AVAILABLE_AT,
            feature_name="quote_derived_skew",
            feature_family="options",
            value=0.50,
            direction="supports",
            denominator=100,
            requires_denominator=True,
            weight=0.25,
            regime="risk_off",
            cohort="technology",
            catalyst_id=None,
            point_in_time=True,
            origin_layer="research",
        ),
        EvidencePoint(
            evidence_id="evaluation:3",
            source_id="official-short-interest",
            source_hash="3" * 64,
            observed_at_utc=OBSERVED_AT,
            available_at_utc=AVAILABLE_AT,
            feature_name="open_short_interest",
            feature_family="short_interest",
            value=0.50,
            direction="supports",
            denominator=100,
            requires_denominator=True,
            weight=0.25,
            regime="high_volatility",
            cohort="technology",
            catalyst_id=None,
            point_in_time=True,
            origin_layer="research",
        ),
        EvidencePoint(
            evidence_id="evaluation:4",
            source_id="official-prices",
            source_hash="4" * 64,
            observed_at_utc=OBSERVED_AT,
            available_at_utc=AVAILABLE_AT,
            feature_name="relative_strength",
            feature_family="price",
            value=0.50,
            direction="supports",
            denominator=100,
            requires_denominator=True,
            weight=0.25,
            regime="normal_volatility",
            cohort="technology",
            catalyst_id=None,
            point_in_time=True,
            origin_layer="research",
        ),
    )


def _stable_regimes() -> tuple[RegimeEffect, ...]:
    return (
        RegimeEffect("risk_on", "technology", 0.03, 100),
        RegimeEffect("risk_off", "technology", 0.02, 100),
        RegimeEffect("high_volatility", "technology", 0.01, 100),
    )


def test_clean_claim_is_deterministic_and_cannot_promote_or_execute() -> None:
    first = evaluate_epistemic_claim(
        _clean_claim(),
        _clean_evidence(),
        _stable_regimes(),
        default_epistemic_policy(),
    )
    second = evaluate_epistemic_claim(
        _clean_claim(),
        _clean_evidence(),
        _stable_regimes(),
        default_epistemic_policy(),
    )

    assert first == second
    assert first["supervision_status"] == "eligible_for_existing_research_gates"
    assert first["finding_count"] == 0
    assert first["content_hash"] == second["content_hash"]
    assert first["research_only"] is True
    assert first["simulated_execution_separated"] is True
    assert first["existing_research_gates_still_required"] is True
    assert first["promotion_allowed"] is False
    assert first["order_construction_allowed"] is False
    assert first["live_execution_allowed"] is False
    assert first["profit_or_edge_claimed"] is False


def test_adversary_catches_temporal_duplicate_contradiction_and_laundering() -> None:
    duplicated_future = EvidencePoint(
        evidence_id="dup:1",
        source_id="official-short-interest",
        source_hash="d" * 64,
        observed_at_utc="2026-07-27T13:00:00+00:00",
        available_at_utc="2026-07-27T14:00:00+00:00",
        feature_name="short_percent_float",
        feature_family="short_interest",
        value=0.99,
        direction="supports",
        denominator=None,
        requires_denominator=True,
        weight=0.95,
        regime="risk_on",
        cohort="small_cap",
        catalyst_id=None,
        point_in_time=False,
        origin_layer="research",
    )
    evidence = (
        duplicated_future,
        replace(duplicated_future, evidence_id="dup:2"),
        EvidencePoint(
            evidence_id="opposition:1",
            source_id="relabelled-broker-source",
            source_hash="d" * 64,
            observed_at_utc=OBSERVED_AT,
            available_at_utc=AVAILABLE_AT,
            feature_name="borrow_availability",
            feature_family="short_interest",
            value=0.90,
            direction="opposes",
            denominator=200,
            requires_denominator=True,
            weight=10.0,
            regime="risk_off",
            cohort="small_cap",
            catalyst_id=None,
            point_in_time=True,
            origin_layer="simulated_execution",
        ),
        EvidencePoint(
            evidence_id="stale:1",
            source_id="old-options",
            source_hash="e" * 64,
            observed_at_utc="2026-07-10T13:00:00+00:00",
            available_at_utc="2026-07-10T14:00:00+00:00",
            feature_name="call_open_interest_ratio",
            feature_family="options_crowding",
            value=0.20,
            direction="supports",
            denominator=None,
            requires_denominator=True,
            weight=0.10,
            regime="high_volatility",
            cohort="small_cap",
            catalyst_id=None,
            point_in_time=True,
            origin_layer="research",
        ),
    )
    claim = CandidateClaim(
        claim_id="claim:squeeze:TRAP:20260726",
        symbol="TRAP",
        lane="squeeze",
        upstream_status="blocked_missing_real_dataset",
        as_of_utc=CLAIM_AT,
        direction="bullish",
        score=0.99,
        aggregate_effect=0.20,
        issuer_sector="technology",
        valuation_peer_sector="technology",
        days_since_ipo=None,
        catalyst_ids=(),
        promotion_requested=True,
        fitness_delta=-0.10,
        training_evidence_ids=("dup:1", "dup:2"),
        evaluation_evidence_ids=("dup:2", "missing:evaluation"),
        hidden_holdout_passed=False,
        external_holdout_passed=False,
        prior_artifact_hash="",
        order_capability_present=True,
    )
    regime_effects = (
        RegimeEffect("risk_on", "small_cap", -0.20, 100),
        RegimeEffect("risk_off", "small_cap", -0.10, 100),
        RegimeEffect("high_volatility", "small_cap", 0.05, 20),
    )

    result = evaluate_epistemic_claim(
        claim,
        evidence,
        regime_effects,
        default_epistemic_policy(),
    )
    reason_codes = set(result["finding_reason_codes"])

    assert result["supervision_status"] == "blocked_missing_real_dataset"
    assert result["upstream_status_preserved_exactly"] is True
    assert result["automatic_rollback_required"] is True
    assert result["mutation_retention_allowed"] is False
    assert {
        "future_observation_after_claim",
        "future_evidence_available_after_claim",
        "non_point_in_time_evidence",
        "stale_evidence",
        "duplicated_evidence_contribution",
        "source_hash_relabeling",
        "contradictory_feature_direction",
        "missing_or_insufficient_denominator",
        "single_observation_weight_domination",
        "single_observation_contribution_domination",
        "simpson_or_regime_direction_inversion",
        "regime_direction_instability",
        "crowding_without_independent_catalyst",
        "execution_layer_evidence_contamination",
        "order_capability_present_in_research_claim",
        "fitness_drop_requires_rollback",
        "promotion_attempt_from_blocked_or_inconclusive_upstream",
        "hidden_holdout_not_passed",
        "external_holdout_not_passed",
        "positive_fitness_delta_not_proven",
        "training_evaluation_evidence_reuse",
        "unbound_evaluation_evidence",
        "promotion_missing_parent_artifact_hash",
    } <= reason_codes
    assert result["promotion_allowed"] is False
    assert result["order_construction_allowed"] is False


def test_bubble_adversary_rejects_sector_mismatch_and_mechanical_ipo() -> None:
    evidence = (
        EvidencePoint(
            evidence_id="bubble:valuation",
            source_id="official-filing",
            source_hash="a" * 64,
            observed_at_utc=OBSERVED_AT,
            available_at_utc=AVAILABLE_AT,
            feature_name="extreme_price_to_sales",
            feature_family="valuation",
            value=0.60,
            direction="supports",
            denominator=100,
            requires_denominator=True,
            weight=0.25,
            regime="risk_on",
            cohort="technology",
            catalyst_id=None,
            point_in_time=True,
            origin_layer="research",
        ),
        EvidencePoint(
            evidence_id="bubble:ipo",
            source_id="official-ipo",
            source_hash="b" * 64,
            observed_at_utc=OBSERVED_AT,
            available_at_utc=AVAILABLE_AT,
            feature_name="days_since_first_trade",
            feature_family="ipo",
            value=0.60,
            direction="supports",
            denominator=100,
            requires_denominator=True,
            weight=0.25,
            regime="risk_off",
            cohort="technology",
            catalyst_id=None,
            point_in_time=True,
            origin_layer="research",
        ),
        EvidencePoint(
            evidence_id="bubble:price",
            source_id="official-prices",
            source_hash="c" * 64,
            observed_at_utc=OBSERVED_AT,
            available_at_utc=AVAILABLE_AT,
            feature_name="post_ipo_price_extension",
            feature_family="price",
            value=0.60,
            direction="supports",
            denominator=100,
            requires_denominator=True,
            weight=0.25,
            regime="high_volatility",
            cohort="technology",
            catalyst_id=None,
            point_in_time=True,
            origin_layer="research",
        ),
        EvidencePoint(
            evidence_id="bubble:volume",
            source_id="official-volume",
            source_hash="f" * 64,
            observed_at_utc=OBSERVED_AT,
            available_at_utc=AVAILABLE_AT,
            feature_name="post_ipo_volume",
            feature_family="volume",
            value=0.60,
            direction="supports",
            denominator=100,
            requires_denominator=True,
            weight=0.25,
            regime="normal_volatility",
            cohort="technology",
            catalyst_id=None,
            point_in_time=True,
            origin_layer="research",
        ),
    )
    claim = CandidateClaim(
        claim_id="claim:bubble:NEW:20260726",
        symbol="NEW",
        lane="bubble",
        upstream_status=(
            "bubble_unwind_candidate_requires_options_control_and_existing_gates"
        ),
        as_of_utc=CLAIM_AT,
        direction="bearish",
        score=0.80,
        aggregate_effect=-0.04,
        issuer_sector="technology",
        valuation_peer_sector="energy",
        days_since_ipo=20,
        catalyst_ids=(),
        promotion_requested=False,
        fitness_delta=0.01,
        training_evidence_ids=(),
        evaluation_evidence_ids=(),
        hidden_holdout_passed=False,
        external_holdout_passed=False,
        prior_artifact_hash="b" * 64,
        order_capability_present=False,
    )
    regimes = (
        RegimeEffect("risk_on", "technology", -0.04, 100),
        RegimeEffect("risk_off", "technology", -0.03, 100),
        RegimeEffect("high_volatility", "technology", -0.02, 100),
    )

    result = evaluate_epistemic_claim(
        claim,
        evidence,
        regimes,
        default_epistemic_policy(),
    )

    assert result["supervision_status"] == ("blocked_epistemic_adversarial_failure")
    assert {
        "valuation_sector_mismatch",
        "mechanical_post_ipo_effect_not_excluded",
    } <= set(result["finding_reason_codes"])
    assert result["promotion_allowed"] is False


@pytest.mark.parametrize(
    "upstream_status",
    (
        "inconclusive_timeout",
        "insufficient_evidence_shadow_watch",
        "bubble_watch_or_blocked",
        "missing_real_dataset",
    ),
)
def test_blocked_and_inconclusive_states_are_preserved_exactly(
    upstream_status: str,
) -> None:
    claim = replace(_clean_claim(), upstream_status=upstream_status)

    result = evaluate_epistemic_claim(
        claim,
        _clean_evidence(),
        _stable_regimes(),
        default_epistemic_policy(),
    )

    assert result["supervision_status"] == upstream_status
    assert result["upstream_status_preserved_exactly"] is True
    assert result["promotion_allowed"] is False


def test_current_supervisor_truth_is_39_stages_with_epistemic_lineage() -> None:
    stage_contracts = tuple(
        StageContract(name=name, dependencies=dependencies)
        for name, _runner, dependencies in STAGES
    )

    audit = audit_supervisor_topology(stage_contracts, 39)

    assert audit["current_stage_count"] == 39
    assert audit["stage_count_status"] == "verified_current_39_stage_truth"
    assert audit["topologically_ordered"] is True
    assert audit["structural_validity"] is True
    assert audit["audit_status"] == ("structurally_valid_no_epistemic_lineage_gaps")
    assert audit["gap_count"] == 0
    assert audit["critical_lineage"]["epistemic_supervision_dependencies"] == (
        "symbol_targeting",
        "squeeze_bubble_intelligence",
    )
    assert audit["research_execution_separation_preserved"] is True
    assert audit["intentional_separations"] == {
        "action_readiness_is_independent_root": True,
        "account_reconciliation_is_independent_root": True,
        "research_epistemic_stage_has_execution_dependencies": False,
    }
    assert audit["mutation_performed"] is False
    assert audit["promotion_allowed"] is False
    assert audit["order_capability_present"] is False


def test_inconclusive_epistemic_stage_is_supervisor_degraded() -> None:
    assert _is_degraded("inconclusive_epistemic_claims_present")
