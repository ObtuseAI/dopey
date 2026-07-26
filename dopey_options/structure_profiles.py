"""Deterministic option-structure profiles for DOPEY.

These profiles are fixture-only metadata. They do not price live options, connect to a
broker, or authorize execution.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


STRUCTURE_PROFILE_VERSION = "dopey-structure-profiles-v1"


@dataclass(frozen=True)
class StructureProfile:
    structure_type: str
    execution_structure: str
    family_hint: str
    leg_count: int
    risk_policy: str
    directional_bias: str
    volatility_bias: str
    allowed_for_families: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


SUPPORTED_STRUCTURE_TYPES: tuple[str, ...] = (
    "long_call_vertical",
    "long_put_vertical",
    "long_straddle_proxy",
    "long_strangle_proxy",
    "iron_condor_proxy",
    "credit_spread_pair_proxy",
    "butterfly_proxy",
    "short_dte_debit_spread_proxy",
)


def build_structure_profiles() -> dict[str, StructureProfile]:
    return {
        "long_call_vertical": StructureProfile(
            "long_call_vertical",
            "vertical",
            "directional_convexity",
            2,
            "defined_risk_debit",
            "bullish",
            "moderate_positive_vega",
            ["directional_convexity", "short_duration_defined_risk"],
        ),
        "long_put_vertical": StructureProfile(
            "long_put_vertical",
            "vertical",
            "directional_convexity",
            2,
            "defined_risk_debit",
            "bearish",
            "moderate_positive_vega",
            ["directional_convexity"],
        ),
        "long_straddle_proxy": StructureProfile(
            "long_straddle_proxy",
            "strangle",
            "volatility_expansion",
            2,
            "long_premium_defined_loss",
            "neutral",
            "positive_vega",
            ["volatility_expansion"],
        ),
        "long_strangle_proxy": StructureProfile(
            "long_strangle_proxy",
            "strangle",
            "volatility_expansion",
            2,
            "long_premium_defined_loss",
            "neutral",
            "positive_vega",
            ["volatility_expansion"],
        ),
        "iron_condor_proxy": StructureProfile(
            "iron_condor_proxy",
            "iron_condor",
            "volatility_compression",
            4,
            "defined_risk_credit",
            "neutral",
            "negative_vega",
            ["volatility_compression"],
        ),
        "credit_spread_pair_proxy": StructureProfile(
            "credit_spread_pair_proxy",
            "iron_condor",
            "volatility_compression",
            4,
            "defined_risk_credit",
            "neutral",
            "negative_vega",
            ["volatility_compression"],
        ),
        "butterfly_proxy": StructureProfile(
            "butterfly_proxy",
            "butterfly",
            "short_duration_defined_risk",
            3,
            "defined_risk_debit",
            "pin_or_mild_directional",
            "low_vega",
            ["short_duration_defined_risk"],
        ),
        "short_dte_debit_spread_proxy": StructureProfile(
            "short_dte_debit_spread_proxy",
            "vertical",
            "short_duration_defined_risk",
            2,
            "defined_risk_debit",
            "bullish",
            "low_vega",
            ["short_duration_defined_risk"],
        ),
    }


def profile_for_structure(structure_type: str) -> StructureProfile:
    profiles = build_structure_profiles()
    if structure_type not in profiles:
        raise ValueError(f"unsupported structure_type: {structure_type}")
    return profiles[structure_type]
