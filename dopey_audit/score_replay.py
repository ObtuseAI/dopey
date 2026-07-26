"""Deterministic score replay for the offline evidence audit harness.

Verifies score self-consistency within stored records: ensemble weights must sum to the
stored `weights_sum`, accepted weights must sum to ~1.0, and re-applying the allocation
policy to stored candidates must still normalize to 1.0. These are reproducible invariant
checks that pass on honest records and flag tampering or score drift.
"""
from __future__ import annotations

from dopey_strategy_lab.allocation_policy import apply_allocation_policy
from dopey_strategy_lab.ensemble_models import StrategyAllocationCandidate

from .evidence_models import ScoreDriftFinding


SCORE_DRIFT_TOLERANCE = 1e-3
WEIGHTS_SUM_TOLERANCE = 1e-2


def _candidate_from_row(row: dict) -> StrategyAllocationCandidate:
    family = str(row.get("strategy_family", ""))
    return StrategyAllocationCandidate(
        strategy_id=str(row.get("strategy_id", "")),
        strategy_family=family,
        source_type=str(row.get("source_type", "tournament")),
        base_score=float(row.get("base_score", 0.0)),
        walk_forward_score=float(row.get("walk_forward_score", 0.0)),
        analysis_fusion_score=float(row.get("analysis_fusion_score", 0.0)),
        macro_fit_score=float(row.get("macro_fit_score", 0.0)),
        iv_surface_fit_score=float(row.get("iv_surface_fit_score", 0.0)),
        greek_fit_score=float(row.get("greek_fit_score", 0.0)),
        liquidity_robustness_score=float(row.get("liquidity_robustness_score", 0.0)),
        slippage_robustness_score=float(row.get("slippage_robustness_score", 0.0)),
        pattern_score=float(row.get("pattern_score", 0.0)),
        failure_pressure_score=float(row.get("failure_pressure_score", 0.0)),
        overfit_level=str(row.get("overfit_level", "unknown")),
        overfit_rank=int(row.get("overfit_rank", 3)),
        mutation_delta=float(row.get("mutation_delta", 0.0)),
        promotion_state=str(row.get("promotion_state", "entrant")),
        paper_only=bool(row.get("paper_only", True)),
        holdout_score=float(row.get("holdout_score", 0.0)),
        best_regimes=[str(r) for r in row.get("best_regimes", [])],
        worst_regimes=[str(r) for r in row.get("worst_regimes", [])],
    )


def replay_ensemble_policy_sum(ensemble_record: dict) -> float:
    """Re-apply allocation policy to stored candidates; return the recomputed weight sum."""
    candidates = [_candidate_from_row(row) for row in ensemble_record.get("candidates", [])]
    if not candidates:
        return 0.0
    policy = apply_allocation_policy(candidates)
    return policy.weights_sum


def audit_ensemble_score_consistency(ensemble_record: dict) -> list[ScoreDriftFinding]:
    """Verify stored ensemble weights are internally self-consistent (detects score drift)."""
    findings: list[ScoreDriftFinding] = []
    decisions = ensemble_record.get("decisions", [])
    stored_weights_sum = float(ensemble_record.get("weights_sum", 0.0))
    recomputed_decision_sum = round(sum(float(d.get("recommended_weight", 0.0)) for d in decisions), 6)
    if abs(recomputed_decision_sum - stored_weights_sum) > SCORE_DRIFT_TOLERANCE:
        findings.append(ScoreDriftFinding(
            case_id="score-ensemble-weights-sum",
            field="weights_sum",
            stored=stored_weights_sum,
            recomputed=recomputed_decision_sum,
            delta=round(abs(stored_weights_sum - recomputed_decision_sum), 6),
            severity="warning",
        ))
    accepted = [d for d in decisions if float(d.get("recommended_weight", 0.0)) > 0.0]
    if accepted:
        accepted_sum = round(sum(float(d.get("recommended_weight", 0.0)) for d in accepted), 6)
        if abs(accepted_sum - 1.0) > WEIGHTS_SUM_TOLERANCE:
            findings.append(ScoreDriftFinding(
                case_id="score-ensemble-accepted-invariant",
                field="accepted_weights_sum",
                stored=1.0,
                recomputed=accepted_sum,
                delta=round(abs(1.0 - accepted_sum), 6),
                severity="warning",
            ))
    return findings
