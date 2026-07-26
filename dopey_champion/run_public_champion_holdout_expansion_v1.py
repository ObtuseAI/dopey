"""CLI runner for public champion holdout expansion V1."""
from __future__ import annotations

import json

from dopey_champion.public_champion_holdout_expansion_v1 import run_public_champion_holdout_expansion_v1


def main() -> int:
    summary = run_public_champion_holdout_expansion_v1()
    print(json.dumps({
        "holdout_expansion_status": summary["holdout_expansion_status"],
        "champions_tested": summary["champions_tested"],
        "holdout_count": summary["holdout_count"],
        "holdout_survivor_count": summary["holdout_survivor_count"],
        "summary_path": summary["artifact_paths"]["public_champion_holdout_expansion_v1_summary"],
        "live_trading_enabled": summary["live_trading_enabled"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
