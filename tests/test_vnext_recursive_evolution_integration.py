"""Integration coverage for genome lineage, replay, evolution, and rollback."""

from __future__ import annotations

from pathlib import Path

import pytest

from dopey.chronos.replay import ReplayEra, ReplayRole
from dopey.constitution.mutation_protection import MutationProtectionViolation
from dopey.evolution.archive import append_archive_record
from dopey.evolution.evaluator import evaluate_evolution_candidate
from dopey.evolution.mutations import propose_genome_mutation
from dopey.evolution.rollback import build_rollback_plan
from dopey.evolution.runtime import (
    derive_recursive_evolution_seed_precommitment,
    run_recursive_evolution_cycle,
)
from dopey.genome.lineage import build_lineage
from dopey.genome.registry import append_genome, genome_from_record
from dopey.genome.schema import PromotionState, ResearchGenome, build_research_genome
from dopey.protocols.identity import canonical_hash
from dopey.simulation.replay import (
    build_replay_observation_manifest,
    run_isolated_replay,
)
from dopey.simulation.semantic_rng import semantic_seed


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


def _observations() -> list[dict[str, object]]:
    return [
        {
            "child_id": f"replay-{index}",
            "strategy_id": f"breakout-v{index % 2}",
            "setup_family": "volatility_squeeze_breakout",
            "exit_policy": "swing_exit",
            "dte_bucket": 14,
            "moneyness_bucket": "ATM",
            "direction": "bullish",
            "regime": "low_volatility" if index < 20 else "normal_volatility",
            "symbol": ("SPY", "QQQ", "IWM", "DIA")[index % 4],
            "era": "held-out-a" if index < 20 else "held-out-b",
            "signal_value": 1.0 if index % 3 else -1.0,
            "outcome_value": 0.02 if index % 3 else -0.015,
            "baseline_value": 0.001,
            "held_out": True,
            "contested_truth": index % 13 == 0,
        }
        for index in range(40)
    ]


def _manifest(
    candidate: dict[str, object],
    eras: tuple[ReplayEra, ...],
    observations: tuple[dict[str, object], ...],
) -> dict[str, object]:
    challenger = dict(candidate["challenger_genome"])
    return dict(
        build_replay_observation_manifest(
            str(candidate["candidate_id"]),
            str(challenger["genome_id"]),
            eras,
            observations,
            "recursive-evolution-integration-fixture-v1",
            canonical_hash({"dataset": "recursive-evolution-integration-fixture-v1"}),
            "protected-fixture-observation-generator-v1",
        )
    )


def test_recursive_evolution_is_isolated_append_only_and_autonomously_gated(
    tmp_path: Path,
) -> None:
    parent = _parent_genome()
    candidate = propose_genome_mutation(
        parent, "evidence_budgets", 800, "increase-budget-v1"
    )
    challenger = genome_from_record(dict(candidate["challenger_genome"]))
    eras = (
        ReplayEra("held-out-a", "2018-01-01", "2020-12-31", ReplayRole.HELD_OUT),
        ReplayEra("held-out-b", "2021-02-01", "2023-12-31", ReplayRole.HELD_OUT),
    )
    observation_manifest = _manifest(
        candidate,
        eras,
        tuple(_observations()),
    )
    calibration = {
        "settled_total": 0,
        "expected_calibration_error": None,
        "minimum_calibration_sample": 30,
    }
    specifications = (
        {
            "surface": "evidence_budgets",
            "value": 800,
            "operator_id": "increase-budget-v1",
        },
    )
    manifests = {str(candidate["candidate_id"]): observation_manifest}
    seed_precommitment = derive_recursive_evolution_seed_precommitment(
        parent,
        specifications,
        eras,
        manifests,
    )
    committed_seed = int(seed_precommitment["committed_root_seed"])
    cycle = run_recursive_evolution_cycle(
        parent,
        specifications,
        eras,
        manifests,
        calibration,
        200,
        committed_seed,
        20,
        0.05,
        100,
    )

    assert cycle["proposed_state_transition_count"] == 1
    assert cycle["automatic_state_transition_count"] == 0
    assert cycle["persisted_state_transition_count"] == 0
    assert cycle["automatic_research_activation_count"] == 0
    assert cycle["evaluations"][0]["recommended_state"] == "SHADOW_ONLY"
    assert cycle["evaluations"][0]["evaluator_attestation_verified"] is False
    assert (
        cycle["evaluations"][0]["state_cap_reason"] == "untrusted_local_replay_manifest"
    )
    assert cycle["cycle_hash"] == canonical_hash(
        {key: value for key, value in cycle.items() if key != "cycle_hash"}
    )
    assert cycle["promotion_packets"][0]["operator_decision"] == "NOT_REQUIRED"
    assert cycle["promotion_packets"][0]["transition_status"] == (
        "proposed_not_persisted"
    )
    assert cycle["promotion_packets"][0]["auto_applied"] is False
    assert (
        cycle["promotion_packets"][0]["automatic_research_activation_allowed"] is False
    )
    assert cycle["human_review_required"] is False
    assert (
        cycle["evaluations"][0]["fitness"]["optimizer_may_tune_fitness_judge"] is False
    )

    registry = tmp_path / "genomes.jsonl"
    assert append_genome(registry, parent)["append_status"] == "appended"
    assert (
        append_genome(registry, parent)["append_status"] == "already_present_identical"
    )
    assert append_genome(registry, challenger)["append_status"] == "appended"
    lineage = build_lineage((parent, challenger))
    assert lineage["acyclic"] is True and len(lineage["edges"]) == 1

    archive = tmp_path / "evolution.jsonl"
    evaluation = cycle["evaluations"][0]
    assert append_archive_record(archive, evaluation)["append_status"] == "appended"
    assert (
        append_archive_record(archive, evaluation)["append_status"]
        == "already_present_identical"
    )
    second_cycle = run_recursive_evolution_cycle(
        parent,
        specifications,
        eras,
        manifests,
        calibration,
        201,
        committed_seed,
        20,
        0.05,
        100,
    )
    second_evaluation = second_cycle["evaluations"][0]
    assert second_evaluation["candidate_id"] == evaluation["candidate_id"]
    assert second_evaluation["evaluation_id"] != evaluation["evaluation_id"]
    assert (
        second_evaluation["evaluation_spec_hash"] != evaluation["evaluation_spec_hash"]
    )
    assert (
        append_archive_record(archive, second_evaluation)["append_status"] == "appended"
    )
    rollback = build_rollback_plan(
        challenger, parent, "calibration_drift_or_forward_failure"
    )
    assert rollback["transition_status"] == "proposed_not_persisted"
    assert rollback["auto_applied"] is False

    with pytest.raises(MutationProtectionViolation):
        propose_genome_mutation(parent, "readiness_gate", "weaken", "unsafe-v1")


def test_recursive_evolution_uses_common_random_numbers_independent_of_order() -> None:
    parent = _parent_genome()
    specifications = (
        {
            "surface": "evidence_budgets",
            "value": 800,
            "operator_id": "increase-budget-v1",
        },
        {
            "surface": "stopping_policies",
            "value": "stop_on_low_utility_v2",
            "operator_id": "stopping-v2",
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
    eras = (
        ReplayEra("held-out-a", "2018-01-01", "2020-12-31", ReplayRole.HELD_OUT),
        ReplayEra("held-out-b", "2021-02-01", "2023-12-31", ReplayRole.HELD_OUT),
    )
    observations = {
        str(candidate["candidate_id"]): _manifest(
            candidate,
            eras,
            tuple(_observations()),
        )
        for candidate in candidates
    }
    calibration = {
        "settled_total": 0,
        "expected_calibration_error": None,
        "minimum_calibration_sample": 30,
    }
    seed_precommitment = derive_recursive_evolution_seed_precommitment(
        parent,
        specifications,
        eras,
        observations,
    )
    committed_seed = int(seed_precommitment["committed_root_seed"])

    forward = run_recursive_evolution_cycle(
        parent,
        specifications,
        eras,
        observations,
        calibration,
        200,
        committed_seed,
        20,
        0.05,
        100,
    )
    reversed_cycle = run_recursive_evolution_cycle(
        parent,
        tuple(reversed(specifications)),
        eras,
        observations,
        calibration,
        200,
        committed_seed,
        20,
        0.05,
        100,
    )

    assert forward["candidate_random_seeds"] == reversed_cycle["candidate_random_seeds"]
    assert len(set(forward["candidate_random_seeds"].values())) == 1
    assert (
        forward["randomization_policy"]
        == "immutable_context_fixed_seed_panel_common_random_numbers_v4"
    )
    assert forward["fixed_seed_panel"] == reversed_cycle["fixed_seed_panel"]
    assert {
        record["candidate_id"]: record["replay_hash"]
        for record in forward["evaluations"]
    } == {
        record["candidate_id"]: record["replay_hash"]
        for record in reversed_cycle["evaluations"]
    }


def test_recursive_evolution_rejects_swapped_observation_manifests() -> None:
    parent = _parent_genome()
    specifications = (
        {
            "surface": "evidence_budgets",
            "value": 800,
            "operator_id": "increase-budget-v1",
        },
        {
            "surface": "stopping_policies",
            "value": "stop_on_low_utility_v2",
            "operator_id": "stopping-v2",
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
    eras = (
        ReplayEra("held-out-a", "2018-01-01", "2020-12-31", ReplayRole.HELD_OUT),
        ReplayEra("held-out-b", "2021-02-01", "2023-12-31", ReplayRole.HELD_OUT),
    )
    swapped = {
        str(candidates[0]["candidate_id"]): _manifest(
            candidates[1],
            eras,
            tuple(_observations()),
        ),
        str(candidates[1]["candidate_id"]): _manifest(
            candidates[0],
            eras,
            tuple(_observations()),
        ),
    }

    with pytest.raises(ValueError, match="manifest candidate mismatch"):
        run_recursive_evolution_cycle(
            parent,
            specifications,
            eras,
            swapped,
            {
                "settled_total": 0,
                "expected_calibration_error": None,
                "minimum_calibration_sample": 30,
            },
            200,
            20260714,
            20,
            0.05,
            100,
        )


def test_recursive_evolution_rejects_frame_drift_and_self_asserted_trust() -> None:
    parent = _parent_genome()
    specifications = (
        {
            "surface": "evidence_budgets",
            "value": 800,
            "operator_id": "increase-budget-v1",
        },
        {
            "surface": "stopping_policies",
            "value": "stop_on_low_utility_v2",
            "operator_id": "stopping-v2",
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
    eras = (
        ReplayEra("held-out-a", "2018-01-01", "2020-12-31", ReplayRole.HELD_OUT),
        ReplayEra("held-out-b", "2021-02-01", "2023-12-31", ReplayRole.HELD_OUT),
    )
    frame_drift_manifests = {
        str(candidates[0]["candidate_id"]): _manifest(
            candidates[0],
            eras,
            tuple(_observations()),
        ),
        str(candidates[1]["candidate_id"]): _manifest(
            candidates[1],
            eras,
            tuple(_observations()[:-1]),
        ),
    }
    calibration = {
        "settled_total": 0,
        "expected_calibration_error": None,
        "minimum_calibration_sample": 30,
    }

    with pytest.raises(ValueError, match="one protected evaluation context"):
        run_recursive_evolution_cycle(
            parent,
            specifications,
            eras,
            frame_drift_manifests,
            calibration,
            200,
            20260714,
            20,
            0.05,
            100,
        )

    candidate_id = str(candidates[0]["candidate_id"])
    self_asserted = dict(frame_drift_manifests[candidate_id])
    self_asserted["evaluator_attestation_status"] = "verified"
    self_asserted_body = {
        key: value for key, value in self_asserted.items() if key != "manifest_hash"
    }
    self_asserted["manifest_hash"] = canonical_hash(self_asserted_body)
    with pytest.raises(ValueError, match="cannot self-assert trust"):
        run_recursive_evolution_cycle(
            parent,
            (specifications[0],),
            eras,
            {candidate_id: self_asserted},
            calibration,
            200,
            20260714,
            20,
            0.05,
            100,
        )


def test_replay_order_is_canonical_and_forged_attestation_is_rejected() -> None:
    parent = _parent_genome()
    candidate = propose_genome_mutation(
        parent,
        "evidence_budgets",
        800,
        "increase-budget-v1",
    )
    challenger = genome_from_record(dict(candidate["challenger_genome"]))
    eras = (
        ReplayEra("held-out-a", "2018-01-01", "2020-12-31", ReplayRole.HELD_OUT),
        ReplayEra("held-out-b", "2021-02-01", "2023-12-31", ReplayRole.HELD_OUT),
    )
    forward_manifest = _manifest(candidate, eras, tuple(_observations()))
    reversed_manifest = _manifest(
        candidate,
        eras,
        tuple(reversed(_observations())),
    )
    evaluation_spec_hash = canonical_hash(
        {"evaluation_spec": "order-invariant-integration-v1"}
    )
    policy = "protected_sampling_frame_common_random_numbers_v3"
    forward_replay = run_isolated_replay(
        challenger,
        str(candidate["candidate_id"]),
        eras,
        forward_manifest,
        evaluation_spec_hash,
        policy,
        200,
        20260714,
        20,
        0.05,
        100,
    )
    reversed_replay = run_isolated_replay(
        challenger,
        str(candidate["candidate_id"]),
        eras,
        reversed_manifest,
        evaluation_spec_hash,
        policy,
        200,
        20260714,
        20,
        0.05,
        100,
    )

    assert forward_replay["causal_evaluation"] == reversed_replay["causal_evaluation"]
    forged_replay = {
        **forward_replay,
        "evaluator_attestation_verified": True,
    }
    forged_body = {
        key: value
        for key, value in forged_replay.items()
        if key != "reproducibility_hash"
    }
    forged_replay["reproducibility_hash"] = canonical_hash(forged_body)
    with pytest.raises(ValueError, match="protected boundary"):
        evaluate_evolution_candidate(
            candidate,
            forged_replay,
            {
                "settled_total": 0,
                "expected_calibration_error": None,
                "minimum_calibration_sample": 30,
            },
            0.75,
        )


def test_recursive_evolution_rejects_duplicate_genomes_and_rng_label_collisions() -> (
    None
):
    parent = _parent_genome()
    duplicate_genome_specs = (
        {
            "surface": "evidence_budgets",
            "value": 800,
            "operator_id": "first-label",
        },
        {
            "surface": "evidence_budgets",
            "value": 800,
            "operator_id": "seed-shopping-label",
        },
    )
    eras = (
        ReplayEra("held-out-a", "2018-01-01", "2020-12-31", ReplayRole.HELD_OUT),
        ReplayEra("held-out-b", "2021-02-01", "2023-12-31", ReplayRole.HELD_OUT),
    )

    with pytest.raises(ValueError, match="duplicate challenger genomes"):
        run_recursive_evolution_cycle(
            parent,
            duplicate_genome_specs,
            eras,
            {},
            {
                "settled_total": 0,
                "expected_calibration_error": None,
                "minimum_calibration_sample": 30,
            },
            200,
            20260714,
            20,
            0.05,
            100,
        )

    assert semantic_seed(7, "a\x1fb") != semantic_seed(7, "a", "b")
    assert semantic_seed(7, 1) != semantic_seed(7, "1")
