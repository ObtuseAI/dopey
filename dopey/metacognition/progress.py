"""Estimate whether more research can reduce uncertainty."""

from __future__ import annotations


def expected_information_gain(
    unknown_fraction: float,
    missing_data_recoverability: float,
    duplication_pressure: float,
) -> float:
    values = {
        "unknown_fraction": unknown_fraction,
        "missing_data_recoverability": missing_data_recoverability,
        "duplication_pressure": duplication_pressure,
    }
    invalid = {name: value for name, value in values.items() if not 0.0 <= value <= 1.0}
    if invalid:
        raise ValueError(f"progress inputs must be within [0, 1]: invalid={invalid}")
    gain = unknown_fraction * missing_data_recoverability * (1.0 - duplication_pressure)
    return round(gain, 6)
