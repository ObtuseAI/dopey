"""CLI runner for autonomous open-data validator bridge."""
from __future__ import annotations

import json

from .autonomous_open_data_validator_bridge import run_autonomous_open_data_validator_bridge


def main() -> int:
    result = run_autonomous_open_data_validator_bridge()
    print(json.dumps({
        "autonomous_open_data_status": result["autonomous_open_data_status"],
        "valid_real_dataset": result["valid_real_dataset"],
        "history_activation_status": result["history_activation_status"],
        "real_signal_validation_status": result["real_signal_validation_status"],
        "summary_path": result["artifact_paths"]["autonomous_open_data_validator_bridge_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

