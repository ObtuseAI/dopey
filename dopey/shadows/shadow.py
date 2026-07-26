"""Aggregate shadow guards into a downgrade-only control decision."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dopey.protocols.agents import AgentResult
from dopey.protocols.identity import canonical_hash

from .bias_detector import inspect_bias
from .calibration_guard import inspect_calibration
from .claim_guard import inspect_claim_quality
from .drift_detector import inspect_drift
from .provenance_guard import inspect_provenance
from .resource_guard import inspect_resources
from .scope_guard import inspect_scope


def run_shadow_controller(
    organism: Mapping[str, Any],
    agent_results: Sequence[AgentResult],
    evidence_records: Sequence[Mapping[str, Any]],
    metacognition: Mapping[str, Any],
    resource_ledger: Mapping[str, Any],
    event_time: str,
    maximum_evidence_age_hours: float,
) -> dict[str, Any]:
    guards = [
        inspect_provenance(evidence_records, agent_results),
        inspect_scope(organism, agent_results),
        inspect_drift(evidence_records, event_time, maximum_evidence_age_hours),
        inspect_bias(
            {str(key): float(value) for key, value in organism.get("hypotheses", {}).items()},
            sum(len(result.counterevidence) for result in agent_results),
        ),
        inspect_calibration(metacognition),
        inspect_resources(resource_ledger),
        inspect_claim_quality(agent_results),
    ]
    statuses = {str(guard["status"]) for guard in guards}
    if "terminate" in statuses:
        decision = "TERMINATE"
    elif "veto" in statuses:
        decision = "ABSTAIN"
    elif "request_more_evidence" in statuses:
        decision = "EXPAND_EVIDENCE"
    elif "request_adversary" in statuses:
        decision = "ADD_ADVERSARY"
    else:
        decision = "NO_DOWNGRADE"
    body: dict[str, Any] = {
        "artifact_type": "shadow_controller_result",
        "shadow_version": "dopey-shadow-controller-v1",
        "guards": guards,
        "shadow_decision": decision,
        "can_downgrade": True,
        "can_veto": True,
        "can_increase_readiness": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}
