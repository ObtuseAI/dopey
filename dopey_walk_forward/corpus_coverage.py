"""Deterministic offline corpus v2 coverage scoring (paper-only).

Workstream C of `DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2`.

Models:
  CorpusCoverageScore              — overall corpus coverage (0..1)
  RegimeCoverageScore              — regime tag coverage
  SectorCoverageScore              — sector-specific coverage
  StressCoverageScore              — stress-window coverage (macro / IV / liquidity / bad-fill)
  FamilyChallengeCoverageScore     — cross-family challenge coverage

Coverage scoring tracks:
  * regime coverage
  * sector coverage
  * macro-shock coverage
  * IV transition coverage
  * skew/term danger coverage
  * liquidity stress coverage
  * bad-fill coverage
  * cross-family challenge coverage
  * family-specific weakness coverage
  * holdout diversity
  * duplicate-window pressure
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Iterable

from .regime_holdout_models import (
    RegimeHoldoutCorpus,
    RegimeHoldoutWindow,
    V2_CATEGORIES,
    V2_STRATEGY_FAMILIES,
)


# ---------------------------------------------------------------------------
# Required coverage categories.
#
# v2 corpus coverage is "informational" — it tracks which categories the v2 corpus
# covers. The required lists below match the canonical v2 templates; if the v2 corpus
# is missing any of these, the test suite (and `_recommended_next_windows`) flags the gap.
# ---------------------------------------------------------------------------

REQUIRED_REGIME_TAGS: tuple[str, ...] = (
    "trend_vol_expansion", "chop_vol_compression", "gap_reversal",
    "liquidity_decay", "event_vol_expansion", "post_event_iv_crush",
    "bearish_breakdown", "bullish_breakout", "range_bound_pin",
    "high_spread_bad_fill", "low_liquidity_decay", "macro_shock_risk_off",
    "macro_contradiction_pressure", "surface_instability_fakeout",
    "short_duration_bad_fill", "vol_expansion_trap",
    "compression_shock_failure", "clean_directional_confirmation",
)

REQUIRED_SECTORS_V2: tuple[str, ...] = (
    "tech_growth", "financials", "energy", "healthcare",
    "small_caps", "semiconductors", "consumer_discretionary", "broad_market",
)

REQUIRED_MACRO_SHOCKS: tuple[str, ...] = (
    "hot_cpi_gap_down_risk_off", "cool_cpi_gap_up_risk_on",
    "hawkish_fomc_vix_spike", "dovish_fomc_iv_crush",
    "jobs_surprise_yield_spike", "dollar_squeeze_liquidity_contraction",
)

REQUIRED_IV_TRANSITIONS: tuple[str, ...] = (
    "pre_event_iv_expansion_trap", "post_event_iv_crush_continuation",
    "front_iv_backwardation_panic", "normal_contango_chop_decay",
    "wing_elevation_breakout", "skew_collapse_reversal",
)

REQUIRED_LIQUIDITY_STRESSES: tuple[str, ...] = (
    "wide_spread_opening_gap", "low_oi_chain_decay",
    "multi_leg_fill_fragility", "late_day_liquidity_fade",
    "short_duration_bad_fill_cluster", "macro_gap_slippage_cluster",
)

REQUIRED_CROSS_FAMILY_CHALLENGES: tuple[str, ...] = (
    "directional_fakeout_macro_contradiction",
    "vol_expansion_post_event_crush_trap",
    "compression_breakout_shock_failure",
    "short_duration_theta_liquidity_failure",
    "all_family_high_uncertainty_stress",
    "clean_multi_signal_directional_confirmation",
)


# ---------------------------------------------------------------------------
# Score dataclasses.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegimeCoverageScore:
    """Regime tag coverage over the corpus."""
    covered: tuple[str, ...]
    missing: tuple[str, ...]
    coverage_fraction: float
    overrepresented: tuple[str, ...]
    duplicate_window_pressure: float

    def to_dict(self) -> dict:
        return {
            "covered": list(self.covered),
            "missing": list(self.missing),
            "coverage_fraction": round(self.coverage_fraction, 6),
            "overrepresented": list(self.overrepresented),
            "duplicate_window_pressure": round(self.duplicate_window_pressure, 6),
        }


@dataclass(frozen=True)
class SectorCoverageScore:
    """Sector coverage score."""
    covered: tuple[str, ...]
    missing: tuple[str, ...]
    coverage_fraction: float
    sectors_represented: int

    def to_dict(self) -> dict:
        return {
            "covered": list(self.covered),
            "missing": list(self.missing),
            "coverage_fraction": round(self.coverage_fraction, 6),
            "sectors_represented": self.sectors_represented,
        }


@dataclass(frozen=True)
class StressCoverageScore:
    """Macro-shock + IV-transition + liquidity-stress + bad-fill coverage."""
    macro_shock_covered: tuple[str, ...]
    macro_shock_missing: tuple[str, ...]
    iv_transition_covered: tuple[str, ...]
    iv_transition_missing: tuple[str, ...]
    liquidity_stress_covered: tuple[str, ...]
    liquidity_stress_missing: tuple[str, ...]
    bad_fill_windows: int
    bad_fill_coverage_fraction: float
    overall_coverage_fraction: float

    def to_dict(self) -> dict:
        return {
            "macro_shock_covered": list(self.macro_shock_covered),
            "macro_shock_missing": list(self.macro_shock_missing),
            "iv_transition_covered": list(self.iv_transition_covered),
            "iv_transition_missing": list(self.iv_transition_missing),
            "liquidity_stress_covered": list(self.liquidity_stress_covered),
            "liquidity_stress_missing": list(self.liquidity_stress_missing),
            "bad_fill_windows": self.bad_fill_windows,
            "bad_fill_coverage_fraction": round(self.bad_fill_coverage_fraction, 6),
            "overall_coverage_fraction": round(self.overall_coverage_fraction, 6),
        }


@dataclass(frozen=True)
class FamilyChallengeCoverageScore:
    """Per-family challenge coverage: how much pressure does the corpus put on each family?"""
    family: str
    pressure_windows: int
    support_windows: int
    high_uncertainty_windows: int
    mean_pressure: float
    mean_uncertainty: float
    is_challenged: bool
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "pressure_windows": self.pressure_windows,
            "support_windows": self.support_windows,
            "high_uncertainty_windows": self.high_uncertainty_windows,
            "mean_pressure": round(self.mean_pressure, 6),
            "mean_uncertainty": round(self.mean_uncertainty, 6),
            "is_challenged": self.is_challenged,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CorpusCoverageScore:
    """Overall corpus coverage score."""
    coverage_fraction: float
    missing_categories: tuple[str, ...]
    overrepresented_categories: tuple[str, ...]
    holdout_diversity: float
    duplicate_window_pressure: float
    regime: RegimeCoverageScore
    sector: SectorCoverageScore
    stress: StressCoverageScore
    family_challenge: tuple[FamilyChallengeCoverageScore, ...]
    recommended_next_windows: tuple[str, ...]
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "coverage_fraction": round(self.coverage_fraction, 6),
            "missing_categories": list(self.missing_categories),
            "overrepresented_categories": list(self.overrepresented_categories),
            "holdout_diversity": round(self.holdout_diversity, 6),
            "duplicate_window_pressure": round(self.duplicate_window_pressure, 6),
            "regime": self.regime.to_dict(),
            "sector": self.sector.to_dict(),
            "stress": self.stress.to_dict(),
            "family_challenge": [f.to_dict() for f in self.family_challenge],
            "recommended_next_windows": list(self.recommended_next_windows),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Score helpers.
# ---------------------------------------------------------------------------

def _coverage_fraction(covered: Iterable[str], required: Iterable[str]) -> float:
    required_set = set(required)
    covered_set = set(covered)
    if not required_set:
        return 1.0
    return len(required_set & covered_set) / len(required_set)


def _overrepresented(counter: Counter, threshold: int = 4) -> list[str]:
    """Categories that appear >threshold times are considered overrepresented."""
    return [k for k, v in counter.most_common() if v > threshold]


def _overrepresented_relative(counter: Counter, total: int, fraction: float = 0.5) -> list[str]:
    """Categories that exceed `fraction` of the total corpus are overrepresented."""
    if total <= 0:
        return []
    return [k for k, v in counter.most_common() if v / total > fraction]


def _duplicate_pressure(windows: list[RegimeHoldoutWindow]) -> float:
    """Fraction of windows sharing a regime tag with another window (0..1). 0 = unique."""
    if len(windows) < 2:
        return 0.0
    tags = Counter(w.regime_tag for w in windows)
    dup = sum(v for v in tags.values() if v > 1)
    return dup / len(windows)


def _holdout_diversity(windows: list[RegimeHoldoutWindow]) -> float:
    """Shannon-style diversity of regime tags (normalized; 0 = uniform, 1 = single tag)."""
    if not windows:
        return 0.0
    tags = Counter(w.regime_tag for w in windows)
    n = len(tags)
    if n == 1:
        return 1.0
    # 0 = uniform distribution; 1 = single category.
    total = len(windows)
    max_count = max(tags.values())
    return (max_count / total) - (1.0 / n)  # not strictly bounded; clamp.
    # We deliberately keep it as a relative concentration metric.


# ---------------------------------------------------------------------------
# Per-category scorers.
# ---------------------------------------------------------------------------

def score_regime_coverage(windows: list[RegimeHoldoutWindow]) -> RegimeCoverageScore:
    covered = sorted({w.regime_tag for w in windows})
    missing = sorted(set(REQUIRED_REGIME_TAGS) - set(covered))
    coverage = _coverage_fraction(covered, REQUIRED_REGIME_TAGS)
    counter = Counter(w.regime_tag for w in windows)
    overrep = _overrepresented(counter, threshold=4)
    dup_pressure = _duplicate_pressure(windows)
    return RegimeCoverageScore(
        covered=tuple(covered),
        missing=tuple(missing),
        coverage_fraction=coverage,
        overrepresented=tuple(overrep),
        duplicate_window_pressure=dup_pressure,
    )


def score_v2_category_coverage(windows: list[RegimeHoldoutWindow]) -> RegimeCoverageScore:
    """v2-specific regime coverage: tracks category-prefix coverage and category distribution.

    The v2 corpus uses regime tags like `v2_window_025_sector_tech_growth_risk_on_breakout`
    or `macro_hot_cpi_gap_down_risk_off`. We do not require any specific tag, but we do
    require that the v2 categories are all represented and that no single category
    dominates beyond 50% of the corpus.
    """
    covered = sorted({w.regime_tag for w in windows})
    counter = Counter(w.category for w in windows)
    total = max(1, len(windows))
    missing_categories = [c for c in V2_CATEGORIES if counter.get(c, 0) == 0]
    overrep = [c for c, v in counter.items() if v > 0.5 * total]
    # Coverage: fraction of v2 categories represented; each contributes 1 / len(V2_CATEGORIES).
    coverage = round(sum(1.0 for c in V2_CATEGORIES if counter.get(c, 0) > 0) / max(1, len(V2_CATEGORIES)), 6)
    dup_pressure = _duplicate_pressure(windows)
    return RegimeCoverageScore(
        covered=tuple(covered),
        missing=tuple(missing_categories),
        coverage_fraction=coverage,
        overrepresented=tuple(overrep),
        duplicate_window_pressure=dup_pressure,
    )


def score_sector_coverage(windows: list[RegimeHoldoutWindow]) -> SectorCoverageScore:
    covered = sorted({w.sector_context.sector for w in windows})
    missing = sorted(set(REQUIRED_SECTORS_V2) - set(covered))
    coverage = _coverage_fraction(covered, REQUIRED_SECTORS_V2)
    return SectorCoverageScore(
        covered=tuple(covered),
        missing=tuple(missing),
        coverage_fraction=coverage,
        sectors_represented=len(covered),
    )


def score_stress_coverage(windows: list[RegimeHoldoutWindow]) -> StressCoverageScore:
    macro_covered = sorted({w.macro_context.event_label for w in windows})
    macro_missing = sorted(set(REQUIRED_MACRO_SHOCKS) - set(macro_covered))
    macro_cov = _coverage_fraction(macro_covered, REQUIRED_MACRO_SHOCKS)
    iv_covered = sorted({w.iv_surface_context.transition_label for w in windows})
    iv_missing = sorted(set(REQUIRED_IV_TRANSITIONS) - set(iv_covered))
    iv_cov = _coverage_fraction(iv_covered, REQUIRED_IV_TRANSITIONS)
    liq_covered = sorted({w.liquidity_context.stress_label for w in windows})
    liq_missing = sorted(set(REQUIRED_LIQUIDITY_STRESSES) - set(liq_covered))
    liq_cov = _coverage_fraction(liq_covered, REQUIRED_LIQUIDITY_STRESSES)
    bad_fill = sum(1 for w in windows if w.liquidity_context.bad_fill_pressure >= 0.50)
    bad_fill_cov = bad_fill / max(1, len(windows))
    overall = (macro_cov + iv_cov + liq_cov) / 3.0
    return StressCoverageScore(
        macro_shock_covered=tuple(macro_covered),
        macro_shock_missing=tuple(macro_missing),
        iv_transition_covered=tuple(iv_covered),
        iv_transition_missing=tuple(iv_missing),
        liquidity_stress_covered=tuple(liq_covered),
        liquidity_stress_missing=tuple(liq_missing),
        bad_fill_windows=bad_fill,
        bad_fill_coverage_fraction=bad_fill_cov,
        overall_coverage_fraction=overall,
    )


def score_family_challenge_coverage(windows: list[RegimeHoldoutWindow]) -> tuple[FamilyChallengeCoverageScore, ...]:
    """For each family, count pressure vs support windows and compute mean pressure/uncertainty."""
    out = []
    for family in V2_STRATEGY_FAMILIES:
        pressures: list[float] = []
        uncertainties: list[float] = []
        pressure_windows = 0
        support_windows = 0
        high_uncertainty = 0
        for w in windows:
            p = float(w.expected_family_pressure.get(family, 0.0))
            pressures.append(p)
            if p > 0.0:
                pressure_windows += 1
            elif p < 0.0:
                support_windows += 1
            if w.challenge_context is not None:
                uncertainties.append(w.challenge_context.high_uncertainty)
                if w.challenge_context.high_uncertainty >= 0.7:
                    high_uncertainty += 1
            else:
                uncertainties.append(0.0)
        if not pressures:
            continue
        mean_pressure = sum(pressures) / len(pressures)
        mean_uncertainty = sum(uncertainties) / len(uncertainties)
        is_challenged = mean_pressure > 0.10 or high_uncertainty >= 2
        notes = "challenged" if is_challenged else "supported"
        out.append(FamilyChallengeCoverageScore(
            family=family,
            pressure_windows=pressure_windows,
            support_windows=support_windows,
            high_uncertainty_windows=high_uncertainty,
            mean_pressure=mean_pressure,
            mean_uncertainty=mean_uncertainty,
            is_challenged=is_challenged,
            notes=notes,
        ))
    return tuple(out)


def _recommended_next_windows(
    regime: RegimeCoverageScore,
    sector: SectorCoverageScore,
    stress: StressCoverageScore,
    max_items: int = 8,
) -> tuple[str, ...]:
    recs: list[str] = []
    for tag in regime.missing[:max_items]:
        recs.append(f"add walk-forward window covering regime_tag={tag}")
    for sec in sector.missing[:max_items]:
        recs.append(f"add v2 sector window for sector={sec}")
    for m in stress.macro_shock_missing[:max_items]:
        recs.append(f"add v2 macro-shock window for event_label={m}")
    for m in stress.iv_transition_missing[:max_items]:
        recs.append(f"add v2 iv-transition window for transition_label={m}")
    for m in stress.liquidity_stress_missing[:max_items]:
        recs.append(f"add v2 liquidity-stress window for stress_label={m}")
    return tuple(recs[:max_items])


def score_corpus_coverage(corpus: RegimeHoldoutCorpus) -> CorpusCoverageScore:
    windows = list(corpus.windows)
    # v2-specific regime scoring: tracks category distribution rather than v1 required tags.
    regime = score_v2_category_coverage(windows)
    sector = score_sector_coverage(windows)
    stress = score_stress_coverage(windows)
    family = score_family_challenge_coverage(windows)
    overall = round((regime.coverage_fraction * 0.30
                     + sector.coverage_fraction * 0.20
                     + stress.overall_coverage_fraction * 0.50), 6)
    category_counts = Counter(w.category for w in windows)
    overrep_cat = _overrepresented_relative(category_counts, total=len(windows), fraction=0.5)
    diversity = _holdout_diversity(windows)
    dup_pressure = _duplicate_pressure(windows)
    missing: list[str] = []
    for c in regime.missing:
        missing.append(f"category:{c}")
    for sec in sector.missing:
        missing.append(f"sector:{sec}")
    for m in stress.macro_shock_missing:
        missing.append(f"macro_shock:{m}")
    for m in stress.iv_transition_missing:
        missing.append(f"iv_transition:{m}")
    for m in stress.liquidity_stress_missing:
        missing.append(f"liquidity_stress:{m}")
    recs = _recommended_next_windows(regime, sector, stress)
    return CorpusCoverageScore(
        coverage_fraction=overall,
        missing_categories=tuple(missing),
        overrepresented_categories=tuple(overrep_cat),
        holdout_diversity=round(diversity, 6),
        duplicate_window_pressure=round(dup_pressure, 6),
        regime=regime,
        sector=sector,
        stress=stress,
        family_challenge=family,
        recommended_next_windows=recs,
        notes="deterministic fixture coverage score",
    )
