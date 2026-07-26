"""Regime explainability cards for static DOPEY reporting."""
from __future__ import annotations

from .data_loader import ReportingEvidence
from .report_models import RegimeReportCard, StrategyReportCard


def _top_strategy(strategy_cards: list[StrategyReportCard], family: str) -> str:
    matches = [card for card in strategy_cards if card.strategy_family == family]
    if not matches:
        return ""
    return sorted(matches, key=lambda card: (-card.tournament_score, card.strategy_id))[0].strategy_id


def _weak_strategy(strategy_cards: list[StrategyReportCard], family: str) -> str:
    matches = [card for card in strategy_cards if card.strategy_family == family]
    if not matches:
        return ""
    return sorted(matches, key=lambda card: (card.tournament_score, card.strategy_id))[0].strategy_id


def _dominant_failure(evidence: ReportingEvidence, family: str) -> str:
    modes = [
        mode for mode in evidence.failure_modes.get("failure_modes", []) or []
        if isinstance(mode, dict) and str(mode.get("affected_family", "")) == family
    ]
    if not modes:
        return ""
    top = sorted(modes, key=lambda mode: (-int(mode.get("recurrence_count", 0)), str(mode.get("failure_mode_id", ""))))[0]
    return str(top.get("failure_mode_id", ""))


def _profile_cards(
    profiles: list[dict],
    source_layer: str,
    regime_type: str,
    strategy_cards: list[StrategyReportCard],
    evidence: ReportingEvidence,
) -> list[RegimeReportCard]:
    cards: list[RegimeReportCard] = []
    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            continue
        regime_id = str(profile.get("regime_tag", "")) or str(profile.get("regime_class", "")) or f"{source_layer}-{index:03d}"
        preferred = [str(item) for item in profile.get("preferred_families", []) if str(item)]
        penalized = [str(item) for item in profile.get("penalized_families", []) if str(item)]
        winning_family = preferred[0] if preferred else ""
        failing_family = penalized[0] if penalized else ""
        cards.append(RegimeReportCard(
            regime_id=regime_id,
            regime_type=regime_type,
            source_layer=source_layer,
            preferred_families=preferred,
            penalized_families=penalized,
            winning_strategy=_top_strategy(strategy_cards, winning_family),
            failing_strategy=_weak_strategy(strategy_cards, failing_family),
            primary_failure_mode=_dominant_failure(evidence, failing_family),
            score_movement_explanation=str(profile.get("regime_notes", "")) or f"{regime_id} shifts paper score by family fit and failure pressure.",
            safety_note="deterministic fixture only; paper-only; not live evidence",
            reproducibility_hash="",
        ))
    return cards


def build_regime_report_cards(
    evidence: ReportingEvidence,
    strategy_cards: list[StrategyReportCard],
) -> list[RegimeReportCard]:
    cards: list[RegimeReportCard] = []
    cards.extend(_profile_cards(
        list(evidence.ensemble.get("regime_profiles", []) or []),
        "ensemble_regime_allocator",
        "allocation_regime",
        strategy_cards,
        evidence,
    ))
    cards.extend(_profile_cards(
        list(evidence.meta_governor.get("regime_trust_profiles", []) or []),
        "meta_governor_regime_trust",
        "governance_regime",
        strategy_cards,
        evidence,
    ))
    for split in (evidence.stronger_consistency.get("split_set", {}) or {}).get("splits", []) or []:
        if not isinstance(split, dict):
            continue
        regime_tags = [str(item) for item in split.get("regime_tags", [])]
        cards.append(RegimeReportCard(
            regime_id=str(split.get("split_id", "")),
            regime_type=str(split.get("split_type", "walk_forward_split")),
            source_layer="stronger_walk_forward_consistency",
            preferred_families=[],
            penalized_families=[],
            winning_strategy=str(evidence.stronger_consistency.get("top_consistent_strategy", "")),
            failing_strategy="",
            primary_failure_mode="",
            score_movement_explanation=f"Split covers {', '.join(regime_tags[:5])}; holdout movement is deterministic fixture replay.",
            safety_note="deterministic fixture only; paper-only; not live evidence",
            reproducibility_hash="",
        ))
    for split in (evidence.corpus_v2.get("split_set", {}) or {}).get("splits", []) or []:
        if not isinstance(split, dict):
            continue
        regime_tags = [str(item) for item in split.get("regime_tags", [])]
        cards.append(RegimeReportCard(
            regime_id=str(split.get("split_id", "")),
            regime_type=str(split.get("split_type", "corpus_v2_split")),
            source_layer="regime_holdout_corpus_v2",
            preferred_families=[],
            penalized_families=[],
            winning_strategy=str(evidence.corpus_v2.get("top_consistent_strategy_v2", "")),
            failing_strategy="",
            primary_failure_mode="",
            score_movement_explanation=f"Corpus v2 split covers {', '.join(regime_tags[:5])}; broader holdout pressure is paper-only.",
            safety_note="deterministic fixture only; paper-only; not live evidence",
            reproducibility_hash="",
        ))
    cards.sort(key=lambda card: (card.source_layer, card.regime_id))
    return cards
