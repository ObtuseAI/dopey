"""Build deterministic per-family reporting cards from DOPEY evidence."""
from __future__ import annotations

from .data_loader import ReportingEvidence
from .report_models import FamilyReportCard, StrategyReportCard


ALL_STRATEGY_FAMILIES = [
    "directional_convexity",
    "volatility_expansion",
    "volatility_compression",
    "short_duration_defined_risk",
]


def _float(record: dict, key: str) -> float:
    try:
        return round(float(record.get(key, 0.0)), 6)
    except (TypeError, ValueError):
        return 0.0


def _trust_profiles(evidence: ReportingEvidence) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for profile in evidence.meta_governor.get("family_trust_profiles", []) or []:
        if isinstance(profile, dict):
            family = str(profile.get("strategy_family", ""))
            if family:
                out[family] = profile
    return out


def _champion_family_rows(evidence: ReportingEvidence) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in evidence.champion.get("family_ranking", []) or []:
        if isinstance(row, dict):
            family = str(row.get("family", ""))
            if family:
                out[family] = row
    return out


def _fundamental_pressure(evidence: ReportingEvidence, family: str) -> float:
    row = (evidence.fundamental.get("average_family_scores", {}) or {}).get(family, {})
    if not isinstance(row, dict):
        return 0.0
    fragility = _float(row, "fragility_penalty") or _float(row, "average_fragility_penalty")
    contradiction = _float(row, "fundamental_contradiction_penalty") or _float(row, "average_fundamental_contradiction_penalty")
    return round(min(1.0, fragility + contradiction), 6)


def build_family_report_cards(
    evidence: ReportingEvidence,
    strategy_cards: list[StrategyReportCard],
) -> list[FamilyReportCard]:
    trust = _trust_profiles(evidence)
    champion_rows = _champion_family_rows(evidence)
    cards: list[FamilyReportCard] = []
    for family in ALL_STRATEGY_FAMILIES:
        members = [card for card in strategy_cards if card.strategy_family == family]
        best = sorted(members, key=lambda card: (-card.tournament_score, card.strategy_id))[0] if members else None
        average_score = round(sum(card.tournament_score for card in members) / len(members), 6) if members else 0.0
        row = champion_rows.get(family, {})
        profile = trust.get(family, {})
        best_regimes = list(profile.get("best_regimes", [])) or list(row.get("best_regimes", []))
        worst_regimes = list(profile.get("worst_regimes", [])) or list(row.get("worst_regimes", []))
        family_rank = int(row.get("rank", len(cards) + 1))
        score_table = {
            "average_score": average_score,
            "trust_score": _float(profile, "trust_score"),
            "failure_pressure": _float(profile, "failure_pressure"),
            "liquidity_pressure": _float(profile, "liquidity_pressure"),
            "macro_pressure": _float(profile, "macro_pressure"),
            "iv_pressure": _float(profile, "greek_iv_pressure"),
            "fundamental_pressure": _fundamental_pressure(evidence, family),
        }
        cards.append(FamilyReportCard(
            strategy_family=family,
            family_rank=family_rank,
            best_strategy=best.strategy_id if best else str(row.get("strategy_id", "")),
            average_score=average_score,
            best_regimes=[str(item) for item in best_regimes],
            worst_regimes=[str(item) for item in worst_regimes],
            family_strengths=[
                str(item)
                for item in (evidence.champion.get("family_strengths", {}) or {}).get(family, [])
            ],
            family_weaknesses=[
                str(item)
                for item in (evidence.champion.get("family_weaknesses", {}) or {}).get(family, [])
            ],
            overfit_pressure=_float(profile, "overfit_pressure"),
            failure_pressure=_float(profile, "failure_pressure"),
            liquidity_pressure=_float(profile, "liquidity_pressure"),
            macro_pressure=_float(profile, "macro_pressure"),
            iv_pressure=_float(profile, "greek_iv_pressure"),
            fundamental_pressure=_fundamental_pressure(evidence, family),
            recommended_research_action=str(profile.get("recommended_attention", "research_only")),
            summary_decision="paper-only family report; no live allocation",
            score_table=score_table,
            paper_only=True,
            live_allowed=False,
            known_limitations=[
                "family report is deterministic fixture aggregation",
                "family rank is research-only and does not allocate real capital",
            ],
            reproducibility_hash="",
        ))
    cards.sort(key=lambda card: (card.family_rank, card.strategy_family))
    return cards
