"""Enrich the shared world model without inventing unavailable evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.protocols.identity import canonical_hash


def _dimension(state: str, probability: float, evidence_id: str, limitations: list[str]) -> dict[str, Any]:
    bounded = max(0.0, min(1.0, probability))
    return {
        "state": state,
        "probability": round(bounded, 6),
        "uncertainty": round(1.0 - bounded, 6),
        "evidence_ids": [evidence_id] if evidence_id else [],
        "limitations": limitations,
    }


def enrich_world_model(
    base_world_model: Mapping[str, Any],
    cross_section: Mapping[str, Any],
    cross_asset_context: Mapping[str, Any],
    credit_proxy_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if cross_section.get("paper_only") is not True or cross_section.get("live_blocked") is not True:
        raise ValueError("world-model enrichment rejects non-governed cross-sectional context")
    cross_id = str(cross_section.get("evidence_id", ""))
    if not cross_id:
        raise ValueError("world-model enrichment requires cross-sectional evidence identity")
    if credit_proxy_evidence.get("paper_only") is not True or credit_proxy_evidence.get("live_blocked") is not True:
        raise ValueError("world-model enrichment rejects non-governed credit proxy evidence")
    credit_id = str(credit_proxy_evidence.get("evidence_id", ""))
    if not credit_id:
        raise ValueError("world-model enrichment requires credit proxy evidence identity")
    regimes = {name: dict(record) for name, record in base_world_model.get("regimes", {}).items()}
    breadth = cross_section.get("breadth", {})
    breadth_sample = int(breadth.get("sample_count", 0) or 0)
    regimes["breadth"] = _dimension(
        str(breadth.get("state", "unknown")),
        min(0.85, 0.45 + breadth_sample / 200.0) if breadth_sample else 0.0,
        cross_id,
        ["governed_history_universe_not_full_exchange_advance_decline"],
    )
    leadership = cross_section.get("sector_leadership", {})
    ranking = list(leadership.get("ranking", []))
    regimes["sector_leadership"] = _dimension(
        str(leadership.get("state", "unknown")),
        min(0.8, 0.45 + len(ranking) / 25.0) if ranking else 0.0,
        cross_id,
        ["sector_etf_return_ranking_not_constituent_attribution"],
    )
    correlation = cross_section.get("correlation_structure", {})
    pair_count = len(correlation.get("pairs", []))
    regimes["correlation_structure"] = _dimension(
        str(correlation.get("state", "unknown")),
        min(0.82, 0.5 + pair_count / 30.0) if pair_count else 0.0,
        cross_id,
        ["large_cap_index_proxy_correlation"],
    )
    fragility = cross_section.get("market_fragility", {})
    regimes["market_fragility"] = _dimension(
        str(fragility.get("state", "unknown")),
        0.68 if fragility.get("state") != "unknown" else 0.0,
        cross_id,
        ["breadth_correlation_composite_not_crash_probability"],
    )
    credit_values = credit_proxy_evidence.get("values", {})
    regimes["credit"] = _dimension(
        str(credit_values.get("state", "unknown")),
        float(credit_values.get("probability", 0.0) or 0.0),
        credit_id,
        [
            "etf_relative_return_proxy_not_option_adjusted_credit_spread",
            "duration_and_fund_flow_effects_are_not_separated",
        ],
    )
    positioning = cross_asset_context.get("es_positioning", {})
    positioning_z = positioning.get("noncomm_net_z_52w")
    if positioning_z is not None:
        z_value = float(positioning_z)
        positioning_state = (
            "relative_positioning_extreme_positive_z" if z_value >= 2.0
            else "relative_positioning_extreme_negative_z" if z_value <= -2.0
            else "relative_positioning_normal_range"
        )
        regimes["crowding"] = _dimension(
            positioning_state,
            min(0.8, 0.55 + abs(z_value) / 10.0),
            "",
            ["weekly_es_noncommercial_positioning_relative_z_not_complete_market_crowding"],
        )
    contradictions = list(base_world_model.get("contradictions", []))
    if regimes.get("equity_trend", {}).get("state") == "uptrend_supported" and regimes["breadth"]["state"] == "narrow_participation":
        contradictions.append("index_or_symbol_strength_conflicts_with_narrow_cross_sectional_participation")
    contradictions = sorted(
        contradiction
        for contradiction in set(contradictions)
        if contradiction != "symbol_technical_strength_lacks_validated_market_breadth_confirmation"
    )
    evidence_ids = sorted(set(base_world_model.get("evidence_ids", [])) | {cross_id, credit_id})
    excluded = {
        "evidence_id", "content_hash", "schema_version", "provenance", "regimes", "contradictions",
        "known_dimension_count", "unknown_dimension_count", "evidence_ids", "world_model_version",
    }
    body: dict[str, Any] = {
        **{key: value for key, value in base_world_model.items() if key not in excluded},
        "world_model_version": "dopey-world-model-v3",
        "regimes": regimes,
        "contradictions": contradictions,
        "known_dimension_count": sum(record.get("state") != "unknown" for record in regimes.values()),
        "unknown_dimension_count": sum(record.get("state") == "unknown" for record in regimes.values()),
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
        "schema_version": "dopey-world-model-v3",
        "provenance": "deterministic_fusion_of_typed_local_and_cross_sectional_evidence",
    }
