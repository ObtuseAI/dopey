"""Dopey tournament aggression integration: paper-only promotion targets only.

Allowed decisions: rejected, research_only, paper_candidate, tournament_champion_paper_only.
Explicitly FORBIDDEN: micro_live, adaptive_live, live_candidate, any live promotion.
Tests must prove live promotion is impossible from the tournament path.
"""
from __future__ import annotations

from dopey_edge.proof_weighted_aggression_gate import ProofWeightedAggressionGate, PromotionDecision
from dopey_analysis.analysis_fusion import AnalysisFusionScore

ALLOWED_TARGETS = {"rejected", "research_only", "paper_candidate", "tournament_champion_paper_only"}
FORBIDDEN_LIVE_TARGETS = {"micro_live", "adaptive_live", "live_candidate", "live", "promote_live"}


def _tournament_proof_bundle(wf_overall: float, fusion: AnalysisFusionScore,
                             overfit_level: str) -> dict:
    """Translate tournament summary into a proof bundle the aggression gate can score."""
    return {
        "proof_strength": round(min(1.0, (wf_overall + fusion.overall_score) / 2.0), 6),
        "oos_edge": round(max(0.0, fusion.replay_confirmation_score), 6),
        "walk_forward_consistency": round(wf_overall, 6),
        "paper_fill_quality": round(fusion.microstructure_score, 6),
        "regime_alignment": fusion.macro_score >= 0.5,
        "capital_efficiency": round(fusion.overall_score, 6),
        "family_proof": overfit_level in {"none", "low"},
        "overfit_flag": overfit_level in {"moderate", "high"},
        "signal_decay": round(1.0 - fusion.replay_confirmation_score, 6),
        "drawdown_slope": round(1.0 - wf_overall, 6),
        "slippage_bps": int(round((1.0 - fusion.microstructure_score) * 100, 0)),
    }


def evaluate_tournament_promotion(gate: ProofWeightedAggressionGate, genome: dict,
                                  wf_overall: float, fusion: AnalysisFusionScore,
                                  overfit_level: str, liquidity: float, regime: str,
                                  broker_capability: dict,
                                  is_champion: bool = False) -> PromotionDecision:
    """Map the tournament summary onto a paper-only promotion decision.

    Live promotion is impossible here: any gate 'promote' is downgraded to a paper-only target;
    forbidden live targets raise. The champion may earn `tournament_champion_paper_only` (still
    paper-only; never live)."""
    proof = _tournament_proof_bundle(wf_overall, fusion, overfit_level)
    gate_decision = gate.decide(genome, proof, liquidity, regime, broker_capability)

    # Overfit gating
    if overfit_level == "high":
        target = "rejected"
        reasons = ["high overfit overrides gate"]
    elif overfit_level == "moderate":
        target = "research_only"
        reasons = ["moderate overfit caps at research_only"]
    elif gate_decision.decision == "promote":
        if is_champion and overfit_level in {"none", "low"} and fusion.overall_score >= 0.55:
            target = "tournament_champion_paper_only"
        else:
            target = "paper_candidate"
        reasons = []
    elif gate_decision.decision == "hold":
        target = "research_only"
        reasons = []
    else:  # demote
        target = "rejected"
        reasons = []

    if target in FORBIDDEN_LIVE_TARGETS:
        raise RuntimeError(f"tournament produced a forbidden live target: {target}")
    if target not in ALLOWED_TARGETS:
        target = "rejected"

    reasons = reasons + gate_decision.reasons + [
        f"walk_forward_overall={wf_overall}", f"analysis_fusion={fusion.overall_score}",
        f"overfit={overfit_level}", f"champion={is_champion}"]
    return PromotionDecision(decision=target, aggression=gate_decision.aggression, reasons=reasons)
