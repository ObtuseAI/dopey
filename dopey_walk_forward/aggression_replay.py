"""Dopey walk-forward aggression integration: maps the walk-forward summary onto paper-only
promotion targets via the ProofWeightedAggressionGate.

Allowed promotion targets in this pass:
  - research_only
  - paper_candidate
  - replay_promoted_paper_candidate
  - rejected

Explicitly DISALLOWED (and impossible from this path):
  - micro_live
  - adaptive_live
  - any live promotion

Tests must prove live promotion is impossible.
"""
from __future__ import annotations

from dopey_edge.proof_weighted_aggression_gate import ProofWeightedAggressionGate, PromotionDecision
from .replay_models import WalkForwardScore, OverfitSignal, ReplayVerdict

ALLOWED_TARGETS = {"research_only", "paper_candidate", "replay_promoted_paper_candidate", "rejected"}
DISALLOWED_LIVE_TARGETS = {"micro_live", "adaptive_live", "live", "promote_live"}


def _replay_proof_bundle(score: WalkForwardScore, overfit: OverfitSignal) -> dict:
    """Translate the walk-forward summary into a proof bundle the aggression gate can score."""
    return {
        "proof_strength": round(min(1.0, score.overall), 6),
        "oos_edge": round(max(0.0, (score.validation_mean_pnl + score.holdout_mean_pnl) / 2.0), 6),
        "walk_forward_consistency": score.consistency_score,
        "paper_fill_quality": score.slippage_tolerance_score,
        "regime_alignment": score.regime_survival_score >= 0.5,
        "capital_efficiency": min(1.0, max(0.0, score.window_pass_rate)),
        "family_proof": overfit.level in {"none", "low"},
        "overfit_flag": overfit.level in {"moderate", "high"},
        "signal_decay": round(score.overfit_suspicion_score, 6),
        "drawdown_slope": round(min(1.0, score.overfit_suspicion_score), 6),
        "slippage_bps": int(round((1.0 - score.slippage_tolerance_score) * 100, 0)),
    }


def evaluate_replay_promotion(gate: ProofWeightedAggressionGate, genome: dict,
                              score: WalkForwardScore, overfit: OverfitSignal,
                              liquidity: float, regime: str, broker_capability: dict) -> ReplayVerdict:
    """Map the walk-forward summary onto a paper-only ReplayVerdict.

    The verdict is ALWAYS one of the allowed paper-only targets. Live promotion is impossible
    here: any gate 'promote' is downgraded to a paper-only target; disallowed live targets raise.
    """
    proof = _replay_proof_bundle(score, overfit)
    gate_decision = gate.decide(genome, proof, liquidity, regime, broker_capability)

    # Overfit gating: high overfit forces rejection regardless of gate score
    if overfit.level == "high":
        return ReplayVerdict(decision="rejected", reasons=["high overfit overrides gate"] + gate_decision.reasons)
    if overfit.level == "moderate":
        # moderate overfit can at most reach research_only
        return ReplayVerdict(decision="research_only", reasons=["moderate overfit caps at research_only"] + gate_decision.reasons)

    # Map gate decision onto paper-only replay targets
    if gate_decision.decision == "promote":
        # Strong replay + low/none overfit + holdout survived -> replay_promoted_paper_candidate
        if overfit.level in {"none", "low"} and score.holdout_mean_pnl >= 0 and score.overall >= 0.55:
            target = "replay_promoted_paper_candidate"
        else:
            target = "paper_candidate"
    elif gate_decision.decision == "hold":
        target = "research_only"
    else:  # demote
        target = "rejected"

    if target in DISALLOWED_LIVE_TARGETS:
        raise RuntimeError(f"walk-forward replay produced a disallowed live target: {target}")
    if target not in ALLOWED_TARGETS:
        target = "rejected"

    reasons = gate_decision.reasons + [f"walk_forward_overall={score.overall}",
                                        f"overfit={overfit.level}",
                                        f"holdout_pnl={score.holdout_mean_pnl}"]
    return ReplayVerdict(decision=target, reasons=reasons)
