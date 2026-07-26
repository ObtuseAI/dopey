"""Dopey pipeline aggression integration: maps the ProofWeightedAggressionGate to paper-only
promotion targets.

Allowed promotion targets in this pass: paper_candidate, research_only, rejected. Live
promotion is NEVER produced. The gate's promote/hold/demote is mapped: promote->paper_candidate
(strong proof earns paper execution only), hold->research_only (observe), demote->rejected.
"""
from __future__ import annotations

from dopey_edge.proof_weighted_aggression_gate import ProofWeightedAggressionGate, PromotionDecision

ALLOWED_TARGETS = {"paper_candidate", "research_only", "rejected"}

_GATE_TO_TARGET = {
    "promote": "paper_candidate",
    "hold": "research_only",
    "demote": "rejected",
}


def evaluate_paper_promotion(gate: ProofWeightedAggressionGate, genome: dict, proof: dict,
                             liquidity: float, regime: str, broker_capability: dict) -> PromotionDecision:
    """Run the gate and re-map its decision onto the allowed paper-only promotion targets.

    The PromotionDecision.decision field is overwritten with one of the allowed targets; the
    underlying aggression score and reasons are preserved. Live promotion is impossible here."""
    dec = gate.decide(genome, proof, liquidity, regime, broker_capability)
    target = _GATE_TO_TARGET.get(dec.decision, "rejected")
    if target not in ALLOWED_TARGETS:
        target = "rejected"
    # Hard boundary: never produce a live promotion target.
    return PromotionDecision(decision=target, aggression=dec.aggression, reasons=dec.reasons)
