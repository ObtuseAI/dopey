"""Compatibility CLI for the real OHLCV history activation gate."""
from __future__ import annotations

import json
from typing import Any

from .run_real_ohlcv_history_spine_activation import run_real_ohlcv_history_spine_activation


def run_real_ohlcv_history_spine_upgrade() -> dict[str, Any]:
    result = run_real_ohlcv_history_spine_activation()
    return {
        **result,
        "history_spine_status": "valid_real_history_spine" if result["valid_real_dataset"] else "missing_real_dataset",
        "history_spine_upgrade_status": result["history_spine_activation_status"],
    }


def main() -> int:
    result = run_real_ohlcv_history_spine_upgrade()
    print(json.dumps({
        "history_spine_upgrade_status": result["history_spine_upgrade_status"],
        "valid_real_dataset": result["valid_real_dataset"],
        "real_history_used": result["real_history_used"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
