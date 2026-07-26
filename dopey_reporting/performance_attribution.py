"""Build deterministic performance attribution records for DOPEY reporting."""
from __future__ import annotations

from .data_loader import ReportingEvidence
from .performance_models import attribution_record_hash
from .report_models import PerformanceAttributionSummary, StrategyReportCard


def _decision_by_strategy(evidence: ReportingEvidence) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for decision in evidence.ensemble.get("decisions", []) or []:
        if isinstance(decision, dict):
            sid = str(decision.get("strategy_id", ""))
            if sid:
                out[sid] = dict(decision)
    for decision in evidence.meta_governor.get("decisions", []) or []:
        if isinstance(decision, dict):
            sid = str(decision.get("strategy_id", ""))
            if sid:
                merged = dict(out.get(sid, {}))
                merged.update(decision)
                out[sid] = merged
    return out


def _positive_negative_drivers(components: dict[str, float]) -> tuple[list[str], list[str]]:
    positive = [
        name for name, value in sorted(components.items(), key=lambda item: (-item[1], item[0]))
        if value > 0.0
    ][:5]
    negative = [
        name for name, value in sorted(components.items(), key=lambda item: (item[1], item[0]))
        if value < 0.0
    ][:5]
    return positive, negative


def build_performance_attribution(
    evidence: ReportingEvidence,
    strategy_cards: list[StrategyReportCard],
) -> list[PerformanceAttributionSummary]:
    decisions = _decision_by_strategy(evidence)
    records: list[PerformanceAttributionSummary] = []
    for card in strategy_cards:
        decision = decisions.get(card.strategy_id, {})
        breakdown = decision.get("score_breakdown", {}) if isinstance(decision.get("score_breakdown", {}), dict) else {}
        tournament_baseline = round(card.tournament_score * 0.20, 6)
        components = {
            "tournament_baseline": tournament_baseline,
            "walk_forward_consistency": round(card.walk_forward_consistency_score * 0.15, 6),
            "corpus_v2_holdout": round(card.corpus_v2_score * 0.10, 6),
            "mutation_delta": round(float(breakdown.get("mutation_bonus", 0.0)), 6),
            "failure_feedback": round(-card.failure_pressure_score * 0.10, 6),
            "ensemble_allocation": round(card.ensemble_weight * 0.10, 6),
            "meta_governor_trust": round(float(decision.get("proof_strength", 0.0)) * 0.10, 6),
            "macro_fit": round(card.macro_fit_score * 0.05, 6),
            "iv_surface_skew_term_fit": round(card.iv_surface_fit_score * 0.05, 6),
            "greeks_fit": round(card.greek_fit_score * 0.05, 6),
            "liquidity_slippage": round((card.liquidity_robustness_score + card.slippage_robustness_score) * 0.05, 6),
            "sector_peer_fundamental_fit": round(card.fundamental_fit_score * 0.05, 6),
            "pattern_confirmation": round(card.pattern_score * 0.04, 6),
            "overfit_penalty": -0.08 if card.overfit_level == "high" else (-0.03 if card.overfit_level == "moderate" else 0.0),
            "failure_pressure": round(-card.failure_pressure_score * 0.08, 6),
        }
        positives, negatives = _positive_negative_drivers(components)
        component_sum = round(sum(components.values()), 6)
        residual = round(card.tournament_score - component_sum, 6)
        base_record = {
            "record_id": f"attribution-{card.strategy_id}",
            "strategy_id": card.strategy_id,
            "strategy_family": card.strategy_family,
            **components,
            "top_positive_drivers": positives,
            "top_negative_drivers": negatives,
            "unexplained_residual": residual,
            "paper_only": True,
            "live_allowed": False,
        }
        deterministic_hash = attribution_record_hash(base_record)
        records.append(PerformanceAttributionSummary(
            record_id=base_record["record_id"],
            strategy_id=card.strategy_id,
            strategy_family=card.strategy_family,
            tournament_baseline=components["tournament_baseline"],
            walk_forward_consistency=components["walk_forward_consistency"],
            corpus_v2_holdout=components["corpus_v2_holdout"],
            mutation_delta=components["mutation_delta"],
            failure_feedback=components["failure_feedback"],
            ensemble_allocation=components["ensemble_allocation"],
            meta_governor_trust=components["meta_governor_trust"],
            macro_fit=components["macro_fit"],
            iv_surface_skew_term_fit=components["iv_surface_skew_term_fit"],
            greeks_fit=components["greeks_fit"],
            liquidity_slippage=components["liquidity_slippage"],
            sector_peer_fundamental_fit=components["sector_peer_fundamental_fit"],
            pattern_confirmation=components["pattern_confirmation"],
            overfit_penalty=components["overfit_penalty"],
            failure_pressure=components["failure_pressure"],
            top_positive_drivers=positives,
            top_negative_drivers=negatives,
            unexplained_residual=residual,
            deterministic_hash=deterministic_hash,
            paper_only=True,
            live_allowed=False,
            reproducibility_hash="",
        ))
    return records
