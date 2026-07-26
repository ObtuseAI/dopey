"""Deterministic sector/peer/fundamental coverage scoring for DOPEY paper replay.

Tracks how well the deterministic scenario library covers the fundamental surface, flags
missing categories, identifies overrepresented categories, and recommends next scenarios.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .fundamental_fixture_models import FUNDAMENTAL_FIXTURE_VERSION
from .sector_peer_scenarios import build_sector_peer_fundamental_scenarios


FUNDAMENTAL_COVERAGE_VERSION = "dopey-fundamental-coverage-v1"


REQUIRED_COVERAGE_CATEGORIES = (
    "sector_coverage",
    "peer_dispersion_coverage",
    "valuation_regime_coverage",
    "earnings_quality_coverage",
    "margin_pressure_coverage",
    "revision_shock_coverage",
    "crowding_coverage",
    "fundamental_confirmation_trap_coverage",
    "family_specific_challenge_coverage",
)


@dataclass(frozen=True)
class FundamentalCoverageScore:
    coverage_id: str
    categories: dict[str, float]
    missing_categories: list[str]
    overrepresented_categories: list[str]
    recommended_next_scenarios: list[str]
    overall_coverage: float
    notes: str = ""
    version: str = FUNDAMENTAL_COVERAGE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _score_sector_coverage(scenarios) -> float:
    sectors = {s.sector_context.sector_id for s in scenarios}
    return min(1.0, len(sectors) / 8.0)


def _score_peer_dispersion_coverage(scenarios) -> float:
    high_dispersion = sum(1 for s in scenarios if s.peer_context.peer_dispersion_score >= 0.70)
    low_dispersion = sum(1 for s in scenarios if s.peer_context.peer_dispersion_score <= 0.30)
    return min(1.0, (high_dispersion + low_dispersion) / 4.0)


def _score_valuation_regime_coverage(scenarios) -> float:
    regimes = {s.valuation_context.valuation_regime for s in scenarios}
    return min(1.0, len(regimes) / 5.0)


def _score_earnings_quality_coverage(scenarios) -> float:
    high = sum(1 for s in scenarios if s.earnings_quality_context.earnings_quality_score >= 0.65)
    low = sum(1 for s in scenarios if s.earnings_quality_context.earnings_quality_score <= 0.35)
    return min(1.0, (high + low) / 4.0)


def _score_margin_pressure_coverage(scenarios) -> float:
    pressure = sum(1 for s in scenarios if s.earnings_quality_context.margin_quality_score <= 0.40
                   or s.fundamental_fixture.fundamental_fragility_score >= 0.55)
    return min(1.0, pressure / 3.0)


def _score_revision_shock_coverage(scenarios) -> float:
    shocks = sum(1 for s in scenarios if s.fundamental_fixture.revision_momentum_proxy <= 0.30
                 or "revision_shock" in s.scenario_id)
    return min(1.0, shocks / 2.0)


def _score_crowding_coverage(scenarios) -> float:
    crowded = sum(1 for s in scenarios if s.peer_context.crowding_proxy_score >= 0.70
                  or s.fundamental_fixture.short_interest_pressure_proxy >= 0.45)
    return min(1.0, crowded / 3.0)


def _score_fundamental_confirmation_trap_coverage(scenarios) -> float:
    confirm = sum(1 for s in scenarios if s.risk_summary.verdict in {"strong_fundamental_confirmation", "sector_peer_confirmed"})
    trap = sum(1 for s in scenarios if s.risk_summary.verdict in {"valuation_trap", "fundamental_fragility", "crowding_danger", "peer_contradiction"})
    return min(1.0, (confirm + trap) / 6.0)


def _score_family_specific_challenge_coverage(scenarios) -> float:
    preferred_pairs = set()
    for s in scenarios:
        for family in s.preferred_strategy_families:
            preferred_pairs.add((family, s.scenario_id))
    return min(1.0, len(preferred_pairs) / 16.0)


def _flag_missing(categories: dict[str, float]) -> list[str]:
    return sorted([category for category, score in categories.items() if score < 0.50])


def _flag_overrepresented(scenarios) -> list[str]:
    counts: dict[str, int] = {}
    for s in scenarios:
        counts[s.regime_tag] = counts.get(s.regime_tag, 0) + 1
    return sorted([regime for regime, count in counts.items() if count >= 4])


def _recommend_next(categories: dict[str, float]) -> list[str]:
    recommendations: list[str] = []
    if categories.get("sector_coverage", 1.0) < 0.65:
        recommendations.append("add more sector-specific scenarios (e.g. energy, materials, staples)")
    if categories.get("peer_dispersion_coverage", 1.0) < 0.65:
        recommendations.append("add more high-dispersion and low-dispersion peer windows")
    if categories.get("valuation_regime_coverage", 1.0) < 0.65:
        recommendations.append("add value_support and growth_justified valuation windows")
    if categories.get("earnings_quality_coverage", 1.0) < 0.65:
        recommendations.append("add high- and low-quality earnings windows")
    if categories.get("margin_pressure_coverage", 1.0) < 0.65:
        recommendations.append("add margin-pressure gap windows")
    if categories.get("revision_shock_coverage", 1.0) < 0.65:
        recommendations.append("add revision-shock and stability-revision windows")
    if categories.get("crowding_coverage", 1.0) < 0.65:
        recommendations.append("add crowded-unwind and short-interest windows")
    if categories.get("fundamental_confirmation_trap_coverage", 1.0) < 0.65:
        recommendations.append("add valuation-trap and fundamental-fragility trap windows")
    if categories.get("family_specific_challenge_coverage", 1.0) < 0.65:
        recommendations.append("add more family-specific challenge windows")
    return recommendations


def build_fundamental_coverage(scenarios: list | None = None) -> FundamentalCoverageScore:
    """Compute coverage score across the deterministic fundamental fixture library."""
    scenarios = scenarios if scenarios is not None else build_sector_peer_fundamental_scenarios()
    categories: dict[str, float] = {
        "sector_coverage": _score_sector_coverage(scenarios),
        "peer_dispersion_coverage": _score_peer_dispersion_coverage(scenarios),
        "valuation_regime_coverage": _score_valuation_regime_coverage(scenarios),
        "earnings_quality_coverage": _score_earnings_quality_coverage(scenarios),
        "margin_pressure_coverage": _score_margin_pressure_coverage(scenarios),
        "revision_shock_coverage": _score_revision_shock_coverage(scenarios),
        "crowding_coverage": _score_crowding_coverage(scenarios),
        "fundamental_confirmation_trap_coverage": _score_fundamental_confirmation_trap_coverage(scenarios),
        "family_specific_challenge_coverage": _score_family_specific_challenge_coverage(scenarios),
    }
    missing = _flag_missing(categories)
    overrepresented = _flag_overrepresented(scenarios)
    recommendations = _recommend_next(categories)
    overall = round(sum(categories.values()) / len(categories), 6)
    return FundamentalCoverageScore(
        coverage_id="dopey-fundamental-coverage-v1",
        categories={k: round(v, 6) for k, v in categories.items()},
        missing_categories=missing,
        overrepresented_categories=overrepresented,
        recommended_next_scenarios=recommendations,
        overall_coverage=overall,
        notes="fixture-only coverage of sector/peer/fundamental surface; not real fundamentals",
    )
