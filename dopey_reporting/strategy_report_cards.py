"""Build deterministic per-strategy reporting cards from current DOPEY evidence."""
from __future__ import annotations

from .data_loader import EVIDENCE_PATHS, ReportingEvidence
from .report_models import EvidenceLayerExplanation, StrategyReportCard


def _float(record: dict, key: str) -> float:
    try:
        return round(float(record.get(key, 0.0)), 6)
    except (TypeError, ValueError):
        return 0.0


def _list(record: dict, key: str) -> list[str]:
    value = record.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _strategy_rows(evidence: ReportingEvidence) -> list[dict]:
    rows: dict[str, dict] = {}
    for candidate in evidence.ensemble.get("candidates", []) or []:
        sid = str(candidate.get("strategy_id", ""))
        if sid:
            rows[sid] = dict(candidate)
    for profile in evidence.meta_governor.get("strategy_proof_profiles", []) or []:
        sid = str(profile.get("strategy_id", ""))
        if sid:
            merged = dict(rows.get(sid, {}))
            merged.update(profile)
            rows[sid] = merged
    for row in evidence.champion.get("family_ranking", []) or []:
        sid = str(row.get("strategy_id", ""))
        if sid:
            merged = dict(rows.get(sid, {}))
            merged.setdefault("strategy_id", sid)
            merged.setdefault("strategy_family", str(row.get("family", "")))
            merged.setdefault("base_score", row.get("combined_score", 0.0))
            merged.setdefault("current_score", row.get("combined_score", 0.0))
            merged.setdefault("walk_forward_score", row.get("walk_forward", 0.0))
            merged.setdefault("best_regimes", evidence.champion.get("best_regimes_by_family", {}).get(str(row.get("family", "")), []))
            merged.setdefault("worst_regimes", evidence.champion.get("worst_regimes_by_family", {}).get(str(row.get("family", "")), []))
            rows[sid] = merged
    return sorted(rows.values(), key=lambda row: str(row.get("strategy_id", "")))


def _decision_by_strategy(evidence: ReportingEvidence) -> dict[str, dict]:
    decisions: dict[str, dict] = {}
    for decision in evidence.ensemble.get("decisions", []) or []:
        sid = str(decision.get("strategy_id", ""))
        if sid:
            decisions[sid] = dict(decision)
    for decision in evidence.meta_governor.get("decisions", []) or []:
        sid = str(decision.get("strategy_id", ""))
        if sid:
            merged = dict(decisions.get(sid, {}))
            merged.update(decision)
            decisions[sid] = merged
    return decisions


def _fundamental_score_by_family(evidence: ReportingEvidence) -> dict[str, float]:
    scores: dict[str, float] = {}
    for family, row in (evidence.fundamental.get("average_family_scores", {}) or {}).items():
        if isinstance(row, dict):
            scores[str(family)] = _float(row, "fundamental_fit_score") or _float(row, "average_fundamental_fit_score")
    return scores


def _failure_modes_by_family(evidence: ReportingEvidence) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    modes = evidence.failure_modes.get("failure_modes", []) or []
    sorted_modes = sorted(
        [m for m in modes if isinstance(m, dict)],
        key=lambda mode: (-int(mode.get("recurrence_count", 0)), str(mode.get("failure_mode_id", ""))),
    )
    for mode in sorted_modes:
        family = str(mode.get("affected_family", ""))
        mode_id = str(mode.get("failure_mode_id", ""))
        if family and mode_id:
            out.setdefault(family, []).append(mode_id)
    return {family: values[:5] for family, values in out.items()}


def _layer_explanations(evidence: ReportingEvidence) -> tuple[list[EvidenceLayerExplanation], list[EvidenceLayerExplanation]]:
    supporting: list[EvidenceLayerExplanation] = []
    contradicting: list[EvidenceLayerExplanation] = []
    artifact_by_layer = {
        "tournament": str(EVIDENCE_PATHS["tournament"]),
        "walk_forward_replay": str(EVIDENCE_PATHS["tournament"]),
        "mutation_population": str(EVIDENCE_PATHS["mutation"]),
        "failure_mode_miner": str(EVIDENCE_PATHS["failure_modes"]),
        "feedback_optimizer": str(EVIDENCE_PATHS["feedback"]),
        "iv_surface_skew_term": str(EVIDENCE_PATHS["iv_surface"]),
        "macro_event_fixtures": str(EVIDENCE_PATHS["macro_events"]),
        "sector_peer_fundamental_fixtures": str(EVIDENCE_PATHS["fundamental"]),
        "liquidity_slippage": str(EVIDENCE_PATHS["ensemble"]),
        "greeks_iv_validation": str(EVIDENCE_PATHS["ensemble"]),
        "pattern_fixture_intelligence": str(EVIDENCE_PATHS["champion"]),
        "ensemble_allocator": str(EVIDENCE_PATHS["ensemble"]),
        "meta_governor": str(EVIDENCE_PATHS["meta_governor"]),
        "champion_registry": str(EVIDENCE_PATHS["champion"]),
        "stronger_walk_forward_consistency": str(EVIDENCE_PATHS["stronger_consistency"]),
        "regime_holdout_corpus_v2": str(EVIDENCE_PATHS["corpus_v2"]),
    }
    for layer in evidence.meta_governor.get("evidence_layer_scores", []) or []:
        if not isinstance(layer, dict):
            continue
        name = str(layer.get("layer_name", ""))
        score = _float(layer, "score")
        contradiction = _float(layer, "contradiction_pressure")
        explanation = EvidenceLayerExplanation(
            layer_name=name,
            supports=[f"{name} score {score}"] if score >= 0.45 else [],
            contradicts=[f"{name} contradiction {contradiction}"] if contradiction > 0.0 or score < 0.45 else [],
            score_contribution=score,
            confidence=_float(layer, "confidence"),
            known_limitations=_list(layer, "known_limitations"),
            artifact_paths=[artifact_by_layer.get(name, "")] if artifact_by_layer.get(name, "") else [],
        )
        if score >= 0.45 and contradiction <= 0.0:
            supporting.append(explanation)
        if contradiction > 0.0 or 0.0 < score < 0.45:
            contradicting.append(explanation)
    supporting.sort(key=lambda item: (-item.score_contribution, item.layer_name))
    contradicting.sort(key=lambda item: (-item.score_contribution, item.layer_name))
    return supporting, contradicting


def _corpus_v2_by_strategy(evidence: ReportingEvidence) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in evidence.corpus_v2.get("strategy_consistency_scores", []) or []:
        if isinstance(row, dict):
            sid = str(row.get("strategy_id", ""))
            if sid:
                out[sid] = _float(row, "overall")
    return out


def build_strategy_report_cards(evidence: ReportingEvidence) -> list[StrategyReportCard]:
    decisions = _decision_by_strategy(evidence)
    fundamental_by_family = _fundamental_score_by_family(evidence)
    failures_by_family = _failure_modes_by_family(evidence)
    supporting_layers, contradicting_layers = _layer_explanations(evidence)
    corpus_scores = _corpus_v2_by_strategy(evidence)
    cards: list[StrategyReportCard] = []
    for row in _strategy_rows(evidence):
        sid = str(row.get("strategy_id", ""))
        family = str(row.get("strategy_family", ""))
        decision = decisions.get(sid, {})
        meta_decision = str(decision.get("decision", "hold_research_only"))
        tournament_score = _float(row, "current_score") or _float(row, "base_score") or _float(row, "combined_score")
        wf_score = _float(row, "walk_forward_consistency") or _float(row, "consistency_score") or _float(row, "walk_forward_score")
        corpus_score = corpus_scores.get(sid, _float(row, "corpus_v2_consistency_score"))
        macro = _float(row, "macro_fit") or _float(row, "macro_fit_score")
        iv = _float(row, "iv_surface_fit") or _float(row, "iv_surface_fit_score")
        greek = _float(row, "greek_fit") or _float(row, "greek_fit_score")
        liquidity = _float(row, "liquidity_robustness") or _float(row, "liquidity_robustness_score")
        slippage = _float(row, "slippage_robustness") or _float(row, "slippage_robustness_score")
        pattern = _float(row, "pattern_fit") or _float(row, "pattern_score")
        failure_pressure = _float(row, "failure_pressure") or _float(row, "failure_pressure_score")
        score_table = {
            "tournament_score": tournament_score,
            "walk_forward_consistency_score": wf_score,
            "corpus_v2_score": corpus_score,
            "macro_fit_score": macro,
            "iv_surface_fit_score": iv,
            "greek_fit_score": greek,
            "fundamental_fit_score": fundamental_by_family.get(family, 0.0),
            "liquidity_robustness_score": liquidity,
            "slippage_robustness_score": slippage,
            "pattern_score": pattern,
            "failure_pressure_score": failure_pressure,
        }
        cards.append(StrategyReportCard(
            strategy_id=sid,
            strategy_family=family,
            promotion_state=str(row.get("promotion_state", decision.get("eligible_tier", "research_only"))),
            tournament_score=tournament_score,
            walk_forward_consistency_score=wf_score,
            corpus_v2_score=corpus_score,
            macro_fit_score=macro,
            iv_surface_fit_score=iv,
            greek_fit_score=greek,
            fundamental_fit_score=fundamental_by_family.get(family, 0.0),
            liquidity_robustness_score=liquidity,
            slippage_robustness_score=slippage,
            pattern_score=pattern,
            failure_pressure_score=failure_pressure,
            overfit_level=str(row.get("overfit_level", "unknown")),
            ensemble_weight=_float(row, "ensemble_weight") or _float(decision, "recommended_weight"),
            meta_governor_decision=meta_decision,
            top_supporting_evidence=[layer.layer_name for layer in supporting_layers[:5]],
            top_contradicting_evidence=[layer.layer_name for layer in contradicting_layers[:5]],
            top_failure_modes=failures_by_family.get(family, []),
            best_regimes=_list(row, "best_regimes"),
            worst_regimes=_list(row, "worst_regimes"),
            paper_only=True,
            live_allowed=False,
            summary_decision=f"{meta_decision}; paper-only report card",
            score_table=score_table,
            evidence_support=supporting_layers[:6],
            evidence_contradiction=contradicting_layers[:6],
            scenario_explanations=[
                f"best regimes: {', '.join(_list(row, 'best_regimes')[:3])}",
                f"worst regimes: {', '.join(_list(row, 'worst_regimes')[:3])}",
            ],
            known_limitations=[
                "deterministic fixture aggregation only",
                "not live performance evidence",
                "no broker execution or live promotion authority",
            ],
            reproducibility_hash="",
        ))
    cards.sort(key=lambda card: (-card.tournament_score, card.strategy_id))
    return cards
