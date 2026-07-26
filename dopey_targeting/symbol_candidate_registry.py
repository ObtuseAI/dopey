"""Turn every covered symbol into an honestly scored research candidate."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from statistics import median

from dopey.protocols.identity import canonical_hash
from dopey.strategy_engineering.option_expression_cost import survives_option_costs

from .models import TargetingPolicy

CANDIDATE_REGISTRY_VERSION = "dopey-symbol-candidate-registry-v1"
JsonObject = dict[str, object]


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def build_symbol_iv_profiles(
    rows: Iterable[Mapping[str, object]],
    calibration_summary: Mapping[str, object],
) -> dict[str, JsonObject]:
    """Build latest-snapshot median IV profiles without cross-symbol imputation."""

    grouped: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        symbol_value = row.get("symbol")
        snapshot_value = row.get("snapshot_date")
        if not isinstance(symbol_value, str) or not isinstance(snapshot_value, str):
            continue
        symbol = symbol_value.upper()
        iv = _finite_float(row.get("mid_bisection_iv"))
        if iv is None or not 0.01 <= iv <= 5.0:
            continue
        grouped.setdefault(symbol, {}).setdefault(snapshot_value, []).append(iv)

    multiplier_rows = calibration_summary.get("per_symbol_multipliers")
    multipliers = multiplier_rows if isinstance(multiplier_rows, dict) else {}
    profiles: dict[str, JsonObject] = {}
    for symbol, by_snapshot in sorted(grouped.items()):
        latest_snapshot = max(by_snapshot)
        values = by_snapshot[latest_snapshot]
        multiplier_row = multipliers.get(symbol)
        multiplier = (
            _finite_float(multiplier_row.get("multiplier"))
            if isinstance(multiplier_row, dict)
            else None
        )
        profiles[symbol] = {
            "snapshot_date": latest_snapshot,
            "median_mid_bisection_iv": round(median(values), 6),
            "contract_count": len(values),
            "calibration_multiplier": multiplier,
            "iv_source": "latest_quote_derived_mid_bisection_median",
        }
    return profiles


def _history_profile(
    bars: Sequence[Mapping[str, object]],
    minimum_average_dollar_volume: float,
) -> JsonObject:
    if not bars:
        return {
            "bar_count": 0,
            "latest_date": None,
            "latest_close": None,
            "average_dollar_volume_20d": None,
            "liquidity_state": "missing_history",
            "data_quality_flags": ["missing_history"],
        }
    recent = bars[-20:]
    dollar_volumes: list[float] = []
    invalid_recent_rows = 0
    for bar in recent:
        close = _finite_float(bar.get("close"))
        volume = _finite_float(bar.get("volume"))
        if close is None or volume is None or close <= 0.0 or volume < 0.0:
            invalid_recent_rows += 1
            continue
        dollar_volumes.append(close * volume)
    latest_close = _finite_float(bars[-1].get("close"))
    average_dollar_volume = (
        sum(dollar_volumes) / float(len(dollar_volumes))
        if dollar_volumes
        else None
    )
    flags: list[str] = []
    if len(bars) < 30:
        flags.append("fewer_than_30_bars")
    if invalid_recent_rows:
        flags.append("invalid_recent_ohlcv_rows")
    if average_dollar_volume is None:
        flags.append("average_dollar_volume_unavailable")
    liquidity_state = (
        "liquid_for_shadow_research"
        if average_dollar_volume is not None
        and average_dollar_volume >= minimum_average_dollar_volume
        else "below_shadow_liquidity_floor"
    )
    return {
        "bar_count": len(bars),
        "latest_date": str(bars[-1].get("date", "")) or None,
        "latest_close": round(latest_close, 6) if latest_close is not None else None,
        "average_dollar_volume_20d": (
            round(average_dollar_volume, 2)
            if average_dollar_volume is not None
            else None
        ),
        "liquidity_state": liquidity_state,
        "liquidity_floor": minimum_average_dollar_volume,
        "data_quality_flags": flags,
    }


def _cost_annotation(
    family_skill: Mapping[str, object],
    iv_profile: Mapping[str, object] | None,
    policy: TargetingPolicy,
) -> JsonObject:
    if iv_profile is None:
        return {
            "status": "unavailable_no_symbol_iv",
            "survives_long_option_costs": None,
            "promotion_allowed": False,
        }
    implied_vol = _finite_float(iv_profile.get("median_mid_bisection_iv"))
    excess = _finite_float(
        family_skill.get(
            "mean_directional_excess_over_horizon_adjusted_drift"
        )
    )
    horizon_value = family_skill.get("representative_horizon_days")
    horizon_days = int(horizon_value) if isinstance(horizon_value, int) else None
    if implied_vol is None or excess is None or horizon_days is None:
        return {
            "status": "unavailable_incomplete_skill_or_iv",
            "survives_long_option_costs": None,
            "promotion_allowed": False,
        }
    result = survives_option_costs(
        underlying_excess=excess,
        iv=implied_vol,
        dte_days=policy.option_dte_days,
        horizon_days=horizon_days,
    )
    result["status"] = "measured"
    return result


def _liquidity_weight(history_profile: Mapping[str, object]) -> float:
    average = _finite_float(history_profile.get("average_dollar_volume_20d"))
    floor = _finite_float(history_profile.get("liquidity_floor"))
    if average is None or floor is None or average < floor:
        return 0.0
    return min(math.log1p(average) / math.log1p(1_000_000_000.0), 1.0)


def _family_targeting_score(
    family_skill: Mapping[str, object],
    cost: Mapping[str, object],
    liquidity_weight: float,
    policy: TargetingPolicy,
) -> float:
    if family_skill.get("verdict") != "positive_verified":
        return 0.0
    if cost.get("survives_long_option_costs") is not True:
        return 0.0
    effective_value = family_skill.get("effective_sample_size")
    effective_samples = (
        int(effective_value) if isinstance(effective_value, int) else 0
    )
    evidence_weight = min(
        float(effective_samples) / float(policy.minimum_effective_samples),
        1.0,
    )
    excess = _finite_float(
        family_skill.get(
            "mean_directional_excess_over_horizon_adjusted_drift"
        )
    )
    excess_weight = (
        min(excess / (policy.positive_excess_floor * 5.0), 1.0)
        if excess is not None and excess > 0.0
        else 0.0
    )
    return round(
        evidence_weight * excess_weight * liquidity_weight,
        8,
    )


def _research_priority_score(
    family_rows: Sequence[Mapping[str, object]],
    history_profile: Mapping[str, object],
    iv_profile: Mapping[str, object] | None,
    policy: TargetingPolicy,
) -> float:
    if not family_rows:
        evidence_progress = 0.0
    else:
        maximum_effective = max(
            int(row.get("effective_sample_size", 0))
            if isinstance(row.get("effective_sample_size"), int)
            else 0
            for row in family_rows
        )
        evidence_progress = min(
            float(maximum_effective) / float(policy.minimum_effective_samples),
            1.0,
        )
    iv_weight = 1.0 if iv_profile is not None else 0.5
    return round(
        _liquidity_weight(history_profile)
        * iv_weight
        * (0.25 + 0.75 * evidence_progress),
        8,
    )


def _per_symbol_skill(
    forecast_report: Mapping[str, object],
    symbol: str,
) -> Mapping[str, object]:
    per_symbol = forecast_report.get("per_symbol")
    if not isinstance(per_symbol, dict):
        return {}
    row = per_symbol.get(symbol)
    return row if isinstance(row, dict) else {}


def _family_rows(skill_row: Mapping[str, object]) -> dict[str, JsonObject]:
    per_family = skill_row.get("per_family")
    if not isinstance(per_family, dict):
        return {}
    return {
        str(family): dict(row)
        for family, row in per_family.items()
        if isinstance(row, dict)
    }


def _status_for(
    family_rows: Mapping[str, Mapping[str, object]],
    family_costs: Mapping[str, Mapping[str, object]],
    history_profile: Mapping[str, object],
) -> str:
    is_liquid = history_profile.get("liquidity_state") == "liquid_for_shadow_research"
    eligible = any(
        row.get("verdict") == "positive_verified"
        and family_costs.get(family, {}).get("survives_long_option_costs") is True
        for family, row in family_rows.items()
    )
    if eligible and is_liquid:
        return "targeting_shadow_eligible_for_forward_validation"
    if family_rows and all(
        row.get("verdict") == "negative_verified" for row in family_rows.values()
    ):
        return "avoid_observed_families_graded"
    return "insufficient_evidence_shadow_watch"


def _assign_shadow_weights(
    candidates: list[JsonObject],
    policy: TargetingPolicy,
) -> None:
    eligible = sorted(
        (
            row
            for row in candidates
            if row["candidate_status"]
            == "targeting_shadow_eligible_for_forward_validation"
        ),
        key=lambda row: (-float(row["targeting_score"]), str(row["symbol"])),
    )[: policy.maximum_shadow_candidates]
    total_score = sum(float(row["targeting_score"]) for row in eligible)
    selected_symbols = {str(row["symbol"]) for row in eligible}
    for row in candidates:
        if str(row["symbol"]) not in selected_symbols or total_score <= 0.0:
            row["shadow_attention_weight"] = 0.0
            continue
        raw_weight = float(row["targeting_score"]) / total_score
        row["shadow_attention_weight"] = round(
            min(raw_weight, policy.maximum_symbol_weight),
            8,
        )


def build_symbol_candidate_registry(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, object]]],
    forecast_report: Mapping[str, object],
    iv_profiles: Mapping[str, Mapping[str, object]],
    source_hashes: Mapping[str, str],
    policy: TargetingPolicy,
) -> JsonObject:
    """Build the complete symbol registry; absence of skill stays visible."""

    candidates: list[JsonObject] = []
    status_counts: Counter[str] = Counter()
    for symbol, bars in sorted(bars_by_symbol.items()):
        history_profile = _history_profile(
            bars,
            policy.minimum_average_dollar_volume,
        )
        skill_row = _per_symbol_skill(forecast_report, symbol)
        family_rows = _family_rows(skill_row)
        iv_profile = iv_profiles.get(symbol)
        costs: dict[str, JsonObject] = {
            family: _cost_annotation(row, iv_profile, policy)
            for family, row in sorted(family_rows.items())
        }
        liquidity_weight = _liquidity_weight(history_profile)
        family_scores = {
            family: _family_targeting_score(
                row,
                costs[family],
                liquidity_weight,
                policy,
            )
            for family, row in sorted(family_rows.items())
        }
        targeting_score = max(family_scores.values(), default=0.0)
        status = _status_for(family_rows, costs, history_profile)
        status_counts[status] += 1
        candidates.append(
            {
                "symbol": symbol,
                "candidate_status": status,
                "targeting_score": targeting_score,
                "research_priority_score": _research_priority_score(
                    list(family_rows.values()),
                    history_profile,
                    iv_profile,
                    policy,
                ),
                "per_family_skill": family_rows,
                "per_family_option_cost": costs,
                "per_family_targeting_score": family_scores,
                "history_profile": history_profile,
                "iv_profile": dict(iv_profile) if iv_profile is not None else None,
                "shadow_attention_weight": 0.0,
                "targeting_research_only": True,
                "promotion_allowed": False,
            }
        )

    _assign_shadow_weights(candidates, policy)
    candidates.sort(
        key=lambda row: (
            -float(row["targeting_score"]),
            -float(row["research_priority_score"]),
            str(row["symbol"]),
        )
    )
    report: JsonObject = {
        "artifact_type": "symbol_candidate_registry",
        "candidate_registry_version": CANDIDATE_REGISTRY_VERSION,
        "candidate_count": len(candidates),
        "candidate_status_counts": dict(sorted(status_counts.items())),
        "candidates": candidates,
        "source_hashes": dict(sorted(source_hashes.items())),
        "capacity_policy": {
            "minimum_average_dollar_volume": (
                policy.minimum_average_dollar_volume
            ),
            "maximum_shadow_candidates": policy.maximum_shadow_candidates,
            "maximum_shadow_candidates_per_direction": (
                policy.maximum_shadow_candidates_per_direction
            ),
            "maximum_symbol_weight": policy.maximum_symbol_weight,
            "sector_concentration_status": (
                "unavailable_no_point_in_time_sector_classification"
            ),
        },
        "every_history_symbol_is_a_candidate": True,
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
        "profit_or_edge_claimed": False,
    }
    report["reproducibility_hash"] = canonical_hash(report)
    return report
