"""Focused adversarial coverage for recursive-evolution replay integrity."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from dopey.chronos.replay import ReplayEra, ReplayRole
from dopey.evolution.evaluator import evaluate_evolution_candidate
from dopey.evolution.mutations import propose_genome_mutation
from dopey.evolution.runtime import run_recursive_evolution_cycle
from dopey.genome.registry import genome_from_record
from dopey.genome.schema import PromotionState, ResearchGenome, build_research_genome
from dopey.protocols.identity import canonical_hash
from dopey.simulation.replay import (
    build_replay_observation_manifest,
    run_isolated_replay,
)


def _parent_genome() -> ResearchGenome:
    agents = ("technical_evidence_agent", "adversarial_agent", "synthesizer_agent")
    return build_research_genome(
        (),
        0,
        agents,
        agents,
        ("RSI", "MACD_HISTOGRAM", "BREADTH"),
        ("daily", "weekly", "monthly"),
        700,
        "stop_on_nonpositive_marginal_utility",
        "reliability_bins_v1",
        "weakest_dimension_capped_synthesis",
        "deterministic",
        ("price", "cross_asset", "news"),
        "objective_template_with_boundary_agent",
        "uncertainty_weighted_world_model_v2",
        "breakout_regime_conditioned_v1",
        "deterministic_prompt_bundle_v1",
        "adversarial_veto_then_abstain",
        PromotionState.SHADOW_ONLY,
    )


def _eras() -> tuple[ReplayEra, ...]:
    return (
        ReplayEra("held-out-a", "2018-01-01", "2020-12-31", ReplayRole.HELD_OUT),
        ReplayEra("held-out-b", "2021-02-01", "2023-12-31", ReplayRole.HELD_OUT),
    )


def _observations() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "child_id": f"integrity-{index:02d}",
            "strategy_id": "breakout-v1",
            "setup_family": "volatility_squeeze_breakout",
            "exit_policy": "swing_exit",
            "dte_bucket": 14,
            "moneyness_bucket": "ATM",
            "regime": "normal_volatility",
            "symbol": ("SPY", "QQQ", "IWM", "DIA")[index % 4],
            "era": "held-out-a" if index < 12 else "held-out-b",
            "signal_value": 1.0 if index % 3 else -1.0,
            "outcome_value": 0.02 if index % 3 else -0.015,
            "baseline_value": 0.001,
            "held_out": True,
            "contested_truth": False,
        }
        for index in range(24)
    )


def _manifest(
    candidate: dict[str, Any],
    eras: tuple[ReplayEra, ...],
    observations: tuple[dict[str, object], ...],
) -> dict[str, Any]:
    challenger = dict(candidate["challenger_genome"])
    return dict(
        build_replay_observation_manifest(
            str(candidate["candidate_id"]),
            str(challenger["genome_id"]),
            eras,
            observations,
            "recursive-evolution-replay-integrity-v1",
            canonical_hash({"dataset": "recursive-evolution-replay-integrity-v1"}),
            "replay-integrity-observation-generator-v1",
        )
    )


def test_sampling_frame_distinguishes_missing_from_explicit_null() -> None:
    parent = _parent_genome()
    specifications = (
        {
            "surface": "evidence_budgets",
            "value": 800,
            "operator_id": "integrity-budget-v1",
        },
        {
            "surface": "stopping_policies",
            "value": "stop_on_low_utility_v2",
            "operator_id": "integrity-stopping-v1",
        },
    )
    candidates = tuple(
        propose_genome_mutation(
            parent,
            str(specification["surface"]),
            specification["value"],
            str(specification["operator_id"]),
        )
        for specification in specifications
    )
    eras = _eras()
    missing_direction = _observations()
    mixed_null_direction = tuple(
        (
            {**record, "direction": None}
            if index < len(missing_direction) // 2
            else dict(record)
        )
        for index, record in enumerate(missing_direction)
    )
    first_manifest = _manifest(candidates[0], eras, missing_direction)
    second_manifest = _manifest(candidates[1], eras, mixed_null_direction)

    assert (
        first_manifest["sampling_frame_hash"] != second_manifest["sampling_frame_hash"]
    )
    with pytest.raises(ValueError, match="one protected evaluation context"):
        run_recursive_evolution_cycle(
            parent,
            specifications,
            eras,
            {
                str(candidates[0]["candidate_id"]): first_manifest,
                str(candidates[1]["candidate_id"]): second_manifest,
            },
            {
                "settled_total": 0,
                "expected_calibration_error": None,
                "minimum_calibration_sample": 30,
            },
            40,
            20260724,
            10,
            0.05,
            10,
        )


def test_replay_recomputes_causal_evaluation_from_bound_inputs() -> None:
    parent = _parent_genome()
    candidate = propose_genome_mutation(
        parent,
        "evidence_budgets",
        800,
        "integrity-budget-v1",
    )
    challenger = genome_from_record(dict(candidate["challenger_genome"]))
    eras = _eras()
    manifest = _manifest(candidate, eras, _observations())
    replay = run_isolated_replay(
        challenger,
        str(candidate["candidate_id"]),
        eras,
        manifest,
        canonical_hash({"evaluation_spec": "replay-integrity-v1"}),
        "protected_sampling_frame_common_random_numbers_v3",
        40,
        20260724,
        10,
        0.05,
        10,
    )
    evaluation = evaluate_evolution_candidate(
        candidate,
        replay,
        {
            "settled_total": 30,
            "expected_calibration_error": 0.0,
            "minimum_calibration_sample": 30,
        },
        1.0,
    )

    assert evaluation["recommended_state"] == "SHADOW_ONLY"
    assert evaluation["evaluator_attestation_verified"] is False

    forged_replay = deepcopy(replay)
    forged_causal = dict(forged_replay["causal_evaluation"])
    forged_evaluations = [dict(record) for record in forged_causal["evaluations"]]
    forged_evaluations[0]["observed_gain"] = (
        float(forged_evaluations[0]["observed_gain"]) + 1.0
    )
    forged_causal["evaluations"] = forged_evaluations
    forged_causal_body = {
        key: value
        for key, value in forged_causal.items()
        if key != "reproducibility_hash"
    }
    forged_causal["reproducibility_hash"] = canonical_hash(forged_causal_body)
    forged_replay["causal_evaluation"] = forged_causal
    forged_replay_body = {
        key: value
        for key, value in forged_replay.items()
        if key != "reproducibility_hash"
    }
    forged_replay["reproducibility_hash"] = canonical_hash(forged_replay_body)

    with pytest.raises(
        ValueError,
        match="does not recompute from bound inputs",
    ):
        evaluate_evolution_candidate(
            candidate,
            forged_replay,
            {
                "settled_total": 30,
                "expected_calibration_error": 0.0,
                "minimum_calibration_sample": 30,
            },
            1.0,
        )
