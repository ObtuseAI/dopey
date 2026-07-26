"""CLI runner for breakthrough validator bridge."""
from __future__ import annotations

import json

from .open_data_breakthrough_validator_bridge import run_open_data_breakthrough_validator_bridge


def main() -> int:
    result = run_open_data_breakthrough_validator_bridge()
    print(json.dumps({
        "valid_real_dataset": result["valid_real_dataset"],
        "options_validation_status": result["options_validation_status"],
        "quote_priced_backtest_allowed": result["quote_priced_backtest_allowed"],
        "summary_path": result["artifact_paths"]["open_data_validator_bridge_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

