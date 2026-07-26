"""Defined-risk policy checks for deterministic DOPEY structures."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


DEFINED_RISK_POLICY_VERSION = "dopey-defined-risk-structures-v1"

UNSAFE_STRUCTURE_TYPES: frozenset[str] = frozenset({
    "naked_call",
    "naked_put",
    "naked_short_call",
    "naked_short_put",
    "short_straddle",
    "short_strangle",
    "undefined_risk_short_vol",
})


@dataclass(frozen=True)
class StructureSafetyDecision:
    structure_type: str
    safe: bool
    verdict: str
    reasons: list[str] = field(default_factory=list)
    policy_version: str = DEFINED_RISK_POLICY_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def validate_defined_risk_structure(
    structure_type: str,
    allow_undefined_risk: bool,
    legs: list[dict],
) -> StructureSafetyDecision:
    reasons: list[str] = []
    if structure_type in UNSAFE_STRUCTURE_TYPES:
        reasons.append("explicit undefined-risk structure type is forbidden")
    if allow_undefined_risk:
        reasons.append("allow_undefined_risk=true is forbidden in this bundle")
    short_count = sum(1 for leg in legs if leg.get("side") == "sell")
    long_count = sum(1 for leg in legs if leg.get("side") == "buy")
    if short_count > 0 and long_count == 0:
        reasons.append("short option legs require offsetting long protection")
    if any(bool(leg.get("naked", False)) for leg in legs):
        reasons.append("naked leg marker is forbidden")
    safe = len(reasons) == 0
    return StructureSafetyDecision(
        structure_type=structure_type,
        safe=safe,
        verdict="defined_risk" if safe else "unsafe_rejected",
        reasons=reasons,
    )
