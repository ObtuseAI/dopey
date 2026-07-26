"""Interpretable forward construction and quality-diversity archiving."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dopey.protocols.identity import canonical_hash

from .catalog import MECHANISMS, primitive_by_id
from .factor_language import build_factor_program
from .schema import EvaluationManifest, StrategyCandidate


def _candidate(
    mechanism_index: int,
    horizon: int,
    variant: int,
    reverse_hypothesis: Mapping[str, Any] | None,
) -> StrategyCandidate:
    mechanism = MECHANISMS[mechanism_index]
    primitives = mechanism["primitive_ids"]
    rotated = (
        primitives[variant % len(primitives) :]
        + primitives[: variant % len(primitives)]
    )
    selected = rotated[: min(3 + variant % 2, len(rotated))]
    base_expression = " AND ".join(
        f"rank({primitive_id}) >= governed_quantile" for primitive_id in selected
    )
    reverse_expression = (
        ""
        if reverse_hypothesis is None
        else f" AND meta({reverse_hypothesis['feature']}) {'>=' if float(reverse_hypothesis['correctness_effect']) >= 0.0 else '<'} {float(reverse_hypothesis['split_threshold']):.8g}"
    )
    expression = base_expression + reverse_expression
    complexity = round(
        min(1.0, (len(selected) + len(mechanism["regime_guards"])) / 20.0), 8
    )
    body = {
        "mechanism_id": mechanism["mechanism_id"],
        "horizon_trading_days": horizon,
        "primitive_ids": selected,
        "research_expression": expression,
        "regime_guards": mechanism["regime_guards"],
        "abstention_conditions": (
            *mechanism["regime_guards"],
            "abstain when point-in-time evidence or calibration gate fails",
        ),
        "failure_conditions": mechanism["failure_conditions"],
        "complexity_score": complexity,
        "source_ids": tuple(
            sorted(
                set(
                    mechanism["source_ids"]
                    + tuple(
                        source_id
                        for primitive_id in selected
                        for source_id in primitive_by_id(primitive_id)["source_ids"]
                    )
                )
            )
        ),
        "evidence_parent_ids": ()
        if reverse_hypothesis is None
        else (str(reverse_hypothesis["hypothesis_id"]),),
        "factor_program": build_factor_program(selected),
        "activation_state": "EXPERIMENTAL",
        "candidate_may_grade_itself": False,
        "positive_promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {"candidate_id": f"strategy-candidate:{canonical_hash(body)[:24]}", **body}  # type: ignore[return-value]


def generate_forward_candidates(
    candidate_budget: int,
    reverse_hypotheses: Sequence[Mapping[str, Any]],
) -> tuple[StrategyCandidate, ...]:
    if candidate_budget <= 0:
        raise ValueError(
            f"forward strategy candidate budget must be positive: candidate_budget={candidate_budget}"
        )
    records = tuple(
        _candidate(
            index % len(MECHANISMS),
            MECHANISMS[index % len(MECHANISMS)]["horizons"][
                (index // len(MECHANISMS))
                % len(MECHANISMS[index % len(MECHANISMS)]["horizons"])
            ],
            index // len(MECHANISMS),
            reverse_hypotheses[index % len(reverse_hypotheses)]
            if reverse_hypotheses
            else None,
        )
        for index in range(candidate_budget)
    )
    if len({record["candidate_id"] for record in records}) != len(records):
        raise ValueError(
            "forward strategy construction produced duplicate candidate identities"
        )
    return records


def build_quality_diversity_archive(
    candidates: Sequence[StrategyCandidate],
) -> dict[str, object]:
    cells: dict[str, StrategyCandidate] = {}
    for candidate in sorted(
        candidates,
        key=lambda record: (record["complexity_score"], record["candidate_id"]),
    ):
        complexity_cell = (
            "simple" if candidate["complexity_score"] <= 0.25 else "moderate"
        )
        horizon = candidate["horizon_trading_days"]
        horizon_cell = (
            "short" if horizon <= 5 else "medium" if horizon <= 20 else "long"
        )
        cell_id = f"{candidate['mechanism_id']}::{horizon_cell}::{complexity_cell}"
        cells.setdefault(cell_id, candidate)
    return {
        "artifact_type": "strategy_quality_diversity_archive",
        "archive_version": "dopey-strategy-quality-diversity-v1",
        "candidate_count": len(candidates),
        "occupied_cell_count": len(cells),
        "cells": tuple(
            {"cell_id": cell_id, "candidate_id": candidate["candidate_id"]}
            for cell_id, candidate in sorted(cells.items())
        ),
        "single_scalar_champion_selected": False,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def build_evaluation_manifest(candidate: StrategyCandidate) -> EvaluationManifest:
    return {
        "candidate_id": candidate["candidate_id"],
        "partition_sequence": (
            "VISIBLE_DEVELOPMENT",
            "PRIVATE_SELECTION",
            "EXTERNAL_GENERALIZATION",
            "FORWARD_PAPER_SETTLEMENT",
        ),
        "required_checks": (
            "determinism",
            "schema",
            "candidate_escrow_complete",
            "leakage_audit",
            "circular_shift_null",
            "random_entry_baseline",
            "no_trade_and_opposed_thesis",
            "factor_residualization",
            "effective_independent_evidence_groups",
            "reality_check_or_spa",
            "probability_of_backtest_overfitting",
            "deflated_sharpe",
            "purged_rolling_origin",
            "cost_and_capacity_surface",
            "execution_arrival_benchmark",
            "cross_symbol_transfer",
            "cross_era_transfer",
            "regime_holdout",
            "regime_model_diagnostic_only_until_forward_validated",
            "implied_assumption_inversion",
            "feature_budget_and_causal_claim_boundary",
            "instrument_lifecycle_dependencies",
            "contested_truth",
            "calibration",
            "immutable_thesis_correction",
        ),
        "sequential_inference": (
            "online_alpha_budget",
            "anytime_valid_confidence_sequence",
            "conformal_abstention",
            "multiple_testing_correction",
            "variant_family_false_discovery_control",
        ),
        "minimum_independent_evidence_groups": 3,
        "required_counterfactuals": (
            "no_trade",
            "simplest_plausible_baseline",
            "opposed_thesis",
        ),
        "institutional_council_required": True,
        "promotion_authority": "protected_operator_promotion_matrix",
        "candidate_may_grade_itself": False,
        "paper_only": True,
        "live_blocked": True,
    }
