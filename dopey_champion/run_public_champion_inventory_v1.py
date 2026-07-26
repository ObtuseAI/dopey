"""CLI runner for public champion inventory V1."""
from __future__ import annotations

import json

from dopey_champion.public_champion_inventory_v1 import run_public_champion_inventory_v1


def main() -> int:
    summary = run_public_champion_inventory_v1()
    print(json.dumps({
        "public_champion_inventory_status": summary["public_champion_inventory_status"],
        "public_paper_champion_count": summary["public_paper_champion_count"],
        "champion_names": summary["champion_names"],
        "summary_path": summary["artifact_paths"]["public_champion_inventory_v1_summary"],
        "live_trading_enabled": summary["live_trading_enabled"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
