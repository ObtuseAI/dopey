"""Integration coverage for source-backed institutional research intelligence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from dopey.strategy_engineering.forward import (
    build_evaluation_manifest,
    generate_forward_candidates,
)
from dopey.strategy_engineering.institutional_intelligence import (
    allocate_research_gap_portfolio,
    synthesize_institutional_council,
)
from dopey.strategy_engineering.institutional_registry import (
    INSTITUTIONAL_DOCTRINES,
    INSTITUTIONAL_SOURCES,
    validate_institutional_registry,
)
from dopey.strategy_engineering.institutional_runtime import (
    run_institutional_intelligence_cycle,
)
from dopey.strategy_engineering.schema import (
    CouncilObservation,
    ResearchGap,
    ThesisEscrow,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parent / "fixtures" / "institutional_intelligence"
)


def _json(path: Path) -> dict[str, Any]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(
            f"institutional intelligence fixture must be an object: path={path}"
        )
    return cast(dict[str, Any], value)


def _council_case() -> tuple[ThesisEscrow, tuple[CouncilObservation, ...]]:
    raw = _json(FIXTURE_ROOT / "council_case.json")
    thesis = cast(ThesisEscrow, raw["thesis"])
    observations = tuple(
        cast(CouncilObservation, record) for record in raw["observations"]
    )
    return thesis, observations


def _gap_snapshot() -> tuple[ResearchGap, ...]:
    raw = _json(FIXTURE_ROOT / "audited_gap_snapshot_20260721.json")
    return tuple(cast(ResearchGap, record) for record in raw["gaps"])


def test_institutional_registry_is_primary_source_linked_and_explicit_about_misuse() -> (
    None
):
    validate_institutional_registry()

    assert len(INSTITUTIONAL_SOURCES) >= 20
    assert len(INSTITUTIONAL_DOCTRINES) >= 12
    assert all(source["url"].startswith("https://") for source in INSTITUTIONAL_SOURCES)
    assert all(
        doctrine["prohibited_inferences"] for doctrine in INSTITUTIONAL_DOCTRINES
    )
    assert any(
        doctrine["doctrine_id"] == "same_day_expiry_lifecycle"
        and "constitution_compatibility" in doctrine["required_checks"]
        for doctrine in INSTITUTIONAL_DOCTRINES
    )
    assert any(
        doctrine["doctrine_id"] == "regime_diagnostic_uncertainty"
        and "prospective_regime_validation" in doctrine["required_checks"]
        for doctrine in INSTITUTIONAL_DOCTRINES
    )
    assert any(
        doctrine["doctrine_id"] == "implied_assumption_inversion"
        and "assumption_perturbation_stability" in doctrine["required_checks"]
        for doctrine in INSTITUTIONAL_DOCTRINES
    )
    assert any(
        doctrine["doctrine_id"] == "causal_feature_budget"
        and "predictive_vs_causal_claim_boundary" in doctrine["required_checks"]
        for doctrine in INSTITUTIONAL_DOCTRINES
    )


def test_council_keeps_source_backed_support_research_only() -> None:
    thesis, observations = _council_case()

    result = synthesize_institutional_council(thesis, observations)

    assert (
        result["council_status"] == "research_candidate_requires_protected_evaluation"
    )
    assert result["effective_independent_group_count"] == 5
    assert result["escrow_failures"] == ()
    assert result["not_a_probability"] is True
    assert result["not_edge_evidence"] is True
    assert result["positive_promotion_allowed"] is False
    assert result["order_construction_allowed"] is False
    assert result["paper_only"] is True and result["live_blocked"] is True


def test_correlated_duplicate_observation_cannot_inflate_council_support() -> None:
    thesis, observations = _council_case()
    baseline = synthesize_institutional_council(thesis, observations)
    duplicate = cast(
        CouncilObservation,
        {
            **observations[0],
            "observation_id": "fixture:duplicate-fundamental-observation",
            "evidence_ids": ("fixture:duplicate-fundamental-evidence",),
        },
    )

    duplicated = synthesize_institutional_council(thesis, (*observations, duplicate))

    assert duplicated["raw_observation_count"] == baseline["raw_observation_count"] + 1
    assert (
        duplicated["effective_independent_group_count"]
        == baseline["effective_independent_group_count"]
    )
    assert duplicated["net_support"] == baseline["net_support"]
    assert duplicated["epistemic_strength"] == baseline["epistemic_strength"]
    assert duplicated["redundancy_discount"] > 0.0


def test_source_reputation_cannot_be_counted_as_candidate_edge_evidence() -> None:
    thesis, observations = _council_case()
    source_claim = cast(
        CouncilObservation,
        {
            **observations[0],
            "observation_id": "fixture:source-claim",
            "evidence_ids": ("primary-source:aqr-value-momentum-everywhere",),
        },
    )

    with pytest.raises(ValueError, match="cannot count a source claim"):
        synthesize_institutional_council(thesis, (source_claim,))


def test_zero_dte_thesis_fails_escrow_without_quote_and_same_day_lifecycle_doctrines() -> (
    None
):
    thesis = cast(
        ThesisEscrow,
        {
            "candidate_id": "fixture:zero-dte",
            "instrument_class": "zero_dte_option",
            "economic_mechanism": "fixture-only same-day convexity hypothesis",
            "base_rate_evidence_id": "fixture:base-rate",
            "opposed_thesis_id": "fixture:opposed",
            "kill_condition_ids": ("fixture:kill",),
            "cost_model_id": "fixture:cost",
            "capacity_model_id": "fixture:capacity",
            "forward_plan_id": "fixture:forward",
            "counterfactual_ids": ("no_trade", "fixture:simple", "fixture:opposed"),
            "required_lens_ids": ("validation",),
            "required_doctrine_ids": ("multi_axis_generalization",),
        },
    )

    result = synthesize_institutional_council(thesis, ())

    assert result["council_status"] == "abstain_incomplete_thesis_escrow"
    assert "missing_doctrine:option_quote_lifecycle" in result["escrow_failures"]
    assert "missing_doctrine:same_day_expiry_lifecycle" in result["escrow_failures"]
    assert result["positive_promotion_allowed"] is False


def test_unresolved_independent_contradiction_quarantines_candidate() -> None:
    thesis, observations = _council_case()
    contradicted = tuple(
        cast(
            CouncilObservation,
            {
                **observation,
                "direction": 1.0 if index < 2 else -1.0,
            },
        )
        for index, observation in enumerate(observations)
    )

    result = synthesize_institutional_council(thesis, contradicted)

    assert result["contradiction_index"] > 0.45
    assert result["council_status"] == "quarantined_unresolved_contradiction"
    assert result["order_construction_allowed"] is False


def test_gap_allocator_is_dependency_aware_and_allocates_research_not_capital() -> None:
    result = allocate_research_gap_portfolio(_gap_snapshot(), 12)
    by_id = {record["gap_id"]: record for record in result["gap_records"]}

    assert result["allocated_budget_units"] == 12
    assert len(result["domain_allocations"]) >= 3
    assert by_id["historical_option_quote_corpus"]["allocated_research_units"] == 0
    assert by_id["zero_dte_lifecycle_research"]["allocated_research_units"] == 0
    assert by_id["leaps_term_surface_research"]["allocated_research_units"] == 0
    assert by_id["zero_dte_lifecycle_research"]["blocking_dependency_ids"] == (
        "historical_option_quote_corpus",
    )
    assert result["allocation_target"] == "research_attention_only"
    assert result["capital_allocation_allowed"] is False
    assert all(
        record["capital_allocation_allowed"] is False
        for record in result["gap_records"]
    )


def test_institutional_cycle_writes_auditable_fail_closed_artifacts(
    tmp_path: Path,
) -> None:
    result = run_institutional_intelligence_cycle(
        (),
        {},
        _gap_snapshot(),
        tmp_path,
        12,
        datetime(2026, 7, 21, 18, 0, tzinfo=timezone.utc),
    )

    latest = _json(tmp_path / "latest_cycle.json")
    portfolio = _json(tmp_path / "latest_gap_portfolio.json")
    assert latest["cycle_hash"] == result["cycle_hash"]
    assert portfolio["portfolio_hash"] == result["gap_portfolio"]["portfolio_hash"]
    assert result["cycle_status"] == "complete_research_only_gap_ranked"
    assert result["source_claims_are_not_dopey_evidence"] is True
    assert result["positive_promotion_allowed"] is False
    assert result["order_construction_allowed"] is False
    assert result["paper_only"] is True and result["live_blocked"] is True


def test_every_generated_candidate_requires_institutional_escrow_and_counterfactuals() -> (
    None
):
    candidate = generate_forward_candidates(1, ())[0]

    manifest = build_evaluation_manifest(candidate)

    assert manifest["institutional_council_required"] is True
    assert manifest["minimum_independent_evidence_groups"] == 3
    assert manifest["required_counterfactuals"] == (
        "no_trade",
        "simplest_plausible_baseline",
        "opposed_thesis",
    )
    assert "candidate_escrow_complete" in manifest["required_checks"]
    assert "factor_residualization" in manifest["required_checks"]
    assert "purged_rolling_origin" in manifest["required_checks"]
    assert (
        "regime_model_diagnostic_only_until_forward_validated"
        in manifest["required_checks"]
    )
    assert "implied_assumption_inversion" in manifest["required_checks"]
    assert "feature_budget_and_causal_claim_boundary" in manifest["required_checks"]
    assert "variant_family_false_discovery_control" in manifest["sequential_inference"]
