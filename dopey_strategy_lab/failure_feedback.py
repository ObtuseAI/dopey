"""Aggregate mined failure modes into deterministic family feedback profiles."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .failure_feedback_models import (
    FailureModeAggregate,
    FamilyFailureProfile,
    RegimeFailureProfile,
)
from .failure_mode_registry import FAILURE_MODE_REGISTRY_PATH


SEVERITY_SCORE: dict[str, float] = {
    "low": 0.25,
    "medium": 0.50,
    "high": 0.75,
    "critical": 1.00,
}

OVERFIT_RANK: dict[str, int] = {
    "unknown": 0,
    "none": 0,
    "low": 1,
    "moderate": 2,
    "high": 3,
}

FAMILY_STRUCTURE_TYPE: dict[str, str] = {
    "directional_convexity": "vertical",
    "volatility_expansion": "strangle",
    "volatility_compression": "iron_condor",
    "short_duration_defined_risk": "butterfly",
}


def load_latest_failure_mode_record(path: Path | str) -> dict:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"failure-mode registry not found: {target}")
    lines = [line for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"failure-mode registry is empty: {target}")
    return json.loads(lines[-1])


def default_failure_mode_record() -> dict:
    return load_latest_failure_mode_record(FAILURE_MODE_REGISTRY_PATH)


def failure_category_for_mode(failure_mode_id: str) -> str:
    if failure_mode_id in {"high_spread_bad_fill_failure", "low_liquidity_decay_failure", "slippage_over_sensitivity"}:
        return "liquidity_slippage"
    if failure_mode_id in {"IV_crush_against_vol_expansion", "iv_crush_after_vol_expansion_failure", "poor_greek_fit", "wrong_delta_direction"}:
        return "greek_iv"
    if failure_mode_id == "premium_overpayment_trap_failure":
        return "premium"
    if failure_mode_id in {"front_event_bump_against_compression", "backwardation_against_compression", "short_duration_front_iv_instability", "term_structure_mismatch"}:
        return "term_structure"
    if failure_mode_id in {"skew_trap_against_directional", "wing_elevation_breakout_risk"}:
        return "skew"
    if failure_mode_id == "surface_instability_fakeout_failure":
        return "surface_instability"
    if failure_mode_id in {"overfit_train_only", "holdout_collapse"}:
        return "overfit"
    if failure_mode_id == "unsafe_structure_rejected":
        return "structure"
    if failure_mode_id in {"fakeout_against_directional", "pattern_contradiction"}:
        return "pattern"
    if failure_mode_id in {"macro_shock_against_compression", "regime_mismatch", "theta_decay_against_short_duration"}:
        return "regime"
    if failure_mode_id == "mutation_drift":
        return "mutation_drift"
    return "general"


def _pattern_type_for_mode(failure_mode_id: str, regime_tag: str) -> str:
    if failure_mode_id == "fakeout_against_directional":
        return "failed_breakout_fakeout"
    if failure_mode_id == "surface_instability_fakeout_failure":
        return "surface_fakeout"
    if failure_mode_id == "macro_shock_against_compression":
        return "macro_shock_contradiction"
    if failure_mode_id in {"backwardation_against_compression", "wing_elevation_breakout_risk"}:
        return "compression_surface_contradiction"
    if failure_mode_id == "theta_decay_against_short_duration":
        return "theta_decay_window"
    if failure_mode_id == "short_duration_front_iv_instability":
        return "front_iv_instability"
    if failure_mode_id == "pattern_contradiction":
        return "family_pattern_contradiction"
    if regime_tag:
        return regime_tag
    return "not_flagged"


def _greek_verdict_for_mode(failure_mode_id: str) -> str:
    if failure_mode_id in {"IV_crush_against_vol_expansion", "iv_crush_after_vol_expansion_failure", "poor_greek_fit"}:
        return "fragile_fit"
    if failure_mode_id == "wrong_delta_direction":
        return "directional_mismatch"
    if failure_mode_id == "theta_decay_against_short_duration":
        return "theta_gamma_liquidity_pressure"
    if failure_mode_id == "premium_overpayment_trap_failure":
        return "premium_overpayment"
    if failure_mode_id in {"front_event_bump_against_compression", "backwardation_against_compression", "term_structure_mismatch"}:
        return "term_structure_mismatch"
    if failure_mode_id in {"skew_trap_against_directional", "wing_elevation_breakout_risk"}:
        return "skew_mismatch"
    if failure_mode_id == "surface_instability_fakeout_failure":
        return "unstable_surface"
    if failure_mode_id == "short_duration_front_iv_instability":
        return "front_iv_instability"
    return "not_flagged"


def _iv_context_for_mode(failure_mode_id: str, regime_tag: str) -> str:
    if failure_mode_id in {"IV_crush_against_vol_expansion", "iv_crush_after_vol_expansion_failure"}:
        return "post_event_iv_crush"
    if failure_mode_id in {"macro_shock_against_compression", "backwardation_against_compression"}:
        return "macro_shock_risk_off"
    if failure_mode_id == "premium_overpayment_trap_failure":
        return "premium_overpayment_trap"
    if failure_mode_id in {"front_event_bump_against_compression", "short_duration_front_iv_instability"}:
        return "front_expiry_event_bump"
    if failure_mode_id == "skew_trap_against_directional":
        return "skew_distortion"
    if failure_mode_id == "surface_instability_fakeout_failure":
        return "unstable_surface_fakeout"
    if failure_mode_id == "term_structure_mismatch":
        return "term_structure_stress"
    if failure_mode_id == "wing_elevation_breakout_risk":
        return "wing_elevation_breakout"
    if regime_tag in {"event_vol_expansion", "post_event_iv_crush", "macro_shock_risk_off"}:
        return regime_tag
    return "not_flagged"


def _liquidity_verdict_for_mode(failure_mode_id: str) -> str:
    if failure_mode_id == "low_liquidity_decay_failure":
        return "poor"
    if failure_mode_id == "high_spread_bad_fill_failure":
        return "fragile"
    return "not_flagged"


def _slippage_verdict_for_mode(failure_mode_id: str) -> str:
    if failure_mode_id in {"high_spread_bad_fill_failure", "slippage_over_sensitivity"}:
        return "high_pressure"
    if failure_mode_id == "low_liquidity_decay_failure":
        return "liquidity_decay_pressure"
    return "not_flagged"


def _overfit_level_for_mode(failure_mode_id: str) -> str:
    if failure_mode_id in {"overfit_train_only", "holdout_collapse"}:
        return "high"
    return "unknown"


def _mutation_type_for_mode(failure_mode_id: str, evidence: list[dict]) -> str:
    for item in evidence:
        notes = str(item.get("notes", ""))
        if "unsafe mutation" in notes or "family envelope" in notes:
            return "unsafe_probe"
    if failure_mode_id == "mutation_drift":
        return "family_envelope_drift"
    return "not_flagged"


def _mode_regimes(mode: dict) -> list[str]:
    regimes = [str(value) for value in mode.get("windows_or_regimes", []) if str(value)]
    if regimes:
        return sorted(set(regimes))
    return ["unknown"]


def aggregate_failure_modes(registry_record: dict) -> list[FailureModeAggregate]:
    aggregates: list[FailureModeAggregate] = []
    for mode in registry_record.get("failure_modes", []):
        mode_id = str(mode.get("failure_mode_id", ""))
        family = str(mode.get("affected_family", ""))
        severity = str(mode.get("severity", "medium"))
        recurrence_count = int(mode.get("recurrence_count", 0))
        evidence_score = round(float(mode.get("evidence_score", 0.0)), 6)
        category = failure_category_for_mode(mode_id)
        evidence = [dict(item) for item in mode.get("evidence", [])]
        for regime_tag in _mode_regimes(mode):
            aggregates.append(FailureModeAggregate(
                failure_mode_id=mode_id,
                strategy_family=family,
                structure_type=FAMILY_STRUCTURE_TYPE.get(family, "unknown"),
                regime_tag=regime_tag,
                pattern_type=_pattern_type_for_mode(mode_id, regime_tag),
                greek_risk_verdict=_greek_verdict_for_mode(mode_id),
                iv_context=_iv_context_for_mode(mode_id, regime_tag),
                liquidity_verdict=_liquidity_verdict_for_mode(mode_id),
                slippage_verdict=_slippage_verdict_for_mode(mode_id),
                overfit_level=_overfit_level_for_mode(mode_id),
                mutation_type=_mutation_type_for_mode(mode_id, evidence),
                failure_category=category,
                recurrence_count=recurrence_count,
                evidence_score=evidence_score,
                severity=severity,
                severity_score=SEVERITY_SCORE.get(severity, 0.50),
                affected_strategy_ids=[str(value) for value in mode.get("affected_strategy_ids", [])],
                mitigation_hints=[str(mode.get("mitigation_hint", ""))],
                constraint_updates=[str(mode.get("recommended_mutation_constraint_update", ""))],
            ))
    return sorted(
        aggregates,
        key=lambda item: (
            item.strategy_family,
            item.failure_mode_id,
            item.regime_tag,
            item.structure_type,
        ),
    )


def _top_modes(aggregates: list[FailureModeAggregate]) -> list[str]:
    ranked = sorted(
        aggregates,
        key=lambda item: (
            -item.recurrence_count,
            -item.severity_score,
            -item.evidence_score,
            item.failure_mode_id,
        ),
    )
    output: list[str] = []
    for item in ranked:
        if item.failure_mode_id not in output:
            output.append(item.failure_mode_id)
    return output[:5]


def _ranked_values_by_recurrence(aggregates: list[FailureModeAggregate], field_name: str) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    severities: dict[str, float] = defaultdict(float)
    for item in aggregates:
        value = str(getattr(item, field_name))
        if not value or value in {"unknown", "not_flagged"}:
            continue
        counts[value] += item.recurrence_count
        severities[value] += item.severity_score
    ranked = sorted(counts, key=lambda value: (-counts[value], -severities[value], value))
    return ranked


def _pressure_by_category(aggregates: list[FailureModeAggregate]) -> dict[str, float]:
    pressure: dict[str, float] = defaultdict(float)
    for item in aggregates:
        pressure[item.failure_category] += item.severity_score * max(1, item.recurrence_count)
    return {key: round(value, 6) for key, value in pressure.items()}


def _max_overfit_level(aggregates: list[FailureModeAggregate]) -> str:
    levels = [item.overfit_level for item in aggregates if item.overfit_level != "unknown"]
    if not levels:
        return "unknown"
    return sorted(levels, key=lambda value: OVERFIT_RANK.get(value, 0), reverse=True)[0]


def build_family_failure_profiles(aggregates: list[FailureModeAggregate]) -> list[FamilyFailureProfile]:
    by_family: dict[str, list[FailureModeAggregate]] = defaultdict(list)
    for item in aggregates:
        by_family[item.strategy_family].append(item)
    profiles: list[FamilyFailureProfile] = []
    for family in sorted(by_family):
        items = by_family[family]
        blocked = [
            item.mutation_type
            for item in items
            if item.failure_mode_id in {"unsafe_structure_rejected", "mutation_drift"}
            and item.mutation_type != "not_flagged"
        ]
        profiles.append(FamilyFailureProfile(
            strategy_family=family,
            total_failure_modes=len({item.failure_mode_id for item in items}),
            total_recurrence_count=sum(item.recurrence_count for item in items),
            top_failure_modes=_top_modes(items),
            worst_regimes=_ranked_values_by_recurrence(items, "regime_tag")[:5],
            failure_categories=sorted({item.failure_category for item in items}),
            structure_types=sorted({item.structure_type for item in items}),
            greek_risk_verdicts=sorted({item.greek_risk_verdict for item in items if item.greek_risk_verdict != "not_flagged"}),
            liquidity_verdicts=sorted({item.liquidity_verdict for item in items if item.liquidity_verdict != "not_flagged"}),
            slippage_verdicts=sorted({item.slippage_verdict for item in items if item.slippage_verdict != "not_flagged"}),
            overfit_level=_max_overfit_level(items),
            recommendation_pressure=_pressure_by_category(items),
            blocked_mutation_types=sorted(set(blocked)),
        ))
    return profiles


def build_regime_failure_profiles(aggregates: list[FailureModeAggregate]) -> list[RegimeFailureProfile]:
    grouped: dict[tuple[str, str], list[FailureModeAggregate]] = defaultdict(list)
    for item in aggregates:
        grouped[(item.strategy_family, item.regime_tag)].append(item)
    profiles: list[RegimeFailureProfile] = []
    for (family, regime), items in sorted(grouped.items()):
        profiles.append(RegimeFailureProfile(
            strategy_family=family,
            regime_tag=regime,
            recurrence_count=sum(item.recurrence_count for item in items),
            failure_mode_ids=sorted({item.failure_mode_id for item in items}),
            failure_categories=sorted({item.failure_category for item in items}),
            severity_score=round(sum(item.severity_score * max(1, item.recurrence_count) for item in items), 6),
        ))
    return sorted(
        profiles,
        key=lambda item: (-item.recurrence_count, -item.severity_score, item.strategy_family, item.regime_tag),
    )
