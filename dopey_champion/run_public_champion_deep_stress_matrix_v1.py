"""CLI runner for public champion deep stress matrix V1."""
from __future__ import annotations

import json

from dopey_champion.public_champion_deep_stress_matrix_v1 import run_public_champion_deep_stress_matrix_v1


def main() -> int:
    summary = run_public_champion_deep_stress_matrix_v1()
    print(json.dumps({
        "deep_stress_status": summary["deep_stress_status"],
        "champions_tested": summary["champions_tested"],
        "stress_case_count": summary["stress_case_count"],
        "champions_survived_core": summary["champions_survived_core"],
        "champions_failed": summary["champions_failed"],
        "summary_path": summary["artifact_paths"]["public_champion_deep_stress_matrix_v1_summary"],
        "live_trading_enabled": summary["live_trading_enabled"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
