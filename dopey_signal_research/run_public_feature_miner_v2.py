"""CLI runner for public feature miner V2."""
from __future__ import annotations

import json

from .public_feature_miner_v2 import run_public_feature_miner_v2


def main() -> int:
    summary = run_public_feature_miner_v2()
    print(json.dumps({
        "public_feature_miner_v2_status": summary["public_feature_miner_v2_status"],
        "feature_count": summary["feature_count"],
        "symbol_count": summary["symbol_count"],
        "sector_count": summary["sector_count"],
        "summary_path": summary["artifact_paths"]["public_feature_miner_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
