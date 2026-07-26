"""CLI runner for S-tier options benchmark."""
from __future__ import annotations

import json

from .s_tier_options_benchmark import run_s_tier_options_benchmark


def main() -> int:
    result = run_s_tier_options_benchmark()
    print(json.dumps({
        "s_tier_benchmark_status": result["s_tier_benchmark_status"],
        "s_tier_engineering_progress": result["s_tier_engineering_progress"],
        "live_readiness_claim": result["live_readiness_claim"],
        "summary_path": result["artifact_paths"]["s_tier_options_benchmark_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

