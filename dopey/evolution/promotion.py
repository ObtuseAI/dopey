"""Protected lifecycle-transition proposals before full research activation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.genome.schema import PromotionState
from dopey.protocols.identity import canonical_hash


def build_promotion_packet(
    evaluation: Mapping[str, Any],
    requested_state: PromotionState,
) -> dict[str, Any]:
    recommended = PromotionState(str(evaluation["recommended_state"]))
    allowed_requests = {
        PromotionState.SHADOW_ONLY: {PromotionState.SHADOW_ONLY},
        PromotionState.HELD_OUT_VALIDATED: {
            PromotionState.SHADOW_ONLY,
            PromotionState.HELD_OUT_VALIDATED,
        },
    }
    if requested_state not in allowed_requests.get(
        recommended, {PromotionState.SHADOW_ONLY}
    ):
        raise ValueError(
            "promotion request exceeds evaluated recommendation: "
            f"recommended={recommended.value}, requested={requested_state.value}"
        )
    body: dict[str, Any] = {
        "artifact_type": "research_genome_promotion_packet",
        "promotion_packet_version": "dopey-autonomous-lifecycle-transition-v2",
        "candidate_id": str(evaluation["candidate_id"]),
        "evaluation_id": str(evaluation["evaluation_id"]),
        "recommended_state": recommended.value,
        "requested_state": requested_state.value,
        "operator_decision": "NOT_REQUIRED",
        "transition_status": "proposed_not_persisted",
        "auto_applied": False,
        "automatic_research_state_transition_allowed": True,
        "automatic_research_activation_allowed": False,
        "human_review_required": False,
        "full_promotion_matrix_required_for_activation": True,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "packet_hash": canonical_hash(body)}
