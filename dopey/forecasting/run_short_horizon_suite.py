"""CLI for independently scored one-to-five-session equity forecasts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .operational import run_short_horizon_equity_distribution_suite


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--benchmark-symbol", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    arguments = parser.parse_args()
    result = run_short_horizon_equity_distribution_suite(
        str(arguments.symbol),
        str(arguments.benchmark_symbol),
        Path(arguments.output_root),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
