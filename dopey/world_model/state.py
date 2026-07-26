"""Build a conservative shared market world model from validated evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.chronos.clocks import ClockStamp, validate_clock_stamp
from dopey.protocols.identity import canonical_hash


def _clamp_probability(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)


def _dimension(
    state: str,
    probability: float,
    uncertainty: float,
    evidence_ids: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "state": state,
        "probability": _clamp_probability(probability),
        "uncertainty": _clamp_probability(uncertainty),
        "evidence_ids": sorted(set(evidence_ids)),
        "limitations": limitations,
    }


def _technical_evidence_ids(technical: Mapping[str, Any], indicator: str) -> list[str]:
    return [
        str(record["evidence_id"])
        for record in technical.get("measurements", [])
        if record.get("indicator") == indicator and record.get("measurement_status") == "complete"
    ]


def _technical_trend_dimension(technical: Mapping[str, Any]) -> dict[str, Any]:
    fusion = technical.get("fusion_states", {})
    directional = [
        str(fusion.get(indicator, "mixed_or_neutral"))
        for indicator in ("MACD_HISTOGRAM", "DMI_SPREAD", "ROC", "OBV_SLOPE")
    ]
    positive = sum("positive" in state for state in directional)
    negative = sum("negative" in state for state in directional)
    score = (positive - negative) / max(len(directional), 1)
    if score >= 0.5:
        state = "uptrend_supported"
    elif score <= -0.5:
        state = "downtrend_supported"
    else:
        state = "mixed_or_transitioning"
    evidence_ids = [
        evidence_id
        for indicator in ("MACD_HISTOGRAM", "DMI_SPREAD", "ROC", "OBV_SLOPE")
        for evidence_id in _technical_evidence_ids(technical, indicator)
    ]
    probability = 0.5 + 0.35 * abs(score)
    return _dimension(
        state,
        probability,
        1.0 - probability,
        evidence_ids,
        ["technical_state_is_symbol_specific_not_market_wide_breadth"],
    )


def _cross_asset_dimensions(cross_asset: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    context_complete = cross_asset.get("context_status") == "complete"
    general_limitations = [] if context_complete else ["cross_asset_context_incomplete"]
    volatility = cross_asset.get("volatility_term_structure", {})
    vix = float(volatility.get("VIX", 0.0) or 0.0)
    slope = float(volatility.get("term_slope_9d_3m", 0.0) or 0.0)
    if not context_complete or vix <= 0.0:
        volatility_dimension = _dimension("unknown", 0.0, 1.0, [], general_limitations + ["vix_unavailable"])
    else:
        volatility_state = (
            "high_or_stressed" if vix >= 30.0 else
            "elevated" if vix >= 22.0 else
            "low_with_backwardation_risk" if slope < 0.0 else
            "low_to_normal_contango"
        )
        volatility_dimension = _dimension(
            volatility_state,
            0.72 if abs(slope) >= 0.1 else 0.6,
            0.28 if abs(slope) >= 0.1 else 0.4,
            [],
            general_limitations + ["term_structure_is_context_not_direction_authority"],
        )
    liquidity = cross_asset.get("fed_liquidity", {})
    liquidity_state = str(liquidity.get("impulse_state", "unknown"))
    liquidity_dimension = _dimension(
        liquidity_state,
        0.62 if liquidity_state != "unknown" else 0.0,
        0.38 if liquidity_state != "unknown" else 1.0,
        [],
        general_limitations + ["weekly_fed_liquidity_proxy"],
    )
    treasury = cross_asset.get("treasury_curve", {})
    rates_state = str(treasury.get("curve_state", "unknown"))
    rates_dimension = _dimension(
        rates_state,
        0.7 if rates_state != "unknown" else 0.0,
        0.3 if rates_state != "unknown" else 1.0,
        [],
        general_limitations + ["curve_shape_does_not_establish_growth_causality"],
    )
    series_states = cross_asset.get("series_states", {})
    dollar = series_states.get("DXY", {}) if isinstance(series_states, Mapping) else {}
    dollar_score = float(dollar.get("directional_score", 0.0) or 0.0)
    dollar_state = "strengthening" if dollar_score > 0.2 else "weakening" if dollar_score < -0.2 else "neutral"
    dollar_dimension = _dimension(
        dollar_state if dollar else "unknown",
        0.5 + min(abs(dollar_score), 0.35) if dollar else 0.0,
        0.5 - min(abs(dollar_score), 0.35) if dollar else 1.0,
        [],
        general_limitations + ["continuous_market_proxy"],
    )
    commodity_scores = [
        float(series_states.get(symbol, {}).get("directional_score", 0.0) or 0.0)
        for symbol in ("CL", "GC", "HG")
        if isinstance(series_states, Mapping) and series_states.get(symbol)
    ]
    commodity_score = sum(commodity_scores) / len(commodity_scores) if commodity_scores else 0.0
    commodity_state = "firming" if commodity_score > 0.2 else "weakening" if commodity_score < -0.2 else "mixed"
    commodity_dimension = _dimension(
        commodity_state if commodity_scores else "unknown",
        0.55 + min(abs(commodity_score), 0.3) if commodity_scores else 0.0,
        0.45 - min(abs(commodity_score), 0.3) if commodity_scores else 1.0,
        [],
        general_limitations + ["continuous_futures_roll_discontinuities_possible"],
    )
    return {
        "volatility": volatility_dimension,
        "liquidity": liquidity_dimension,
        "rates": rates_dimension,
        "dollar": dollar_dimension,
        "commodity": commodity_dimension,
    }


def _unknown_dimension(reason: str) -> dict[str, Any]:
    return _dimension("unknown", 0.0, 1.0, [], [reason])


def build_world_model(
    technical_evidence: Mapping[str, Any],
    cross_asset_context: Mapping[str, Any],
    news_context: Mapping[str, Any],
    clock: ClockStamp,
) -> dict[str, Any]:
    validate_clock_stamp(clock)
    dimensions: dict[str, dict[str, Any]] = {
        "equity_trend": _technical_trend_dimension(technical_evidence),
        **_cross_asset_dimensions(cross_asset_context),
        "credit": _unknown_dimension("no_validated_credit_regime_input_in_vertical_slice"),
        "inflation": _dimension(
            "pressure_positive" if float(cross_asset_context.get("inflation_pressure_score", 0.0) or 0.0) > 0.2 else "muted_or_mixed",
            0.55 if cross_asset_context.get("context_status") == "complete" else 0.0,
            0.45 if cross_asset_context.get("context_status") == "complete" else 1.0,
            [],
            ["cross_asset_proxy_not_macro_release_causal_model"],
        ),
        "growth": _dimension(
            "positive" if float(cross_asset_context.get("growth_impulse_score", 0.0) or 0.0) > 0.2 else "muted_or_mixed",
            0.55 if cross_asset_context.get("context_status") == "complete" else 0.0,
            0.45 if cross_asset_context.get("context_status") == "complete" else 1.0,
            [],
            ["cross_asset_proxy_not_economic_nowcast"],
        ),
        "sector_leadership": _unknown_dimension("symbol_theme_context_is_not_a_complete_sector_breadth_model"),
        "breadth": _unknown_dimension("validated_advance_decline_or_constituent_breadth_input_missing"),
        "crowding": _unknown_dimension("point_in_time_positioning_is_not_broad_crowding_history"),
        "options_dealer_state": _unknown_dimension("validated_dealer_inventory_not_available_and_not_inferred_from_open_interest"),
        "geopolitical_stress": _dimension(
            "elevated" if int(news_context.get("corroborated_alert_count", 0) or 0) > 0 else "no_corroborated_alert",
            0.65 if news_context.get("pipeline_status") == "complete" else 0.0,
            0.35 if news_context.get("pipeline_status") == "complete" else 1.0,
            [],
            ["headline_metadata_classification_only"],
        ),
        "news_intensity": _dimension(
            "active" if int(news_context.get("fresh_7d_event_count", 0) or 0) >= 10 else "quiet",
            0.7 if news_context.get("pipeline_status") == "complete" else 0.0,
            0.3 if news_context.get("pipeline_status") == "complete" else 1.0,
            [],
            ["coverage_is_source_bounded"],
        ),
        "correlation_structure": _unknown_dimension("rolling_cross_asset_correlation_matrix_not_yet_integrated"),
        "market_fragility": _dimension(
            "elevated" if float(cross_asset_context.get("systemic_stress_score", 0.0) or 0.0) >= 0.5 else "contained_but_uncertain",
            0.58 if cross_asset_context.get("context_status") == "complete" else 0.0,
            0.42 if cross_asset_context.get("context_status") == "complete" else 1.0,
            [],
            ["systemic_stress_is_composite_context_not_crash_probability"],
        ),
    }
    contradictions: list[str] = []
    risk_appetite = float(cross_asset_context.get("risk_appetite_score", 0.0) or 0.0)
    systemic_stress = float(cross_asset_context.get("systemic_stress_score", 0.0) or 0.0)
    if risk_appetite > 0.15 and systemic_stress > 0.3:
        contradictions.append("positive_risk_appetite_conflicts_with_nontrivial_systemic_stress")
    if dimensions["equity_trend"]["state"] == "uptrend_supported" and dimensions["breadth"]["state"] == "unknown":
        contradictions.append("symbol_technical_strength_lacks_validated_market_breadth_confirmation")
    evidence_ids = sorted(
        {
            str(record["evidence_id"])
            for record in technical_evidence.get("measurements", [])
            if record.get("measurement_status") == "complete"
        }
    )
    body: dict[str, Any] = {
        "artifact_type": "shared_market_world_model",
        "world_model_version": "dopey-world-model-v1",
        "as_of": clock.market_time,
        "symbol_context": str(technical_evidence.get("symbol", "")),
        "regimes": dimensions,
        "contradictions": contradictions,
        "known_dimension_count": sum(record["state"] != "unknown" for record in dimensions.values()),
        "unknown_dimension_count": sum(record["state"] == "unknown" for record in dimensions.values()),
        "evidence_ids": evidence_ids,
        "paper_only": True,
        "live_blocked": True,
        "not_readiness_evidence": True,
    }
    content_hash = canonical_hash(body)
    return {
        **body,
        "evidence_id": f"world-model:{content_hash[:20]}",
        "content_hash": content_hash,
        "observed_at": clock.market_time,
        "source_uri": "local://dopey/vnext/world-model",
        "schema_version": "dopey-world-model-v1",
        "provenance": "deterministic_fusion_of_typed_local_evidence",
    }
