"""CLI runner for symbol/sector density scheduler V2."""
from __future__ import annotations

import json

from .symbol_sector_density_scheduler_v2 import run_symbol_sector_density_scheduler_v2


def main() -> int:
    summary = run_symbol_sector_density_scheduler_v2()
    print(json.dumps({
        "symbol_sector_density_status": summary["symbol_sector_density_status"],
        "covered_symbol_count": summary["covered_symbol_count"],
        "covered_sector_count": summary["covered_sector_count"],
        "summary_path": summary["artifact_paths"]["symbol_sector_density_scheduler_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
