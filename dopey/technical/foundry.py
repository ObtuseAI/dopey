"""Unified versioned technical primitive registry."""

from __future__ import annotations

from .batch_a import BATCH_A_SPECS, IndicatorSpec
from .batch_b import BATCH_B_SPECS
from .batch_c import BATCH_C_SPECS
from .batch_d import BATCH_D_SPECS


ALL_TECHNICAL_SPECS: tuple[IndicatorSpec, ...] = (
    BATCH_A_SPECS + BATCH_B_SPECS + BATCH_C_SPECS + BATCH_D_SPECS
)


def validate_foundry_registry(specs: tuple[IndicatorSpec, ...]) -> None:
    identifiers = [spec.indicator for spec in specs]
    duplicates = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
    if duplicates:
        raise ValueError(f"technical foundry indicator identities must be unique: duplicates={duplicates}")
    for spec in specs:
        if spec.required_lookback <= 0 or spec.warmup_period < 0:
            raise ValueError(
                "technical foundry lookbacks must be valid: "
                f"indicator={spec.indicator}, required={spec.required_lookback}, warmup={spec.warmup_period}"
            )
        if not spec.formula_version:
            raise ValueError(f"technical foundry formula version is required: indicator={spec.indicator}")


validate_foundry_registry(ALL_TECHNICAL_SPECS)
