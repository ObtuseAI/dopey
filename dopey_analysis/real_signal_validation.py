"""Compatibility wrapper for real signal validation gate."""
from __future__ import annotations

from typing import Any

from .real_signal_validation_gate import (
    REAL_DIRECTIONAL_SETUP_RECORDS_PATH,
    REAL_SIGNAL_QUALITY_FLAGS_PATH,
    REAL_SIGNAL_RECORDS_PATH,
    REAL_SIGNAL_VALIDATION_INPUT_PATH,
    REAL_SIGNAL_VALIDATION_PROOF_PATH,
    REAL_SIGNAL_VALIDATION_SUMMARY_PATH,
    SIGNAL_FAMILIES,
    build_real_signal_validation_gate,
)


def build_real_signal_validation() -> dict[str, Any]:
    return build_real_signal_validation_gate()
