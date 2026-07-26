"""Scenario explainability cards for static DOPEY reporting."""
from __future__ import annotations

from .data_loader import ReportingEvidence
from .report_models import ScenarioReportCard, StrategyReportCard


def _top_strategy_for_family(strategy_cards: list[StrategyReportCard], family: str) -> str:
    matches = [card for card in strategy_cards if card.strategy_family == family]
    if not matches:
        return ""
    return sorted(matches, key=lambda card: (-card.tournament_score, card.strategy_id))[0].strategy_id


def _lowest_strategy_for_family(strategy_cards: list[StrategyReportCard], family: str) -> str:
    matches = [card for card in strategy_cards if card.strategy_family == family]
    if not matches:
        return ""
    return sorted(matches, key=lambda card: (card.tournament_score, card.strategy_id))[0].strategy_id


def _failure_modes_for_family(evidence: ReportingEvidence, family: str) -> list[str]:
    modes = []
    for mode in evidence.failure_modes.get("failure_modes", []) or []:
        if isinstance(mode, dict) and str(mode.get("affected_family", "")) == family:
            modes.append(str(mode.get("failure_mode_id", "")))
    return [m for m in modes if m][:5]


def _scenario_id(row: dict, fallback: str) -> str:
    for key in ("scenario_id", "surface_scenario_id", "macro_scenario_id", "window_id", "split_id"):
        value = str(row.get(key, ""))
        if value:
            return value
    return fallback


def _preferred(row: dict) -> list[str]:
    for key in ("preferred_strategy_families", "preferred_families", "rewarded_families"):
        value = row.get(key, [])
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def _penalized(row: dict) -> list[str]:
    for key in ("penalized_strategy_families", "penalized_families", "starve_families"):
        value = row.get(key, [])
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def _scenario_explanation(row: dict, source_layer: str) -> str:
    notes = str(row.get("notes", "")) or str(row.get("explanation", "")) or str(row.get("regime_tag", ""))
    if notes:
        return f"{source_layer} fixture tests {notes}; score movement is deterministic and paper-only."
    return f"{source_layer} fixture scenario; score movement is deterministic and paper-only."


def _cards_from_rows(
    rows: list[dict],
    source_layer: str,
    scenario_type: str,
    strategy_cards: list[StrategyReportCard],
    evidence: ReportingEvidence,
) -> list[ScenarioReportCard]:
    cards: list[ScenarioReportCard] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        preferred = _preferred(row)
        penalized = _penalized(row)
        winning_family = preferred[0] if preferred else ""
        losing_family = penalized[0] if penalized else ""
        cards.append(ScenarioReportCard(
            scenario_id=_scenario_id(row, f"{source_layer}-{index:03d}"),
            scenario_type=scenario_type,
            source_layer=source_layer,
            preferred_families=preferred,
            penalized_families=penalized,
            winning_strategy=_top_strategy_for_family(strategy_cards, winning_family),
            losing_strategy=_lowest_strategy_for_family(strategy_cards, losing_family),
            dominant_failure_modes=_failure_modes_for_family(evidence, losing_family or winning_family),
            explanation=_scenario_explanation(row, source_layer),
            safety_note="deterministic fixture only; paper-only; not live evidence",
            reproducibility_hash="",
        ))
    return cards


def build_scenario_report_cards(
    evidence: ReportingEvidence,
    strategy_cards: list[StrategyReportCard],
) -> list[ScenarioReportCard]:
    cards: list[ScenarioReportCard] = []
    cards.extend(_cards_from_rows(
        list(evidence.macro_events.get("macro_scenarios", []) or []),
        "macro_event_fixtures",
        "macro",
        strategy_cards,
        evidence,
    ))
    cards.extend(_cards_from_rows(
        list(evidence.iv_surface.get("surface_scenarios", []) or []),
        "iv_surface_skew_term",
        "iv_skew_term",
        strategy_cards,
        evidence,
    ))
    cards.extend(_cards_from_rows(
        list(evidence.fundamental.get("scenarios", []) or []),
        "sector_peer_fundamental_fixtures",
        "sector_peer_fundamental",
        strategy_cards,
        evidence,
    ))
    for mode in evidence.failure_modes.get("failure_modes", []) or []:
        if not isinstance(mode, dict):
            continue
        family = str(mode.get("affected_family", ""))
        cards.append(ScenarioReportCard(
            scenario_id=str(mode.get("failure_mode_id", "")),
            scenario_type="failure_mode_cluster",
            source_layer="failure_mode_miner",
            preferred_families=[],
            penalized_families=[family] if family else [],
            winning_strategy="",
            losing_strategy=_lowest_strategy_for_family(strategy_cards, family),
            dominant_failure_modes=[str(mode.get("failure_mode_id", ""))],
            explanation=str(mode.get("mitigation_hint", "failure-mode cluster explains demotion pressure")),
            safety_note="deterministic fixture only; paper-only; not live evidence",
            reproducibility_hash="",
        ))
    cards.sort(key=lambda card: (card.source_layer, card.scenario_id))
    return cards
