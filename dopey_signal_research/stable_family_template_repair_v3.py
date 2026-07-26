"""Stable family template repair V3 — fixes volume dry-up under-generation."""
from __future__ import annotations

from dataclasses import dataclass

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import is_quarantined_signature
from dopey_autonomy.signal_research_v3_common import (
    RESEARCH_V3_ROOT,
    STABLE_FAMILY_CONTINUATION,
    STABLE_FAMILY_VOLUME,
    STABLE_TEMPLATES_PATH,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file


REPAIRS_PATH = RESEARCH_V3_ROOT / "stable_family_template_repairs_v3.jsonl"
QUALITY_PATH = RESEARCH_V3_ROOT / "stable_family_template_quality_flags_v3.jsonl"
SUMMARY_PATH = RESEARCH_V3_ROOT / "stable_family_template_repair_v3_summary.json"
PROOF_PATH = RESEARCH_V3_ROOT / "stable_family_template_repair_v3_proof.jsonl"


@dataclass(frozen=True)
class StableFamilyTemplateV3:
    stable_family_template_id: str
    direction: str
    family_type: str
    feature_requirements: tuple[str, ...]
    direction_logic: str
    entry_setup: str
    stop_target_logic: str
    dte_default: int
    moneyness_default: str
    exit_policy: str
    risk_filters: tuple[str, ...]
    no_trade_filters: tuple[str, ...]
    min_symbol_coverage: int
    min_sector_coverage: int
    min_sample_target: int


V3_TEMPLATES: tuple[StableFamilyTemplateV3, ...] = (
    StableFamilyTemplateV3(
        stable_family_template_id=STABLE_FAMILY_CONTINUATION,
        direction="bullish",
        family_type="continuation",
        feature_requirements=("prior_trend", "pullback_or_pause", "volume_confirmation", "relative_strength"),
        direction_logic="long_call on bullish continuation after pullback with volume confirmation",
        entry_setup="pullback_continuation with high volume percentile and RS confirmation",
        stop_target_logic="invalidation below structure; trend_follow exit",
        dte_default=14,
        moneyness_default="1pct_otm",
        exit_policy="trend_follow",
        risk_filters=("public_data_only", "no_short_options", "avoid_thin_volume"),
        no_trade_filters=("overextended_move", "volatility_shock_regime_conflict"),
        min_symbol_coverage=80,
        min_sector_coverage=12,
        min_sample_target=500,
    ),
    StableFamilyTemplateV3(
        stable_family_template_id=STABLE_FAMILY_VOLUME,
        direction="bullish",
        family_type="volume",
        feature_requirements=(
            "volume_dry_up",
            "range_compression",
            "close_above_structure",
            "optional_relative_strength",
        ),
        direction_logic="long_call on dry-up then expansion breakout (V2 contradictory rules repaired)",
        entry_setup="dry-up proxy then close above short-term structure without exhaustion spike",
        stop_target_logic="invalidation below compression range; trend_follow exit",
        dte_default=14,
        moneyness_default="1pct_otm",
        exit_policy="trend_follow",
        risk_filters=("public_data_only", "no_short_options", "avoid_thin_volume", "avoid_low_liquidity"),
        no_trade_filters=(
            "one_day_exhaustion_spike",
            "overextended_gap",
            "market_sector_regime_conflict",
            "volatility_shock",
        ),
        min_symbol_coverage=80,
        min_sector_coverage=12,
        min_sample_target=500,
    ),
)


def matches_continuation_v3(features: dict[str, dict[str, float]]) -> bool:
    continuation = features.get("continuation", {})
    volume = features.get("volume", {})
    rs = features.get("relative_strength", {})
    risk = features.get("risk_filter", {})
    if float(risk.get("avoid_overextended_move", 0.0)) >= 1.0:
        return False
    if float(risk.get("avoid_poor_regime_alignment", 0.0)) >= 1.0:
        return False
    pullback = float(continuation.get("pullback_continuation", 0.0)) >= 1.0
    vol_confirm = float(volume.get("volume_percentile", 0.0)) >= 0.9
    rs_ok = float(rs.get("vs_spy", 0.0)) >= -0.01
    return pullback and vol_confirm and rs_ok


def matches_volume_dry_up_v3(features: dict[str, dict[str, float]]) -> bool:
    """Repaired matcher: V1 required dry-up AND volume spike simultaneously (impossible)."""
    volume = features.get("volume", {})
    price = features.get("price_structure", {})
    continuation = features.get("continuation", {})
    volatility = features.get("volatility", {})
    risk = features.get("risk_filter", {})
    regime = features.get("regime", {})

    if float(volume.get("volume_climax", 0.0)) >= 1.0:
        return False
    if float(risk.get("avoid_overextended_move", 0.0)) >= 1.0:
        return False
    if float(risk.get("avoid_thin_volume", 0.0)) >= 1.0:
        return False
    if float(regime.get("volatility_regime", 0.0)) >= 1.0 and float(regime.get("risk_on_proxy", 0.0)) < 1.0:
        return False

    dry_up = float(volume.get("volume_dry_up", 0.0)) >= 1.0 or float(volume.get("volume_percentile", 1.0)) < 0.7
    compression = (
        float(price.get("compression_10d", 0.0)) >= 0.35
        or float(volatility.get("vol_compression_percentile", 0.0)) >= 0.3
    )
    structure_break = float(price.get("close_location_value", 0.0)) >= 0.5
    expansion = (
        float(continuation.get("breakout_continuation", 0.0)) >= 1.0
        or float(volume.get("volume_percentile", 0.0)) >= 0.65
        or float(price.get("range_expansion", 0.0)) >= 0.02
    )
    return dry_up and compression and structure_break and expansion


def run_stable_family_template_repair_v3() -> dict[str, object]:
    RESEARCH_V3_ROOT.mkdir(parents=True, exist_ok=True)
    templates: list[dict[str, object]] = []
    repairs: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []
    quarantine_overlap = 0

    for template in V3_TEMPLATES:
        overlap = is_quarantined_signature(template.stable_family_template_id)
        if overlap:
            quarantine_overlap += 1
            quality_flags.append(
                record_with_hash(
                    {
                        "artifact_type": "stable_family_template_quality_flag_v3",
                        "flag_id": "quarantine_overlap",
                        "family_id": template.stable_family_template_id,
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
        record = template_record(template)
        templates.append(record)
        if template.stable_family_template_id == STABLE_FAMILY_VOLUME:
            repairs.append(
                record_with_hash(
                    {
                        "artifact_type": "stable_family_template_repair_v3",
                        "repair_id": "volume_dry_up_contradictory_rules",
                        "family_id": template.stable_family_template_id,
                        "issue": "V2 required volume_dry_up and volume_percentile>1.0 simultaneously",
                        "fix": "matches_volume_dry_up_v3 uses dry-up then structure break without spike",
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )

    status = "stable_family_templates_repaired_v3"
    summary = {
        "artifact_type": "stable_family_template_repair_v3_summary",
        "stable_family_template_repair_v3_version": "dopey-public-stable-family-template-repair-v3",
        "stable_family_template_repair_status": status,
        "template_count": len(templates),
        "volume_template_enabled": True,
        "continuation_template_enabled": True,
        "quarantine_overlap_count": quarantine_overlap,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STABLE_TEMPLATES_PATH, templates)
    write_jsonl_file(REPAIRS_PATH, repairs)
    write_jsonl_file(QUALITY_PATH, quality_flags)
    write_stage_proof(PROOF_PATH, "stable-family-template-repair-v3", status, summary)
    return {**summary, "artifact_paths": {"stable_family_template_repair_v3_summary": str(SUMMARY_PATH)}}


def template_record(template: StableFamilyTemplateV3) -> dict[str, object]:
    return record_with_hash(
        {
            "artifact_type": "stable_family_template_v3",
            "stable_family_template_id": template.stable_family_template_id,
            "direction": template.direction,
            "family_type": template.family_type,
            "feature_requirements": list(template.feature_requirements),
            "direction_logic": template.direction_logic,
            "entry_setup": template.entry_setup,
            "stop_target_logic": template.stop_target_logic,
            "dte_default": template.dte_default,
            "moneyness_default": template.moneyness_default,
            "exit_policy": template.exit_policy,
            "risk_filters": list(template.risk_filters),
            "no_trade_filters": list(template.no_trade_filters),
            "min_symbol_coverage": template.min_symbol_coverage,
            "min_sector_coverage": template.min_sector_coverage,
            "min_sample_target": template.min_sample_target,
            "public_data_only": True,
            **live_safety_fields(),
        },
        "record_hash",
    )


def load_v3_templates() -> list[StableFamilyTemplateV3]:
    return list(V3_TEMPLATES)
