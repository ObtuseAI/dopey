"""One bounded recursive-evolution cycle with protected transition proposals."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

from dopey.chronos.replay import ReplayEra
from dopey.genome.fitness import evaluate_genome_fitness
from dopey.genome.registry import genome_from_record
from dopey.genome.schema import PromotionState, ResearchGenome
from dopey.protocols.identity import canonical_hash
from dopey.simulation.replay import (
    REPLAY_EVALUATOR_VERSION,
    run_isolated_replay,
    validate_replay_observation_manifest,
)
from dopey.simulation.semantic_rng import semantic_seed

from .challenger import compare_challenger
from .evaluator import evaluate_evolution_candidate
from .mutations import propose_genome_mutation
from .population import build_population
from .promotion import build_promotion_packet


SEED_PRECOMMITMENT_VERSION: Final[str] = (
    "dopey-recursive-evolution-seed-precommitment-v1"
)
FIXED_SEED_PANEL_SIZE: Final[int] = 3
RANDOMIZATION_POLICY: Final[str] = (
    "immutable_context_fixed_seed_panel_common_random_numbers_v4"
)
CONSERVATIVE_PANEL_SELECTION_POLICY: Final[str] = (
    "minimum_fitness_score_then_fixed_panel_index_v1"
)
ValidatedCandidate = tuple[dict[str, Any], ResearchGenome, Mapping[str, Any]]
EvaluationContext = tuple[str, str, str, str, str]


def _prepare_evolution_cycle(
    parent: ResearchGenome,
    mutation_specs: Sequence[Mapping[str, Any]],
    eras: tuple[ReplayEra, ...],
    observation_manifests_by_candidate: Mapping[str, Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    list[ValidatedCandidate],
    EvaluationContext,
]:
    candidates = [
        propose_genome_mutation(
            parent,
            str(spec["surface"]),
            spec["value"],
            str(spec["operator_id"]),
        )
        for spec in mutation_specs
    ]
    population = build_population(candidates)
    candidate_ids = {str(candidate["candidate_id"]) for candidate in candidates}
    orphan_manifest_ids = sorted(
        set(observation_manifests_by_candidate) - candidate_ids
    )
    if orphan_manifest_ids:
        raise ValueError(
            "evolution cycle received orphan replay observation manifests: "
            f"candidate_ids={orphan_manifest_ids}"
        )
    validated_candidates: list[ValidatedCandidate] = []
    evaluation_contexts: set[EvaluationContext] = set()
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        manifest = observation_manifests_by_candidate.get(candidate_id)
        if manifest is None:
            raise ValueError(
                "evolution cycle is missing replay observation manifest: "
                f"candidate_id={candidate_id}"
            )
        challenger = genome_from_record(dict(candidate["challenger_genome"]))
        validate_replay_observation_manifest(
            manifest,
            candidate_id,
            challenger.genome_id,
            eras,
        )
        evaluation_contexts.add(
            (
                str(manifest["dataset_id"]),
                str(manifest["dataset_content_hash"]),
                str(manifest["era_set_hash"]),
                str(manifest["sampling_frame_hash"]),
                str(manifest["observation_generator_version"]),
            )
        )
        validated_candidates.append((candidate, challenger, manifest))
    if len(evaluation_contexts) != 1:
        raise ValueError(
            "evolution candidates must share one protected evaluation context: "
            f"context_count={len(evaluation_contexts)}"
        )
    return (
        candidates,
        population,
        validated_candidates,
        next(iter(evaluation_contexts)),
    )


def _seed_precommitment(
    parent: ResearchGenome,
    evaluation_context: EvaluationContext,
) -> dict[str, Any]:
    (
        dataset_content_hash,
        era_set_hash,
        sampling_frame_hash,
    ) = (
        evaluation_context[1],
        evaluation_context[2],
        evaluation_context[3],
    )
    body: dict[str, Any] = {
        "artifact_type": "recursive_evolution_seed_precommitment",
        "seed_precommitment_version": SEED_PRECOMMITMENT_VERSION,
        "parent_genome_id": parent.genome_id,
        "dataset_content_hash": dataset_content_hash,
        "era_set_hash": era_set_hash,
        "sampling_frame_hash": sampling_frame_hash,
        "replay_evaluator_version": REPLAY_EVALUATOR_VERSION,
        "fixed_seed_panel_size": FIXED_SEED_PANEL_SIZE,
        "randomization_policy": RANDOMIZATION_POLICY,
        "caller_selectable_randomization": False,
        "paper_only": True,
        "live_blocked": True,
    }
    precommitment_hash = canonical_hash(body)
    committed_root_seed = int(precommitment_hash[:16], 16)
    seed_panel = [
        semantic_seed(
            committed_root_seed,
            SEED_PRECOMMITMENT_VERSION,
            "fixed_seed_panel",
            panel_index,
        )
        for panel_index in range(FIXED_SEED_PANEL_SIZE)
    ]
    if len(set(seed_panel)) != FIXED_SEED_PANEL_SIZE:
        raise RuntimeError(
            "recursive-evolution deterministic seed panel contains a collision: "
            f"precommitment_hash={precommitment_hash}, seed_panel={seed_panel}"
        )
    return {
        **body,
        "precommitment_hash": precommitment_hash,
        "committed_root_seed": committed_root_seed,
        "seed_panel": seed_panel,
        "seed_commitment_id": (
            f"recursive-evolution-seed-commitment:{precommitment_hash[:24]}"
        ),
    }


def derive_recursive_evolution_seed_precommitment(
    parent: ResearchGenome,
    mutation_specs: Sequence[Mapping[str, Any]],
    eras: tuple[ReplayEra, ...],
    observation_manifests_by_candidate: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    _candidates, _population, _validated, evaluation_context = _prepare_evolution_cycle(
        parent,
        mutation_specs,
        eras,
        observation_manifests_by_candidate,
    )
    return _seed_precommitment(
        parent,
        evaluation_context,
    )


def _require_committed_seed(
    supplied_seed: int,
    seed_precommitment: Mapping[str, Any],
) -> int:
    if isinstance(supplied_seed, bool) or not isinstance(supplied_seed, int):
        raise TypeError(
            "recursive-evolution supplied seed must be an integer: "
            f"actual={type(supplied_seed).__name__}"
        )
    committed_root_seed = seed_precommitment.get("committed_root_seed")
    if not isinstance(committed_root_seed, int) or isinstance(
        committed_root_seed,
        bool,
    ):
        raise TypeError(
            "recursive-evolution seed precommitment has an invalid root seed: "
            f"actual={type(committed_root_seed).__name__}"
        )
    if supplied_seed != committed_root_seed:
        raise ValueError(
            "recursive-evolution caller seed does not match the immutable "
            "evaluation-context precommitment: "
            f"supplied={supplied_seed}, committed={committed_root_seed}, "
            f"precommitment_hash={seed_precommitment.get('precommitment_hash')}"
        )
    return committed_root_seed


def _require_fixed_seed_panel(
    seed_precommitment: Mapping[str, Any],
) -> tuple[int, ...]:
    raw_seed_panel = seed_precommitment.get("seed_panel")
    if not isinstance(raw_seed_panel, list):
        raise TypeError(
            "recursive-evolution seed precommitment panel must be an array: "
            f"actual={type(raw_seed_panel).__name__}"
        )
    if len(raw_seed_panel) != FIXED_SEED_PANEL_SIZE:
        raise ValueError(
            "recursive-evolution seed precommitment panel has the wrong size: "
            f"expected={FIXED_SEED_PANEL_SIZE}, actual={len(raw_seed_panel)}"
        )
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in raw_seed_panel
    ):
        raise TypeError(
            "recursive-evolution seed precommitment panel requires integer seeds"
        )
    seed_panel = tuple(raw_seed_panel)
    if len(set(seed_panel)) != FIXED_SEED_PANEL_SIZE:
        raise ValueError(
            "recursive-evolution seed precommitment panel requires unique seeds: "
            f"seed_panel={seed_panel}"
        )
    return seed_panel


def _conservative_panel_evaluation(
    evaluations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(evaluations) != FIXED_SEED_PANEL_SIZE:
        raise ValueError(
            "recursive-evolution fixed seed panel is incomplete: "
            f"expected={FIXED_SEED_PANEL_SIZE}, actual={len(evaluations)}"
        )
    scored: list[tuple[float, int, Mapping[str, Any]]] = []
    for panel_index, evaluation in enumerate(evaluations):
        fitness = evaluation.get("fitness")
        if not isinstance(fitness, Mapping):
            raise TypeError("recursive-evolution panel evaluation lacks fitness")
        fitness_score = fitness.get("fitness_score")
        if (
            isinstance(fitness_score, bool)
            or not isinstance(fitness_score, (int, float))
            or not math.isfinite(float(fitness_score))
        ):
            raise ValueError(
                "recursive-evolution panel fitness score must be finite: "
                f"actual={fitness_score}"
            )
        scored.append(
            (
                float(fitness_score),
                panel_index,
                evaluation,
            )
        )
    _score, _panel_index, selected = min(
        scored,
        key=lambda item: (item[0], item[1]),
    )
    return dict(selected)


def _build_attempt_commitment(
    candidates: Sequence[Mapping[str, Any]],
    seed_precommitment: Mapping[str, Any],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "artifact_type": "recursive_evolution_attempt_commitment",
        "attempt_commitment_version": (
            "dopey-recursive-evolution-attempt-commitment-v1"
        ),
        "seed_precommitment_hash": seed_precommitment["precommitment_hash"],
        "candidate_ids": sorted(
            str(candidate["candidate_id"]) for candidate in candidates
        ),
        "challenger_genome_ids": sorted(
            str(candidate["challenger_genome"]["genome_id"]) for candidate in candidates
        ),
        "commitment_mode": "deterministic_cycle_artifact_no_external_ledger",
        "append_before_return_status": "not_appended_no_explicit_ledger_path",
        "append_before_return_reason": (
            "runtime_has_no_authorized_repository_root_or_attempt_ledger_path"
        ),
        "cycle_artifact_commits_complete_fixed_seed_panel": True,
        "identical_seed_context_produces_identical_panel": True,
        "caller_seed_shopping_within_identical_seed_context_possible": False,
        "external_signed_seed_commitment_present": False,
        "paper_only": True,
        "live_blocked": True,
    }
    attempt_hash = canonical_hash(body)
    return {
        **body,
        "attempt_id": f"recursive-evolution-attempt:{attempt_hash[:24]}",
        "attempt_hash": attempt_hash,
    }


def run_recursive_evolution_cycle(
    parent: ResearchGenome,
    mutation_specs: Sequence[Mapping[str, Any]],
    eras: tuple[ReplayEra, ...],
    observation_manifests_by_candidate: Mapping[str, Mapping[str, Any]],
    calibration_summary: Mapping[str, Any],
    bootstrap_iterations: int,
    seed: int,
    null_shifts: int,
    familywise_alpha: float,
    minimum_sample: int,
) -> dict[str, Any]:
    (
        candidates,
        population,
        validated_candidates,
        evaluation_context,
    ) = _prepare_evolution_cycle(
        parent,
        mutation_specs,
        eras,
        observation_manifests_by_candidate,
    )
    (
        dataset_id,
        dataset_content_hash,
        era_set_hash,
        sampling_frame_hash,
        generator_version,
    ) = evaluation_context
    seed_precommitment = _seed_precommitment(
        parent,
        evaluation_context,
    )
    committed_root_seed = _require_committed_seed(seed, seed_precommitment)
    seed_panel = _require_fixed_seed_panel(seed_precommitment)
    attempt_commitment = _build_attempt_commitment(
        candidates,
        seed_precommitment,
    )
    shared_evaluation_seed = seed_panel[0]
    evaluation_spec_body: dict[str, Any] = {
        "artifact_type": "recursive_evolution_evaluation_specification",
        "evaluation_spec_version": "dopey-recursive-evolution-evaluation-spec-v2",
        "parent_genome_id": parent.genome_id,
        "dataset_id": dataset_id,
        "dataset_content_hash": dataset_content_hash,
        "era_set_hash": era_set_hash,
        "sampling_frame_hash": sampling_frame_hash,
        "observation_generator_version": generator_version,
        "replay_evaluator_version": REPLAY_EVALUATOR_VERSION,
        "calibration_summary_hash": canonical_hash(dict(calibration_summary)),
        "bootstrap_iterations": bootstrap_iterations,
        "root_seed": committed_root_seed,
        "shared_evaluation_seed": shared_evaluation_seed,
        "fixed_seed_panel": list(seed_panel),
        "fixed_seed_panel_size": FIXED_SEED_PANEL_SIZE,
        "seed_precommitment_version": SEED_PRECOMMITMENT_VERSION,
        "seed_precommitment_hash": seed_precommitment["precommitment_hash"],
        "caller_seed_validation": "matched_immutable_precommitment",
        "null_shifts": null_shifts,
        "familywise_alpha": familywise_alpha,
        "minimum_sample": minimum_sample,
        "randomization_policy": RANDOMIZATION_POLICY,
        "panel_selection_policy": CONSERVATIVE_PANEL_SELECTION_POLICY,
        "paper_only": True,
        "live_blocked": True,
    }
    evaluation_spec_hash = canonical_hash(evaluation_spec_body)
    evaluations: list[dict[str, Any]] = []
    packets: list[dict[str, Any]] = []
    parent_fitness = evaluate_genome_fitness(
        parent,
        {"evaluations": []},
        calibration_summary,
        0.0,
    )
    comparisons: list[dict[str, Any]] = []
    candidate_random_seeds: dict[str, int] = {}
    candidate_seed_panels: dict[str, list[int]] = {}
    candidate_seed_panel_evaluations: dict[str, list[dict[str, Any]]] = {}
    candidate_selected_evaluation_seeds: dict[str, int] = {}
    for candidate, challenger, manifest in validated_candidates:
        candidate_id = str(candidate["candidate_id"])
        candidate_random_seeds[candidate_id] = shared_evaluation_seed
        candidate_seed_panels[candidate_id] = list(seed_panel)
        panel_evaluations: list[dict[str, Any]] = []
        for evaluation_seed in seed_panel:
            replay = run_isolated_replay(
                challenger,
                candidate_id,
                eras,
                manifest,
                evaluation_spec_hash,
                RANDOMIZATION_POLICY,
                bootstrap_iterations,
                evaluation_seed,
                null_shifts,
                familywise_alpha,
                minimum_sample,
            )
            panel_evaluations.append(
                evaluate_evolution_candidate(
                    candidate,
                    replay,
                    calibration_summary,
                    0.75,
                )
            )
        candidate_seed_panel_evaluations[candidate_id] = panel_evaluations
        selected_evaluation = _conservative_panel_evaluation(panel_evaluations)
        selected_seed = int(selected_evaluation["evaluation_seed"])
        candidate_selected_evaluation_seeds[candidate_id] = selected_seed
        evaluations.append(selected_evaluation)
        comparisons.append(compare_challenger(parent_fitness, selected_evaluation))
        packets.append(
            build_promotion_packet(
                selected_evaluation,
                PromotionState(str(selected_evaluation["recommended_state"])),
            )
        )
    body: dict[str, Any] = {
        "artifact_type": "bounded_recursive_evolution_cycle",
        "evolution_cycle_version": "dopey-recursive-evolution-v3",
        "parent_genome_id": parent.genome_id,
        "population": population,
        "candidates": candidates,
        "evaluations": evaluations,
        "comparisons": comparisons,
        "promotion_packets": packets,
        "evaluation_context": {
            "dataset_id": dataset_id,
            "dataset_content_hash": dataset_content_hash,
            "era_set_hash": era_set_hash,
            "sampling_frame_hash": sampling_frame_hash,
            "observation_generator_version": generator_version,
        },
        "evaluation_specification": {
            **evaluation_spec_body,
            "evaluation_spec_hash": evaluation_spec_hash,
        },
        "seed_precommitment": seed_precommitment,
        "attempt_commitment": attempt_commitment,
        "randomization_policy": RANDOMIZATION_POLICY,
        "panel_selection_policy": CONSERVATIVE_PANEL_SELECTION_POLICY,
        "root_random_seed": committed_root_seed,
        "shared_evaluation_seed": shared_evaluation_seed,
        "fixed_seed_panel": list(seed_panel),
        "candidate_random_seeds": candidate_random_seeds,
        "candidate_seed_panels": candidate_seed_panels,
        "candidate_seed_panel_evaluations": candidate_seed_panel_evaluations,
        "candidate_selected_evaluation_seeds": candidate_selected_evaluation_seeds,
        "caller_seed_validated_against_precommitment": True,
        "caller_selectable_randomization": False,
        "trade_authority_granted": False,
        "proposed_state_transition_count": len(packets),
        "automatic_state_transition_count": 0,
        "persisted_state_transition_count": 0,
        "automatic_research_activation_count": 0,
        "recursive_levels_available": [0, 1, 2, 3, 4, 5],
        "human_review_required": False,
        "full_promotion_matrix_required_for_activation": True,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "cycle_hash": canonical_hash(body)}
