"""Protected challenger evaluation over isolated replay and calibration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.genome.fitness import evaluate_genome_fitness
from dopey.genome.registry import genome_from_record
from dopey.protocols.identity import canonical_hash
from dopey.simulation.replay import validate_replay_artifact


def evaluate_evolution_candidate(
    candidate: Mapping[str, Any],
    replay: Mapping[str, Any],
    calibration_summary: Mapping[str, Any],
    efficiency_score: float,
) -> dict[str, Any]:
    genome = genome_from_record(dict(candidate["challenger_genome"]))
    candidate_id = str(candidate["candidate_id"])
    validate_replay_artifact(replay, candidate_id, genome.genome_id)
    fitness = evaluate_genome_fitness(
        genome,
        replay["causal_evaluation"],
        calibration_summary,
        efficiency_score,
    )
    evaluator_attestation_verified = False
    evidence_state = (
        "HELD_OUT_VALIDATED" if bool(fitness["held_out_validated"]) else "SHADOW_ONLY"
    )
    recommended_state = "SHADOW_ONLY"
    body: dict[str, Any] = {
        "artifact_type": "research_evolution_candidate_evaluation",
        "evolution_evaluator_version": "dopey-evolution-evaluator-v1",
        "candidate_id": candidate_id,
        "challenger_genome_id": genome.genome_id,
        "replay_hash": str(replay["reproducibility_hash"]),
        "fitness": fitness,
        "evidence_state_before_trust_cap": evidence_state,
        "recommended_state": recommended_state,
        "recommended_state_cap": str(replay.get("promotion_state_cap", "SHADOW_ONLY")),
        "evaluator_attestation_verified": evaluator_attestation_verified,
        "state_cap_reason": (
            "none"
            if evaluator_attestation_verified
            else "untrusted_local_replay_manifest"
        ),
        "evaluation_spec_hash": str(replay["evaluation_spec_hash"]),
        "evaluation_seed": int(replay["evaluation_seed"]),
        "randomization_policy": str(replay["randomization_policy"]),
        "observation_manifest_hash": str(replay["observation_manifest_hash"]),
        "optimizer_may_tune_evaluator": False,
        "automatic_research_state_transition_allowed": True,
        "automatic_research_activation_allowed": False,
        "human_review_required": False,
        "full_promotion_matrix_required_for_activation": True,
        "paper_only": True,
        "live_blocked": True,
    }
    content_hash = canonical_hash(body)
    return {
        **body,
        "evaluation_id": f"evolution-evaluation:{content_hash[:24]}",
        "content_hash": content_hash,
        "reproducibility_hash": content_hash,
    }
