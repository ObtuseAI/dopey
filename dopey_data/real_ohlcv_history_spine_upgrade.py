"""Compatibility wrapper for the real OHLCV history activation gate."""
from __future__ import annotations

from typing import Any

from .real_ohlcv_history_spine_activation import (
    REAL_OHLCV_HISTORY_ACTIVATION_BLOCKERS_PATH,
    REAL_OHLCV_HISTORY_ACTIVATION_PROOF_PATH as REAL_OHLCV_HISTORY_SPINE_PROOF_PATH,
    REAL_OHLCV_HISTORY_ACTIVATION_QUALITY_FLAGS_PATH as REAL_OHLCV_HISTORY_QUALITY_FLAGS_PATH,
    REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH as REAL_OHLCV_HISTORY_SPINE_UPGRADE_PATH,
    REAL_OHLCV_HISTORY_SYMBOL_COVERAGE_PATH,
    build_real_ohlcv_history_spine_activation,
)


def build_real_ohlcv_history_spine_upgrade() -> dict[str, Any]:
    result = build_real_ohlcv_history_spine_activation()
    activation = result["activation"]
    upgrade = {
        **activation,
        "artifact_type": "real_ohlcv_history_spine_upgrade",
        "history_spine_status": "valid_real_history_spine" if activation["valid_real_dataset"] else "missing_real_dataset",
        "history_spine_upgrade_status": activation["history_spine_activation_status"],
        "upgrade_version": "dopey-real-ohlcv-history-spine-upgrade-compat-v1",
    }
    return {
        "upgrade": upgrade,
        "coverage": result["symbol_coverage"],
        "quality_flags": result["quality_flags"],
        "activation_blockers": result["blockers"],
        "proof": result["proof"],
    }
