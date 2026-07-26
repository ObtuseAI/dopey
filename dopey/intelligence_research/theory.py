"""Promote replicated cognitive methods into conditional theory candidates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.protocols.identity import canonical_hash

from .schema import CognitiveHypothesis, CognitiveMethodEvidence


def build_theory_candidate(
    hypothesis: CognitiveHypothesis,
    evidence: CognitiveMethodEvidence,
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    if evaluation.get("method_id") != hypothesis["method_id"] or evidence["method_id"] != hypothesis["method_id"]:
        raise ValueError(
            "cognitive theory identity mismatch: "
            f"hypothesis={hypothesis['method_id']}, evidence={evidence['method_id']}, evaluation={evaluation.get('method_id')}"
        )
    if evaluation.get("automatic_cognitive_method_activation_allowed") is not True:
        raise ValueError(f"cognitive theory requires an activated method: method_id={hypothesis['method_id']}")
    conditional_law = (
        f"When the originating problem conditions hold, {hypothesis['method_statement']} "
        "improves calibrated task quality and information gain relative to the precommitted baseline."
    )
    body: dict[str, Any] = {
        "artifact_type": "cognitive_theory_candidate",
        "theory_version": "dopey-cognitive-theory-v1",
        "method_id": hypothesis["method_id"],
        "conditional_law": conditional_law,
        "scope": {
            "domain_count": evidence["domain_count"],
            "replication_count": evidence["replication_count"],
            "transfer_score": evidence["transfer_score"],
        },
        "supporting_evaluation_hash": str(evaluation["evaluation_hash"]),
        "known_falsification_conditions": list(hypothesis["falsification_conditions"]),
        "theory_state": "GENERAL_LAW_CANDIDATE",
        "publication_candidate": True,
        "authority_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "theory_id": f"cognitive-theory:{canonical_hash(body)[:24]}", "content_hash": canonical_hash(body)}
