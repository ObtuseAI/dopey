"""CLI runner for public-first market lake promotion."""
from __future__ import annotations

import json

from .market_lake_public_promotion import run_market_lake_public_promotion


def main() -> int:
    summary = run_market_lake_public_promotion(True)
    print(json.dumps({
        "active_lake_status": summary["active_lake_status"],
        "active_symbols_public": summary["active_symbols_public"],
        "active_symbols_fixture": summary["active_symbols_fixture"],
        "public_rows_active": summary["public_rows_active"],
        "summary_path": summary["artifact_paths"]["market_lake_public_promotion_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
