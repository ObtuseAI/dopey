"""CLI runner for public feature miner V1."""
from __future__ import annotations

import json

from .public_feature_miner_v1 import run_public_feature_miner_v1


def main() -> int:
    summary = run_public_feature_miner_v1()
    print(json.dumps({
        "public_feature_miner_status": summary["public_feature_miner_status"],
        "feature_count": summary["feature_count"],
        "symbol_count": summary["symbol_count"],
        "summary_path": summary["artifact_paths"]["public_feature_miner_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
